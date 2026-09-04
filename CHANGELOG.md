# Changelog

All notable changes to FinView are documented here.

## [Unreleased]

### Ideas (geo-intel) volvía a estar muerta — 2026-09-04

La sección llevaba seis semanas sin una señal nueva y sin un solo error a la vista.
Eran dos fallos independientes, y cada uno bastaba por sí solo.

#### Fixed
- **Un evento que reaparecía tras resolverse tumbaba el ciclo entero, para siempre.**
  `geo_signals` era UNIQUE por `(user_id, source, external_id)` sobre toda la tabla,
  pero el advisor solo deduplica contra señales **ACTIVE** porque el auditor resuelve a
  +7d. Las fuentes no rotan sus ids —un evento de EONET sigue abierto durante meses y
  `wx-*`, `ais-*`, `fire-cluster-*` y `*-escalation-*` van por región—, así que la
  primera reaparición lanzaba `IntegrityError` dentro del `flush` de `generate_signal`.
  El ciclo moría **antes** de la fase del auditor: ni señales nuevas ni resoluciones
  nunca más, con `/geo/cron` devolviendo 200. Ahora el índice dice lo que el código
  quería decir: único **parcial** sobre `status='active'`. Una señal resuelta puede
  volver a seguirse como fila nueva; dos ACTIVE del mismo evento siguen siendo
  imposibles. Cada señal se escribe en su propio SAVEPOINT, así que un fallo cuesta una
  señal y no el ciclo, y el auditor corre aunque la escritura falle.
- **Cada despliegue dejaba producción sin periodicidad.** El paso de tráfico de
  `cloudbuild.yaml` pausa `geo-intel-cycle`, `options-agent-cycle` y `zonas-clave-cycle`
  antes de mover tráfico y **nada los reanudaba**: el build terminaba en verde con los
  tres en `PAUSED` y los tres pipelines callados. La reanudación es ahora un `trap ...
  EXIT` —cubre promoción, rollback y build superseded— y el build falla si algún job no
  vuelve a `ENABLED`. `test_cloudbuild_policy` exige el par pausa/reanudación sobre la
  misma lista de jobs.

#### Added
- `geo_cycle_runs`: una fila por ciclo (ok/error, eventos por fuente, señales nuevas,
  descartes al guardar; se podan a 7 días). `GET /geo/scheduler/status` la devuelve como
  `last_run`. La fecha de la última señal no distingue un pipeline parado de una semana
  tranquila, y esa ambigüedad es justo lo que dejó a Ideas muerta seis semanas.
- Línea de estado en la cabecera de `/geo-intel`: nunca ejecutado / última ejecución
  fallida con su error / demasiado antigua / **ninguna fuente devolvió nada** (corte de
  red o claves, nunca un día tranquilo) / señales descartadas / sano con lo que ingirió.
  La lógica vive en `lib/geoHealth.ts`, pura y con tests.
- "Run cycle" dice qué hizo el ciclo ("0 eventos" separa un problema de ingesta de un día
  sin coincidencias) y muestra el error en vez de tragárselo.

#### Changed
- `POST /geo/cron` responde **500** cuando hay usuarios y ningún ciclo termina. Antes
  devolvía 200 "done" sobre un pipeline que fallaba en todas las llamadas, así que Cloud
  Scheduler registraba éxito indefinidamente.

### Auditoría completa: arquitectura, UX, diseño y refactorización — 2026-08-26

Barrido de la aplicación a todos los niveles (#210–#223). Lo que sigue son los
cambios con consecuencias, no la lista de PRs.

#### Fixed
- **El índice del blog enlazaba a dos artículos que nunca existieron** (404 en
  producción) y ocultaba otros dos que sí existían pero no tenían tarjeta. El array
  estaba mantenido a mano sin nada que lo atara a `app/blog/`. `blogPosts()` ahora
  falla el build cuando el índice y el sistema de ficheros no coinciden, en cualquiera
  de los dos sentidos. Cinco entradas estaban además fuera de orden en una lista que
  dice ser cronológica; el orden sale ahora de `date`.
- **Un ticker resuelto se tiraba a la basura.** El supervisor buscaba el ISIN en
  yfinance, escribía la respuesta en la descripción de un `DataIssue` y nadie la volvía
  a leer: el precio seguía en `—` para siempre, la búsqueda se repetía en cada
  importación y la detección de splits —que recorre el mapa curado— ni veía el valor.
  Nueva tabla `ticker_map` con precedencia `manual > CURATED > yfinance`.
- **El límite de importaciones del plan no se aplicaba en ningún sitio.** Estaba en
  `PLAN_LIMITS`, lo devolvía `/billing/subscription` y se pintaba en Facturación, pero
  los seis endpoints de subida aceptaban ficheros al margen del plan.
- **El modo oscuro estaba construido y nunca se encendía**: `globals.css` definía el
  bloque `.dark` completo, `next-themes` era dependencia y `useTheme()` tenía consumidores,
  pero nadie montaba el provider. La paleta era además shadcn de serie —grises con
  primario azul— sobre un producto cuya identidad es tinta cálida y ocre.
- `get_optional_user` no tenía consumidores y era peligroso adquirir uno: a diferencia
  de `get_current_user` nunca comprobaba `is_active`, y devolvía `None` ante un token
  inválido en vez de 401.
- Los mensajes de error de la API estaban en inglés en una aplicación íntegramente en
  español (uno era las dos cosas a la vez: "Issue no encontrado"). 31 cadenas traducidas;
  las nueve de operador que quedan están listadas explícitamente.

#### Performance
- El supervisor de datos hacía trabajo por posición dentro de la petición de importación:
  una llamada a yfinance por ticker sin cache, dos agregados por holding y cuatro consultas
  por ISIN sin compra. Medido sobre el mismo banco de pruebas, 50 ISINs, segunda ejecución:
  **116 SELECT + 50 llamadas de red → 20 + 0** en una cartera sana, **266 + 50 → 22 + 0**
  cuando falta la compra de cada ISIN. Y plano de 5 a 50 posiciones en vez de lineal.
- Catorce índices de clave foránea añadidos (Postgres no los crea solos).

#### Added
- `split_history_cache` (TTL 30 días). Un fallo de Yahoo **no** se cachea: devuelve la
  entrada anterior y reintenta, porque guardar "sin splits" por un corte de red dejaría
  al supervisor ciego un mes. Un resultado vacío sí se cachea: es el caso común.
- Acción `set_ticker` en el resolutor de incidencias. Los avisos `missing_ticker` solo
  ofrecían "ignorar", que dejaba la posición sin precio y reaparecía en la siguiente
  importación.
- Guardas estructurales en test, todas verificadas rompiéndolas a propósito: toda ruta
  `/cron` lleva el secreto compartido y ninguna otra lo lleva; los seis endpoints de
  subida llevan la cuota; el coste en SELECT del supervisor no crece con la cartera;
  ninguna cadena de error de usuario está en inglés fuera de la lista de operador;
  ningún `.catch(() => {})` desnudo vuelve al frontend.
- Modo oscuro real, derivado del tono de marca con los contrastes calculados (el par más
  débil, óxido sobre `muted`, da 4.70:1 — AA), más el conmutador de cabecera.

#### Changed
- El chequeo del secreto de cron era el mismo bloque copiado en los tres endpoints. Ahora
  es una dependencia de ruta: un endpoint nuevo no puede olvidarlo y un test lo comprueba.
- `options/page.tsx` pasa de 2.457 a 1.630 líneas (`BacktestTab`, `AgentChat`,
  `AnalysisTab`, `useBacktest`). Watchlist y monitor siguen dentro a propósito: leen 26 y
  15 enlaces del componente, así que extraerlos es desenredar estado, no mover código.
- El blog pierde 9.928 líneas al compartir el shell de artículo: 58 layouts y 58 hojas de
  estilo casi idénticas.

#### Removed
- Diez scripts de un solo uso. Seis eran depuración de un cálculo de rentabilidad —tres
  con `/Users/brais/VSCODE/FinView` a fuego, así que no corrían en ninguna otra máquina—
  y cuatro correcciones de datos ya aplicadas, dos de ellas escribiendo en Neon.
- El workflow de GitHub Actions, que nunca podría ejecutarse en esta cuenta.

#### Notes
- **ARC-6 era un error del informe.** Los wrappers de APScheduler no están muertos: ambos
  endpoints de arranque devuelven 409 con `request_scoped_runtime` y el frontend desactiva
  el conmutador y lo etiqueta "Cloud Scheduler". Funcionalidad de desarrollo con su guarda
  de producción correcta; se deja como está.
- **UX-5 estaba exagerado.** Los once `.catch(() => {})` degradaban en silencio *a propósito*
  —cargan insignias, conmutadores y sugerencias—, y un cartel de error porque no carga una
  insignia sería peor que la insignia ausente. Lo que sí estaba mal es que un fallo
  persistente no dejaba rastro en ninguna parte: ahora pasan por `bestEffort(label)`.

### Endurecimiento de CI y guard de coste — 2026-08-05

#### Fixed
- El guard vuelve a exigir el máximo a nivel de servicio. En #198 se eliminó esa
  comprobación por una lectura incorrecta: la anotación faltaba porque el servicio
  estaba en escalado manual y pausado cuando se inspeccionó, no porque gcloud no la
  escriba. `--max` sí la escribe.
- El guard rechaza el escalado manual (`run.googleapis.com/scalingMode: manual`), que
  anula `minScale`/`maxScale` y permitía mantener instancias vivas mientras las
  anotaciones leídas seguían pareciendo seguras.
- `cloudbuild.yaml` vuelve a fijar los dos ámbitos de escalado. `--min`/`--max` son
  de servicio y `--min-instances`/`--max-instances` de revisión: no son alias, y el
  límite efectivo es el menor de los dos. Al dejar de pasar `--max`, el máximo de
  servicio quedó sin fijar y `--scaling=auto` lo dejó en 3 mientras la revisión seguía
  en 1. El guard lo detuvo antes de mover tráfico.

#### Added
- La suite backend corre en Cloud Build **antes** de publicar la imagen, dentro del
  contenedor recién construido y con `/workspace` montado. Hasta ahora nada bloqueaba
  un commit roto: el único workflow de GitHub es la revisión con IA y el smoke test
  solo probaba que el proceso arranca.
- `test_cloudbuild_policy` localiza los pasos por contenido en lugar de por índice, así
  que insertar un paso ya no reapunta las aserciones a otro.

#### Operations
- Causa raíz del gasto de julio: el crédito de prueba venció el 18/07/2026 con €224.32
  sin usar. El derroche de facturación por instancia existía desde finales de junio,
  pero el crédito lo absorbía (1–17 jul: €26.08 de uso, €0.00 facturados).
- Los tres jobs de Scheduler estaban `ENABLED` y fallando, no `PAUSED` como decía la
  documentación. `geo-intel-cycle` pasa a `*/30` para caber en la capa gratuita y los
  tres exigen `--attempt-deadline=1800s` y `--max-retry-attempts=0`.

### Cloud Run cost and deployment safety — 2026-08-01

#### Fixed
- Cloud Run no longer uses instance-based billing for `finview-api`; scheduled and
  manual work completes inside the HTTP request so scale-to-zero is reliable.
- Backend deploys now use a private zero-traffic candidate, startup readiness, automatic
  traffic rollback, explicit `PORT=8080` smoke testing, and min/max cost guards.
- Production startup rejects request-unscoped runtimes and ephemeral SQLite.
  Deterministic revisions and supersession checks prevent stale builds from changing
  traffic; rollouts pause periodic callers and leave resumption explicit.
- In-process production schedulers and daemon workers are disabled by
  `FINVIEW_REQUEST_SCOPED_RUNTIME=true`; local development keeps existing behavior.

#### Operations
- Root cause documented: the failed revision exited while Neon was over compute
  quota; Cloud Run's port message was secondary. Continuous billing came from
  instance billing plus Scheduler requests every 10 minutes, not a revision loop.

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
