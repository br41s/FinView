"""Portfolio service — compute open positions from transactions + live prices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
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


PosKey = tuple[int, str]
QTY_TOLERANCE = Decimal("0.01")


def _load_accounts(db: Session, user_id: int | None) -> dict[int, Account]:
    q = db.query(Account)
    if user_id is not None:
        q = q.filter(Account.user_id == user_id)
    return {a.id: a for a in q.all()}


def _load_snapshots(
    db: Session, account_ids: list[int]
) -> tuple[dict[PosKey, PortfolioHolding], set[PosKey], dict[int, date]]:
    """Return (latest_snapshots, all_historical_keys, snap_end_date_by_acct).

    The latest fiscal-year snapshot is authoritative for quantity held today.
    snap_end_date is Dec 31 of that year — used to partition transactions into
    pre- vs post-snapshot when reconciling.
    """
    rows = (
        db.query(PortfolioHolding)
        .filter(
            PortfolioHolding.account_id.in_(account_ids),
            PortfolioHolding.isin.isnot(None),
            PortfolioHolding.isin != "",
        )
        .all()
    )
    max_year: dict[int, int] = {}
    historical: set[PosKey] = set()
    for h in rows:
        historical.add((h.account_id, h.isin))
        if h.account_id not in max_year or h.fiscal_year > max_year[h.account_id]:
            max_year[h.account_id] = h.fiscal_year
    latest: dict[PosKey, PortfolioHolding] = {
        (h.account_id, h.isin): h
        for h in rows
        if h.fiscal_year == max_year.get(h.account_id) and h.quantity > 0
    }
    end_dates = {acct_id: date(fy, 12, 31) for acct_id, fy in max_year.items()}
    return latest, historical, end_dates


def _apply_tx_to_position(pos: Position, tx: Transaction) -> None:
    if tx.type == TransactionType.BUY:
        pos.total_cost_eur = (pos.total_cost_eur or ZERO) + abs(tx.net_amount_eur)
        pos.quantity += tx.quantity
    elif tx.type == TransactionType.SELL:
        sell_qty = abs(tx.quantity)
        if pos.quantity > ZERO and pos.total_cost_eur is not None:
            pos.total_cost_eur -= (sell_qty / pos.quantity) * pos.total_cost_eur
        pos.quantity -= sell_qty
    if tx.name and not pos.name:
        pos.name = tx.name
    if tx.ticker and not pos.ticker:
        pos.ticker = tx.ticker


def _build_tx_positions(
    db: Session,
    account_ids: list[int],
    accounts: dict[int, Account],
    snap_end_by_acct: dict[int, date],
) -> tuple[dict[PosKey, Position], dict[PosKey, Decimal]]:
    """FIFO aggregate of all BUY/SELL transactions, plus qty-at-snap-date."""
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
    positions: dict[PosKey, Position] = {}
    qty_at_snap: dict[PosKey, Decimal] = {}
    for tx in txs:
        key = (tx.account_id, tx.isin)
        if key not in positions:
            acct = accounts[tx.account_id]
            positions[key] = Position(
                isin=tx.isin, ticker=tx.ticker, name=tx.name, country=tx.country,
                broker=acct.broker, account_id=tx.account_id,
                quantity=ZERO, total_cost_eur=ZERO,
            )
        snap_end = snap_end_by_acct.get(tx.account_id)
        if snap_end is not None and tx.trade_date <= snap_end:
            delta = tx.quantity if tx.type == TransactionType.BUY else -abs(tx.quantity)
            qty_at_snap[key] = qty_at_snap.get(key, ZERO) + delta
        _apply_tx_to_position(positions[key], tx)
    return positions, qty_at_snap


def _reconcile(
    latest_snapshots: dict[PosKey, PortfolioHolding],
    historical_snap_keys: set[PosKey],
    tx_positions: dict[PosKey, Position],
    tx_qty_at_snap: dict[PosKey, Decimal],
    accounts: dict[int, Account],
) -> dict[PosKey, Position]:
    """Merge snapshot-authoritative and tx-derived views.

    - Snapshot present AND tx qty at snap date matches (±0.01): use tx_pos
      (preserves real cost basis, including post-snapshot activity).
    - Snapshot present but tx qty differs: snapshot wins, cost unknown.
    - Tx-only position, never in any snapshot: flow-through (eToro/IBKR).
    - Tx-only position that was in historical snapshots but not latest: sold, skip.
    """
    out: dict[PosKey, Position] = {}
    for key, snap in latest_snapshots.items():
        tx_pos = tx_positions.get(key)
        tx_qty_snap = tx_qty_at_snap.get(key, ZERO)
        if tx_pos is not None and abs(tx_qty_snap - snap.quantity) <= QTY_TOLERANCE:
            out[key] = tx_pos
        else:
            acct = accounts[snap.account_id]
            out[key] = Position(
                isin=snap.isin,
                ticker=tx_pos.ticker if tx_pos else None,
                name=snap.name, country=snap.country,
                broker=acct.broker, account_id=snap.account_id,
                quantity=snap.quantity,
            )
    for key, pos in tx_positions.items():
        if key not in out and key not in historical_snap_keys:
            out[key] = pos
    return out


def _apply_prices(db: Session, positions: list[Position]) -> None:
    """Fetch live prices and fill market_value, P&L, and weight_pct in place."""
    isins = list({p.isin for p in positions})
    if not isins:
        return
    prices = fetch_and_cache_prices(db, isins)
    total_mv = ZERO
    for pos in positions:
        price = prices.get(pos.isin)
        if price is None:
            continue
        pos.current_price_eur = price
        pos.market_value_eur = price * pos.quantity
        if pos.total_cost_eur is not None:
            pos.unrealized_pl_eur = pos.market_value_eur - pos.total_cost_eur
            if pos.total_cost_eur > ZERO:
                pos.unrealized_pl_pct = (pos.unrealized_pl_eur / pos.total_cost_eur) * Decimal("100")
        total_mv += pos.market_value_eur
    if total_mv > ZERO:
        for pos in positions:
            if pos.market_value_eur is not None:
                pos.weight_pct = (pos.market_value_eur / total_mv) * Decimal("100")


def get_open_positions(db: Session, user_id: int | None = None, *, skip_prices: bool = False) -> list[Position]:
    """Compute open positions by aggregating BUY - SELL per ISIN per account.

    Uses FIFO-style average cost: sum(cost of buys consumed) / remaining qty.
    When *skip_prices* is True the expensive yfinance call is skipped and
    price-dependent fields (current_price, market_value, P&L, weight) stay None.
    """
    accounts = _load_accounts(db, user_id)
    if not accounts:
        return []
    account_ids = list(accounts.keys())

    latest_snapshots, historical_keys, snap_end_by_acct = _load_snapshots(db, account_ids)
    tx_positions, tx_qty_at_snap = _build_tx_positions(
        db, account_ids, accounts, snap_end_by_acct,
    )
    positions = _reconcile(
        latest_snapshots, historical_keys, tx_positions, tx_qty_at_snap, accounts,
    )

    open_positions = [p for p in positions.values() if p.quantity > ZERO]
    for pos in open_positions:
        if pos.total_cost_eur is not None and pos.quantity > ZERO:
            pos.avg_cost_eur = pos.total_cost_eur / pos.quantity

    if not skip_prices:
        _apply_prices(db, open_positions)

    open_positions.sort(key=lambda p: p.market_value_eur or ZERO, reverse=True)
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
