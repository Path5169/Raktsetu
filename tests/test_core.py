import unittest, sqlite3, sys, os
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from raktsetu import compat, db, inventory as inv, seed

def fresh():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA); seed.seed(conn); return conn

class Compat(unittest.TestCase):
    def test_universal_donor_and_recipient(self):
        self.assertEqual(set(compat.recipients_for("O-")), set(compat.GROUPS))
        self.assertEqual(set(compat.donors_for("AB+")), set(compat.GROUPS))
    def test_known_pairs(self):
        self.assertTrue(compat.can_donate("O+", "A+")); self.assertFalse(compat.can_donate("A+", "O+"))
        self.assertFalse(compat.can_donate("B+", "B-")); self.assertFalse(compat.can_donate("A-", "B-"))
    def test_exact_first_and_universal_last(self):
        order = compat.donors_for("A+")
        self.assertEqual(order[0], "A+"); self.assertEqual(order[-1], "O-")
    def test_platelets_abo_identical(self):
        self.assertEqual(set(compat.donors_for("B-", "PLT")), {"B-", "B+"})

class Inventory(unittest.TestCase):
    def test_shelf_life(self):
        conn = fresh(); d = date(2026, 10, 3)
        self.assertEqual(inv.add_units(conn, 1, "A+", "PLT", 1, d), d + timedelta(days=5))
        self.assertEqual(inv.add_units(conn, 1, "A+", "RBC", 1, d), d + timedelta(days=42))
    def test_sweep_expires_old_units(self):
        conn = fresh(); inv.add_units(conn, 1, "A+", "PLT", 3, date.today() - timedelta(days=9))
        self.assertGreaterEqual(inv.sweep(conn), 3)
    def test_fefo_order(self):
        rows = inv.expiring(fresh(), 42)
        self.assertEqual([r["expires_on"] for r in rows], sorted(r["expires_on"] for r in rows))
    def test_audit_written(self):
        conn = fresh(); inv.add_units(conn, 1, "O+", "RBC", 2)
        self.assertEqual(conn.execute("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()[0], "ADD_UNITS")

if __name__ == "__main__": unittest.main()
