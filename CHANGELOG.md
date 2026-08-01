# Changelog

All notable changes to FinView are documented here.

## [Unreleased]

### Retenciones y casillas IRPF

#### Fixed
- Las retenciones usan magnitudes positivas y separan el efectivo retenido, el pago a
  cuenta español (casilla 0597) y la retención extranjera. El estimador ya no resta la
  retención total como si toda fuese recuperable.
- La deducción por doble imposición (casilla 0588) solo usa el importe explícito del
  informe fiscal, queda limitada por la cuota y por el tipo efectivo sobre la renta
  extranjera, y no puede crear una devolución por sí sola.
- Los intereses, derechos y demás transacciones con retención entran en los totales;
  la comparativa anual incluye también ejercicios con datos manuales.
- Las casillas 0328 y 0380 del formato 2025 participan en ganancias y pérdidas. La
  validación contra Trade Republic deja de mostrar coincidencias tautológicas cuando
  no existe un cálculo independiente.

#### Migration
- `transactions` incorpora `domestic_withholding_tax` y
  `foreign_withholding_tax` mediante migración aditiva. Las filas antiguas conservan
  el efectivo retenido, pero el estimador avisa y no adivina el desglose; hay que
  reimportar el informe para recuperarlo.

#### Verification
- Suite backend completa, Ruff y TypeScript limpios.

### Corrección de cartera y valoración

#### Fixed
- La cartera conserva la actividad posterior al último snapshot y reconoce un
  snapshot anual vacío como cierre válido de posiciones anteriores.
- Las ventas consumen el coste de los lotes FIFO en vez de reducir un coste medio;
  los `SPINOFF` mantienen la cantidad con coste desconocido.
- Un coste desconocido en cualquier cuenta ya no se convierte en una ganancia ficticia:
  el total invertido y la rentabilidad quedan explícitamente sin calcular.
- Un ticker compartido por varios ISIN recibe precio para todos ellos, `.SI` se
  convierte desde SGD y los ceros reales se conservan en API y UI. Si falta el
  precio de una posición, el total de mercado no publica una suma parcial.

#### Migration
- `import_records.portfolio_snapshot_complete` distingue los informes que contienen
  un snapshot de cartera autoritativo, incluido uno vacío. Se añade de forma
  idempotente y sin reinterpretar importaciones históricas.

#### Verification
- 401 tests backend pasados, 131 omitidos; Ruff, TypeScript y build de producción limpios.

### Integridad residual de costes y FIFO

#### Fixed
- Crear, editar, eliminar o reemplazar una operación histórica recalcula el FIFO del
  año afectado y de todos los ejercicios posteriores con ventas. Al desaparecer la
  última venta también se limpian los lotes y ajustes obsoletos.
- Las compras manuales y de DEGIRO capitalizan comisiones; las ventas descuentan
  comisiones. Los `TaxLot` de DEGIRO usan el resultado fiscal después de comisión e
  impuesto de transacción.
- Las asignaciones IBKR conservan varias patas del mismo subyacente y fecha, fallan si
  el emparejamiento es ambiguo y aplican la prima una sola vez: PUT reduce el coste de
  las acciones adquiridas y CALL aumenta el importe de las acciones vendidas.
- Los spin-offs sin coste conocido participan en la cronología por cantidad. Si una
  venta alcanza uno de esos lotes, el motor no publica un ajuste parcial y crea un
  aviso `fifo_missing_cost_basis`; el supervisor mantiene por separado el aviso
  fuente `missing_cost_basis` mientras el coste siga sin conocerse. Ese aviso permite
  introducir el coste por acción y recalcula la cronología dependiente al resolverlo.
- Los lotes de auditoría conservan seis decimales; ganancias y pérdidas se agregan por
  ISIN/casilla y solo entonces se redondean a céntimos con `ROUND_HALF_UP`.
- Las mutaciones fiscales concurrentes se serializan por usuario en PostgreSQL y los
  reemplazos por usuario/bróker/año se bloquean desde la comprobación de duplicados
  hasta el commit. El CRUD manual rechaza cantidades, precios, tipos y costes inválidos.

#### Operations
- No hay migración de esquema. Para corregir datos históricos ya persistidos es
  necesario reemplazar/reimportar los informes DEGIRO e IBKR afectados.
- El reemplazo elimina e inserta dentro de la misma transacción y ejecuta un único
  recálculo desde el año más antiguo afectado.

#### Verification
- 453 tests backend pasados, 131 omitidos; Ruff limpio. Validado además contra los
  extractos reales DEGIRO 2024 e IBKR 2024.

### Corrección fiscal FIFO cross-broker (#185)

#### Fixed
- El motor FIFO ahora consume ventas históricas antes de calcular el ejercicio objetivo
  y rechaza compras posteriores a la venta. ISIN vacíos e inventario incompleto no
  generan lotes o ajustes autoritativos.
- Las comisiones de IBKR aumentan el coste de compra y reducen el importe de venta.
- Los ajustes se calculan por separado para ganancias (332) y pérdidas (337), incluso
  cuando el P&L neto del ISIN no cambia, y se aplican coherentemente en casillas,
  resumen, estimador, dashboard, exportación y comparativa anual.
- La UI ya no suma dos veces el ajuste y muestra los deltas de cada casilla.

#### Migration
- `CrossBrokerLot` y `FIFOAdjustment` incorporan desglose/versionado mediante columnas
  nullable creadas de forma idempotente en startup. Las filas legacy se conservan pero
  no se aplican hasta recalcular o reimportar el ejercicio; no hay backfill automático.

#### Verification
- 375 tests backend pasados, 131 omitidos; Ruff, TypeScript y build de producción limpios.

### Cobertura de Ideas — cuencas de materia prima (#177)

#### Added
- **Tres regiones de materia prima con cuatro reglas** (#177) — `west_africa_cocoa`
  (Costa de Marfil + Ghana, ~60% del cacao mundial): sequía → `CC=F+ HSY- MDLZ-`
  (0.78) e inundación → misma cesta por podredumbre parda (0.62, el enlace más
  débil de los cuatro a propósito). `australia_pilbara` (Port Hedland, el mayor
  puerto exportador de hierro del mundo): ciclón → `BHP- RIO- VALE+` (0.80), el
  cierre de puerto quita volumen a los australianos y Vale gana con la oferta
  marítima más tensa. `lithium_triangle` (salmuera de Atacama/Puna): terremoto
  M≥6 → `LIT+ ALB+ SQM-` (0.74).
- Expansión **por tesis, no por cobertura de mapa**: cada añadido es región +
  regla + cesta con un enlace de mercado defendible. Nada de reglas de alta
  frecuencia y poco filo.

#### Notes
- **Las tres van sobre fuentes sin clave** (EONET+GDACS y USGS): no hacen falta
  variables de entorno nuevas. Se descartó a propósito una regla de helada en
  Brasil porque `extreme_cold` viene de **Windy** y sin `FINVIEW_WINDY_API_KEY` no
  dispararía jamás — en silencio. Queda diferida y condicionada a esa clave.
- **El solape con `chile_mining` es intencionado**: `match_regions` devuelve todas
  las cajas que contienen el punto, así que un terremoto en Atacama casa las dos
  reglas y lleva la tesis del cobre y la del litio a la vez. Está aseverado en
  tests para que quitarlo tenga que ser una decisión, no un descuido.
- Cambio puramente aditivo: sin migración, `seed_rule_stats` recoge los `rule_id`
  nuevos en el siguiente arranque. Recuentos: 89 → **93 reglas**, 46 → **49 regiones**.

### Signal architecture (PRs #148–#156)

Cada sección de mercado pasa a tener **una capa**: Zonas Clave dispara (técnico),
Options Monitor ejecuta (PUT/CALL), Ideas razona (tesis). Los enlaces cruzan la
frontera; el contenido no.

#### Fixed
- **Los ciclos del agente de opciones no corrían en producción** (#148). El
  `APScheduler` en proceso muere en cada scale-to-zero de Cloud Run, así que el
  agente solo se ejecutaba al pulsar el botón manual. Con `/options/alerts`
  filtrando a 7 días, el tab Monitor llevaba tiempo leyendo vacío sin ningún
  error visible. Nuevo `POST /api/options/agent/cron` + job de Cloud Scheduler.
- **Un ticker en dos brókeres renderizaba dos filas idénticas** en la Cartera de
  opciones (#149): las filas se indexaban por `(isin, broker)` en vez de por
  ticker. Con FIFO cross-broker era alcanzable de verdad.
- **`/geo-intel` ignoraba `?ticker=`** (#150) pese a que los enlaces entrantes lo
  asumían.
- **El scorer de zonas fallaba en todas las llamadas** (#156). El LLM devolvía 200
  con `content: null` y `json.loads(None)` lanzaba. Falló seguro
  (`break_probability` NULL, sin alertas, sin datos falsos) pero en silencio.

#### Added
- **Señales técnicas** (#153, #154) — Zonas Clave emite por fin. Puerta de
  proximidad determinista (2%) → scorer LLM solo sobre candidatos →
  `TechnicalSignal`. Se persisten **todos** los candidatos puntuados; solo alertan
  los >70. Ese corte **no está calibrado** y guardar los sub-umbral es la única
  forma de comprobarlo luego. `break_probability = NULL` significa "sin puntuar",
  nunca 0. Nuevos `POST /api/zonas-clave/cron` y `GET /zonas-clave/signals`.
- **El Monitor es el hub de alertas** (#150, #154) — tres vistas (Alertas, Smart
  Money, Técnico) y chips por alerta hacia la sección relevante. El chip de Ideas
  solo aparece si ese ticker tiene señal geo activa: un enlace a una página vacía
  es peor que ninguno.
- **Fundamentales en Ideas** (#155) — `GET /charts/fundamentals` (yfinance `.info`,
  caché 6h) + botón "Añadir a Zonas Clave" en los tickers recomendados. Los
  fundamentales son **contexto para una tesis humana, jamás entrada de señal,
  score o gate**.

#### Changed
- **Cartera y Watchlist fusionadas** en una lista (#149). Las posiciones ya se
  auto-sincronizaban en la watchlist: las dos tabs enseñaban los mismos tickers.
  El borrado es asimétrico a propósito — los tickers en cartera solo tienen
  "Ocultar", porque un borrado normal lo deshace la sincronización.
- **Geo-Intel → "Ideas"** (#148). Solo la etiqueta de UI: la ruta `/geo-intel`, la
  tabla `geo_signals` y el prefijo de API se mantienen (renombrar la ruta rompe
  deep links; renombrar tablas es DDL en prod sin Alembic).
- **Las zonas se detectan sobre 10 años, no 20** (#153). Los 20y venían de un
  commit de *gráficos* (el scope MAX los necesita) y la detección los heredó. Ahora
  son dos ventanas de una misma descarga. La mediana de volumen se recorta también:
  es el denominador de `vol_score`, y a 20y infravaloraba las zonas actuales
  (SAN.MC: 62.5M vs 43.5M).
- **`max_tokens` del scorer 200 → 500** (#156), igualando el valor que geo usa con
  el mismo modelo sin fallar nunca.

#### Removed
- `InstrumentDrawer` y `app-sidebar.tsx` (#151), y con ellos `ZonasTab`,
  `FiscalTab`, `DividendosTab` y `usePositionDetail` (#152). La página
  `/ticker/[symbol]` para la que se guardaban queda **descartada**: mezclar fiscal
  + opciones + zonas de un ticker es lo contrario de "cada página, una capa".
- El card de Opciones en Zonas Clave (#148).

#### Docs
- `claude.md` documentaba el stack de IA como anthropic SDK / claude-haiku cuando
  todo va por **OpenRouter + deepseek-v4-flash**; el mismo error estaba en README,
  admin-guide y la tabla de env vars. Las variables del README además iban **sin el
  prefijo `FINVIEW_`**, así que copiarlas dejaba las notificaciones muertas en
  silencio.
- `docs/deployment.md` no mencionaba **Cloud Scheduler** — el mecanismo del que
  depende que los tres pipelines corran. Añadido, con el orden de rotación del
  secreto y los síntomas de que falte un job.
- Recuentos de tests corregidos (151/255 → 369 backend + 18 frontend).


### Security
- **Startup secret validation** — `FINVIEW_ENV=production` now enforces that
  `FINVIEW_SECRET_KEY` and `FINVIEW_AUTH_SECRET` are non-default at boot.
  Default env is `local` so local dev is unaffected.
- **Removed `user_id or 1` fallback** — missing `user_id` in import service and
  FIFO engine now raises `IntegrityError` instead of silently writing to user 1.
- **Removed ORM `default=1`** on `TaxResult.user_id` and `FIFOAdjustment.user_id`.
- **Auth rate limiting** — `/auth/login` 5 req/min per IP, `/auth/register`
  3 req/min. Thresholds configurable via `FINVIEW_RATE_LIMIT_LOGIN` /
  `FINVIEW_RATE_LIMIT_REGISTER`. Uses rightmost `X-Forwarded-For` entry behind
  Cloud Run (unspoofable by client).

### Added
- **Catalog search — NAV + fund size + sort/filter** — the `/alt-investments` CNMV
  search now enriches each fund with its latest **NAV per unit** and **fund size
  (AUM)** from the CNMV `FONDMENS` monthly file (same ZIP, no extra download). Results
  show NAV and fund size; you can **sort** by patrimonio/NAV and set a **minimum fund
  size**, and **browse** (e.g. largest funds) without typing a name. New `/search`
  params: `sort` (`fund_size_desc`|`nav_desc`|`nav_asc`), `min_fund_size`,
  `max_fund_size`. NAV/size are the only fields any free Spanish source publishes — PE
  metrics (DPI/TVPI/IRR/vintage/commitment/hurdle) remain manual on positions. NAV/size
  columns added to `alt_investment_catalog` via the `ensure_columns()` additive migration.
- **Alt-investments search (CNMV)** — a search bar at the top of `/alt-investments`
  finds regulated Spanish investment funds by name or ISIN and pre-fills the add
  form (name, type, gestora, ISIN). Backed by a new `alt_investment_catalog` table
  populated from the free CNMV "información individual de IIC" monthly registry
  (`services/cnmv_catalog.py`): ~3,000 share-class ISINs across ~1,400 funds,
  refreshed in a background thread on startup when stale (>7 days). Endpoint
  `GET /alt-investments/search?q=&type=`. Amounts stay manual — the catalog only
  supplies identity. (SICAVs, real-estate IICs, hedge funds and PE/VC live in
  separate CNMV registries — deferred to later slices.)
- **Additive column migration on startup** — `database.ensure_columns()` adds
  columns to tables that already exist in production (which `create_all` cannot
  alter), starting with `alt_investments.isin`. Idempotent, dialect-safe.
- **Alternative investments tracker** — new `/alt-investments` page and
  `/api/alt-investments` endpoints to manually track private-banking positions
  (Private Equity, Venture Capital, Real Estate, Hedge Fund, Structured Product,
  Other). Stores committed/called/distributed/NAV aggregates per position and
  derives the standard PE metrics — TVPI, DPI, RVPI, unfunded commitment — plus
  a `/summary` consolidation with NAV-weighted allocation by type, geography and
  currency. UI has summary cards, allocation bars, a positions table and an
  inline add/edit form. Migrated as an MVP from the OptionsAI "coming soon" spec.
- **ECB exchange-rate service** — `services/exchange_rates.py` caches official
  ECB EUR reference rates in a new `exchange_rates` table as an IRPF fallback for
  when a broker file omits the rate or for manual entries. Syncs in a background
  thread on startup (full history first boot, then 90-day feed, skipped if
  fresh); `get_rate()` is DB-only with ±7-day weekend/holiday fallback. Lookup
  via `GET /fiscal/fx-rate?currency=USD&on=YYYY-MM-DD`. Ported from OptionsAI.
- **User-visible error states** on all 5 main pages (dashboard, portfolio,
  options, zonas-clave, billing) with inline Retry buttons. Previously all fetch
  errors were swallowed silently to the console.
- **Dashboard loading skeleton** now shows on every year-filter change, not only
  on first mount.
- **Options monitor — Análisis tab** — new 6th tab in `/options` that renders
  the last Claude analysis cycle as 7 structured section cards (Resumen
  Ejecutivo, Smart Money, Señales Greeks, Top Picks, Catalizadores, Contexto
  MEFF, Gestión de Riesgo) plus a cycle metadata header (timestamp, tickers
  analyzed, total alerts, sentiment). Powered by `GET /options/agent/last-analysis`.
- **Historical Volatility for MEFF tickers** — `.MC` tickers now compute HV
  from 60 days of yfinance price history (`log(Close/Close.shift(1)).std() ×
  √252 × 100`) since MEFF HTML does not publish HV. Previously HV was `None`
  for all MEFF tickers.
- **`GET /options/agent/last-analysis`** — new endpoint returning the most
  recent agent cycle metadata and the full Claude markdown analysis for the
  authenticated user.

### Performance
- `GET /accounts/` — eliminated 2N lazy-load queries; now 3 queries (was 1 + 2N).
- `GET /fiscal/yearly-comparison` — collapsed 6 queries × N fiscal years into
  2 GROUP BY queries (was 1 + 6N).
- `GET /zonas-clave/analysis` — eliminated 1 query per watchlist item; now 1
  query with subquery (was 1 + N).

### Housekeeping
- Declared `pandas>=2.0` as an explicit dependency — used directly in
  `zonas_clave_analyzer.py` but previously only present as a transitive dep of
  `yfinance`.
- Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)` — 12
  ORM column defaults in `models.py` and 1 call site in `zonas_clave_analyzer.py`
  (Python 3.12 deprecation).
- Removed 4 unused imports: `sqlalchemy.orm.Session` (`auth.py`),
  `dataclasses.field` and `TaxResult` (`fifo_engine.py`), `CasillaOut`
  (`fiscal.py`).
- **`.githooks/pre-commit` asset-refs guard** — blocks a commit that introduces
  a new dangling image reference in blog MDX (markdown `![](./x.png)` relative
  to the `.mdx` dir, or `<img src="/x.png">` → `frontend/public/x.png`). Closes
  the gap where the article-generation cron commits an MDX but not the
  infographic it points at; a missing ES `import` is already caught by the
  existing `pre-push` build check. Pre-existing breakage is baselined in
  `.githooks/asset-refs-baseline.txt`; only new breakage fails. Enable locally
  with `git config core.hooksPath .githooks` (agent clones get it automatically
  via the Hermes managed git-guard).
