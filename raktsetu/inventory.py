from datetime import date, timedelta
from .compat import GROUPS, SHELF_LIFE_DAYS
from .db import log

def sweep(conn, today=None):
    """Mark past-expiry units as expired and audit it."""
    today = (today or date.today()).isoformat()
    n = conn.execute("UPDATE units SET status='expired' WHERE status='available' AND expires_on < ?", (today,)).rowcount
    if n:
        log(conn, "system", "EXPIRE_SWEEP", f"{n} unit(s) expired")
    conn.commit()
    return n

def add_units(conn, bank_id, group, component, qty=1, collected_on=None, actor=None):
    if group not in GROUPS: raise ValueError(f"unknown blood group {group}")
    if component not in SHELF_LIFE_DAYS: raise ValueError(f"unknown component {component}")
    collected = collected_on or date.today()
    expires = collected + timedelta(days=SHELF_LIFE_DAYS[component])
    for _ in range(qty):
        conn.execute("INSERT INTO units(bank_id,blood_group,component,collected_on,expires_on) VALUES(?,?,?,?,?)",
                     (bank_id, group, component, collected.isoformat(), expires.isoformat()))
    log(conn, actor or f"bank:{bank_id}", "ADD_UNITS", f"{qty} x {group} {component}, expires {expires}")
    conn.commit()
    return expires

def stock_matrix(conn, component):
    rows = conn.execute("SELECT bank_id, blood_group, COUNT(*) n FROM units WHERE status='available' AND component=? GROUP BY bank_id, blood_group", (component,))
    return {(r["bank_id"], r["blood_group"]): r["n"] for r in rows}

def expiring(conn, days=7, today=None):
    """Available units expiring within `days`, soonest first (FEFO order)."""
    today = today or date.today()
    return conn.execute("""SELECT b.name bank, u.blood_group, u.component, u.expires_on, COUNT(*) n
        FROM units u JOIN banks b ON b.id=u.bank_id
        WHERE u.status='available' AND u.expires_on <= ?
        GROUP BY u.bank_id, u.blood_group, u.component, u.expires_on
        ORDER BY u.expires_on, b.name""", ((today + timedelta(days=days)).isoformat(),)).fetchall()
