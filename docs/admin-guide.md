# Guía de administración — FinView

## 1. Requisitos

- Python 3.12+
- Node.js 20+ / pnpm 10+
- ~200 MB disco (dependencias + DB)

## 2. Instalación

```bash
git clone <repo-url> FinView && cd FinView

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && pnpm install && cd ..
```

## 3. Ejecución

```bash
# Backend (puerto 8000, hot-reload)
uvicorn backend.app:app --reload --port 8000

# Frontend (puerto 3000, turbopack)
cd frontend && pnpm dev
```

La base de datos SQLite se crea automáticamente en `data/finview.db` al arrancar el backend.

## 4. Estructura de la base de datos

| Tabla | Descripción |
|-------|-------------|
| `accounts` | Cuentas por broker (1 por broker importado) |
| `transactions` | Todas las operaciones (buy, sell, dividend, interest, fee, spinoff) |
| `tax_lots` | Lotes FIFO por broker |
| `tax_results` | Resultados fiscales precalculados (casillas Modelo 100/714) |
| `cross_broker_lots` | Lotes FIFO cruzados entre todos los brokers |
| `fifo_adjustments` | Diferencias entre FIFO broker y FIFO cruzado por ISIN |
| `import_records` | Registro de importaciones (hash para deduplicación) |
| `option_assignments` | Asignaciones de opciones detectadas (IBKR) |
| `portfolio_holdings` | Holdings a fin de año por broker |
| `price_cache` | Cache de precios Yahoo Finance |

### Reset de la DB

```bash
rm data/finview.db
# Reiniciar backend — se recrea automáticamente
```

## 5. Tests

```bash
# Todos los tests
pytest tests/ backend/tests/ -v

# Solo un módulo
pytest backend/tests/test_fifo_engine.py -v

# Con cobertura
pytest tests/ backend/tests/ --cov=backend --cov-report=term-missing
```

Tests que requieren archivos reales (PDFs/CSVs en `files/`) se marcan como `skip` si no existen.

## 6. Añadir un nuevo broker

### 6.1 Crear el parser

Crear `backend/importers/<broker>.py`:

```python
from pathlib import Path
from backend.importers.base import (
    ParsedTransaction, ParsedPortfolioHolding, TxType, country_from_isin
)

@dataclass
class NewBrokerReport:
    fiscal_year: int
    transactions: list[ParsedTransaction]
    holdings: list[ParsedPortfolioHolding]
    # ... otros campos

def parse_new_broker(file_path: Path) -> NewBrokerReport:
    # Implementar parsing
    ...

def compute_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

### 6.2 Añadir el Broker enum

En `backend/models.py`:
```python
class Broker(str, Enum):
    ...
    NEW_BROKER = "NEW_BROKER"
```

### 6.3 Crear función de importación

En `backend/services/import_service.py`, añadir `import_new_broker_report()` siguiendo el patrón de los existentes:
1. Check duplicados (hash + año fiscal)
2. Crear/obtener cuenta
3. Insertar transacciones, holdings, casillas
4. Triggear FIFO cruzado: `recalculate_cross_broker_fifo(db, fiscal_year)`

### 6.4 Añadir endpoint API

En `backend/api/imports.py`:
```python
@router.post("/new-broker", response_model=ImportResult)
async def upload_new_broker(file: UploadFile, db: Session = Depends(get_db)):
    ...
```

### 6.5 Actualizar frontend

En `frontend/src/components/FileUpload.tsx`:
1. Añadir detección del formato en `detectBroker()`
2. Añadir la extensión aceptada
3. Mapear al endpoint en `uploadFunctions`

En `frontend/src/lib/api.ts`:
```typescript
export async function uploadNewBrokerReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  return fetchApi("/imports/new-broker", { method: "POST", body: form });
}
```

### 6.6 Añadir tests

Crear `backend/tests/test_new_broker.py` con fixtures reales o mock.

## 7. Motor FIFO cruzado

El motor en `backend/services/fifo_engine.py` funciona así:

1. **Recopila** todas las compras y ventas de todos los brokers para un año fiscal
2. **Ordena** cronológicamente (fecha de trade)
3. **Matching FIFO:** Para cada venta, consume las compras más antiguas primero
4. **Lotes parciales:** Si una compra no se consume entera, queda remainder para futuras ventas
5. **Periodo de tenencia:** <1 año → casilla 332 (ganancias), ≥1 año → casilla 337
6. **Persistencia:** Guarda `CrossBrokerLot` y `FIFOAdjustment` en BD

Se recalcula automáticamente cada vez que se importa o elimina datos de cualquier broker.

## 8. Cache de precios

`backend/services/prices.py` mantiene un mapeo de ~200 ISINs a tickers de Yahoo Finance. Los precios se cachean en `price_cache` para evitar llamadas repetidas a la API.

Para añadir ISINs al mapa, editar `_ISIN_TICKER_MAP` en `prices.py`.

## 9. CORS

Configurado en `backend/app.py` para permitir `localhost:3000`. Para producción, actualizar `allow_origins`.

## 10. Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/finview.db` | URL de la base de datos |
| `PORT` | `8000` | Puerto del backend |

## 11. Troubleshooting

**Error "duplicate import":** El archivo ya fue importado (mismo hash SHA-256). Eliminar la importación anterior primero.

**Error "year already imported":** Ya existe una importación del mismo broker para ese año fiscal. Eliminar primero.

**Casillas no cuadran:** Comparar el FIFO cruzado (pestaña casillas) con el del broker individual. Los ajustes FIFO explican las diferencias.

**Frontend no conecta al backend:** Verificar que el backend está en `localhost:8000` y CORS permite `localhost:3000`.
