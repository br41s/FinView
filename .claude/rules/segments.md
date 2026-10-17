---
paths:
  - "backend/services/segments/**"
  - "backend/models/segments.py"
  - "frontend/src/app/portfolio/ExposureCharts.tsx"
  - "frontend/src/app/portfolio/useExposure.ts"
  - "frontend/src/lib/exposure.ts"
  - "frontend/src/app/portfolio/AiExposureCard.tsx"
  - "frontend/src/lib/aiExposure.ts"
  - "scripts/build_ai_industry_exposure.py"
---

## Sector and region exposure — from annual reports

`/portfolio` spreads each position's market value over the sectors and regions its
issuer's **own latest annual report** attributes revenue to. Not the company's
listing sector, not its domicile: what the report says it sells, and where. Only
when no report gives an axis does a stock fall back to its listing (below), and
that line is labelled as an estimate.

### Sources (`backend/services/segments/`)

- **US ISINs → SEC EDGAR** (`sec.py`). Latest 10-K from the submissions API; the
  file names of the XBRL instance (`*_htm.xml`) and label linkbase (`*_lab.xml`) are
  read from the filing's `index.json` — they do not always share the primary
  document's stem (Microsoft's does not). Revenue facts with one member on
  `srt:ProductOrServiceAxis`, `us-gaap:StatementBusinessSegmentsAxis` or
  `srt:StatementGeographicalAxis` (plus the neutral `OperatingSegmentsMember`) are the
  candidates. `companyfacts` is useless here: it carries no dimensioned facts.
  SEC returns 403 on `/Archives` and `company_tickers.json` without a contact in the
  User-Agent: `settings.sec_user_agent` (`FINVIEW_SEC_USER_AGENT`).
- **Everything else → ESEF** (`esef.py`). ISIN → LEI via GLEIF, latest filing from
  filings.xbrl.org, the total is the first `TOTAL_CONCEPTS` fact tagged for the year, the
  segment note is a tagged HTML **block** (ESEF does not require the numbers in notes
  to be tagged; none of 25 Spanish FY2024 reports did). The model copies the amounts
  out of that block. filings.xbrl.org runs months behind some registers (no Spanish
  FY2025 report yet in October 2026), so the UI always names the report year.
- **The year is the report's own, not the listing's** (`esef.fiscal_year_end`).
  filings.xbrl.org's `period_end` is wrong for some filings: Aviva's FY2025 report is
  listed at 2026-03-02 and Carrefour's at 2026-12-31 (2 of the 45 held issuers with a
  filing in October 2026), so every fact failed the period check (`no_revenue`) and the
  year would have shown as 2026. The year is the most common full-year (≥350 days)
  period end among the report's facts (a report tags more for its own year than for the
  comparative), the later one on a tie, the listing only when there is none. The segment
  reader takes the periods from the xBRL-JSON; the AI reader, which never downloads the
  JSON (up to 38 MB), from the inline-XBRL contexts `TextStream` passes while streaming
  the report. File names are no better a source: Ebro's and Acciona's carry the wrong
  year while their listings are right. `latest_filing` still orders by the listed date.
- `note_text` keeps **one table row per line**: block tags inside a `<td>` are spaces,
  not breaks. PDF-converted reports wrap every figure in `<div>`s, and reading those as
  line breaks put each cell on its own line — 7 of the 9 "no cuadra" reports in the first
  production run (Naturgy, Endesa, Enagás, Acciona, Ebro, FCC, Severn Trent) failed that
  way. Some notes are positioned blocks with no `<table>` at all (Endesa, Acciona, FCC:
  headers one per line, then the figures in the same order); the prompt says so.
- German issuers are absent from filings.xbrl.org (Unternehmensregister is not mirrored),
  so they end as `no_filing`.
- ETFs and funds need no special case: they end as `no_issuer` / `no_filing`.
- **Issuers that tag no revenue** (owner's decision, 2026-10-17). `TOTAL_CONCEPTS` is an
  ordered list, each concept with its `measure`: `Revenue` / `RevenueFromContractsWithCustomers`
  (revenue) first, then `GrossProfit` as a bank's **margen bruto** (`bank_gross_income`),
  `InsuranceRevenue` (`insurance_revenue`), `RentalIncomeFromInvestmentProperty` /
  `RentalIncome` (`rental_income`). `GrossProfit` counts only when `BANK_MARKER`
  (`InterestRevenueExpense`, net interest income) is tagged for the same year: Spanish
  banks tag margen bruto as `GrossProfit`, but anywhere else it is revenue minus cost of
  sales. The prompt names the measure (`MEASURE_PROMPT`); the stored report carries it
  (`segment_reports.measure`, NULL = revenue) and the UI names it in the source list and in
  each "x % de su margen bruto". Gates unchanged. Checked by hand against the FY2024/25
  filings: BBVA, Sabadell, NN, Línea Directa, URW (IFRS basis; the proportionate table above
  it does not add up) and Colonial add up. Still out: Santander (segments add up to
  "underlying" income, 6% above the statutory total: `unreconciled`), Unicaja (no income by
  segment, 100% Spain), Aviva (no segment note block). Repsol and REN tag no single total —
  theirs is two tags summed (sale of goods + services), and a summed total is deliberately
  not done: nothing says those two are all of the revenue.

### What gets published (`numbers.py`) — keep these gates

- **Add-up check**: a breakdown is stored only if its lines sum to the report's tagged
  total (revenue, or the measure above) within `TOLERANCE` (0.5%). For SEC,
  `pick_partition` takes the largest set of members that adds up, because an axis mixes
  levels (Apple: Product+Service *and* iPhone/Mac/iPad/Wearables+Service). For ESEF, `scale_to_total` finds the
  presentation scale (units/thousands/millions) under which the lines add up.
- **Verbatim check** (ESEF): every amount the model returns must appear in the note
  exactly as printed (`appears_in`); one invented or "corrected" figure drops the
  whole breakdown. Amounts are parsed by `parse_amount`, never by the model.
- **Classification** (`classify.py`) is the only judgment step: one model call maps
  segment names to FinView's own sector list (`SECTORS` — GICS is licensed, do not
  copy it) and `REGIONS`. Output outside those keys becomes `unassigned`. The original
  label is stored and shown next to the category. Among candidate breakdowns for an
  axis, the one that leaves the least revenue `unassigned` wins (Apple: products for
  sector, regional segments for region).

### Caching (`refresh.py`)

- `segment_checks`: one row per ISIN, the last outcome and filing id. A definite answer
  is cached for `RECHECK_DAYS` (7). A failed request or a failed model call is **not
  written at all** — same lesson as `split_history`: caching an outage hides a real
  report for a week.
- `segment_reports`: one row per ISIN **and fiscal year**, so a new report adds a year.
  A recheck that finds the same filing id costs one or two small requests and no
  model call — **except** for `REREAD_OUTCOMES` (`unreconciled`, `no_segments`,
  `no_revenue`): those say how well FinView read the filing, not what it says, so they
  are read again at every weekly recheck. Otherwise a reader fix would only reach a
  report a year later.
- **Reader versions** (`refresh.READERS`, one per check table): every check stores the
  version that wrote it (`segment_checks.reader`, `ai_mention_checks.reader`). A check
  from an older reader is due at once and its filing is read again, whatever its age.
  Bump the version of the reader you change: the fallback totals and the year fix
  (#356) were live and invisible because every answer they change had been cached that
  morning for `RECHECK_DAYS`. Storing a report also drops the row the same filing left
  under another year (`_drop_misdated`), which a wrong listing date had created.
- Status text is `OUTCOME_DETAIL[outcome]`, looked up at read time — never stored.
- Runs inside requests: `POST /portfolio/exposure/refresh` (40s budget, the frontend
  calls it again while `checked > 0 && pending > 0`) and the daily zonas cron through
  `run_reference_data_maintenance` (120s).

### Exposure (`exposure.py`)

Shares are over a report's **positive** lines; corporate adjustments and eliminations
count for the add-up check but have no sector or region.

**Listing fallback** (`listing.py`, owner's decision 2026-10-17): an axis no report
breaks down is, for a stock, 100% in its ISIN's country (`REGION_BY_PREFIX`) and 100% in
its sector on Yahoo Finance (`YAHOO_SECTORS`, a fixed table onto `SECTORS`: no model).
Report data wins axis by axis (BBVA's report gives regions, so only its sector is
estimated). Each such line carries `basis: "listing"` and the UI says "estimado" on it,
in the subtitle ("x % estimado") and in the source list. Only Yahoo `quoteType`
`EQUITY` gets it: an ETF's ISIN country is the fund's domicile, so ETFs and funds stay
`no_data`; offshore prefixes (XS, KY…) and sector names outside the table give nothing
for that axis. `listing_profiles` (global) caches quote type and sector for 30 days; a
Yahoo answer with nothing usable is stored as `quote_type` NULL and asked again after
24 h, not on every page load (each stalled call costs ~30 s). Lookups run at the end of
the segment refresh on the time the reports left, under a `yahoo_budget.Budget` (15 s),
and without a model key too. The AI industry index does **not** use it: it stays
report-only on purpose.

A position with neither is the `no_data` bucket at full value; a position without a
price is listed in `unpriced` and left out, never spread. The latest fiscal year with stored lines is used.

All three tables are global (`GLOBAL_TABLES`): an issuer's annual report is the same for
everybody. Only public report text reaches OpenRouter — no user data.

## AI exposure — what each report says about AI (`ai_mentions.py`)

"Exposición a la IA" on `/portfolio`. **Not a score and not a "risk of closure"**: no
published, verifiable dataset rates that per company, and a closure probability would
read as a sell signal (not-advice rule). What is shown is the issuer's own words.

- **What is read**: US ISINs → the latest 10-K's primary document on EDGAR, cut to
  Item 1A (`risk_factors`: the longest stretch from the Item 1A heading to Item 1B/1C/2,
  compared letter by letter because headings are styled per letter — Microsoft prints
  "RIS K FACTORS"; the table of contents has the same headings a few lines apart).
  Everything else → the whole ESEF report (`report_url` on filings.xbrl.org): ESEF has
  no standard risk section, so the UI says "Informe anual", never "factores de riesgo".
- **Reading** is streamed (`TextStream`): quoted `data:` URIs are dropped at byte level
  (Inditex's FY2024 report is 85 MB, 59 MB of it images), tags as they complete. A read
  may use its run's whole budget; past `MAX_REPORT_BYTES` the filing is `too_large`.
- **Count** (`TERMS`): done in code, in the languages ESEF reports are filed in; the
  acronyms (AI, GenAI, IA, KI) only as whole upper-case words.
- **Quotes**: the model sees only the passages around each mention and returns up to
  three quotes plus a one-sentence Spanish summary (prompt carries `NOT_ADVICE_RULE_ES`).
  Every quote must be in the filing verbatim (after normalising whitespace, quotes and
  dashes) and must itself name AI. **One failing quote drops all of them and the
  summary** (`quotes_status = "unverified"`); the count is still published, and the
  check is stored without its filing id so the same filing is read again at the next
  weekly recheck — not on every page load.
- **Caching** is the segment reader's: `ai_mention_checks` / `ai_mention_reports`
  (global), `due_isins` / `_record` / `_already_read` take the check table as `model=`.
  A failed request or a null/non-JSON model answer writes nothing. A report with zero
  mentions needs no model call.
- **Refresh**: `POST /portfolio/ai-exposure/refresh` (40s) and the daily cron through
  `run_reference_data_maintenance` (120s), after the segment reader.

## AI exposure index by industry — FinView's own calculation (`industry_index.py`)

The published Felten-Raj-Seamans AIIE table (github.com/AIOE-Data/AIOE) carries **no
licence**, so its scores are not republished. FinView computes the same kind of index
with their method from two sources that may be republished (owner's decision, 2026-10-17):

- **Occupations**: Eloundou et al., "GPTs are GPTs", Science 2024 — `occ_level.csv`,
  column `human_rating_beta`, MIT. Pinned to a commit; the licence text is committed as
  `data/LICENSE-GPTs-are-GPTs.txt` (MIT requires it).
- **Employment**: BLS OEWS national industry-specific estimates, 4-digit NAICS, one
  release (public domain). OEWS aggregate codes ending in 0 take the mean of the detailed
  codes under them; an occupation with no score is left out and lowers `coverage`.
- `scripts/build_ai_industry_exposure.py` downloads both at the pinned versions and writes
  `data/ai_industry_exposure.json` with the versions inside (`sources`). Nothing is
  downloaded at runtime. To move to a new OEWS release, bump the constants, rerun, commit
  both. The UI reads the citations, commit and release from `sources`, never hardcoded.
- **Company score** = its segments' industry scores weighted by the revenue each business
  line reports (positive lines only). The model maps business-line labels to the table's
  codes (`map_industries`), held to those keys; anything else is `unassigned` and lowers
  `revenue_pct` instead of the score. Mapping writes an `industry` key into the segment
  report's `lines` JSON (no schema change), runs first in the AI refresh for any latest
  report with unmapped business lines — so reports read before this existed, or by a new
  filing, get mapped without waiting a year. A model failure writes nothing.
- A company with only a regional breakdown, or no segment report, has no industry score;
  the UI says why (`INDUSTRY_DETAIL`). There is no company-level fallback on purpose.
- The UI says "cálculo de FinView", names the method, both sources with links, the commit
  and the OEWS release, and that it describes US work in those industries, not the company.
