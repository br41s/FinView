"""Read model for Living World ("Mundo vivo"): the portfolio as the town draws it.

Read-only and derived. The positions, valuations, costs and weights are exactly what
`get_open_positions` computes (one row per ISIN, brokers already folded together); nothing
here values, converts or reconciles anything. What this module adds is the classification
the town needs to pick a building: asset type and sector, read from what FinView already
stored and never from a network call.

Rules that carry over from the portfolio:

* An unknown cost, price or weight is `None`, never zero. The portfolio totals are
  fail-closed: one position without a price makes the market value of the whole `None`.
* Weights are the service's own, taken over the positions that have a price. The summary
  says whether the valuation is complete so the screen can say so.
* No Yahoo call. Listing profiles (`listing_profiles`) and annual-report segments are
  filled by the portfolio's exposure refresh; whatever is not there yet stays
  unclassified and is drawn with the default building, marked as such.

Precedence for the archetype is manual > curated > derived, as for tickers
(`ticker_map`). "Manual" (a per-user override) does not exist yet.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import ListingProfile, PriceCache
from backend.services.portfolio_service import Position, get_open_positions
from backend.services.segments import exposure, listing

# Yahoo `quoteType` → the town's asset type. Anything else (an index, a future) is not a
# holding the town knows how to build, so it falls back to an unclassified equity.
ASSET_TYPE_BY_QUOTE_TYPE = {
    "EQUITY": "equity",
    "ETF": "etf",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
}

# FinView's sector keys (from annual reports) → the Yahoo spelling the frontend classifier
# reads. The inverse of `listing.YAHOO_SECTORS`, which is already the one mapping between them.
_YAHOO_NAME_BY_KEY = {key: name for name, key in listing.YAHOO_SECTORS.items()}

# Curated corrections, ISIN → archetype id (`ARCHETYPES` in the frontend `model/types.ts`).
# Only for holdings whose Yahoo *sector* places them in the wrong building (a chip maker is
# "Technology"; a miner is "Basic Materials"): the archetype needs the industry, which is
# not stored. Empty on purpose: this repository is public and the list would be somebody's
# holdings. Fill it for a deployment that needs it; an unknown archetype id is ignored by the
# frontend.
ARCHETYPE_OVERRIDES: dict[str, str] = {}


def _money(v: Decimal | None) -> float | None:
    return float(round(v, 2)) if v is not None else None


def _brokers(position: Position) -> list[str]:
    """Broker labels of an aggregated position (`"IBKR, TR"` → `["IBKR", "TR"]`)."""
    raw = getattr(position.broker, "value", position.broker) or ""
    return [b for b in (part.strip() for part in str(raw).split(",")) if b]


def _report_sector(db: Session, isins: list[str]) -> dict[str, str]:
    """Yahoo-spelled sector of each ISIN's latest annual report, by revenue share."""
    out: dict[str, str] = {}
    for isin, report in exposure.latest_reports(db, isins).items():
        by_category: dict[str, Decimal] = defaultdict(Decimal)
        for _label, category, share in exposure.shares(report, "business"):
            if category in _YAHOO_NAME_BY_KEY:  # "unassigned" says nothing
                by_category[category] += share
        if by_category:
            out[isin] = _YAHOO_NAME_BY_KEY[max(by_category, key=by_category.__getitem__)]
    return out


def _classify(
    isin: str, profile: ListingProfile | None, report_sector: str | None
) -> tuple[str, str | None, bool]:
    """(asset_type, sector, classified) from stored data only."""
    asset_type = ASSET_TYPE_BY_QUOTE_TYPE.get(profile.quote_type or "") if profile else None
    if asset_type in ("etf", "fund", "crypto"):
        return asset_type, None, True  # a pavilion needs no sector
    sector = profile.sector if profile and asset_type == "equity" else None
    if sector not in listing.YAHOO_SECTORS:
        sector = report_sector
    classified = sector is not None or isin in ARCHETYPE_OVERRIDES
    return "equity", sector, classified


MAX_DAY_CHANGE_PCT = 50.0


def _latest_price_rows(db: Session, isins: list[str]) -> dict[str, PriceCache]:
    """Each ISIN's most recent `price_cache` row (the one the valuation used)."""
    latest = (
        db.query(PriceCache.isin, func.max(PriceCache.fetched_date).label("d"))
        .filter(PriceCache.isin.in_(isins))
        .group_by(PriceCache.isin)
        .subquery()
    )
    rows = db.query(PriceCache).join(
        latest, (PriceCache.isin == latest.c.isin) & (PriceCache.fetched_date == latest.c.d)
    )
    return {r.isin: r for r in rows}


def _day_change_pct(row: PriceCache | None, prices_as_of) -> float | None:
    """Last session's move, in percent, from one `price_cache` row; None if unknown.

    `row.original_price` is the latest close (or the live price if the market was open
    when the day's first valuation ran) and `row.previous_close` the session before,
    both in the listing's own currency, so the euro exchange rate does not leak into
    the move. `prices_as_of` is the newest `fetched_date` across the portfolio.

    Fail-closed, like the totals:
    * no row, no price or no previous close (rows written before the column existed) →
      unknown;
    * a row older than the rest of the portfolio is a price that could not be refreshed;
      its move belongs to another day and would read as today's;
    * a move beyond ±MAX_DAY_CHANGE_PCT is far likelier a Yahoo slip (an unadjusted
      split, pence read as pounds) than a session, and a wrong number in the town is
      worse than a dash.
    """
    if row is None or row.original_price is None or row.previous_close is None:
        return None
    if row.previous_close <= 0 or row.fetched_date != prices_as_of:
        return None
    pct = float((row.original_price / row.previous_close - 1) * 100)
    if abs(pct) > MAX_DAY_CHANGE_PCT:
        return None
    return round(pct, 4)


def build_world(db: Session, user_id: int) -> dict:
    positions = get_open_positions(db, user_id)
    isins = [p.isin for p in positions]
    price_rows = _latest_price_rows(db, isins) if isins else {}

    profiles = (
        {p.isin: p for p in db.query(ListingProfile).filter(ListingProfile.isin.in_(isins))}
        if isins
        else {}
    )
    report_sectors = _report_sector(db, isins) if isins else {}

    valued = [p for p in positions if p.market_value_eur is not None]
    prices_as_of = (
        max((r.fetched_date for r in price_rows.values()), default=None) if valued else None
    )

    assets = []
    for p in positions:
        asset_type, sector, classified = _classify(
            p.isin, profiles.get(p.isin), report_sectors.get(p.isin)
        )
        assets.append(
            {
                "isin": p.isin,
                "ticker": p.ticker,
                "name": p.name,
                "country": p.country,
                "brokers": _brokers(p),
                "asset_type": asset_type,
                "sector": sector,
                "classified": classified,
                "archetype_override": ARCHETYPE_OVERRIDES.get(p.isin),
                "market_value_eur": _money(p.market_value_eur),
                "weight_pct": float(round(p.weight_pct, 4)) if p.weight_pct is not None else None,
                "total_cost_eur": _money(p.total_cost_eur),
                "unrealized_pl_eur": _money(p.unrealized_pl_eur),
                # From the stored previous close, never from two price_cache snapshots:
                # those are whenever the portfolio happened to be opened, not sessions.
                "day_change_pct": _day_change_pct(price_rows.get(p.isin), prices_as_of),
            }
        )

    valuation_complete = len(valued) == len(positions)
    return {
        "summary": {
            "positions": len(positions),
            "valued": len(valued),
            "cost_known": sum(1 for p in positions if p.total_cost_eur is not None),
            "valuation_complete": valuation_complete,
            "total_market_value": (
                _money(sum((p.market_value_eur for p in valued), Decimal(0)))
                if valuation_complete
                else None
            ),
            "classified": sum(1 for a in assets if a["classified"]),
            "prices_as_of": prices_as_of.isoformat() if prices_as_of else None,
        },
        "assets": assets,
    }
