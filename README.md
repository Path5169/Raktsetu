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
