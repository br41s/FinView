---
paths:
  - "frontend/src/components/**"
  - "frontend/src/lib/**"
  - "frontend/src/app/**"
---

## Theming

`next-themes` is mounted in `app/layout.tsx` via `components/theme-provider.tsx` with
`attribute="class"`, matching the `@custom-variant dark (&:is(.dark *))` in `globals.css`.
Default is `system`; `ThemeToggle` in the header makes it an explicit choice.

- **Never hardcode a palette literal.** Every colour goes through a token — shadcn's
  (`--background`, `--card`, …) or FinView's `--fv-*`, which is what all 66 CSS modules
  read. A baked-in `rgba(245,241,232,…)` looked fine until dark mode turned on and the
  featured pricing card rendered light text on a light card.
- A surface that inverts against the page uses the `--fv-invert-*` pair, which each theme
  defines for itself, rather than assuming which theme is active.
- Canvas cannot read CSS variables, so `PriceChart` reads the resolved theme from
  `useTheme()` and passes colours in explicitly. SVG can: `fill`/`stroke` attributes
  resolve `var()` and `color-mix()` (Ideas' map relies on it).
- A translucent token is `color-mix(in srgb, var(--x) N%, transparent)` or Tailwind's
  `text-foreground/N`, never a hex alpha suffix: `"var(--x)" + "1A"` is invalid CSS and
  silently drops the colour. Ideas hardcoded its light palette until 2026-10-02 and
  stayed light in dark mode.

## Page header and footer

Every signed-in top-level page renders `components/PageHeader.tsx`. Its first row is the
same on every page (title · `QuickNav` · `HeaderActions`), so the nav and account buttons
never move when you switch pages. Page-specific controls go in `actions` on the second row,
next to the subtitle, and wrap downward; status lines go in `children`. Legal notices
(`AiDisclaimer`, `PastPerformanceNote` for a page-level hit rate) go in a `<footer>` at the
end of the page, not in the header.

## Failed enrichment fetches

`bestEffort("label")` from `src/lib/bestEffort.ts`, never a bare `.catch(() => {})`.
It swallows exactly as before but logs with `console.warn`, so a persistent failure is
findable. `console.error` is reserved for the dashboard's primary loads — the two should
stay distinguishable in a console. `bestEffort.test.ts` fails if a bare swallow returns.

Use it only where the page is genuinely fine without the data (badges, lens toggles,
autocomplete). A fetch whose absence a user would misread as "you have none" needs a real
error state instead.

## Options page layout

`app/options/page.tsx` was 2,457 lines, then 1,628, then ~500, now ~300: it owns the UI
state (tab, monitor filter, expanded row, new-ticker input, run-cycle spinner) and composes
modules that sit beside it — `useOptionsData.ts` + `optionsData.ts`, `WatchlistTab.tsx`,
`MonitorTab.tsx` (with `AlertsPanel`, `UnusualPanel`, `TechnicalSignalsPanel` and the
`TickerLinks` chips as named components), `OptionsStatsCards.tsx`, `BacktestTab.tsx`,
`AgentChat.tsx`, `AnalysisTab.tsx`, `badges.tsx`, `meffTickers.ts`, `useBacktest.ts`,
`useCrossLens.ts`, `types.ts` (number/date formatting is shared app-wide in
`src/lib/format.ts`).

The watchlist and monitor tabs read 19 and 14 bindings from the page and receive every one
as an **explicit prop** — no context, no store. State stays on the page because both tabs
and the stats cards read the same alerts/watchlist, and Radix unmounts inactive
`TabsContent`, so owning any of it in a tab would drop it (and refetch) on every tab switch;
that is also why `useBacktest` is held by the page, not its tab.

**Server data is a reducer, not a bag of setters.** `optionsData.ts` is a pure
`optionsDataReducer`: every change the page makes to positions, snapshots, alerts, unusual,
watchlist, agent status, hidden/no-options sets, technical signals and the load flags is an
action dispatched *after* the API call it mirrors succeeds (removing a ticker also drops its
alerts and unusual rows; a retry clears the banner without re-arming the spinner).
`useOptionsData` owns the loads, the watchlist auto-sync effect (with its `watchlistRef` /
`syncedTickersRef` dance, documented at the site) and the mutations, and returns read-only
state plus commands — never a setter. It was deferred in Phase 5 because the only shape then
on offer handed six setters back to the page; moving the handlers in as actions removed them.
The page calls it right after the geo effect so the mount-time fetch order is unchanged.
Transitions are pinned in `optionsData.test.ts`.

## Portfolio page layout

`app/portfolio/page.tsx` was 1,016 lines; it is now ~220 and owns only the header,
the Zonas Clave / geo badge state and `handleAddToZonas`. Beside it: `types.ts`
(response shapes, `TX_LABELS`/`TX_COLORS`, `PositionsListProps`),
`PortfolioSummaryCards.tsx` (fail-closed totals render "—" plus the reason),
`PositionDetailPanel.tsx` (the expanded row, shared by desktop and mobile),
`PositionsTable.tsx` / `PositionsMobileList.tsx` (same `PositionsListProps`, no
context), `usePortfolioData.ts` (two-phase load + retry) and `usePositionDetails.ts`
(expand state, detail cache, OHLC cache, chart scope), and `ExposureCharts.tsx` +
`useExposure.ts` (sector/region bars from annual reports; loads once prices are in,
then steps `POST /portfolio/exposure/refresh` while it makes progress — see
`.claude/rules/segments.md`), and `AiExposureCard.tsx` (what reports say about AI; same
loop through `useAnnualReports`, against `/portfolio/ai-exposure`). The two hooks are called
*after* the badge effects on purpose: effects run in declaration order and the
mount-time fetch order (zonas → geo → portfolio → OHLC) is unchanged from the inline
version.

## Price charts (lightweight-charts) — shared infra

`components/charts/PriceChart.tsx` is the one generic price chart used everywhere
except Zonas Clave's wrapper: candlesticks (line-series fallback when OHLC absent),
optional `priceLines` (S/R, strikes, spot) and optional `markers` (executions).
Attribution logo on (Apache-2.0). Theme-aware via next-themes (canvas can't read CSS vars).

- **Data**: `GET /charts/price-history?ticker=&period=` (charts.py) — daily OHLC from
  yfinance, period whitelisted {6mo,1y,2y,5y,10y,max}, best-effort (returns `[]` on any
  failure → caller hides the chart). Read-only; never touches FIFO/transactions.
- **lib/chartMarkers.ts**: `executionMarkers(txs)` (BUY ▲ / SELL ▼ / DIVIDEND ●, same-day
  same-type collapsed into one marker labelled with the count)
  + `CHART_SCOPES` (1D / 1W / 1M / 1A / 5A / MAX, client-side slicing).
- **Used in**:
  - `/portfolio` list expansion: candles + buy/sell/dividend markers.
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

### Landing page garden game
- `components/GardenGame` sits under the hero on `/`. Idle, it is an animation (demo mode:
  the garden reinvests its own coins and restarts when full); "Jugar" hands the same canvas
  to the player. Same idea as FlyWell's airport on its sign-in page.
- **Rules are a pure module** — `src/game/garden/sim.ts`, tested in `sim.test.ts` with a fixed
  random. The canvas only draws (`scene.ts`), and the component owns the clock, the pointer
  and the HUD. Change a rule in `sim.ts` and its test, never in the component.
- **Difficulty is one function**: `bearsPerMinute` in `game/garden/difficulty.ts`.
- The simulation lives in refs; React state holds only what the HUD shows. The best score is
  read with `useSyncExternalStore` (localStorage key `fv-garden-best`, listed in
  `/legal/cookies`) because `react-hooks/set-state-in-effect` rejects reading it in an effect.
- The loop pauses when the section is off screen or the tab is hidden, and with
  `prefers-reduced-motion` the idle garden is a still picture. Colours are read from the
  site's CSS variables, so it follows the theme; nothing is downloaded.
- **Watching it in the Browser pane**: the pane reports `document.hidden = true` and fires
  `requestAnimationFrame` about once a second, so the garden looks frozen. For debugging
  only, shim rAF with `setTimeout` and override `document.hidden` in the page.
- The copy is a joke about a bear market eating a garden and says so ("Es solo un juego.
  Aquí tampoco hay consejos de inversión"). Keep it that way: see the not-advice rule.

---

## Living World (`/living-world`, "Mundo vivo")

Spec: `FinView_Living_World_Technical_Spec.md` (Brais's Downloads). A standalone 3D town for the
portfolio, built in phases. **Phase 1 (current): the buildings are the user's real portfolio; every
event is still simulated.** `/living-world?demo=1` keeps the Phase 0 fictional town (`model/fixtures.ts`,
ISINs start `ZZ`, nothing fetched) and says "Datos ficticios"; the real town says "Tu cartera · precios
del …". Phase 2 (real event history, previous close for price moves) is not built.

- **Real data = one read-only endpoint.** `GET /api/living-world/world` (`backend/services/living_world.py`)
  is `get_open_positions` plus classification; it values, converts and reconciles nothing. Unknown cost,
  price or weight is `null` (the summary's `total_market_value` is `null` unless every position is priced);
  the town draws an unpriced holding small and marked, and the footer says how many. No Yahoo call: asset
  type and sector are read from what the portfolio's exposure refresh already stored (`listing_profiles`,
  else the dominant sector of the latest `segment_reports`); what is not there yet is `classified: false`
  ("Sin clasificar", default building) and fills in once Cartera has run its refresh. `ARCHETYPE_OVERRIDES`
  (curated ISIN → archetype) is **empty on purpose**: this repo is public and the list would be someone's
  holdings. `day_change_pct` is always `null`: two `price_cache` snapshots (taken whenever the portfolio
  was first opened that day) are not a daily move; Phase 2 stores the previous close.
- **Frontend load is `hooks/useWorldData.ts`** through `api.livingWorld.world()` (`request()`, never
  `fetch`): loading / error (Spanish, retry, link to demo) / empty (link to import) / ready. A refresh
  keeps the town on screen and, if it fails, says so in the footer and keeps the old data.
- **The scene rebuilds only when `sceneSignature(assets)` changes** (id, name, archetype, type, weight
  rounded to 0.1). `WorldShell` keeps the latest assets for the inspector and filters and hands the renderer
  a stable copy (set-state-during-render). On a real rebuild the camera refits; quality, pause, director
  mode and filters are re-applied by effects keyed on the scene's assets, and the selection is handed back
  by `reselect`. Add any new "survive a rebuild" state to that list.
- **Events in the real town start empty.** «Simular eventos» (off) seeds a week of demo history and a live
  trickle; every simulated event has confidence `demo` (tag «Simulado»), a «Simulado · » title prefix and
  a banner. Turning it off clears them. Never present a generated event as a fact about a real company.

- **Same split as the garden game.** `model/` is pure TypeScript with colocated `*.test.ts`
  (layout, scale, filters, priority, director, routes, fixtures); `engine/` is Three.js and is
  mostly untested (vitest runs in node, `.ts` only; the pure Three.js geometry builders are the exception: `towers.test.ts`, `fillers.test.ts`); `components/` is React controls and cards.
  A rule changes in `model/` and its test, never in the renderer. Per-frame state never goes
  through React: the render loop, agents and director live in `engine/scene.ts`.
- **Do not name a file `layout.ts` (or `page`, `route`, `template`, `loading`, `error`, …) under
  `app/`.** Next treats it as a special App Router file; `model/layout.ts` broke `tsc` with
  "Property 'default' is missing". The town layout is `model/townLayout.ts`.
- **Three.js is lazy**: only `LivingWorldClient.tsx` imports the shell, behind
  `next/dynamic(..., { ssr: false })`, so no other route pays for it. Keep it that way: check
  the `pnpm build` output when adding imports.
- **One merged mesh per site** (`engine/buildingFactory.ts`, vertex colours, a `Builder` that
  merges primitives) so ~100 companies stay ~100 draw calls; trees, people and vans are
  `InstancedMesh`. `createSite` is the seam for authored glTF kits in a later phase.
- **Every holding is a unique complex (F3).** `model/towerSpec.ts` derives a spec from (archetype, id,
  tier) only: weight never reaches it, so a price move cannot redraw a building and a tier change only
  ADDS parts (each tier's parts are a prefix of the next's; pinned in `towerSpec.test.ts`). The id picks
  the silhouette family of the main structure from the archetype's pool, the plan, taper, twist,
  setbacks, crown, diagrid, accent hue (archetype palette + id nudge, `accentColour`; the few brand
  colours in `companyProfile` still win) and glass tint. `engine/mains.ts` builds the main structure
  (twisting tower, gherkin with diagrid, setbacks, cylinder with helipad ring, twin slabs with a
  sky-bridge, lattice mast or headframe, dome, arena, power-plant stacks, faceted crystal),
  `engine/parts.ts` the extras (plaza, hall, pavilion, annex tower, car park, mall, hospital wing, dish,
  silos, tanks, flare, pipe rack, turbine hall, substation, wind turbines, solar field, cooling tower,
  heaps, conveyor, vault, colonnade...), `engine/towers.ts` the primitives (`loft`: a plan lofted floor
  by floor with taper, twist and an optional lathe profile; lattice mast; crowns; helipad). Parts stand
  in the slots of `model/siteLayout.ts` (front band low, flanks, back), shuffled and mirrored by the id,
  assigned in the order parts are added so none moves when a tier adds one.
  Tiers: outpost = main + 1 part, small + 3, campus + 5, major + 7, and the tallest element is 8.4-9.8 /
  11-13.4 / 15-19 / 22-30 local units (x1.28..1.6 in the town); `stadium` and `dome` take
  `FAMILY_HEIGHT` of that (their tallest element is a mast). Budgets, tested in `engine/towers.test.ts`
  (it also checks every face is wound outwards): <= 1.5k / 2.4k / 3.2k / 4k triangles per site, and
  everything inside the plot. The utilities complex (cooling tower, chimneys, turbine hall, substation,
  wind turbines, solar field) and the energy one (process columns, flare, tanks, pipe rack) are the
  proof that an archetype is a whole industrial site, not a bigger box. The sign wall and brand plate
  stand at the front of the plot (z = 0.5 n), not on the tower, so the plate suits any height.
- **Layout is a pure function of asset ids** and the street skeleton of none. `model/cityGraph.ts` builds
  the roads once (planar graph on one orthogonal grid, PITCH 44, 9 x 9 cells): a plaza block bounded by a
  ring road, an avenue loop at +-110 (the monorail rides it), a perimeter avenue, streets on every other
  line, a canal (cells x = -88 then z = 44, crossed by bridge edges), and a railway along z = 0 that meets
  streets only at `crossing` nodes. Node ids come from integer coordinates, never insertion order. Blocks
  are the bounded faces of a half-edge walk (not a hand list); `model/cityLots.ts` shrinks each by its
  pavements and splits it by a jittered oriented-box cut into lots that front a street. The skeleton never
  reads the holdings: adding one cannot move a road, block or lot.
- **Districts keep a fixed compass wedge** (`slotAt`, their index in `DISTRICT_IDS`): a block belongs to the
  district of its centroid's angle. A holding picks its lot by ranking its district's free lots with its own
  hash, premium frontage (ring road, avenues) first, claiming in hash order (`townLayout.ts`); beyond a
  district's capacity it takes the nearest free lots. Stateless, so a newcomer can only push a holding to its
  next-best lot when their hashes collide (pinned: at most a handful move). Holdings need lots of at least
  14.4 on a side; the biggest landmark is 16.4, so filler lots are subdivided every ~6.4 and fillers stay <= 5.
- **The city is flat.** `terrain.ts` is a level plain with the canal carved into it (`groundAxes` gives the
  ground mesh coarse samples away from the canal, fine across it). There are no mountains, plateau or sea.
  Everything still asks `terrain.heightAt` / `roadY` (0, flat across water = bridge).
- **Roads are built from the graph** (`engine/roads.ts`): per junction, incident roads are sorted by angle,
  offset side lines intersected for the corner points, asphalt corners get a 3-unit kerb fillet and the
  pavement keeps square corners; ribbons start at each arm's stop distance; zebras sit on every junction
  leg and at the plaza gates. Two draw calls for the whole network. Triangle winding is forced per triangle
  (`Flat.tri`), so a strip can never face down.
- **Holdings are landmarks, the rest is scenery.** `FillerSpot`s fill every lot no holding took; they are
  coloured (saturated palettes per kind), never labelled or clickable, and **must stay smaller than the holdings** (`WIDTH` in
  `townLayout.ts`) or "size = weight" stops meaning anything. Pinned in `engine/fillers.test.ts`: the tallest
  possible filler (`fillerMaxExtent`, spire included) is lower than the lowest outpost of any archetype and no
  wider than an outpost's plot, so tune `HEIGHT_SCALE` and the recipes against that test. Three kinds
  (skyscraper, tower, house) have a second silhouette (round, stepped, gabled with a water tank) that takes
  about half of their spots by a stable hash: 9 filler draw calls.
- **Everything that stands on the ground asks the terrain for its height** (`terrain.heightAt`).
- **Transport** (`model/infra.ts`, `engine/infra.ts`), derived from the graph: a monorail on pillars above
  the avenue loop (pillars are chosen in the model, always in the avenue's central reservation, never in
  water or on a crossing; stations on the loop edge nearest each district) and a ground railway from a
  terminus beside the plaza east out of town (a platform at each end) with level crossings.
  **Both trains run on timetables** (`model/trainSchedule.ts`, pure functions of the simulation clock, so
  renderer, barriers and road traffic read the same answer): the ground train dwells at a terminus with its
  door lamps lit, pulls out, cruises at 11 u/s and brakes into the other end; the monorail circles the loop
  and stops at every station (head half a train past the platform centre), the doors slide open while it
  dwells, and a second train runs the same timetable half a period behind. **Level-crossing barriers** are
  an `InstancedMesh` of arms plus flashing lamps; `crossingClosed` (6 s before the train reaches the barrier
  until its tail has cleared) drives them and is the predicate road traffic stops on.
- **Road traffic (F4)** is `model/traffic.ts` (pure, tested) + `engine/vehicles.ts`. `buildLaneNetwork` cuts
  right-hand lanes from the graph (`lanes / 2` per direction, offset clear of an avenue's median, trimmed
  to the junction mouth) and every legal movement through a node is a short curve (`turn`); two movements
  that come within a vehicle's width of each other (3.3 for turns, 1.9 for parallel straights) or end in
  the same lane are recorded as **conflicts**. `TrafficSim` is a fixed-step (1/30 s) sim: IDM car-following
  with the nearest leader on the lane, on the next movement and on its siblings, a virtual obstacle at the
  stop line, and a **reservation rule**: a vehicle may only enter a junction when its signal is green, the
  exit lane has room for it (and for everything already granted) and no conflicting movement is inside. A
  vehicle can hold reservations at two junctions at once (`holds`): releasing on "rear left the lane"
  only is what let long vehicles run a short lane unprotected (found by the overlap test, 2026-11-11). Signals
  alternate by axis with an all-red gap and are only the flow; the reservation is the safety net. The
  longest-waiting movement on green goes first (left turns never starve). Level crossings stop traffic at
  a stop line while `crossingClosed`. Spawning is deterministic and weighted to the centre; `trafficLevel(hour)`
  scales the target; a vehicle stuck 60 s is removed. Event vans (`AgentSystem.sendVan` -> `VehicleSystem`)
  are scripted on the right-hand lane, send themselves out 1.6 s apart and are **external actors**: traffic
  brakes for them and they give way to traffic (never for more than 3 s).
  `engine/toyMaterial.ts` is the shared material of cars, trains and walkers (a `MeshStandardMaterial`
  patched like the facade one): per-vertex `aKind` (paint takes the instance colour, glass, headlight,
  taillight, lit window, hair), `uNight` from `facadeShared` lights lamps, brake lights follow the per-instance
  `aBrake`, headlight beams are one additive instanced wedge mesh shown only at night. Vehicles are rounded
  boxes (`GeoBuilder.roundBox`), scaled x1.2-1.35 so they read next to the lanes; their size lives in
  `VEHICLE_SPEC` (the sim uses the same length and width).
- **People (F4)** are `model/pedestrians.ts` + `engine/people.ts` + `engine/agents.ts`. Walkers follow a
  pavement network: each road half-edge has a pavement either side, a walker owns one side for good and at a
  junction hugs the corner (`next` = the road before the one it came from in angle order), which walks a
  city block and **never crosses the asphalt** (pinned in `pedestrians.test.ts`; inner corners are rounded,
  outer ones chamfered round the kerb corner). Four professions (worker, executive, courier, analyst), each
  one merged geometry drawn as one `InstancedMesh`, chosen by the district a walker spawns in (the district's
  own profession half of the time) and fading in and out with `crowdLevel(hour)`. The walk is in the vertex
  shader (`aLimb`, `aAnim`), so the CPU writes a matrix and three numbers per person. Company staff keep their
  post and act out events (role -> profession); event actors walk the route offset onto the pavement
  (`sidewalkRoute`). `AgentSystem.pickAgent` replaces picking `bodies`; follow mode is unchanged.
- **Quality tiers** add `maxWalkers` (40 / 150 / 300) and `maxVehicles` (60 / 180 / 300 at the busiest hour);
  `maxAgents` is now company staff only. Measured at hour 9 from the default camera: low 294k triangles
  (before 269k), medium 1.13M (989k), high 1.44M (1.30M), 3 more draw calls, 60 fps (30 on low, capped).
  `engine/rollingStock.test.ts` keeps a vehicle under 560 triangles (bus 900) and a person under 600.
- Dev handles added in F4: `__livingWorld.crowd()` (visible people with ids and professions, vehicles, train
  positions), `.followAgent(id)`, `.followTrain()`; `stats().vehicles`.
- **Routes** (`routeToPlaza`) are Dijkstra over the ground roads from a lot's door to the nearest plaza
  gate; event vans (on their lane) and event actors (on the pavement, via `sidewalkRoute`) follow them.
- **A ribbon's index order matters**: strips that wind clockwise face down and are culled, so roads looked
  missing while their bridges showed. `Flat.tri` in `engine/roads.ts` forces the normal up; `ribbon()` in
  `props.ts` (route highlight) still needs counter-clockwise order. Check roads from above.
- **Size = portfolio weight, not price action** (`model/scale.ts`, piecewise-linear, tiers with
  hysteresis). An unknown weight/valuation is drawn small *and marked* (yellow diamond), never
  treated as zero. Events are acted out temporarily; only tier changes alter a building.
- **Event priority is deterministic** (`model/priority.ts`: base × magnitude × relevance ×
  confidence, every factor kept). `bucketFor` / `IMPORTANT_AT` / `CRITICAL_AT` decide how noisy
  the town is. Brais confirmed 2 / 6 (2026-11-08); revisit with real event volumes in Phase 1.
- **Material gotcha**: toggling `material.transparent` needs `material.needsUpdate = true`.
  Opaque materials compile with alpha forced to 1, so fading buildings (filters mute to 22 %)
  silently ignored `opacity` until the flag change triggered a recompile.
- **The look (F2).** `engine/materials.ts` is one `MeshStandardMaterial` patched with `onBeforeCompile`:
  glass parts (the per-vertex `aKind` that `Builder` writes: 0 wall, 1 glass, 2 accent/roof; the
  landmark window colours count as glass) get a window grid with mullions, a vertical gradient, sky
  reflections and lit windows at night (`uNight`); walls and roofs stay plain. It serves merged sites
  (one material per site, seed uniform) and the filler `InstancedMesh`es (per-instance `aWall`,
  `aGlass`, `aSeed` from `fillerPalette.ts`). **Glass stays opaque** (the AO pass draws transparent
  depth-writing meshes twice). The sky map (`createSkyEnvironment`, PMREM) is set as `material.envMap`,
  never `scene.environment`: Lambert materials would pick it up as a mirror. Ambient comes only from
  the hemisphere light (the shader zeroes the map's diffuse term). Filler floors are exactly 1.0 tall
  and start on whole numbers so the shader's rows match the storeys: keep that when editing recipes.
  **F3 extensions of the same shader (all additive, fillers unaffected):** `aKind` 3 is glass with a
  diagrid (two families of diagonals across the window cells, period 4, colour `lattice.hex`, no lit
  windows on the bars); `aArc` is the arc length along a curved shell, written by `loft`, in a whole
  number of window columns per ring so the grid closes without a seam (`ARC_NONE` = "pick the axis from
  the facing", what every other part gets); `spandrel` darkens the lower edge of each window cell so
  storeys read as floor plates. Site material: `FACADE_ROWS` = 2.6 rows and columns per local unit, a
  storey is `FLOOR_H` = 1/2.6: glass volumes stand on `k * FLOOR_H` (`BASE_Y`).
- **Lighting and clock** live in `engine/lighting.ts` (hemisphere, sun + shadow, fog, sky backdrop,
  env) driven by `engine/skyModel.ts`, a pure function of the city hour (keyframes, wraps at midnight,
  `night` 0..1 drives windows and bloom). `PCFSoftShadowMap` no longer exists in three 0.186: use
  `PCFShadowMap` + `shadow.radius`. Tone mapping is Khronos Neutral (ACES muted the colours).
- **Post-processing** (`engine/post.ts`): N8AO (`n8ao`, CC0 licence file; peer `postprocessing` is
  Zlib) -> bloom (night only) -> OutputPass -> SMAA. `QUALITY[tier].post` is `null` for low (plain
  `renderer.render`, no composer or float targets exist). N8AO renders the scene once into its own
  target; the shadow pass is what doubles `stats().drawCalls`. `renderer.info.autoReset` is off and
  read after the frame so the numbers cover the whole chain. A quality change keeps the city hour.
- Dev handles for screenshots: `__livingWorld.setHour(h)`, `.focusPoint(x, z, distance)`, `.setQuality(q)`,
  `.sites()` (id, archetype, tier, silhouette family, position and the asset of every holding; with
  `setAssets` it lets you force tiers). `.focusPoint` keeps the camera high: tilt it with a shift-drag
  (`PointerEvent` with `shiftKey` dispatched on the canvas) to see a skyline, and hide the React overlay
  (`.world-module__*__ui`, `display: none`) for a clean screenshot.
- **Canvas lifecycle**: `hooks/useWorld.ts` creates a fresh `<canvas>` per mount. A canvas whose
  context was released by `forceContextLoss()` cannot be reused, and React strict mode mounts
  twice; the `webglcontextlost` listener is removed in `dispose()` or the first mount's
  cleanup reports a "lost context" error to the second.
- **Browser pane**: it reports `document.hidden = true`, so the loop (which stops when hidden)
  renders nothing. For debugging, shim `requestAnimationFrame` with `setTimeout`, override
  `document.hidden`, dispatch `visibilitychange`. In dev, `window.__livingWorld.stats()` returns
  fps / draw calls / triangles.
- No `localStorage`, cookies or third-party requests in Phase 0 (the cookie list in
  `/legal/cookies` is unchanged). Any persisted preference in a later phase needs listing there.
- Footer renders `NOT_ADVICE.short`. Nothing in the town tells anyone to buy or sell: arrows
  and "A la baja" describe a market move, not an operating result or a recommendation.

