---
paths:
  - "backend/services/segments/**"
  - "backend/models/segments.py"
  - "frontend/src/app/portfolio/ExposureCharts.tsx"
  - "frontend/src/app/portfolio/useExposure.ts"
  - "frontend/src/lib/exposure.ts"
  - "frontend/src/app/portfolio/AiExposureCard.tsx"
  - "frontend/src/lib/aiExposure.ts"
---

## Sector and region exposure — from annual reports

`/portfolio` spreads each position's market value over the sectors and regions its
issuer's **own latest annual report** attributes revenue to. Not the company's
listing sector, not its domicile: what the report says it sells, and where.

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
  filings.xbrl.org, total revenue is the tagged `ifrs-full:Revenue` for the year, the
  segment note is a tagged HTML **block** (ESEF does not require the numbers in notes
  to be tagged; none of 25 Spanish FY2024 reports did). The model copies the amounts
  out of that block. filings.xbrl.org runs months behind some registers (no Spanish
  FY2025 report yet in October 2026), so the UI always names the report year.
- ETFs and funds need no special case: they end as `no_issuer` / `no_filing`.
- Banks and insurers tag no `Revenue`, so they end as `no_revenue`. Supporting them
  means choosing their equivalent (gross margin) — not done.

### What gets published (`numbers.py`) — keep these gates

- **Add-up check**: a breakdown is stored only if its lines sum to the report's tagged
  total revenue within `TOLERANCE` (0.5%). For SEC, `pick_partition` takes the largest
  set of members that adds up, because an axis mixes levels (Apple: Product+Service
  *and* iPhone/Mac/iPad/Wearables+Service). For ESEF, `scale_to_total` finds the
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
  model call.
- Status text is `OUTCOME_DETAIL[outcome]`, looked up at read time — never stored.
- Runs inside requests: `POST /portfolio/exposure/refresh` (40s budget, the frontend
  calls it again while `checked > 0 && pending > 0`) and the daily zonas cron through
  `run_reference_data_maintenance` (120s).

### Exposure (`exposure.py`)

Shares are over a report's **positive** lines; corporate adjustments and eliminations
count for the add-up check but have no sector or region. A position without data is
the `no_data` bucket at full value; a position without a price is listed in
`unpriced` and left out, never spread. The latest fiscal year with stored lines is used.

Both tables are global (`GLOBAL_TABLES`): an issuer's annual report is the same for
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
- **Industry exposure index** (published AI-exposure scores by industry, weighted by
  segment revenue) is not built: the Felten-Raj-Seamans AIIE table on GitHub carries no
  licence, so republishing its scores needs a decision first.
