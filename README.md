# Quizee API

Backend for **Quizee**, a quiz creation and grading platform. Handles auth, quiz CRUD, access control, attempts, and grading. Built with FastAPI + async SQLAlchemy + PostgreSQL.

Frontend: [quizee-frontend](https://github.com/IslamEssam01/quizee-frontend) (React 19, TanStack Router/Query, Tailwind v4, shadcn/ui).

## Features

- **Auth**: JWT access tokens + rotating refresh tokens with reuse/theft detection (a reused refresh token revokes its whole token family). Login rate limiting per email+IP. Argon2 password hashing. Password reset via emailed token.
- **Quizzes**: create, update, delete, duplicate. Visibility levels (public, public-with-link, private) with per-user grant/revoke access control.
- **Attempts**: anonymous (name-only) or authenticated attempts, resumable in-progress attempts, optional question/answer shuffling per attempt.
- **Grading**: point-based scoring, optional negative scoring, configurable pass threshold, optional grade tiers (e.g. A/B/C by score percentage).
- **Users**: registration, profile updates, password change with optional "log out all other sessions".

## Stack

FastAPI · SQLAlchemy 2 (async) · PostgreSQL (JSONB for quiz/answer content) · Alembic migrations · Pydantic v2 · PyJWT · pwdlib (Argon2) · pytest + Hypothesis (property-based tests) · uv

## Running locally

Requires Python 3.14+, [uv](https://docs.astral.sh/uv/), and a PostgreSQL instance.

```bash
uv sync
cp .env.example .env   # fill in DB_URL, TEST_DB_URL, SECRET_KEY, etc.
uv run alembic upgrade head
uv run fastapi dev main.py
```

API docs (Swagger UI) at `http://localhost:8000/docs` once running.

## Tests

```bash
uv run pytest
```

Tests run against `TEST_DB_URL` (a real Postgres database, not mocked) and include property-based tests via Hypothesis for input validation edge cases.

## CI

GitHub Actions runs the test suite against a Postgres service container on every push/PR to `main` (`.github/workflows/ci.yml`).

## Roadmap

- [x] Email notification on detected refresh-token theft (reuse of a revoked token)
- [ ] User groups
- [ ] Quiz groups
- [ ] Quiz timers
- [ ] Ban users / user groups from a quiz
