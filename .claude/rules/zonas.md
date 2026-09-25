---
paths:
  - "backend/services/zonas_clave*"
  - "backend/services/technical_signals.py"
  - "backend/services/zone_scorer.py"
  - "backend/api/zonas_clave.py"
  - "frontend/src/app/zonas-clave/**"
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
  → BacktestSignal (ZONE_BREAK, break_probability) ALL scored candidates
  → alerted=True                                  only > alert_threshold_for()
```

- **The gate is what bounds token spend.** `PROXIMITY_THRESHOLD = 0.02` (2%);
  its floor is `_CLUSTER_THRESHOLD` (1.5%) — closer than that and you're *inside*
  the zone, not near it. Most tickers most days produce zero candidates, so the
  LLM is never called.
- **Break direction comes from which side price is on, NOT from `zone_type`.**
  A level built from pivot highs is labelled "resistance" forever; once price
  trades above it, it acts as support and the pending move is a breakdown.
  Trusting the label inverts the direction on every flipped level.
- **The gate is calibrated from outcomes, default 70.** An LLM's "73%" is an
  opinion with a number attached, so *every* scored candidate gets a
  `BacktestSignal` row with its `break_probability`, `alerted` and the
  `alert_threshold` it was measured against — sub-threshold included, because
  ">70 vs <70" needs outcomes on both sides. `backtest_service.zone_calibration`
  reads the curve (`by_bucket`) and the hit rate a gate at each floor would have
  had (`cumulative_from`, for reading only). The gate (`alert_threshold_for`) moves
  from 70 **one band at a time on that band's own record**: down to 60 only if
  60-69 has ≥20 measured 7d outcomes and ≥55% hits (then to 50 on 50-59's record),
  up to 80 if 70-79 has ≥20 measured and fails the bar. Judging a floor by the
  cumulative population let a strong 80+ tail carry a 10%-accurate 50-59 band
  across the bar (auditor, PR #289). A thin band stops the walk; a calibration
  failure falls back to 70. The gate is computed once per cycle and passed into
  `emit_for_analysis`. The alert-accuracy views (`get_stats`, `get_calibration`,
  `GET /options/backtest`) go through `alerting_only`: sub-threshold ZONE_BREAK rows
  exist for calibration, not for the alert stats.
  `GET /zonas-clave/calibration` shows it; the page header prints the effective
  gate. `GET /zonas-clave/signals` returns everything by default; `alerted_only=true`
  is the Monitor's view.
- **Outcomes are evaluated by the zonas cycle itself** (`run_analysis_for_user`
  ends with `backtest_service.evaluate_pending`). The options agent also
  evaluates, but returns early for a user with no options watchlist, so a
  zonas-only user never got ZONE_BREAK outcomes — and without outcomes nothing
  calibrates.
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
