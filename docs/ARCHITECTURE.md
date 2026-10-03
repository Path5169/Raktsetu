# RaktSetu Architecture

## Frontend

`frontend/` contains presentation only:

- `index.html` + `assets/index.js` — hospital/network operations dashboard
- `bank.html` + `assets/bank.js` — blood-bank verification desk
- `donor.html` + `assets/donor.js` — donor OTP application
- `login.html` + `assets/login.js` — staff authentication
- CSS/assets remain isolated from backend business logic

The frontend never decides permissions. It sends authenticated API requests and the backend is authoritative.

## Backend

`raktsetu/` contains the application and domain logic:

- `server.py` — HTTP/API boundary and authorization enforcement
- `auth.py` — password hashing, sessions, roles and permissions
- `dispatch.py` — emergency routing, reservation and race-safe allocation
- `inventory.py` — unit-level stock and FEFO expiry handling
- `donors.py` — eligibility, OTP, donor calls and donation verification
- `alerts.py` — donor waves and emergency broadcasts
- `compat.py` — blood/component compatibility
- `db.py` — SQLite schema, migrations and audit logging
- `seed.py` — deterministic fictional Nagpur network and demo accounts

## Roles

| Role | Login | Allowed actions |
|---|---|---|
| Network Admin | Username/password | Full network operations, race tests, all inventory, all verification, audit access |
| Hospital Staff | Username/password | Create emergency requests and broadcasts for their assigned verified hospital; read network state |
| Blood Bank Staff | Username/password | Manage stock for their assigned bank, process assigned requests, verify donations assigned to that bank |
| Donor | OTP | View own profile/calls, accept/decline own donor calls, share own presence |

## Security model

- Passwords are stored as salted PBKDF2-SHA256 hashes.
- Staff sessions use random bearer tokens with an expiry.
- Role checks happen on the backend for every protected mutation.
- Organization ownership is checked server-side: hospital accounts cannot act for another hospital and bank accounts cannot manage another bank.
- Unverified hospitals cannot create emergency requests or broadcasts through the domain layer.
- Donor OTP remains single-use, expires, and has an attempt limit.
- Important actions are written to the audit log.
- The demo uses fictional credentials/data and localhost HTTP; production deployment should use HTTPS, secure cookies/token storage, real identity management, rate limiting, CSRF protection where cookie auth is used, secrets management, and real SMS/identity verification.

## Seeded demo network

The seed contains **6 blood banks, 8 hospitals (including 2 intentionally unverified facilities), and 32 fictional donors**. Staff accounts are generated for the verified hospitals and all six banks, plus one network administrator.
