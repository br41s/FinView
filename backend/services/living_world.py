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
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import Account, ListingProfile, PriceCache, Transaction, TransactionType
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
    if row is None or row.fetched_date != prices_as_of:
        return None
    return _move_pct(row)


def _move_pct(row: PriceCache) -> float | None:
    """The session move one row records, under the same fail-closed rules."""
    if row.original_price is None or row.previous_close is None or row.previous_close <= 0:
        return None
    pct = float((row.original_price / row.previous_close - 1) * 100)
    if abs(pct) > MAX_DAY_CHANGE_PCT:
        return None
    return round(pct, 4)


# ── Real events ───────────────────────────────────────────────────────────────
#
# Facts only, from what FinView already stores: the town's widest activity window is a
# week, so that is how far back they go. The frontend turns them into cards and scores
# them with the same rule as everything else (`model/priority.ts`); the copy lives there.

EVENT_WINDOW_DAYS = 7
# A smaller daily move is noise for a town of ~100 buildings; 2 % is also where the
# priority rule's magnitude factor reaches 1.
PRICE_MOVE_EVENT_PCT = 2.0
_LEDGER_EVENT_TYPES = (TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND)


def _price_move_events(db: Session, positions: list[Position], since: date) -> list[dict]:
    names = {p.isin: p.name for p in positions}
    rows = db.query(PriceCache).filter(
        PriceCache.isin.in_(names), PriceCache.fetched_date >= since
    )
    out = []
    for row in rows:
        pct = _move_pct(row)
        if pct is None or abs(pct) < PRICE_MOVE_EVENT_PCT:
            continue
        out.append({
            "id": f"px:{row.isin}:{row.fetched_date.isoformat()}",
            "event_type": "price_move_up" if pct > 0 else "price_move_down",
            "isin": row.isin,
            "name": names[row.isin],
            "occurred_on": row.fetched_date,
            "source_type": "price_cache",
            # A close against the close before: computed here, not reported by anyone.
            "confidence": "derived",
            "metrics": {
                "change_pct": round(pct, 2),
                "price": float(row.original_price),
                "currency": row.original_currency or row.currency,
                "period": "1d",
            },
        })
    return out


def _ledger_events(db: Session, user_id: int, open_isins: set[str], since: date) -> list[dict]:
    rows = (
        db.query(Transaction, Account.broker)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.trade_date >= since,
            Transaction.type.in_(_LEDGER_EVENT_TYPES),
            Transaction.isin.isnot(None),
        )
    )
    out = []
    for tx, broker in rows:
        account = getattr(broker, "value", broker)
        if tx.type == TransactionType.DIVIDEND:
            event_type = "dividend_paid"
            metrics = {
                "net_eur": _money(tx.net_amount_eur),
                "gross": _money(tx.gross_amount),
                "currency": tx.currency,
                "account": account,
            }
        else:
            if tx.type == TransactionType.BUY:
                event_type = "position_added"
            else:
                # Closed means the ISIN is no longer held at all, across every broker.
                event_type = "position_reduced" if tx.isin in open_isins else "position_closed"
            metrics = {
                "quantity": float(abs(tx.quantity)),
                "value_eur": _money(abs(tx.net_amount_eur)),
                "account": account,
            }
        out.append({
            "id": f"tx:{tx.id}",
            "event_type": event_type,
            "isin": tx.isin,
            "name": tx.name or tx.isin,
            "occurred_on": tx.trade_date,
            "source_type": "ledger",
            "confidence": "verified",
            "metrics": metrics,
        })
    return out


def _events(db: Session, user_id: int, positions: list[Position], today: date) -> list[dict]:
    since = today - timedelta(days=EVENT_WINDOW_DAYS)
    events = _ledger_events(db, user_id, {p.isin for p in positions}, since)
    if positions:
        events += _price_move_events(db, positions, since)
    return sorted(events, key=lambda e: (e["occurred_on"], e["id"]), reverse=True)


def build_world(db: Session, user_id: int, today: date | None = None) -> dict:
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
        "events": _events(db, user_id, positions, today or date.today()),
    }
