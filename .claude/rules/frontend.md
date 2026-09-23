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
  `useTheme()` and passes colours in explicitly.

## Failed enrichment fetches

`bestEffort("label")` from `src/lib/bestEffort.ts`, never a bare `.catch(() => {})`.
It swallows exactly as before but logs with `console.warn`, so a persistent failure is
findable. `console.error` is reserved for the dashboard's primary loads — the two should
stay distinguishable in a console. `bestEffort.test.ts` fails if a bare swallow returns.

Use it only where the page is genuinely fine without the data (badges, lens toggles,
autocomplete). A fetch whose absence a user would misread as "you have none" needs a real
error state instead.

## Options page layout

`app/options/page.tsx` was 2,457 lines, then 1,628, now ~500: it owns the state, the
effects and the handlers, and composes modules that sit beside it — `WatchlistTab.tsx`,
`MonitorTab.tsx` (with `AlertsPanel`, `UnusualPanel`, `TechnicalSignalsPanel` and the
`TickerLinks` chips as named components), `OptionsStatsCards.tsx`, `BacktestTab.tsx`,
`AgentChat.tsx`, `AnalysisTab.tsx`, `badges.tsx`, `meffTickers.ts`, `useBacktest.ts`,
`useCrossLens.ts`, `types.ts` (number/date formatting is shared app-wide in
`src/lib/format.ts`).

The watchlist and monitor tabs read 19 and 14 bindings from the page and receive every one
as an **explicit prop** — no context, no store. State stays on the page because both tabs
and the stats cards read the same alerts/watchlist, and Radix unmounts inactive
`TabsContent`, so owning any of it in a tab would drop it (and refetch) on every tab switch;
that is also why `useBacktest` is held by the page, not its tab. Two hooks were left inline
on purpose: a `useOptionsData` would have to hand back six setters the page's handlers
write to, and the watchlist auto-sync effect reads seven page bindings and depends on the
`watchlistRef` dance documented above it.

## Portfolio page layout

`app/portfolio/page.tsx` was 1,016 lines; it is now ~220 and owns only the header,
the Zonas Clave / geo badge state and `handleAddToZonas`. Beside it: `types.ts`
(response shapes, `TX_LABELS`/`TX_COLORS`, `PositionsListProps`),
`PortfolioSummaryCards.tsx` (fail-closed totals render "—" plus the reason),
`PositionDetailPanel.tsx` (the expanded row, shared by desktop and mobile),
`PositionsTable.tsx` / `PositionsMobileList.tsx` (same `PositionsListProps`, no
context), `usePortfolioData.ts` (two-phase load + retry) and `usePositionDetails.ts`
(expand state, detail cache, OHLC cache, chart scope). The two hooks are called
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
