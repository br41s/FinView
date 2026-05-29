# Audit Remediation Changelog

Running log of changes made during the audit-driven remediation work.
Source: audit report from 2026-05-22 session.

## Perf Batch 1 — Dashboard load latency (branch: `claude/nervous-clarke-6ba65c`)

**Status:** Implemented, frontend `tsc --noEmit` clean. Not yet built (`next build`) or visually verified on localhost.
Source: performance audit from 2026-05-29 session (see `tasks/todo.md` → "⚡ Auditoría de rendimiento").

### Diagnosis
The slowness was in the request path, not the FIFO/fiscal engine (which is
precomputed at import into `TaxResult`/`TaxLot` and read back as plain
aggregations). The dashboard fired ~16 requests, each preceded by a
`getSession()` network round-trip, in 3 sequential batches, all gated on the
slowest call (a synchronous yfinance fetch in `dividend-yield`).

### Changes — `frontend/src/lib/api.ts`
- **#1 — Access-token cache.** `getSession()` (a network call to
  `/api/auth/session`) was invoked before every request. Now the JWT is
  resolved once and cached at module scope, reused until it nears expiry
  (decoded from the token's `exp`) or a request returns 401 (self-healing:
  clears + retries once). Concurrent resolves are deduped via a shared
  promise, so ~16 parallel requests trigger a single `getSession()`.
  Exposed `clearAuthToken()`.
- **#6 — Client cache for charts/fiscal reads.** All dashboard-feeding GETs
  (`charts.*`, fiscal dashboard/casillas/summary/cross-broker-lots/
  fifo-adjustments/option-assignments/cross-validation/yearly-comparison,
  dividends, capital-gains) now go through the existing 5-min `fetchCached`
  (keyed by path+year). Invalidated via `invalidateCache()` on the 6 uploads,
  `deleteImport`, `deleteAllImports`, and `resolveIssue`. `transactions()` and
  `imports()` left uncached so the imported-files list stays fresh. Also masks
  the symptom of the slow `dividend-yield` call client-side after first load.

### Changes — `frontend/src/components/app-sidebar.tsx`
- Logout now calls `clearAuthToken()` + `invalidateCache()` before `signOut`,
  so neither the token nor cached data leaks across users.

### Changes — `frontend/src/app/dashboard/page.tsx`
- **#2 — Decoupled dashboard render from the slowest request.** The 3
  sequential `Promise.all` batches are merged into one parallel group holding
  the fast data the default (gráficas) view needs; `loading` gates only that.
  Slow/secondary data (`dividend-yield` → yfinance, `yearly-comparison`,
  year-only fiscal tables) is streamed in behind a separate `secondaryLoading`
  flag — the rendimiento/comparativa views show a skeleton instead of an
  empty-state flash until their slice lands.
- Per-request failure isolation: each streamed request fails independently
  (previously one failing chart threw into a single `catch` and broke the
  whole dashboard).
- Stale-response guard (`loadSeq` ref): a rapid year switch can no longer let
  an older in-flight response overwrite the current view's state.

### Verification
- `pnpm install` + `pnpm exec tsc --noEmit` — clean (exit 0).
- Backend untouched (no test impact); `fifo_engine.py` untouched.

### Deferred (backend, see `tasks/todo.md`)
- #3 (`dividend_yield` read cache-only), #5 (scope `get_position_detail`),
  #7 (date-range filters to use indexes), #8 (Neon pool tuning), #9 (options
  synchronous scraping), #4/#11 (Cloud Run min-instances, drop `create_all`).
  Each requires `pytest backend/tests/` after.

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
