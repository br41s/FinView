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
  not unit-tested (vitest runs in node, `.ts` only); `components/` is React controls and cards.
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
- **Layout is a pure function of asset ids** (hash slots in a district grid). It never reads
  weights, prices or events: a price refresh must not move a building. Lots have one pitch (the
  largest footprint plus a street), so a building that grows a tier cannot collide.
- **The city is organic, not a set of pads** (`model/townLayout.ts`, `terrain.ts`, `infra.ts`).
  Districts keep a **fixed compass slot** (their index in `DISTRICT_IDS`), so adding a holding
  never turns the town; each is a street grid rotated a few degrees from its neighbours. The
  land is a heightfield: sea, a lake and a river that bends round the square, a **plateau for
  the funds and treasury districts** with mountains behind it. Terrain is a function of the
  compass and the district sizes only (never of weights), so a hill cannot move either.
- **Holdings are landmarks, the rest is scenery.** `FillerSpot`s (homes, towers, skyscrapers,
  villas on the plateau, sheds) fill free slots and the land between districts; they are coloured
  (saturated palettes per kind) but never labelled or clickable, and **must stay smaller than the holdings** (`WIDTH` in
  `townLayout.ts`) or "size = weight" stops meaning anything. Homes exist in every district
  (fewer downtown, villas only on the plateau): pinned in `townLayout.test.ts`.
- **Everything that stands on the ground asks the terrain for its height** (`terrain.heightAt`;
  `roadY` is the ground but flat across water, i.e. a bridge). Sites, labels, markers, agents,
  vans and the camera target all do; a new object placed at y = 0 will sink on the plateau.
- **Transport** (`model/infra.ts`, `engine/infra.ts`): an elevated expressway ring, an
  expressway round the square, a surface railway with a shuttle, and a monorail loop on pillars.
  They run in the corridors between districts and the layout keeps buildings out of them
  (`nearInfra`, tested). Traffic is scenery for now: it does not act out events.
- **A ribbon's index order matters**: `ribbon()` strips that wind clockwise face down and are
  culled, so roads looked missing while their bridges showed. Check roads from above.
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
- **Lighting and clock** live in `engine/lighting.ts` (hemisphere, sun + shadow, fog, sky backdrop,
  env) driven by `engine/skyModel.ts`, a pure function of the city hour (keyframes, wraps at midnight,
  `night` 0..1 drives windows and bloom). `PCFSoftShadowMap` no longer exists in three 0.186: use
  `PCFShadowMap` + `shadow.radius`. Tone mapping is Khronos Neutral (ACES muted the colours).
- **Post-processing** (`engine/post.ts`): N8AO (`n8ao`, CC0 licence file; peer `postprocessing` is
  Zlib) -> bloom (night only) -> OutputPass -> SMAA. `QUALITY[tier].post` is `null` for low (plain
  `renderer.render`, no composer or float targets exist). N8AO renders the scene once into its own
  target; the shadow pass is what doubles `stats().drawCalls`. `renderer.info.autoReset` is off and
  read after the frame so the numbers cover the whole chain. A quality change keeps the city hour.
- Dev handles for screenshots: `__livingWorld.setHour(h)`, `.focusPoint(x, z, distance)`, `.setQuality(q)`.
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

