"""US issuers: segment revenue from the XBRL instance of the latest 10-K on EDGAR.

SEC's `companyfacts` API is the easy door and the wrong one: it carries only
undimensioned facts, so total revenue is there and the segment split is not.
The split lives in the 10-K's own XBRL instance, as revenue facts whose context
names a member on a segment, product or geographic axis. Every value read here
is a tagged fact in a filing anyone can open from `source_url`.

The fetchers raise `SourceUnavailable` on a failed request (not cached, retried
next run) and return None for a definite "there is nothing to read".
"""

from __future__ import annotations

import re

# Stdlib, as cnmv_catalog: expat >= 2.4 resolves no external entities and caps
# entity expansion, and the input is SEC's own archive.
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from backend.config import settings
from backend.services.segments.hosts import Client, SourceUnavailable

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# In preference order. A company tags segment revenue with the same concept as
# its total; the first concept with an undimensioned full-year total is used.
REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)

BUSINESS_AXES = ("srt:ProductOrServiceAxis", "us-gaap:StatementBusinessSegmentsAxis")
GEOGRAPHY_AXES = ("srt:StatementGeographicalAxis", "us-gaap:StatementBusinessSegmentsAxis")
# Present alongside a segment member when the fact is the segment's own figure.
_NEUTRAL_DIMENSION = ("srt:ConsolidationItemsAxis", "us-gaap:OperatingSegmentsMember")


@dataclass
class Filing:
    cik: int
    accession: str
    document: str
    period_end: date

    @property
    def filing_id(self) -> str:
        return self.accession

    @property
    def url(self) -> str:
        return _ARCHIVE_URL.format(
            cik=self.cik, accession=self.accession.replace("-", ""), document=self.document
        )

    def file_url(self, name: str) -> str:
        return _ARCHIVE_URL.format(
            cik=self.cik, accession=self.accession.replace("-", ""), document=name
        )


@dataclass
class Instance:
    """What one 10-K instance tags about full-year revenue."""

    currency: str
    period_end: date
    total: Decimal
    # axis QName → {member QName → value}
    axes: dict[str, dict[str, Decimal]] = field(default_factory=dict)


def _get(client: httpx.Client, url: str) -> httpx.Response:
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"SEC {type(exc).__name__}") from exc
    if resp.status_code == 404:
        return resp
    if resp.status_code != 200:
        raise SourceUnavailable(f"SEC HTTP {resp.status_code}")
    return resp


def client() -> httpx.Client:
    return Client(
        headers={"User-Agent": settings.sec_user_agent}, timeout=20.0, follow_redirects=True
    )


def ticker_to_cik(http: httpx.Client) -> dict[str, int]:
    """SEC's own ticker → CIK list (~10k listed US issuers)."""
    data = _get(http, _TICKERS_URL).json()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def latest_10k(http: httpx.Client, cik: int) -> Filing | None:
    resp = _get(http, _SUBMISSIONS_URL.format(cik=cik))
    if resp.status_code == 404:
        return None
    recent = resp.json().get("filings", {}).get("recent", {})
    for i, form in enumerate(recent.get("form", [])):
        if form != "10-K":
            continue
        if not recent["primaryDocument"][i].endswith(".htm") or not recent["isXBRL"][i]:
            return None
        return Filing(
            cik=cik,
            accession=recent["accessionNumber"][i],
            document=recent["primaryDocument"][i],
            period_end=date.fromisoformat(recent["reportDate"][i]),
        )
    return None


def xbrl_files(http: httpx.Client, filing: Filing) -> dict[str, str]:
    """{"instance": name, "labels": name} from the filing index; either may be missing.

    Inline-XBRL filings publish the extracted instance as `*_htm.xml` and the label
    linkbase as `*_lab.xml`, but the stem is not always the primary document's
    (Microsoft's is not), so the names are read, not derived.
    """
    resp = _get(http, filing.file_url("index.json"))
    if resp.status_code == 404:
        return {}
    names = [i.get("name", "") for i in resp.json().get("directory", {}).get("item", [])]
    out = {}
    for key, suffix in (("instance", "_htm.xml"), ("labels", "_lab.xml")):
        match = next((n for n in names if n.endswith(suffix)), None)
        if match:
            out[key] = match
    return out


def fetch_instance(http: httpx.Client, filing: Filing, files: dict[str, str]) -> str | None:
    if "instance" not in files:
        return None
    resp = _get(http, filing.file_url(files["instance"]))
    return None if resp.status_code == 404 else resp.text


def fetch_labels(http: httpx.Client, filing: Filing, files: dict[str, str]) -> dict[str, str]:
    """Member QName → the name the company gives it ("aapl:IPhoneMember" → "iPhone").

    Read from the filing's label linkbase, so the label shown is the report's own.
    A missing linkbase is not an error: `member_label` derives a name instead.
    """
    if "labels" not in files:
        return {}
    resp = _get(http, filing.file_url(files["labels"]))
    return {} if resp.status_code == 404 else parse_labels(resp.text)


def parse_labels(xml: str) -> dict[str, str]:
    xlink = "{http://www.w3.org/1999/xlink}"
    root = ET.fromstring(xml)
    concept_by_loc: dict[str, str] = {}
    text_by_label: dict[str, str] = {}
    arcs: list[tuple[str, str]] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "loc":
            fragment = el.get(f"{xlink}href", "").rsplit("#", 1)[-1]
            concept_by_loc[el.get(f"{xlink}label", "")] = fragment.replace("_", ":", 1)
        elif name == "label" and el.get(f"{xlink}role", "").endswith("/role/label"):
            text_by_label[el.get(f"{xlink}label", "")] = (el.text or "").strip()
        elif name == "labelArc":
            arcs.append((el.get(f"{xlink}from", ""), el.get(f"{xlink}to", "")))
    out: dict[str, str] = {}
    for loc, lab in arcs:
        concept, text = concept_by_loc.get(loc), text_by_label.get(lab)
        if concept and text:
            out[concept] = re.sub(r"\s*\[Member\]$", "", text)
    return out


# ── instance parsing ─────────────────────────────────────────────────


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _contexts(
    root: ET.Element,
) -> dict[str, tuple[date | None, date | None, list[tuple[str, str]]]]:
    out = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        start = end = None
        members: list[tuple[str, str]] = []
        for el in ctx.iter():
            name = _local(el.tag)
            if name == "startDate":
                start = date.fromisoformat(el.text.strip()[:10])
            elif name == "endDate":
                end = date.fromisoformat(el.text.strip()[:10])
            elif name == "explicitMember":
                members.append((el.get("dimension", ""), (el.text or "").strip()))
        out[ctx.get("id")] = (start, end, members)
    return out


def _units(root: ET.Element) -> dict[str, str]:
    out = {}
    for unit in root.iter():
        if _local(unit.tag) == "unit":
            measures = [
                m.text.strip() for m in unit.iter() if _local(m.tag) == "measure" and m.text
            ]
            if len(measures) == 1:
                out[unit.get("id")] = measures[0]
    return out


def parse_instance(xml: str) -> Instance | None:
    """Full-year revenue, total and per axis member, for the report's own period."""
    root = ET.fromstring(xml)
    period_end = next(
        (
            date.fromisoformat(el.text.strip()[:10])
            for el in root.iter()
            if _local(el.tag) == "DocumentPeriodEndDate" and el.text
        ),
        None,
    )
    if period_end is None:
        return None
    contexts, units = _contexts(root), _units(root)

    for concept in REVENUE_CONCEPTS:
        total: Decimal | None = None
        currency = ""
        axes: dict[str, dict[str, Decimal]] = {}
        for el in root.iter():
            if _local(el.tag) != concept or not el.text or el.get("contextRef") not in contexts:
                continue
            start, end, members = contexts[el.get("contextRef")]
            if end != period_end or start is None or (end - start).days < 350:
                continue
            unit = units.get(el.get("unitRef", ""), "")
            if not unit.startswith("iso4217:"):
                continue
            try:
                value = Decimal(el.text.strip())
            except InvalidOperation:
                continue
            dims = [m for m in members if m != _NEUTRAL_DIMENSION]
            if not dims:
                if not members:
                    total, currency = value, unit.split(":", 1)[1]
            elif len(dims) == 1:
                axis, member = dims[0]
                axes.setdefault(axis, {})[member] = value
        if total is not None:
            return Instance(currency=currency, period_end=period_end, total=total, axes=axes)
    return None


def member_label(member: str) -> str:
    """'aapl:GreaterChinaSegmentMember' → 'Greater China'; 'country:US' → 'US'."""
    name = member.split(":", 1)[-1]
    name = re.sub(r"(Segments?)?Member$", "", name)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name).strip() or member
