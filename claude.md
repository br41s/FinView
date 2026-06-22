# FinView

Personal investment dashboard with multi-broker import, Spanish IRPF fiscal engine, and AI-powered options monitor.
Extends root claude.md. Rules here are FinView-specific only.

---

## What this project is

- **Type**: Full-stack web app (personal tool, planning maybe upgrade SaaS)
- **Owner**: Brais — personal investment tracking across TR, DEGIRO, IBKR, ING, BBVA, eToro
- **Core value**: Unified view of dividends, capital gains, IRPF tax boxes, and live options intelligence

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy (create_all + ensure_columns, no Alembic) |
| Parsers | pdfplumber (PDF), openpyxl (XLSX), csv (IBKR) |
| Options data | yfinance · MEFF HTML scraping · Eurex RDF |
| AI | anthropic SDK — claude-haiku-4-5-20251001 (options analysis) |
| Frontend | Next.js 15 · React 19 · TailwindCSS · Recharts · lightweight-charts (price/candles) · NextAuth · shadcn/ui |
| DB prod | Neon Postgres |
| DB local | SQLite fallback |
| Deploy | Vercel (frontend) · Google Cloud Run europe-west1 (backend) |
| CI | Cloud Build trigger on push to backend/**, Dockerfile, pyproject.toml, cloudbuild.yaml |
| Tests | pytest · 151 tests (35 skipped — need real PDFs/CSVs in files/) |
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
  api/                — Endpoints: imports, transactions, fiscal, charts, options
  importers/          — One file per broker: tr.py (+ tr_v2.py, tr_csv.py), dg.py, ibkr.py, ing.py, bbva.py, etoro.py
  services/
    fifo_engine.py         — Cross-broker FIFO engine — most critical, touch carefully
    import_service.py      — Import logic + deduplication
    prices.py              — Yahoo Finance price cache
    options_scraper.py     — Yahoo Finance + MEFF (30 .MC tickers) + Eurex RDF scraper
    options_agent.py       — Monitor agent: Observe→Greeks→Analyze→Store→Notify→Claude cycle
    options_analyzer.py    — Rule-based analysis: IV, P/C ratio, IV skew, unusual volume
    greeks_calculator.py   — Black-Scholes Delta/Gamma/Theta/Vega/Rho enrichment
    premium_spike.py       — In-memory EMA baseline; fires HIGH alert when premium ≥ 2.5× EMA
    backtest_service.py    — record_signal() + evaluate_pending() at +1d/+3d/+7d horizons
    notification_service.py — ntfy.sh push + Gmail SMTP + Telegram Bot API
    exchange_rates.py      — ECB reference-rate service (DB cache + ±7d fallback); official FX fallback for IRPF
    cnmv_catalog.py        — CNMV IIC registry → searchable catalog for the alt-investments search bar
  api/alt_investments.py — Alt-investments CRUD + /summary consolidation (TVPI/DPI/RVPI) + /search

frontend/
  src/app/page.tsx                  — Main investment dashboard (5 tabs)
  src/app/options/page.tsx          — Options monitor (6 tabs: Cartera, Watchlist, Alertas, Backtest, Análisis, Agente)
  src/app/alt-investments/page.tsx  — Alt-investments dashboard (summary cards, allocation, table, inline form)
  src/components/                   — FileUpload, tables, stat cards
  src/components/charts/            — 8 Recharts components + PriceChart + ZonasClaveChart (lightweight-charts)
  src/lib/                          — API client + TypeScript types; chartMarkers.ts (execution markers + scope slicing)
  src/app/zonas-clave/page.tsx      — Zonas Clave dashboard (scope buttons, auto-poll, chart)
  src/app/markets/page.tsx          — Markets: localStorage watchlist + candlestick viewer (suggestions from portfolio)

---

## Zonas Clave — architecture

Pure technical analysis engine for support/resistance detection. No AI calls.

### Pipeline per ticker
`fetch_history (10y daily) → detect_pivots → cluster_pivots → compute_zone_strength → RSI → MACD → MAs → trend_bias → store ZonasClaveAnalysis`

### Key constants (zonas_clave_analyzer.py)
- `_HISTORY_PERIOD = "10y"` — yfinance download window
- `_PIVOT_WINDOW = 10` — bars each side for pivot detection
- `_CLUSTER_THRESHOLD = 0.015` — 1.5% merge radius for zone clustering
- `_MAX_ZONES = 8` — top zones returned (scored by touches × volume)
- All bars sent to frontend (no server-side truncation); frontend slices by scope
- `price_history` points carry full OHLC (`open/high/low/close`) + `volume`; OHLC drives candlesticks

### Add-ticker flow
- `POST /zonas-clave/watchlist` → persists item → fires `_analyze_single_in_background(item_id, ticker)` in a background thread (only that ticker, not all)
- `POST /zonas-clave/analyze-all` → fires `run_analysis_for_user(user_id)` for all tickers

### Frontend — /zonas-clave
- Left panel: ticker list with trend bias %; clicking selects ticker
- Right panel: trend card (RSI, MACD, price) + candlestick chart + zones table.
  Chart is `components/charts/ZonasClaveChart.tsx` (TradingView lightweight-charts v5,
  candlesticks + S/R as `createPriceLine` overlays; line-series fallback for pre-OHLC
  stored analyses). Attribution logo on (Apache-2.0). Other charts stay on Recharts.
- Scope buttons (1D / 1W / 1M / 1Y / 5Y / MAX) filter `price_history` client-side; default 1Y
- Auto-polls every 3s when selected ticker has no analysis yet; stops when data arrives
- Scheduler: APScheduler every 24h; start/stop via UI

### Trend bias weights
RSI 30% + MACD 30% + MA50/MA200 avg 40% → composite [-1, +1] → bullish/bearish %

---

## Price charts (lightweight-charts) — shared infra

`components/charts/PriceChart.tsx` is the one generic price chart used everywhere
except Zonas Clave's wrapper: candlesticks (line-series fallback when OHLC absent),
optional `priceLines` (S/R, strikes, spot) and optional `markers` (executions).
Attribution logo on (Apache-2.0). Theme-aware via next-themes (canvas can't read CSS vars).

- **Data**: `GET /charts/price-history?ticker=&period=` (charts.py) — daily OHLC from
  yfinance, period whitelisted {6mo,1y,2y,5y,10y,max}, best-effort (returns `[]` on any
  failure → caller hides the chart). Read-only; never touches FIFO/transactions.
- **lib/chartMarkers.ts**: `executionMarkers(txs)` (BUY ▲ / SELL ▼ / DIVIDEND ●, same-day
  same-type collapsed into one marker labelled with the count) + `sliceOhlc(bars, scope)`
  + `CHART_SCOPES` (1D / 1W / 1M / 1A / 5A / MAX, client-side slicing).
- **Used in**:
  - `/portfolio` list expansion + `/portfolio/[isin]`: candles + buy/sell/dividend markers.
    Dividends come from `position_detail`'s `dividend_events` (kept out of `transactions`
    so the history table stays buy/sell only). Window auto-sized to the oldest trade.
  - `/options` Cartera: underlying candles + spot (solid) + near-money strikes (3 below,
    3 above, dashed) from the selected expiry's chain; OHLC fetched `max`, cached per ticker.
  - `/markets`: localStorage watchlist; OHLC fetched `max` once, sliced client-side.

---

## Options monitor — architecture

### Data sources
- **Yahoo Finance**: global options chains; all available expirations exposed via `fetch_expirations()` (instant metadata call). Agent cycle uses first 3 expirations; UI fetches per-expiry on demand.
- **MEFF**: direct HTML scraping from meff.es, 30 verified `.MC` tickers (Ibex-35 blue chips + extended). HV computed via yfinance 60d history since MEFF doesn't publish it.
- **Eurex**: daily RDF file; covers .DE, .PA, .AS, .L, .MI, .SW, .ZU, .BR, .VI, .OL, .ST, .CO, .HE, .LS, .PR suffixes. Cached once per trading day.
- Options chain cached 5 min (TTL) per ticker to avoid redundant scrapes. Per-expiry chains have their own cache keyed by `TICKER:YYYY-MM-DD`.
- **Availability check** (`POST /options/check-availability`, cached 24h): routes per source so the UI doesn't flag tickers as "no options" wrongly. ISIN → always visible; `.MC` → visible if base in `_MEFF_SLUGS` (Yahoo has no Spanish options, so never delegate `.MC` to Yahoo); European suffix → check Eurex RDF `sym_to_code`; else Yahoo `t.options`.

### Agent cycle (options_agent.py)
1. Fetch watchlist tickers for the user
2. For each ticker: fetch chain → enrich with Greeks → rule analysis → premium spike detection → store snapshot + alerts + unusual activity → record backtest signals (HIGH/MEDIUM)
3. evaluate_pending() resolves outcomes from previous cycles
4. If `ANTHROPIC_API_KEY` set and alerts exist → Claude analysis (7-section Markdown)
5. notify_alerts() → ntfy.sh + email; notify_spike_telegram() → Telegram for PREMIUM_SPIKE

### Claude analysis prompt
Agent persona: *VolatilityEdge* (quant analyst, senior). Spanish only. Structured as exactly 7 sections:
`## 1. Resumen Ejecutivo` / `## 2. Smart Money` / `## 3. Señales Greeks` / `## 4. Top Picks` / `## 5. Catalizadores` / `## 6. Contexto MEFF` (only if .MC tickers present) / `## 7. Gestión de Riesgo`
Model: claude-haiku-4-5-20251001 · max_tokens: 1500 · max 750 words in output.
Result stored in `OptionsAgentLog.result_json` as `claude_analysis` key.

### Premium spike detector
Tracks (ticker, option_type, strike) EMA baseline per user in memory (resets on server restart).
Fires `PREMIUM_SPIKE` severity=HIGH when `current_premium ≥ 2.5 × EMA` and `current_premium ≥ $0.10` and `samples ≥ 3`. EMA α = 0.3.

### Backtest engine
- `record_signal()`: stores every HIGH/MEDIUM alert as a `BacktestSignal` with direction (BULLISH/BEARISH derived from alert type)
- `evaluate_pending()`: fetches current price via yfinance, fills `price_at_1d/3d/7d`, marks CORRECT/NEUTRAL/INCORRECT per horizon (threshold ±0.5%)
- UI shows accuracy % per horizon and per signal type in the Backtest tab

### Frontend — /options (6 tabs)
- **Cartera**: positions accordion with P&L; expiry navigator (‹ YYYY-MM-DD › n/total) — expanding a ticker fetches dates only (`GET /options/expirations/{ticker}`); navigating to a date lazy-loads that expiry's chain (`GET /options/chain/{ticker}?expiration=`); cached client-side. IV/HV badge ("IV cara" >+5 / "IV barata" <-5 / "IV normal"), sentiment per ticker. Underlying `PriceChart` above the chain (spot + near-money strikes; see "Price charts").
- **Watchlist**: add/remove tickers; stats bar shows aggregated P/C ratio → Alcista/Neutral/Bajista with color
- **Alertas**: all cycle alerts filtered by severity (HIGH/MEDIUM/LOW)
- **Backtest**: accuracy table +1d/+3d/+7d per signal type; per-ticker breakdown
- **Análisis**: calls `GET /options/agent/last-analysis`; parses `## N.` Markdown sections via `parseAnalysisSections()`; renders each section as a Card; shows cycle metadata header (timestamp, tickers, alerts, sentiment)
- **Agente**: scheduler status, cycle metrics, chat input → `POST /options/agent/chat`

---

## Alt-Investments — architecture

Manual tracker for alternative investments held in private banking (PE/VC/Real Estate,
plus Hedge Fund / Structured Product / Other). MVP: no AI, no import — pure CRUD + metrics.

### Model (`AltInvestment`)
- One row per position. Cash flows stored as running **aggregates** (not a movement
  sub-table): `committed_capital`, `called_capital`, `distributed_capital`, `current_nav`.
- Plus: `type`, `status` (ACTIVE/REALIZED), `manager`, `vintage_year`, `geography`, `currency`, `notes`.
- New tables auto-create via `Base.metadata.create_all` on startup (no Alembic needed for adds).

### Derived metrics (computed in `api/alt_investments.py`, never stored)
- **TVPI** = (distributed + NAV) / called · **DPI** = distributed / called · **RVPI** = NAV / called
- **Unfunded** = committed − called · **Total value** = distributed + NAV
- All None when called = 0. `/summary` aggregates portfolio totals + NAV-weighted allocation by type/geo/currency.

### Endpoints (`/alt-investments/...`)
`GET /` list · `GET /summary` consolidation · `GET /search?q=&type=` CNMV catalog search ·
`POST /` create · `PATCH /{id}` update · `DELETE /{id}`

### Search — CNMV catalog (`services/cnmv_catalog.py`)
Search bar finds regulated Spanish funds by name or ISIN and pre-fills the add form
(identity only — name, type, gestora, ISIN; amounts stay manual).
- Source: free CNMV "información individual de IIC" monthly ZIP (no auth). Download flow:
  fetch the year page → BeautifulSoup the latest `lnkZip` (opaque `verdocumento/ver?e=`
  token) → `_download_zip_members` reads two XMLs (1 retry on transient drop):
  **FONDREGISTRO** (identity) → `_parse_registry`, one `alt_investment_catalog` row per
  share-class ISIN; **FONDMENS** (NAV/fund size) → `_parse_mens`, merged by ISIN.
- Enrichment: `nav` = class's latest daily VL (`VL_DiaN`); `fund_size` = sum of latest
  `Patrimonio_DiaN` across the fund's classes; `data_date` from root `FechaDatos`.
- `refresh_iic_catalog()` upserts the catalog; runs in a background thread on startup when
  `catalog_is_stale` (>7 days). Best-effort, never blocks/breaks the page. Never per request.
- `search_catalog(db, q, type_filter, min_fund_size, max_fund_size, sort, limit)` is DB-only:
  ILIKE on name + exact ISIN, prefix matches rank first. `sort` ∈ {name, fund_size_desc,
  nav_desc, nav_asc}. **Browse mode**: short/empty `q` still returns rows when a filter or
  non-default sort is set; otherwise `[]`.
- Coverage: the monthly file is Fondos de Inversión (Tipo=FI) only — ~1,400 funds / ~3,000 ISINs,
  mapped to `OTHER`, all with NAV + fund size. SICAV / real-estate IIC / hedge / PE-VC live in
  separate CNMV registries (deferred); `_TIPO_MAP` already wired for FII→REAL_ESTATE, FIL→HEDGE_FUND.
  PE metrics (DPI/TVPI/IRR/vintage/commitment/hurdle) aren't public — manual on positions.

### Frontend — /alt-investments
Self-contained page (QuickNav, like /portfolio /zonas-clave — not the AppSidebar dashboard).
Top search bar (debounced 300ms → `/search` → results dropdown → click pre-fills the form) +
summary stat cards + allocation bars + positions table + inline add/edit form (native selects).

### Deferred (original OptionsAI roadmap)
Structured-products barrier/knock-in alerts, private-bank PDF import, AI reporting,
capital-call/distribution movement sub-table. Search: CNMV ECR (PE/VC) + SICAV/RE/hedge registries,
listed SOCIMIs via Yahoo.

---

## Exchange rates — ECB service

`services/exchange_rates.py` — official EUR reference rates as an IRPF fallback when a broker
file omits the rate or for manual entries. Ported from OptionsAI.
- `ExchangeRate` table (rate_date, currency, rate, source); unique (rate_date, currency).
- `sync_rates()` runs in a background thread on startup: full ECB history on first boot,
  then the 90-day feed; skips if already fresh (≤1 day). Never runs inside a request.
- `get_rate(currency, on)` is DB-only (no HTTP), with ±7-day fallback for weekends/holidays.
  `to_eur(amount, currency, on)` = amount / rate. EUR is always 1.
- Lookup endpoint: `GET /fiscal/fx-rate?currency=USD&on=YYYY-MM-DD`.

---

## Trade Republic importer — formats & migration year

`parse_tr_tax_report()` (tr.py) dispatches by report layout:
- **`legacy`** — pre-2025 full-year Roman-numeral report (Modelo 100 = Section VIII,
  Modelo 714 = IX, Section VI transaction history imported).
- **`tr_de_premigration`** — partial-year report issued when the account moved
  DE→ES IBAN (cover says "migró a un IBAN español"). Same legacy layout but
  Modelo 100 shifts to **Section VII** (no patrimonio/714), Saveback rows count as
  casilla 27, and Section VI is **dropped** (fiscal figures only — its positions
  were transferred to the ES account, which owns the year-end holdings).
- **`es_branch`** — 2025+ Sucursal España report (tr_v2.py, `is_spanish_branch_format`).

A migration year has **two** TR reports (pre + post). They must coexist, not
replace each other:
- `TRTaxReport.source_variant` is persisted on `ImportRecord.source_variant` and is
  part of the year-replace key (`_check_year_duplicate(broker, year, variant)`), so
  re-uploading either file replaces only its own slot.
- `tax_results` rows are owned by `import_id` (no UNIQUE on broker+casilla — a
  broker can have two reports/year); `fiscal.py` sums rows per casilla and sums TR
  reference amounts. Deletion is scoped by `import_id` (legacy NULL rows swept by
  broker+year). Upload each PDF separately — both persist and combine.
- tr_csv.py imports the TR transaction-export CSV (multi-year ledger, dedups by
  date/isin/type/qty, never year-replaces).

---

## Auth & security

### Auth flow
- Frontend `NextAuth` (Credentials provider, `frontend/src/auth.ts`) → backend `/api/auth/login`.
  Backend issues an HS256 JWT signed with `FINVIEW_SECRET_KEY`; NextAuth stores it as
  `accessToken` and the API client (`src/lib/api.ts`) sends it as `Authorization: Bearer`.
- Passwords: bcrypt (`auth_service.py`). JWT + NextAuth session both last **90 days**.
- `FINVIEW_AUTH_SECRET` (backend) **must equal** `AUTH_SECRET` (frontend) or every request
  fails with "Invalid token".

### Secret enforcement
- `config.py` blocks startup if `FINVIEW_ENV ∈ {staging,production,prod}` and `secret_key`
  or `auth_secret` is missing / still the insecure default. **`FINVIEW_ENV=production` must
  be set on Cloud Run** or the guard never fires and JWTs sign with the public default.

### Turnstile (bot protection on login)
- Cloudflare Turnstile gates login. Token: login page → NextAuth `authorize` →
  backend body `turnstile_token` → `services/turnstile.py` verifies via Cloudflare siteverify.
- **No-op when `FINVIEW_TURNSTILE_SECRET` is unset** (dev/unconfigured deploys work unchanged).
  Frontend widget renders only when `NEXT_PUBLIC_TURNSTILE_SITE_KEY` is set.
- **Fail-closed**: missing/invalid token or any verify error → 403. Flip the `except` in
  `turnstile.py` to fail-open if a Cloudflare outage blocking logins is unacceptable.
- Login only (not register) — register Turnstile is a deferred follow-up.

### HTTP security headers
- Set on every response in `frontend/next.config.ts` (`headers()`): `X-Frame-Options: DENY`,
  CSP `frame-ancestors 'none'`, HSTS, `X-Content-Type-Options`, `Referrer-Policy`,
  `Permissions-Policy`. **Intentionally no content-CSP** (`script-src` etc.) — would break
  Next.js inline scripts / Recharts. Don't add one without testing every page.

### Rate limiting
- slowapi per-IP on login (`5/minute`) and register (`3/minute`), in-memory per instance.
  Client IP = **rightmost** `X-Forwarded-For` entry (the value Cloud Run's GFE appended;
  leftmost is spoofable). See `services/rate_limit.py`.

### Privacy mode (dashboard)
- Eye toggle in the dashboard header sets `data-privacy` on `<main>`; CSS blurs any
  `.fv-sensitive` value (`globals.css`). Persisted in `localStorage` (`fv-privacy`).
  Currently tags StatsCards money only — add the class to extend to tables/charts.

---

## Critical rules

- fifo_engine.py is the most sensitive file. Any change must be followed by full test suite.
  Never touch it without understanding cross-broker FIFO matching logic.
- Importer changes: each importer is isolated — changes in one must not break others.
  Always run pytest backend/tests/ after importer changes.
- DB schema: there is **no Alembic**. New tables auto-create via
  `Base.metadata.create_all` on startup. `create_all` does NOT alter existing tables, so
  adding a column to a table that already exists in prod requires registering it in
  `database._ADDITIVE_COLUMNS` (applied idempotently by `ensure_columns()` at startup).
  Dropping an obsolete UNIQUE constraint in prod (Postgres only) goes in
  `database._DROP_UNIQUE_CONSTRAINTS` (applied by `ensure_constraints()`); SQLite tables
  are rebuilt from the model and never carry it.
- No breaking changes to API contracts without updating frontend src/lib/ types.
- options_scraper.py cache TTL (5 min) must not be removed — MEFF rate-limits scraping.
- Premium spike baselines are in-memory only. Do not try to persist them to DB.
- Claude analysis is fire-and-forget; non-availability must never break the agent cycle.
  Always guard: `if _ANTHROPIC_AVAILABLE and settings.anthropic_api_key and all_alerts`.

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
- Cloud Run runtime flags in cloudbuild.yaml are load-bearing: `--no-cpu-throttling` +
  `--cpu-boost` + `--memory=1Gi` (+ `--min-instances=0`). Without `--no-cpu-throttling`,
  CPU is throttled outside requests and the startup background loaders (Eurex RDF ~63s,
  ECB FX-sync, CNMV catalog) never finish — European options stop loading. Do not remove these.
  `--min-instances=0` scales to zero (cost ~0) but cold starts re-pay the ~63s Eurex preload;
  bump to 1 (~€45/mo always-on) only if always-instant European data is worth it.
- Full deploy docs: docs/deployment.md

---

## Tests

Run: pytest backend/tests/ -v

151 tests pass on clean data. 35 skipped = need real broker files in files/ (not in repo).
If a test breaks, fix it before committing — no exceptions.