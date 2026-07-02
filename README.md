# HTS Project QA

Standalone quality-assurance tracking for structural-engineering projects.
Engineers answer evidence-weighted QA forms across six design stages; directors
watch a roll-up dashboard of calc-package completion at construction stage.

This app is split across **two repositories**:

| Repo | Contents | Stack |
| --- | --- | --- |
| [`project-qa-server`](https://github.com/stiwari-sudo/project-qa-server) | FastAPI API (this repo) | FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 · Postgres 16 |
| [`project-qa-ui`](https://github.com/stiwari-sudo/project-qa-ui) | Next.js web app | Next.js 14 (App Router, TS strict) · Tailwind · TanStack Query/Table |

- **Auth** — pluggable; a dev stub now (no Azure needed), Azure AD JWKS later.

## Quick start (full stack, Docker)

The two repos must be checked out as **siblings** (the default clone folder
names already match):

```
<parent>/
├── project-qa-server/   # this repo
└── project-qa-ui/
```

```bash
git clone https://github.com/stiwari-sudo/project-qa-server.git
git clone https://github.com/stiwari-sudo/project-qa-ui.git
cd project-qa-server          # (or project-qa-ui — compose is identical in both)
cp .env.compose.example .env
docker compose up --build
```

`docker-compose.yml` is duplicated, identical, in both repos and builds the API
from `../project-qa-server` and the web app from `../project-qa-ui`, so it works
from whichever directory you run it in.

On first boot the API container waits for Postgres, runs Alembic migrations,
and loads the (idempotent) seeds. Then:

- Web: http://localhost:3000  (redirects to `/overview`)
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

The dev stub signs you in as the seeded engineer (`engineer@hts.uk.com`); set
`DEV_USER_EMAIL` to act as a different seeded user.

## What ships in Phase 1

- Six stages, one example form per stage (7 sections each), sample users + projects.
- **Overview** — 3 KPIs + per-director calc-package completion with expandable
  incomplete-project rows and a director filter.
- **Projects** — server-side paginated/filterable table with an expandable
  per-stage breakdown.
- **Project detail** — stage tabs, the JSON-driven `QuestionRenderer`
  (evidence-aware dropdowns, conditional subforms), bulk-save with server-side
  completion recompute.

`/event-log` and `/hrb` are stubbed in the nav and land in Phase 2.

## Local development (API only, without Docker)

```bash
# in this repo (project-qa-server)
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -e ".[dev]"
cp .env.example .env          # API-only env (point DATABASE_URL at a local Postgres)
alembic upgrade head && python -m seeds.run   # SEED_SAMPLE_DATA=true in .env for demo data
uvicorn app.main:app --reload
```

Run the web app from the `project-qa-ui` repo (`npm install && npm run dev`).

## Quality gates (API)

```bash
./.venv/Scripts/python.exe -m ruff check app seeds tests \
  && ./.venv/Scripts/python.exe -m mypy app \
  && ./.venv/Scripts/python.exe -m pytest -q
```

## Scoring rules (faithful to the reference)

For questions whose options mention *evidence*: `Yes w/ Evidence = 1.0`,
`Yes w/o Evidence = 0.5`, `No = 0.0`, plain `Yes`/other non-empty = `1.0`.
`N/A` is excluded from both numerator and denominator. Subform questions are
counted only when the parent's answer equals its `trigger_value`.
`completion_percentage = total_points / (total_questions − na_count) × 100`.

## Roadmap

Phase 2 — Event Log + HRB pages. Phase 3 — deadline-reminder emails.
Phase 4 — Azure AD auth. Phase 5 — admin form editor + projects CRUD.
Phase 6 — CMAP webhook sync (flip `CONSTRUCTION_SOURCE=cmap`).
