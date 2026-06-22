# FinView — Dashboard de Inversiones con Brokers Reales

## Onboarding fiscal estilo TaxDown — base del ahorro primero — 2026-06-22

**Decisión CEO:** (1) por fases — completar la **base del ahorro** primero, luego la
base general. (2) salida doble: **casillas** (para rellenar el Modelo 100 guiado) **y**
el **número final estimado** (cuota / resultado a ingresar o devolver). Estilo
cuestionario inteligente, preguntas amplias→detalle.

**Done en esta sesión (copy público, fuera del alcance del onboarding):**
- [x] Quitar el claim "solo validado contra Trade Republic" de las páginas públicas;
      ahora afirman cálculo cross-broker para todos los brokers.
      [features/page.tsx:119](frontend/src/app/features/page.tsx), [pricing/page.tsx:86](frontend/src/app/pricing/page.tsx).

### Por qué "ahorro primero" es la rebanada limpia
- La **escala de la base del ahorro es estatal** (uniforme en toda España) → el número
  final del ahorro **no depende de la comunidad autónoma**. La base general sí (tramo
  autonómico) → de ahí que se difiera. Esto valida la decisión de empezar por ahorro.
- **Acoplamiento a vigilar:** el *mínimo personal y familiar* se aplica primero contra
  la base general y solo el sobrante contra la base del ahorro. Para estimar bien la
  cuota del ahorro hace falta UNA pregunta puente: "¿tienes rentas del trabajo / base
  general?" (sí/no + importe aprox). Sin general → el mínimo entero recae en ahorro.

### Invariantes (topología)
- **Estado:** nueva tabla `FiscalProfile` (user_id, fiscal_year, respuestas). Renta
  manual fuera de brokers → filas `TaxResult` con pseudo-broker `MANUAL` → entran solas
  en la agregación de casillas existente (no se toca el motor FIFO).
- **Feedback:** wizard con progreso; resultado = casillas + desglose de cuota + aviso
  "estimación, no asesoramiento fiscal".
- **Blast radius:** aditivo. NO tocar `fifo_engine.py`. Reusa la suma de `TaxResult`.
- **Timing:** recomputar cuota cuando cambie el perfil O una importación de broker.

### Modelo de datos
- [x] `FiscalProfile` (1 fila por user+año): edad, discapacidad (general/severe),
      descendientes, importe de base general. `Base.metadata.create_all` la crea sola.
      (Estado civil/conjunta y residencia autonómica → diferidos a Fase 2, no se usan
      en v1 individual.)
- [x] ~~Pseudo-broker `MANUAL`~~ → **tabla dedicada `ManualSavingsIncome`**. `Broker`
      es un ENUM nativo de Postgres y el path `create_all`/`ensure_columns` NO puede
      hacer `ALTER TYPE ... ADD VALUE`. La tabla es aditiva y más limpia. `amount_eur`
      siempre magnitud positiva; el signo lo da `category` (RCM/GAIN/LOSS).

### Árbol de preguntas (amplio → detalle) — sección ahorro
- [ ] Gate: "¿Tienes rendimientos/ganancias del ahorro aparte de tus brokers?"
      (intereses bancarios, cripto, fondos en otra plataforma) → si no, salta el bloque.
- [ ] Gate: "¿Te han practicado retenciones fuera de tus brokers?"
- [ ] Datos personales para la cuota: edad, estado civil + conjunta/individual,
      discapacidad, descendientes/ascendientes.
- [ ] Pregunta puente base general (para repartir el mínimo correctamente).

### Cálculo (`services/tax_estimator.py`) — HECHO (motor puro, 12 tests)
- [x] Base del ahorro = RCM (027/029) + G/P (332/337) con compensación cruzada (cap 25%).
- [x] Escala estatal del ahorro por año (tablas por año; **2024 codificado, marcado para
      verificar contra AEAT antes de lanzar**: 19/21/23/27/28%).
- [x] Mínimo personal/familiar (base + edad + discapacidad + descendientes) repartido tras
      la base general. `rates_year_used` expuesto (fallback al último año codificado).
- [x] Retenciones → resultado a ingresar / a devolver.

### API — HECHO (agregación DB + endpoints, 4 tests)
- [x] `_aggregate_savings_inputs`: suma casillas broker (TaxResult) + entradas manuales
      + retenciones (DIVIDEND/INTEREST).
- [x] `GET/PUT /fiscal/profile/{year}`.
- [x] `GET/POST/DELETE /fiscal/manual-income`.
- [x] `GET /fiscal/estimate/{year}` → casillas + desglose de cuota + resultado.

### Frontend — HECHO (typecheck limpio)
- [x] Tipos TS + métodos de cliente API (`src/lib/types.ts`, `src/lib/api.ts`).
- [x] Vista "Mi declaración" en la nav fiscal del dashboard (`app-sidebar.tsx` →
      `view="declaracion"` → [DeclaracionView.tsx](frontend/src/components/DeclaracionView.tsx)):
      formulario de datos (edad/discapacidad/descendientes/base general) + alta/baja de
      ingresos del ahorro manuales + tarjeta de resultado (casillas, base, mínimo, cuota,
      resultado a ingresar/devolver, aviso de año de tablas + disclaimer).

### QA en vivo (localhost) — HECHO ✅
- [x] Backend HTTP end-to-end: PUT perfil, POST/DELETE ingreso manual, GET estimate.
      Compensación (cap 25%), borrado revierte, validación 422. Números exactos.
- [x] Navegador (login → año 2024 → "Mi declaración"): formulario + ingresos manuales +
      tarjeta de resultado renderizan; broker + manual combinan bien; añadir ingreso
      recalcula al instante (A devolver 982 € → A ingresar 68 €). Sin errores de consola.

### Decisiones tomadas
- **v1 = declaración individual únicamente.** Conjunta vs individual (calcular ambas y
  sugerir la mejor) se difiere a una iteración posterior.
- Tablas de escala/mínimos **por año fiscal**, verificadas contra AEAT al construir
  (no hardcodear de memoria).

### Riesgos a confirmar antes de construir
- Postura legal: copy de "estimación orientativa, no asesoramiento fiscal".

### Verificación AEAT (2024) — HECHO ✅
Tablas 2024 confirmadas contra el BOE consolidado de la Ley 35/2006 (IRPF):
escala del ahorro art. 66 (estatal 9,5/10,5/11,5/13,5/15% ×2 → 19/21/23/27/28%),
mínimo contribuyente art. 57 (5.550 € · +1.150 >65 · +1.400 >75), descendientes
art. 58 (2.400/2.700/4.000/4.500 €), discapacidad art. 60 (3.000/9.000 €),
compensación art. 49 (25%). Sin cambios de números; docstring cita artículos +
documenta simplificaciones v1 (no aplica +2.800 <3a, +3.000 asistencia,
ascendientes, ni mínimos autonómicos — todas reducirían la cuota, estimación
conservadora).

**2025 añadido y verificado:** la escala del ahorro subió solo el tramo >300.000 €
del 28% al 30% (Ley 7/2024, ef. 1-1-2025); mínimos y tope de compensación sin cambios.
Ojo: el texto consolidado del BOE muestra SIEMPRE la redacción vigente (la de 2025,
tramo estatal 15%), no la histórica — por eso 2024 (tramo estatal 14% → 28% combinado)
hay que leerlo por la Ley 31/2022, no por el consolidado.

**2023 añadido:** idéntico a 2024 (tramos 27%/28% introducidos por la Ley 31/2022,
ef. 1-1-2023; mínimos y tope sin cambios) → reusa los valores de 2024. Cobertura
completa 2023–2025. Pendiente: mínimos autonómicos por CCAA si se quiere precisión total.

**Nota de proceso:** el PR #68 se fusionó con SOLO el primer commit (verificación 2024);
el segundo (tabla 2025 + corrección del desglose ×2) se perdió. Recuperado por cherry-pick
en este PR junto con 2023.

### Fase 2 (diferida) — base general
Rentas del trabajo, inmuebles, escala general **autonómica**, planes de pensiones, etc.
Aquí entran las preguntas amplias tipo "¿trabajas? ¿tienes inmuebles?".

---

## TR foundation: CSV ledger + PDF fiscal, no data loss — 2026-06-05

**Goal:** 100% accurate for taxes AND positions, composing TR's documents without
double-counting. Evidence on real files (DE PDF + ES PDF + full CSV 2024→2026):
- CSV is the complete buy/sell ledger across the migration; parser already skips
  MIGRATION/transfer/card noise. With CSV: **59/59 positions get cost basis**
  (Unibail 15 @ €990). Only 1 genuine missing-buy edge: ES0684262944 (spin-off).
- BUG: PDF + CSV **double-count dividends/interest** (2025 net €11,214 vs ~€6,592).
- TR fragments into 3 accounts (`0329750901`/`""`/`TR`); other brokers use one id.

**Ownership model (one source per fact):** PDF = fiscal truth (casillas, gain
TaxLots, dividends, interest, withholding). CSV = position ledger (BUY/SELL/SPINOFF).

- [x] CSV import = ledger only: skip DIVIDEND + INTEREST (PDF owns income).
- [x] Unify TR account → fixed `"TR"` id for DE PDF, ES PDF, CSV.
- [x] Verify on real files: 1 account; 59/59 cost basis; div net €5,374 (not the
      doubled €11,214); c29 gross €6,591.84 unchanged.
- [x] Test: CSV+PDF composition (no income double-count, single account, cost basis).
- [x] Full suite (96 passed) + ruff clean.
- Follow-up: supervisor clears superseded missing_buy issues; closed-position
  history may show real+synthetic sells (cosmetic).

---

## UI Deduplication — 2026-06-01

## Navigation & Menu — 2026-06-01

## Display / UX — 2026-06-01

- [x] **U1 — ZC portfolio suggestions**: fetch portfolio positions in ZC page; show "De tu cartera" chip panel below ticker list for tickers not yet in watchlist.
- [x] **U4 — Backtest accuracy bar chart**: add horizontal BarChart above the signal-type table in the Backtesting tab.
- [x] **U9 — Monitor "Mark all" always visible**: show button when monitorFilter === "alerts", disabled (not hidden) when unreadAlerts.length === 0.

---

## Navigation & Menu — 2026-06-01

- [ ] **N2 — Import shortcut in QuickNav**: Upload icon → `/dashboard#importar`; dashboard detects hash on mount and switches to importar view.
- [ ] **N5/N6 — Cross-links ZC ↔ Options**: ZC ticker row → "Ver opciones" (`/options?ticker=X`); Options Cartera row → "Ver en ZC" (`/zonas-clave?ticker=X`). Both pages auto-select the ticker from URL param on load.

---

## UI Deduplication — 2026-06-01

- [x] **D2 — Merge two dividend-by-country charts** (`GrossDividendsByCountryChart.tsx`): bar chart now shows Bruto + Neto grouped bars. Pie chart unchanged.
- [x] **D7 — Merge Alertas + Smart Money into Monitor tab** (`options/page.tsx`): one `monitor` tab with filter buttons (Alertas / Smart Money). Unread badge on tab trigger.
- [x] **D6 — Merge Agente + Análisis into IA tab** (`options/page.tsx`): one `ia` tab with inner sub-tabs (Informe | Chat). `analysisCycle` key preserved on AnalysisTab.

---

## Pendiente de revisión

- [ ] **Animación landing page no reproduce en carga inicial** — La animación SVG (tronco/ramas/flores) solo se ve al pulsar "repetir". Fix intentado: mover keyframes a `globals.css` + `useEffect(() => setReplayCount(c=>c+1), [])` en `FinviewIntro/index.tsx`. Causa probable: race condition SSR/CSS en dev mode. Comprobar en producción; si persiste en dev, inspeccionar Network waterfall de `globals.css` vs primera pintura del SVG.

---

## ⚡ Auditoría de rendimiento — 2026-05-29

**Síntoma reportado:** la app va muy lenta, sobre todo la **carga inicial del dashboard** y en general.
**Diagnóstico:** la lentitud NO está en el motor FIFO (precalculado en import → `TaxResult`/`TaxLot`, se leen como agregaciones simples). Está en: (a) fan-out de peticiones, (b) un `getSession()` por cada petición, (c) llamadas síncronas a yfinance/scraping en el request path, (d) doble salto de red Vercel→Cloud Run.

Orden por ROI. No tocar `fifo_engine.py`. Tras cambios de backend: `pytest backend/tests/ -v` (128 pass). Verificar dashboard antes/después con el Network waterfall.

### 🔴 Crítico — causa principal de la lentitud percibida

- [x] **#1 — Eliminar `getSession()` por petición.** ✅ Hecho ([api.ts](frontend/src/lib/api.ts)): token JWT cacheado a nivel de módulo, dedupe de resolución concurrente (16 peticiones → 1 `getSession()`), refresco al acercarse `exp` (decodificado del JWT) y auto-curado en 401 (retry único). `clearAuthToken()` + `invalidateCache()` en logout ([app-sidebar.tsx](frontend/src/components/app-sidebar.tsx)). *Pendiente verificación: `next build` (no hay node_modules en el worktree) y waterfall sin `/api/auth/session` repetido.* [api.ts:77](frontend/src/lib/api.ts) `authHeaders()` hace `await getSession()` (fetch a `/api/auth/session`) en CADA llamada; el dashboard dispara ~16 → ~16 fetches de sesión extra en el critical path. Resolver el token UNA vez por página (token cacheado a nivel de módulo con refresco por expiración, o `useSession` en el componente y pasar el token). *Verificación: el waterfall debe mostrar 0 llamadas repetidas a `/api/auth/session`.*

- [x] **#2 — Desacoplar el render del dashboard del request más lento.** ✅ Hecho ([dashboard/page.tsx](frontend/src/app/dashboard/page.tsx)): los 3 `Promise.all` secuenciales se fusionan en **un solo grupo paralelo** con los datos rápidos (core fiscal + charts de la vista gráficas) que controla `loading`. El dato lento (`dividendYield` → yfinance) y los secundarios (`yearlyComparison`, tablas fiscales por año) se **streamean** vía `secondaryLoading` sin bloquear el primer pintado; cada fallo degrada solo su vista (antes un único `catch` rompía todo el dashboard). Guard de secuencia (`loadSeq` ref) evita que una respuesta vieja (cambio rápido de año) pise el estado actual. `tsc --noEmit` limpio. *Falta: `next build` y verificación visual en localhost.*

- [x] **#3 — `dividend_yield` no debe llamar a yfinance en el request path.** ✅ Hecho ([charts.py](backend/api/charts.py)): cambiado `fetch_and_cache_prices()` → `get_cached_prices()` (solo lectura). El cache lo puebla `warm-prices` + el agente; los ISINs aún en cartera son exactamente las posiciones abiertas que el warming cubre, y los ISINs totalmente vendidos tienen `current_value` 0 independientemente del precio. Los no cacheados caen al precio histórico de transacción ya presente en `price_map`. Elimina la llamada bloqueante y la carrera con `warm-prices`. *(El unique constraint `(isin, fetched_date)` queda como mejora futura opcional — ya no hay doble fetch concurrente.)*

- [ ] **#4 — Cloud Run: confirmar `min-instances ≥ 1`** (matar cold starts) y keep-alive HTTP. El doble salto browser→Vercel→Cloud Run multiplica latencia por nº de llamadas; reducir llamadas (#1, #2) es lo que más rinde aquí. *Solo verificación de infra, no requiere código.*

### 🟠 Alto — ineficiencias backend

- [x] **#5 — `get_position_detail` recalcula toda la cartera para un solo ISIN.** ✅ Hecho ([portfolio_service.py](backend/services/portfolio_service.py)): `get_open_positions` acepta `isins=[...]`; `_build_tx_positions` filtra las transacciones por ISIN (SQL) y `_load_snapshots` acota `latest`/`historical` al ISIN pero computa `max_year` desde el histórico completo de la cuenta (la cuestión del año autoritativo depende de todas las posiciones). `_apply_prices` ya deriva los ISINs de las posiciones → solo pide 1 precio. `get_position_detail` pasa `isins=[isin]`. Suite completa: **119 passed, 35 skipped**.

- [x] **#6 — Cache cliente para charts/fiscal.** ✅ Hecho ([api.ts](frontend/src/lib/api.ts)): todas las lecturas que alimentan el dashboard (`charts.*`, `fiscal` dashboard/casillas/summary/cross-broker/fifo/option-assignments/cross-validation/yearly-comparison, `dividends`, `capital-gains`) pasan por `fetchCached` (TTL 5 min, clave path+año). Invalidación con `invalidateCache()` en los 6 uploads + `deleteImport` + `deleteAllImports` + `resolveIssue`. `transactions()`/`imports()` quedan sin cache (lista de archivos siempre fresca). Mitiga además el síntoma de #3 en cliente (yield cacheado tras 1ª carga).

- [x] **#7 — Filtros por año rompen el índice.** ✅ Hecho: nuevo helper `year_range(column, year)` en [sql_compat.py](backend/services/sql_compat.py) → rango medio-abierto `>= AAAA-01-01 AND < (AAAA+1)-01-01` que deja la columna sin envolver y usa los índices de fecha (`trade_date`/`close_date` son DATE). Reemplazados **13 filtros** en charts.py (7), fiscal.py (2) y transactions.py (3). Los `group_by(year_str(...))`/`year_month_str` se mantienen (son claves de agregación, no filtros). Regresión: [test_year_range.py](backend/tests/test_year_range.py) — 3 tests incl. equivalencia con el `year_str` antiguo y límites Ene-1/Dic-31. Suite: **122 passed, 35 skipped**.

- [x] **#8 — Tuning de pool para Neon.** ✅ Hecho ([database.py](backend/database.py)): para Postgres/Neon `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`. Se MANTIENE `pool_pre_ping=True` a propósito: Neon autosuspende el compute en reposo, así que el ping convierte una conexión muerta en una reconexión transparente en vez de un error — el round-trip extra compensa por correctness en Postgres serverless. SQLite no recibe args de pool (rama aparte).

### 🟡 Medio — diferir hasta tener el rendimiento resuelto

- [ ] **#9 — Scraping síncrono en options.** `/options/chain/{ticker}` ([options.py:148](backend/api/options.py)) y `/check-availability` ([options.py:350](backend/api/options.py)) raspan en vivo; `check-availability` corre al cargar la página de options sobre todos los tickers. Servir desde snapshot cacheado al cargar; raspar solo bajo demanda (expand).
- [ ] **#10 — Refactor de archivos gigantes** (no es coste de runtime): `import_service.py` (1279 líneas) y `options/page.tsx` (1906 líneas). Solo DESPUÉS de los fixes de perf y con tests en verde.
- [ ] **#11 — `Base.metadata.create_all()` en import** ([app.py:29](backend/app.py)) redundante con Alembic; añade latencia en cold start. Quitar en prod.

---



## Visión
Dashboard personal de inversiones que conecta con tus 3 brokers (DEGIRO, IBKR, Trade Republic), importa datos reales y genera la declaración fiscal española (IRPF).

---

## Resultado investigación APIs e importación

| Broker | Formato entrada | Parser | Datos disponibles |
|--------|----------------|--------|-------------------|
| **Trade Republic** | **PDF Tax Report** (genera TR automáticamente, ~45 págs) | pdfplumber | Dividendos, ganancias/pérdidas con FIFO, retenciones por país, transacciones, patrimonio, **casillas Modelo 100 y 714 pre-calculadas** |
| **IBKR** | CSV Activity Statement / Flex Query XML | ibflex / csv | Trades, dividendos, retenciones, posiciones |
| **DEGIRO** | CSV Transacciones + CSV Cuenta | csv | Trades, comisiones, dividendos |

### Conclusión actualizada
- **Trade Republic**: PDF Tax Report es la fuente perfecta — ya calcula FIFO según normativa española, incluye casillas pre-asignadas. Parser PDF con pdfplumber.
- **IBKR**: CSV o Flex Query XML. `ibflex` para XML, csv nativo para CSV.
- **DEGIRO**: CSV manual de su plataforma (Transacciones + Cuenta)
- **Validación cruzada**: Los cálculos de TR se usan para validar nuestro propio motor FIFO

---

## Arquitectura propuesta

```
FinView/
├── backend/               # Python — FastAPI
│   ├── main.py            # Entrypoint FastAPI + uvicorn
│   ├── config.py          # Settings (env vars, paths DB)
│   ├── models.py          # SQLAlchemy/Pydantic models
│   ├── database.py        # SQLite (dev) → PostgreSQL (prod)
│   ├── connectors/        # Broker connections
│   │   ├── base.py        # ABC BrokerConnector
│   │   ├── ibkr.py        # IBKR Flex Query API + ibflex parser
│   │   ├── degiro.py      # degiro-connector + CSV fallback
│   │   └── tr.py          # Trade Republic CSV parser
│   ├── importers/         # File import logic (CSV + PDF)
│   │   ├── base.py        # ABC Importer
│   │   ├── ibkr.py        # IBKR Activity Statement CSV/XML
│   │   ├── degiro.py      # DG-Transactions + DG-Account CSVs
│   │   └── tr.py          # TR Tax Report PDF parser (pdfplumber)
│   ├── fiscal/            # Motor fiscal español
│   │   ├── fifo.py        # FIFO lot matching (cross-year, cross-broker)
│   │   ├── tax_engine.py  # Cálculo IRPF casillas
│   │   └── export.py      # Exportar declaración (PDF/JSON)
│   ├── api/               # FastAPI routers
│   │   ├── portfolio.py   # GET positions, P&L, allocations
│   │   ├── import_.py     # POST upload CSV / trigger API sync
│   │   ├── fiscal.py      # GET tax summary, casillas, export
│   │   └── auth.py        # Simple auth (JWT/session)
│   └── tests/             # pytest
│       ├── test_parsers.py
│       ├── test_fifo.py
│       ├── test_tax.py
│       └── conftest.py
├── frontend/              # Next.js 15 + Tailwind + shadcn/ui
│   ├── app/
│   │   ├── page.tsx       # Dashboard principal
│   │   ├── portfolio/     # Posiciones, gráficos
│   │   ├── import/        # Upload CSVs, sync APIs
│   │   ├── fiscal/        # Vista fiscal, casillas IRPF
│   │   └── settings/      # Config brokers, API keys
│   └── components/
│       ├── charts/        # Recharts / Tremor
│       ├── tables/        # TanStack Table
│       └── ui/            # shadcn components
├── data/                  # Archivos broker reales (gitignored)
│   ├── degiro/
│   ├── ibkr/
│   └── tr/
├── tasks/                 # Planes y tracking
├── pyproject.toml
├── package.json
└── README.md
```

### Stack técnico
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + Pydantic v2
- **DB**: SQLite (dev) con opción PostgreSQL (prod)
- **Frontend**: Next.js 15 + TypeScript + Tailwind CSS + shadcn/ui
- **Charts**: Recharts o Tremor para visualización
- **Broker APIs**: `ibflex` (IBKR), `pdfplumber` (TR PDF), csv nativo (DEGIRO)
- **Testing**: pytest (backend), Vitest (frontend)

---

## Mejoras vs OptionsAI

| Problema en OptionsAI | Solución en FinView |
|----------------------|---------------------|
| parsers monolíticos, difícil de testear | Importers modulares con ABC + tests unitarios por parser |
| FIFO frágil (posicional matching opciones) | FIFO robusto con lot tracking explícito y tests |
| DB init con indexes antes de tablas | SQLAlchemy migrations (Alembic) |
| realized_pl precalculado en parser (a veces 0) | P&L SIEMPRE calculado por el FIFO engine, nunca por el parser |
| Sin conexión API a brokers | IBKR Flex Query nativo, DEGIRO CSV, **TR PDF parser nativo** |
| Flask monolito | FastAPI con routers separados, async, OpenAPI docs |
| Sin frontend real | Next.js dashboard con gráficos interactivos |
| Withholdings country siempre 'US' | Parser IBKR extrae país del ISIN/description |

---

## Fases de desarrollo

### Fase 1 — Core (MVP funcional)
- [ ] Scaffold proyecto (backend FastAPI + frontend Next.js)
- [ ] Modelos DB (accounts, transactions, lots, positions, dividends, withholdings, tax_results)
- [ ] **TR PDF parser** (pdfplumber): extraer secciones I, III, V, VI, VII, VIII del Tax Report
- [ ] DEGIRO CSV parser (reutilizar lógica buena de OptionsAI)
- [ ] IBKR CSV parser (reutilizar lógica buena de OptionsAI)
- [ ] FIFO engine con tests exhaustivos (validar contra cálculos de TR)
- [ ] Tax engine (casillas IRPF) con tests
- [ ] API endpoints: upload, portfolio, fiscal
- [ ] Frontend: dashboard básico con posiciones y P&L

### Fase 2 — Conexiones API
- [ ] IBKR Flex Query connector (token + query_id → auto-import)
- [ ] DEGIRO connector (degiro-connector lib) con fallback CSV
- [ ] Sync automático programado (cron/background)

### Fase 3 — Dashboard completo  
- [ ] Gráficos: evolución patrimonio, allocation por sector/país
- [ ] Vista fiscal interactiva con drill-down por casilla
- [ ] Exportación declaración IRPF (PDF)
- [ ] Multi-año: comparativa 2024 vs 2025 vs ...

### Fase 4 — Polish
- [ ] Auth (multi-usuario si se quiere compartir)
- [ ] Deploy (Docker compose, opción cloud)
- [ ] Notificaciones (dividendos próximos, vencimientos opciones)
- [ ] Open Banking si algún día cubra inversiones

---

## Archivos de datos disponibles

Los datos reales están en:
- **Trade Republic**: `/Users/brais/Downloads/FinView/Tax Report 2024.pdf` (PDF Tax Report - FUENTE PRINCIPAL)
- **DEGIRO CSVs**: `/Users/brais/VSCODE/OptionsAI/files/DG-Transactions-202{4,5}.csv` + `DG-Account-202{4,5}.csv`
- **IBKR CSVs**: `/Users/brais/VSCODE/OptionsAI/files/IBKR-U11040354_2024_2024.csv` + `U11040354_2025_2025.csv`

Se copiarán a `FinView/data/` (gitignored) para desarrollo.

## Trade Republic PDF — Estructura detallada (45 págs)

| Sección | Páginas | Contenido | Datos extraíbles |
|---------|---------|-----------|-----------------|
| I. Rendimientos capital mobiliario | 4-12 | Dividendos detallados | ISIN, fecha, divisa, qty, precio, gastos, retención, tipo cambio, total EUR, casilla |
| II. Resumen rendimientos | 13 | Totales por categoría | Verificación |
| III. G/P patrimoniales | 15-24 | Compra+Venta pareadas | ISIN, fechas, qty, precios buy/sell, gastos, P&L, casilla 332/337, clasificación </>1 año |
| IV. Resumen G/P | 25 | Ganancias/Pérdidas totales | Ganancias <1a: 297.40€, Pérdidas <1a: -2,155.11€ |
| V. Retenciones detalladas | 26-28 | Por país | Ingresos, retención, tipo %, doble imposición |
| VI. Transacciones completas | 29-36 | TODAS las operaciones | Fecha, tipo, ISIN, qty, importe (sin P&L) |
| VII. Patrimonio 31/12 | 37-39 | Holdings al cierre | ISIN, qty, saldo medio Q4, valor 31/12, valoración fiscal |
| VIII. Modelo 100 | 40 | **Casillas pre-calculadas** | C27=1,529.64€, C29=5,301.02€, C332=297.40€, C337=-2,155.11€ |
| IX. Modelo 714 | 41 | Patrimonio casillas | C05, C06, C08, C09 |

**Clave**: TR ya calcula FIFO según normativa española (sección 5.4 notas). Usamos sus resultados como ground truth para validar nuestro motor.
