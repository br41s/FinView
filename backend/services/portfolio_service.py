"""Portfolio service — compute open positions from transactions + live prices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import Account, PortfolioHolding, Transaction, TransactionType
from backend.services.prices import fetch_and_cache_prices

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


@dataclass
class Position:
    isin: str
    ticker: str | None
    name: str
    country: str | None
    broker: str
    account_id: int
    quantity: Decimal
    avg_cost_eur: Decimal | None = None  # per unit; None when cost basis unknown (snapshot-only)
    total_cost_eur: Decimal | None = None  # None when cost basis unknown
    current_price_eur: Decimal | None = None
    market_value_eur: Decimal | None = None
    unrealized_pl_eur: Decimal | None = None
    unrealized_pl_pct: Decimal | None = None
    weight_pct: Decimal | None = None  # filled later


def get_open_positions(db: Session, user_id: int | None = None, *, skip_prices: bool = False) -> list[Position]:
    """Compute open positions by aggregating BUY - SELL per ISIN per account.

    Uses FIFO-style average cost: sum(cost of buys consumed) / remaining qty.
    When *skip_prices* is True the expensive yfinance call is skipped and
    price-dependent fields (current_price, market_value, P&L, weight) stay None.
    """
    # Get accounts
    account_q = db.query(Account)
    if user_id is not None:
        account_q = account_q.filter(Account.user_id == user_id)
    accounts = {a.id: a for a in account_q.all()}

    if not accounts:
        return []

    account_ids = list(accounts.keys())

    # Load all snapshots: year-end holdings snapshots from fiscal reports
    # (ING, DEGIRO, BBVA, etc.). The latest year's snapshot is authoritative
    # for quantity held today.
    snapshot_rows = (
        db.query(PortfolioHolding)
        .filter(
            PortfolioHolding.account_id.in_(account_ids),
            PortfolioHolding.isin.isnot(None),
            PortfolioHolding.isin != "",
        )
        .all()
    )
    max_snap_year_by_acct: dict[int, int] = {}
    historical_snap_keys: set[tuple[int, str]] = set()
    latest_snapshots: dict[tuple[int, str], PortfolioHolding] = {}
    for h in snapshot_rows:
        historical_snap_keys.add((h.account_id, h.isin))
        if h.account_id not in max_snap_year_by_acct or h.fiscal_year > max_snap_year_by_acct[h.account_id]:
            max_snap_year_by_acct[h.account_id] = h.fiscal_year
    for h in snapshot_rows:
        if h.fiscal_year == max_snap_year_by_acct.get(h.account_id) and h.quantity > 0:
            latest_snapshots[(h.account_id, h.isin)] = h

    # Run FIFO over ALL transactions to build the tx-based view. This gives
    # us real cost basis for broker reports that include full acquisition
    # history (BBVA, eToro). We'll reconcile with snapshots afterwards.
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.type.in_([TransactionType.BUY, TransactionType.SELL]),
            Transaction.isin.isnot(None),
        )
        .order_by(Transaction.trade_date.asc(), Transaction.id.asc())
        .all()
    )
    tx_positions: dict[tuple[int, str], Position] = {}
    for tx in txs:
        key = (tx.account_id, tx.isin)
        if key not in tx_positions:
            acct = accounts[tx.account_id]
            tx_positions[key] = Position(
                isin=tx.isin,
                ticker=tx.ticker,
                name=tx.name,
                country=tx.country,
                broker=acct.broker,
                account_id=tx.account_id,
                quantity=ZERO,
                total_cost_eur=ZERO,
            )
        pos = tx_positions[key]
        if tx.type == TransactionType.BUY:
            pos.total_cost_eur = (pos.total_cost_eur or ZERO) + abs(tx.net_amount_eur)
            pos.quantity += tx.quantity
        elif tx.type == TransactionType.SELL:
            sell_qty = abs(tx.quantity)
            if pos.quantity > ZERO and pos.total_cost_eur is not None:
                cost_fraction = (sell_qty / pos.quantity) * pos.total_cost_eur
                pos.total_cost_eur -= cost_fraction
            pos.quantity -= sell_qty
        if tx.name and not pos.name:
            pos.name = tx.name
        if tx.ticker and not pos.ticker:
            pos.ticker = tx.ticker

    # Reconcile tx-based positions with latest snapshots:
    # - For accounts WITHOUT any snapshot history: trust tx-based (eToro/IBKR).
    # - For accounts WITH snapshots:
    #     * Snapshot exists AND tx qty matches snapshot qty (±0.01): use tx-based
    #       (preserves real cost basis).
    #     * Snapshot exists but tx qty differs: snapshot wins, cost unknown
    #       (txs are incomplete — e.g., ING fiscal PDFs that only cover partial
    #       history and include scrip subscriptions already reflected in snapshot).
    #     * Snapshot doesn't include this ISIN but txs do: position was closed
    #       by year-end (or never in snapshot) → check tx qty. If > 0 and no
    #       historical snapshot entry → flow-through (eToro-like). Include.
    #       If historical snapshot entry exists (was sold): exclude.
    positions: dict[tuple[int, str], Position] = {}
    qty_tolerance = Decimal("0.01")

    for key, snap in latest_snapshots.items():
        acct = accounts[snap.account_id]
        tx_pos = tx_positions.get(key)
        if tx_pos is not None and abs(tx_pos.quantity - snap.quantity) <= qty_tolerance:
            # Tx history matches snapshot — use tx-based (keeps real cost)
            positions[key] = tx_pos
            positions[key].quantity = snap.quantity  # snap is the source of truth
        else:
            # Snapshot is authoritative, cost basis unknown
            positions[key] = Position(
                isin=snap.isin,
                ticker=tx_pos.ticker if tx_pos else None,
                name=snap.name,
                country=snap.country,
                broker=acct.broker,
                account_id=snap.account_id,
                quantity=snap.quantity,
            )

    # Include tx-only positions (no snapshot for this account/isin) where
    # no historical snapshot existed either → genuine positions from brokers
    # without fiscal reports (eToro, etc.).
    for key, pos in tx_positions.items():
        if key in positions:
            continue
        if key in historical_snap_keys:
            # Was in snapshot history but not in latest → sold. Skip.
            continue
        positions[key] = pos

    # Filter out closed positions (qty <= 0)
    open_positions = [p for p in positions.values() if p.quantity > ZERO]

    # Compute avg cost only when total cost is known
    for pos in open_positions:
        if pos.total_cost_eur is not None and pos.quantity > ZERO:
            pos.avg_cost_eur = pos.total_cost_eur / pos.quantity

    # Fetch live prices (skippable for fast first-paint)
    isins = list({p.isin for p in open_positions})
    if isins and not skip_prices:
        prices = fetch_and_cache_prices(db, isins)
        total_market_value = ZERO

        for pos in open_positions:
            price = prices.get(pos.isin)
            if price is not None:
                pos.current_price_eur = price
                pos.market_value_eur = price * pos.quantity
                if pos.total_cost_eur is not None:
                    pos.unrealized_pl_eur = pos.market_value_eur - pos.total_cost_eur
                    if pos.total_cost_eur > ZERO:
                        pos.unrealized_pl_pct = (pos.unrealized_pl_eur / pos.total_cost_eur) * Decimal("100")
                total_market_value += pos.market_value_eur

        # Compute weight
        if total_market_value > ZERO:
            for pos in open_positions:
                if pos.market_value_eur is not None:
                    pos.weight_pct = (pos.market_value_eur / total_market_value) * Decimal("100")

    # Sort by market value descending (positions without price at end)
    open_positions.sort(
        key=lambda p: p.market_value_eur or ZERO,
        reverse=True,
    )

    return open_positions


def get_portfolio_summary(db: Session, user_id: int | None = None, *, skip_prices: bool = False) -> dict:
    """Return aggregated portfolio stats."""
    positions = get_open_positions(db, user_id, skip_prices=skip_prices)

    total_cost = sum((p.total_cost_eur for p in positions if p.total_cost_eur is not None), ZERO)
    total_value = sum((p.market_value_eur for p in positions if p.market_value_eur), ZERO)
    total_pl = sum((p.unrealized_pl_eur for p in positions if p.unrealized_pl_eur), ZERO)
    total_pl_pct = (total_pl / total_cost * Decimal("100")) if total_cost > ZERO else ZERO

    # Count unique ISINs and brokers
    unique_isins = {p.isin for p in positions}
    unique_brokers = {p.broker for p in positions}

    return {
        "total_positions": len(positions),
        "unique_assets": len(unique_isins),
        "brokers": len(unique_brokers),
        "total_invested": float(round(total_cost, 2)),
        "total_market_value": float(round(total_value, 2)),
        "unrealized_pl": float(round(total_pl, 2)),
        "unrealized_pl_pct": float(round(total_pl_pct, 2)),
    }


def get_position_detail(db: Session, isin: str, user_id: int | None = None) -> dict | None:
    """Detailed info for a single ISIN across all accounts."""
    positions = get_open_positions(db, user_id)
    isin_positions = [p for p in positions if p.isin == isin]

    if not isin_positions:
        return None

    # Aggregate across accounts
    total_qty = sum((p.quantity for p in isin_positions), ZERO)
    known_costs = [p.total_cost_eur for p in isin_positions if p.total_cost_eur is not None]
    total_cost: Decimal | None = sum(known_costs, ZERO) if known_costs else None
    total_value = sum((p.market_value_eur for p in isin_positions if p.market_value_eur), ZERO)
    total_pl = sum((p.unrealized_pl_eur for p in isin_positions if p.unrealized_pl_eur), ZERO)
    avg_cost = (total_cost / total_qty) if (total_cost is not None and total_qty > ZERO) else None
    current_price = isin_positions[0].current_price_eur

    # Get transaction history for this ISIN
    account_q = db.query(Account)
    if user_id is not None:
        account_q = account_q.filter(Account.user_id == user_id)
    account_ids = [a.id for a in account_q.all()]

    txs = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.isin == isin,
        )
        .order_by(Transaction.trade_date.desc())
        .limit(100)
        .all()
    )

    return {
        "isin": isin,
        "name": isin_positions[0].name,
        "ticker": isin_positions[0].ticker,
        "country": isin_positions[0].country,
        "total_quantity": float(round(total_qty, 6)),
        "avg_cost_eur": float(round(avg_cost, 4)) if avg_cost is not None else None,
        "total_cost_eur": float(round(total_cost, 2)) if total_cost is not None else None,
        "current_price_eur": float(round(current_price, 4)) if current_price else None,
        "market_value_eur": float(round(total_value, 2)),
        "unrealized_pl_eur": float(round(total_pl, 2)) if total_cost is not None else None,
        "unrealized_pl_pct": float(round(total_pl / total_cost * 100, 2)) if total_cost and total_cost > ZERO else None,
        "accounts": [
            {
                "broker": p.broker,
                "account_id": p.account_id,
                "quantity": float(round(p.quantity, 6)),
                "cost_eur": float(round(p.total_cost_eur, 2)) if p.total_cost_eur is not None else None,
                "value_eur": float(round(p.market_value_eur, 2)) if p.market_value_eur else None,
            }
            for p in isin_positions
        ],
        "transactions": [
            {
                "id": tx.id,
                "type": tx.type,
                "date": tx.trade_date.isoformat(),
                "quantity": float(tx.quantity),
                "price": float(tx.price),
                "currency": tx.currency,
                "net_eur": float(tx.net_amount_eur),
            }
            for tx in txs
        ],
    }
