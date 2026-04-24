# FinView — Dashboard de Inversiones con Brokers Reales

## Pendiente de revisión

- [ ] **Animación landing page no reproduce en carga inicial** — La animación SVG (tronco/ramas/flores) solo se ve al pulsar "repetir". Fix intentado: mover keyframes a `globals.css` + `useEffect(() => setReplayCount(c=>c+1), [])` en `FinviewIntro/index.tsx`. Causa probable: race condition SSR/CSS en dev mode. Comprobar en producción; si persiste en dev, inspeccionar Network waterfall de `globals.css` vs primera pintura del SVG.

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
