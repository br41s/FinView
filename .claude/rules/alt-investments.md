---
paths:
  - "backend/api/alt_investments.py"
  - "backend/services/cnmv_catalog.py"
  - "frontend/src/app/alt-investments/**"
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
