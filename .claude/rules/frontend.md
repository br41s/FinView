---
paths:
  - "frontend/src/components/**"
  - "frontend/src/lib/**"
  - "frontend/src/app/**"
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
