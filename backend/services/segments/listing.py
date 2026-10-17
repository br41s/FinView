"""The last resort for a stock no annual report breaks down: its country and listed sector.

The owner's rule (2026-10-17): a stock whose sector or region no report gives is
counted 100% in its ISIN's country and 100% in the sector its listing carries on
Yahoo Finance. It is an estimate, and the UI says so on every line it produces —
"país del ISIN", "sector de cotización (Yahoo Finance)" — so it is never read as
something the company reported. Report data always wins, axis by axis: BBVA's
report gives regions only, so only its sector comes from here.

Only a listing Yahoo calls EQUITY gets it. An ETF's ISIN country is where the fund
is domiciled (Ireland, Luxembourg), not what it holds, and its "sector" is not one;
ETFs and funds stay "Sin datos". A country whose prefix says nothing about where a
company works (XS, offshore registries) gives no region either.

Yahoo's sector names are mapped to FinView's own `SECTORS` by a fixed table: no
model, nothing to verify. The raw name is stored and shown next to the category.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import ListingProfile, SegmentReport
from backend.services.yahoo_budget import Budget

logger = logging.getLogger(__name__)

RECHECK_DAYS = 30  # a listing's sector changes rarely
# Yahoo gave nothing usable: asked again after this, not on every page load. An outage
# and "Yahoo knows no such listing" look the same from here, and each costs up to 30s.
# What a day's wait hides is an estimate, not a report.
RETRY_HOURS = 24
SECONDS = 15.0  # of a refresh run; ~1.5s a healthy lookup

EQUITY = "EQUITY"

# Yahoo Finance's eleven sector names → FinView's SECTORS keys.
YAHOO_SECTORS = {
    "Basic Materials": "materials",
    "Communication Services": "communication",
    "Consumer Cyclical": "consumer_discretionary",
    "Consumer Defensive": "consumer_staples",
    "Energy": "energy",
    "Financial Services": "financials",
    "Healthcare": "health",
    "Industrials": "industrials",
    "Real Estate": "real_estate",
    "Technology": "technology",
    "Utilities": "utilities",
}

# ISIN prefix → FinView's REGIONS key. Prefixes absent here give no region.
# fmt: off
_PREFIXES = {
    "spain": ("ES",),
    "europe": (
        "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "FI", "FO", "FR", "GB", "GG",
        "GR", "HR", "HU", "IE", "IM", "IS", "IT", "JE", "LI", "LT", "LU", "LV", "MC", "MT",
        "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
    ),
    "north_america": ("US", "CA"),
    "latin_america": ("AR", "BR", "CL", "CO", "MX", "PE", "UY"),
    "asia_pacific": (
        "AU", "CN", "HK", "ID", "IN", "JP", "KR", "MY", "NZ", "PH", "SG", "TH", "TW", "VN",
    ),
    "middle_east_africa": ("AE", "EG", "IL", "KE", "MA", "NG", "QA", "SA", "ZA"),
}
# fmt: on
REGION_BY_PREFIX = {code: region for region, codes in _PREFIXES.items() for code in codes}


def region_of(isin: str) -> str | None:
    return REGION_BY_PREFIX.get(isin[:2].upper())


def sector_of(profile: ListingProfile | None) -> str | None:
    """FinView's sector for an equity listing, or None (not a stock, or no sector)."""
    if profile is None or profile.quote_type != EQUITY:
        return None
    return YAHOO_SECTORS.get(profile.sector or "")


def is_stock(profile: ListingProfile | None) -> bool:
    return profile is not None and profile.quote_type == EQUITY


def fetch(ticker: str) -> tuple[str, str | None] | None:
    """(quoteType, sector) for a Yahoo ticker, or None when Yahoo does not answer usably.

    One network call with no usable timeout (see yahoo_budget): `refresh` loops
    under a Budget. A None never overwrites a stored answer: `refresh` keeps the
    listing it had and only moves the check date.
    """
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    quote_type = info.get("quoteType")
    if not isinstance(quote_type, str) or not quote_type:
        return None
    sector = info.get("sector")
    return quote_type, sector if isinstance(sector, str) and sector else None


def _covered(db: Session, isins: list[str]) -> set[str]:
    """ISINs whose latest segment report gives both a sector and a region breakdown."""
    latest: dict[str, SegmentReport] = {}
    for row in db.query(SegmentReport).filter(SegmentReport.isin.in_(isins)).all():
        if row.isin not in latest or row.fiscal_year > latest[row.isin].fiscal_year:
            latest[row.isin] = row
    out = set()
    for isin, row in latest.items():
        axes = {line["axis"] for line in json.loads(row.lines) if float(line["value"]) > 0}
        if {"business", "geography"} <= axes:
            out.add(isin)
    return out


def due(
    db: Session, holdings: dict[str, tuple[str | None, str]], now: datetime | None = None
) -> list[str]:
    """Held ISINs with a ticker that no report fully covers and whose listing is unknown
    or older than RECHECK_DAYS."""
    now = now or datetime.now(timezone.utc)
    wanted = sorted(isin for isin, (ticker, _) in holdings.items() if ticker)
    covered = _covered(db, wanted)
    profiles = {
        p.isin: p for p in db.query(ListingProfile).filter(ListingProfile.isin.in_(wanted)).all()
    }
    known = (now - timedelta(days=RECHECK_DAYS)).replace(tzinfo=None)
    unknown = (now - timedelta(hours=RETRY_HOURS)).replace(tzinfo=None)

    def stale(p: ListingProfile) -> bool:
        return _naive(p.checked_at) < (known if p.quote_type else unknown)

    return [
        isin
        for isin in wanted
        if isin not in covered
        and (
            isin not in profiles
            or profiles[isin].ticker != holdings[isin][0]
            or stale(profiles[isin])
        )
    ]


def refresh(
    db: Session, holdings: dict[str, tuple[str | None, str]], seconds: float = SECONDS
) -> tuple[int, int]:
    """Look up the due listings until the Yahoo budget is spent. Returns (checked, pending)."""
    todo = due(db, holdings)
    budget = Budget(seconds, "listing sectors")
    checked = 0
    for isin in todo:
        if budget.spent():
            break
        ticker = holdings[isin][0]
        answer = fetch(ticker)
        if answer is None:
            logger.warning("[listing] %s (%s): no usable answer from Yahoo", isin, ticker)
        row = db.query(ListingProfile).filter(ListingProfile.isin == isin).one_or_none()
        if row is None:
            # Nothing usable yet is stored as unknown (quote_type NULL), asked again
            # after RETRY_HOURS.
            row = ListingProfile(isin=isin, quote_type=None, sector=None)
            db.add(row)
        if answer is not None:
            row.quote_type, row.sector = answer
        # else: a Yahoo hiccup at a 30-day recheck keeps the sector it had, rather than
        # dropping a known stock to "Sin datos" for a day.
        row.ticker = ticker
        row.checked_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except IntegrityError:
            # A concurrent refresh (the daily cron, another tab) inserted it first; its
            # answer stands.
            db.rollback()
            continue
        checked += 1
    return checked, len(due(db, holdings))


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt
