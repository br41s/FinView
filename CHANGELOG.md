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
- **Alt-investments search (CNMV)** — a search bar at the top of `/alt-investments`
  finds regulated Spanish investment funds by name or ISIN and pre-fills the add
  form (name, type, gestora, ISIN). Backed by a new `alt_investment_catalog` table
  populated from the free CNMV "información individual de IIC" monthly registry
  (`services/cnmv_catalog.py`): ~3,000 share-class ISINs across ~1,400 funds,
  refreshed in a background thread on startup when stale (>7 days). Endpoint
  `GET /alt-investments/search?q=&type=`. Amounts stay manual — the catalog only
  supplies identity. (SICAVs, real-estate IICs, hedge funds and PE/VC live in
  separate CNMV registries — deferred to later slices.)
- **Additive column migration on startup** — `database.ensure_columns()` adds
  columns to tables that already exist in production (which `create_all` cannot
  alter), starting with `alt_investments.isin`. Idempotent, dialect-safe.
- **Alternative investments tracker** — new `/alt-investments` page and
  `/api/alt-investments` endpoints to manually track private-banking positions
  (Private Equity, Venture Capital, Real Estate, Hedge Fund, Structured Product,
  Other). Stores committed/called/distributed/NAV aggregates per position and
  derives the standard PE metrics — TVPI, DPI, RVPI, unfunded commitment — plus
  a `/summary` consolidation with NAV-weighted allocation by type, geography and
  currency. UI has summary cards, allocation bars, a positions table and an
  inline add/edit form. Migrated as an MVP from the OptionsAI "coming soon" spec.
- **ECB exchange-rate service** — `services/exchange_rates.py` caches official
  ECB EUR reference rates in a new `exchange_rates` table as an IRPF fallback for
  when a broker file omits the rate or for manual entries. Syncs in a background
  thread on startup (full history first boot, then 90-day feed, skipped if
  fresh); `get_rate()` is DB-only with ±7-day weekend/holiday fallback. Lookup
  via `GET /fiscal/fx-rate?currency=USD&on=YYYY-MM-DD`. Ported from OptionsAI.
- **User-visible error states** on all 5 main pages (dashboard, portfolio,
  options, zonas-clave, billing) with inline Retry buttons. Previously all fetch
  errors were swallowed silently to the console.
- **Dashboard loading skeleton** now shows on every year-filter change, not only
  on first mount.
- **Options monitor — Análisis tab** — new 6th tab in `/options` that renders
  the last Claude analysis cycle as 7 structured section cards (Resumen
  Ejecutivo, Smart Money, Señales Greeks, Top Picks, Catalizadores, Contexto
  MEFF, Gestión de Riesgo) plus a cycle metadata header (timestamp, tickers
  analyzed, total alerts, sentiment). Powered by `GET /options/agent/last-analysis`.
- **Historical Volatility for MEFF tickers** — `.MC` tickers now compute HV
  from 60 days of yfinance price history (`log(Close/Close.shift(1)).std() ×
  √252 × 100`) since MEFF HTML does not publish HV. Previously HV was `None`
  for all MEFF tickers.
- **`GET /options/agent/last-analysis`** — new endpoint returning the most
  recent agent cycle metadata and the full Claude markdown analysis for the
  authenticated user.

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
