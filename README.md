# RaktSetu: live blood network (engine, emergency routing, donor side)
Python 3.8+, standard library only.

    python -m raktsetu init                 # create DB + demo data (Nagpur, fictional)
    python -m raktsetu stock                # stock by group per bank (-c PLT for platelets)
    python -m raktsetu expiring --days 3    # FEFO expiry list
    python -m raktsetu compat A+            # who can give to / receive from
    python -m raktsetu add orange B- 2      # add units (audited)
    python -m raktsetu audit
    python -m unittest discover tests -v    # run tests

## Web UI
    python -m raktsetu serve        # opens http://127.0.0.1:8000

## Emergency engine
    python -m raktsetu request "city" B- 1      # rank banks, reserve the best (30 min hold)
    python -m raktsetu request unverified A+    # blocked: hospital not verified
    python -m raktsetu race B- -n 20            # 20 simultaneous requests, shows 0 oversold

## Donor side (Phase 4)
    python -m raktsetu init                       # re-run once if you have an older DB: adds donor profiles + history
    python -m raktsetu donors [--eligible]        # eligibility countdown, badge, streak per donor
    python -m raktsetu alert B- 2 --hospital city # open a call, alert wave 1 (nearest 5 eligible, compatible donors)
    python -m raktsetu alert --scan               # call donors for any group the city is nearly out of
    python -m raktsetu calls                      # open calls, slots filled, wave
    python -m raktsetu tick [--force]             # widen to the next wave (automatic after 10 min)
    python -m raktsetu accept 1 aarav             # first donors to accept fill the slots, the rest see "already covered"
    python -m raktsetu accept 1 --race            # every alerted donor accepts at the same instant
Web: `/donor` is the donor app (mock OTP login, the code is shown on screen in demo mode; demo phones are listed on the page).
The dashboard has a Donor calls card. A request that no bank can cover opens a call automatically.

**Eligibility rules** (NBTC / MoHFW donor selection guidelines, Feb 2025; `donors.RULES`): whole blood age 18-65
(first-time donors 60 or younger), weight 45 kg+, gap 90 days for men and 120 days for women. Platelet (apheresis) donors: age 18-60,
50 kg+, 28 days since a whole-blood donation. Indicative only: haemoglobin, BP and history are checked by a doctor at donation.

**Waves:** (5 donors, 8 km) then (5, 15 km) then (10, 40 km), 10 minutes apart. Exact blood group first, then substitutes, nearest first.
Low-stock calls ask exact-group donors only so scarcer groups are not drained.
**Accept:** one `BEGIN IMMEDIATE` transaction plus a guarded `UPDATE ... WHERE slots_filled < slots_needed`, so a slot is never given twice.
A donation counts (eligibility, badges, streak) only after a blood bank verifies it (`donors.verify_donation`; screen comes in Phase 5).
