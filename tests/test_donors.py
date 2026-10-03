import unittest, os, sys, tempfile, time
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["RAKTSETU_DB"] = os.path.join(tempfile.mkdtemp(), "d.db")
from raktsetu import alerts, db, dispatch, donors as dn, inventory as inv, seed

TODAY = date(2026, 10, 3)

def donor(sex="M", age=30, kg=70, last=None, today=TODAY):
    """A donor row-like dict for the pure eligibility function."""
    return {"sex": sex, "dob": date(today.year - age, 1, 1).isoformat(), "weight_kg": kg,
            "last_donation": (today - timedelta(days=last)).isoformat() if last is not None else None}

def reset():
    conn = db.connect(); seed.seed(conn); return conn

def only_donors(conn, n, group="B-", lat=21.15, lon=79.09):
    """Replace all donors with n eligible, verified donors of one group, spread a little so distances differ."""
    for t in ("donors", "donations", "donor_calls", "call_alerts", "sessions", "otp_codes"): conn.execute(f"DELETE FROM {t}")
    for i in range(1, n + 1):
        conn.execute("INSERT INTO donors(id,name,blood_group,lat,lon,last_donation,verified,sex,dob,weight_kg,phone) VALUES(?,?,?,?,?,NULL,1,'M','1995-06-01',70,?)",
                     (i, f"Donor {i}", group, lat + i * 0.004, lon, f"91000{i:05d}"))
    conn.commit()

class Eligibility(unittest.TestCase):
    def e(self, d, comp="RBC"): return dn.eligibility(d, comp, TODAY)
    def test_men_90_days_women_120(self):
        self.assertTrue(self.e(donor("M", last=90))["eligible"])
        self.assertFalse(self.e(donor("M", last=89))["eligible"])
        self.assertFalse(self.e(donor("F", last=100))["eligible"])
        self.assertTrue(self.e(donor("F", last=120))["eligible"])
    def test_countdown(self):
        r = self.e(donor("F", last=95))
        self.assertEqual((r["days_left"], r["next_date"]), (25, (TODAY + timedelta(days=25)).isoformat()))
    def test_age_limits(self):
        self.assertFalse(self.e(donor(age=17))["eligible"]); self.assertTrue(self.e(donor(age=18))["eligible"])
        self.assertTrue(self.e(donor(age=65, last=200))["eligible"]); self.assertFalse(self.e(donor(age=66, last=200))["eligible"])
    def test_under_18_countdown_is_the_birthday(self):
        d = donor(age=17); d["dob"] = date(2009, 12, 1).isoformat()   # turns 18 on 1 Dec 2027
        self.assertEqual(self.e(d)["next_date"], "2027-12-01")
    def test_first_timer_over_60_deferred_but_repeat_donor_ok(self):
        self.assertFalse(self.e(donor(age=62))["eligible"]); self.assertTrue(self.e(donor(age=62, last=200))["eligible"])
    def test_weight(self):
        self.assertFalse(self.e(donor(kg=44))["eligible"]); self.assertTrue(self.e(donor(kg=45))["eligible"])
        self.assertIsNone(self.e(donor(kg=44))["next_date"])   # no date promised for something time will not fix
    def test_platelet_rules_stricter(self):
        d = donor(kg=47, age=62, last=200)
        self.assertTrue(self.e(d, "RBC")["eligible"]); self.assertFalse(self.e(d, "PLT")["eligible"])
    def test_incomplete_profile(self):
        self.assertFalse(dn.eligibility({"sex": None, "dob": None, "weight_kg": None, "last_donation": None}, "RBC", TODAY)["eligible"])

class Badges(unittest.TestCase):
    def test_tiers(self):
        self.assertIsNone(dn.badge_info(0)["name"]); self.assertEqual(dn.badge_info(1)["name"], "First Drop")
        self.assertEqual(dn.badge_info(5)["name"], "Lifesaver"); self.assertIsNone(dn.badge_info(10)["next"])
    def test_streak(self):
        ds = [TODAY - timedelta(days=x) for x in (95, 190, 285)]
        self.assertEqual(dn.streak(ds, TODAY), 3)
        self.assertEqual(dn.streak([TODAY - timedelta(days=x) for x in (95, 400)], TODAY), 1)   # gap too long
        self.assertEqual(dn.streak([TODAY - timedelta(days=200)], TODAY), 0)                    # lapsed

class Verification(unittest.TestCase):
    def test_pledge_does_not_count_until_bank_verifies(self):
        conn = reset(); only_donors(conn, 1)
        dn.record_donation(conn, 1, 1, date.today(), verified=False)
        self.assertIsNone(conn.execute("SELECT last_donation FROM donors WHERE id=1").fetchone()[0])
        self.assertEqual(dn.profile(conn, 1)["badge"]["donations"], 0)
        dn.verify_donation(conn, conn.execute("SELECT id FROM donations").fetchone()[0])
        self.assertEqual(conn.execute("SELECT last_donation FROM donors WHERE id=1").fetchone()[0], date.today().isoformat())
        self.assertEqual(dn.profile(conn, 1)["badge"]["donations"], 1)

class Otp(unittest.TestCase):
    def setUp(self): self.conn = reset(); self.phone = "9000000001"
    def test_login_flow(self):
        r = dn.send_otp(self.conn, "+91 90000 00001", code="123456")
        self.assertEqual(r["phone"], self.phone)
        s = dn.verify_otp(self.conn, self.phone, "123456")
        self.assertEqual(dn.session_donor(self.conn, s["token"]), s["donor_id"])
    def test_code_is_single_use(self):
        dn.send_otp(self.conn, self.phone, code="123456"); dn.verify_otp(self.conn, self.phone, "123456")
        with self.assertRaises(ValueError): dn.verify_otp(self.conn, self.phone, "123456")
    def test_unknown_number(self):
        with self.assertRaises(ValueError): dn.send_otp(self.conn, "9999999999")
    def test_lockout_after_five_wrong_tries(self):
        dn.send_otp(self.conn, self.phone, code="123456")
        for _ in range(5):
            with self.assertRaises(ValueError): dn.verify_otp(self.conn, self.phone, "000000")
        with self.assertRaises(ValueError): dn.verify_otp(self.conn, self.phone, "123456")   # right code, still locked
    def test_expiry(self):
        t = datetime(2026, 10, 3, 12, 0); dn.send_otp(self.conn, self.phone, now=t, code="123456")
        with self.assertRaises(ValueError): dn.verify_otp(self.conn, self.phone, "123456", now=t + timedelta(minutes=6))
    def test_bad_token_and_expired_session(self):
        with self.assertRaises(dn.AuthError): dn.session_donor(self.conn, "nope")
        dn.send_otp(self.conn, self.phone, code="123456"); s = dn.verify_otp(self.conn, self.phone, "123456")
        with self.assertRaises(dn.AuthError): dn.session_donor(self.conn, s["token"], now=datetime.now() + timedelta(hours=13))

class Waves(unittest.TestCase):
    def test_wave_one_is_nearest_five_eligible_compatible(self):
        conn = reset(); only_donors(conn, 8)
        conn.execute("UPDATE donors SET weight_kg=40 WHERE id=1")                       # nearest donor, but under weight
        conn.execute("UPDATE donors SET blood_group='A+' WHERE id=2")                   # incompatible with B-
        conn.execute("UPDATE donors SET last_donation=? WHERE id=3", (date.today().isoformat(),))   # donated today
        conn.commit()
        r = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)
        self.assertEqual([x["donor_id"] for x in r["alerted"]], [4, 5, 6, 7, 8])
    def test_exact_group_before_nearer_substitute(self):
        conn = reset(); only_donors(conn, 3, "O-")
        conn.execute("UPDATE donors SET blood_group='B-' WHERE id=3"); conn.commit()   # the farthest donor is the only exact match
        r = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)
        self.assertEqual(r["alerted"][0]["donor_id"], 3)
    def test_waves_widen_after_timeout_and_then_close(self):
        conn = reset(); only_donors(conn, 12); t0 = datetime.now()
        cid = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1, now=t0)["call_id"]
        self.assertEqual(alerts.tick(conn, now=t0 + timedelta(minutes=5)), [])           # too early
        moved = alerts.tick(conn, now=t0 + timedelta(minutes=11))
        self.assertEqual(len(moved[0]["alerted"]), 5)                                    # wave 2: the next five
        self.assertEqual(conn.execute("SELECT COUNT(DISTINCT donor_id) FROM call_alerts WHERE call_id=?", (cid,)).fetchone()[0], 10)
        alerts.tick(conn, now=t0 + timedelta(minutes=22))                                # wave 3: the last two
        self.assertEqual(conn.execute("SELECT wave FROM donor_calls WHERE id=?", (cid,)).fetchone()[0], 3)
        alerts.tick(conn, now=t0 + timedelta(minutes=33))
        self.assertEqual(conn.execute("SELECT status FROM donor_calls WHERE id=?", (cid,)).fetchone()[0], "closed")
    def test_radius_limits_a_wave(self):
        conn = reset(); only_donors(conn, 2)
        conn.execute("UPDATE donors SET lat=21.45 WHERE id=2"); conn.commit()          # about 33 km away: only reached in wave 3
        r = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)
        self.assertEqual([x["donor_id"] for x in r["alerted"]], [1])
        self.assertEqual([x["donor_id"] for x in alerts.tick(conn, force=True)[0]["alerted"]], [2])   # waves 2 is empty, skipped
    def test_duplicate_open_call_is_not_created(self):
        conn = reset(); only_donors(conn, 3)
        a = alerts.open_call(conn, "B-", "RBC", 1, bank_id=1, lat=21.15, lon=79.09); b = alerts.open_call(conn, "B-", "RBC", 1, bank_id=1, lat=21.15, lon=79.09)
        self.assertTrue(b["existing"]); self.assertEqual(a["call_id"], b["call_id"])

class Triggers(unittest.TestCase):
    def test_unfulfilled_request_calls_donors(self):
        conn = reset(); conn.execute("DELETE FROM units"); conn.commit()
        r = dispatch.create_request(conn, 1, "B-", "RBC", 2)
        self.assertEqual(r["status"], "unfulfilled"); self.assertGreater(r["donor_call"]["alerted"], 0)
        call = conn.execute("SELECT * FROM donor_calls WHERE id=?", (r["donor_call"]["call_id"],)).fetchone()
        self.assertEqual((call["slots_needed"], call["request_id"], call["exact_only"]), (2, r["request_id"], 0))
    def test_race_test_does_not_spam_donors(self):
        conn = reset(); conn.execute("DELETE FROM units"); conn.commit()
        dispatch.race("B-", "RBC", 6)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM donor_calls").fetchone()[0], 0)
    def test_low_stock_scan_exact_group_only_and_idempotent(self):
        conn = reset(); conn.execute("DELETE FROM units"); inv.add_units(conn, 1, "B-", "RBC", 1)
        for g in ("O-", "O+", "A-", "A+", "B+", "AB-", "AB+"): inv.add_units(conn, 1, g, "RBC", 9)
        first = alerts.scan_low_stock(conn)
        self.assertEqual([o["blood_group"] for o in first], ["B-"])
        row = conn.execute("SELECT * FROM donor_calls").fetchone()
        self.assertEqual((row["slots_needed"], row["exact_only"]), (3, 1))
        self.assertTrue(all(conn.execute("SELECT blood_group FROM donors WHERE id=?", (a["donor_id"],)).fetchone()[0] == "B-" for a in first[0]["alerted"]))
        self.assertEqual(alerts.scan_low_stock(conn), [])

class Accept(unittest.TestCase):
    def call(self, conn, n=6, slots=1):
        only_donors(conn, n); return alerts.open_call(conn, "B-", "RBC", slots, lat=21.15, lon=79.09, bank_id=1)["call_id"]
    def test_first_wins_second_sees_covered(self):
        conn = reset(); cid = self.call(conn)
        a, b = alerts.accept(conn, cid, 1), alerts.accept(conn, cid, 2)
        self.assertTrue(a["won"]); self.assertFalse(b["won"]); self.assertTrue(b["covered"])
        self.assertEqual(conn.execute("SELECT status FROM donor_calls WHERE id=?", (cid,)).fetchone()[0], "covered")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM donations WHERE status='pledged'").fetchone()[0], 1)
    def test_multiple_slots_fill_then_cover(self):
        conn = reset(); cid = self.call(conn, slots=2)
        self.assertTrue(alerts.accept(conn, cid, 1)["won"]); self.assertTrue(alerts.accept(conn, cid, 2)["won"]); self.assertTrue(alerts.accept(conn, cid, 3)["covered"])
    def test_accepting_twice_is_harmless(self):
        conn = reset(); cid = self.call(conn, slots=2)
        alerts.accept(conn, cid, 1); again = alerts.accept(conn, cid, 1)
        self.assertTrue(again["already"]); self.assertEqual(conn.execute("SELECT slots_filled FROM donor_calls").fetchone()[0], 1)
    def test_donor_who_was_not_alerted_is_rejected(self):
        conn = reset(); cid = self.call(conn, n=8)   # wave 1 reaches 5 of 8
        with self.assertRaises(alerts.AlertError): alerts.accept(conn, cid, 8)
    def test_donor_who_became_ineligible_is_rejected(self):
        conn = reset(); cid = self.call(conn)
        conn.execute("UPDATE donors SET last_donation=? WHERE id=1", (date.today().isoformat(),)); conn.commit()
        with self.assertRaises(alerts.AlertError): alerts.accept(conn, cid, 1)
        self.assertEqual(conn.execute("SELECT slots_filled FROM donor_calls").fetchone()[0], 0)
    def test_one_pending_donation_at_a_time(self):
        conn = reset(); only_donors(conn, 2)
        c1 = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)["call_id"]
        c2 = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1, exact_only=True)["call_id"]
        alerts.accept(conn, c1, 1)
        with self.assertRaises(alerts.AlertError): alerts.accept(conn, c2, 1)
    def test_declined_donor_cannot_be_counted(self):
        conn = reset(); cid = self.call(conn); alerts.decline(conn, cid, 1)
        self.assertEqual(conn.execute("SELECT response FROM call_alerts WHERE donor_id=1").fetchone()[0], "declined")
    def test_ten_donors_accept_at_once_one_slot_one_winner(self):
        conn = reset(); only_donors(conn, 10)
        cid = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)["call_id"]
        alerts.tick(conn, force=True)                      # wave 2 so all 10 are alerted
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM call_alerts WHERE call_id=?", (cid,)).fetchone()[0], 10)
        r = alerts.race_accept(cid)
        self.assertEqual((r["donors"], r["won"], r["covered"], r["overbooked"]), (10, 1, 9, 0))
        row = conn.execute("SELECT slots_filled,status FROM donor_calls WHERE id=?", (cid,)).fetchone()
        self.assertEqual((row[0], row[1]), (0, "open"))    # restored after the test
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0], 0)
    def test_race_holds_even_when_the_check_is_slow(self):
        """Short accepts barely overlap under CPython, so widen the window: a 25 ms pause between the
        'is it still open?' check and the slot grab. Without BEGIN IMMEDIATE this oversells the slot."""
        conn = reset(); only_donors(conn, 10)
        cid = alerts.open_call(conn, "B-", "RBC", 1, lat=21.15, lon=79.09, bank_id=1)["call_id"]; alerts.tick(conn, force=True)
        real = alerts.eligibility
        alerts.eligibility = lambda *a, **k: (time.sleep(0.025), real(*a, **k))[1]
        try: r = alerts.race_accept(cid)
        finally: alerts.eligibility = real
        self.assertEqual((r["donors"], r["won"], r["overbooked"]), (10, 1, 0))
    def test_ten_donors_three_slots_exactly_three_winners(self):
        conn = reset(); only_donors(conn, 10)
        cid = alerts.open_call(conn, "B-", "RBC", 3, lat=21.15, lon=79.09, bank_id=1)["call_id"]; alerts.tick(conn, force=True)
        r = alerts.race_accept(cid)
        self.assertEqual((r["won"], r["overbooked"]), (3, 0))
    def test_race_leaves_earlier_real_accepts_alone(self):
        conn = reset(); only_donors(conn, 6)
        cid = alerts.open_call(conn, "B-", "RBC", 2, lat=21.15, lon=79.09, bank_id=1)["call_id"]
        alerts.accept(conn, cid, 1)
        r = alerts.race_accept(cid)
        self.assertEqual(r["slots"], 1); self.assertEqual(r["won"], 1)
        self.assertEqual(conn.execute("SELECT slots_filled FROM donor_calls").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT response FROM call_alerts WHERE donor_id=1").fetchone()[0], "accepted")

if __name__ == "__main__": unittest.main()
