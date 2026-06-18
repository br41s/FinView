# OptionsAI → FinView migration + Alt-Investments MVP

## Context
- Most OptionsAI functionality already lives in FinView (options agent, fiscal engine,
  importers, fifo, notifications). FinView is generally more advanced.
- Two genuine gaps from OptionsAI: (1) ECB exchange-rate service, (2) synthetic_options (deferred).
- `/alt-investments` in OptionsAI is only a "Próximamente" marketing page — no WIP backend.
  Decision: build MVP slice fresh in FinView (PE/VC/RE positions + manual entry + consolidation).

## Part A — ECB exchange-rate service (port) ✅
- [x] `ExchangeRate` model in models.py (rate_date, currency, rate, source; unique date+currency)
- [x] `backend/services/exchange_rates.py` — SQLAlchemy port: sync_rates, get_rate, to_eur (dialect-aware upsert)
- [x] Background sync on startup (lifespan thread, like Eurex preload)
- [x] `GET /fiscal/fx-rate?currency=&on=` lookup endpoint
- [x] Test: get_rate EUR→1, exact hit, ±7d fallback, unknown ccy, to_eur conversion

## Part B — Alt-Investments MVP ✅
- [x] `AltInvestmentType`/`AltInvestmentStatus` enums + `AltInvestment` model (committed/called/distributed/NAV)
- [x] `backend/api/alt_investments.py` — CRUD + `/summary` (TVPI/DPI/RVPI/unfunded, NAV allocation by type/geo/ccy)
- [x] Register router in app.py
- [x] api.ts: `altInvestments` object + types
- [x] `frontend/src/app/alt-investments/page.tsx` — summary cards + allocation bars + table + inline add/edit form
- [x] Nav entries: app-sidebar.tsx + QuickNav.tsx
- [x] Verify: backend imports OK, 5 new pytest pass + full suite no new failures, tsc clean, HTTP integration test green

## Deferred (not in MVP)
- Structured products + barrier/knock-in alerts (Q3'26 spec)
- Private-bank PDF import (Q4'26 spec)
- AI reporting (Q4'26 spec)
- Capital-call / distribution movement sub-table (aggregates suffice for MVP)
- synthetic_options.py port (low value given 3 real data sources)
