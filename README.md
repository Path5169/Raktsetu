<<<<<<< HEAD
# RaktSetu — Live Blood Network

> A local-first emergency blood routing and donor coordination demo for hackathons.

RaktSetu connects hospital requests, blood-bank inventory, donor alerts, and bank verification in one lightweight application. It uses Python's standard library and SQLite, so there is no account setup, cloud database, or external service required for the demo.

## Phase 5 highlights

- **Emergency routing:** rank blood banks by compatibility, distance, expiry, and opening hours.
- **FEFO inventory:** use the units that expire first and prevent expired stock from being issued.
- **Race-safe reservations:** concurrent requests cannot oversell the same blood units.
- **Donor app:** mock OTP login, eligibility countdown, donor calls, badges, streaks, and donation history.
- **Bank verification desk:** `/bank` gives operators a queue of pledged donations and lets them verify completed donations.
- **Trusted impact data:** verification updates donor eligibility, last-donation date, badges, streaks, and history in one audited action.
- **Local demo data:** fictional Nagpur data is loaded with one command.

## Quick start

### Windows

Double-click [`start.bat`](start.bat), or run it from Command Prompt:

```bat
start.bat
```

The script creates the demo database if needed, starts the server, and opens the app in your browser.

### macOS / Linux

```bash
python3 -m raktsetu init
python3 -m raktsetu serve
```

Then open <http://127.0.0.1:8000>.

## Demo routes

| Route | Purpose |
| --- | --- |
| `/` | Hospital and blood-bank dashboard |
| `/donor` | Donor-facing app with mock OTP login |
| `/bank` | Phase 5 bank verification desk |

### Suggested hackathon demo

1. Open `/` and show blood-group inventory plus expiring units.
2. Create an emergency request for a low-stock group.
3. Open `/donor`, choose a demo donor, and accept the donor call.
4. Open `/bank` and verify the pledged donation.
5. Return to `/donor` to show updated eligibility, impact, and history.
6. Use the race test to demonstrate that no units are oversold under concurrent requests.

## CLI examples

```bash
python3 -m raktsetu init
python3 -m raktsetu stock
python3 -m raktsetu expiring --days 3
python3 -m raktsetu compat A+
python3 -m raktsetu donors --eligible
python3 -m raktsetu calls
python3 -m raktsetu audit
```

## Tests

```bash
python3 -m unittest discover tests -v
```

The project currently passes the full regression suite covering compatibility, inventory, emergency routing, concurrency, donor eligibility, OTP login, donor waves, and verification.

## Project structure

```text
raktsetu/
├── raktsetu/
│   ├── web/
│   │   ├── index.html       # Main operations dashboard
│   │   ├── donor.html       # Donor app
│   │   └── bank.html        # Phase 5 verification desk
│   ├── alerts.py            # Donor calls and alert waves
│   ├── db.py                # SQLite schema and audit log
│   ├── dispatch.py          # Emergency routing and reservations
│   ├── donors.py            # Eligibility, OTP, badges, and verification
│   ├── inventory.py         # Stock and FEFO expiry logic
│   └── server.py            # Standard-library web server and JSON API
├── tests/                   # Unit and concurrency tests
├── start.bat                # Windows one-click launcher
└── README.md
```

## Notes for GitHub

- The app is intentionally **local-first** for a simple, privacy-friendly demo.
- The included people, hospitals, and blood banks are fictional.
- OTP is mock-only: the demo code is displayed on screen instead of sent by SMS.
- For production, add bank-staff authentication, role-based permissions, real SMS delivery, encrypted storage, and deployment behind HTTPS.

## License

Add the license required by your hackathon or team before publishing publicly.
=======
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
>>>>>>> 38b6d65c03090c2bf1241720d12fe797db4654ba
