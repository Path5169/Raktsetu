"""Emergency engine: rank banks, reserve atomically, reroute when a race is lost."""
import math, threading
from collections import Counter
from datetime import date, datetime, timedelta
from .compat import GROUPS, SHELF_LIFE_DAYS, donors_for, reach
from .db import connect, log

HOLD_MIN = 30
W = {"match": .30, "dist": .30, "expiry": .15, "open": .25}   # routing weights

class Blocked(Exception): pass

def km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))

def release_holds(conn):
    """Reservations past their hold time go back into stock."""
    now = datetime.now().isoformat(timespec="seconds")
    ids = [r[0] for r in conn.execute("SELECT DISTINCT request_id FROM units WHERE status='reserved' AND reserved_until < ?", (now,))]
    n = conn.execute("UPDATE units SET status='available',reserved_until=NULL,request_id=NULL WHERE status='reserved' AND reserved_until < ?", (now,)).rowcount
    for i in ids: conn.execute("UPDATE requests SET status='expired' WHERE id=? AND status='reserved'", (i,))
    if n: log(conn, "system", "HOLD_EXPIRED", f"{n} unit(s) back in stock")
    conn.commit()
    return n

def rank_banks(conn, hospital, group, component, qty, today=None):
    today, order, out = today or date.today(), donors_for(group, component), []
    for b in conn.execute("SELECT * FROM banks"):
        picked = []
        for g in order:   # exact group first, then substitutes; oldest unit first (FEFO)
            if len(picked) >= qty: break
            picked += conn.execute("SELECT id,blood_group,expires_on FROM units WHERE bank_id=? AND status='available' AND component=? AND blood_group=? ORDER BY expires_on LIMIT ?",
                                   (b["id"], component, g, qty - len(picked))).fetchall()
        if len(picked) < qty: continue   # bank cannot fully cover this request
        d = km(hospital["lat"], hospital["lon"], b["lat"], b["lon"])
        m = sum(1.0 if u["blood_group"] == group else .35 if component == "RBC" and reach(u["blood_group"]) == 8 else .7 for u in picked) / qty
        days = min((date.fromisoformat(u["expires_on"]) - today).days for u in picked)
        parts = {"match": m, "dist": max(0, 1 - d / 25), "expiry": 1 - min(days, 14) / 14, "open": 1.0 if b["open_24x7"] else 0.0}
        subs = sorted({u["blood_group"] for u in picked} - {group})
        why = [f"Exact {group} match" if not subs else f"Uses {', '.join(subs)}: no exact {group} here" + (" (universal donor, last resort)" if "O-" in subs else ""),
               f"{d:.1f} km from the hospital"]
        if days <= 3: why.append(f"Oldest unit expires in {days} day{'s' if days != 1 else ''}: using it avoids waste")
        if not b["open_24x7"]: why.append("Not open 24x7")
        out.append({"bank_id": b["id"], "bank": b["name"], "km": round(d, 1), "score": round(100 * sum(W[k] * v for k, v in parts.items())),
                    "unit_ids": [u["id"] for u in picked], "units": ", ".join(f"{n} x {g}" for g, n in Counter(u["blood_group"] for u in picked).items()), "why": why})
    return sorted(out, key=lambda o: -o["score"])

def _reserve(conn, unit_ids, request_id):
    """All-or-nothing. UPDATE ... WHERE status='available' inside BEGIN IMMEDIATE means
    two requests can never hold the same unit; the loser gets None and reroutes."""
    until = (datetime.now() + timedelta(minutes=HOLD_MIN)).isoformat(timespec="seconds")
    if conn.in_transaction: conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for uid in unit_ids:
            if conn.execute("UPDATE units SET status='reserved',reserved_until=?,request_id=? WHERE id=? AND status='available'", (until, request_id, uid)).rowcount != 1:
                conn.rollback(); return None
        conn.commit(); return until
    except Exception:
        conn.rollback(); raise

def create_request(conn, hospital_id, group, component="RBC", qty=1, actor=None, alert_donors=True):
    if group not in GROUPS: raise ValueError(f"Unknown blood group {group}.")
    if component not in SHELF_LIFE_DAYS: raise ValueError(f"Unknown component {component}.")
    h = conn.execute("SELECT * FROM hospitals WHERE id=?", (hospital_id,)).fetchone()
    if not h: raise Blocked("Unknown hospital.")
    actor = actor or f"hospital:{h['id']}"
    if not h["verified"]:
        log(conn, actor, "REQUEST_BLOCKED", f"{h['name']} is not verified"); conn.commit()
        raise Blocked(f"{h['name']} is not a verified hospital, so it cannot raise requests.")
    release_holds(conn)
    rid = conn.execute("INSERT INTO requests(hospital_id,blood_group,component,qty,status,created_at) VALUES(?,?,?,?,'open',?)",
                       (h["id"], group, component, qty, datetime.now().isoformat(timespec="seconds"))).lastrowid
    conn.commit()
    lost, first = [], None
    for _ in range(6):
        ranking = rank_banks(conn, h, group, component, qty)
        first = first if first is not None else ranking
        if not ranking: break
        best = ranking[0]
        until = _reserve(conn, best["unit_ids"], rid)
        if until:
            conn.execute("UPDATE requests SET status='reserved',bank_id=?,detail=? WHERE id=?", (best["bank_id"], best["units"], rid))
            log(conn, actor, "RESERVED", f"#{rid}: {best['units']} {component} at {best['bank']}" + (f" after losing {len(lost)} race(s)" if lost else ""))
            conn.commit()
            return {"request_id": rid, "status": "reserved", "bank": best, "hold_until": until, "fallthroughs": lost, "ranking": first[:4]}
        lost.append(best["bank"])
        log(conn, actor, "RACE_LOST", f"#{rid}: units at {best['bank']} were taken first, rerouting"); conn.commit()
    conn.execute("UPDATE requests SET status='unfulfilled' WHERE id=?", (rid,))
    log(conn, actor, "UNFULFILLED", f"#{rid}: no bank could supply {qty} x {group} {component}"); conn.commit()
    out = {"request_id": rid, "status": "unfulfilled", "fallthroughs": lost, "ranking": []}
    if alert_donors:   # nothing in stock: call compatible donors near the hospital (wave 1 goes out now)
        from . import alerts
        c = alerts.open_call(conn, group, component, qty, lat=h["lat"], lon=h["lon"], request_id=rid, actor=actor,
                             reason=f"Request #{rid} from {h['name']} could not be covered from stock.")
        out["donor_call"] = {"call_id": c["call_id"], "alerted": len(c["alerted"]), "existing": c["existing"]}
    return out

def _finish(conn, rid, unit_status, req_status):
    n = conn.execute("UPDATE units SET status=?,reserved_until=NULL" + (",request_id=NULL" if unit_status == "available" else "") + " WHERE request_id=? AND status='reserved'", (unit_status, rid)).rowcount
    conn.execute("UPDATE requests SET status=? WHERE id=?", (req_status, rid))
    log(conn, "system", req_status.upper(), f"#{rid}: {n} unit(s)"); conn.commit()
    return n

def issue(conn, rid): return _finish(conn, rid, "issued", "issued")
def cancel(conn, rid): return _finish(conn, rid, "available", "cancelled")

def race(group, component="RBC", n=6):
    """Fire n simultaneous requests from separate connections, report, then restore stock."""
    conn = connect()
    hosp = [r[0] for r in conn.execute("SELECT id FROM hospitals WHERE verified=1")]
    supply = sum(conn.execute("SELECT COUNT(*) FROM units WHERE status='available' AND component=? AND blood_group=?", (component, g)).fetchone()[0] for g in donors_for(group, component))
    out, gate = [], threading.Barrier(n)
    def go(i):
        c = connect(); gate.wait()
        try: out.append(create_request(c, hosp[i % len(hosp)], group, component, 1, actor="race-test", alert_donors=False))
        finally: c.close()
    ts = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in ts]; [t.join() for t in ts]
    won = [r for r in out if r["status"] == "reserved"]
    for r in won: cancel(conn, r["request_id"])
    log(conn, "system", "RACE_TEST", f"{n} requests, {supply} compatible unit(s), {len(won)} served"); conn.commit(); conn.close()
    return {"requests": n, "supply": supply, "served": len(won), "turned_away": n - len(won),
            "rerouted": sum(1 for r in out if r["fallthroughs"]), "oversold": max(0, len(won) - supply)}
