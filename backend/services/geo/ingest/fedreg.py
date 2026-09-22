"""Federal Register — BIS Entity List additions and USTR tariff actions, keyless.

The trade theses (`gdelt-trade-dispute-china`, the semiconductor leg of
`gdelt-sanctions-china`) had never fired once: GDELT codes a tariff as a
diplomatic story and never as a dated action. Measured 2026-09-22 over 90 days
of the Federal Register: USTR published 4 tariff actions (Section 301 China
exclusions, a Section 301 action on Brazil, a Section 301 initiation) and BIS
2 Entity List rules — the whole policy stream is one or two events a month,
each of which is exactly what those rules were written for.

Source: ``https://www.federalregister.gov/api/v1/documents.json`` — a stable,
keyless JSON API. One query for both agencies over the last 3 days; the
document's ``title`` decides what it is and ``title + abstract`` which
countries it names (the same country table as OFAC). Requests for comments,
hearings, quota allocations and investigation *initiations* are not actions
and start nothing; neither do Entity List removals or address revisions.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from .base import TTLCache, fetch_json
from .ofac import COUNTRY_SLUGS, _COUNTRY_PATTERNS
from .types import FedRegDocument

logger = logging.getLogger(__name__)

_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
_CACHE_TTL = 30 * 60
_REQUEST_TIMEOUT = 20.0
# Same reasoning as OFAC: shorter than the advisor's +7 d resolution so an
# action is never re-tracked as new.
_WINDOW_DAYS = 3

AGENCY_SLUGS = {
    "industry-and-security-bureau": "bis",
    "trade-representative-office-of-united-states": "ustr",
}

_RE_ENTITY_LIST = re.compile(r"Entity List", re.I)
_RE_ENTITY_ADDITION = re.compile(r"\bAdditions?\b", re.I)
_RE_ENTITY_SKIP = re.compile(r"\bRemovals?\b", re.I)
_RE_USTR_ACTION = re.compile(
    r"Section 301|Section 232|Notice of Actions?|Modification of (?:Duties|Tariffs?)|"
    r"Product Exclusions|Tariff Actions?",
    re.I,
)
_RE_USTR_SKIP = re.compile(
    r"Request for Comments|Public Hearing|Tariff-Rate Quota|Notorious Markets|"
    r"Initiation of|Extension of (?:Comment|the Comment)|Annual Review",
    re.I,
)

_cache = TTLCache()


def classify(agency: str, title: str) -> str | None:
    """sanctions (BIS Entity List additions) / trade_dispute (USTR tariff actions) / None."""
    if agency == "bis":
        if _RE_ENTITY_LIST.search(title) and _RE_ENTITY_ADDITION.search(title) \
                and not _RE_ENTITY_SKIP.search(title):
            return "sanctions"
        return None
    if agency == "ustr":
        if _RE_USTR_ACTION.search(title) and not _RE_USTR_SKIP.search(title):
            return "trade_dispute"
        return None
    return None


def countries_in(text: str) -> tuple[str, ...]:
    found: list[tuple[int, str]] = []
    for slug, pattern in _COUNTRY_PATTERNS:
        hit = pattern.search(text)
        if hit and slug not in {s for _, s in found}:
            found.append((hit.start(), slug))
    return tuple(slug for _, slug in sorted(found))


def _agency_of(raw: dict) -> str | None:
    for agency in raw.get("agencies") or []:
        if not isinstance(agency, dict):
            continue
        slug = AGENCY_SLUGS.get(agency.get("slug") or "")
        if slug:
            return slug
        name = (agency.get("name") or agency.get("raw_name") or "").lower()
        if "industry and security" in name:
            return "bis"
        if "trade representative" in name:
            return "ustr"
    return None


def parse_document(raw: object) -> FedRegDocument | None:
    if not isinstance(raw, dict):
        return None
    title = " ".join(str(raw.get("title") or "").split())
    number = str(raw.get("document_number") or "")
    date = str(raw.get("publication_date") or "")
    if not title or not number or not date:
        return None
    agency = _agency_of(raw)
    if agency is None:
        return None
    category = classify(agency, title)
    if category is None:
        return None
    abstract = " ".join(str(raw.get("abstract") or "").split())
    return FedRegDocument(
        document_number=number,
        publication_date=date,
        title=title,
        abstract=abstract,
        url=str(raw.get("html_url") or ""),
        agency=agency,
        category=category,
        countries=countries_in(f"{title} {abstract}"),
    )


def is_result_envelope(payload: object) -> bool:
    """The API's own shape: ``results`` when there are documents, and — verified
    against the live endpoint — just ``{"count": 0, ...}`` with no ``results`` key
    on a day with none. Both are answers; anything else is not."""
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("results"), list):
        return True
    return isinstance(payload.get("count"), int)


def parse_payload(payload: object, today: datetime | None = None) -> list[FedRegDocument]:
    if not is_result_envelope(payload) or not isinstance(payload.get("results"), list):
        return []
    floor = ((today or datetime.now(timezone.utc)) - timedelta(days=_WINDOW_DAYS)).strftime(
        "%Y-%m-%d"
    )
    docs: list[FedRegDocument] = []
    for raw in payload["results"]:
        doc = parse_document(raw)
        if doc is not None and doc.publication_date >= floor:
            docs.append(doc)
    return docs


def _params(today: datetime) -> dict:
    return {
        "conditions[publication_date][gte]": (today - timedelta(days=_WINDOW_DAYS)).strftime(
            "%Y-%m-%d"
        ),
        "conditions[agencies][]": list(AGENCY_SLUGS),
        "fields[]": [
            "title", "abstract", "publication_date", "document_number", "html_url", "agencies",
        ],
        "per_page": 50,
        "order": "newest",
    }


async def fetch_fedreg() -> list[FedRegDocument]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached
    today = datetime.now(timezone.utc)
    payload = await fetch_json(_API_URL, params=_params(today), timeout=_REQUEST_TIMEOUT)
    if payload is None:
        logger.warning("federal register unavailable")
        return _cache.stale or []
    if not is_result_envelope(payload):
        logger.warning("federal register payload unusable: %r", str(payload)[:120])
        return _cache.stale or []
    docs = parse_payload(payload, today)
    for doc in docs:
        logger.info(
            "fedreg %s %s %s: %s — %s", doc.publication_date, doc.agency, doc.category,
            ", ".join(doc.countries) or "no country", doc.title[:80],
        )
    _cache.set(docs)
    return docs


__all__ = [
    "COUNTRY_SLUGS", "classify", "countries_in", "fetch_fedreg", "is_result_envelope",
    "parse_payload",
]
