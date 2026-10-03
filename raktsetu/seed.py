"""Demo data around Nagpur. All names and licence numbers are fictional."""
import random
from datetime import date, timedelta
from .compat import GROUPS, SHELF_LIFE_DAYS
from .db import log
from .auth import make_password

BANKS = [
    ("Orange City Blood Bank", 21.1498, 79.0806, 1), ("Lifeline Blood Centre", 21.1290, 79.1120, 1),
    ("Sanjeevani Blood Bank", 21.1702, 79.0577, 0), ("Central Hospital Blood Bank", 21.1458, 79.0882, 1),
    ("Vidarbha Red Cross Centre", 21.1340, 79.0680, 1), ("MediCare Blood Services", 21.1820, 79.1180, 1)
]
HOSPITALS = [
    ("Nagpur City Hospital", 21.1610, 79.0750, "MH-HSP-1001", 1), ("Riverside Medical", 21.1180, 79.0450, "MH-HSP-1002", 1),
    ("Alexis Multispeciality Hospital", 21.1450, 79.1040, "MH-HSP-1003", 0), ("Wockhardt Medical Centre", 21.1320, 79.0900, "MH-HSP-1004", 1),
    ("Government Medical College Hospital", 21.1470, 79.0880, "MH-HSP-1005", 1), ("CarePoint Trauma Hospital", 21.1770, 79.1020, "MH-HSP-1006", 1),
    ("Sahyadri Community Hospital", 21.1100, 79.1150, "MH-HSP-1007", 1), ("Unverified Clinic", 21.1400, 79.1300, "MH-HSP-9999", 0)
]
# name, group, lat, lon, sex, age, kg, days-ago of each past donation (newest first)
DONORS = [("Aarav Deshmukh", "B-", 21.15, 79.09, "M", 32, 76, [120, 250, 380]), ("Sneha Patil", "O+", 21.14, 79.08, "F", 27, 54, [20, 150]),
          ("Rohan Kulkarni", "A+", 21.16, 79.07, "M", 45, 82, [200]), ("Meera Joshi", "B-", 21.13, 79.10, "F", 30, 57, [95, 230]),
          ("Imran Sheikh", "O-", 21.12, 79.06, "M", 35, 70, [150, 290]), ("Kavya Nair", "AB+", 21.17, 79.09, "F", 29, 62, [60, 200]),
          ("Vikram Rathod", "B+", 21.15, 79.11, "M", 52, 88, [300]), ("Pooja Wankhede", "A-", 21.14, 79.05, "F", 25, 50, [15]),
          ("Nikhil Bhoyar", "B-", 21.18, 79.08, "M", 29, 72, [140, 270]), ("Ritu Sahu", "B-", 21.12, 79.09, "F", 31, 58, [200]),
          ("Tejas Raut", "O-", 21.19, 79.10, "M", 26, 68, [110, 240, 370]), ("Divya Gajbhiye", "O-", 21.10, 79.07, "F", 34, 61, [260]),
          ("Farhan Qureshi", "O+", 21.13, 79.13, "M", 38, 80, [100]), ("Anjali Thakre", "A+", 21.15, 79.04, "F", 24, 43, []),
          ("Sunil Bawane", "A+", 21.17, 79.12, "M", 67, 70, [400, 560]), ("Tanvi Gaikwad", "O+", 21.14, 79.09, "F", 17, 52, []),
          ("Harsh Mishra", "A-", 21.16, 79.06, "M", 41, 78, [95, 190, 285, 380, 475]), ("Shweta Dhoke", "B+", 21.11, 79.11, "F", 28, 55, [130]),
          ("Omkar Lande", "AB-", 21.20, 79.05, "M", 33, 74, []), ("Nisha Verma", "AB+", 21.09, 79.14, "F", 36, 66, [300, 430])]
DONORS += [
    ("Aditya Mahajan", "O+", 21.18, 79.08, "M", 39, 79, [100]), ("Isha Borkar", "A-", 21.16, 79.11, "F", 28, 56, [150]),
    ("Rahul Zade", "B+", 21.10, 79.09, "M", 34, 73, [210]), ("Neha Tiwari", "O-", 21.13, 79.06, "F", 31, 59, [140]),
    ("Manav Soni", "A+", 21.19, 79.12, "M", 27, 68, [105]), ("Sakshi Kale", "B-", 21.08, 79.10, "F", 29, 55, [180]),
    ("Yash Chavan", "O+", 21.15, 79.13, "M", 43, 81, [300]), ("Priya Nandurkar", "AB+", 21.12, 79.07, "F", 26, 52, [90]),
    ("Kunal Pande", "A+", 21.20, 79.11, "M", 30, 77, [125]), ("Ayesha Khan", "O+", 21.09, 79.06, "F", 37, 64, [200]),
    ("Dhruv Shinde", "B+", 21.17, 79.05, "M", 24, 65, []), ("Riya Meshram", "O-", 21.11, 79.13, "F", 33, 60, [115])
]
WEIGHT = {"O+": 9, "B+": 8, "A+": 6, "AB+": 2, "O-": 1.2, "B-": 1, "A-": 1, "AB-": 0.4}
BANK_SCALE = {1: 1.0, 2: 0.7, 3: 0.5, 4: 1.3, 5: 0.8, 6: 0.9}
B_NEG_DRAMA = {1: 0, 2: 0, 3: 1, 4: 1, 5: 0, 6: 1}   # city is nearly out of B-: great for the demo

def _dob(today, age):
    """A birthday of 15 March, placed so the donor is exactly `age` today (a 17-year-old turns 18 on the coming 15 March)."""
    y = today.year - age
    return date(y if (today.month, today.day) >= (3, 15) else y - 1, 3, 15).isoformat()

def seed(conn, today=None):
    rng, today = random.Random(7), today or date.today()
    for t in ("units", "requests", "banks", "hospitals", "donors", "donations", "donor_calls", "call_alerts", "otp_codes", "sessions", "users", "user_sessions"): conn.execute(f"DELETE FROM {t}")
    for i, b in enumerate(BANKS, 1): conn.execute("INSERT INTO banks VALUES(?,?,?,?,?)", (i, *b))
    for i, h in enumerate(HOSPITALS, 1): conn.execute("INSERT INTO hospitals VALUES(?,?,?,?,?,?)", (i, *h))
    for i, (n, g, la, lo, sex, age, kg, hist) in enumerate(DONORS, 1):
        conn.execute("INSERT INTO donors(id,name,blood_group,lat,lon,last_donation,verified,sex,dob,weight_kg,phone) VALUES(?,?,?,?,?,?,1,?,?,?,?)",
                     (i, n, g, la, lo, (today - timedelta(days=hist[0])).isoformat() if hist else None, sex, _dob(today, age), kg, f"90000{i:05d}"))
        for ago in hist:
            conn.execute("INSERT INTO donations(donor_id,bank_id,donated_on,status,created_at) VALUES(?,?,?,'verified',?)", (i, rng.randint(1, len(BANKS)), (today - timedelta(days=ago)).isoformat(), today.isoformat()))
    # Demo staff accounts. Passwords are intentionally simple for the local hackathon demo.
    accounts = [
        (1, "admin@raktsetu.demo", "Network Admin", "admin", None, None, "Admin@123"),
        *[(10+i, f"hospital{i}@raktsetu.demo", f"{HOSPITALS[i-1][0]} · Emergency Desk", "hospital", i, None, "Hospital@123") for i in (1,2,4,5,6,7)],
        *[(30+i, f"bank{i}@raktsetu.demo", f"{BANKS[i-1][0]} · Operator", "bank", None, i, "Bank@123") for i in range(1, 7)],
    ]
    for uid, username, display, role, hospital_id, bank_id, password in accounts:
        conn.execute("INSERT INTO users(id,username,password_hash,display_name,role,hospital_id,bank_id) VALUES(?,?,?,?,?,?,?)",
                     (uid, username, make_password(password), display, role, hospital_id, bank_id))

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
