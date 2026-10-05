---
paths:
  - "backend/services/geo/**"
  - "backend/api/geo.py"
  - "frontend/src/app/geo-intel/**"
  - "frontend/src/components/geo-intel/**"
---

## Geo-Intel — architecture

WorldHawk port: geopolitical/natural events → market signals. 84 rules / 49 regions
(`services/geo/rules.py`), 6 country templates over 33 country markets
(`services/geo/countries.py`), 9 ingest sources (seismic, EONET + GDACS events, FIRMS
fires, maritime AIS, meteo, flights, GDELT, OFAC, Federal Register) — every source key
optional, a missing key degrades that source to empty.

### Every rule states its reach and writes down its transmission
`FastRule.scope` (site/local/regional/global) and `chain` — (physical effect, the price or
flow it moves, why this instrument follows) — are **written, never inferred**; `chain`
renders as the thesis, `scope` bounds the basket against `INSTRUMENT_BREADTH` and the
mismatch costs confidence. A leg whose third clause cannot be written is dropped and a rule
with no surviving leg is deleted (eight were, 2026-09-21). `INSTRUMENT_TRADABILITY` tags
each symbol cash_eu / options_only / not_tradable with its UCITS or EU-listed alternate.

### Country layer — where an event is, and what it may reach
The boxes were drawn for commodity and chokepoint theses, so until 2026-10-04 an event
that hurt one country and nobody else had nowhere to go: a quake outside every box was
dropped in the sentinel, and seven countries had an instrument of their own.

- **The country is the source's own word, never geometry.** GDELT's export carries
  `ActionGeo_CountryCode` in column 53 (**FIPS 10-4, not ISO**: `SP` is Spain, `CH` is
  China, `AS` is Australia), a USGS `place` ends in the country — including the offshore
  quakes a polygon misses — and GDACS lists the countries affected (ISO3). Only the last
  comma-part of a place is read (towns are named after countries) and a short trap list
  drops "New Mexico", "Gulf of Mexico", "Chile Rise" and the seas. A GDACS event is
  attributed **only when it names exactly one listed country**: which of three a typhoon
  hit hardest is not in the feed.
- **`GeoEvent.country` is not `raw_data["country"]`.** The second is the *target* of a
  policy action and is what the `country=` rule atom reads. Stamping a wire story there
  would make GDELT sanctions stories match the OFAC rules. Slugs are OFAC's vocabulary,
  but `ofac.COUNTRY_SLUGS` is not extended — `_country_of` takes the earliest name, so a
  new entry re-attributes SDN designations.
- **Template rules** (`rules.TEMPLATE_RULES`): one written chain per (event category,
  tier) — earthquake, cyclone, flood × national, local — rendered for the event's
  country by `resolve_rule`. National is the country ETF; local is up to two companies
  that earn only there (`countries.COUNTRY_LOCALS`), in the 13 countries that have one.
  All legs bearish. The id is **shared by every country** (`tpl-earthquake-national`),
  so `geo_rule_stats` pools its samples; a rule per country would never reach the ten
  resolutions the learned mod needs. National and local are separate ids so each tier
  keeps its own record. A template states only what holds for any country. What a quake
  does to one country's copper is a hand-written rule's claim.
- **Beside a hand-written rule a template adds legs and nothing else**
  (`rules.scoring_rules`). In the mean confidence or the max risk it would change the
  importance of events that have always been scored without it: an M7.2 under Tokyo is
  52 and silent today and would page at 60. Written legs come first and win a symbol
  collision. With no written rule the templates are all there is, and they score.
- **Local companies are US-listed on purpose.** The +1h and +6h checkpoints are measured
  on the US session; a Jakarta or Santiago listing would be read at a bar its exchange
  never traded. A company with a large book abroad is not a local leg (Japan's
  megabanks, Spain's banks, the global miners).
- **The floor is `rules.template_floor_met`** — PAGER yellow or worse for a quake (USGS'
  own damage estimate, `raw_data.pagerAlert`), GDACS orange or red otherwise.
  **Provisional: the owner has not confirmed it** (the function carries the TODO).
  Magnitude alone is not it: all seven M≥5.8 quakes of September 2026 were PAGER green,
  one of them M6.6 at 10 km. Set it too low and the shared template learns it is wrong
  for every country at once. The sentinel admits a no-box event through the same
  function, so there is one floor: a big quake that damaged nothing must not enter by
  the country door and reach the generative LLM, which treats M≥7 as salient.
- **PAGER arrives after the quake, so legs can arrive after the signal.** The cycle that
  first tracks a quake usually sees no rating: the written rule matches alone. When the
  rating comes, `advisor._adopt_template_legs` adds the template legs to the ACTIVE
  signal — priced then, measured from then — and records the template ids. Confidence,
  risk and paging are untouched, and the signal's `direction` is always the **stored**
  basket's, never the analysis'. No price for any new leg means no adoption that cycle.
- **A template displaces the generative path** for the event it reads: `_generative_pass`
  skips anything that already has legs. An M7+ in a box with no quake rule (the
  Philippines, Indonesia) used to get a generated thesis that could page at 68; it is
  now a template signal, 40 at most, until the template has a record. Deliberate — the
  template is deterministic and measurable, and that thesis was chosen from a universe
  with no instrument for the country — but it is one fewer page. Pinned in
  `test_geo_templates.py`.
- **A template cannot page until it has earned it.** Base confidence 0.50 × the highest
  risk it can reach (8, a PAGER-red quake) is 40 against a gate of 60. Cyclone and flood
  top out at risk 7 and 5 and never page.
- **The gate is `rules.allowed_symbols(event)`**: an instrument bound to a country
  (`countries.INSTRUMENT_COUNTRY`) is admitted for an event in that country, or in a
  region box a hand-written rule already ties it to (a Korean-peninsula event reaches EWY
  whichever side it is geocoded on). Unbound instruments are admitted everywhere. Both
  LLM paths answer to it — the enrichment used to append whatever the model named, the
  one way a symbol outside the universe entered a signal.
- **Only quakes and GDACS orange widen the sentinel.** GDELT stories outside a box are
  keyed by 1° cell (dozens of buckets an hour), EONET volcanoes stay open for months and
  FIRMS is agricultural burning: those are stamped with a country and still need a box.
- **Adding a country fund**: confirm 5-minute bars on Yahoo, set `route` from the open
  interest of the two nearest expiries (~1000 contracts is the line; EPHE and EIS list no
  options), add it to `EXPECTED_SYMBOLS`. ENZL was tried and left out — 69 bars in five
  sessions. A bound company must be domiciled *and* operating in the one country;
  Southern Copper (Peru and Mexico) is bound to nothing.
- **Tier is a property of the instrument** (`rules.instrument_tier`): local = a company
  bound to a country, national = a country fund, international = the rest. A Taiwan
  signal can carry China's fund as "national".
- **Prices are asked core-first** (`rules.fetch_order`): a stall spends the budget on
  whatever comes first, and alphabetical order put the country funds ahead of GLD, USO
  and XLE. A template signal whose one leg has no price is not created that cycle — it
  would sit unmeasurable for seven days holding the event's dedup row.

### The ladder — a basket read tier by tier (`services/geo/ladder.py`)
An event that hurts a country shows first in the companies that earn only there, then in
the country's market, and only sometimes in what the rest of the world prices. One score
for the whole basket could not say how far an event had travelled.

- **Each leg keeps its own reading** on `geo_signal_tickers`: `live_change_pct` and
  `live_state` are overwritten by every audit while the signal is active, `final_state`
  is written once at +7d. **NULL is "never read", not "flat"** — a leg with no price this
  run keeps the reading it had, like the signal's live rating.
- **`ladder.leg_state` is the only definition of "moved as predicted"** (confirms /
  contradicts / flat against the leg's own sigma). The auditor's `_score` calls it, so
  the basket score, the rules' learning and the ladder cannot disagree.
- **`ladder.tier_states`**: pending (no leg read) · confirmed (more legs with the thesis
  than against) · contradicted · unreadable (read, and decided nothing — no measurable
  move, or an even split). A tie is not a confirmation, the same rule that makes a
  1-for-2 basket NEUTRAL.
- **On the wire**: each ticker carries `state` (the +7d one once it exists) and
  `liveChangePct`; the signal carries `ladder`. "Pending" only exists while a signal is
  open: resolved, a tier never read is unreadable, and a signal resolved before legs kept
  a reading has no ladder at all. `/geo/accuracy` adds `tiers` (hit rate
  per tier at +7d) and `ladder` — for local→national and national→international, the
  wider tier's hit rate when the narrower one confirmed (`rate`, over `n` signals)
  against its hit rate overall (`baseline`).
- **Nothing here moves a confidence, on purpose.** "A confirmed local tier makes the
  national one more likely" is a hypothesis until `rate` beats `baseline` on real
  resolutions. The lift ships once ~30 laddered signals have resolved, derived from that
  gap the way `learned_confidence_mod` is derived from accuracy — never a hand-set step.
  `test_geo_ladder.py` fails if a lift appears in the module before then.
- **Copy**: a rung reads "a favor / en contra / sin lectura / pendiente" — where prices
  went against the written thesis, in the live rating's own words. Never a reason to act.

### GDACS — SEARCH with an activity window, never MAP
`geteventlist/MAP` answers **400 "Eventtype is required."** and nothing noticed: the
source counts EONET and GDACS together, and EONET carries no alert level, so no natural
event had a severity. `ingest/events.py` asks `SEARCH` for `TC;FL;VO;DR`, all three
levels (the default is orange and red only), over the last three days. The window is on
activity, so an event that already ended comes back too: it is dropped only on an
explicit `iscurrent=false`, never on a missing flag. `url` is an object there, not a
string. `TS` in GDACS is tsunami, not storm: it is neither requested nor mapped (it was
mapped to "storm", one request change away from firing the storm rules on a wave), so one
that ever arrives is "other" and the sentinel drops it. Asking for `TS` starts with a
written rule that reads a tsunami.

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
  fetches once per hourly cycle, ~24×/day, so each point costs ~24 calls.
- Sentinel gates decide what ever reaches the matcher: earthquakes need `magnitude>=5.5`
  **and** to land inside some region or a country with a market; natural events need a
  region, `severity=red`, or orange in a single country with a market.
  A rule whose threshold sits below the sentinel's floor is unreachable.
- Adding is fully additive — no schema change; `seed_rule_stats` picks up new `rule_id`s
  on next boot. `base_confidence` is **not cosmetic**: it feeds
  `effective_confidence → importance = round(confidence × risk/10)`, and ≥60 is the
  notify gate. It decides what pushes to a phone.

### FIRMS — a rolling 24 hours, never "today"
`DAY_RANGE` counts UTC calendar days: `world/1` is today's file, empty at 00:00 UTC until the
first passes land (~03:30). Prod read 0 hotspots for three hours every night with nothing to
log. `ingest/fires.py` asks for `world/2` (30 s timeout, ~10 MB) and keeps hotspots acquired
in the last 24 h by `acq_date` + `acq_time`; an unreadable time is kept and counted, never
dropped, so a format change cannot silently empty the feed.

### GDELT — the 15-minute export files, never the DOC API
The DOC API answers **429 to a single request from Google Cloud** (prod: up in 17% of
cycles) and carries no Goldstein, no mention counts, no coordinates — so the old ingest
fabricated a per-query Goldstein and a capital centroid, and the sentinel had to delete its
floors and ban "red". `data.gdeltproject.org/gdeltv2/` is static, 200 in <0.5 s, and gives
all three per event: `lastupdate.txt` + the 7 prior batches (**2 h**, bridges one missed or
late hourly cron — Scheduler has no retry and a deploy across :00 pauses the job; dedup by
GlobalEventID). **Every count is over the newest hour only** (4 batches by `DATEADDED`,
which is the batch stamp): the novelty sample, the cluster bar and `storiesThisHour`. The
counts are per window read, not per newly seen event, so counting the bridge would double
every sample against a baseline built on 60-minute windows and page the map as "novel" for
days; a bridged row still reaches the matcher and can be tracked, it just is not counted.
GDELT writes each batch ~9 min before its stamp, so an on-time :00 cycle reads :00 as newest. Floors are real again, calibrated on live batches —
mentions 4–6 by category, **sources 1** (NumSources was 1 in 1758/1790 rows, so the original
3–5 floor would drop the whole feed). Classification is CAMEO root code first, actor
keywords only as fallback; root 17 (coerce, mostly 173 arrest) is deliberately **not** armed
conflict, and the escalation cluster counts deduped stories, not rows. The article behind a
bucket is its representative row's, stored as `raw_data.sourceUrl`; `api/geo._source_url`
reads that key (`url` for the feeds with an event page of their own) and is tested through
the sentinel's own output — writer and reader disagreed on the key from 2026-09-20 and no
GDELT signal carried its link, with a passing test on each side.

### OFAC — official designations, because GDELT does not carry them
Measured 2026-09-21: five OFAC actions and three BIS orders in a week produced one GDELT
sanctions signal (actors "MUSLIM → ?"). A wire story only becomes a GDELT signal inside a
region box — Russia, Cuba, Venezuela, Belarus have none — and the wire never names the
designated entities, which is the tradable content. `ingest/ofac.py` reads
`ofac.treasury.gov/recent-actions` (no feed or API exists for the dated delta) and parses
the **canonical SDN entry format** from the page text — the same format as the Federal
Register notice and the SDN files, unchanged for decades: kind from `(individual)` /
`(vessel)`, programs from `[TAG]`s, country from `nationality X` else the first country in
the address. Window 3 days (a +7 d resolution must not re-track the same action), 5 pages
max, cached one cycle, page failures skip that page and a dead listing returns the stale
payload. `sentinel.analyze_ofac_actions` emits one `sanctions` event per (action, country)
with ≥1 **addition**, matched at the capital: Tehran and Beijing fall in the `iran` /
`china_industrial` boxes and hit the existing rules; Moscow and Caracas are in no box and
match through the new condition atom **`country=<slug>`** (`ofac-sanctions-russia`,
`ofac-sanctions-venezuela`, scope global). ≥8 additions is severity red (+1 risk through
`severity_headroom`). Removals and modifications are parsed, counted and start nothing —
a delisting is a different thesis. The generative path does not see OFAC events: with no
box their reach is "local" and the validator would reject every national instrument, so a
country without a rule is a rule to write, not an LLM call.

### Federal Register — USTR tariff actions and BIS Entity List additions
The trade theses had never fired once (0 `trade_dispute` signals in the table's history):
GDELT codes a tariff as a diplomatic story, never as a dated action. Measured 2026-09-22
over 90 days: USTR published 4 tariff actions and BIS 2 Entity List rules — one or two
events a month, each exactly what `gdelt-trade-dispute-china` and the semiconductor leg of
`gdelt-sanctions-china` were written for. `ingest/fedreg.py` queries the keyless JSON API
(`federalregister.gov/api/v1/documents.json`, both agencies, last 3 days, one request,
cached one cycle, stale payload on failure). **Classification is by title**: a BIS rule
with "Entity List" and "Addition(s)" is `sanctions` (removals and address revisions are
not); a USTR notice matching Section 301 / 232 / Notice of Action / Product Exclusions is
`trade_dispute` unless it is a request for comments, a hearing, a quota allocation, a
Notorious Markets review or an investigation *initiation*. Countries come from title +
abstract through the OFAC country table, one event per (document, country) at the capital
(`sentinel.analyze_fedreg_documents`, stamped at the Register's 08:45 Eastern release,
DST-aware — 12:45 UTC in summer, 13:45 in winter): China lands in `china_industrial` and hits the GDELT rules, Russia hits
`ofac-sanctions-russia` through `country=`, Brazil hits the new `fedreg-trade-brazil`
(EWZ−). Investigation initiations are deliberately not events: the market moves on the
duty, and an initiation ends in a hearing as often as in a tariff.

### One owner, every reader
Ideas is the same for every account: the feeds are public, the channels are global env
vars and the frontend keeps no per-user geo state, so N accounts used to mean N identical
copies of every row and N cycles. The pipeline runs **once, under a system user**
(`services/geo/owner.py`, `ideas-system@finview.internal`, inactive, no password) that owns
`geo_signals` / `geo_checkpoints` / `geo_cycle_runs`; every read, `/run`, `/scheduler/*`
and `/cron` resolve `geo_owner_id(db)` and `CurrentUser` is only the auth gate. It is a
`users` row because the three tables carry a NOT NULL FK and there is no Alembic. The boot
that creates it adopts the **oldest account's** history (one-shot, logged) so the first
shared cycle does not re-track and re-page every live event; other accounts' copies stay
unread. The options and zonas-clave crons skip inactive users so the owner never gets a
portfolio cycle.

### Pipeline (`services/geo/orchestrator.py`, one cycle for the owner)
`ingest → sentinel (event extraction) → analyst (rule matching, LLM enrichment for
importance ≥ 60) → compound rules (energy/food/conflict buckets, ≥2 simultaneous) →
advisor (score + dedup + persist GeoSignal) → notify → auditor.evaluate_pending`.
- **LLM token gating**: the OpenRouter call fires only on first sighting — skipped when
  the user already has an ACTIVE signal for the event, and results are cached in-memory
  per event id (6h TTL) so N users cost one call. Long-lived feed events cost ~1 call total.
- **Both LLM calls turn reasoning off** (`llm_envelope.NO_REASONING`, sent as
  `reasoning: {"effort": "none"}`). `max_tokens` pays for the reasoning and the answer
  alike, and with reasoning on prod lost 2–7 generative calls a day to a 200 with
  `content: null` and `finish_reason: "length"` (1799–2054 reasoning tokens of 2000; once,
  half a JSON) — each billed in full, debited from the 3-per-request cap and, because a
  failure is not cached, asked again the next cycle. There is nothing to cap on this model:
  OpenRouter's catalogue (`GET /api/v1/models`, the `reasoning` object) gives
  deepseek-v4-flash `supported_efforts: [xhigh, high]`, no reasoning budget and
  `mandatory: false`, and `reasoning.exclude` only hides tokens that are still spent. A
  larger budget moves the cliff: 2000 tokens already take 9–12 s of the 20 s timeout.
  **Changing `FINVIEW_OPENROUTER_MODEL` means reading that model's `reasoning` entry
  first** — one with `mandatory: true` rejects `effort: "none"` and both calls would fail
  (logged `OpenRouter HTTP 4xx`, never raised). The options agent's three calls share the
  model and the constant (`options.md`); the zone scorer shares the model and still
  reasons, on purpose (`zonas.md`).
- **Dedup**: per owner by (source, external_id) on ACTIVE signals — and the DB index says
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
  ≥ 2× the median). No baseline yet (first 12 samples — twelve hours of the hourly cron
  after a cold table) is *not* novel.
  Physical events (quakes, cyclones, AIS drops) are new ids by nature and are not gated.
- **Notify gate**: importance = round(confidence × risk/10) ≥ 60 → ntfy + Telegram + email
  via `geo/notify.py` (Telegram text is Markdown-escaped — external headlines contain
  `*_[` and would 400 the Bot API otherwise; keep the escaping).
- **Auditor**: 5 checkpoints per signal (1h/6h/1d/3d/7d), basket scoring; the +7d
  checkpoint resolves the signal and updates the matched rules' counters in
  geo_rule_stats. **Each rule learns from its own legs** (`_update_rule_stats`): the
  symbols it names, each against its own direction. One outcome for the whole basket
  used to teach every matched rule, so a mod followed whatever else was in the signal
  (GLD and USO drift, mostly). A rule whose own legs were unreadable learns nothing; a
  tied basket can still teach one rule right and another wrong; a leg the LLM added
  teaches no rule. A signal carrying none of a rule's current legs — written before the
  rule was last edited — is scored whole, as before. **It runs on its own job**, `POST /api/geo/audit` every 4 hours
  (`geo-intel-audit`), not inside the hourly cycle: `run_audit` = recompute
  confidence_mods → score due checkpoints → re-rate every ACTIVE signal.
  - **confidence_mod is derived from accuracy, never stepped**:
    `clamp((correct/total − 0.5) × 0.6 × min(1, total/10), ±0.30)`
    (`auditor.learned_confidence_mod`). A rule at 100% earns +0.30, at 0% loses 0.30,
    at 24% (prod before the audit) −0.156; the first outcomes weigh a tenth each so one
    lucky hit is not a promotion. `recompute_confidence_mods` re-derives every row from
    its counters at the start of each audit, so a formula change or a row still carrying
    the old ±0.02/−0.03 step value converges on the next run. The old steps only drifted
    upward for a rule right more than 60% of the time and never converged.
  - **Live rating** (`rate_active`): every ACTIVE signal is scored against the latest
    price on each audit and the result is stored on the signal (`live_score`,
    `live_outcome`, `live_rated_at`; shown as "Ahora: N% a favor" in the panel). The
    readability threshold is the sigma of the horizon the signal's age has reached.
    Checkpoints are never rewritten; a run with no price keeps the last rating.
  - `create_checkpoints` skips horizons the signal already has. `_reanchor` deletes only
    the pending ones, and recreating a scored horizon violated the (signal_id, horizon)
    unique constraint — the page rolled back as a persist failure every cycle until +7d.
  **A ticker that didn't move is excluded from the basket, not counted against it**, and a
  checkpoint with nothing measurable is NEUTRAL and teaches the rules nothing. Since the
  2026-09-20 audit (prod had 23.9% accuracy ex-neutral and random baskets scored 61–68%
  "correct" — the auditor measured nothing) the scorer is:
  - **the bar at the checkpoint's own target time** (`prices.fetch_price_series`: 5-minute
    bars inside the 5-day window, the daily close otherwise), never "now" — when this ran inside the
    30-min cycle, "now" was a random 60–90 min window for +1h and every horizon due in
    one cycle received the same price;
  - **+1h/+6h in trading time** on the US session (`trading_time.py`, DST-aware, no holiday
    calendar); a Sunday-03:00 signal's +1h lands Monday 10:30 ET;
  - **a ticker is readable when it moved more than 0.75 of its own horizon sigma**, computed
    from the same series (floor 0.1%); ties are NEUTRAL;
  - **no price → pending**, retried next audit for up to 3 days (`_GIVE_UP_AFTER`), then
    NEUTRAL "sin datos".
    Never stamp `evaluated_at` on a missing price: a Yahoo stall used to burn every due
    window forever.
  The portfolio path (`fetch_and_cache_prices`) stays on daily closes — one row per ISIN
  per day paired with that day's ECB rate. Don't switch it.

### Scheduling — prod runs on external cron, NOT APScheduler
The in-process APScheduler (`/geo/scheduler/start`, UI "Monitor" button) only survives
while the instance is alive — with `--min-instances=0` it dies on scale-to-zero.
**Prod periodicity = two Cloud Scheduler jobs**: `geo-intel-cycle` → `POST /api/geo/cron`
hourly, `0 * * * *` (ingest, signals, notify; was `*/30` until 2026-10-01 — see the cost
note in `docs/deployment.md`) and `geo-intel-audit` → `POST /api/geo/audit` every
4 hours (checkpoints, live re-rating, rule learning). Both authenticate with header
`X-Cron-Key == FINVIEW_CRON_SECRET` (constant-time compare; empty secret disables the
endpoint) and run synchronously so Cloud Run keeps CPU until they finish. Don't convert
them to fire-and-forget threads — the instance can be reclaimed after the response.

**The rollout pauses the jobs and must resume them.** `cloudbuild.yaml` pauses the
four Scheduler jobs before switching traffic; for a month nothing resumed them, so every
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
direction **grouped by tier** (Local / Nacional / Internacional, `lib/geo.ts`
`groupByTier`; a basket with no tier renders as one unlabelled group) — read top
to bottom the groups are the ladder, each headed by how its tier reads
(`tierStateBadge`) — and the 5 backtest checkpoints (1h/6h/1d/3d/7d). Tapping a ticker chip
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

### What Ideas is, legally
Ideas is **data interpretation, not financial advice** (owner's decision, 2026-10-02). It
relates public events to the assets that have historically moved with them; the instrument
and direction describe that relation. Keep it that way: no copy, prompt or notification may
say what to buy or sell, how much, where or how. `/legal/condiciones` §3 states it and
`docs/compliance/pendientes.md` records the decision and what would reopen it.
