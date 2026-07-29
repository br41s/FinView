# Audit Remediation Changelog

Running log of changes made during the audit-driven remediation work.
Source: audit report from 2026-05-22 session.

## Financial correctness — FIFO fiscal v2 (PR #185)

**Status:** Implemented, reviewed and documented; awaiting merge.

- Chronological ledger through the target year; prior sales consume inventory and
  future purchases cannot fund earlier sales.
- Empty ISIN and incomplete inventory fail closed without authoritative lots.
- IBKR buy/sell commissions normalized into cost/proceeds.
- Versioned, per-box 332/337 adjustments used consistently by every fiscal output and UI.
- Additive nullable migration; legacy calculations are ignored until explicit recalculation.
- Verification: 375 backend tests passed, 131 skipped; Ruff, TypeScript and Next build green.

Deferred to separate PRs: future-year invalidation after historical edits, option
assignment/spinoff cost basis, withholding normalization and portfolio valuation.

---

## Perf Batch 3 — Drop yfinance from request path + index-friendly year filters (branch: `claude/nervous-clarke-6ba65c`)

**Status:** Implemented, full backend suite green (122 passed, 35 skipped).
Source: performance audit from 2026-05-29 session.

### Changes — `backend/api/charts.py` (#3)
- `dividend_yield` no longer calls `fetch_and_cache_prices()` (a synchronous
  `yf.download()`) in the request path — it now reads `get_cached_prices()`
  only. The cache is populated out-of-band by `POST /portfolio/warm-prices`
  and the options agent; ISINs still held are exactly the open positions that
  warming covers, and fully-sold ISINs have `current_value` 0 regardless of
  price. Uncached ISINs fall back to the historical transaction price already
  in `price_map`. Removes the blocking call and the warm-prices race.

### Changes — `backend/services/sql_compat.py` + endpoints (#7)
- New `year_range(column, fiscal_year)` helper: a half-open date range
  (`>= Jan 1 AND < next Jan 1`) that leaves the column bare so the date index
  applies, replacing `year_str(column) == str(year)` (the function wrapper
  forced a full scan).
- Replaced **13 filter sites**: `charts.py` (7), `fiscal.py` (2),
  `transactions.py` (3). `group_by(year_str(...))` / `year_month_str`
  aggregation keys are unchanged — those are grouping, not filtering.

### Tests — `backend/tests/test_year_range.py` (new)
- 3 regression tests: exact fiscal-year selection, Jan-1/Dec-31 boundary
  correctness, and equivalence with the legacy `year_str` comparison across
  three years. Pins filter semantics against the cross-cutting change.

### Verification
- `pytest backend/tests/` — 122 passed, 35 skipped.
- `ruff check` on changed files: clean except one *pre-existing* unused
  `HTTPException` import in `fiscal.py:7` (untouched line; already noted as
  deferred in Batch 1). No new lint errors introduced.
- `fifo_engine.py` untouched.

---

## Perf Batch 2 — Backend query scoping & DB pool (branch: `claude/nervous-clarke-6ba65c`)

**Status:** Implemented, full backend suite green (119 passed, 35 skipped).
Source: performance audit from 2026-05-29 session.

### Changes — `backend/services/portfolio_service.py` (#5)
- `get_position_detail` no longer recomputes the entire portfolio (all
  transactions + snapshots + a live-price fetch for every holding) just to
  return one ISIN. `get_open_positions` gained an `isins=[...]` scope:
  `_build_tx_positions` filters transactions by ISIN in SQL, and
  `_load_snapshots` narrows `latest`/`historical` to the ISIN while still
  computing `max_year` (the authoritative snapshot year) from the account's
  full holding history. `_apply_prices` derives ISINs from the positions, so
  the live-price fetch is automatically scoped to the single ISIN.

### Changes — `backend/database.py` (#8)
- Postgres/Neon now uses `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`
  (was the SQLAlchemy default of 5 + 10). `pool_pre_ping=True` is deliberately
  kept: Neon autosuspends idle computes, so the per-checkout ping turns a dead
  connection into a transparent reconnect rather than a request error — the
  right trade for serverless Postgres. SQLite takes no pool args.

### Verification
- `pytest backend/tests/` — 119 passed, 35 skipped (the skips need real broker
  files in `files/`, not in the repo). No new failures.
- `fifo_engine.py` untouched.

---

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
