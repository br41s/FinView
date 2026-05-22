# Changelog

All notable changes to FinView are documented here.

## [Unreleased]

### Security
- **Startup secret validation** — `FINVIEW_ENV=production` now enforces that
  `FINVIEW_SECRET_KEY` and `FINVIEW_AUTH_SECRET` are non-default at boot.
  Default env is `local` so local dev is unaffected.
- **Removed `user_id or 1` fallback** — missing `user_id` in import service and
  FIFO engine now raises `IntegrityError` instead of silently writing to user 1.
- **Removed ORM `default=1`** on `TaxResult.user_id` and `FIFOAdjustment.user_id`.
- **Auth rate limiting** — `/auth/login` 5 req/min per IP, `/auth/register`
  3 req/min. Thresholds configurable via `FINVIEW_RATE_LIMIT_LOGIN` /
  `FINVIEW_RATE_LIMIT_REGISTER`. Uses rightmost `X-Forwarded-For` entry behind
  Cloud Run (unspoofable by client).

### Added
- **User-visible error states** on all 5 main pages (dashboard, portfolio,
  options, zonas-clave, billing) with inline Retry buttons. Previously all fetch
  errors were swallowed silently to the console.
- **Dashboard loading skeleton** now shows on every year-filter change, not only
  on first mount.

### Performance
- `GET /accounts/` — eliminated 2N lazy-load queries; now 3 queries (was 1 + 2N).
- `GET /fiscal/yearly-comparison` — collapsed 6 queries × N fiscal years into
  2 GROUP BY queries (was 1 + 6N).
- `GET /zonas-clave/analysis` — eliminated 1 query per watchlist item; now 1
  query with subquery (was 1 + N).

### Housekeeping
- Declared `pandas>=2.0` as an explicit dependency — used directly in
  `zonas_clave_analyzer.py` but previously only present as a transitive dep of
  `yfinance`.
- Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)` — 12
  ORM column defaults in `models.py` and 1 call site in `zonas_clave_analyzer.py`
  (Python 3.12 deprecation).
- Removed 4 unused imports: `sqlalchemy.orm.Session` (`auth.py`),
  `dataclasses.field` and `TaxResult` (`fifo_engine.py`), `CasillaOut`
  (`fiscal.py`).
