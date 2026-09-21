---
paths:
  - "backend/services/geo/**"
  - "backend/api/geo.py"
  - "frontend/src/app/geo-intel/**"
  - "frontend/src/components/geo-intel/**"
---

## Geo-Intel — architecture

WorldHawk port: geopolitical/natural events → market signals. 81 rules / 49 regions
(`services/geo/rules.py`), 7 ingest sources (seismic, EONET events, FIRMS fires,
maritime AIS, meteo, flights, GDELT) — every source key optional, a missing
key degrades that source to empty.

### Every rule states its reach and writes down its transmission
`FastRule.scope` (site/local/regional/global) and `chain` — (physical effect, the price or
flow it moves, why this instrument follows) — are **written, never inferred**; `chain`
renders as the thesis, `scope` bounds the basket against `INSTRUMENT_BREADTH` and the
mismatch costs confidence. A leg whose third clause cannot be written is dropped and a rule
with no surviving leg is deleted (eight were, 2026-09-21). `INSTRUMENT_TRADABILITY` tags
each symbol cash_eu / options_only / not_tradable with its UCITS or EU-listed alternate.

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
  keeps the rule just as dead. Override it in `meteo._REGION_POINTS` (as `us_northeast` does
  — its centroid, Albany, sees -30°C once a decade) and mind the ~500 calls/day Windy budget: the source
  really fetches ~48×/day, so each point costs ~48 calls.
- Sentinel gates decide what ever reaches the matcher: earthquakes need `magnitude>=5.5`
  **and** to land inside some region; natural events need a region **or** `severity=red`.
  A rule whose threshold sits below the sentinel's floor is unreachable.
- Adding is fully additive — no schema change; `seed_rule_stats` picks up new `rule_id`s
  on next boot. `base_confidence` is **not cosmetic**: it feeds
  `effective_confidence → importance = round(confidence × risk/10)`, and ≥60 is the
  notify gate. It decides what pushes to a phone.

### GDELT — the 15-minute export files, never the DOC API
The DOC API answers **429 to a single request from Google Cloud** (prod: up in 17% of
cycles) and carries no Goldstein, no mention counts, no coordinates — so the old ingest
fabricated a per-query Goldstein and a capital centroid, and the sentinel had to delete its
floors and ban "red". `data.gdeltproject.org/gdeltv2/` is static, 200 in <0.5 s, and gives
all three per event: `lastupdate.txt` + the 3 prior batches (**60 min**, bridges one missed
30-min cron; dedup by GlobalEventID). Floors are real again, calibrated on live batches —
mentions 4–6 by category, **sources 1** (NumSources was 1 in 1758/1790 rows, so the original
3–5 floor would drop the whole feed). Classification is CAMEO root code first, actor
keywords only as fallback; root 17 (coerce, mostly 173 arrest) is deliberately **not** armed
conflict, and the escalation cluster counts deduped stories, not rows.

### Pipeline (`services/geo/orchestrator.py`, per user)
`ingest → sentinel (event extraction) → analyst (rule matching, LLM enrichment for
importance ≥ 60) → compound rules (energy/food/conflict buckets, ≥2 simultaneous) →
advisor (score + dedup + persist GeoSignal) → notify → auditor.evaluate_pending`.
- **LLM token gating**: the OpenRouter call fires only on first sighting — skipped when
  the user already has an ACTIVE signal for the event, and results are cached in-memory
  per event id (6h TTL) so N users cost one call. Long-lived feed events cost ~1 call total.
- **Dedup**: per-user by (source, external_id) on ACTIVE signals — and the DB index says
  the same thing (`uq_geo_sig_active_dedup`, partial on `status='active'`). It used to be
  a plain UNIQUE over the whole table, which contradicted the pipeline: the auditor
  resolves at +7d while most feeds keep publishing the same id (EONET events stay open
  for months; `wx-*`, `ais-*`, `fire-cluster-*` and `*-escalation-*` ids are region-keyed
  and never rotate). The first recurrence raised IntegrityError inside `generate_signal`
  and killed the cycle **before the auditor ran** — no new signals and no resolutions
  again, ever, while `/geo/cron` answered 200. A resolved signal may now be tracked again
  as a new row; two ACTIVE rows for one event are still impossible. Each signal is
  persisted in its own SAVEPOINT, so one bad write costs one signal, not the cycle.
  Existing signals get confidence/importance refreshed; they only re-notify when
  confidence shifts ≥ 15.
- **Liveness**: every cycle writes a `GeoCycleRun` (ok/error, per-source ingest counts,
  new signals, persist failures; pruned to 7 days) and `/geo/scheduler/status` returns the
  latest as `last_run`. `last_signal_at` alone cannot tell a stopped pipeline from a quiet
  one — that ambiguity is what let Ideas sit dead for six weeks. Every source at zero is
  an ingest outage, never a calm day. The header of `/geo-intel` renders this
  (`lib/geoHealth.ts`), and `/geo/cron` answers **500** when no user's cycle completes so
  Cloud Scheduler records a failure instead of a green run.
- **Generative path (events no rule covers)**: after the compound tally, `prepare_cycle` gives
  a *salient* unmatched event (red severity, M≥7, or GDELT with a novelty spike or ≥15 mentions)
  one generative LLM call — at most 3 *real* calls per cron request (a cache hit is free),
  cached 6 h per event, "not actionable" cached too. News is tested first and needs a named
  region (a story in no box is never salient — nearly every conflict bucket is "red", so a
  severity-first test pointed the calls at wire noise). The model must pick from the tradable
  universe and no wider than the event's reach (`rules.region_reach`, the same invariant the
  rules are tested against); confidence is capped at 85 and risk at 8 (importance ≤ 68 — the
  title it reasons from is external text and must not be able to manufacture a 100). The
  result is a signal with **no matched rules** (it never teaches `geo_rule_stats`), stamped
  `raw_data.generated` with the LLM's confidence, thesis chain and narrative, rendered as
  "Tesis generada por IA · sin regla" with the chain; it is **pinned at first sighting** (a
  6-hour re-call would describe instruments the priced basket does not hold) and pages only
  when the model's own confidence is ≥ 75, on top of every other gate.
- **Macro regime (FRED)**: `prepare_cycle` reads `macro_context()` once per request (cached
  series, synced nightly by the zonas-clave job; no HTTP in the cycle). In a `risk_off` regime
  every conflict / chokepoint / sanctions rule gets +1 risk (`rules.regime_headroom`); compound
  is excluded (its risk is held at 6 so it never pages) and physical/agricultural events are
  unmoved. The headroom applies at **creation**: a tracked signal keeps its risk across regime
  flips (the LLM-risk-sticks rule), so the badge speaks of *new* events. The regime is stamped on each event's
  `raw_data.macroRegime`, returned by `/geo/scheduler/status` as `macro`, and shown as a badge
  in the Ideas header. Unavailable macro data means no headroom, never an error.
- **Novelty gate (GDELT only)**: a news bucket is one tracked signal per (category, region),
  re-tracked after every +7d resolution, so an ongoing war paged weekly. The sentinel stamps
  every GDELT event with `raw_data.novelty = {stories, baseline, novel}` — this hour's story
  count against the 7-day rolling median of `geo_region_samples` (one row per cycle for every
  escalation region, zero or not, and for any other named region only on cycles it has
  stories — so a non-escalation region's baseline is its median *active* hour and stricter;
  hydrated/persisted once per cron request like the flight baseline) — and the advisor pages a GDELT signal only when `novel` is True (≥ 3 stories and
  ≥ 2× the median). No baseline yet (first six hours after a cold table) is *not* novel.
  Physical events (quakes, cyclones, AIS drops) are new ids by nature and are not gated.
- **Notify gate**: importance = round(confidence × risk/10) ≥ 60 → ntfy + Telegram + email
  via `geo/notify.py` (Telegram text is Markdown-escaped — external headlines contain
  `*_[` and would 400 the Bot API otherwise; keep the escaping).
- **Auditor**: 5 checkpoints per signal (1h/6h/1d/3d/7d), basket scoring; the +7d
  checkpoint resolves the signal and feeds confidence_mod back into geo_rule_stats.
  **A ticker that didn't move is excluded from the basket, not counted against it**, and a
  checkpoint with nothing measurable is NEUTRAL and teaches the rules nothing. Since the
  2026-09-20 audit (prod had 23.9% accuracy ex-neutral and random baskets scored 61–68%
  "correct" — the auditor measured nothing) the scorer is:
  - **the bar at the checkpoint's own target time** (`prices.fetch_price_series`: 5-minute
    bars inside the 5-day window, the daily close otherwise), never "now" — the cron runs
    every 30 min, so "now" was a random 60–90 min window for +1h and every horizon due in
    one cycle received the same price;
  - **+1h/+6h in trading time** on the US session (`trading_time.py`, DST-aware, no holiday
    calendar); a Sunday-03:00 signal's +1h lands Monday 10:30 ET;
  - **a ticker is readable when it moved more than 0.75 of its own horizon sigma**, computed
    from the same series (floor 0.1%); ties are NEUTRAL;
  - **no price → pending**, retried next cycle for up to 7 days, then NEUTRAL "sin datos".
    Never stamp `evaluated_at` on a missing price: a Yahoo stall used to burn every due
    window forever.
  The portfolio path (`fetch_and_cache_prices`) stays on daily closes — one row per ISIN
  per day paired with that day's ECB rate. Don't switch it.

### Scheduling — prod runs on external cron, NOT APScheduler
The in-process APScheduler (`/geo/scheduler/start`, UI "Monitor" button) only survives
while the instance is alive — with `--min-instances=0` it dies on scale-to-zero.
**Prod periodicity = Cloud Scheduler → `POST /api/geo/cron` every 30 min**, authenticated
by header `X-Cron-Key == FINVIEW_CRON_SECRET` (constant-time compare; empty secret
disables the endpoint). The endpoint runs one cycle per user synchronously so Cloud Run
keeps CPU until it finishes. Don't convert it to fire-and-forget threads — the instance
can be reclaimed after the response.

**The rollout pauses `geo-intel-cycle` and must resume it.** `cloudbuild.yaml` pauses the
three Scheduler jobs before switching traffic; for a month nothing resumed them, so every
deploy silently ended production periodicity on a green build. The resume is an EXIT trap
(covers rollback and supersession) and the build fails if a job doesn't come back ENABLED
— `test_cloudbuild_policy.py` asserts the pause/resume pair over the same job list. A new
scheduled pipeline goes in that list, not just in a new job.

**Timestamps leave `api/geo.py` through `_as_utc`.** The DateTime columns are naive
(written from `datetime.now(timezone.utc)`), and `new Date("…T12:00:00")` is *local* in
every browser — so an unstamped field shifts every age the page renders by the viewer's
offset. That is not cosmetic here: the feed's "Nh ago", the staleness read and the
checkpoint clock are all derived from it. A new timestamp field goes through the helper.

### Frontend — /geo-intel (labelled "Ideas")
**The thesis desk**, not an event feed: geopolitics is what seeds it today, but
the page's job is the investment/speculation case. Route, table and API prefix
keep the `geo` name — only the user-facing label changed (renaming the route
breaks deep links; renaming tables is DDL in prod without Alembic).

Map (react-simple-maps) + signal feed + detail panel. Header: "Run cycle" (manual,
polls until signals land, and **reports what the cycle did** — "0 eventos" is how you
tell an ingest problem from a day the rules matched nothing; a failure is shown, never
swallowed), "Monitor" toggle (in-process scheduler — dev convenience, not the prod
mechanism), Active/Tracked/Regions/Last-signal stats, and a health line derived from
`last_run` (`lib/geoHealth.ts`, pure and unit-tested: never run / failed / stale / no
source returned anything / signals dropped / healthy). Signals silently re-fetch every
60s. Reads `?ticker=` to select the newest signal affecting it.

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
`FINVIEW_OPENSKY_CLIENT_ID/SECRET` (all optional).
OpenSky moved to **OAuth2 client credentials**: `flights.py` exchanges them for a bearer
token at `_TOKEN_URL` (cached until ~1 min before expiry) and falls back to the legacy
`FINVIEW_OPENSKY_USERNAME/PASSWORD` basic auth, then to anonymous. Anonymous is
rate-limited hard enough to read as "no flights". OpenSky is also **unreachable from
Google Cloud** (connect timeout from Cloud Run and Cloud Build alike, credentials fine
from outside), so flights come from **adsb.lol** first (keyless, one 250 nm point query
per region plus `/v2/mil`) and OpenSky is only the fallback. **Every ingest key is backend-only — Cloud Run, never Vercel.**
Notifications: `FINVIEW_NTFY_TOPIC`, `FINVIEW_TELEGRAM_BOT_TOKEN/CHAT_ID`,
`FINVIEW_NOTIFY_EMAIL_FROM/TO/PASSWORD` — unset = channel silently no-ops.
Cron: `FINVIEW_CRON_SECRET` (must match the Cloud Scheduler job header). One secret, shared by
all three cron entries — `/api/geo/cron`, `/api/options/agent/cron` and
`/api/zonas-clave/cron`. Rotating it means updating Cloud Run **first**, then every job:
miss one and it 403s silently.
