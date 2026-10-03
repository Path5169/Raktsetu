# RaktSetu

## Centralized Real-Time Blood Inventory and Donor Engagement Platform

I built RaktSetu to solve a problem that is easy to describe but surprisingly difficult to handle properly: during a blood emergency, knowing that blood exists somewhere is not enough. I need to know where it is, whether it is compatible, whether it is actually available, whether it is close enough to be useful, and what happens if multiple hospitals request the same unit.

RaktSetu connects hospitals, blood banks, and donors through one centralized system. The platform keeps track of blood inventory, handles emergency requests, matches compatible resources, manages donor engagement, and keeps the inventory consistent when multiple requests happen at the same time.

The project is designed as a working prototype for a hackathon, but I have tried to keep the architecture realistic instead of building everything as a single demo page.

## What I am trying to solve

Blood inventory is usually distributed across different locations. This creates several problems:

* A hospital may not know which nearby blood bank has the required blood group.
* Blood can approach expiry while another location has a shortage.
* Emergency requests can involve multiple hospitals competing for limited stock.
* Searching for compatible donors manually takes time.
* Fake or repeated donor activity can make the system unreliable.
* A displayed inventory number is useless if two requests can claim the same unit.

I built RaktSetu around these problems rather than treating it as just a blood availability dashboard.

## How RaktSetu works

The basic workflow is:

```text
Hospital creates emergency request
        |
        v
Hospital and request validation
        |
        v
Blood group compatibility check
        |
        v
Search available blood banks
        |
        v
Rank suitable inventory by availability and distance
        |
        v
Reserve required units safely
        |
        +---- If enough blood is available
        |          |
        |          v
        |       Request fulfilled
        |
        +---- If stock is insufficient
                   |
                   v
              Start donor search
                   |
                   v
          Contact eligible donors in waves
                   |
                   v
             Donation verification
```

## Main features

### Real-time inventory

Blood banks can manage their available inventory by blood group and component.

Each inventory unit can contain information such as:

* Blood group
* Component
* Collection date
* Expiry date
* Current status
* Blood bank

This allows the system to identify inventory that is approaching expiry instead of treating every unit as identical.

### Compatibility matching

I did not want the matching system to simply compare two strings such as `A+` and `A+`.

RaktSetu has a compatibility layer that determines whether a blood group can be used for a particular request and can prefer exact matches where appropriate.

### Emergency dispatch

A hospital can create an emergency requirement with the required blood group, component, quantity, and location.

RaktSetu searches available blood banks and considers factors such as compatibility, quantity, availability, and distance.

If the available inventory cannot satisfy the requirement, the system can move the request into the donor workflow.

### Donor engagement

Instead of contacting every donor at once, RaktSetu uses progressive donor waves.

The system first looks for donors who are compatible, eligible, verified, and closer to the requirement.

If the requirement is still open, the search can expand.

This keeps emergency notifications more targeted.

### Donation verification

A donor accepting a request does not automatically mean that a successful donation happened.

The blood bank has to verify the completed donation.

This distinction is important because otherwise a donor could repeatedly accept requests and artificially build up their donation history.

### Concurrent inventory protection

One of the parts I specifically wanted to handle was the last-unit problem.

For example, if a blood bank has one unit available and two hospitals request it almost simultaneously, both requests should not be able to claim it.

RaktSetu uses transactional reservation so that the inventory check and allocation happen safely.

The goal is:

```text
Available units: 1

Request A -> successful
Request B -> rejected

Final inventory: 0
Oversold units: 0
```

The project also contains a race-condition test for this behavior.

## Security and access control

I wanted the different users of the platform to have clearly different responsibilities.

RaktSetu currently uses four main roles:

### Network Admin

The administrator has network-wide access.

The admin can manage and monitor the overall system and its organizations.

### Hospital Staff

Hospital accounts are connected to a specific hospital.

Hospital staff can create and manage requests belonging to their hospital.

They cannot perform blood-bank operations for another organization.

### Blood Bank Staff

Blood-bank accounts are connected to a specific blood bank.

They can manage inventory and verify donations belonging to their assigned bank.

They cannot simply access another bank's inventory by changing an ID in a request.

### Donor

Donors have access to their own donor information and emergency opportunities.

They cannot access hospital or blood-bank management functions.

These permissions are enforced on the backend. They are not based only on hiding buttons in the frontend.

## Authentication

The current prototype includes:

* Password authentication for staff accounts
* PBKDF2 password hashing with salts
* Session-based authentication
* Session expiry
* Role-based authorization
* Organization-level access control
* OTP-based donor verification
* Protected backend API routes

Unauthorized requests are rejected by the backend even if someone attempts to call the API directly.

## Project structure

I separated the frontend from the backend so that the user interface does not become responsible for business logic.

```text
RaktSetu/
|
+-- frontend/
|   +-- index.html
|   +-- login.html
|   +-- bank.html
|   +-- donor.html
|   +-- assets/
|       +-- CSS
|       +-- JavaScript
|
+-- raktsetu/
|   +-- auth.py
|   +-- compat.py
|   +-- db.py
|   +-- dispatch.py
|   +-- donors.py
|   +-- inventory.py
|   +-- alerts.py
|   +-- seed.py
|   +-- server.py
|   +-- cli.py
|
+-- tests/
|   +-- test_auth.py
|   +-- test_core.py
|   +-- test_dispatch.py
|   +-- test_donors.py
|
+-- docs/
|   +-- ARCHITECTURE.md
|
+-- DEMO_ACCOUNTS.md
+-- README.md
+-- start.bat
```

The frontend is responsible for presentation and interaction.

The backend is responsible for authentication, authorization, validation, compatibility, inventory, dispatch, donor logic, and database operations.

## Seed data

I included fictional seed data so the application can be demonstrated as an actual network rather than with two or three example records.

The current seed network contains:

* 6 blood banks
* 8 hospitals
* 32 donors
* Staff accounts for different organizations
* Blood inventory
* Emergency scenarios
* Verified and unverified organizations

All seed organizations and donor information are fictional and intended for development and demonstration.

Demo credentials are available in `DEMO_ACCOUNTS.md`.

## Testing

I have included tests for the main parts of the system.

The test suite covers areas including:

* Authentication
* Role-based access control
* Blood compatibility
* Inventory operations
* Emergency dispatch
* Concurrent requests
* Donor eligibility
* OTP behavior
* Donation verification
* Donor alert waves
* Duplicate or conflicting donor acceptance

The current test suite contains 54 automated tests.

## Running the project

The project can be started using the included startup script:

```text
start.bat
```

The backend can also be started through the Python entry points provided in the project.

The exact development setup can be found in the project documentation.

## Important note

RaktSetu is a hackathon prototype and not a production medical system.

The blood, hospital, bank, donor, and location data included in the project is fictional.

A real deployment would require integration with verified blood-bank systems, stronger identity verification, proper medical and regulatory compliance, secure infrastructure, privacy controls, monitoring, and operational validation.

## Why I built it this way

My main goal with RaktSetu was not to make a page that says which blood groups are available.

I wanted to build the coordination layer behind the problem.

A useful system should be able to answer:

```text
What blood is available?

Is it compatible?

Where is it?

Is it still usable?

Who should receive it?

What happens if two people request it?

What happens when there is not enough?

Who can respond?

Can I trust the donor information?

Was the donation actually verified?
```

That is what I am trying to solve with RaktSetu.

## Current status

RaktSetu is currently a functional hackathon prototype with:

* Separate frontend and backend
* Role-based authentication
* Organization-level permissions
* Centralized inventory
* Compatibility matching
* Emergency dispatch
* Donor engagement
* Donation verification
* Expiry tracking
* Concurrent inventory protection
* Seed data
* Automated tests
* Audit-oriented architecture

The next step would be moving from fictional seed data and prototype authentication toward integrations with real, verified blood-bank and hospital systems.
