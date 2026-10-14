# FinView — Dashboard de Inversiones con Brokers Reales

## Seguimientos del 2026-10-14 (token caducado, cron perdido, ruff)

Origen: tras desplegar el PR #342 todas las secciones fallaban con 401. No era el deploy: el JWT
del backend caduca a los 90 días del login y nunca se renovaba, mientras la cookie de NextAuth se
prorroga sola; el PR #343 cierra sesión cuando el reintento sigue en 401. Al leer los logs salió
además que el cron de opciones de las :00 se perdía cuando coincidía con el ciclo geo (429 "no
available instance", 3 veces en un mes) y que los jobs no tenían reintentos.

### Renovar el token antes del día 90 (rama `feat/token-refresh`)
- [x] `POST /api/auth/refresh`: con un token válido y usuario activo devuelve uno nuevo de 90 días.
      Sesión deslizante, como la cookie; tests para token caducado y usuario inactivo.
- [x] `src/lib/tokenExpiry.ts` (puro, con vitest): `decodeExp` y `shouldRefresh`; `api.ts` lo reutiliza.
- [x] `auth.ts` (callback `jwt`): si quedan < 7 días, pide un token nuevo al backend y lo guarda en la
      cookie; si falla, conserva el viejo y no reintenta durante una hora.
- [x] Docs: `CLAUDE.md` (bullet de `request()`), `.claude/rules/auth-security.md`.

### Cron de opciones (config de Cloud Scheduler, sin código)
- [x] `options-agent-cycle` pasa a `5,35 7-22 * * 1-5` (fuera del minuto :00 del ciclo geo) con 2
      reintentos (60–120 s). Los jobs geo se quedan como están: su 500 es una señal a propósito.
- [x] Docs: `.claude/rules/options.md`, `docs/deployment.md`.

### Ampliar ruff (rama `chore/ruff-widen-rules`, subagente Sonnet en worktree)
- [x] `B`, `C4`, `SIM`, `PERF`, `RUF015`, `RUF100` en `pyproject.toml`, árbol limpio, suite en verde.

### Tipo `Position` de opciones
- [x] `avg_cost_eur`/`total_cost_eur` pasan a `number | null`, que es lo que devuelve el backend
      (el único consumidor ya comprueba null).

### No se hace, y por qué
- `fifo_engine` (~4 consultas por ISIN multibroker y año): fichero más sensible; regla explícita.
- Memoizar `get_open_positions`: hace falta una huella del ledger como clave; es una decisión de
  diseño sobre números fiscales, y para el tamaño actual del ledger el replay cuesta milisegundos.

## Optimizar y factorizar — 2026-10-14 (rama `refactor/factorize-fiscal-imports`)

Punto de partida (inventario con tres subagentes Haiku + ruff ampliado): `fiscal_summary`
lanzaba ~15 consultas donde bastan 6 (la de ingresos manuales 4 veces, el barrido anual de
transacciones 2 veces, porque llamaba al endpoint `list_casillas` por dentro); `yearly_comparison`
hacía 3 consultas por ejercicio; cinco rutas de subida en `imports.py` eran copias; `_norm_cdf` /
`_norm_pdf` estaban duplicadas en `options_scraper.py` y `greeks_calculator.py`; la página de
registro llamaba a `fetch` directo saltándose `request()`; `LastAnalysis` estaba tipado dos veces.

### Backend
- [x] `fiscal.py`: cargar manuales, FIFO y retenciones una vez por (usuario, año) y pasarlos a
      `list_casillas`/`fiscal_summary`/`savings_estimate`; un `GROUP BY` en vez de 5 `_sum_casilla`;
      el barrido de retenciones proyecta columnas y filtra filas sin retención ni crédito;
      `yearly_comparison` pasa de 3 consultas por año a 3 en total.
- [x] Test que fije el número de consultas de `fiscal_summary` (que no vuelva a crecer en silencio).
- [x] `imports.py`: una función para las cinco rutas de un solo fichero (sufijo → spool → import → unlink).
- [x] `options_scraper.py`: importar `_norm_cdf`/`_norm_pdf` de `greeks_calculator.py`.

### Frontend
- [x] `register/page.tsx` pasa por `send()` de `src/lib/api.ts` (regla: nunca `fetch` directo a `/api/*`).
- [x] `LastAnalysis` exportado desde `api.ts`, `AnalysisTab.tsx` lo importa; `macro` reutiliza `GeoMacro`.

### Verificación
- [x] `pytest` completo, `ruff`, `pnpm test`, `tsc`, `pnpm lint`, `pnpm build`.
- [x] Docs: conteos de tests en `CLAUDE.md` / `README.md` / `ci.yml` si cambian.

### Revisión adversarial (subagente Sonnet, fuzz diferencial viejo/nuevo: 0 diferencias)
- [x] `fix(api)`: un 429 de slowapi devolvía `{"error": ...}` en inglés y el formulario de registro lo
      mostraba tal cual; ahora `services/rate_limit.rate_limited` responde `detail` en castellano.
      `apiError` colapsa una página HTML de error a `Error <status>`.
- [x] `fix(fiscal)`: el dashboard con `fiscal_year=0` volvía a leerse como "todos los años"; test que
      fija cada rama del filtro SQL de retenciones (crédito, desglose nacional, desglose extranjero).
- `main` se fusionó en la rama; conteos medidos: 1428 backend (148 skip sin `files/`), 149 frontend.

### Aplazado (medido, no tocado)
- `portfolio_service.get_open_positions` rehace el FIFO completo en cada llamada (5 sitios): memoizar
  exige decidir la clave de invalidación del ledger — decisión de diseño, no refactor.
- `fifo_engine.recalculate_cross_broker_fifo`: ~4 consultas por ISIN multibroker y año. Fichero más
  sensible del repo; fuera de alcance.
- Ampliar `ruff` (B/SIM/C4/PERF/RUF100): 10 `B904`, 10 `noqa` huérfanos, 7 `B023` falsos positivos en
  `sentinel.py` (los cierres se invocan en la misma iteración), 185 `UP017`. `pyproject.toml` pide que
  vaya en su propio PR con el diff adjunto.
- Frontend: 18 sitios `${fmt(x)} €` en vez de `formatEur` (cambia el espacio por NBSP), `Position`
  duplicado en `options/types.ts` y `portfolio/types.ts` (difiere la nulabilidad del coste), tarjetas
  de error con "Reintentar" en `MonitorTab`/`WatchlistTab` que podrían usar `ErrorState`.

## Ideas: país, más activos y escalera local → nacional → internacional — 2026-10-04 (rama `feat/geo-country-tier`)

Punto de partida: 84 reglas escritas a mano sobre 54 símbolos (USO, GLD, LMT, ZIM, DAC y XLE
llevan el 43 % de los enlaces), solo 7 países con instrumento nacional y ningún evento sabe
en qué país está: un terremoto fuera de las 49 cajas se descarta antes de llegar a una regla.
Plan aprobado en `~/.claude/plans/we-need-to-improve-merry-chipmunk.md`.

Hallazgo al verificar las fuentes (2026-10-04): **GDACS llevaba devolviendo 400** — el
endpoint `geteventlist/MAP` ahora exige `eventtype` — y como comparte contador con EONET
nadie lo veía. Sin GDACS ningún evento natural tenía severidad. Se arregla en esta rama
porque las plantillas de ciclón e inundación dependen de esa severidad.

### Fase 1 — país, nivel nacional y filtro por país
- [x] `fix(geo)`: GDACS por `SEARCH` con ventana de fechas; país(es) afectados en `NaturalEvent`.
- [x] `services/geo/countries.py`: tabla de países (FIPS de GDELT, ISO3 de GDACS, nombres de USGS, ETF del país) e `INSTRUMENT_COUNTRY`.
- [x] Ingesta: columna 53 de GDELT, alerta PAGER de USGS.
- [x] `GeoEvent.country` en el sentinel; terremotos y GDACS naranja/rojo pasan sin caja si el país está cubierto.
- [x] `rules.py`: plantillas (`tpl-<categoría>-national`), `resolve_rule`, `instrument_tier`, `allowed_symbols`, `fetch_order`.
- [x] `analyst.py`: plantilla solo si no hay regla escrita; las dos rutas del LLM limitadas al universo permitido para el evento.
- [x] Orden de descarga de precios (símbolos de siempre primero); señal de plantilla sin precio no se crea.
- [x] `geo_signals.country` + API (`country`, `tier`) + tipos y panel del frontend (chips agrupados por nivel).
- [x] Tests nuevos y ampliados; `pytest`, `ruff`, `vitest`, `tsc`, `build`.
- [x] Docs: `.claude/rules/geo.md`, `CLAUDE.md` (conteos), cabecera de `rules.py`, decisiones.

### Fase 2 — plantillas junto a reglas escritas y nivel local
- [x] Auditor: lectura por pata y cada regla aprende de sus propias patas.
- [x] Mezcla: la plantilla añade patas pero no entra en confianza ni riesgo.
- [x] Hasta 2 empresas por país, por domicilio, cotizadas en EE. UU.

### Fase 3 — escalera
- [x] `ladder.py`: estado por nivel (pendiente / confirmado / contradicho / ilegible).
- [x] Lectura por pata guardada; aciertos por nivel y condicionados en `/geo/accuracy`.
- [x] Escalera en el panel: los grupos Local / Nacional / Internacional, cada uno con su lectura.
- Aplazado hasta poder medirlo: que un nivel confirmado suba la confianza del siguiente.

## Legal y cumplimiento (RGPD · LSSI-CE · consumo · MiFID/MAR · AI Act) — 2026-09-30 (rama `feat/legal-compliance`)

Punto de partida: ningún documento legal, registro sin consentimiento, el FAQ de precios
prometía borrar la cuenta y nada lo hacía, discapacidad (dato de salud) sin consentimiento,
copy de planes distinto de `PLAN_LIMITS`, señales de IA sin aviso. Mapa completo en
`docs/compliance/README.md`.

Datos del CEO (2026-09-30): titular **Biglobster LLC** (Nuevo México), contacto
hola@biglobster.top, y **no hay Stripe: FinView no se vende**. Los documentos describen un
servicio gratuito bajo ley de Nuevo México con las protecciones imperativas del consumidor de
la UE (misma cláusula que biglobster.top). Las cláusulas de contratación quedan en
`docs/compliance/planes-de-pago.md`.

Decisiones tomadas sin preguntar: sin banner de cookies (solo técnicas); email del usuario
fuera de `test-telegram`, las alertas de mercado al operador se mantienen porque no llevan
identidad; el prompt de opciones ya no pide tamaño de posición; `/pricing` conserva las
tarjetas de pago con un aviso de que no están a la venta.

### Documentos y avisos (frontend)
- [x] `src/lib/legal.ts`: Biglobster LLC, `LEGAL_UPDATED`, `PROCESSORS` (sin Stripe).
- [x] `/legal/aviso-legal`, `/legal/privacidad`, `/legal/cookies`, `/legal/condiciones` (MDX, shell del blog). Públicas en `auth.ts`, en `sitemap.ts`.
- [x] `PublicFooter` con los cuatro enlaces + aviso de no asesoramiento (cubre blog, precios, funcionalidades); footer añadido a la landing.
- [x] `AiDisclaimer` en Opciones, Zonas Clave e Ideas.
- [x] `/pricing`: planes = `PLAN_LIMITS`, aviso de que Pro y Unlimited no están a la venta, brókers reales, contacto hola@biglobster.top.

### Consentimiento
- [x] `users.terms_version` / `terms_accepted_at`; registro rechazado sin `accept_terms`; casilla sin premarcar en `/register`.
- [x] `POST /users/me/accept-terms` + `TermsBanner` en el dashboard para cuentas anteriores o versión nueva.
- [x] `fiscal_profiles.health_data_consent_at`: discapacidad solo con casilla de consentimiento expreso; borrar el campo lo retira.
- [x] Descartado: `consent_collection` en Stripe Checkout (falla si no hay URL de condiciones en el panel de Stripe, y el reembolso íntegro lo hace innecesario).

### Derechos
- [x] `services/user_data.py`: propiedad derivada del esquema, `GLOBAL_TABLES` explícito.
- [x] `GET /users/me/export` (streaming, sin `password_hash`) y `POST /users/me/delete` (contraseña, límite de peticiones, borra cliente Stripe antes y aborta si falla).
- [x] `AccountDataRights` en Facturación › Cuenta.
- [x] `test-telegram` ya no envía el email del usuario ni devuelve el `chat_id`.

### Documentación
- [x] `docs/compliance/` (mapa normativo, registro de actividades, brechas, pendientes).
- [x] `CLAUDE.md`, `README.md`, `.claude/rules/auth-security.md`, `docs/user-guide.md`.

### Verificación
- [x] Backend: ruff limpio, pytest 1180/1180 tras rebase sobre `origin/main` (27 nuevos: `test_user_data.py` con claves foráneas activas, `test_consent.py`).
- [x] Frontend: tsc, ESLint, vitest 102/102, `pnpm build` (las 4 páginas legales estáticas), sin `<[0-9]` en MDX.
- [x] Navegador contra backend local con BD temporal: páginas legales sin sesión; registro bloqueado sin casilla; alta → sin banner; export 28 tablas sin hash; contraseña errónea → "Contraseña incorrecta"; borrado → sesión cerrada, landing con footer, 0 filas del usuario.
- [x] Commit, push, merge (#303) el 2026-09-30. El backend no se pudo desplegar hasta el 2026-10-02 (facturación de GCP desactivada por presupuestos con enforcement desde el 29-09); desplegado en `finview-api-5ebefff` y verificado.
- [ ] `docs/user-guide.pdf` no regenerado.

### Después del despliegue — 2026-10-01 / 02
- [x] Cadencia de cron: opciones 15→30 min, geo 30→60 min (los dos cron eran el 97 % del tiempo de Cloud Run). Código y docs alineados en #307.
- [x] #306 (el pipeline restaura `spec.traffic` si falla la promoción) y #307 en un solo build (#309).
- [x] Blog #300 y #308 en un solo merge (#310), resolviendo el patrón de conflicto de los ficheros compartidos.
- [x] "Datos, no consejos" en todo el producto (#311): `NOT_ADVICE`, `AiDisclaimer` junto a cada texto de IA, regla común en los prompts (`llm_rules.py`), "Top Picks" renombrado, `TERMS_VERSION` 2026-10-02.
- [x] Decisiones del titular: Ideas es interpretación de datos; representante en la UE con la misma solución que biglobster.top (política de privacidad: art. 3.2, acceso desde Tailandia declarado, autoridades, registro de versiones).

### Pendiente del CEO / abogado
Ver `docs/compliance/pendientes.md`: ley de Nuevo México frente a consumidores de la UE,
tarjetas de pago en `/pricing`, DPA de Neon y Vercel, enrutado de OpenRouter, detector de
spikes de prima con la cadencia de 30 min.

## Diferidos de Fase 5 / auditoría — 2026-09-25 (un PR por ítem)

- [x] 1. `zonas-clave/page.tsx`: el poll de análisis casa por `selectedItemId` (derivado en render) y deja de leer `watchlist` → sin `eslint-disable`; mismas dependencias efectivas porque (user, ticker) es único y cada cambio de id llega en el mismo batch que `selectedTicker`. La carga inicial conserva el suyo, con el porqué en el sitio: un updater funcional cambiaría la carrera del "Reintentar" (el buscador está vivo durante el reintento).
- [x] 2. `charts.py`: yield-on-cost con la base de coste de `portfolio_service` en vez de su FIFO propio. Divergían en cantidad (cambio de ISIN: la ISIN vieja nunca se cerraba → AENA 110 en vez de 100) y en coste (FIFO global entre cuentas). Coste desconocido → `null` (contrato + tipos frontend), también en la fila fusionada por ticker. Consecuencia: AENA pasa a "—" como en Cartera hasta vincular el coste.
- [x] 3. `options/page.tsx` (496 → 299): `optionsDataReducer` puro (16 acciones, cada una tras la llamada API que refleja) + `useOptionsData` con cargas, auto-sync y mutaciones como acciones; la página ya no recibe ningún setter. 8 tests de reducer. Sin smoke autenticado (login por contraseña).
- [x] 4. `import_service.py`: `_TX_DEPENDENT_TABLES` (CrossBrokerLot, TaxLot) y `_IMPORT_DEPENDENT_TABLES` (OptionAssignmentRecord, PortfolioHolding) consumidas por los tres cascade-deletes vía `_delete_tx_dependents` / `_delete_import_dependents`; orden y `synchronize_session` de cada función intactos. TaxResult/FIFOAdjustment/DataIssue siguen con su alcance propio en cada función. `test_cascade_delete_tables.py` recorre las FK del esquema. `test_import_service.py` sin tocar.
- [x] 5. Persistencia de holdings TR/DEGIRO/IBKR: memo de decisión en `tasks/holdings-persistence-decision.md` (no implementado). Medido con los ficheros 2025: DEGIRO 8/8 coincide, IBKR 2/9 discrepan, TR 25/47 discrepan y 3 posiciones se cerrarían. Hallazgo: `_load_snapshots` trata cualquier año con filas como completo aunque el marcador sea `false` (latente hoy).
- [x] Decisión (Brais, 2026-09-25): fix del loader primero, luego persistir DEGIRO; IBKR y TR sin decidir.
- [x] Loader: `_load_snapshots` ignora filas de imports `portfolio_snapshot_complete=false` (no cierran ni reescriben); legacy NULL intacto. Tests: parametrizado complete/legacy/partial + no reescribe + no desplaza un año completo anterior (3 fallan en el loader viejo).
- [x] DEGIRO: guardar holdings con `complete` = sección "Certificado de Beneficiario" presente y todos sus ISIN parseados. `test_dg_holdings.py` (8, uno con los PDF reales 2024+2025: posiciones = certificado, coste conocido). Los imports DEGIRO ya existentes sólo ganan filas al re-subir el PDF.

## Zonas Clave: calibrar el umbral de ruptura — 2026-09-25 (rama `feat/zonas-calibration`)

- [x] Cada candidato puntuado (no sólo >70) genera un `BacktestSignal ZONE_BREAK` con `break_probability`, `alerted` y `alert_threshold` (columnas aditivas).
- [x] `backtest_service.zone_calibration`: curva por buckets, acierto acumulado ≥ cada floor, `suggested_threshold` = floor más bajo con ≥30 medidos y ≥55% a 7d; `alert_threshold_for` = ese o 70. Nunca afloja con pocos datos.
- [x] `emit_for_analysis` usa `alert_threshold_for`; `run_analysis_for_user` evalúa outcomes al final (el agente de opciones salía antes si no había watchlist de opciones).
- [x] `GET /zonas-clave/calibration` + línea en la cabecera de la página ("Umbral de alerta N% (calibrado|por defecto) · …").
- [x] Docs: `.claude/rules/zonas.md`.
- [x] Verificar: pytest, tsc/vitest/lint/build, push, checks, merge (#289), Cloud Run `finview-api-02531ec` sano, `/zonas-clave/calibration` responde (401 sin auth).
- [x] Revisión del auditor (#289): el floor acumulado dejaba que una cola 80+ fuerte arrastrara una banda 50-59 al 10% por encima del listón → el gate se mueve **banda a banda sobre su propio registro** (≥20 medidos, ≥55%; baja si la banda inferior cumple, sube si la banda sobre el gate falla). `get_stats`/`get_calibration`/`GET /options/backtest` filtran `alerting_only`. Gate calculado una vez por ciclo.

## Geo: cerrar el bucle de aprendizaje — 2026-09-25 (rama `feat/geo-learning-loop`)

- [x] `confidence_mod` derivado de la precisión: `clamp((acc − 0.5) × 0.6 × min(1, n/10), ±0.30)`; recompute idempotente al inicio de cada auditoría (las filas con el viejo contador ±0.02/−0.03 convergen solas).
- [x] Test de cierre: una regla al 20% en 10 resultados cae por debajo del gate de notificación.
- [x] `_reanchor`: `create_checkpoints` no recrea horizontes ya puntuados (violaba el unique `(signal_id, horizon)` y tiraba la página como persist failure).
- [x] Re-puntuación en vivo de cada señal ACTIVE en cada auditoría (`live_score/outcome/rated_at` en `geo_signals`, `_ADDITIVE_COLUMNS`); panel muestra "Ahora: N% a favor".
- [x] Auditoría en su propio job: `POST /api/geo/audit` (CronKey), `run_audits`; el ciclo de 30 min ya no puntúa. Job `geo-intel-audit` `0 */4 * * *` creado en PAUSED; `cloudbuild.yaml` lo pausa/reanuda con los demás.
- [x] Docs: `.claude/rules/geo.md` (auditor, scheduling, give-up 3d), `docs/deployment.md` (job + comando).
- [ ] Verificar: pytest, tsc/vitest/lint/build, push, checks, merge, Cloud Run sano, `geo-intel-audit` ENABLED tras el rollout, primera auditoría con `recomputed > 0`.
- [ ] No incluido (decisión): calibración del 70 de Zonas Clave (requiere guardar `break_probability` en cada candidato puntuado, no sólo >70).

## Fase 5 — splits de módulos — 2026-09-23 (ramas `refactor/phase5-*`)

### Backend (`refactor/phase5-backend-splits`)
- [x] `models.py` → paquete `backend/models/` por dominio, `__init__` re-exporta todo.
- [x] `import_service.py`: `_run_annual_import` (lock → dup → replace → account → ImportRecord → store → FIFO → supervisor → commit) + `_store_holdings`; los 6 `import_*_report` sólo aportan el almacenamiento.
- [x] Diferido (decidido): unificar los tres cascade-deletes (semánticas distintas por import/cuenta/usuario; no es un movimiento seguro).
- [x] Verificar: ruff, pytest 1096, docs (`README`, `admin-guide`), push, checks, merge (#282), Cloud Run `finview-api-055f269` sano.

### Frontend (`refactor/phase5-options-page`, `refactor/phase5-portfolio-page`)
- [x] `options/page.tsx` (1628 → 496) → `badges.tsx`, `meffTickers.ts`, `OptionsStatsCards`, `WatchlistTab`, `MonitorTab`, hooks si salen limpios.
- [x] `portfolio/page.tsx` (1016 → 218) → `types.ts`, `PortfolioSummaryCards`, `PositionDetailPanel`, `PositionsTable`, `PositionsMobileList`, hooks si salen limpios.
- [x] Verificar: tsc, vitest, lint, build, Vercel verde, merge (#283, #284). Sin smoke manual: los splits son extracciones con props explícitas y diff de cuerpo idéntico; `useOptionsData`/`useWatchlistAutoSync` se dejan inline a propósito (ver `.claude/rules/frontend.md`).

## Auditoría y refactor — 2026-09-23 (rama `refactor/audit-2026-09-23`)

Informe completo: `tasks/audit-2026-09-23.md`.

### Fase 1 — bugs
- [x] Una sola tabla sufijo→moneda (`prices.py` / `fred_rates.py`).
- [x] Lock de `yf.download` compartido (charts, prices, zonas-clave).
- [x] Webhook Stripe sin bloquear el event loop.
- [x] Rutas de upload: helper único, límite de tamaño, `logger.exception`, 422 sólo para parse.
- [x] `api.ts`: helper `send()` con `res.ok` + retry 401 para todas las mutaciones.
- [x] Flag de scheduler de opciones por usuario.
- [x] Toaster con tema.
- [x] pre-push: trigger incluye `scripts/`, `cloudbuild.yaml`, `uv.lock`.
- [x] `.gitignore`: `.env`, `*.db-*`, `*.sqlite3`. Destrackear `finview_casillas_2024.json`.

### Fase 2 — código muerto
- [x] Frontend: 7 ficheros shadcn/intro, ruta `portfolio/[isin]`, 3 métodos API + tipos, `d3-geo`, `@mdx-js/react`.
- [x] Backend: helpers listados en el informe; Section VI no infla `record_count`.

### Fase 3 — helpers compartidos
- [x] `importers/base.py`: `file_sha256`, `parse_eur_decimal`, `parse_dmy`, `ISIN_RE`.
- [x] ISIN→ticker: `ticker_map.resolve` primero en scraper y supervisor.
- [x] `llm_envelope.chat()` para las 6 llamadas OpenRouter.
- [x] Frontend: `lib/format.ts`, `components/ErrorState.tsx`, `bestEffort` en catches mudos.

### Fase 4 — docs y lint
- [x] CLAUDE.md (Next 16 / TS 6, counts), README counts, `.claude/rules/frontend.md`.
- [x] ESLint (`eslint-config-next`) + script `lint` — 0 errores, 0 warnings; las reglas React Compiler vuelven a `error` (PR de seguimiento).
- [ ] Verificar: ruff, pytest, tsc, vitest, build, pre-push, Vercel preview verde, merge.


## Incidente Cloud Run: crash-loop y prevención de coste — 2026-08-01

- [x] Confirmar qué revisión/servicio mantiene tiempo facturable y aislar la causa
      real del fallo de arranque de `finview-api`.
- [x] Contener el gasto sin interrumpir el backend sano ni perder configuración.
- [ ] Corregir el despliegue y exigir `Ready=True`, tráfico correcto y `/api/health`.
- [x] Añadir guardas reutilizables contra puerto incorrecto, revisión no lista,
      billing por instancia y capacidad mínima/máxima inesperada.
- [x] Ejecutar tests, `/review`, documentar el runbook y verificar el estado remoto.
- [x] Publicar y mergear el PR #192 tras revisión del CEO.

## PR #190/#191 — resolución de conflictos con main — 2026-08-01

- [x] Rebasar el artículo de riesgo divisa (#190) preservando el índice y estilos
      de los artículos ya incorporados a `main`; validar frontend y Vercel.
- [x] Rebasar el hardening FIFO (#191) preservando cartera/valoración de #187 y
      retenciones/casillas de #186; validar backend, Ruff y frontend.
- [x] Ejecutar `/review` sobre ambas ramas y publicar con `--force-with-lease`.
- [x] Confirmar ambos PRs como `CLEAN`/`MERGEABLE` con checks remotos verdes.

## PR #187 — resolución de conflictos con main — 2026-08-01

- [x] Rebasar `codex/fix-portfolio-valuation` sobre `origin/main`.
- [x] Resolver conflictos conservando valoración fail-closed, snapshots autoritativos
      y el modelo actualizado de retenciones/casillas de `main`.
- [x] Ejecutar `/review`, suite backend, Ruff, TypeScript, tests y build frontend.
- [x] Publicar con `--force-with-lease` y confirmar PR mergeable con Vercel verde.

## Auditoría financiera 2026-07-29

- [x] Aislamiento por usuario (PR #184).
- [x] FIFO fiscal v2 y recálculo operativo (PR #185).
- [x] Retenciones, doble imposición y casillas (PR #186).
- [x] Cartera/valoración corregida: FIFO de posiciones, snapshots vacíos y
      actividad posterior, coste desconocido fail-closed, precios multi-ISIN/SGD y
      ceros preservados en API/UI.
- [x] Hardening FIFO residual: cerrar invalidación histórica, fees, asignaciones,
      spinoffs y redondeo en PR separado.
- [ ] Hardening de imports/snapshots: impedir que un informe parcial sustituya uno
      completo y distinguir cartera realmente vacía de un fallo de parseo.
- [ ] Hacer atómica la escritura de la caché diaria de precios ante peticiones
      concurrentes de posiciones y resumen.

## Auditoría financiera — fase 3: integridad FIFO residual — 2026-08-01 ✅

- [x] Invalidación descendente desde el primer año modificado para import/replace/delete,
      borrado de cuenta y CRUD manual; limpia años posteriores y el último sell.
- [x] Semántica única de importes: BUY suma fees; SELL los descuenta. Aplicada a CRUD
      manual y DEGIRO; sus `TaxLot` descuentan comisión e impuesto de transacción.
- [x] Asignaciones IBKR: todas las patas se conservan, matching unívoco, prima aplicada
      una sola vez (PUT al coste, CALL al importe de venta).
- [x] SPINOFF entra por cantidad con base desconocida; venta que lo alcanza falla
      cerrada y genera `fifo_missing_cost_basis` sin cerrar el aviso fuente
      `missing_cost_basis`, en vez de asumir coste cero.
- [x] El aviso fuente permite introducir coste por acción con la acción `set_price`;
      al resolverlo se actualiza el SPINOFF y se recalculan los años dependientes.
- [x] Agregación por ISIN/casilla antes de redondeo `ROUND_HALF_UP` a céntimos; detalle
      de auditoría a seis decimales.
- [x] Concurrencia: advisory locks transaccionales para reemplazo de import y rebuild
      FIFO; validación backend de importes y acciones de resolución.
- [x] Verificación: Ruff limpio; 453 passed/131 skipped; fixtures reales DEGIRO 2024
      (537,01 € tras costes) e IBKR 2024 (ADM/VZ, primas exactas).
- [x] Operación: sin cambio de esquema ni versión FIFO. Reimportar históricos DEGIRO e
      IBKR afectados para regenerar valores persistidos; no hay backfill automático.

## Cross-section coherence — instrument drawer (C now, B roadmap) — 2026-06-24

**Origen:** /office-hours (proyecto completo). Decisión: **coherencia, no features.**
Diseño completo: `~/.gstack/projects/braisntext-FinView/brais-claude-festive-northcutt-faf7e2-design-20260624-015924.md`

**Modelo elegido:** "C ahora, B en roadmap". Drawer global por instrumento (ticker)
con pestañas que reutilizan cada sección; pensado para promocionarse luego a una
página `/ticker/[symbol]` (B) sin reescribir los componentes de pestaña.

**Decisiones cerradas:**
- Watchlists de opciones y zonas son **listas distintas** (no fusionar). `zonas_clave_watchlist`
  es tabla aparte y **posee** filas `zonas_clave_analysis` por FK → se deja intacta.
- El informe IA de opciones **por ticker** vive en la pestaña Opciones del drawer,
  **bajo demanda** (llamada fresca al abrir), separado del informe global del ciclo.

### Fase 0 — Decisión a confirmar antes de tocar código
- [x] **Almacén de la watchlist de markets → Opción B (CEO, 2026-06-24):** tabla
      nueva `markets_watchlist` (mismo patrón de API que `/options/watchlist`, sin
      cirugía de constraint). Options queda sin tocar; mínimo blast radius en prod.

### Fase 1 — Unificación de mecanismo de watchlist (fundación de A) ✅
- [x] Backend: tabla `markets_watchlist` ([models.py](backend/models.py)) +
      router `/markets/watchlist` (list/add/import/delete) ([api/markets.py](backend/api/markets.py)),
      schemas + registro en [app.py](backend/app.py). Endpoint `import` idempotente
      para la migración. (No toca `watchlist_items` ni zonas.)
- [x] Tipos TS + cliente API (`MarketsWatchlistItem` + `api.markets` en
      [lib/api.ts](frontend/src/lib/api.ts)).
- [x] `markets/page.tsx`: lee/escribe vía API; **migración única** localStorage→DB
      al montar (importa `fv-markets-watchlist`, limpia la clave); siembra defaults
      si la lista está vacía.
- [x] Verificado: ruff limpio; app importa y monta rutas; **120 passed** (los 60
      errors son fixtures sin ficheros reales en `files/`, preexistentes); E2E con
      TestClient: list/add(201)/dup(409)/import idempotente/delete(204)/404 ✅.
- Nota: si el usuario borra TODOS los tickers, al recargar se re-siembran los
      defaults (igual que el comportamiento previo de localStorage). Aceptable; si
      molesta → flag "seeded" en follow-up.

**Invariantes:** estado→DB por usuario (fin del localStorage no portable);
blast radius→aditivo, no toca FIFO ni el scraper; timing→migración idempotente
(solo si existe la clave).

### Fase 2 — Shell del drawer global de instrumento ✅
- [x] `InstrumentDrawerProvider` + `useInstrumentDrawer()` ([components/InstrumentDrawer.tsx](frontend/src/components/InstrumentDrawer.tsx))
      montado en [app/layout.tsx](frontend/src/app/layout.tsx) dentro de
      `AuthProvider`/`TooltipProvider`; expone `openInstrument(symbol, { isin?, name?, tab? })`.
- [x] Drawer con `Sheet` (side=right, `data-[side=right]:sm:max-w-2xl`); cabecera
      ticker + badge **"En cartera"** (holdings lazy-cargados al abrir); `Tabs`
      controladas (Precio | Opciones | Zonas).
- [x] **Precio** tab funcional (`PrecioTab` self-contained `{symbol}` → `priceHistory`
      + `PriceChart` + scopes); Opciones/Zonas = placeholders con CTA a la página
      completa (sin pérdida de acceso).
- [x] Rewire cross-links: options "ZC" → `openInstrument(t,{tab:'zonas'})`;
      zonas "ver opciones" → `openInstrument(t,{tab:'opciones'})`. `router` sobrante
      eliminado en options.
- [x] Verificado: `tsc --noEmit` limpio + `next build` verde (todas las rutas).
- **Tradeoff transitorio:** los dos cross-links ahora abren el drawer en una
      pestaña placeholder (Opciones/Zonas) → 1 click extra hasta la página completa.
      Se elimina en Fase 3 cuando esas pestañas rendericen el análisis real in-place.
- Pendiente: QA en navegador (requiere stack levantado + login).

**Invariantes:** estado→efímero en cliente (qué ticker/pestaña), nada en DB;
blast radius→nuevo provider envuelve children, no rompe páginas; cada pestaña
componente aislado `{ symbol }` (listo para promocionar a B).

### Fase 3 — Pestañas v1 (las que ya tienen plumbing `?ticker=`) ✅
- [x] **Precio**: `PrecioTab` (Fase 2) — `PriceChart` + `/charts/price-history`.
- [x] **Opciones** ([components/instrument/OpcionesTab.tsx](frontend/src/components/instrument/OpcionesTab.tsx)):
      **informe IA por ticker bajo demanda** → nuevo `POST /options/agent/analyze-ticker`
      ([options_agent.py](backend/services/options_agent.py) `analyze_single_ticker` +
      prompt `_CLAUDE_TICKER_*` de 5 secciones, max_tokens 1500; corre aunque no haya
      alertas; guard `openrouter_api_key`; fallo IA devuelve igualmente el resumen de
      reglas). Más cadena compacta (selector de vencimiento + tabla calls/puts por strike).
- [x] **Zonas** ([components/instrument/ZonasTab.tsx](frontend/src/components/instrument/ZonasTab.tsx)):
      `ZonasClaveChart` + tarjeta de tendencia (RSI/MACD/bias) + tabla de zonas. Si el
      ticker NO está en `zonas_clave_watchlist` (404) → CTA "Añadir y analizar"
      (`addTicker` dispara análisis en background, polling 3s ×12).
- [x] Placeholders eliminados; cross-links aterrizan en contenido real. Link sutil
      "Ver en Opciones/Zonas Clave" a la página completa.
- [x] Verificado: ruff limpio; `tsc` limpio; `next build` verde; `analyze_single_ticker`
      probado (status ok/no_data, ai_error not_configured sin key, resumen siempre).

### Fase 4 — Pestañas v2 ✅
- [x] **Fiscal** ([components/instrument/FiscalTab.tsx](frontend/src/components/instrument/FiscalTab.tsx)):
      coste medio/total, valor, P&L no realizada, país, desglose por bróker.
- [x] **Dividendos** ([components/instrument/DividendosTab.tsx](frontend/src/components/instrument/DividendosTab.tsx)):
      `dividends_by_year` (bruto/neto/pagos) + total.
- [x] Ambas reusan `GET /portfolio/positions/{isin}` vía hook compartido
      `usePositionDetail` (cache por ISIN en sesión → 1 fetch para las 2 pestañas).
      ISIN resuelto en el provider desde holdings (ticker→isin); si no es posición
      en cartera → estado vacío. Sin cambios de backend (solo Vercel al desplegar).
- [x] Verificado: `tsc` limpio; `next build` verde.

### Fase 5 — Resolver Cartera (pregunta original) ✅
- [x] **CEO: drawer + portar strikes.** Cartera ahora es un lanzador: la fila abre
      el drawer (pestaña Opciones) en vez de expandir inline. Eliminadas ~500 líneas
      de chain/expiry/chart inline + su estado y effects ([options/page.tsx](frontend/src/app/options/page.tsx) 2212→1696).
      Overlay de strikes near-money portado a la pestaña Opciones del drawer
      (spot + 3 abajo/3 arriba sobre las velas). Cross-links "Ver en Cartera" y el
      deep-link `?ticker=` también abren el drawer. P&L de holdings preservado en la lista.
- [x] Verificado en local: fila AAPL → drawer en Opciones con chart de strikes + cadena;
      sin expansión inline. `tsc` limpio, `next build` verde.

### Fase 6 — Documentar promoción a B ✅
- [x] Documentado el camino `/ticker/[symbol]` en [claude.md](claude.md) (sección
      Instrument drawer → "Promotion to /ticker/[symbol]"): los componentes de pestaña
      se montan tal cual como secciones de página; `usePositionDetail` + APIs por sección
      funcionan fuera del drawer; owned/watched pasa a flag explícito solo si SSR/SEO lo pide.

---

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

---

## Arquitectura de señales — trigger / execution / thesis — 2026-07-16

**Origen:** sesión de planificación con CEO. Problema: las señales no están cableadas
entre secciones; cada página mezcla conceptos que no le tocan.

### Diagnóstico

Fuentes que HOY emiten señal:
- `options_analyzer.py` — IV alta, P/C ratio, IV skew, volumen inusual → `OptionsAlert`
- `premium_spike.py` — EMA en memoria → `PREMIUM_SPIKE` HIGH
- `geo/rules.py` — 89 reglas → `GeoSignal` (silo cerrado: tabla, tickers y auditor propios)

Fuentes que NO emiten:
- `zonas_clave_analyzer.py` — RSI/MACD/MAs/S-R son **puro display**, no disparan nada
- `macro_context.py` (FRED) — solo anota (Fase 2b), por diseño
- Fundamentales — **no existen en el código**

**Está invertido:** lo que debe disparar (técnico + geo) no dispara; lo único que
dispara es microestructura de opciones.

**Monitor vacío = bug, no arquitectura:** `/options/alerts` filtra a 7 días
([options.py:227](backend/api/options.py:227)) y el ciclo solo corre por botón manual o por
`options_scheduler.py` (APScheduler en proceso, muere con `--min-instances=0`).
Options **no tiene endpoint de cron**; geo sí ([geo.py:161](backend/api/geo.py:161)).

### Modelo objetivo

| Capa | Página | Responsabilidad | Prohibido |
|------|--------|-----------------|-----------|
| **Trigger** | Zonas Clave | Análisis técnico; emite señales | Nada de opciones |
| **Execution** | Options Monitor | PUT/CALL y estrategias sobre triggers | Fundamentales, tesis especulativa |
| **Thesis** | Geo-Intel (mesa de ideas) | Oportunidad: dirección, fundamentales, macro, IA, backtest | Nada de opciones (salvo enlace de navegación) |

### Decisiones cerradas (CEO, 2026-07-16)
- [x] **Geo-Intel = mesa de ideas**, no feed de eventos. Ideas nacidas solo del técnico
      también aterrizan ahí. Rechazado: geo-solo-eventos (condena al técnico a mero
      disparador) y página nueva de ideas (fragmenta la nav).
- [x] **Fundamentales vía `yfinance .info`**. Gratis, ya es dependencia, cero llaves.
      Rechazado: FMP/pago (coste + servicio nuevo) y diferirlos (vacía la mesa de ideas).
- [x] **Se mantiene el enlace Geo-Intel → `/options?ticker=`**. Un enlace es navegación,
      no contenido de opciones.
- [x] **NO unificar `GeoSignal` + `OptionsAlert` + `BacktestSignal` en una tabla `Signal`.**
      Ciclos de vida distintos (geo: 5 checkpoints con basket scoring; options: 3 horizontes
      en columnas), no hay Alembic, sería DDL en prod. Si hace falta vista unificada →
      read-model fino de solo lectura sobre las tres tablas.

### Slice 0 — Cron de options (bug, se envía solo y primero) ✅ código
- [x] `POST /api/options/agent/cron` ([options.py](backend/api/options.py)): header `X-Cron-Key` ==
      `FINVIEW_CRON_SECRET`, compare en tiempo constante, un ciclo por usuario **síncrono**
      (Cloud Run puede reclamar la instancia tras responder — no hilos fire-and-forget).
- [x] **No es copiar-pegar de geo**, dos diferencias reales:
      - Honra el guard `_cycles_in_progress` que comparte con el `/agent/run` manual — un tick
        de cron encima de una ejecución manual re-descargaría todas las cadenas y duplicaría
        snapshots. Los usuarios saltados se reportan como `skipped`.
      - `run_cycle()` devuelve `{"status": "error"}` y nunca lanza ni devuelve None, así que
        `cycles_ok` mira el status. El idiom `is not None` de geo contaría fallos como éxitos.
- [x] 7 tests nuevos en [test_options_agent_trigger.py](backend/tests/test_options_agent_trigger.py)
      (auth ×3, ciclo por usuario, solo-ok, guard, liberación del guard). Suite: 189 pass / 131 skip.
- [x] Verificado por HTTP con TestClient: ruta registrada como `/api/options/agent/cron` junto a
      `/api/geo/cron`; 403 sin secreto / con clave mala / sin header; 200 con la buena.
- [ ] **Pendiente CEO — job en Cloud Scheduler** (no lo toco sin permiso: es infra de prod).
      Reusar `FINVIEW_CRON_SECRET`, mismo patrón que el job de geo. Sin esto el código no sirve
      de nada: el Monitor sigue vacío.
- [ ] Verificar en prod que el Monitor se puebla sin tocar el botón manual.

### Slice 1 — Zonas Clave: quitar Opciones ✅
- [x] Eliminada la card `OpcionesTab` del panel de detalle de ticker + el import huérfano
      ([zonas-clave/page.tsx](frontend/src/app/zonas-clave/page.tsx)).
- [x] `OpcionesTab` **no se borra**: sigue usada en 5 puntos de `options/page.tsx`.
- [x] Los toggles de lente cruzada (D2-A) **se quedan** — son navegación/suscripción, no contenido.
- [x] Verificado: build verde (50 páginas), cero referencias huérfanas a `OpcionesTab` en zonas.
      **No verificado visualmente** — `/zonas-clave` está tras login y no introduzco credenciales.

### Slice 2 — Options Monitor: fusionar Cartera + Watchlist ✅
- [x] Una sola lista guiada por la watchlist (las posiciones se auto-sincronizan → es
      superset de lo poseído), enriquecida con lotes + snapshot. Tab Cartera eliminada,
      6 tabs → 5. Default tab: `watchlist`.
- [x] Expandir fila → `OpcionesTab` (gráfica + cadena + navegador de vencimientos).
- [x] **Bug arreglado de paso**: la Cartera vieja iteraba `positions` con key
      `(isin, broker)` → un ticker en dos brókeres = **dos filas idénticas**. Con FIFO
      cross-broker esto pasaba de verdad. Ahora se agrupa por ticker.
- [x] **Borrado asimétrico**: los tickers en cartera solo tienen "Ocultar" (el borrado
      normal lo deshace el auto-sync al recargar); los no-poseídos tienen "Eliminar".
      Resuelve la interacción rara que documentaba claude.md.
- [x] Acciones fuera de la expansión (expandir cuesta fetch de vencimientos+cadena;
      borrar una fila no debe costar red).
- [x] Deep-link `?ticker=` re-cableado a la watchlist (antes solo miraba posiciones →
      un ticker no-poseído enlazado desde Ideas no se expandía).
- [x] **Extracción: reversada parcialmente.** El plan decía "extraer la lista a componente".
      Habría necesitado ~15 props = props drilling, peor que inline. En su lugar se extrajo
      solo la lógica **pura** a [lib/optionsWatchlistRows.ts](frontend/src/lib/optionsWatchlistRows.ts)
      — motivo real: testabilidad. 9 tests nuevos (18 total en frontend).
- [x] Verificado: build verde (50 páginas), 18/18 tests, typecheck limpio.
      **No verificado visualmente** — `/options` está tras login.
- [ ] Pendiente: `options/page.tsx` sigue en ~1990 líneas. Si molesta, la extracción real
      es un hook/contexto, no un componente con 15 props. Commit aparte.

### Slice 3 — Monitor tab = hub de alertas ✅
- [x] **La tab ya mostraba alertas.** Lo que fallaba era que no había ciclos (Slice 0).
      Lo que faltaba de verdad eran los enlaces.
- [x] Chips por alerta: `Opciones` (expande `OpcionesTab` inline), `Técnico`
      (→ `/zonas-clave?ticker=`), `Ideas` (→ `/geo-intel?ticker=`).
- [x] **`Ideas` solo aparece si el ticker tiene señal geo activa.** Un enlace a una
      página vacía es peor que no tener enlace. Options pide `/geo/signals?status=active`
      best-effort solo para saber qué tickers califican — metadato de navegación, no
      cruza contenido de tesis.
- [x] **Ideas no leía `?ticker=`** (solo enlazaba hacia fuera) → el enlace habría sido
      muerto. Añadido soporte en `GeoIntelSection`: selecciona la señal más reciente que
      afecta al ticker; sin match, no-op silencioso.
- [x] Smart Money sin chips a propósito: filas por contrato (ticker+strike+exp), varias
      comparten ticker → los chips serían ruido en una tabla de 9 columnas.
- [x] Nada de tesis ni fundamentales en Options: solo navegación.
- [x] Verificado: build verde, 18/18 tests, colSpan de la expansión ajustado a la
      columna nueva. **No verificado visualmente** (login).

### Slice 4 — El técnico emite señales (plumbing nuevo, el núcleo del cambio)

**Diseño cerrado (CEO, 2026-07-16): proximidad determinista como puerta, IA como scorer.**

```
zonas_clave_analyzer, tras calcular zonas + indicadores:
  1. GATE (barato, sin IA): para cada zona, distance_pct = |price - zone.center| / price
     distance_pct <= _PROXIMITY_THRESHOLD (2.0%) → candidato
  2. SCORE (IA, solo candidatos): OpenRouter → break_probability 0-100 + rationale
     Contexto del prompt: fuerza de zona, toques, volumen, RSI, MACD, MA50/200,
     trend_bias, distance_pct, dirección (soporte vs resistencia)
  3. REGISTRAR: todos los candidatos puntuados, con su %
  4. ALERTAR: solo break_probability > 70
```

**4a (backend) ✅ — el Slice 4 se partió en dos: 4a backend, 4b superficie en Monitor.**

- [x] **Umbral de proximidad = 2.0%.** Racional: `_CLUSTER_THRESHOLD` ya es 1.5% (radio de
      fusión de zonas); por debajo de eso estás *dentro* de la zona, no cerca de ella.
- [x] `services/zone_proximity.py` — puerta determinista, pura, 12 tests.
- [x] `services/zone_scorer.py` — scorer LLM + caché (ticker, nivel 2dp, día UTC).
- [x] `services/technical_signals.py` — une puerta+scorer+persistencia, 12 tests.
- [x] `models.TechnicalSignal` — tabla nueva (create_all la crea sola, sin DDL manual).
- [x] `POST /api/zonas-clave/cron` + `GET /api/zonas-clave/signals`.
- [x] **Dirección derivada del lado del precio, NO de `zone_type`.** Una "resistencia" que el
      precio ya superó es un nivel volteado que actúa como soporte: fiarse de la etiqueta
      histórica invierte la dirección en cada nivel volteado.
- [x] Suite: 213 pass / 131 skip (24 tests nuevos), ruff limpio.
- [x] **Ventana de zonas → 10y (CEO, 2026-07-16), desacoplada de la de descarga.**
      El `20y` venía de `a2bc58e`, un commit de **gráficos**: existe para el scope MAX del
      chart, no por calidad de zonas. Bajar la constante habría recortado el gráfico en
      silencio. Ahora: descarga 20y (gráfico intacto) + `zone_window()` recorta a 10y solo
      para pivotes y mediana de volumen. Misma descarga, cero coste. 9 tests.
      Efecto no anticipado: la mediana de volumen es el **denominador** de `vol_score`;
      medirla a 20y infravaloraba todas las zonas actuales (SAN.MC: 62.5M vs 43.5M).
- [x] **Notificaciones: NO por ahora (CEO, 2026-07-16).** Las señales técnicas solo se
      persisten. Se activarán cuando haya datos de outcome que digan si el 70 significa
      algo — no antes de que suene el móvil por un número sin calibrar.
**4b (superficie) ✅**
- [x] Tercer filtro "Técnico" en el Monitor, junto a Alertas y Smart Money — mismo patrón
      que ya existía (`monitorFilter`), cada forma de dato en su vista nativa en vez de
      aplastarlas en una tabla con el mínimo común denominador.
- [x] Muestra **todos** los candidatos puntuados, no solo los que alertan: >70 es raro y
      una vista alerted-only leería vacía (justo el problema que arregló el cron), y ver
      los casi-aciertos junto a su nota hace legible el umbral en vez de mágico.
- [x] `break_probability = null` → "sin puntuar", nunca 0%.
- [x] Chips (Opciones/Técnico/Ideas) reutilizados del Slice 3.
- [x] Aviso permanente en la vista: la probabilidad no está calibrada.
- [x] Verificado: build verde, 18/18 tests, colSpan=8 acorde a 8 cabeceras.
      **No verificado visualmente** (login).
- [ ] **Registrar todos, alertar >70.** El 70 es un corte sin calibrar — un "73%" de un LLM
      no es una probabilidad. Guardando también los <70 se puede comprobar en semanas si
      los >70 rompen más que los <70, y mover el número con datos. Mismo patrón que
      Fase 2b (instrumentar y mostrar, sin que el dato toque el gating hasta validarlo).
- [ ] **Token gating (lección de `geo/analyst.py`)**: la proximidad persiste días. Cachear
      por (ticker, zona, día) y re-puntuar solo al *entrar* en proximidad desde fuera o si
      `distance_pct` se mueve materialmente. Sin esto, cada ciclo re-paga el mismo scoring.
- [ ] IA reutiliza `settings.openrouter_model` — sin llave ni proveedor nuevos.
      Fallo de IA nunca rompe el ciclo de análisis (guardar como best-effort).
- [ ] Backtest: `backtest_service.record_signal()`. Ojo con el gotcha de enums
      (`_outcome_value()`), no comparar contra `.value` directamente.
- [ ] Ruta: trigger técnico → Options Monitor (ejecución) **y** → Ideas (tesis).
- [ ] **Deuda que esto destapa**: `zonas_clave_scheduler.py` tiene el mismo defecto que
      options (APScheduler en proceso, muere con `--min-instances=0`). Hoy no duele porque
      el técnico no dispara nada. Con el Slice 4 dolerá → necesita cron como el Slice 0.
- [ ] Backtest: reutilizar `backtest_service.record_signal()`. Ojo con el gotcha de enums
      (`_outcome_value()`), no comparar contra `.value` directamente.

### Slice 5 — Ideas: mesa de ideas ✅ (parcial)
- [x] **La mayor parte ya existía.** El panel ya tenía stats, "Why this was triggered" con
      la regla + su tesis + confianza, tickers con dirección y precio al disparo, y los 5
      checkpoints de backtest. Tercera vez en esta serie que lo pedido ya estaba a medias.
- [x] Fundamentales vía yfinance `.info`: `GET /charts/fundamentals` (caché 6h) +
      `FundamentalsCard`. Verificado con tickers reales: AAPL 14 campos, SAN.MC 13
      (los europeos también), inexistente → `{}` sin romper.
      **Contexto para la tesis, nunca entrada de señal/score/gate** — y la UI lo dice.
- [x] Botón "Añadir a Zonas Clave" en el ticker expandido. Estado propio en vez de props:
      el panel re-renderiza en cada poll de 60s y pasar add/busy/error de N tickers sería
      prop drilling. Va por `/zonas-clave/watchlist` → `enable_zonas`, nunca filas hijas.
- [x] Subtítulo actualizado — ya no miente: el técnico alimenta la página desde el Slice 4.
- [ ] **Pendiente**: régimen macro en la página (existe `MacroBadge` en options, reutilizable).
- [x] **Renombrado → "Ideas" (CEO, 2026-07-16).** Solo la etiqueta de cara al usuario:
      [QuickNav.tsx:17](frontend/src/components/QuickNav.tsx:17) y
      [GeoIntelSection.tsx:137](frontend/src/components/geo-intel/GeoIntelSection.tsx:137).
      Ruta `/geo-intel`, tabla `geo_signals`, prefijo de API e identificadores de código
      **se quedan**: renombrar la ruta rompe deep links y renombrar tablas es DDL en prod
      sin Alembic. Churn sin valor para el usuario.
- [ ] Subtítulo (`GeoIntelSection.tsx:143`, "Geopolitical & natural events, plotted as
      financial signals") **pendiente hasta este slice**: hoy la página sigue siendo solo
      eventos geo; cambiarlo antes de que el técnico la alimente la haría mentir.

## Ideas compartido: un owner del sistema para todos los usuarios — 2026-09-21

Decisión del CEO: Ideas se calcula con los mismos datos para todos, así que se muestra
lo mismo a todos y se ahorra el ciclo por usuario. Slice mínimo, sin cambio de esquema.

- [x] `services/geo/owner.py`: usuario del sistema (inactivo, sin password) dueño de
      `geo_signals` / `geo_checkpoints` / `geo_cycle_runs`; adopta el histórico de la
      cuenta más antigua en el arranque que lo crea.
- [x] `app.py`: `ensure_geo_owner()` tras `ensure_constraints()`.
- [x] `api/geo.py`: todas las lecturas y `/run`, `/scheduler/*`, `/cron` sobre el owner.
- [x] Crons de options y zonas-clave ignoran usuarios inactivos (el owner no tiene cartera).
- [x] Tests: `test_geo_owner.py` + adaptar los tests de cron en `test_geo_notify_cron.py`.
- [x] Docs: `.claude/rules/geo.md`, `CLAUDE.md` (conteos), memoria, decisiones.
- [x] Verificar: suite backend, ruff, push, 4 checks verdes, merge, siguiente ciclo cron
      (un solo ciclo, 0 páginas repetidas, la UI de cualquier cuenta ve las mismas señales).

## OFAC ingest — designaciones oficiales, porque GDELT no las trae — 2026-09-22

- [x] `ingest/ofac.py`: listado + páginas `/recent-actions/YYYYMMDD`, parser del formato
      canónico SDN (kind, programas, país), ventana 3 días, caché por ciclo, rutas feas.
- [x] `sentinel.analyze_ofac_actions`: un evento `sanctions` por (acción, país) con altas.
- [x] `rules.py`: átomo `country=` + `ofac-sanctions-russia` / `ofac-sanctions-venezuela`.
- [x] Frontend: etiqueta de fuente "OFAC". Docs: `.claude/rules/geo.md`, `CLAUDE.md`.
- [x] Verificar: suite, push, 4 checks, merge, primer ciclo con `ofac` en `sources` (17:30 UTC: ofac=1, página 20260918 parseada, 11 entradas, 0 altas → sin evento, correcto).

## Federal Register ingest — aranceles USTR y altas en la Entity List — 2026-09-22

Medido: en 90 días, 4 acciones arancelarias USTR + 2 reglas BIS Entity List; 0 señales
`trade_dispute` en toda la historia de la tabla. Mismo patrón que OFAC (país → capital,
átomo `country=`), sin HTML: API JSON sin clave.

- [x] `ingest/fedreg.py`: una consulta para ambas agencias, clasificación por título, países
      por título+abstract, ventana 3 días, caché por ciclo, degradación a stale.
- [x] `sentinel.analyze_fedreg_documents` + regla `fedreg-trade-brazil` (EWZ−).
- [x] Frontend: etiqueta "Federal Register". Docs: `.claude/rules/geo.md`, `CLAUDE.md`.
- [x] Verificar: suite, push, 4 checks, merge, primer ciclo con `fedreg` en `sources` (03:00 UTC 2026-09-22: fedreg=0 sin aviso — ventana vacía tratada como respuesta, no como caída).
