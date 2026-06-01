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
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic |
| Parsers | pdfplumber (PDF), openpyxl (XLSX), csv (IBKR) |
| Options data | yfinance · MEFF HTML scraping · Eurex RDF |
| AI | anthropic SDK — claude-haiku-4-5-20251001 (options analysis) |
| Frontend | Next.js 15 · React 19 · TailwindCSS · Recharts · NextAuth · shadcn/ui |
| DB prod | Neon Postgres |
| DB local | SQLite fallback |
| Deploy | Vercel (frontend) · Google Cloud Run europe-west1 (backend) |
| CI | Cloud Build trigger on push to backend/**, Dockerfile, pyproject.toml, cloudbuild.yaml |
| Tests | pytest · 133 tests (35 skipped — need real PDFs/CSVs in files/) |
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
  importers/          — One file per broker: tr.py, dg.py, ibkr.py, ing.py, bbva.py, etoro.py
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
  api/alt_investments.py — Alt-investments CRUD + /summary consolidation (TVPI/DPI/RVPI)

frontend/
  src/app/page.tsx                  — Main investment dashboard (5 tabs)
  src/app/options/page.tsx          — Options monitor (6 tabs: Cartera, Watchlist, Alertas, Backtest, Análisis, Agente)
  src/app/alt-investments/page.tsx  — Alt-investments dashboard (summary cards, allocation, table, inline form)
  src/components/                   — FileUpload, tables, stat cards
  src/components/charts/            — 8 chart components (Recharts)
  src/lib/                          — API client + TypeScript types
  src/app/zonas-clave/page.tsx      — Zonas Clave dashboard (scope buttons, auto-poll, chart)

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

### Add-ticker flow
- `POST /zonas-clave/watchlist` → persists item → fires `_analyze_single_in_background(item_id, ticker)` in a background thread (only that ticker, not all)
- `POST /zonas-clave/analyze-all` → fires `run_analysis_for_user(user_id)` for all tickers

### Frontend — /zonas-clave
- Left panel: ticker list with trend bias %; clicking selects ticker
- Right panel: trend card (RSI, MACD, price) + price chart + zones table
- Scope buttons (1D / 1W / 1M / 1Y / 5Y / MAX) filter `price_history` client-side; default 1Y
- Auto-polls every 3s when selected ticker has no analysis yet; stops when data arrives
- Scheduler: APScheduler every 24h; start/stop via UI

### Trend bias weights
RSI 30% + MACD 30% + MA50/MA200 avg 40% → composite [-1, +1] → bullish/bearish %

---

## Options monitor — architecture

### Data sources
- **Yahoo Finance**: global options chains; all available expirations exposed via `fetch_expirations()` (instant metadata call). Agent cycle uses first 3 expirations; UI fetches per-expiry on demand.
- **MEFF**: direct HTML scraping from meff.es, 30 verified `.MC` tickers (Ibex-35 blue chips + extended). HV computed via yfinance 60d history since MEFF doesn't publish it.
- **Eurex**: daily RDF file; covers .DE, .PA, .AS, .L, .MI, .SW, .ZU, .BR, .VI, .OL, .ST, .CO, .HE, .LS, .PR suffixes. Cached once per trading day.
- Options chain cached 5 min (TTL) per ticker to avoid redundant scrapes. Per-expiry chains have their own cache keyed by `TICKER:YYYY-MM-DD`.

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
- **Cartera**: positions accordion with P&L; expiry navigator (‹ YYYY-MM-DD › n/total) — expanding a ticker fetches dates only (`GET /options/expirations/{ticker}`); navigating to a date lazy-loads that expiry's chain (`GET /options/chain/{ticker}?expiration=`); cached client-side. IV/HV badge ("IV cara" >+5 / "IV barata" <-5 / "IV normal"), sentiment per ticker.
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
`GET /` list · `GET /summary` consolidation · `POST /` create · `PATCH /{id}` update · `DELETE /{id}`

### Frontend — /alt-investments
Self-contained page (QuickNav, like /portfolio /zonas-clave — not the AppSidebar dashboard).
Summary stat cards + allocation bars + positions table + inline add/edit form (native selects).

### Deferred (original OptionsAI roadmap)
Structured-products barrier/knock-in alerts, private-bank PDF import, AI reporting,
capital-call/distribution movement sub-table.

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

## Critical rules

- fifo_engine.py is the most sensitive file. Any change must be followed by full test suite.
  Never touch it without understanding cross-broker FIFO matching logic.
- Importer changes: each importer is isolated — changes in one must not break others.
  Always run pytest backend/tests/ after importer changes.
- DB migrations: use Alembic. Never modify models.py without a migration.
  Run alembic upgrade head after pulling changes with model changes.
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
- Full deploy docs: docs/deployment.md

---

## Tests

Run: pytest backend/tests/ -v

133 tests pass on clean data. 35 skipped = need real broker files in files/ (not in repo).
If a test breaks, fix it before committing — no exceptions.