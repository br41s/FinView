---
paths:
  - "backend/services/geo/**"
  - "backend/api/geo.py"
  - "frontend/src/app/geo-intel/**"
  - "frontend/src/components/geo-intel/**"
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
