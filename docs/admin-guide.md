# Guía de administración — FinView

---

## 1. Stack de producción

| Componente | Tecnología | URL / Recurso |
|------------|-----------|---------------|
| Frontend | Next.js 16 + Vercel | https://fin-view-topaz.vercel.app |
| Backend | Python 3.12 + FastAPI + Cloud Run (europe-west1) | finview-api-748911075551.europe-west1.run.app |
| Base de datos | Neon Postgres (eu-central-1) | ep-mute-rain-alwkqvfz |
| CI/CD | Cloud Build (trigger automático en push a main) | Proyecto: finview-brais-2026 |
| Auth | NextAuth 5.0 (JWT) | — |
| Pagos | Stripe | — |
| IA | Anthropic Claude API (claude-haiku-4-5) | — |
| Push | ntfy.sh | — |

### Notas críticas de producción

- `BACKEND_URL` en Vercel es build-time: **redeploy manual** si cambia la URL del backend.
- `AUTH_SECRET` en Vercel debe ser idéntico a `FINVIEW_AUTH_SECRET` en Cloud Run.
- Cloud Build solo se dispara si hay cambios en: `backend/`, `Dockerfile`, `pyproject.toml`, `cloudbuild.yaml`.
- El FIFO cruzado se recalcula en cada import/delete — nunca omitirlo.

---

## 2. Desarrollo local

### Requisitos

- Python 3.12+
- Node.js 20+ / pnpm 10+
- ~200 MB disco

### Instalación

```bash
git clone <repo-url> FinView && cd FinView

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && pnpm install && cd ..
```

### Ejecución

```bash
# Backend (puerto 8000, hot-reload)
uvicorn backend.app:app --reload --port 8000

# Frontend (puerto 3000, turbopack)
cd frontend && pnpm dev
```

La base de datos SQLite se crea automáticamente en `data/finview.db` al arrancar el backend.

---

## 3. Variables de entorno

### Backend (Cloud Run / `.env` local)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `FINVIEW_DATABASE_URL` | `sqlite:///finview.db` | URL de la base de datos |
| `FINVIEW_AUTH_SECRET` | `change-me` | Debe coincidir con `AUTH_SECRET` del frontend |
| `FINVIEW_SECRET_KEY` | `change-me` | JWT signing key |
| `FINVIEW_JWT_EXPIRE_MINUTES` | `10080` (7 días) | Expiración del token JWT |
| `FINVIEW_STRIPE_SECRET_KEY` | — | Clave secreta Stripe |
| `FINVIEW_STRIPE_WEBHOOK_SECRET` | — | Webhook Stripe |
| `FINVIEW_STRIPE_PRICE_PRO` | — | Price ID plan Pro |
| `FINVIEW_STRIPE_PRICE_UNLIMITED` | — | Price ID plan Unlimited |
| `FINVIEW_FRONTEND_URL` | `http://localhost:3000` | URL del frontend (para redirects Stripe) |
| `FINVIEW_ANTHROPIC_API_KEY` | — | Claude API key (opcional — activa análisis IA en opciones) |
| `FINVIEW_NTFY_TOPIC` | — | Topic ntfy.sh para push notifications |
| `FINVIEW_NOTIFY_EMAIL_TO` | — | Email destino de alertas |
| `FINVIEW_NOTIFY_EMAIL_FROM` | — | Email origen (Gmail) |
| `FINVIEW_NOTIFY_EMAIL_PASSWORD` | — | App password de Gmail |
| `FINVIEW_OPTIONS_MONITOR_INTERVAL_MINUTES` | `15` | Frecuencia del agente de opciones |

### Frontend (Vercel / `.env.local`)

| Variable | Descripción |
|----------|-------------|
| `NEXTAUTH_URL` | URL pública del frontend |
| `AUTH_SECRET` | Debe coincidir con `FINVIEW_AUTH_SECRET` |
| `BACKEND_URL` | URL base del backend (build-time) |
| `NEXT_PUBLIC_STRIPE_PRICE_PRO` | Price ID Stripe plan Pro |
| `NEXT_PUBLIC_STRIPE_PRICE_UNLIMITED` | Price ID Stripe plan Unlimited |

---

## 4. Base de datos

### Esquema de tablas

| Tabla | Descripción |
|-------|-------------|
| `users` | Usuarios registrados |
| `accounts` | Cuentas por broker (una por broker importado) |
| `import_records` | Registro de importaciones (hash SHA-256 para deduplicación) |
| `transactions` | Todas las operaciones: BUY, SELL, DIVIDEND, INTEREST, FEE, SPINOFF |
| `tax_lots` | Lotes FIFO por broker |
| `tax_results` | Casillas Modelo 100/714 precalculadas |
| `cross_broker_lots` | Lotes FIFO cruzados entre todos los brokers |
| `fifo_adjustments` | Diferencias FIFO broker vs. FIFO cruzado |
| `option_assignments` | Asignaciones de opciones detectadas en IBKR |
| `portfolio_holdings` | Holdings a fin de año por broker |
| `price_cache` | Cache de precios Yahoo Finance |
| `data_issues` | Avisos del supervisor de datos por importación |
| `watchlist_items` | Tickers en watchlist por usuario (monitor de opciones) |
| `options_snapshots` | Snapshots de cadena de opciones por ciclo |
| `options_alerts` | Alertas generadas por el agente de opciones |
| `unusual_activity` | Actividad inusual detectada (smart money) |
| `options_agent_logs` | Log de cada ciclo del agente |

### Orden de borrado (FK constraints)

Al eliminar una importación (`import_records`), el orden de borrado debe ser:
1. `cross_broker_lots` (referencia a `transactions.id`)
2. `tax_lots` (referencia a `transactions.id`)
3. `transactions`
4. `tax_results`
5. `fifo_adjustments`
6. `option_assignments`
7. `portfolio_holdings`
8. `data_issues`
9. `import_records`

### Reset de la DB (local)

```bash
rm data/finview.db
# Reiniciar el backend — se recrea automáticamente
```

---

## 5. Agente de opciones

El agente (`backend/services/options_agent.py`) es un worker APScheduler que corre dentro del proceso FastAPI.

### Arquitectura

```
WatchlistItem (DB)
    └─► fetch_options (Yahoo Finance / MEFF)
    └─► enrich_options_with_greeks (Black-Scholes)
    └─► analyze_ticker (alertas, unusual activity, sentiment)
    └─► OptionsSnapshot, OptionsAlert, UnusualActivity (DB)
    └─► _run_claude_analysis (opcional, claude-haiku-4-5-20251001)
    └─► OptionsAgentLog (DB)
    └─► notify_alerts (ntfy.sh + email)
```

### Fuentes de datos

- **Yahoo Finance** (`yfinance`): tickers US/EU sin sufijo `.MC`.
- **MEFF** (`requests` + `BeautifulSoup`): tickers con sufijo `.MC` (bolsa española). Usa proxy `allorigins.win` para evitar bloqueos CORS.

### Greeks (Black-Scholes)

Implementados en `backend/services/greeks_calculator.py` sin dependencias externas (solo `math`).  
Parámetros por defecto: r = 5.3%, q = 1.3%, 252 días de trading.

### Umbrales de alerta

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `HIGH_IV_THRESHOLD` | 50% | IV media alta |
| `HIGH_PCR_THRESHOLD` | 1.5 | P/C ratio bajista |
| `LOW_PCR_THRESHOLD` | 0.5 | P/C ratio alcista |
| `IV_SKEW_THRESHOLD` | 10 pp | Diferencia IV puts-calls |
| `IV_PREMIUM_RATIO` | 1.5× | IV vs. volatilidad histórica |
| `UNUSUAL_VOLUME_RATIO` | 3.0× | Volumen / Open Interest |

### Análisis Claude

- Modelo: `claude-haiku-4-5-20251001`
- Temperatura: 0.3 (analítico)
- Max tokens: 1024
- Activación: solo si `FINVIEW_ANTHROPIC_API_KEY` está configurado Y existen alertas en el ciclo
- Output: texto narrativo en español, truncado a 5000 caracteres en DB

### Endpoints de control

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/options/agent/run` | Ciclo manual inmediato |
| `GET` | `/options/agent/status` | Estado del scheduler, último ciclo, total ciclos |
| `POST` | `/options/agent/start` | Arrancar job periódico APScheduler |
| `POST` | `/options/agent/stop` | Parar job periódico |

---

## 6. Motor FIFO cruzado

El motor en `backend/services/fifo_engine.py`:

1. Recopila todas las compras y ventas de todos los brokers para un año fiscal.
2. Ordena cronológicamente por fecha de trade.
3. Matching FIFO: para cada venta, consume las compras más antiguas primero.
4. Lotes parciales: si una compra no se consume entera, queda remainder para futuras ventas.
5. Periodo de tenencia: <1 año → casilla 332, ≥1 año → casilla 337.
6. Persiste `CrossBrokerLot` y `FIFOAdjustment` en BD.

Se recalcula automáticamente en cada import y delete.

---

## 7. Tests

```bash
# Todos los tests
pytest backend/tests/ -v

# Solo un módulo
pytest backend/tests/test_fifo_engine.py -v

# Con cobertura
pytest backend/tests/ --cov=backend --cov-report=term-missing
```

Los tests que necesitan archivos reales (PDFs/CSVs en `files/`) se saltan automáticamente si no existen.

---

## 8. Añadir un nuevo broker

### 8.1 Parser

Crear `backend/importers/<broker>.py`:

```python
from dataclasses import dataclass, field
from pathlib import Path
from backend.importers.base import ParsedTransaction, ParsedPortfolioHolding

@dataclass
class NewBrokerReport:
    fiscal_year: int
    transactions: list[ParsedTransaction] = field(default_factory=list)
    dividends: list[ParsedTransaction] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)

def parse_new_broker(file_path: Path) -> NewBrokerReport: ...
def compute_file_hash(path: Path) -> str: ...
```

### 8.2 Broker enum

En `backend/models.py`:
```python
class Broker(str, Enum):
    NEW_BROKER = "NEW_BROKER"
```

### 8.3 Import service

En `backend/services/import_service.py`, añadir `import_new_broker_report()` siguiendo el patrón existente:
1. `_check_duplicate()` → hash SHA-256
2. `_check_year_duplicate()` → broker + año
3. `_get_or_create_account()`
4. Crear `ImportRecord`
5. Insertar transacciones, holdings, casillas
6. `recalculate_cross_broker_fifo(db, fiscal_year)`
7. `_run_supervisor(db, import_rec.id)`
8. `db.commit()`

### 8.4 Endpoint API

En `backend/api/imports.py`:
```python
@router.post("/new-broker", response_model=ImportResult)
def upload_new_broker(file: UploadFile, db: DbSession, user: CurrentUser): ...
```

### 8.5 Frontend

En `frontend/src/lib/api.ts`:
```typescript
export async function uploadNewBrokerReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  return fetchApi("/imports/new-broker", { method: "POST", body: form });
}
```

En `frontend/src/components/FileUpload.tsx`:
1. Añadir `detectBroker()` — detección por nombre de archivo.
2. Añadir entrada en `BROKERS` con key, label, accept y color.
3. Mapear en `uploadBroker()` si no es BBVA.

---

## 9. Supervisor de datos

`backend/services/data_supervisor.py` ejecuta checks de calidad tras cada import:

- Detecta ISINs sin precio de mercado
- Valida coherencia de retenciones
- Marca auto-resoluciones cuando es posible

Los avisos se almacenan en `data_issues` y se muestran en el UI tras la importación.

---

## 10. Troubleshooting

**Error 500 al borrar importación**  
Causa más común: FK violation en `cross_broker_lots` (referencias a transacciones). El orden de borrado en `_delete_import_data` debe eliminar CrossBrokerLots antes que Transactions.

**"duplicate import"**  
El archivo ya fue importado (mismo hash SHA-256). Eliminar la importación anterior primero.

**"year already imported"**  
Ya existe importación del mismo broker + año. La nueva importación reemplaza automáticamente.

**Casillas no cuadran**  
Comparar el FIFO cruzado (pestaña casillas) con el del broker individual. Los ajustes FIFO explican las diferencias.

**Frontend no conecta al backend**  
Verificar `BACKEND_URL` en Vercel y que CORS en `backend/app.py` incluye el dominio del frontend.

**Agente de opciones no genera análisis Claude**  
Verificar que `FINVIEW_ANTHROPIC_API_KEY` está configurado en Cloud Run y que existe al menos un ticker en la watchlist con alertas activas.

**MEFF no devuelve datos**  
El proxy `allorigins.win` puede estar caído. El agente hace fallback a Yahoo Finance para el precio y devuelve `None` para la cadena de opciones.
