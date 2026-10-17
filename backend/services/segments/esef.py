"""EU issuers: segment revenue from the segment note of the latest ESEF annual report.

ESEF tags the primary statements number by number, so total revenue is a
machine-readable fact. The notes are only required as tagged blocks of HTML:
in a sample of 25 Spanish FY2024 reports none carried segment figures as
dimensioned facts, and all 12 checked carried the segment note as a block.

So the note is read by the shared model, and nothing it returns is trusted on
its word. Every amount must be quoted exactly as printed and must appear in the
note, and the lines of each breakdown must add up to the tagged total revenue
under one presentation scale. A breakdown that fails either check is dropped.

Reports come from filings.xbrl.org, which republishes what national registers
collect. It runs months behind some registers (no Spanish FY2025 report was
there in October 2026), so the year shown is always the report's own.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import httpx

from backend.services import llm_envelope
from backend.services.segments.numbers import appears_in, parse_amount, scale_to_total
from backend.services.segments.sec import SourceUnavailable

_GLEIF_URL = "https://api.gleif.org/api/v1/lei-records"
_FILINGS_URL = "https://filings.xbrl.org/api/entities/{lei}/filings"
_BASE = "https://filings.xbrl.org"

# The total a segment breakdown must add up to, with the measure it is. The first one
# tagged for the year wins, so revenue always comes first. Banks, insurers and
# property companies tag no revenue line: their segment note breaks down margen
# bruto, insurance revenue or rental income instead, and the UI names which.
TOTAL_CONCEPTS = (
    ("ifrs-full:Revenue", "revenue"),
    ("ifrs-full:RevenueFromContractsWithCustomers", "revenue"),
    ("ifrs-full:GrossProfit", "bank_gross_income"),
    ("ifrs-full:InsuranceRevenue", "insurance_revenue"),
    ("ifrs-full:RentalIncomeFromInvestmentProperty", "rental_income"),
    ("ifrs-full:RentalIncome", "rental_income"),
)
# Spanish banks tag margen bruto as GrossProfit. Anywhere else GrossProfit is revenue
# minus cost of sales, so it counts only in an income statement that also tags net
# interest income: a bank's.
BANK_MARKER = "ifrs-full:InterestRevenueExpense"
SEGMENT_NOTES = (
    "ifrs-full:DisclosureOfEntitysReportableSegmentsExplanatory",
    "ifrs-full:DisclosureOfOperatingSegmentsExplanatory",
    "ifrs-full:DisclosureOfGeographicalAreasExplanatory",
)
# A long note is truncated rather than skipped; if the table falls past the cut
# the extraction fails the add-up check and nothing is published.
MAX_NOTE_CHARS = 60_000
_CORE_DIMENSIONS = {"concept", "entity", "period", "unit", "language"}


@dataclass
class Filing:
    filing_id: str
    period_end: date  # as listed: may not be the report's own (`fiscal_year_end`)
    json_url: str
    viewer_url: str
    # The full inline-XBRL report, prose included. Read for what it says about AI.
    report_url: str | None = None

    @property
    def url(self) -> str:
        return _BASE + self.viewer_url


@dataclass
class Report:
    currency: str
    total: Decimal
    note: str
    period_end: date  # the report's own fiscal year end
    measure: str = "revenue"  # a TOTAL_CONCEPTS measure


def client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True)


def _get_json(http: httpx.Client, url: str, **params) -> dict | None:
    try:
        resp = http.get(url, params=params or None)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"{type(exc).__name__} on {url.split('/')[2]}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise SourceUnavailable(f"HTTP {resp.status_code} on {url.split('/')[2]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceUnavailable(f"non-JSON body from {url.split('/')[2]}") from exc


def isin_to_lei(http: httpx.Client, isin: str) -> str | None:
    data = _get_json(http, _GLEIF_URL, **{"filter[isin]": isin})
    records = (data or {}).get("data") or []
    return records[0]["id"] if records else None


def latest_filing(http: httpx.Client, lei: str) -> Filing | None:
    data = _get_json(http, _FILINGS_URL.format(lei=lei))
    filings = [
        f["attributes"]
        for f in (data or {}).get("data") or []
        if f.get("attributes", {}).get("json_url") and f["attributes"].get("period_end")
    ]
    if not filings:
        return None
    # Latest year; within a year the latest upload (a corrected re-filing).
    best = max(filings, key=lambda a: (a["period_end"], a.get("date_added") or ""))
    return Filing(
        filing_id=best["fxo_id"],
        period_end=date.fromisoformat(best["period_end"]),
        json_url=best["json_url"],
        viewer_url=best.get("viewer_url") or best["json_url"],
        report_url=best.get("report_url"),
    )


def fetch_report(http: httpx.Client, filing: Filing) -> Report | None:
    """The tagged total for the filing's year (`TOTAL_CONCEPTS`) plus the segment note."""
    data = _get_json(http, _BASE + filing.json_url)
    if not data:
        return None
    return parse_report(data, filing.period_end)


def parse_report(data: dict, listed_end: date) -> Report | None:
    facts = list((data.get("facts") or {}).values())
    period_end = fiscal_year_end(_json_periods(facts), listed_end)
    found = None
    for concept, measure in TOTAL_CONCEPTS:
        if measure == "bank_gross_income" and _year_total(facts, BANK_MARKER, period_end) is None:
            continue
        total = _year_total(facts, concept, period_end)
        if total is not None:
            found = (*total, measure)
            break
    if found is None:
        return None
    total, currency, measure = found

    blocks: list[str] = []
    for fact in facts:
        dims = fact.get("dimensions") or {}
        if dims.get("concept") in SEGMENT_NOTES and set(dims) <= _CORE_DIMENSIONS:
            text = note_text(str(fact.get("value") or ""))
            if text and text not in blocks:
                blocks.append(text)
    note = "\n\n".join(blocks)[:MAX_NOTE_CHARS]
    return Report(currency=currency, total=total, note=note, period_end=period_end, measure=measure)


def fiscal_year_end(periods: Iterable[tuple[date, date]], listed_end: date) -> date:
    """The year a report covers, read from its own (start, last day) periods.

    filings.xbrl.org's `period_end` is not always the report's: Aviva's FY2025 report
    is listed at 2026-03-02 and Carrefour's at 2026-12-31, so every fact for the year
    failed the period check and the year shown would have been 2026. A report tags
    more facts for its own year than for the comparative one (Carrefour 312 vs 161),
    so the most common full-year end is its year; on a tie, the later one. Without a
    full-year period at all, the listing is all there is.
    """
    ends = Counter(end for start, end in periods if (end - start).days >= 350)
    if not ends:
        return listed_end
    return max(ends, key=lambda end: (ends[end], end))


def _json_periods(facts: list[dict]) -> Iterable[tuple[date, date]]:
    """xBRL-JSON durations end at midnight after the last day: '…/2025-01-01T00:00:00'."""
    for fact in facts:
        period = (fact.get("dimensions") or {}).get("period", "")
        if "/" not in period:
            continue
        start, end = period.split("/", 1)
        try:
            yield date.fromisoformat(start[:10]), date.fromisoformat(end[:10]) - timedelta(days=1)
        except ValueError:
            continue


def _year_total(facts: list[dict], concept: str, period_end: date) -> tuple[Decimal, str] | None:
    """The undimensioned monetary fact for `concept` over the fiscal year, and its currency."""
    for fact in facts:
        dims = fact.get("dimensions") or {}
        if dims.get("concept") != concept or set(dims) - _CORE_DIMENSIONS:
            continue
        if not _covers_year(dims.get("period", ""), period_end):
            continue
        unit = dims.get("unit", "")
        if unit.startswith("iso4217:") and fact.get("value") is not None:
            return Decimal(str(fact["value"])), unit.split(":", 1)[1]
    return None


def _covers_year(period: str, period_end: date) -> bool:
    """xBRL-JSON durations end at midnight after the last day: '…/2025-01-01T00:00:00'."""
    if "/" not in period:
        return False
    start_s, end_s = period.split("/", 1)
    start, end = date.fromisoformat(start_s[:10]), date.fromisoformat(end_s[:10])
    return end - timedelta(days=1) == period_end and (end - start).days >= 350


_CELL = re.compile(r"(?is)<t([dh])\b.*?</t\1\s*>")
_BREAK = re.compile(r"(?i)</p\s*>|</div\s*>|<br\s*/?>")


def note_text(fragment: str) -> str:
    """The note's HTML as plain text, one table row per line with its cells apart.

    Reports converted from PDF wrap each cell's figure in <div>s. Read as line
    breaks, those put every cell of a row on its own line and the model can no
    longer tell which column a figure belongs to: Naturgy, Endesa, Enagás,
    Acciona, Ebro, FCC and Severn Trent all failed the add-up check that way.
    So a break inside a cell is only a space.
    """
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    s = _CELL.sub(lambda m: _BREAK.sub(" ", m.group(0)), s)
    s = re.sub(r"(?i)</t[dh]\s*>", " | ", s)
    s = re.sub(r"(?i)</tr\s*>|<br\s*/?>|</p\s*>|</div\s*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    lines = (re.sub(r"[ \t ]+", " ", line).strip(" |") for line in s.splitlines())
    return "\n".join(line for line in lines if line)


# ── extraction ───────────────────────────────────────────────────────

_SYSTEM = (
    "You read the operating-segment note of a company's annual report and copy out "
    "one figure per segment for one fiscal year: {measure}. Answer with one JSON object "
    "and nothing else: "
    '{{"business": [{{"label": "...", "amount": "..."}}], '
    '"geography": [{{"label": "...", "amount": "..."}}]}}. '
    "business = that figure by line of business; geography = by country or area. "
    "Include adjustment, corporate or elimination lines with their "
    "sign. Never include a total or subtotal line. Copy each amount exactly as printed, "
    "with its separators and parentheses, without converting units. Copy each label as "
    "printed. Leave a list empty if the note does not give that breakdown for the year. "
    "Tables arrive as text: usually one row per line with cells separated by |, but in "
    "some reports each cell is on its own line, the column headers first and then each "
    "row's figures in the same order. Match figures to columns by that order."
)

# What the figure is called in the notes, per measure. The add-up check holds the
# model to it: lines of any other figure do not add up to the tagged total.
MEASURE_PROMPT = {
    "revenue": "external revenue (importe neto de la cifra de negocios, ventas, revenue "
    "from external customers)",
    "bank_gross_income": "gross income, the bank's total income (margen bruto, gross "
    "income, total income)",
    "insurance_revenue": "insurance revenue (ingresos de las actividades ordinarias de "
    "seguros, insurance revenue, insurance income)",
    "rental_income": "gross rental income on the IFRS basis, not a proportionate basis "
    "(ingresos por arrendamientos, cifra de negocios de inversiones inmobiliarias, gross "
    "rental income)",
}


class ExtractionError(Exception):
    """The model did not answer usably. Not cached: the next refresh retries."""


def extract(company: str, report: Report, period_end: date) -> dict[str, list[tuple[str, str]]]:
    """Raw (label, amount-as-printed) pairs per axis, straight from the model."""
    user = (
        f"Company: {company}\nFiscal year ending: {period_end.isoformat()}\n"
        f"Currency: {report.currency}\n\nSegment note:\n{report.note}"
    )
    content, error = llm_envelope.chat(
        [
            {"role": "system", "content": _SYSTEM.format(measure=MEASURE_PROMPT[report.measure])},
            {"role": "user", "content": user},
        ],
        context=f"segment note {company}",
        timeout=45.0,
        temperature=0,
        max_tokens=3000,
        response_format={"type": "json_object"},
        reasoning=llm_envelope.NO_REASONING,
    )
    if error:
        raise ExtractionError(error)
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        answer = json.loads(text)
    except ValueError as exc:
        raise ExtractionError("The segment reader did not return JSON") from exc
    if not isinstance(answer, dict):
        raise ExtractionError("The segment reader did not return an object")
    out: dict[str, list[tuple[str, str]]] = {}
    for axis in ("business", "geography"):
        rows = answer.get(axis) or []
        out[axis] = (
            [
                (str(r["label"]).strip(), str(r["amount"]).strip())
                for r in rows
                if isinstance(r, dict) and r.get("label") and r.get("amount") is not None
            ]
            if isinstance(rows, list)
            else []
        )
    return out


def verify(
    rows: list[tuple[str, str]], report: Report
) -> tuple[list[tuple[str, Decimal]] | None, str]:
    """Scaled lines if every amount is in the note and they add up; else (None, why)."""
    if len(rows) < 2:
        return None, "absent"
    parsed: list[tuple[str, Decimal]] = []
    for label, raw in rows:
        value = parse_amount(raw)
        if value is None or not appears_in(raw, report.note):
            return None, "not_in_note"
        parsed.append((label, value))
    scale = scale_to_total([v for _, v in parsed], report.total)
    if scale is None:
        return None, "unreconciled"
    return [(label, value * scale) for label, value in parsed], "ok"
