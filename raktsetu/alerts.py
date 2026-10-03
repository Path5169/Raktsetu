"""Donor calls: wave alerts and an atomic first-to-accept, same pattern as unit reservation."""
import threading
from datetime import date, datetime, timedelta
from .compat import GROUPS, donors_for
from .db import connect, log
from .dispatch import km
from .donors import eligibility

WAVES = [(5, 8), (5, 15), (10, 40)]   # (donors to alert, radius in km): nearest 5 first, then widen
WAVE_TIMEOUT_MIN = 10                 # nobody accepted in this time -> next wave
LOW_STOCK, TARGET_STOCK = 2, 4        # city holds <= 2 units of a group -> call donors to bring it back to 4

class AlertError(ValueError): pass

def _now(now): return (now or datetime.now()).isoformat(timespec="seconds")

def candidates(conn, call, today=None):
    """Eligible, verified donors who can help and are not already alerted or booked.
    Order: exact group first, then substitutes (least versatile first), then nearest."""
    today = today or date.today()
    rank = {call["blood_group"]: 0} if call["exact_only"] else {g: i for i, g in enumerate(donors_for(call["blood_group"], call["component"]))}
    rows = conn.execute("SELECT * FROM donors WHERE verified=1 AND lat IS NOT NULL "
                        "AND id NOT IN (SELECT donor_id FROM call_alerts WHERE call_id=?) "
                        "AND id NOT IN (SELECT donor_id FROM donations WHERE status='pledged')", (call["id"],)).fetchall()
    out = [(rank[d["blood_group"]], km(call["lat"], call["lon"], d["lat"], d["lon"]), d) for d in rows
           if d["blood_group"] in rank and eligibility(d, call["component"], today)["eligible"]]
    return sorted(out, key=lambda t: (t[0], t[1]))

def send_next_wave(conn, call_id, now=None):
    """Alert the next wave. A wave with nobody to alert is skipped straight away, nobody waits for an empty wave."""
    call = conn.execute("SELECT * FROM donor_calls WHERE id=?", (call_id,)).fetchone()
    alerted = []
    while call["wave"] < len(WAVES) and not alerted:
        count, radius = WAVES[call["wave"]]
        picks = [t for t in candidates(conn, call, (now or datetime.now()).date()) if t[1] <= radius][:count]
        wave = call["wave"] + 1
        for _, dist, d in picks:
            conn.execute("INSERT INTO call_alerts(call_id,donor_id,wave,sent_at,km) VALUES(?,?,?,?,?)", (call_id, d["id"], wave, _now(now), round(dist, 1)))
            alerted.append({"donor_id": d["id"], "name": d["name"], "blood_group": d["blood_group"], "km": round(dist, 1), "phone": d["phone"], "wave": wave})
        conn.execute("UPDATE donor_calls SET wave=?,wave_started=? WHERE id=?", (wave, _now(now), call_id))
        log(conn, "system", "WAVE_SENT", f"call #{call_id}: wave {wave}, {len(picks)} donor(s) alerted within {radius} km")
        call = conn.execute("SELECT * FROM donor_calls WHERE id=?", (call_id,)).fetchone()
    conn.commit()
    return alerted

def _nearest_bank(conn, lat, lon):
    banks = conn.execute("SELECT * FROM banks ORDER BY open_24x7 DESC, id").fetchall()
    return min((b for b in banks if b["open_24x7"] == banks[0]["open_24x7"]), key=lambda b: km(lat, lon, b["lat"], b["lon"]))

def open_call(conn, group, component="RBC", slots=1, lat=None, lon=None, bank_id=None, request_id=None, exact_only=False, reason="", actor="system", now=None):
    """Open a donor call and send wave 1. If an identical call is already open, return that one instead."""
    if group not in GROUPS: raise AlertError(f"Unknown blood group {group}.")
    if slots < 1: raise AlertError("A call needs at least one slot.")
    ex = conn.execute("SELECT * FROM donor_calls WHERE status='open' AND blood_group=? AND component=? AND exact_only=?", (group, component, int(exact_only))).fetchone()
    if ex: return {"call_id": ex["id"], "existing": True, "alerted": [], "slots": ex["slots_needed"]}
    bank = conn.execute("SELECT * FROM banks WHERE id=?", (bank_id,)).fetchone() if bank_id else _nearest_bank(conn, lat, lon)
    lat, lon = (lat, lon) if lat is not None else (bank["lat"], bank["lon"])
    cid = conn.execute("INSERT INTO donor_calls(request_id,bank_id,blood_group,component,exact_only,slots_needed,lat,lon,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (request_id, bank["id"], group, component, int(exact_only), slots, lat, lon, reason, _now(now))).lastrowid
    log(conn, actor, "CALL_OPENED", f"#{cid}: {slots} x {group} {component} donor(s) at {bank['name']}. {reason}"); conn.commit()
    return {"call_id": cid, "existing": False, "alerted": send_next_wave(conn, cid, now), "slots": slots, "bank": bank["name"]}

def scan_low_stock(conn, now=None):
    """Call donors for every red-cell group the city is nearly out of. Exact-group donors only, so nobody is pulled from a scarcer group."""
    opened = []
    for g in GROUPS:
        per = {r["bank_id"]: r["n"] for r in conn.execute("SELECT bank_id, COUNT(*) n FROM units WHERE status='available' AND component='RBC' AND blood_group=? GROUP BY bank_id", (g,))}
        n = sum(per.values())
        if n > LOW_STOCK: continue
        banks = conn.execute("SELECT * FROM banks WHERE open_24x7=1 ORDER BY id").fetchall()
        bank = min(banks, key=lambda b: (per.get(b["id"], 0), b["id"]))   # the open bank holding the least
        r = open_call(conn, g, "RBC", TARGET_STOCK - n, bank_id=bank["id"], exact_only=True, reason=f"{g} stock is critically low ({n} unit{'s' if n != 1 else ''} in the city).", now=now)
        if not r["existing"]: opened.append({**r, "blood_group": g})
    return opened

def tick(conn, now=None, force=False):
    """Escalate overdue calls to the next wave; close a call once every wave has timed out. force=True skips the wait (demo)."""
    now, moved = now or datetime.now(), []
    for c in conn.execute("SELECT * FROM donor_calls WHERE status='open' AND wave>0").fetchall():
        if not force and now - datetime.fromisoformat(c["wave_started"]) < timedelta(minutes=WAVE_TIMEOUT_MIN): continue
        if c["wave"] < len(WAVES):
            moved.append({"call_id": c["id"], "alerted": send_next_wave(conn, c["id"], now)})
        elif conn.execute("UPDATE donor_calls SET status='closed' WHERE id=? AND status='open'", (c["id"],)).rowcount:
            log(conn, "system", "CALL_CLOSED", f"call #{c['id']}: all waves timed out, {c['slots_filled']}/{c['slots_needed']} filled"); conn.commit()
            moved.append({"call_id": c["id"], "closed": True})
    return moved

def _covered(conn, call_id, donor_id, why):
    conn.rollback()
    log(conn, f"donor:{donor_id}", "ACCEPT_REJECTED", f"call #{call_id}: {why}"); conn.commit()
    return {"won": False, "covered": True, "message": "Already covered. Another donor got there first. Thank you for being ready to help."}

def accept(conn, call_id, donor_id, now=None, today=None):
    """First donors to accept fill the slots. The check and the slot grab happen inside one BEGIN IMMEDIATE
    transaction, and the slot UPDATE is guarded (slots_filled < slots_needed), so a slot can never be given twice."""
    if conn.in_transaction: conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        call = conn.execute("SELECT c.*, b.name bank FROM donor_calls c JOIN banks b ON b.id=c.bank_id WHERE c.id=?", (call_id,)).fetchone()
        al = conn.execute("SELECT response FROM call_alerts WHERE call_id=? AND donor_id=?", (call_id, donor_id)).fetchone()
        if not call: raise AlertError("Unknown request.")
        if not al: raise AlertError("This request was not sent to you.")
        if al["response"] == "accepted":
            conn.rollback(); return {"won": True, "already": True, "bank": call["bank"], "message": f"You have already accepted. Please go to {call['bank']}."}
        if call["status"] != "open": return _covered(conn, call_id, donor_id, f"call is {call['status']}")
        if conn.execute("SELECT 1 FROM donations WHERE donor_id=? AND status='pledged'", (donor_id,)).fetchone():
            raise AlertError("You already have a donation waiting to be confirmed by a blood bank.")
        d = conn.execute("SELECT * FROM donors WHERE id=?", (donor_id,)).fetchone()
        el = eligibility(d, call["component"], today)
        if not el["eligible"]: raise AlertError("You are not eligible right now. " + " ".join(el["reasons"]))
        got = conn.execute("UPDATE donor_calls SET slots_filled=slots_filled+1, status=CASE WHEN slots_filled+1>=slots_needed THEN 'covered' ELSE 'open' END "
                           "WHERE id=? AND status='open' AND slots_filled<slots_needed", (call_id,)).rowcount
        if got != 1: return _covered(conn, call_id, donor_id, "no slot left")
        conn.execute("UPDATE call_alerts SET response='accepted' WHERE call_id=? AND donor_id=?", (call_id, donor_id))
        conn.execute("INSERT INTO donations(donor_id,bank_id,call_id,status,created_at) VALUES(?,?,?,'pledged',?)", (donor_id, call["bank_id"], call_id, _now(now)))
        filled = call["slots_filled"] + 1
        log(conn, f"donor:{donor_id}", "CALL_ACCEPTED", f"call #{call_id}: {d['name']} ({d['blood_group']}) to {call['bank']}, slot {filled}/{call['slots_needed']}")
        if filled >= call["slots_needed"]: log(conn, "system", "CALL_COVERED", f"call #{call_id}: all {filled} slot(s) filled")
        conn.commit()
        return {"won": True, "bank": call["bank"], "slot": filled, "of": call["slots_needed"],
                "message": f"You are confirmed. Please go to {call['bank']}; they will verify your donation."}
    except Exception:
        conn.rollback(); raise

def decline(conn, call_id, donor_id):
    n = conn.execute("UPDATE call_alerts SET response='declined' WHERE call_id=? AND donor_id=? AND response IS NULL", (call_id, donor_id)).rowcount
    if n: log(conn, f"donor:{donor_id}", "CALL_DECLINED", f"call #{call_id}")
    conn.commit()
    return n

def list_calls(conn, include_closed=False):
    q = ("SELECT c.*, b.name bank, h.name hospital, (SELECT COUNT(*) FROM call_alerts a WHERE a.call_id=c.id) alerted, "
         "(SELECT COUNT(*) FROM call_alerts a WHERE a.call_id=c.id AND a.response='declined') declined "
         "FROM donor_calls c JOIN banks b ON b.id=c.bank_id LEFT JOIN requests r ON r.id=c.request_id LEFT JOIN hospitals h ON h.id=r.hospital_id")
    rows = conn.execute(q + ("" if include_closed else " WHERE c.status IN ('open','covered') AND c.created_at > ?") + " ORDER BY c.id DESC LIMIT 20",
                        () if include_closed else ((datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds"),)).fetchall()
    return [dict(r) for r in rows]

def calls_for_donor(conn, donor_id, now=None):
    """What a donor sees: calls sent to them in the last 24h, open ones first. Covered ones read 'already covered'."""
    since = ((now or datetime.now()) - timedelta(hours=24)).isoformat(timespec="seconds")
    rows = conn.execute("SELECT c.id, c.blood_group, c.component, c.slots_needed, c.slots_filled, c.status, c.reason, c.created_at, b.name bank, a.km, a.wave, a.response, h.name hospital "
                        "FROM call_alerts a JOIN donor_calls c ON c.id=a.call_id JOIN banks b ON b.id=c.bank_id LEFT JOIN requests r ON r.id=c.request_id LEFT JOIN hospitals h ON h.id=r.hospital_id "
                        "WHERE a.donor_id=? AND c.created_at > ? ORDER BY (c.status='open') DESC, c.id DESC", (donor_id, since)).fetchall()
    return [dict(r) for r in rows]

def alert_text(name, a, call):
    return f"[mock SMS to {name}] Urgent: {call['blood_group']} blood needed {a['km']} km away at {call['bank']}. Open RaktSetu to accept."

def race_accept(call_id):
    """Every donor alerted for this call taps Accept at the same instant. Reports the result, then restores the call."""
    conn = connect()
    before = conn.execute("SELECT slots_needed,slots_filled,status FROM donor_calls WHERE id=?", (call_id,)).fetchone()
    if not before: raise AlertError("Unknown call.")
    ids = [r[0] for r in conn.execute("SELECT donor_id FROM call_alerts WHERE call_id=? AND response IS NULL", (call_id,))]
    out, gate = [], threading.Barrier(max(1, len(ids)))
    def go(did):
        c = connect(); gate.wait()
        try: out.append((did, accept(c, call_id, did)))
        except AlertError as e: out.append((did, {"won": False, "error": str(e)}))
        finally: c.close()
    ts = [threading.Thread(target=go, args=(i,)) for i in ids]
    [t.start() for t in ts]; [t.join() for t in ts]
    winners = [d for d, r in out if r.get("won")]
    marks = ",".join("?" * len(winners)) or "NULL"
    conn.execute(f"DELETE FROM donations WHERE call_id=? AND status='pledged' AND donor_id IN ({marks})", (call_id, *winners))
    conn.execute(f"UPDATE call_alerts SET response=NULL WHERE call_id=? AND donor_id IN ({marks})", (call_id, *winners))
    conn.execute("UPDATE donor_calls SET slots_filled=?,status=? WHERE id=?", (before["slots_filled"], before["status"], call_id))
    free = before["slots_needed"] - before["slots_filled"]
    log(conn, "system", "ACCEPT_RACE_TEST", f"call #{call_id}: {len(ids)} donors, {free} slot(s), {len(winners)} won"); conn.commit(); conn.close()
    return {"donors": len(ids), "slots": free, "won": len(winners), "covered": len(ids) - len(winners), "overbooked": max(0, len(winners) - free)}
