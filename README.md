# FinView

Dashboard de inversiones personales con importación multi-broker y motor fiscal IRPF español.

## Stack

- **Backend:** FastAPI · SQLAlchemy · SQLite · pdfplumber · openpyxl
- **Frontend:** Next.js 16 · React 19 · TailwindCSS · Recharts
- **Tests:** pytest (128 tests)

## Brokers soportados

| Broker | Formato | Datos extraídos |
|--------|---------|-----------------|
| Trade Republic | PDF (Steuerbericht) | Dividendos, plusvalías, retenciones, casillas, cartera |
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
│   │   └── prices.py         # Cache de precios Yahoo Finance
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/page.tsx       # Dashboard principal (5 tabs)
│       ├── components/        # FileUpload, tablas, stats cards
│       ├── components/charts/ # 8 componentes de gráficas
│       └── lib/               # API client + tipos TypeScript
└── pyproject.toml
```

## Motor fiscal IRPF

- **Modelo 100:** Casillas 27 (intereses), 29 (dividendos), 332 (ganancias >1 año), 337 (pérdidas)
- **Modelo 714:** Casillas 05-09 (patrimonio en el extranjero)
- **FIFO cruzado:** Matching cronológico de compras/ventas entre todos los brokers
- **Retenciones:** Tracking por país con deducciones CDI (15% estándar)
- **Ajustes FIFO:** Diferencia entre P&L del broker y FIFO recalculado

## API

Base URL: `http://localhost:8000/api`

### Imports
- `POST /imports/tr` — Trade Republic PDF
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

## Tests

```bash
pytest tests/ backend/tests/ -v
```

128 tests, 35 skipped (los skipped requieren PDFs/CSVs reales en `files/`).
