"""Demo data around Nagpur. All names and licence numbers are fictional."""
import random
from datetime import date, timedelta
from .compat import GROUPS, SHELF_LIFE_DAYS
from .db import log

BANKS = [("Orange City Blood Bank", 21.1498, 79.0806, 1), ("Lifeline Blood Centre", 21.1290, 79.1120, 1),
         ("Sanjeevani Blood Bank", 21.1702, 79.0577, 0), ("Central Hospital Blood Bank", 21.1458, 79.0882, 1)]
HOSPITALS = [("Nagpur City Hospital", 21.1610, 79.0750, "MH-HSP-1001", 1), ("Riverside Medical", 21.1180, 79.0450, "MH-HSP-1002", 1),
             ("Unverified Clinic", 21.1400, 79.1300, "MH-HSP-9999", 0)]
DONORS = [("Aarav Deshmukh", "B-", 21.15, 79.09, 120), ("Sneha Patil", "O+", 21.14, 79.08, 20), ("Rohan Kulkarni", "A+", 21.16, 79.07, 200),
          ("Meera Joshi", "B-", 21.13, 79.10, 95), ("Imran Sheikh", "O-", 21.12, 79.06, 150), ("Kavya Nair", "AB+", 21.17, 79.09, 60),
          ("Vikram Rathod", "B+", 21.15, 79.11, 300), ("Pooja Wankhede", "A-", 21.14, 79.05, 15)]
WEIGHT = {"O+": 9, "B+": 8, "A+": 6, "AB+": 2, "O-": 1.2, "B-": 1, "A-": 1, "AB-": 0.4}
BANK_SCALE = {1: 1.0, 2: 0.7, 3: 0.5, 4: 1.3}
B_NEG_DRAMA = {1: 0, 2: 0, 3: 1, 4: 1}   # city is nearly out of B-: great for the demo

def seed(conn, today=None):
    rng, today = random.Random(7), today or date.today()
    for t in ("units", "banks", "hospitals", "donors"): conn.execute(f"DELETE FROM {t}")
    for i, b in enumerate(BANKS, 1): conn.execute("INSERT INTO banks VALUES(?,?,?,?,?)", (i, *b))
    for i, h in enumerate(HOSPITALS, 1): conn.execute("INSERT INTO hospitals VALUES(?,?,?,?,?,?)", (i, *h))
    for i, (n, g, la, lo, ago) in enumerate(DONORS, 1):
        conn.execute("INSERT INTO donors VALUES(?,?,?,?,?,?,1)", (i, n, g, la, lo, (today - timedelta(days=ago)).isoformat()))
    for bid in BANK_SCALE:
        for comp, max_age in (("RBC", 40), ("PLT", 4)):
            for g in GROUPS:
                k = 1 if comp == "RBC" else 0.35
                n = round(WEIGHT[g] * BANK_SCALE[bid] * k * rng.uniform(0.6, 1.4))
                if comp == "RBC" and g == "B-": n = B_NEG_DRAMA[bid]
                for _ in range(n):
                    col = today - timedelta(days=rng.randint(0, max_age))
                    conn.execute("INSERT INTO units(bank_id,blood_group,component,collected_on,expires_on) VALUES(?,?,?,?,?)",
                                 (bid, g, comp, col.isoformat(), (col + timedelta(days=SHELF_LIFE_DAYS[comp])).isoformat()))
    log(conn, "system", "SEED", "demo data loaded")
    conn.commit()
