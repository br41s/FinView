---
paths:
  - "backend/importers/**"
  - "backend/services/fifo_engine.py"
  - "backend/services/import_service.py"
  - "backend/services/exchange_rates.py"
  - "backend/api/fiscal.py"
  - "backend/api/imports.py"
---

## Trade Republic importer — formats & migration year

`parse_tr_tax_report()` (tr.py) dispatches by report layout:
- **`legacy`** — pre-2025 full-year Roman-numeral report (Modelo 100 = Section VIII,
  Modelo 714 = IX, Section VI transaction history imported).
- **`tr_de_premigration`** — partial-year report issued when the account moved
  DE→ES IBAN (cover says "migró a un IBAN español"). Same legacy layout but
  Modelo 100 shifts to **Section VII** (no patrimonio/714), Saveback rows count as
  casilla 27, and Section VI is **dropped** (fiscal figures only — its positions
  were transferred to the ES account, which owns the year-end holdings).
- **`es_branch`** — 2025+ Sucursal España report (tr_v2.py, `is_spanish_branch_format`).

A migration year has **two** TR reports (pre + post). They must coexist, not
replace each other:
- `TRTaxReport.source_variant` is persisted on `ImportRecord.source_variant` and is
  part of the year-replace key (`_check_year_duplicate(broker, year, variant)`), so
  re-uploading either file replaces only its own slot.
- `tax_results` rows are owned by `import_id` (no UNIQUE on broker+casilla — a
  broker can have two reports/year); `fiscal.py` sums rows per casilla and sums TR
  reference amounts. Deletion is scoped by `import_id` (legacy NULL rows swept by
  broker+year). Upload each PDF separately — both persist and combine.
- tr_csv.py imports the TR transaction-export CSV (multi-year ledger, dedups by
  date/isin/type/qty, never year-replaces).

---

## Exchange rates — ECB service

`services/exchange_rates.py` — official EUR reference rates as an IRPF fallback when a broker
file omits the rate or for manual entries. Ported from OptionsAI.
- `ExchangeRate` table (rate_date, currency, rate, source); unique (rate_date, currency).
- `sync_rates()` runs from the daily zonas cron on request-scoped production and from
  a startup thread locally: full ECB history on first boot, then the 90-day feed; skips
  if already fresh (≤1 day). Never attach it to the 10/15-minute cycles.
- `get_rate(currency, on)` is DB-only (no HTTP), with ±7-day fallback for weekends/holidays.
  `to_eur(amount, currency, on)` = amount / rate. EUR is always 1.
- Lookup endpoint: `GET /fiscal/fx-rate?currency=USD&on=YYYY-MM-DD`.

---

## IRPF fiscal model (context for AI)

- Modelo 100: casillas 27/29 (rendimientos), 328/380 o 332/337 según el ejercicio (ganancias/pérdidas), 588 (doble imposición) y 597 (retenciones españolas)
- Modelo 714: casillas 05-09 (patrimonio exterior)
- FIFO is chronological and cross-broker — historical sells consume earlier inventory;
  a buy in IBKR can match a later sell in DEGIRO, never an earlier one
- FIFO adjustments are versioned and split by box. `amount_eur` already contains the
  v2 delta; frontend consumers must never add `fifo_adjustment_eur` a second time.
- Assigned IBKR PUT premiums reduce stock acquisition cost; assigned CALL premiums
  increase stock sale proceeds. Apply each detected premium exactly once and fail on
  ambiguous stock legs.
- Annual import replacement and FIFO rebuilds use transaction-scoped PostgreSQL
  advisory locks. Keep duplicate checks, replacement and recalculation in one transaction.
- Withholding has three distinct truths: cash withheld, Spanish payment on account and
  foreign withholding. Never deduct total cash or infer a CDI credit from country;
  casilla 588 requires an explicit credit and is capped by quota/effective tax rate.
- Reference casilla output for a fiscal year stays out of the repo: it is the owner's real
  IRPF data. Keep it local (ignored) and compare by hand.
