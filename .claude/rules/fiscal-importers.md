---
paths:
  - "backend/importers/**"
  - "backend/services/fifo_engine.py"
  - "backend/services/import_service.py"
  - "backend/services/broker_sync.py"
  - "backend/services/ibkr_flex.py"
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

## IBKR direct connection — Flex Web Service

`importers/ibkr_flex.py` parses an Activity Flex Query XML into the **same**
`IBKRAnnualReport` as the CSV parser, so a synced year goes through `import_ibkr_report`
unchanged. One source per broker and year: a synced year replaces an uploaded CSV for that
year and vice versa (no `source_variant`, on purpose — two variants would double-count).
- **Only EUR-base accounts.** "In Base" figures in another base would be imported as euros;
  the parser refuses them. Amounts convert with each row's `fxRateToBase`.
- **Required sections, levels and fields are checked up front** (`REQUIRED_SECTIONS`,
  `_REQUIRED_FIELDS`) and named in the error. Flex lets the user untick a field, and a
  missing attribute reads as 0: a year with no `proceeds` or `totalRealizedPnl` would
  replace a correct import silently. A non-EUR row without `fxRateToBase` is refused for
  the same reason, and so is a statement whose period is not the year asked for (IBKR
  falling back to the query's saved period) or that is not XML.
  Query-layout problems raise `FlexQueryError` (stops the run); a per-year problem such as
  an ambiguous assignment raises a plain `ValueError` (that year becomes a gap).
- **Payments in lieu are dividends**, as in the CSV (its Dividends section carries them;
  the owner's 2024 and 2025 files have five). Flex types them separately
  (`_DIVIDEND_TYPES`). Withholding is matched by (currency, day, symbol) like the CSV, and
  when several payouts share that key it is split by amount — looked up per payout, it
  would be counted once per row.
- **Trades: one level only** — executions, or orders when the query has none. Closed lots
  and orders beside executions would count the same trade twice.
- **Holdings are not stored for IBKR** (CSV or Flex), so `portfolio_snapshot_complete`
  stays NULL. Setting it true would be an empty complete snapshot and close every position.
- **The sync is a run of steps, one year per HTTP request** (`services/broker_sync.py`):
  `queue` and `pending_reference` live on `broker_connections`, so a timed-out request or a
  closed tab resumes. The advisory lock covers the row changes and the SendRequest, never
  the polling; a step that re-locks and finds its reference gone imports nothing.
  Each year recalculates FIFO from that year through `import_ibkr_report` — kept per step
  so every request leaves the ledger consistent.
- **Full history** queues the current year first (its `dateOpened` is the only way to know
  where the account starts), then every older year oldest first. The opening date is read
  from any statement that arrives (`read_date_opened`), so a first year that fails to parse
  or import still queues the rest. `last_synced_at` moves only when a year was imported. Routine sync: the current
  year, plus the previous one until 31 March (`routine_years`). Statements end yesterday.
- **Error codes act by kind** (`services/ibkr_flex.py`): transient (1019 generating, 1018
  rate limit…) keeps the reference; connection (1012 expired, 1015 invalid…) stops the run
  with `last_error`; anything else is a gap for that year; 1017 asks again.
- **The token is in IBKR's query string.** It never reaches a log (a filter redacts `t=` in
  httpx's request line) or an exception message (httpx errors are re-raised without
  their text). `test_ibkr_flex.py` pins both.
- Synced imports carry `import_records.origin = "ibkr_flex"` and do not count against the
  monthly upload allowance.
- **Daily cron** (`POST /api/brokers/cron` → `broker_sync.sync_all`, Scheduler job
  `ibkr-sync-daily`): every active user's connection, round-robin, one step each per round,
  so a statement IBKR keeps generating costs its owner a step a round and never starves the
  others. The whole loop has one wall-clock budget (`CRON_BUDGET_SECONDS`, 300 s); a run it
  does not finish resumes the next day from the row, before any routine refresh starts.
  Each connection gets its own `paced_client` (`ibkr_flex.py`): at most 10 requests in any
  60 s per token, waiting rather than earning 1018s. `needs_user` (an error and an empty
  queue — only `_stop_run` leaves that) is skipped: an expired token or a broken query fails
  the same way every day until the user reconnects or syncs by hand. That predicate only
  holds because **every step clears `last_error`**: an unreachable IBKR sets it but keeps
  the queue, and once the resumed run finished it used to leave a stale message behind that
  looked exactly like an expired token. A step that raises is logged and rolled back, the
  others continue, and the endpoint answers 500 so the job shows red.
- **Not yet checked against a real IBKR file**: the XML attribute names follow IBKR's Flex
  reference, and parity with an uploaded Activity Statement for the same year is the open
  check in `tasks/todo.md`.

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
