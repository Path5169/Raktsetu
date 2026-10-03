"""Donor side: eligibility (NBTC rules), profile with badges and streak, mock OTP login.

Rules are INDICATIVE. A doctor decides at the donation camp (haemoglobin, BP, pulse,
medical history are checked there, not here).
"""
import hashlib, hmac, random, secrets
from datetime import date, datetime, timedelta
from .db import log

# Source: NBTC / MoHFW "Guidelines for Blood Donor Selection and Blood Donor Referral" (Feb 2025);
# nbtc.naco.gov.in eligibility page. Whole blood: age 18-65 (first-time donors 60 or younger),
# weight 45 kg+, gap 90 days (men) / 120 days (women).
# Platelets (apheresis): age 18-60, weight 50 kg+. The apheresis rules also say a platelet donor is not
# accepted within 28 days of a whole-blood donation; we use 28 days as the gap for both sexes.
RULES = {
    "RBC": {"min_age": 18, "max_age": 65, "first_max_age": 60, "min_kg": 45, "gap": {"M": 90, "F": 120}},
    "PLT": {"min_age": 18, "max_age": 60, "first_max_age": 60, "min_kg": 50, "gap": {"M": 28, "F": 28}},
}
BADGES = [(1, "First Drop"), (3, "Regular"), (5, "Lifesaver"), (10, "Champion")]
STREAK_BREAK_DAYS = 183     # a streak survives gaps of up to about 6 months
OTP_MOCK = True             # mock mode: the code is returned to the caller instead of sent by SMS
OTP_TTL_MIN, OTP_MAX_TRIES, SESSION_HOURS = 5, 5, 12

class AuthError(Exception): pass

def age_on(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def _birthday(dob, year):
    try: return dob.replace(year=year)
    except ValueError: return date(year, 3, 1)   # 29 Feb in a non-leap year

def eligibility(donor, component="RBC", today=None):
    """Return {eligible, reasons, next_date, days_left, age, gap_days}.
    next_date is set only when waiting is the one thing standing in the way."""
    today, R = today or date.today(), RULES[component]
    if not donor["dob"] or not donor["weight_kg"] or donor["sex"] not in ("M", "F"):
        return {"eligible": False, "reasons": ["Profile incomplete: age, sex and weight are needed."], "next_date": None, "days_left": None, "age": None, "gap_days": None}
    dob, sex = date.fromisoformat(donor["dob"]), donor["sex"]
    age, gap = age_on(dob, today), R["gap"][sex]
    reasons, dates, other = [], [], False
    first_time = not donor["last_donation"]
    if age < R["min_age"]:
        d18 = _birthday(dob, dob.year + R["min_age"])
        reasons.append(f"Under {R['min_age']}. Can donate from {d18:%d %b %Y}."); dates.append(d18)
    elif age > R["max_age"]:
        reasons.append(f"Over {R['max_age']}, the upper age limit."); other = True
    elif first_time and age > R["first_max_age"]:
        reasons.append(f"First-time donors must be {R['first_max_age']} or younger."); other = True
    if donor["weight_kg"] < R["min_kg"]:
        reasons.append(f"Weight is below {R['min_kg']} kg."); other = True
    if not first_time:
        ready = date.fromisoformat(donor["last_donation"]) + timedelta(days=gap)
        if today < ready:
            who = "men" if sex == "M" else "women"
            reasons.append(f"Last donated {date.fromisoformat(donor['last_donation']):%d %b %Y}. The gap is {gap} days for {who}.")
            dates.append(ready)
    nxt = max(dates) if dates and not other else None
    return {"eligible": not reasons, "reasons": reasons, "next_date": nxt.isoformat() if nxt else None,
            "days_left": (nxt - today).days if nxt else None, "age": age, "gap_days": gap}

def badge_info(n):
    earned = [b for b in BADGES if n >= b[0]]
    nxt = next((b for b in BADGES if n < b[0]), None)
    return {"name": earned[-1][1] if earned else None, "donations": n,
            "next": {"name": nxt[1], "needs": nxt[0] - n} if nxt else None}

def streak(dates, today=None):
    """Donations in a row with no gap over ~6 months, counted back from the latest. Zero if the latest is older than that."""
    today, ds = today or date.today(), sorted(dates, reverse=True)
    if not ds or (today - ds[0]).days > STREAK_BREAK_DAYS: return 0
    n = 1
    for a, b in zip(ds, ds[1:]):
        if (a - b).days > STREAK_BREAK_DAYS: break
        n += 1
    return n

def get_donor(conn, donor_id):
    d = conn.execute("SELECT * FROM donors WHERE id=?", (donor_id,)).fetchone()
    if not d: raise ValueError("Unknown donor.")
    return d

def record_donation(conn, donor_id, bank_id, on, verified=True):
    """Add a donation. Only verified donations count towards eligibility, badges and streaks."""
    conn.execute("INSERT INTO donations(donor_id,bank_id,donated_on,status,created_at) VALUES(?,?,?,?,?)",
                 (donor_id, bank_id, on.isoformat(), "verified" if verified else "pledged", datetime.now().isoformat(timespec="seconds")))
    if verified: _refresh_last(conn, donor_id)
    conn.commit()

def _refresh_last(conn, donor_id):
    conn.execute("UPDATE donors SET last_donation=(SELECT MAX(donated_on) FROM donations WHERE donor_id=? AND status='verified') WHERE id=?", (donor_id, donor_id))

def verify_donation(conn, donation_id, actor="bank"):
    """A blood bank confirms the donor really gave blood. Until then it does not count."""
    d = conn.execute("SELECT * FROM donations WHERE id=?", (donation_id,)).fetchone()
    if not d or d["status"] != "pledged": raise ValueError("No pending donation with that id.")
    conn.execute("UPDATE donations SET status='verified',donated_on=? WHERE id=?", (date.today().isoformat(), donation_id))
    _refresh_last(conn, d["donor_id"])
    log(conn, actor, "DONATION_VERIFIED", f"donation #{donation_id} for donor #{d['donor_id']}"); conn.commit()

def pending_donations(conn):
    """Return pledged donations for the Phase 5 blood-bank verification queue."""
    rows = conn.execute("""SELECT dn.id, dn.created_at, dn.donated_on, d.name donor, d.blood_group,
                                  d.phone, b.name bank, c.id call_id, c.reason
                           FROM donations dn
                           JOIN donors d ON d.id=dn.donor_id
                           LEFT JOIN banks b ON b.id=dn.bank_id
                           LEFT JOIN donor_calls c ON c.id=dn.call_id
                           WHERE dn.status='pledged'
                           ORDER BY dn.created_at ASC""").fetchall()
    return [dict(r) for r in rows]

def donation_summary(conn):
    """Small operational summary for the bank dashboard."""
    return {
        "pending": conn.execute("SELECT COUNT(*) FROM donations WHERE status='pledged'").fetchone()[0],
        "verified_today": conn.execute("SELECT COUNT(*) FROM donations WHERE status='verified' AND donated_on=?", (date.today().isoformat(),)).fetchone()[0],
        "verified_total": conn.execute("SELECT COUNT(*) FROM donations WHERE status='verified'").fetchone()[0],
    }

def profile(conn, donor_id, component="RBC", today=None):
    today, d = today or date.today(), get_donor(conn, donor_id)
    rows = conn.execute("SELECT dn.id, dn.donated_on, dn.status, dn.created_at, b.name bank FROM donations dn LEFT JOIN banks b ON b.id=dn.bank_id "
                        "WHERE dn.donor_id=? AND dn.status!='cancelled' ORDER BY COALESCE(dn.donated_on, dn.created_at) DESC", (donor_id,)).fetchall()
    done = [date.fromisoformat(r["donated_on"]) for r in rows if r["status"] == "verified"]
    el = eligibility(d, component, today)
    last = date.fromisoformat(d["last_donation"]) if d["last_donation"] else None
    el["progress"] = min(1.0, (today - last).days / el["gap_days"]) if last and el["gap_days"] else 1.0
    return {"id": d["id"], "name": d["name"], "blood_group": d["blood_group"], "sex": d["sex"], "weight_kg": d["weight_kg"],
            "eligibility": el, "badge": badge_info(len(done)), "streak": streak(done, today), "last_donation": d["last_donation"],
            "history": [{"id": r["id"], "date": r["donated_on"], "status": r["status"], "bank": r["bank"]} for r in rows]}

# ---------- mock OTP login ----------
def norm_phone(p):
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    if len(digits) < 10: raise ValueError("Enter a 10-digit mobile number.")
    return digits[-10:]

def _hash(phone, code): return hashlib.sha256(f"{phone}:{code}".encode()).hexdigest()

def send_otp(conn, phone, now=None, code=None):
    now, phone = now or datetime.now(), norm_phone(phone)
    if not conn.execute("SELECT 1 FROM donors WHERE phone=?", (phone,)).fetchone():
        raise ValueError("No donor is registered with this number.")
    code = code or f"{random.SystemRandom().randrange(10 ** 6):06d}"
    conn.execute("INSERT OR REPLACE INTO otp_codes(phone,code_hash,expires_at,attempts) VALUES(?,?,?,0)",
                 (phone, _hash(phone, code), (now + timedelta(minutes=OTP_TTL_MIN)).isoformat(timespec="seconds")))
    log(conn, f"phone:{phone[-4:]}", "OTP_SENT", "mock SMS"); conn.commit()
    out = {"phone": phone, "expires_in_min": OTP_TTL_MIN}
    if OTP_MOCK: out["demo_otp"] = code   # a real SMS gateway would never return the code
    return out

def verify_otp(conn, phone, code, now=None):
    now, phone = now or datetime.now(), norm_phone(phone)
    row = conn.execute("SELECT * FROM otp_codes WHERE phone=?", (phone,)).fetchone()
    if not row: raise ValueError("Ask for a code first.")
    if now.isoformat(timespec="seconds") > row["expires_at"]:
        conn.execute("DELETE FROM otp_codes WHERE phone=?", (phone,)); conn.commit(); raise ValueError("That code has expired. Ask for a new one.")
    if row["attempts"] >= OTP_MAX_TRIES:
        raise ValueError("Too many wrong tries. Ask for a new code.")
    if not hmac.compare_digest(row["code_hash"], _hash(phone, str(code).strip())):
        conn.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE phone=?", (phone,))
        log(conn, f"phone:{phone[-4:]}", "OTP_FAILED", f"{row['attempts'] + 1} wrong tr{'y' if row['attempts'] == 0 else 'ies'}"); conn.commit()
        left = OTP_MAX_TRIES - row["attempts"] - 1
        raise ValueError(f"Wrong code. {left} tr{'y' if left == 1 else 'ies'} left." if left else "Too many wrong tries. Ask for a new code.")
    donor = conn.execute("SELECT id,name FROM donors WHERE phone=?", (phone,)).fetchone()
    token = secrets.token_urlsafe(24)
    conn.execute("DELETE FROM otp_codes WHERE phone=?", (phone,))
    conn.execute("INSERT INTO sessions(token,donor_id,expires_at) VALUES(?,?,?)", (token, donor["id"], (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")))
    log(conn, f"donor:{donor['id']}", "DONOR_LOGIN", donor["name"]); conn.commit()
    return {"token": token, "donor_id": donor["id"], "name": donor["name"]}

def session_donor(conn, token, now=None):
    now = (now or datetime.now()).isoformat(timespec="seconds")
    row = conn.execute("SELECT donor_id,expires_at FROM sessions WHERE token=?", (token or "",)).fetchone()
    if not row or row["expires_at"] < now: raise AuthError("Please log in again.")
    return row["donor_id"]

def find_donor(conn, key):
    """CLI helper: id, phone or unique part of the name."""
    k = str(key)
    rows = conn.execute("SELECT * FROM donors WHERE CAST(id AS TEXT)=? OR phone=? OR LOWER(name) LIKE ?", (k, "".join(c for c in k if c.isdigit())[-10:] or "-", f"%{k.lower()}%")).fetchall()
    if len(rows) != 1: raise ValueError(f"Donor '{key}' matched {len(rows)} donors. Use id, phone or a unique name part.")
    return rows[0]
