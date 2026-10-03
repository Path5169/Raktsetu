import argparse, os, sys
from datetime import date
from . import db, dispatch, inventory as inv, seed as seeder
from .compat import GROUPS, SHELF_LIFE_DAYS, donors_for, recipients_for, reach

USE = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
def c(t, code): return f"\033[{code}m{t}\033[0m" if USE else str(t)
RED, GRN, YEL, DIM, BOLD, CYA = 31, 32, 33, 2, 1, 36

def find_bank(conn, key):
    rows = conn.execute("SELECT id,name FROM banks WHERE CAST(id AS TEXT)=? OR LOWER(name) LIKE ?", (key, f"%{key.lower()}%")).fetchall()
    if len(rows) != 1: sys.exit(f"Bank '{key}' matched {len(rows)} banks. Use id or a unique name part.")
    return rows[0]

def cmd_init(a, conn):
    seeder.seed(conn)
    print(c("Demo data loaded: 4 banks, 3 hospitals, 8 donors, units across all groups.", GRN))
    print("Try:  python -m raktsetu stock")

def cmd_stock(a, conn):
    inv.sweep(conn)
    banks, m = conn.execute("SELECT id,name FROM banks ORDER BY id").fetchall(), inv.stock_matrix(conn, a.component)
    names = [b["name"].split(" Blood")[0][:12] for b in banks]
    print(c(f"\n{a.component} stock as of {date.today():%d %b %Y}", BOLD))
    print(c("Group  " + "".join(f"{n:>14}" for n in names) + f"{'Total':>8}", DIM))
    for g in GROUPS:
        cells, tot = [], 0
        for b in banks:
            n = m.get((b["id"], g), 0); tot += n
            cells.append(c(f"{n:>14}", RED if n == 0 else YEL if n <= 2 else GRN))
        print(f"{g:<7}" + "".join(cells) + c(f"{tot:>8}", RED if tot <= 2 else BOLD))
    print(c("\nred = none   yellow = 1-2 left", DIM))

def cmd_expiring(a, conn):
    inv.sweep(conn)
    rows = inv.expiring(conn, a.days)
    print(c(f"\nUnits expiring within {a.days} days (issue these first: FEFO)", BOLD))
    if not rows: return print(c("Nothing close to expiry.", GRN))
    print(c(f"{'Bank':<30}{'Group':<7}{'Type':<6}{'Qty':>4}  {'Expires':<12}Left", DIM))
    for r in rows:
        left = (date.fromisoformat(r["expires_on"]) - date.today()).days
        col = RED if left <= 1 else YEL if left <= 3 else GRN
        print(f"{r['bank']:<30}{r['blood_group']:<7}{r['component']:<6}{r['n']:>4}  {r['expires_on']:<12}" + c("today" if left == 0 else f"{left}d", col))

def cmd_compat(a, conn):
    g = a.group.upper()
    if g not in GROUPS: sys.exit(f"Unknown group. Use one of: {' '.join(GROUPS)}")
    print(c(f"\nPatient {g} ({a.component}) can receive from, best first:", BOLD))
    for i, d in enumerate(donors_for(g, a.component), 1):
        note = "exact match" if d == g else "universal donor, keep for those who need it" if reach(d) == 8 and a.component == "RBC" else "substitute"
        print(f"  {i}. {d:<4} {c(note, DIM)}")
    if a.component == "RBC":
        print(f"\nDonor {g} can give to: {', '.join(recipients_for(g))}")

def cmd_add(a, conn):
    b, g = find_bank(conn, a.bank), a.group.upper()
    exp = inv.add_units(conn, b["id"], g, a.component, a.qty)
    print(c(f"Added {a.qty} x {g} {a.component} to {b['name']}. Expires {exp}.", GRN))

def cmd_audit(a, conn):
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (a.n,)).fetchall()
    print(c("\nAudit log (newest first)", BOLD))
    for r in rows: print(f"{r['ts']}  {r['actor']:<10} {r['action']:<12} {c(r['detail'], DIM)}")

def cmd_request(a, conn):
    rows = conn.execute("SELECT id,name FROM hospitals WHERE CAST(id AS TEXT)=? OR LOWER(name) LIKE ?", (a.hospital, f"%{a.hospital.lower()}%")).fetchall()
    if len(rows) != 1: sys.exit(f"Hospital '{a.hospital}' matched {len(rows)}. Use id or a unique name part.")
    h, g = rows[0], a.group.upper()
    try: r = dispatch.create_request(conn, h["id"], g, a.component, a.qty)
    except (dispatch.Blocked, ValueError) as e: sys.exit(c(str(e), RED))
    print(c(f"\nRequest #{r['request_id']}: {a.qty} x {g} {a.component} for {h['name']}", BOLD))
    for i, o in enumerate(r["ranking"], 1):
        print(f"{i}. {o['bank']:<30}{o['km']:>5} km  score {o['score']:>3}  " + c("; ".join(o["why"]), DIM))
    if r["status"] == "reserved":
        for lb in r["fallthroughs"]: print(c(f"Lost the race at {lb}, rerouted.", YEL))
        print(c(f"\nReserved at {r['bank']['bank']} ({r['bank']['units']}). Held until {r['hold_until'][11:16]}.", GRN))
    else: print(c("\nNo bank can supply this right now.", RED))

def cmd_race(a, conn):
    r = dispatch.race(a.group.upper(), a.component, a.n)
    print(c(f"\n{r['requests']} simultaneous requests for {a.group.upper()} {a.component}, {r['supply']} compatible unit(s) in the city", BOLD))
    print(f"served {r['served']}   turned away {r['turned_away']}   rerouted {r['rerouted']}   " + c(f"oversold {r['oversold']}", GRN if not r["oversold"] else RED))
    print(c("Stock restored after the test.", DIM))

def cmd_serve(a, conn):
    from .server import run
    conn.close(); run(a.port, not a.no_browser)

def main():
    p = argparse.ArgumentParser(prog="raktsetu", description="RaktSetu: live blood network (Phase 1 CLI)")
    sub = p.add_subparsers(dest="cmd", required=True)
    comp = lambda s: s.add_argument("--component", "-c", choices=SHELF_LIFE_DAYS, default="RBC")
    sub.add_parser("init", help="create DB and load demo data").set_defaults(f=cmd_init)
    s = sub.add_parser("stock", help="stock by blood group per bank"); comp(s); s.set_defaults(f=cmd_stock)
    s = sub.add_parser("expiring", help="units close to expiry"); s.add_argument("--days", type=int, default=2); s.set_defaults(f=cmd_expiring)
    s = sub.add_parser("compat", help="who can give to / receive from"); s.add_argument("group"); comp(s); s.set_defaults(f=cmd_compat)
    s = sub.add_parser("add", help="add units to a bank"); s.add_argument("bank"); s.add_argument("group"); s.add_argument("qty", type=int, nargs="?", default=1); comp(s); s.set_defaults(f=cmd_add)
    s = sub.add_parser("audit", help="show audit log"); s.add_argument("-n", type=int, default=10); s.set_defaults(f=cmd_audit)
    s = sub.add_parser("request", help="emergency request: rank banks and reserve"); s.add_argument("hospital"); s.add_argument("group"); s.add_argument("qty", type=int, nargs="?", default=1); comp(s); s.set_defaults(f=cmd_request)
    s = sub.add_parser("race", help="simultaneous-request test"); s.add_argument("group"); s.add_argument("-n", type=int, default=20); comp(s); s.set_defaults(f=cmd_race)
    s = sub.add_parser("serve", help="open the web UI"); s.add_argument("--port", type=int, default=8000); s.add_argument("--no-browser", action="store_true"); s.set_defaults(f=cmd_serve)
    a = p.parse_args()
    conn = db.connect()
    try:
        a.f(a, conn)
    except ValueError as e:
        sys.exit(str(e))
