# FreelanceMatch — Reference Implementation (Deliverable 3)

## Prerequisites

- Python 3.11+ (developed and tested on 3.12)
- The packages listed in `requirements.txt`

## Dependencies

| Package | Version | Role |
|---|---|---|
| `fastapi` | 0.136.3 | HTTP framework — routing, request validation, OpenAPI console |
| `uvicorn` | 0.49.0 | ASGI server that runs the FastAPI app |
| `SQLAlchemy` | 2.0.50 | ORM / persistence layer over SQLite |
| `pydantic` | 2.13.4 | Request/response DTOs (used by FastAPI) |
| `httpx` | 0.28.1 | HTTP client used by the test suite (`fastapi.testclient`) |
| `pytest` | 9.0.3 | Test runner for T1–T8 |

No external services are required: SQLite is file-based (or in-memory for
tests) and needs no separate server; there is no message broker, cache, or
third-party API dependency.

## Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python seed.py                     # optional: demo data (skills, freelancers, one open project)
uvicorn main:app --reload          # or: python main.py
```

Then open <http://127.0.0.1:8000/docs>. Demo accounts created by `seed.py`
all use the password `password` (client `acme@demo.io`, freelancers
`ada@demo.io`, `grace@demo.io`, …).

A typical walkthrough in the console: `POST /login` to obtain a bearer token,
click **Authorize** and paste it, then publish a project, submit proposals,
accept one, complete the project, and leave reviews.

## Assumptions

- **Persistence.** SQLite via SQLAlchemy is used as the datastore; the schema
  is created automatically at startup. No external database server is required.
- **Authentication.** Login issues an opaque in-memory bearer token; the token
  store is process-local. Durable session management is out of scope (RASD
  assumptions) — what the requirements need is that every state-changing call
  is attributable to an authenticated principal, which holds.
- **Concurrency.** Atomicity and the serialisation of competing acceptances
  (R16) are enforced at the persistence layer (single-commit aggregate +
  optimistic lock). The prototype runs single-process; horizontal scaling is
  not addressed.
- **Skill vocabulary.** New-skill *requests* (R10) are recorded but their
  approval is a manual/administrative step with no dedicated endpoint; the
  demo vocabulary is provided by `seed.py`.
- **Notifications** are persisted and exposed through the API/dashboard; actual
  e-mail/push delivery is out of scope.

## Tests

```bash
pytest -q
```

## Status

[ ] Completed
