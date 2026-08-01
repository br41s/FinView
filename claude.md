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
| AI | OpenRouter (hand-rolled httpx) — `settings.openrouter_model`, default `deepseek/deepseek-v4-flash`. One shared model for options analysis + geo analyst. |
| Frontend | Next.js 15 · React 19 · TailwindCSS · Recharts · lightweight-charts (price/candles) · NextAuth · shadcn/ui |
| DB prod | Neon Postgres |
| DB local | SQLite fallback |
| Deploy | Vercel (frontend) · Google Cloud Run europe-west1 (backend) |
| CI | Cloud Build trigger on push to backend/**, Dockerfile, pyproject.toml, cloudbuild.yaml |
| Tests | pytest · 506 collected (375 pass, ~131 skip without real broker PDFs/CSVs in files/) · vitest · 18 frontend tests |
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
    watchlist_service.py   — Canonical followed-instruments model (see "Watchlist unificada")
    options_scraper.py     — Yahoo Finance + MEFF (30 .MC tickers) + Eurex RDF scraper
    options_agent.py       — Monitor agent: Observe→Greeks→Analyze→Store→Notify→Claude cycle
    options_analyzer.py    — Rule-based analysis: IV, P/C ratio, IV skew, unusual volume
    greeks_calculator.py   — Black-Scholes Delta/Gamma/Theta/Vega/Rho enrichment
    premium_spike.py       — In-memory EMA baseline; fires HIGH alert when premium ≥ 2.5× EMA
    backtest_service.py    — record_signal() + evaluate_pending() at +1d/+3d/+7d horizons
    notification_service.py — ntfy.sh push + Gmail SMTP + Telegram Bot API
    exchange_rates.py      — ECB reference-rate service (DB cache + ±7d fallback); official FX fallback for IRPF
    cnmv_catalog.py        — CNMV IIC registry → searchable catalog for the alt-investments search bar
    zonas_clave_analyzer.py — Pure TA: pivots → zones → RSI/MACD/MA → trend bias (no AI)
    zone_proximity.py      — Deterministic gate: which zones price is within 2% of (pure)
    zone_scorer.py         — LLM break-probability scorer; only sees gated candidates
    technical_signals.py   — Gate + scorer + persist; alerts only above ALERT_THRESHOLD
    macro_context.py       — FRED regime (VIX/curve/stress/HY) — annotation, never a gate
    fred_rates.py          — Risk-free rate per currency + macro series cache
    geo/                   — Ideas pipeline (WorldHawk port): ingest/ + sentinel, analyst, advisor, auditor, notify, orchestrator, scheduler, ais_collector
  api/alt_investments.py — Alt-investments CRUD + /summary consolidation (TVPI/DPI/RVPI) + /search
  api/geo.py             — Ideas endpoints: signals, run, scheduler control, /geo/cron (external cron entry)
  api/zonas_clave.py     — Zonas Clave: watchlist, analysis, /signals (technical), /cron

frontend/
  src/app/page.tsx                  — Public landing (FinviewIntro)
  src/app/dashboard/page.tsx        — Fiscal dashboard: 8 views as horizontal tabs
                                      (Dashboard/Rendimiento/Dividendos/Casillas/Ganancias/
                                      Mi declaración/Comparativa/Importar; fiscal tabs only
                                      when a year is selected). Header: year selector,
                                      privacy toggle, billing + logout, QuickNav. QuickNav is
                                      the single global nav on every section (the old
                                      AppSidebar was removed in PR #124, its dead file in #151).
  src/app/options/page.tsx          — Options monitor (5 tabs: Watchlist, Monitor, Backtesting, IA, Agente)
  src/app/alt-investments/page.tsx  — Alt-investments dashboard (summary cards, allocation, table, inline form)
  src/components/                   — FileUpload, tables, stat cards
  src/components/charts/            — 8 Recharts components + PriceChart + ZonasClaveChart (lightweight-charts)
  src/lib/                          — API client + TypeScript types; chartMarkers.ts (execution markers + scope slicing)
  src/app/zonas-clave/page.tsx      — Zonas Clave dashboard (ticker search box, scope buttons,
                                      auto-poll, chart). Absorbed the standalone /markets page
                                      (PR #125) — its candlestick-viewer search box and
                                      last-close change readout were ported in, /markets removed.
  src/app/geo-intel/page.tsx        — Ideas dashboard (map + signal feed + thesis panel;
                                      components in src/components/geo-intel/). Route/table/API
                                      keep the `geo` name — only the UI label is "Ideas".
  src/components/instrument/        — PrecioTab + OpcionesTab only (the drawer and its other
                                      3 tabs were deleted in PRs #151/#152)

---

## Watchlist unificada — followed_instruments (Fase B, PRs #142 · #145 · #146)

One canonical row per (user, ticker) in `followed_instruments`, with **opt-in
per-section lenses** — membership has per-section cost, so nothing auto-subscribes:
- `options_enabled` — in the options watchlist / agent scope; `options_paused`
  keeps it listed but the agent skips it (maps the legacy `enabled=False`).
- `zonas_enabled` — has a synced `zonas_clave_watchlist` child row. That child is
  an internal detail kept ON PURPOSE: `ZonasClaveAnalysis` cascades off its FK and
  we do no DDL surgery in prod. Never create/delete child rows directly — go
  through `services/watchlist_service.py` (`enable_zonas`/`disable_zonas`).
- A row with no lens on is pruned. Removing a ticker from one section only turns
  off that lens.
- Legacy `watchlist_items` is GONE (B3, PR #145): no ORM model; the one-off
  lifespan migration reads any remaining rows via raw SQL and drops the table
  (stranded rows from an old revision keep it + warn). Wrapped in try/except so
  concurrent boots / transient DB errors never kill the instance. Re-pointing
  the analyses FK was evaluated and rejected (2026-07-16) — don't revisit
  unless the synced child produces a real bug.
- API response shapes are unchanged — sections talk to their own endpoints.
- **Cross-section lens toggles (D2-A, PR #146)**: the options watchlist has a
  "Técnico" chip column (toggles the zonas lens; enabling fires the S/R
  analysis, exactly like adding from /zonas-clave) and each zonas list row has
  an Activity toggle for the options lens. Frontend-only — both directions ride
  the per-section endpoints; lens state loads best-effort on mount and is
  re-fetched after each toggle. Known interaction: the options auto-sync
  re-adds held positions on the next /options load, so for portfolio tickers
  the definitive off-switch is "Ocultar del monitor" in Cartera.

---

## Zonas Clave — architecture

Support/resistance engine. The **analysis** is pure TA with no AI
(`zonas_clave_analyzer.py` must stay that way); the **signal emission** built on
top of it does call an LLM — see "Technical signals" below.

### Technical signals (Slice 4) — the trigger layer

Zonas Clave is the trigger layer of the signal architecture: technical proximity
fires, Options Monitor executes with PUT/CALL, Ideas carries the thesis.

```
zones (zonas_clave_analyzer)
  → zone_proximity.detect_proximity_candidates   deterministic, free
  → zone_scorer.score_break_probability          LLM, candidates only
  → TechnicalSignal rows                          ALL scored candidates
  → alerted=True + BacktestSignal                 only > ALERT_THRESHOLD (70)
```

- **The gate is what bounds token spend.** `PROXIMITY_THRESHOLD = 0.02` (2%);
  its floor is `_CLUSTER_THRESHOLD` (1.5%) — closer than that and you're *inside*
  the zone, not near it. Most tickers most days produce zero candidates, so the
  LLM is never called.
- **Break direction comes from which side price is on, NOT from `zone_type`.**
  A level built from pivot highs is labelled "resistance" forever; once price
  trades above it, it acts as support and the pending move is a breakdown.
  Trusting the label inverts the direction on every flipped level.
- **The 70 cut is uncalibrated and should be described that way.** An LLM's
  "73%" is an opinion with a number attached. That's why *every* scored
  candidate is persisted, sub-threshold included — it's the only way to ever
  check whether >70 breaks more often than <70 and move the cut on evidence.
  Same reasoning as Phase 2b regime instrumentation. `GET /zonas-clave/signals`
  returns everything by default; `alerted_only=true` is the Monitor's view.
- **`break_probability = NULL` means "no score"** (no API key, LLM failure,
  unparseable answer). Never coerce it to 0 — that reads as "certainly won't
  break" in any later calibration, and it must not alert either.
- Scores are cached per (ticker, level rounded to 2dp, UTC day); proximity lasts
  days, so without it every cycle re-pays the same call. `_already_open()` dedups
  the *rows* separately, since a cache miss (restart, TTL) would still duplicate.
- Signal emission shares the analysis transaction and never raises: the zones are
  the product, signalling is a bonus on top.
- Technical signals ride `BacktestSignal` as `signal_type="ZONE_BREAK"`, bypassing
  `backtest_service.record_signal()` — that derives direction by keyword-matching
  the message and has no ZONE_BREAK case. Direction is already known exactly here.

### Scheduling — prod runs on external cron, NOT APScheduler
Third instance of the same rule as geo and options: `zonas_clave_scheduler.py`
(APScheduler, the UI's start/stop) dies on scale-to-zero with `--min-instances=0`.
**Prod periodicity = Cloud Scheduler → `POST /api/zonas-clave/cron`**, same
`X-Cron-Key == FINVIEW_CRON_SECRET` shared secret, synchronous per user.
This was latent until Slice 4: before the analysis emitted signals, a missed
cycle cost nothing because nobody was waiting on the output.

### Pipeline per ticker
`fetch_history (20y daily) → zone_window (trailing 10y) → detect_pivots → cluster_pivots → compute_zone_strength → RSI → MACD → MAs → trend_bias → store ZonasClaveAnalysis → emit technical signals`

### Key constants (zonas_clave_analyzer.py)
- **Two windows, on purpose — don't collapse them into one constant:**
  - `_HISTORY_PERIOD = "20y"` — download window. Exists for `price_history`, i.e. the
    chart's MAX scope (a2bc58e also lowered lightweight-charts' `minBarSpacing` so
    decades actually render). "max" was tried and reverted: split-adjusted 1980s
    penny prices.
  - `_ZONE_LOOKBACK_YEARS = 10` — pivot detection + the median volume that scores
    zones (`zone_window()`). A level last touched 15 years ago isn't support today,
    and older levels accumulate touches purely from having had more calendar time.
    Charting wants all the history it can render; zones want only live structure.
  - Trimming the volume median matters as much as trimming the pivots: it's the
    denominator of `vol_score`, so measuring it over 20y scored current zones
    against a decade-old volume regime (SAN.MC: 62.5M over 20y vs 43.5M over 10y).
  - `zone_window()` falls back to the full frame when trimming would leave fewer
    than `_MIN_BARS` (thin tickers, recent IPOs) — stale levels beat no levels.
- `_PIVOT_WINDOW = 10` — bars each side for pivot detection
- `_CLUSTER_THRESHOLD = 0.015` — 1.5% merge radius for zone clustering
- `_MAX_ZONES = 8` — top zones returned (scored by touches × volume)
- All bars sent to frontend (no server-side truncation); frontend slices by scope
- `price_history` points carry full OHLC (`open/high/low/close`) + `volume`; OHLC drives candlesticks

### Add-ticker flow
- `POST /zonas-clave/watchlist` → persists item → fires `_analyze_single_in_background(item_id, ticker)` in a background thread (only that ticker, not all)
- `POST /zonas-clave/analyze-all` → fires `run_analysis_for_user(user_id)` for all tickers
- Two entry points into the same `addTicker`/watchlist state: portfolio quick-add chips
  ("Sin analizar" section, positions-only) and a free-text search box (ticker/name/ISIN,
  ported from the old `/markets` page) that can add any ticker, not just held ones. The
  search box lives in the left panel and renders even with an empty watchlist.

### Frontend — /zonas-clave
- Left panel: search box (add any ticker) + ticker list with trend bias %; clicking selects ticker
- Right panel: trend card (RSI, MACD, price) + candlestick chart + zones table.
  Chart is `components/charts/ZonasClaveChart.tsx` (TradingView lightweight-charts v5,
  candlesticks + S/R as `createPriceLine` overlays; line-series fallback for pre-OHLC
  stored analyses). Attribution logo on (Apache-2.0). Other charts stay on Recharts.
  Chart header shows a last-close change readout (points + %, colored, ↑/↓ icon) computed
  client-side from the last two `price_history` closes.
- Scope buttons (1D / 1W / 1M / 1Y / 5Y / MAX) filter `price_history` client-side; default 1Y
- Auto-polls every 3s when selected ticker has no analysis yet; stops when data arrives
- Scheduler: APScheduler every 24h; start/stop via UI
- **No options content here, on purpose.** The right panel used to carry an "Opciones"
  card (`OpcionesTab`); it was dropped so each page owns one layer: Zonas Clave =
  technical trigger, Options Monitor = PUT/CALL execution, Ideas = investment thesis.
  The D2-A cross-section lens toggles stay — a toggle is subscription, not content.

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
  - `OpcionesTab` (`components/instrument/OpcionesTab.tsx`): underlying candles +
    spot (solid) + near-money strikes (3 below, 3 above, dashed) from the selected
    expiry's chain. Embedded in the Options Watchlist row expand (mobile + desktop)
    — and **only** there: options content is confined to the Options Monitor page.

---

## Instrument tab components — two survivors, inline only

There used to be a global `InstrumentDrawer` slide-over with five tabs, kept as
the building blocks for a future `/ticker/[symbol]` page. **Both are gone**
(PRs #151, #152): the drawer, `app-sidebar.tsx`, and the three tabs only it
reached (`ZonasTab`, `FiscalTab`, `DividendosTab`) plus the `usePositionDetail`
hook. Don't go looking for them.

`/ticker/[symbol]` was **dropped on purpose, not deferred**: a page mixing
fiscal + options + zonas for one ticker is the opposite of "each page owns one
layer". If it's ever revived it's a rebuild, not a reassembly.

Two components remain under `components/instrument/`, embedded inline where they
belong and nowhere else:
- **`PrecioTab.tsx`** — `PriceChart` + `/charts/price-history` + scope buttons.
  Used in Ideas' signal detail panel (`components/geo-intel/SignalPanel.tsx`),
  under the ticker chips.
- **`OpcionesTab.tsx`** — on-demand per-ticker AI report
  (`POST /options/agent/analyze-ticker` → `analyze_single_ticker`, 5-section
  VolatilityEdge prompt, runs regardless of alerts, AI failure still returns the
  rule summary) + compact chain. Used in the Options Watchlist row expand and the
  Monitor's alert/technical expansions — **Options only**. It used to sit in Zonas
  Clave's detail panel too; dropped so options content stays on its own page.

Each page shows only the facet relevant to its layer, so seeing every facet of one
ticker means visiting Cartera / Options / Zonas Clave individually. That's the
intent, not a gap.

**All three signal pages read `?ticker=`**, so cross-section links land focused:
`/options` expands that watchlist row, `/zonas-clave` selects the ticker, and
`/geo-intel` selects the newest signal affecting it. An unmatched ticker is a
silent no-op everywhere (URLs go stale, and a thrown error would be worse).

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
4. If `FINVIEW_OPENROUTER_API_KEY` set and alerts exist → AI analysis (7-section Markdown)
5. notify_alerts() → single entry point for all channels (ntfy + Telegram + email)

### Scheduling — prod runs on external cron, NOT APScheduler
Same rule as Geo-Intel: `options_scheduler.py` (APScheduler, the "Agente" tab's start/stop)
only survives while the instance is alive and dies on scale-to-zero with `--min-instances=0`.
**Prod periodicity = Cloud Scheduler → `POST /api/options/agent/cron`**, authenticated by header
`X-Cron-Key == FINVIEW_CRON_SECRET` (constant-time compare; empty secret disables the endpoint).
Runs one cycle per user synchronously — don't convert it to fire-and-forget threads, the instance
can be reclaimed after the response.
- Unlike geo's cron, this one honours the `_cycles_in_progress` guard it shares with the manual
  `POST /agent/run`: a cron tick landing on a manual run would otherwise double-fetch every chain
  and write duplicate snapshots. Skipped users are reported as `skipped` in the response.
- `run_cycle()` swallows its own errors and returns `{"status": "error"}` — it never raises and
  never returns None, so `cycles_ok` keys off the status. Geo's `is not None` idiom would count
  failures as successes here.
- **Without this cron the Monitor tab reads empty**: `/options/alerts` only returns the last 7
  days, so with no cycles running the UI has nothing to show.
- All three pipelines now have a cron entry (geo, options, zonas-clave). If you add a fourth
  scheduled thing, it needs one too — APScheduler alone is a dev convenience, never the prod
  mechanism.

### Claude analysis prompt
Agent persona: *VolatilityEdge* (quant analyst, senior). Spanish only. Structured as exactly 7 sections:
`## 1. Resumen Ejecutivo` / `## 2. Smart Money` / `## 3. Señales Greeks` / `## 4. Top Picks` / `## 5. Catalizadores` / `## 6. Contexto MEFF` (only if .MC tickers present) / `## 7. Gestión de Riesgo`
Model: `settings.openrouter_model` via OpenRouter · max_tokens: 1500 · max 750 words in output.
Result stored in `OptionsAgentLog.result_json` as `claude_analysis` key.

### Premium spike detector
Tracks (ticker, option_type, strike) EMA baseline per user in memory (resets on server restart).
Fires `PREMIUM_SPIKE` severity=HIGH when `current_premium ≥ 2.5 × EMA` and `current_premium ≥ $0.10` and `samples ≥ 3`. EMA α = 0.3.
- **Baseline per contract, alert per ticker.** A broad move spikes every strike at
  once — IWDA.AS produced 17 alerts (K=136…148) for one event. `detect_spikes`
  collapses a ticker's hits into ONE alert via `_aggregate_ticker_spikes`, keeping
  the direction in the message ("6 calls + 11 puts, +151% a +195%"). The learning
  stays per contract; only the output is aggregated. Don't un-aggregate it.
- The aggregate carries **no `_strike`/`_option_type`** on purpose: that makes
  `notification_service._alert_key` collapse to `(ticker, PREMIUM_SPIKE)`, so dedup
  is one push per ticker per window instead of one per strike.
- **Reset caveat**: the baseline is empty after every deploy, so the first cycle or two
  post-deploy fire spikes off a cold baseline — noise, not signal. Discount them.
- **The effective bar is higher than `SPIKE_MULTIPLIER`**: the EMA absorbs the current
  premium *before* the spike check, so an isolated spike needs ≈7× the prior baseline,
  not 2.5×. Pre-existing; worth revisiting if real spikes seem to be missed.

### Notifications — HIGH only, deduplicated across cycles
`notify_alerts()` is the **single entry point** for every channel (ntfy + Telegram +
email). Two gates, both load-bearing:
- **Only `severity == "HIGH"` notifies.** MEDIUM/LOW still persist and show in the
  Monitor tab — they're for browsing, not pushing. Without this, email carried ~100
  MEDIUM/LOW rows across 70 tickers every cycle.
- **Cross-cycle dedup** (`filter_new_alerts`): an alert that stays true every 15-min
  cycle is pushed once per 6h TTL, not every cycle. In-memory, keyed on
  ticker+type (+contract for spikes), never on the message (its numbers drift).
  Resets on deploy like the spike baseline — re-notifies once, accepted.
- The old split `notify_spike_telegram()` is **gone**: it double-sent spikes on
  Telegram and had no dedup. Spikes now flow through `notify_alerts` with their own
  Telegram label.
- `send_telegram` retries once as plain text on a 400 (legacy Markdown rejects a whole
  message over one stray char), and logs Telegram's `description` — a bare 400 hid a
  wrong `chat_id` for a while.

### Backtest engine
- `record_signal()`: stores every HIGH/MEDIUM alert as a `BacktestSignal` with direction (BULLISH/BEARISH derived from alert type)
- `evaluate_pending()`: fetches current price via yfinance, fills `price_at_1d/3d/7d`, marks CORRECT/NEUTRAL/INCORRECT per horizon (threshold ±0.5%)
- UI shows accuracy % per horizon and per signal type in the Backtest tab
- **Enum-comparison gotcha:** SQLAlchemy returns `outcome_*` as the `BacktestOutcome`
  *member* on read, so `outcome == BacktestOutcome.CORRECT.value` is always False.
  `get_stats` normalizes via `_outcome_value()` before comparing — do the same anywhere
  you compare a stored outcome, or accuracy silently reads 0%.
- **Regime alignment (Phase 2b):** each signal freezes the macro `regime` at record time
  and stores `regime_alignment` (aligned/counter/neutral). `get_stats` adds a `by_alignment`
  breakdown (aligned-vs-counter accuracy at 7d). Instrumentation only — see the FRED section.
- **Evaluator window (load-bearing):** `evaluate_pending` fetches `history(start=oldest-pending)`,
  NOT a fixed window — a `10d` window only reached signals recorded 7-17 days ago, so any that
  missed that sweet spot (weekend, skipped cron) never got a 7d outcome and piled up unbounded.
  Scan is bounded by `_MAX_EVAL_AGE_DAYS` (45); a `[backtest-eval] pending/tickers/priced/updated`
  log line per run makes a zero-throughput regression visible.
- **Cross-cycle dedup (both sources):** a persistent condition fires the same alert every cycle.
  Options: `record_signal` skips a repeat within `_DEDUP_WINDOW_HOURS` (20h) on
  (user, ticker, signal_type, direction). Technical: `technical_signals._already_open` does the
  same per (ticker, level). Without it, one lingering setup stacks ~30-96 duplicate rows/day and
  **biases `by_alignment`** (same direction+regime repeated). Never remove either dedup.
- **Calibration digest** — `get_calibration(user, days)` + `GET /options/backtest/calibration`
  + the Backtest-tab `CalibrationPanel`: aligned-vs-counter edge per signal type, **dedup health**
  (rows/ticker-day; ~1 healthy, high = a dedup regression), and evaluator freshness. This is the
  feedback loop — read it instead of hand-querying Neon; the two bugs above survived weeks because
  nobody was reading the data.

### Frontend — /options (5 tabs)
- **Watchlist** (default tab): the one list — Cartera and Watchlist were separate
  tabs until they merged, since portfolio positions auto-sync into the watchlist
  anyway and the split showed the same tickers twice.
  - **The watchlist is the spine**, positions enrich it: one row per watchlist
    ticker, with the held lots (possibly several brokers) attached. Row building
    lives in `lib/optionsWatchlistRows.ts` (`buildWatchlistRows`) — pure and unit
    tested. **Group by ticker, never by lot**: the old Cartera keyed rows on
    `(isin, broker)` and rendered one ticker twice when held at two brokers.
  - Each row shows Sentimiento, P/C Ratio and an IV/HV badge ("IV cara" >+5 /
    "IV barata" <-5 / "IV normal") from the already-loaded snapshot — no per-row
    fetch. A "Cartera" badge marks held tickers.
  - Clicking/tapping a row expands `OpcionesTab` inline (same on both
    breakpoints): AI report on demand, underlying `PriceChart` (spot + near-money
    strikes), and the expiry navigator (‹ YYYY-MM-DD › n/total) — expanding
    fetches dates only (`GET /options/expirations/{ticker}`), navigating to a date
    lazy-loads that expiry's chain (`GET /options/chain/{ticker}?expiration=`),
    cached client-side. **Keep row actions out of the expansion** — expanding
    costs those fetches, and removing a row shouldn't.
  - **Removal is asymmetric on purpose**: held tickers get "Ocultar" (persists the
    exclusion via `/portfolio/hidden`) because a plain delete is undone by the
    auto-sync on the next load; only non-held tickers get a straight "Eliminar".
  - Ordering is held-first then alphabetical, deliberately independent of
    sentiment/alerts so a cycle landing mid-session can't reshuffle rows.
  - Stats bar shows aggregated P/C ratio → Alcista/Neutral/Bajista with color.
- **Monitor**: the alert hub. Three views behind one filter row — **Alertas**
  (options cycle alerts), **Smart Money** (unusual activity), **Técnico**
  (zone-break signals from Zonas Clave, the trigger layer). `macro ✓/✗` alignment
  tag per alert (Phase 2b, informational).
  - The Técnico view shows **every scored candidate, not just the alerting ones**:
    >70 is rare, so an alerted-only view would usually read empty (the exact
    problem the cron fixed), and showing near-misses beside their scores makes the
    threshold legible instead of magic. Alerting first, then by score; unscored
    (`break_probability = null`) sorts last and renders as "sin puntuar" — never
    as 0%, which would read as "certainly won't break".
  - The view carries a standing caveat that the probability is model-estimated and
    uncalibrated. Keep it until the backtest says otherwise.
  - Each alert carries **jump-off chips**: `Opciones` (expands `OpcionesTab` inline,
    same page), `Técnico` (→ `/zonas-clave?ticker=`), and `Ideas`
    (→ `/geo-intel?ticker=`) — the last one **only when that ticker has an active
    geo signal**, since a link to an empty page is worse than no link. The options
    page fetches `/geo/signals?status=active` best-effort just to know which
    tickers qualify: navigation metadata, no thesis content crosses over.
  - Smart Money rows deliberately have no chips — they're per-contract
    (ticker+strike+expiry), so several rows share a ticker and chips would be noise.
  - **This tab reads empty without the Cloud Scheduler cron** (see Scheduling above).
- **Backtest**: `CalibrationPanel` on top (dedup-health badge + aligned-vs-counter "Ventaja" per type + freshness); accuracy table +1d/+3d/+7d per signal type; per-ticker breakdown; "Precisión por régimen macro" aligned-vs-counter table (Phase 2b)
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
Self-contained page (QuickNav, like every section since the sidebar removal in PR #124).
Top search bar (debounced 300ms → `/search` → results dropdown → click pre-fills the form) +
summary stat cards + allocation bars + positions table + inline add/edit form (native selects).

### Deferred (original OptionsAI roadmap)
Structured-products barrier/knock-in alerts, private-bank PDF import, AI reporting,
capital-call/distribution movement sub-table. Search: CNMV ECR (PE/VC) + SICAV/RE/hedge registries,
listed SOCIMIs via Yahoo.

---

## Geo-Intel — architecture

WorldHawk port: geopolitical/natural events → market signals. 94 rules / 49 regions
(`services/geo/rules.py`), 8 ingest sources (seismic, EONET events, FIRMS fires,
maritime AIS, meteo, flights, GDELT, ACLED) — every source key optional, a missing
key degrades that source to empty.

### Adding regions / rules — overlap is the thing to reason about
`match_regions` returns **every** box containing the point and `match_rules` gates on
`region=X in regions`, so boxes are additive: a new box can only add matches to rules
that **share its category**. Vetting a new region is therefore a category question, not
a geometry one — check which categories the boxes you overlap already carry.
- The **commodity-basin boxes** (`west_africa_cocoa`, `australia_pilbara`,
  `lithium_triangle`) are narrow single-commodity chokepoints deliberately carved inside
  broader boxes. `lithium_triangle` ∩ `chile_mining` share `earthquake` **on purpose**:
  one Atacama quake carries both the copper and the lithium thesis. That dual match is
  asserted in `backend/tests/test_geo_commodity_rules.py`, so de-overlapping has to be a
  deliberate change, not an accident.
- **Keep new rules on keyless sources** unless you're also adding the key: EONET+GDACS
  (cyclone/volcano/flood/storm/drought) and USGS (earthquake) need nothing. The
  `extreme_heat/extreme_cold/severe_storm/heavy_precipitation/deep_cyclone` types come
  from **Windy** and silently never fire without `FINVIEW_WINDY_API_KEY` — a rule written
  against them looks fine in review and is dead in prod. (A Brazil frost rule is deferred
  for exactly this reason.)
- **Weather rules also need a sample point, and the threshold has to be reachable there.**
  Windy is a point source, not a feed: `meteo.py` only sees the coordinates it polls, so a
  weather rule whose region is never sampled is dead no matter the weather. This killed 5
  of 10 rules for the source's entire life (PR #178) — the old fixed 6×6 grid was unrelated
  to the rule regions. **The sample set is now derived from the rules themselves**, so a new
  weather rule gets its point automatically; `backend/tests/test_geo_meteo_sampling.py`
  asserts that invariant. What is still manual is *where* in the box: the sentinel thresholds
  are severe (45°C / -30°C / 50mm per 3h), and a centroid on water or in a mild sub-climate
  keeps the rule just as dead. Override it in `meteo._REGION_POINTS` (as `mediterranean` does
  — its centroid is the Tyrrhenian Sea) and mind the ~500 calls/day Windy budget: the source
  really fetches ~48×/day, so each point costs ~48 calls.
- Sentinel gates decide what ever reaches the matcher: earthquakes need `magnitude>=5.5`
  **and** to land inside some region; natural events need a region **or** `severity=red`.
  A rule whose threshold sits below the sentinel's floor is unreachable.
- Adding is fully additive — no schema change; `seed_rule_stats` picks up new `rule_id`s
  on next boot. `base_confidence` is **not cosmetic**: it feeds
  `effective_confidence → importance = round(confidence × risk/10)`, and ≥60 is the
  notify gate. It decides what pushes to a phone.

### Pipeline (`services/geo/orchestrator.py`, per user)
`ingest → sentinel (event extraction) → analyst (rule matching, LLM enrichment for
importance ≥ 60) → compound rules (energy/food/conflict buckets, ≥2 simultaneous) →
advisor (score + dedup + persist GeoSignal) → notify → auditor.evaluate_pending`.
- **LLM token gating**: the OpenRouter call fires only on first sighting — skipped when
  the user already has an ACTIVE signal for the event, and results are cached in-memory
  per event id (6h TTL) so N users cost one call. Long-lived feed events cost ~1 call total.
- **Dedup**: per-user by (source, external_id) on ACTIVE signals. Existing signals get
  confidence/importance refreshed; they only re-notify when confidence shifts ≥ 15.
- **Notify gate**: importance = round(confidence × risk/10) ≥ 60 → ntfy + Telegram + email
  via `geo/notify.py` (Telegram text is Markdown-escaped — external headlines contain
  `*_[` and would 400 the Bot API otherwise; keep the escaping).
- **Auditor**: 5 checkpoints per signal (1h/6h/1d/3d/7d), basket scoring; the +7d
  checkpoint resolves the signal and feeds confidence_mod back into geo_rule_stats.

### Scheduling — prod runs on external cron, NOT APScheduler
The in-process APScheduler (`/geo/scheduler/start`, UI "Monitor" button) only survives
while the instance is alive — with `--min-instances=0` it dies on scale-to-zero.
**Prod periodicity = Cloud Scheduler → `POST /api/geo/cron` every 10 min**, authenticated
by header `X-Cron-Key == FINVIEW_CRON_SECRET` (constant-time compare; empty secret
disables the endpoint). The endpoint runs one cycle per user synchronously so Cloud Run
keeps CPU until it finishes. Don't convert it to fire-and-forget threads — the instance
can be reclaimed after the response.

### Frontend — /geo-intel (labelled "Ideas")
**The thesis desk**, not an event feed: geopolitics is what seeds it today, but
the page's job is the investment/speculation case. Route, table and API prefix
keep the `geo` name — only the user-facing label changed (renaming the route
breaks deep links; renaming tables is DDL in prod without Alembic).

Map (react-simple-maps) + signal feed + detail panel. Header: "Run cycle" (manual,
polls until signals land), "Monitor" toggle (in-process scheduler — dev convenience,
not the prod mechanism), Active/Tracked/Regions/Last-signal stats. Signals silently
re-fetch every 60s. Reads `?ticker=` to select the newest signal affecting it.

In the detail panel (`components/geo-intel/SignalPanel.tsx`): stats
(importance/confidence/risk/direction), **"Why this was triggered"** (the matched
rules with their thesis and confidence), affected tickers with per-ticker
direction, and the 5 backtest checkpoints (1h/6h/1d/3d/7d). Tapping a ticker chip
expands `PrecioTab` + `FundamentalsCard` inline, with **"Añadir a Zonas Clave"**
(one click to the technical desk — the panel re-renders on every poll, so the
button owns its own state rather than taking props) and links out to
`/zonas-clave?ticker=` and `/options?ticker=`.

**No options content here** — links are navigation, not content.

### Fundamentals — `GET /charts/fundamentals?ticker=`
yfinance `.info`, cached 6h (fundamentals move on earnings, not intraday).
**Colour for a thesis a human reads — never an input to a signal, score or gate**,
and the UI says so. `.info` is scraped with no stable contract and returns a
mostly-empty dict for plenty of valid tickers, so every field is optional, an
empty result means "nothing to show" (not "bad ticker"), and the card hides itself
rather than rendering a grid of dashes. An all-empty result is not cached — that's
a miss, not a result.

### Env keys (Cloud Run)
Sources: `FINVIEW_FIRMS_MAP_KEY`, `FINVIEW_WINDY_API_KEY`, `FINVIEW_AISSTREAM_KEY`,
`FINVIEW_ACLED_EMAIL/KEY`, `FINVIEW_OPENSKY_USERNAME/PASSWORD` (all optional).
Notifications: `FINVIEW_NTFY_TOPIC`, `FINVIEW_TELEGRAM_BOT_TOKEN/CHAT_ID`,
`FINVIEW_NOTIFY_EMAIL_FROM/TO/PASSWORD` — unset = channel silently no-ops.
Cron: `FINVIEW_CRON_SECRET` (must match the Cloud Scheduler job header). One secret, shared by
all three cron entries — `/api/geo/cron`, `/api/options/agent/cron` and
`/api/zonas-clave/cron`. Rotating it means updating Cloud Run **first**, then every job:
miss one and it 403s silently.

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

## FRED service — risk-free rate + macro regime

`services/fred_rates.py` + `services/macro_context.py` — St. Louis Fed (FRED) data,
hand-rolled httpx (not the `fredapi` dep, to match the ECB service). Both sync in the
same startup background thread (`fred-rate-sync` in app.py). **No-op without
`FINVIEW_FRED_API_KEY`** (free key) — degrades to constants/omission like Turnstile/aisstream.
The key belongs on **Cloud Run (backend)**, not Vercel — the frontend never touches FRED.

### Shared cache (`fred_rates` table)
- One row per (series_id, rate_date); `rate` column holds the stored value. New table,
  auto-creates via `create_all`. `_fetch_observations(series_id, start, scale)` multiplies the
  raw FRED value: rates use `scale=0.01` (percent → decimal), macro indices `scale=1.0` (raw).
- `latest_value(series_id, on)` is DB-only with a ±14-day look-back window (shared reader).

### Risk-free rate (Phase 1)
- Fixes Black-Scholes Greeks: previously a single hardcoded `0.053` US rate priced **every**
  option (EUR `.MC`/Eurex underlyings were mispriced — error concentrates in rho/theta, grows
  with expiry). Now resolved **per option currency**: USD=`DGS3MO`, EUR=`ECBESTRVOLWGTTRMDMNRT`
  (€STR). `currency_for_ticker()` maps euro suffixes (`.MC`,`.DE`,`.PA`,`.AS`,`.MI`,`.BR`,
  `.VI`,`.HE`,`.LS`) → EUR; everything else → USD (GBP/CHF series = Phase-2 follow-up).
- **Fallback policy (A):** `risk_free_rate()` returns a per-currency constant when FRED is
  stale/unconfigured; USD keeps `0.053` so behaviour is unchanged without a key.
- Wired at `options_agent.py` (the only Greeks call site): resolves `r` per ticker, passes it
  into `enrich_options_with_greeks(data, r=...)`. `greeks_calculator.py` stays pure math.

### Macro regime (Phase 2a — annotation only)
- `macro_context()` reads VIX (`VIXCLS`), 10y-2y curve (`T10Y2Y`), financial stress
  (`STLFSI4`), HY spread (`BAMLH0A0HYM2`) → coarse `risk_on/neutral/risk_off` via transparent
  vote-scoring (tunable thresholds in `macro_context.py`). **Stateless / read-time** — computed
  in `GET /options/agent/last-analysis`, no per-cycle persistence, no schema change.
- Surfaced in the VolatilityEdge Claude prompt (`macro_prompt_block()`, "contextualize, don't
  change signals") and the Análisis-tab `MacroBadge`. **Does NOT touch scoring/gating.**
### Macro regime (Phase 2b — alignment instrumentation, DONE)
- Freezes the regime once per agent cycle and tags each signal/alert with directional
  **alignment**: `risk_on+BULLISH` or `risk_off+BEARISH` → `aligned`; the crosses → `counter`;
  neutral regime → `neutral`. `alignment_for()` / `alignment_for_alert()` in `backtest_service.py`.
- Persisted: `BacktestSignal.regime` + `.regime_alignment`, `OptionsAlert.regime_alignment`
  (additive columns in `database._ADDITIVE_COLUMNS`). `get_stats` → `by_alignment` breakdown.
- Surfaced: VolatilityEdge prompt (per-alert tag), `AlignmentTag` on alerts, and the
  "Precisión por régimen macro" table in the Backtest tab.
- **Instrument + surface only — does NOT change severity, gating, or notifications.** Every
  signal is still recorded, just labeled, so aligned-vs-counter stays unbiased.
- **Phase 2c (deferred):** let regime alignment actually modulate severity/notifications —
  only after the calibration digest's aligned-vs-counter edge holds up over a week+ of clean,
  evaluated data. Read it from the Backtest-tab `CalibrationPanel` (dedup badge must be green
  first — a red badge means the window still includes pre-dedup firehose data). Higher stakes
  now that notifications are HIGH-only: prefer promoting aligned over muting counter.

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
- FIFO v2 consumes the complete historical ledger through the target year, rejects
  future buys and incomplete inventory, and publishes only versioned results. Never
  apply legacy `calculation_version=NULL` rows to fiscal totals.
- Importer changes: each importer is isolated — changes in one must not break others.
  Always run pytest backend/tests/ after importer changes.
- Portfolio snapshots are authoritative only when
  `ImportRecord.portfolio_snapshot_complete=true`. Empty complete snapshots close old
  positions; partial ING/BBVA document sets must leave the marker false. Apply all
  later transactions after reconciliation and propagate unknown cost instead of zero.
- Portfolio totals are fail-closed: one unknown cost invalidates invested/P&L and one
  missing price invalidates total market value/P&L. Never publish a partial subtotal as
  the whole portfolio.
- Portfolio price resolution is one ticker to many ISINs. Corporate-action ISINs that
  share a Yahoo ticker must all receive the fetched price and cache row.
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
  Always guard: `if settings.openrouter_api_key and all_alerts`.
- Blog/MDX: in `.mdx` prose always escape `<` as `&lt;` — MDX parses `<1` (e.g. "FCF <1,2x")
  as a JSX tag start and breaks the whole Vercel build (see PR #101 → #105).
  Quick check: `grep -rn '<[0-9]' frontend/src/app/blog/*/page.mdx` must return nothing.
- Merge gate: before merging ANY PR that touches `frontend/**`, run `gh pr checks <n>` and
  require the Vercel preview check green. Never merge on a red or pending preview — there
  are no GitHub Actions and no branch protection here; the merge step is the only gate.

---

## IRPF fiscal model (context for AI)

- Modelo 100: casillas 27/29 (rendimientos), 328/380 o 332/337 según el ejercicio (ganancias/pérdidas), 588 (doble imposición) y 597 (retenciones españolas)
- Modelo 714: casillas 05-09 (patrimonio exterior)
- FIFO is chronological and cross-broker — historical sells consume earlier inventory;
  a buy in IBKR can match a later sell in DEGIRO, never an earlier one
- FIFO adjustments are versioned and split by box. `amount_eur` already contains the
  v2 delta; frontend consumers must never add `fifo_adjustment_eur` a second time.
- Withholding has three distinct truths: cash withheld, Spanish payment on account and
  foreign withholding. Never deduct total cash or infer a CDI credit from country;
  casilla 588 requires an explicit credit and is capped by quota/effective tax rate.
- finview_casillas_2024.json in repo root = reference output for fiscal year 2024

---

## Deploy

- Frontend: push to main → Vercel auto-deploys. No action needed.
- Backend: push to main touching backend/**, Dockerfile, pyproject.toml, or cloudbuild.yaml
  → Cloud Build triggers → deploys to Cloud Run europe-west1.
- Never touch cloudbuild.yaml without knowing what you are doing — it controls prod deploys.
- Backend deps are pinned: the Dockerfile installs from requirements.txt (hash-locked,
  exported from uv.lock). After ANY pyproject.toml dependency change run
  `uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.txt` and commit
  both files — `backend/tests/test_requirements_sync.py` fails the suite if you forget.
- Cloud Run runtime flags in cloudbuild.yaml are load-bearing: `--no-cpu-throttling` +
  `--cpu-boost` + `--memory=1Gi` (+ `--min-instances=0`). Without `--no-cpu-throttling`,
  CPU is throttled outside requests and the startup background loaders (Eurex RDF ~63s,
  ECB FX-sync, CNMV catalog) never finish — European options stop loading. Do not remove these.
  `--min-instances=0` scales to zero (cost ~0) but cold starts re-pay the ~63s Eurex preload;
  bump to 1 (~€45/mo always-on) only if always-instant European data is worth it.
- Full deploy docs: docs/deployment.md

---

## Tests

Backend: `pytest` — 464 collected (all under `backend/tests/`). ~131 skip when the real
broker files in `files/` are absent (not in repo — worktrees/CI skip them; the main
machine runs them).

Frontend: `cd frontend && pnpm test` (vitest) — 18 tests over the pure logic in `src/lib/`
(`optionsWatchlistSync`, `optionsWatchlistRows`). **`vitest` must be installed** or
`pnpm build` fails on `vitest.config.ts` even though the app itself compiles — run
`pnpm install` in a fresh worktree before wondering why the build is red.

If a test breaks, fix it before committing — no exceptions.

**Anything that talks to an external service gets tests for the ugly paths, not just the
happy one.** `zone_scorer.py` shipped with zero and spent its first prod cycle failing on
every call: the LLM returned 200 with `content: null` and `json.loads(None)` raised. A 200
means the server answered — nothing more. Validate the envelope before parsing.
