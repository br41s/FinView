# FinView

Dashboard de inversiones personales con importación multi-broker, motor fiscal IRPF español y monitor de opciones con agente IA.

## Stack

- **Backend:** FastAPI · SQLAlchemy · pdfplumber · openpyxl · yfinance · OpenRouter (httpx)
- **Frontend:** Next.js 16 · React 19 · TypeScript 6 · TailwindCSS · Recharts · lightweight-charts · NextAuth · shadcn/ui
- **DB:** Neon Postgres (prod) · SQLite (local fallback)
- **Deploy:** Vercel (frontend) · Google Cloud Run `europe-west1` (backend) · Cloud Build trigger (CI)
- **Tests:** pytest (1798 backend, 148 skipped sin ficheros reales, en CI y en un worktree local por igual) · vitest (394 frontend) · ESLint

## Brokers soportados

| Broker | Formato | Datos extraídos |
|--------|---------|-----------------|
| Trade Republic | PDF (Steuerbericht) + CSV (Transaction export) | Dividendos, plusvalías, retenciones, casillas, cartera (PDF) · ledger de transacciones multi-año + intereses (CSV) |
| DEGIRO | PDF (Informe Anual) | Dividendos, ganancias/pérdidas, cartera, transacciones |
| Interactive Brokers | CSV (Activity Statement) | Trades, dividendos, retenciones, P&L realizado, opciones |
| ING | PDF (Información Fiscal) | Intereses, dividendos, transacciones, cartera |
| BBVA | 3× PDF (operaciones, dividendos, patrimonio) | Compras/ventas, dividendos, cartera |
| eToro | XLSX (Account Statement) | Dividendos, posiciones cerradas/abiertas, actividad |

## Inicio rápido

```bash
# Backend
cd /path/to/FinView
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload --port 8000

# Frontend
cd frontend
pnpm install
pnpm dev
```

Acceder a `http://localhost:3000`.

## Arquitectura

```
FinView/
├── backend/
│   ├── app.py              # FastAPI app + CORS + startup
│   ├── models/             # SQLAlchemy ORM, one module per domain (ledger, options, geo, …)
│   ├── database.py         # Engine + session factory
│   ├── api/
│   │   ├── imports.py      # POST endpoints para cada broker
│   │   ├── transactions.py # GET dividendos, capital gains, listados
│   │   ├── fiscal.py       # GET casillas, resumen fiscal, FIFO lots, fx-rate
│   │   ├── charts.py       # GET datos para gráficas
│   │   ├── alt_investments.py # CRUD inversiones alternativas + /summary
│   │   └── schemas.py      # Pydantic response models
│   ├── importers/
│   │   ├── base.py         # Dataclasses compartidos + country_from_isin
│   │   ├── tr.py           # Parser Trade Republic PDF
│   │   ├── dg.py           # Parser DEGIRO PDF
│   │   ├── ibkr.py         # Parser IBKR CSV
│   │   ├── ing.py          # Parser ING PDF
│   │   ├── bbva.py         # Parser BBVA PDFs
│   │   └── etoro.py        # Parser eToro XLSX
│   ├── services/
│   │   ├── import_service.py  # Lógica de importación + deduplicación
│   │   ├── fifo_engine.py     # Motor FIFO cruzado multi-broker
│   │   ├── prices.py         # Cache de precios Yahoo Finance
│   │   ├── options_scraper.py # Scraper Yahoo Finance + MEFF (30 tickers .MC) + Eurex
│   │   ├── options_agent.py   # Agente monitor: ciclo Observe→Greeks→Analyze→Store→Notify→Claude
│   │   ├── options_analyzer.py # Reglas de análisis IV/P·C/skew/volumen inusual
│   │   ├── greeks_calculator.py # Delta, Gamma, Theta, Vega, Rho (Black-Scholes)
│   │   ├── premium_spike.py   # Detector de spikes de prima vía EMA in-memory
│   │   ├── backtest_service.py # Motor backtesting: record_signal + evaluate_pending
│   │   ├── notification_service.py # ntfy.sh + Email SMTP + Telegram Bot
│   │   ├── exchange_rates.py  # Servicio de tipos de cambio ECB (fallback IRPF)
│   │   └── cnmv_catalog.py    # Catálogo CNMV de IIC (buscador alt-investments)
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/page.tsx                 # Dashboard principal (5 tabs — inversiones)
│       ├── app/options/page.tsx         # Monitor opciones (5 tabs)
│       ├── app/alt-investments/page.tsx # Inversiones alternativas (banca privada)
│       ├── app/living-world/            # Mundo vivo: tu cartera como pueblo 3D (Three.js; Fase 1: cartera real, eventos simulados; ?demo=1 = datos ficticios)
│       ├── components/                  # FileUpload, tablas, stats cards
│       ├── components/charts/           # 8 componentes de gráficas
│       └── lib/                         # API client + tipos TypeScript
└── pyproject.toml
```

## Motor fiscal IRPF

- **Modelo 100:** Casillas 27/29 (rendimientos), 328/380 o 332/337 según el formato del ejercicio (ganancias y pérdidas), 588 (doble imposición) y 597 (retenciones españolas)
- **Modelo 714:** Casillas 05-09 (patrimonio en el extranjero)
- **FIFO cruzado v2:** Matching cronológico global; las ventas históricas consumen inventario antes del ejercicio objetivo y una compra futura nunca puede financiar una venta anterior
- **Invalidación cronológica:** Cambiar o borrar historia recalcula automáticamente todos los ejercicios posteriores con ventas y elimina resultados obsoletos
- **Retenciones:** Efectivo, pago a cuenta español y retención extranjera se guardan por separado; la deducción CDI solo se aplica cuando el informe aporta un importe acreditable explícito
- **Ajustes FIFO:** Desglose versionado por ganancias/pérdidas, integrado en casillas, resumen, estimador, dashboard, exportación y comparativa anual
- **Integridad:** ISIN vacío, inventario incompleto o un spin-off sin coste alcanzado por una venta no generan un resultado FIFO autoritativo; el supervisor conserva `missing_cost_basis`, permite completar el coste por acción y el bloqueo anual usa `fifo_missing_cost_basis`
- **Costes de operación:** Compras manuales, DEGIRO e IBKR incorporan comisiones al coste; las ventas las descuentan. Las asignaciones PUT/CALL de IBKR aplican su prima una sola vez a la pata de acciones
- **Redondeo fiscal:** Se agregan los lotes por ISIN y casilla antes de redondear a céntimos con criterio `ROUND_HALF_UP`; el detalle de auditoría conserva seis decimales
- **Concurrencia:** PostgreSQL serializa los reemplazos anuales y cada rebuild FIFO por usuario dentro de la transacción

Los lotes y ajustes anteriores a FIFO v2 no se aplican a los totales fiscales ni se
exponen como vigentes. Para regenerarlos hay que reemplazar o reimportar el ejercicio;
la migración de esquema no reinterpreta automáticamente datos históricos.
Lo mismo ocurre con retenciones importadas antes del desglose origen/destino: siguen
visibles como efectivo retenido, pero deben reimportarse para aplicarlas al estimador.
Los informes DEGIRO e IBKR importados antes de estas correcciones deben reemplazarse o
reimportarse para regenerar comisiones, primas de asignación y lotes fiscales; no hay
migración de esquema ni backfill implícito.

## Cartera y valoración

- Las cantidades se reconcilian contra el último snapshot anual completo y después
  incorporan todas las operaciones posteriores. Un snapshot completo sin holdings
  cierra correctamente las posiciones antiguas.
- El coste de posiciones abiertas conserva los lotes FIFO. Un `SPINOFF` o una parte
  del inventario sin origen conocido deja el coste como desconocido, nunca como cero.
- Si falta coste en cualquier posición, la UI no inventa capital invertido ni
  rentabilidad. Si falta un precio, tampoco publica una valoración total parcial.
- Los precios compartidos por varios ISIN se aplican a todos; Yahoo `.SI` se interpreta
  en SGD antes de convertir a EUR.
- **Exposición por sector y región**: el valor de mercado se reparte según los ingresos
  que cada empresa declara por segmento y por región en su último informe anual (10-K de
  la SEC para emisores de EE. UU., nota de segmentos del informe ESEF para el resto vía
  GLEIF + filings.xbrl.org). Un desglose solo se publica si suma los ingresos totales
  etiquetados del informe; las cifras que el modelo copia de una nota ESEF deben aparecer
  tal cual en ella. Si el informe no etiqueta ingresos, el total es el margen bruto
  (bancos), los ingresos de seguros (aseguradoras) o los ingresos por alquiler
  (inmobiliarias), y la fuente lo indica. Una acción sin desglose en su informe se cuenta
  entera en el país de su ISIN y en su sector de cotización (Yahoo Finance), marcado como
  estimado. ETFs y fondos quedan como "Sin datos". Cada posición enlaza a su informe. Detalle en `.claude/rules/segments.md`.
- **Exposición a la IA**: lo que cada empresa dice de la inteligencia artificial en su
  último informe anual (factores de riesgo del 10-K en EE. UU., el informe ESEF completo
  en la UE). FinView cuenta las menciones; un modelo elige hasta tres citas, que solo se
  muestran si están palabra por palabra en el informe, con enlace. Al lado, un índice por
  industria que calcula FinView: la exposición β de cada ocupación según Eloundou et al.
  (Science 2024, datos MIT) ponderada por el empleo de cada industria (BLS OEWS) y por los
  ingresos de cada segmento. No es una puntuación ni una probabilidad de cierre.

## Monitor de Opciones

Módulo independiente accesible en `/options`. Funcionalidades implementadas:

### Fuentes de datos
- **Yahoo Finance** — opciones globales (hasta 3 vencimientos, ~6 semanas)
- **MEFF** — scraping HTML directo de meff.es, 30 tickers `.MC` (Ibex-35 blue chips + extended coverage verificados mayo 2026): TEF, BBVA, SAN, IBE, ITX, REP, FER, RED, NTGY, AENA, ACX, AMS, ANA, BKT, CABK, CIE, CLNX, COL, ELE, ENG, GRF, IAG, IDR, MAP, MEL, MRL, PHM, SAB, SLR, VIS
- **Eurex** — RDF (Reference Data File) diario para opciones europeas (.DE, .PA, .AS, .L, .MI…)

### Pipeline del agente (por ciclo)
1. **Observe** — fetch options chain por ticker (caché 5 min TTL)
2. **Greeks** — Delta, Gamma, Theta, Vega, Rho via Black-Scholes (`greeks_calculator.py`)
3. **Analyze** — reglas IV/P·C ratio/skew/volumen inusual (`options_analyzer.py`)
4. **Premium Spike** — prima de cada contrato contra su propio cierre anterior (Yahoo, MEFF; Eurex no publica cierre previo); ≥ 2.5× → alerta HIGH
5. **Store** — snapshot a DB + alertas + actividad inusual + señal de backtest (HIGH/MEDIUM)
6. **Análisis IA** — vía OpenRouter (`FINVIEW_OPENROUTER_MODEL`, default `deepseek/deepseek-v4-flash`; en producción `deepseek/deepseek-v4.1-flash`), estructurado en 7 secciones (sólo si hay alertas y `FINVIEW_OPENROUTER_API_KEY` configurada)
7. **Notify** — ntfy.sh (push) + Email SMTP + Telegram Bot (spikes premium)
8. **Backtest** — `evaluate_pending()` llena outcomes a +1d/+3d/+7d en el siguiente ciclo

### Análisis Claude (7 secciones)
El prompt `_CLAUDE_SYSTEM` define al agente *VolatilityEdge*. Responde siempre en español, máx. 750 palabras:
1. Resumen Ejecutivo — sentimiento global del ciclo
2. Smart Money — flujos institucionales detectados
3. Señales Greeks — IV vs HV, skew, Delta/Gamma relevantes
4. Tickers con más actividad — máx. 3, descripción de los datos y nivel de riesgo (no es una selección para invertir)
5. Catalizadores — eventos próximos que afectan al watchlist
6. Contexto MEFF — solo si hay tickers `.MC`
7. Gestión de Riesgo — cierre siempre con esta sección

### HV para tickers MEFF
`_fetch_meff()` calcula la volatilidad histórica vía `yf.Ticker(ticker).history(period="60d")` y `log(Close/Close.shift(1)).std() × √252 × 100`, rellenando el campo `historical_volatility` que MEFF no publica.

### UI — página `/options` (5 tabs)
| Tab | Contenido |
|-----|-----------|
| **Watchlist** | La lista única. Cartera y Watchlist eran tabs separadas hasta que se fusionaron: las posiciones se auto-sincronizan en la watchlist, así que enseñaban los mismos tickers dos veces. Una fila **por ticker** (no por lote de bróker), con Sentimiento, P/C, badge IV/HV y los lotes dentro |
| **Monitor** | El hub de alertas: **Alertas** (opciones), **Smart Money** (actividad inusual) y **Técnico** (rupturas de zona desde Zonas Clave). Cada alerta lleva chips a la sección relevante |
| **Backtesting** | Tasas de acierto por horizonte (+1d/+3d/+7d), por tipo de señal y por régimen macro |
| **IA** | Último informe del agente en cards (una por sección) + chat |
| **Agente** | Estado del scheduler, métricas del último ciclo |

### Stats bar global
Calcula P/C ratio (volumen) sobre todos los tickers del watchlist; muestra sentimiento agregado "Alcista / Neutral / Bajista" con color.

### HV vs IV — badge visual
En el acordeón de cartera: compara `avg_call_iv` con `historical_volatility`; muestra badge "IV cara" (rojo), "IV barata" (verde) o "IV normal" (gris) con threshold ±5 puntos.

## Arquitectura de señales — trigger / execution / thesis

Las tres secciones de mercado tienen **una capa cada una**. Los enlaces cruzan la
frontera; el contenido no.

| Capa | Página | Responsabilidad | Prohibido |
|------|--------|-----------------|-----------|
| **Trigger** | Zonas Clave | Análisis técnico; emite señales de ruptura | Contenido de opciones |
| **Execution** | Options Monitor | PUT/CALL y estrategias sobre los disparos | Fundamentales, tesis |
| **Thesis** | Ideas | La oportunidad: dirección, fundamentales, macro, backtest | Contenido de opciones |

Las tres leen `?ticker=` para que los enlaces cruzados aterricen enfocados.

**Los tres pipelines corren en producción por Cloud Scheduler, no por el APScheduler
de la UI** — ese muere al escalar a cero. Ver [docs/deployment.md](docs/deployment.md).

## Zonas Clave — análisis técnico y capa de disparo

Motor de soportes/resistencias. El **análisis** es TA puro sin IA; la **emisión de
señales** construida encima sí llama a un LLM.

**Pipeline:** `fetch_history (20y) → zone_window (10y) → detect_pivots → cluster_pivots →
compute_zone_strength → RSI/MACD/MAs → trend_bias → ZonasClaveAnalysis → señales técnicas`

**Dos ventanas a propósito:** se descargan 20 años (el scope MAX del gráfico los necesita)
pero las zonas se detectan sobre los últimos **10** — un nivel tocado por última vez hace
15 años no es soporte hoy, y los niveles viejos acumulan toques solo por haber tenido más
tiempo. La mediana de volumen se mide en la misma ventana recortada: es el denominador de
`vol_score`, y medirla a 20y infravaloraba las zonas actuales (SAN.MC: 62.5M vs 43.5M).

### Señales técnicas

```
zonas → zone_proximity  (determinista, 2%, gratis)
      → zone_scorer     (LLM, solo candidatos)
      → TechnicalSignal (TODOS los candidatos puntuados)
      → alerted + BacktestSignal (solo > 70)
```

- **La dirección sale de qué lado del nivel está el precio, no de `zone_type`.** Una
  "resistencia" que el precio ya superó actúa como soporte: fiarse de la etiqueta
  histórica invierte la dirección en cada nivel volteado.
- **El corte del 70% no está calibrado** — un "73%" de un LLM es una opinión con un número
  pegado. Por eso se guardan también los sub-umbral: es la única forma de comprobar luego
  si >70 rompe más que <70. `GET /zonas-clave/signals` devuelve todo; `alerted_only=true`
  es la vista del Monitor.
- **`break_probability = NULL` significa "sin puntuar"**, no "no romperá". Nunca se
  coerciona a 0.

## Ideas (`/geo-intel`) — la mesa de tesis

Puerto de WorldHawk: eventos geopolíticos y naturales → señales de mercado. 93 reglas /
49 regiones, 8 fuentes de ingesta (cada clave opcional; una que falte degrada esa fuente
a vacío).

Entre ellas, tres **cuencas de materia prima** (cocoa en Costa de Marfil/Ghana, hierro en
Pilbara, litio en el triángulo Atacama/Puna): cajas estrechas de un solo subyacente,
recortadas a propósito dentro de otras más amplias. La del litio solapa con `chile_mining`
**queriendo** — un terremoto en Atacama lleva a la vez la tesis del cobre y la del litio.

**La ruta, la tabla `geo_signals` y el prefijo de API mantienen el nombre `geo`** — solo
cambió la etiqueta de UI. Renombrar la ruta rompe deep links; renombrar tablas es DDL en
prod sin Alembic.

**Pipeline:** `ingest → sentinel → analyst (LLM si importancia ≥60) → reglas compuestas →
advisor (score + dedup + persist) → notify → auditor`

El panel de señal muestra: importancia/confianza/riesgo/dirección, **"Why this was
triggered"** (cada regla con su tesis y confianza), tickers afectados con dirección
propia, los **5 checkpoints** de backtest (1h/6h/1d/3d/7d), y por ticker: gráfico de
precio + **fundamentales** + botón "Añadir a Zonas Clave".

**Los fundamentales son contexto para una tesis humana, jamás entrada de una señal, un
score o un gate.** `yfinance .info` está scrapeado y sin contrato estable: todos los
campos son opcionales y la tarjeta se esconde si no hay nada.

## Inversiones Alternativas

Módulo de seguimiento manual de inversiones de banca privada, accesible en `/alt-investments`. MVP sin IA ni importación — CRUD puro + métricas.

### Tipos soportados
Private Equity, Venture Capital, Real Estate, Hedge Fund, Producto Estructurado, Otro.

### Datos por posición
Capital comprometido, desembolsado (called), distribuido y NAV actual se guardan como **agregados** (no hay sub-tabla de movimientos). Además: gestora/banco, año vintage, geografía, divisa, estado (Activa/Realizada) y notas.

### Métricas derivadas (calculadas, nunca almacenadas)
- **TVPI** = (distribuido + NAV) / called
- **DPI** = distribuido / called · **RVPI** = NAV / called
- **Unfunded** = comprometido − called · **Valor total** = distribuido + NAV
- `/summary` agrega los totales de la cartera y la asignación (ponderada por NAV) por tipo, geografía y divisa.

### UI — página `/alt-investments`
Tarjetas de resumen + barras de asignación por tipo + tabla de posiciones con métricas por fila + formulario inline para añadir/editar.

### Buscador (catálogo CNMV)
Barra de búsqueda en la parte superior: busca fondos registrados en la **CNMV** por nombre o ISIN y, al seleccionar un resultado, pre-rellena el formulario (nombre, tipo, gestora, ISIN; importes siempre manuales). Los datos provienen del registro mensual gratuito "información individual de IIC" de la CNMV (`services/cnmv_catalog.py`) — ~3.000 ISINs de clase sobre ~1.400 fondos — cacheados en la tabla `alt_investment_catalog`. En Cloud Run se refrescan desde el job diario de zonas si están obsoletos (>7 días); localmente se mantiene el hilo de startup.

Cada fondo se enriquece con su **NAV por participación** y **patrimonio (tamaño del fondo)** del fichero `FONDMENS` (mismo ZIP). Los resultados muestran NAV y patrimonio; se puede **ordenar** por patrimonio/NAV y filtrar por **patrimonio mínimo**, e incluso **explorar** (p. ej. los fondos más grandes) sin escribir un nombre. NAV y patrimonio son los únicos campos que publica una fuente pública gratuita — las métricas de PE (DPI/TVPI/IRR/vintage/commitment/hurdle) son privadas y se introducen a mano. SICAV, IIC inmobiliarias, hedge funds y capital riesgo (PE/VC) están en registros CNMV separados y quedan para fases posteriores.

### Tipos de cambio (ECB)
`services/exchange_rates.py` cachea los tipos de referencia oficiales del BCE en la tabla `exchange_rates` como fallback para conversiones IRPF cuando el archivo del broker no trae el tipo (o para entradas manuales). En Cloud Run sincroniza en el job diario de zonas; localmente, en el startup (historia completa el primer boot, luego feed de 90 días). `get_rate()` es solo-DB con fallback ±7 días para fines de semana/festivos.

## API

Base URL: `http://localhost:8000/api`

### Auth
- `POST /auth/register` — Registro; exige `accept_terms: true` (límite: 3 req/min por IP)
- `POST /auth/login` — Login (límite: 5 req/min por IP)
- `GET /auth/me` — Usuario autenticado actual (incluye `terms_accepted`)

### Cuenta del usuario (derechos RGPD)
- `POST /users/me/accept-terms` — Registra la aceptación de las condiciones vigentes
- `GET /users/me/export` — Descarga todos los datos del usuario en JSON
- `POST /users/me/delete` — Elimina la cuenta y todos sus datos (pide la contraseña; límite 5 req/min)

### Imports
- `POST /imports/tr` — Trade Republic PDF o CSV (dispatch por extensión)
- `POST /imports/degiro` — DEGIRO PDF  
- `POST /imports/ibkr` — IBKR CSV
- `POST /imports/ing` — ING PDF
- `POST /imports/bbva` — BBVA PDFs (1-3 archivos)
- `POST /imports/etoro` — eToro XLSX
- `GET /imports/` — Listar importaciones
- `DELETE /imports/{id}` — Eliminar importación

### Consultas
- `GET /transactions/?fiscal_year=2024` — Transacciones
- `GET /transactions/dividends/summary?fiscal_year=2024` — Dividendos agregados
- `GET /transactions/capital-gains?fiscal_year=2024` — Ganancias realizadas

### Fiscal
- `GET /fiscal/casillas?fiscal_year=2024` — Casillas Modelo 100/714
- `GET /fiscal/summary/2024` — Resumen fiscal completo
- `GET /fiscal/cross-broker-lots/2024` — Lotes FIFO cruzados
- `GET /fiscal/fifo-adjustments?fiscal_year=2024` — Ajustes FIFO v2 y desglose 332/337
- `GET /fiscal/fx-rate?currency=USD&on=2024-01-02` — Tipo de cambio ECB (fallback ±7 días)

### Mundo vivo (`/living-world/...`)
- `GET /living-world/world` — Solo lectura: un edificio por ISIN (agregado entre brokers) con valor, peso, coste, P/L, tipo y sector guardados. Lo desconocido es `null`, nunca 0; sin llamadas a Yahoo

### Inversiones Alternativas (`/alt-investments/...`)
- `GET /alt-investments/` — Listar posiciones (con TVPI/DPI/RVPI/unfunded por fila)
- `GET /alt-investments/summary` — Consolidación + asignación por tipo/geografía/divisa
- `GET /alt-investments/search?q=&type=&sort=&min_fund_size=` — Buscar/explorar el catálogo CNMV (nombre o ISIN; orden por patrimonio/NAV; incluye NAV y tamaño del fondo)
- `POST /alt-investments/` — Crear posición
- `PATCH /alt-investments/{id}` — Actualizar posición
- `DELETE /alt-investments/{id}` — Eliminar posición

### Gráficas
- `GET /charts/dividends-by-country` · `dividends-monthly` · `top-dividend-payers`
- `GET /charts/capital-gains-breakdown` · `patrimonio-composition`
- `GET /charts/dividend-yield` · `withholdings-by-country` · `company-dividends-yearly`

### Opciones (`/options/...`)
- `GET /options/snapshots` — Últimas snapshots por ticker
- `GET /options/alerts` — Alertas del ciclo actual
- `GET /options/unusual` — Actividad inusual detectada
- `GET /options/backtest` — Señales + outcomes +1d/+3d/+7d
- `GET /options/agent/status` — Estado del scheduler y último ciclo
- `GET /options/agent/last-analysis` — `claude_analysis` + metadatos del último ciclo
- `POST /options/agent/chat` — Chat con el agente (contexto de alertas recientes)
- `POST /options/watchlist` — Añadir ticker
- `DELETE /options/watchlist/{ticker}` — Eliminar ticker
- `GET /options/watchlist` — Listar watchlist

## Tests

```bash
pytest
```

**Backend:** 1762 tests, todos en `backend/tests/` (lo fija `testpaths` en `pyproject.toml`).
Con los PDFs/CSVs reales en `files/` pasan todos; esos ficheros no están en el repo, y donde
faltan (CI, un worktree sin enlazar `files/`) los 148 tests que los requieren salen como skipped.

**Frontend:**

```bash
cd frontend && pnpm test
```

185 tests sobre lógica pura: `src/lib/`, `src/app/blog/posts.test.ts`,
`src/app/options/optionsData.test.ts` (el reducer de estado de la página de opciones) y
`src/game/garden/` (las reglas del juego del jardín de la landing). Requiere `pnpm install` —
sin `vitest` instalado, `pnpm build` falla en `vitest.config.ts` aunque la app compile bien.

## Despliegue y CI/CD

Ver [docs/deployment.md](docs/deployment.md) para el esquema completo (Vercel + Cloud Run + Neon + Cloud Build), env vars requeridas, y cómo actualizar secretos.

**Flujo:** commit local → push a `main` → Vercel redesplaza frontend automáticamente; Cloud Build crea `finview-api` como candidato privado sin tráfico, valida puerto/configuración/startup y solo entonces lo promueve. Si la validación pública falla, revierte el tráfico. Neon es la base de datos compartida y no se despliega.

En producción, `FINVIEW_ENV=production` activa la validación de secretos en startup y los endpoints de auth están limitados por IP (ver [docs/deployment.md](docs/deployment.md)).

### Variables de entorno — módulo opciones (nuevas)

Todas llevan prefijo `FINVIEW_` (`env_prefix` en [backend/config.py](backend/config.py)).
Sin prefijo **no se leen** y el módulo degrada en silencio.

| Variable | Descripción |
|----------|-------------|
| `FINVIEW_CRON_SECRET` | **Obligatoria en prod.** Secreto compartido con Cloud Scheduler. Sin ella los pipelines no corren — ver [docs/deployment.md](docs/deployment.md) |
| `FINVIEW_OPENROUTER_API_KEY` | Habilita el análisis IA (opcional — sin ella el ciclo sigue, sin informe, y las señales técnicas se guardan sin puntuar) |
| `FINVIEW_OPENROUTER_MODEL` | Modelo compartido. Default `deepseek/deepseek-v4-flash` (producción: `deepseek/deepseek-v4.1-flash`) |
| `FINVIEW_FRED_API_KEY` | Tipo libre de riesgo por divisa + régimen macro (opcional, gratuita) |
| `FINVIEW_TELEGRAM_BOT_TOKEN` | Token del bot de Telegram para notificaciones de spikes |
| `FINVIEW_TELEGRAM_CHAT_ID` | Chat ID destino de las notificaciones Telegram |
| `FINVIEW_NTFY_TOPIC` | Topic de ntfy.sh para push notifications |
| `FINVIEW_NOTIFY_EMAIL_FROM` | Cuenta Gmail origen para digest de alertas |
| `FINVIEW_NOTIFY_EMAIL_PASSWORD` | Contraseña de aplicación Gmail |
| `FINVIEW_NOTIFY_EMAIL_TO` | Destinatario del digest |
