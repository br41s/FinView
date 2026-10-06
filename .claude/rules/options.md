---
paths:
  - "backend/services/options*"
  - "backend/services/premium_spike.py"
  - "backend/services/backtest_service.py"
  - "backend/services/greeks_calculator.py"
  - "backend/services/fred_rates.py"
  - "backend/services/macro_context.py"
  - "backend/api/options.py"
  - "frontend/src/app/options/**"
  - "frontend/src/lib/optionsWatchlist*"
---

## Options monitor — architecture

### Data sources
- **Yahoo Finance**: global options chains; all available expirations exposed via `fetch_expirations()` (instant metadata call). Agent cycle uses first 3 expirations; UI fetches per-expiry on demand.
- **MEFF**: direct HTML scraping from meff.es, 30 verified `.MC` tickers (Ibex-35 blue chips + extended). HV computed via yfinance 60d history since MEFF doesn't publish it.
- **Eurex**: daily RDF file; covers .DE, .PA, .AS, .L, .MI, .SW, .ZU, .BR, .VI, .OL, .ST, .CO, .HE, .LS, .PR suffixes. Cached once per trading day.
- Options chain cached 5 min (TTL) per ticker to avoid redundant scrapes. Per-expiry chains have their own cache keyed by `TICKER:YYYY-MM-DD`.
- **A watchlist row can hold an ISIN, and the sources are only ever asked about tickers.**
  A portfolio position nothing knows a ticker for is sent by its ISIN (`p.ticker || p.isin`
  in the page), the availability check below admits every ISIN, and the auto-sync stores it
  as the row's ticker. `options_scraper._as_ticker` is the one place an identifier becomes
  a symbol, for `fetch_options`, `fetch_expirations` and `fetch_options_for_expiry` alike:
  an ISIN that resolves (curated map, then Yahoo search) is fetched as its ticker; one that
  does not has no chain, logs `ISIN <isin> did not resolve to a ticker` at INFO and
  reaches no source. It used to fall through to `yf.Ticker(<isin>)`: yfinance reads a 12-character
  ISIN-shaped string as an ISIN, looks it up itself and raises `ValueError: Invalid ISIN
  number` — three ERROR tracebacks per cycle (477 in the ten days to 2026-10-05) for a bond
  and two `ES06…` ISINs, Spain's prefix for subscription rights. **The gate is still
  open**: such a position keeps being synced, costs one Yahoo search per cycle and shows a
  row with no data until it is hidden ("Ocultar"). Closing it — an ISIN that resolves to
  nothing is `no_options` — reverses the rule below and needs the resolver to tell "Yahoo
  knows nothing" from "Yahoo did not answer", or a failed search hides a real position
  for the cache's 24 h. `_resolve_isin` reads `ticker_map.CURATED` but not the
  `ticker_map` table (it has no session): a manual correction reaches the options path
  through the position's ticker, not through a row stored by ISIN. Thirteen ISIN rows
  resolved through its Yahoo search in prod in the ten days to 2026-10-05 — once per cold
  instance, `_ISIN_CACHE` being in memory, and taking the search's first quote, which is
  not always the listing wanted (`ONK.HA` for Oneok; one ISIN alternated between two
  symbols).
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
  mechanism, and its start endpoints 409 when `request_scoped_runtime` is set.
- The shared-secret check is one route dependency (`dependencies=[CronKey]`), not a line in
  each handler. See `.claude/rules/auth-security.md`.

### Claude analysis prompt
Agent persona: *VolatilityEdge* (quant analyst, senior). Spanish only. Structured as exactly 7 sections:
`## 1. Resumen Ejecutivo` / `## 2. Smart Money` / `## 3. Señales Greeks` / `## 4. Tickers con más actividad` / `## 5. Catalizadores` / `## 6. Contexto MEFF` (only if .MC tickers present) / `## 7. Gestión de Riesgo`
Model: `settings.openrouter_model` via OpenRouter · max_tokens: 1500 · max 750 words in output.
Result stored in `OptionsAgentLog.result_json` as `claude_analysis` key.

- **All three options calls turn reasoning off** — cycle report, per-ticker report
  (`_run_ticker_claude_analysis`) and the chat (`POST /options/ask`) send
  `reasoning=NO_REASONING` (`llm_envelope`, `{"effort": "none"}`). `max_tokens` pays for the
  reasoning and the answer alike, and with reasoning on a third of the cycles that reached
  the model (48 of 144, 10 days to 2026-10-05) came back 200 with `content: null` and
  `finish_reason: "length"`: all 1500 tokens spent, billed, no report. The model has no
  lower effort and no reasoning budget (see the same bullet in `geo.md`), so the choice was
  off or a budget big enough for both. The budget lost: reasoning has no bound to size it
  by, the 1500 tokens already took 19 s at the median and up to 70 s (`chat()`'s 60 s
  timeout is httpx's per-read timeout, not a deadline for the call), so 3–4× that per
  cycle and per on-demand report, on a key whose monthly limit was hit on 2026-09-28. The
  price is that the report is written without a reasoning pass; the template's seven
  sections carry the plan. With reasoning off `max_tokens` is only the answer's ceiling.
- **Not verified against a live call** (no key outside Cloud Run). After a deploy, or after
  changing `FINVIEW_OPENROUTER_MODEL`, read the logs: `options agent: OpenRouter HTTP 4xx`
  means the model rejected the parameter (`reasoning.mandatory`), `options agent: 200 with
  empty content` with `reasoning_tokens` near 1500 means a provider ignored it. A report
  that stops before `## 7.` means 1500 is short for the answer: raise it, it no longer
  buys reasoning. A truncated report is not logged — any non-empty text is a success.

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
- **Cross-cycle dedup** (`filter_new_alerts`): an alert that stays true every 30-min
  cycle is pushed once per 6h TTL, not every cycle. Keyed on ticker+type (+contract
  for spikes), never on the message (its numbers drift). **Persisted per user in
  `options_alert_notifications`, never in memory**: prod scales to zero between cron
  ticks, so nearly every cycle starts on a cold instance (`Starting new instance` at
  each tick in the logs). The in-memory dict it used to be was always empty there, and
  every still-true HIGH alert was re-pushed each cycle until ntfy answered 429
  (2026-10-05). The row is written and committed *before* the channels send: a failed
  commit sends nothing and retries next cycle, rather than sending without a record.
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

## FRED service — risk-free rate + macro regime

`services/fred_rates.py` + `services/macro_context.py` — St. Louis Fed (FRED) data,
hand-rolled httpx (not the `fredapi` dep, to match the ECB service). Both sync from the
daily zonas cron in request-scoped production and a startup thread locally. **No-op without
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

### Not advice
- FinView shows data and does not advise. Every prompt whose output a user reads includes
  `NOT_ADVICE_RULE_ES` / `NOT_ADVICE_RULE_EN` from `services/llm_rules.py` (cycle report,
  per-ticker report, `/options/ask` chat, zone scorer, both geo analyst prompts);
  `test_llm_rules.py` fails if one drops it or if a template asks for picks or sizing again.
- A new prompt that produces user-visible text must import the rule. A new section heading
  must keep the `## N. Title` format — `AnalysisTab` and `OpcionesTab` split on it — and must
  not name a selection to invest in ("Top Picks" was renamed for that reason).
- In the UI, `AiDisclaimer` sits in the page footer **and** next to each LLM output read on
  its own (chat, cycle report, per-ticker report, a geo signal's detail). Hit rates and
  backtests carry `PastPerformanceNote`. Wording comes from `NOT_ADVICE` in
  `frontend/src/lib/legal.ts`.
