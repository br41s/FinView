# Audit Remediation Changelog

Running log of changes made during the audit-driven remediation work.
Source: audit report from 2026-05-22 session.

## Batch 1 — Security & Data Integrity (branch: `security/batch-1-hardening`)

**Status:** Implemented, validated, awaiting review. Not committed/pushed.

### Changes
- **Startup secret validation** — `backend/config.py` now requires real values
  for `FINVIEW_SECRET_KEY` and `FINVIEW_AUTH_SECRET` when `FINVIEW_ENV` is
  `staging`, `production`, or `prod`. Boots normally for `local`/`dev`/`test`.
  Added new `env` field on `Settings` (default `"local"`).
- **Removed `user_id or 1` fallback** — three sites now require an explicit
  user_id at call time:
  - `_store_casillas` (`backend/services/import_service.py`)
  - `_compute_broker_casillas` (`backend/services/import_service.py`)
  - `recalculate_cross_broker_fifo` (`backend/services/fifo_engine.py`)
- **Removed ORM `default=1`** on `TaxResult.user_id` and
  `FIFOAdjustment.user_id` (`backend/models.py`). Missing user_id now raises
  `IntegrityError` instead of silently writing to user 1.
- **Auth rate limiting** — added `slowapi` (`pyproject.toml`), wired it in
  `backend/app.py`, decorated `/auth/login` (5/min) and `/auth/register`
  (3/min) per IP. Thresholds configurable via `FINVIEW_RATE_LIMIT_LOGIN` /
  `FINVIEW_RATE_LIMIT_REGISTER`.
- **New file** `backend/services/rate_limit.py` — Cloud-Run-aware IP
  extractor that reads the rightmost `X-Forwarded-For` entry (unspoofable
  from the client), falling back to `request.client.host` for local dev.

### Test updates
- `backend/tests/test_fifo_engine.py` — added `user_id` fixture, threaded
  through 10 `recalculate_cross_broker_fifo` calls.
- `backend/tests/test_import_service.py` — added `user_id` fixture, updated
  `_make_import` helper and 7 test methods that build `TaxResult` rows.

### Deferred (separate follow-up)
- `python-jose` → `pyjwt` migration (single file, narrow blast radius).
- CORS `allow_methods` tightening — deferred to Batch 4.
- Three pre-existing ruff `F401` unused-import errors — deferred to Batch 4.

### ⚠️ Production activation requirement
`FINVIEW_ENV` defaults to `"local"`, so the new secret validator is a no-op
until that var is set to a production-like value. **Cloud Run must set
`FINVIEW_ENV=production`** for the startup secret enforcement to actually
fire. Without it, the app boots normally even with insecure defaults — same
behavior as before this batch (no regression, but no protection either).

### Docs to update later
- `docs/deployment.md` — add `FINVIEW_ENV`, `FINVIEW_RATE_LIMIT_LOGIN`,
  `FINVIEW_RATE_LIMIT_REGISTER` env vars; note Cloud Run must set
  `FINVIEW_ENV=production`.
- `README.md` — note rate limiting on auth endpoints.
- `CHANGELOG.md` (does not yet exist) — Batch 4 will create it.
