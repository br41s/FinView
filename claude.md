# FinView

Personal investment dashboard with multi-broker import and Spanish IRPF fiscal engine.
Extends root claude.md. Rules here are FinView-specific only.

---

## What this project is

- **Type**: Full-stack web app (personal tool, planning maybe upgrade SaaS)
- **Owner**: Brais — personal investment tracking across TR, DEGIRO, IBKR, ING, BBVA, eToro
- **Core value**: Unified view of dividends, capital gains, and IRPF tax boxes across all brokers

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic |
| Parsers | pdfplumber (PDF), openpyxl (XLSX), csv (IBKR) |
| Frontend | Next.js 16 · React 19 · TailwindCSS · Recharts · NextAuth |
| DB prod | Neon Postgres |
| DB local | SQLite fallback |
| Deploy | Vercel (frontend) · Google Cloud Run europe-west1 (backend) |
| CI | Cloud Build trigger on push to backend/**, Dockerfile, pyproject.toml, cloudbuild.yaml |
| Tests | pytest · 128 tests (35 skipped — need real PDFs/CSVs in files/) |
| Linter | ruff (line-length 100) |

---

## Dev start (always use venv)

Both at once: ./start.sh

Or separately:
- source .venv/bin/activate
- uvicorn backend.app:app --reload --port 8000 → localhost:8000
- cd frontend && pnpm dev → localhost:3000

Never run pip install outside .venv. Never use npm — frontend uses pnpm.

---

## Project structure (key paths)

backend/
  app.py              — FastAPI entry point
  models.py           — ORM models
  api/                — Endpoints: imports, transactions, fiscal, charts
  importers/          — One file per broker: tr.py, dg.py, ibkr.py, ing.py, bbva.py, etoro.py
  services/
    fifo_engine.py    — Cross-broker FIFO engine — most critical, touch carefully
    import_service.py — Import logic + deduplication
    prices.py         — Yahoo Finance price cache

frontend/
  src/app/page.tsx         — Main dashboard (5 tabs)
  src/components/          — FileUpload, tables, stat cards
  src/components/charts/   — 8 chart components (Recharts)
  src/lib/                 — API client + TypeScript types

---

## Critical rules

- fifo_engine.py is the most sensitive file. Any change must be followed by full test suite.
  Never touch it without understanding cross-broker FIFO matching logic.
- Importer changes: each importer is isolated — changes in one must not break others.
  Always run pytest backend/tests/ after importer changes.
- DB migrations: use Alembic. Never modify models.py without a migration.
  Run alembic upgrade head after pulling changes with model changes.
- No breaking changes to API contracts without updating frontend src/lib/ types.

---

## IRPF fiscal model (context for AI)

- Modelo 100: casillas 27 (intereses), 29 (dividendos), 332 (ganancias >1 año), 337 (pérdidas)
- Modelo 714: casillas 05-09 (patrimonio exterior)
- FIFO is chronological, cross-broker — a buy in IBKR can match a sell in DEGIRO
- Withholding tracking per country, CDI deductions default 15%
- finview_casillas_2024.json in repo root = reference output for fiscal year 2024

---

## Deploy

- Frontend: push to main → Vercel auto-deploys. No action needed.
- Backend: push to main touching backend/**, Dockerfile, pyproject.toml, or cloudbuild.yaml
  → Cloud Build triggers → deploys to Cloud Run europe-west1.
- Never touch cloudbuild.yaml without knowing what you are doing — it controls prod deploys.
- Full deploy docs: docs/deployment.md

---

## Tests

Run: pytest backend/tests/ -v

128 tests pass on clean data. 35 skipped = need real broker files in files/ (not in repo).
If a test breaks, fix it before committing — no exceptions.