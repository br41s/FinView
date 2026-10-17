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

REVENUE_CONCEPTS = ("ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers")
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
    period_end: date
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
    """Total revenue for the filing's year plus the segment note as table text."""
    data = _get_json(http, _BASE + filing.json_url)
    if not data:
        return None
    return parse_report(data, filing.period_end)


def parse_report(data: dict, period_end: date) -> Report | None:
    facts = (data.get("facts") or {}).values()
    total = currency = None
    for concept in REVENUE_CONCEPTS:
        for fact in facts:
            dims = fact.get("dimensions") or {}
            if dims.get("concept") != concept or set(dims) - _CORE_DIMENSIONS:
                continue
            if not _covers_year(dims.get("period", ""), period_end):
                continue
            unit = dims.get("unit", "")
            if unit.startswith("iso4217:") and fact.get("value") is not None:
                total, currency = Decimal(str(fact["value"])), unit.split(":", 1)[1]
                break
        if total is not None:
            break
    if total is None:
        return None

    blocks: list[str] = []
    for fact in facts:
        dims = fact.get("dimensions") or {}
        if dims.get("concept") in SEGMENT_NOTES and set(dims) <= _CORE_DIMENSIONS:
            text = note_text(str(fact.get("value") or ""))
            if text and text not in blocks:
                blocks.append(text)
    return Report(currency=currency, total=total, note="\n\n".join(blocks)[:MAX_NOTE_CHARS])


def _covers_year(period: str, period_end: date) -> bool:
    """xBRL-JSON durations end at midnight after the last day: '…/2025-01-01T00:00:00'."""
    if "/" not in period:
        return False
    start_s, end_s = period.split("/", 1)
    start, end = date.fromisoformat(start_s[:10]), date.fromisoformat(end_s[:10])
    return end - timedelta(days=1) == period_end and (end - start).days >= 350


def note_text(fragment: str) -> str:
    """The note's HTML as plain text that keeps table rows and cells apart."""
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    s = re.sub(r"(?i)</t[dh]\s*>", " | ", s)
    s = re.sub(r"(?i)</tr\s*>|<br\s*/?>|</p\s*>|</div\s*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    lines = (re.sub(r"[ \t ]+", " ", line).strip(" |") for line in s.splitlines())
    return "\n".join(line for line in lines if line)


# ── extraction ───────────────────────────────────────────────────────

_SYSTEM = (
    "You read the operating-segment note of a company's annual report and copy out "
    "revenue for one fiscal year. Answer with one JSON object and nothing else: "
    '{"business": [{"label": "...", "amount": "..."}], '
    '"geography": [{"label": "...", "amount": "..."}]}. '
    "business = revenue by line of business; geography = revenue by country or area. "
    "Use external revenue (importe neto de la cifra de negocios, ventas, revenue from "
    "external customers). Include adjustment, corporate or elimination lines with their "
    "sign. Never include a total or subtotal line. Copy each amount exactly as printed, "
    "with its separators and parentheses, without converting units. Copy each label as "
    "printed. Leave a list empty if the note does not give that breakdown for the year."
)


class ExtractionError(Exception):
    """The model did not answer usably. Not cached: the next refresh retries."""


def extract(company: str, report: Report, period_end: date) -> dict[str, list[tuple[str, str]]]:
    """Raw (label, amount-as-printed) pairs per axis, straight from the model."""
    user = (
        f"Company: {company}\nFiscal year ending: {period_end.isoformat()}\n"
        f"Currency: {report.currency}\n\nSegment note:\n{report.note}"
    )
    content, error = llm_envelope.chat(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
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
