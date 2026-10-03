import unittest, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["RAKTSETU_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from raktsetu import db, dispatch, inventory as inv, seed

def reset(units=()):
    conn = db.connect(); seed.seed(conn); conn.execute("DELETE FROM units")
    for bank, g, comp, q in units: inv.add_units(conn, bank, g, comp, q)
    return conn

class Dispatch(unittest.TestCase):
    def test_race_one_unit_twenty_requests(self):
        conn = reset([(1, "B-", "RBC", 1)])
        r = dispatch.race("B-", "RBC", 20)
        self.assertEqual((r["served"], r["turned_away"], r["oversold"]), (1, 19, 0))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM units WHERE status='available'").fetchone()[0], 1)  # restored
    def test_unverified_hospital_blocked(self):
        conn = reset([(1, "A+", "RBC", 3)])
        with self.assertRaises(dispatch.Blocked): dispatch.create_request(conn, 3, "A+", "RBC", 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM units WHERE status='reserved'").fetchone()[0], 0)
    def test_exact_match_beats_closer_substitute(self):
        conn = reset([(1, "A+", "RBC", 1), (4, "O+", "RBC", 5)])
        h = conn.execute("SELECT * FROM hospitals WHERE id=1").fetchone()
        top = dispatch.rank_banks(conn, h, "A+", "RBC", 1)[0]
        self.assertEqual(top["bank_id"], 1)
    def test_universal_donor_is_last_resort(self):
        conn = reset([(4, "O-", "RBC", 5), (2, "A-", "RBC", 1)])
        r = dispatch.create_request(conn, 1, "A+", "RBC", 1)
        self.assertEqual(r["bank"]["bank_id"], 2)
    def test_partial_supply_not_offered(self):
        conn = reset([(1, "A+", "RBC", 1)])
        self.assertEqual(dispatch.create_request(conn, 1, "A+", "RBC", 2)["status"], "unfulfilled")
    def test_hold_expires_back_to_stock(self):
        conn = reset([(1, "A+", "RBC", 1)])
        r = dispatch.create_request(conn, 1, "A+", "RBC", 1)
        conn.execute("UPDATE units SET reserved_until='2000-01-01T00:00:00' WHERE request_id=?", (r["request_id"],)); conn.commit()
        self.assertEqual(dispatch.release_holds(conn), 1)
    def test_issue_and_cancel(self):
        conn = reset([(1, "A+", "RBC", 2)])
        a = dispatch.create_request(conn, 1, "A+", "RBC", 1); b = dispatch.create_request(conn, 1, "A+", "RBC", 1)
        self.assertEqual(dispatch.issue(conn, a["request_id"]), 1); self.assertEqual(dispatch.cancel(conn, b["request_id"]), 1)
        self.assertEqual(sorted(r[0] for r in conn.execute("SELECT status FROM units")), ["available", "issued"])

if __name__ == "__main__": unittest.main()
