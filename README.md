# RaktSetu — Live Blood Network

> A local-first emergency blood routing and donor coordination demo for hackathons.

RaktSetu connects hospital requests, blood-bank inventory, donor alerts, and bank verification in one lightweight application. It uses Python's standard library and SQLite, so there is no account setup, cloud database, or external service required for the demo.

## Phase 6 highlights

- **Separated frontend/backend:** presentation pages are isolated from the Python API/domain layer.
- **Role-based access:** network admin, hospital staff, blood-bank staff, and donor roles have server-enforced permissions.
- **Organization scoping:** hospital and bank staff can only mutate records belonging to their assigned organization.
- **Staff authentication:** salted PBKDF2 password hashes and expiring bearer sessions.
- **Expanded seed network:** 6 blood banks, 8 hospitals, and 32 fictional donors.
- **Auditability:** login, verification, broadcast, inventory, and routing actions can be traced in the audit log.

## Phase 5 highlights

- **Emergency routing:** rank blood banks by compatibility, distance, expiry, and opening hours.
- **FEFO inventory:** use the units that expire first and prevent expired stock from being issued.
- **Race-safe reservations:** concurrent requests cannot oversell the same blood units.
- **Donor app:** mock OTP login, eligibility countdown, donor calls, badges, streaks, and donation history.
- **Bank verification desk:** `/bank` gives operators a queue of pledged donations and lets them verify completed donations.
- **Trusted impact data:** verification updates donor eligibility, last-donation date, badges, streaks, and history in one audited action.
- **Live field view:** the dashboard maps database-backed donor, hospital, and blood-bank locations and refreshes them every 15 seconds.
- **Emergency broadcasts:** operators can send a targeted shortage broadcast through the existing donor-wave alert engine and see recipients immediately.
- **Consent-based presence:** logged-in donors can share browser GPS after the normal permission prompt; the dashboard displays their last-seen time.
- **Local demo data:** fictional Nagpur data is loaded with one command.

## Quick start

### Windows

Double-click [`start.bat`](start.bat), or run it from Command Prompt:

```bat
start.bat
```

The script creates the demo database if needed, starts the server, and opens the app in your browser.

To reset the fictional hackathon data before a demo:

```bat
start.bat reset
```

### macOS / Linux

```bash
python3 -m raktsetu init
python3 -m raktsetu serve
```

Then open <http://127.0.0.1:8000>.

## Demo routes

| Route | Purpose |
| --- | --- |
| `/login` | Staff sign-in |
| `/` | Hospital/network operations dashboard (staff login required) |
| `/donor` | Donor-facing app with mock OTP login |
| `/bank` | Blood-bank verification desk (bank/admin login required) |

The dashboard also exposes `/api/network` for the live map payload and `/api/broadcast` for operator-triggered donor broadcasts.

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
├── frontend/
│   ├── index.html          # Operations dashboard shell
│   ├── donor.html          # Donor app shell
│   ├── bank.html           # Phase 5 bank desk shell
│   └── assets/             # External CSS and JavaScript per page
├── raktsetu/
│   ├── server.py            # Backend HTTP server and JSON API
│   ├── alerts.py            # Donor calls and alert waves
│   ├── db.py                # SQLite schema and audit log
│   ├── dispatch.py          # Emergency routing and reservations
│   ├── donors.py            # Eligibility, OTP, badges, and verification
│   └── inventory.py         # Stock and FEFO expiry logic
├── tests/                   # Unit and concurrency tests
├── start.bat                # Windows one-click launcher
└── README.md
```

## Notes for GitHub

- The app is intentionally **local-first** for a simple, privacy-friendly demo.
- The included people, hospitals, and blood banks are fictional.
- OTP is mock-only: the demo code is displayed on screen instead of sent by SMS.
- For production, replace demo credentials and mock OTP with real identity/SMS providers, use HTTPS, secure cookie/token storage, rate limiting, CSRF protection where applicable, secrets management, and stronger organizational verification.

## License

This repository is released under the MIT License; see [`LICENSE`](LICENSE).
