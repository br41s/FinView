# FinView

Dashboard de inversiones personales con importación multi-broker, motor fiscal IRPF español y monitor de opciones con agente IA.

## Stack

- **Backend:** FastAPI · SQLAlchemy · pdfplumber · openpyxl · yfinance · anthropic SDK
- **Frontend:** Next.js 15 · React 19 · TailwindCSS · Recharts · NextAuth · shadcn/ui
- **DB:** Neon Postgres (prod) · SQLite (local fallback)
- **Deploy:** Vercel (frontend) · Google Cloud Run `europe-west1` (backend) · Cloud Build trigger (CI)
- **Tests:** pytest (128 tests)

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
│   ├── models.py           # SQLAlchemy ORM (Account, Transaction, TaxLot, etc.)
│   ├── database.py         # Engine + session factory
│   ├── api/
│   │   ├── imports.py      # POST endpoints para cada broker
│   │   ├── transactions.py # GET dividendos, capital gains, listados
│   │   ├── fiscal.py       # GET casillas, resumen fiscal, FIFO lots
│   │   ├── charts.py       # GET datos para gráficas
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
│   │   └── notification_service.py # ntfy.sh + Email SMTP + Telegram Bot
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/page.tsx          # Dashboard principal (5 tabs — inversiones)
│       ├── app/options/page.tsx  # Monitor opciones (6 tabs)
│       ├── components/           # FileUpload, tablas, stats cards
│       ├── components/charts/    # 8 componentes de gráficas
│       └── lib/                  # API client + tipos TypeScript
└── pyproject.toml
```

## Motor fiscal IRPF

- **Modelo 100:** Casillas 27 (intereses), 29 (dividendos), 332 (ganancias >1 año), 337 (pérdidas)
- **Modelo 714:** Casillas 05-09 (patrimonio en el extranjero)
- **FIFO cruzado:** Matching cronológico de compras/ventas entre todos los brokers
- **Retenciones:** Tracking por país con deducciones CDI (15% estándar)
- **Ajustes FIFO:** Diferencia entre P&L del broker y FIFO recalculado

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
4. **Premium Spike** — comparación contra baseline EMA in-memory; multiplier ≥ 2.5× → alerta HIGH
5. **Store** — snapshot a DB + alertas + actividad inusual + señal de backtest (HIGH/MEDIUM)
6. **Claude AI** — `claude-haiku-4-5-20251001`, análisis estructurado en 7 secciones (sólo si hay alertas y `ANTHROPIC_API_KEY` configurada)
7. **Notify** — ntfy.sh (push) + Email SMTP + Telegram Bot (spikes premium)
8. **Backtest** — `evaluate_pending()` llena outcomes a +1d/+3d/+7d en el siguiente ciclo

### Análisis Claude (7 secciones)
El prompt `_CLAUDE_SYSTEM` define al agente *VolatilityEdge*. Responde siempre en español, máx. 750 palabras:
1. Resumen Ejecutivo — sentimiento global del ciclo
2. Smart Money — flujos institucionales detectados
3. Señales Greeks — IV vs HV, skew, Delta/Gamma relevantes
4. Top Picks — máx. 3 tickers con tesis y nivel de riesgo
5. Catalizadores — eventos próximos que afectan al watchlist
6. Contexto MEFF — solo si hay tickers `.MC`
7. Gestión de Riesgo — cierre siempre con esta sección

### HV para tickers MEFF
`_fetch_meff()` calcula la volatilidad histórica vía `yf.Ticker(ticker).history(period="60d")` y `log(Close/Close.shift(1)).std() × √252 × 100`, rellenando el campo `historical_volatility` que MEFF no publica.

### UI — página `/options` (6 tabs)
| Tab | Contenido |
|-----|-----------|
| **Cartera** | Posiciones abiertas con P&L, métricas IV/HV, badge "IV cara/barata", chain desplegable (calls + puts) |
| **Watchlist** | Gestión de tickers monitorizados; sentiment global P/C en stats bar |
| **Alertas** | Todas las alertas del ciclo filtradas por severidad |
| **Backtest** | Tasas de acierto por horizonte (+1d/+3d/+7d) y por tipo de señal |
| **Análisis** | Último análisis Claude renderizado en 7 cards (una por sección), con metadatos del ciclo |
| **Agente** | Estado del scheduler, métricas del último ciclo, chat con el agente |

### Stats bar global
Calcula P/C ratio (volumen) sobre todos los tickers del watchlist; muestra sentimiento agregado "Alcista / Neutral / Bajista" con color.

### HV vs IV — badge visual
En el acordeón de cartera: compara `avg_call_iv` con `historical_volatility`; muestra badge "IV cara" (rojo), "IV barata" (verde) o "IV normal" (gris) con threshold ±5 puntos.

## API

Base URL: `http://localhost:8000/api`

### Auth
- `POST /auth/register` — Registro (límite: 3 req/min por IP)
- `POST /auth/login` — Login (límite: 5 req/min por IP)
- `GET /auth/me` — Usuario autenticado actual

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
pytest tests/ backend/tests/ -v
```

128 tests, 35 skipped (los skipped requieren PDFs/CSVs reales en `files/`).

## Despliegue y CI/CD

Ver [docs/deployment.md](docs/deployment.md) para el esquema completo (Vercel + Cloud Run + Neon + Cloud Build), env vars requeridas, y cómo actualizar secretos.

**Flujo:** commit local → push a `main` → Vercel redesplaza frontend automáticamente; Cloud Build redesplaza `finview-api` en Cloud Run cuando el push toca `backend/**`, `Dockerfile`, `pyproject.toml` o `cloudbuild.yaml`. Neon es la base de datos compartida y no se despliega.

En producción, `FINVIEW_ENV=production` activa la validación de secretos en startup y los endpoints de auth están limitados por IP (ver [docs/deployment.md](docs/deployment.md)).

### Variables de entorno — módulo opciones (nuevas)

| Variable | Descripción |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Habilita análisis Claude (opcional — sin ella el ciclo sigue funcionando) |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram para notificaciones de spikes |
| `TELEGRAM_CHAT_ID` | Chat ID destino de las notificaciones Telegram |
| `NTFY_TOPIC` | Topic de ntfy.sh para push notifications |
| `NOTIFY_EMAIL_FROM` | Cuenta Gmail origen para digest de alertas |
| `NOTIFY_EMAIL_PASSWORD` | Contraseña de aplicación Gmail |
| `NOTIFY_EMAIL_TO` | Destinatario del digest |
