"""Cross-broker FIFO engine for Spanish IRPF compliance.

Implements chronological FIFO matching across all broker accounts
to compute the correct cost basis for casillas 332/337.
Broker-provided TaxLots are kept untouched; this engine creates
parallel CrossBrokerLot records and FIFOAdjustment summaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.services.sql_compat import year_str as _year_str
from backend.models import (
    Account,
    CrossBrokerLot,
    FIFOAdjustment,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _BuySlice:
    """A remaining portion of a buy transaction available for FIFO matching."""
    tx_id: int
    broker: str
    trade_date: date
    isin: str
    name: str
    remaining: Decimal  # qty still unmatched
    price_eur: Decimal  # per-unit cost in EUR


@dataclass
class _SellRecord:
    """A sell transaction to match against the buy queue."""
    tx_id: int
    broker: str
    trade_date: date
    isin: str
    name: str
    quantity: Decimal
    price_eur: Decimal  # per-unit proceeds in EUR


@dataclass
class _MatchedLot:
    """Result of matching a sell against one or more buys."""
    buy_tx_id: int
    sell_tx_id: int
    buy_broker: str
    sell_broker: str
    isin: str
    name: str
    quantity: Decimal
    cost_basis_eur: Decimal
    proceeds_eur: Decimal
    realized_pl_eur: Decimal
    holding_period: str  # ">=1y" or "<1y"
    casilla: int  # 332 or 337


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _holding_period_label(buy_date: date, sell_date: date) -> tuple[str, int]:
    """Return (label, casilla) based on holding period."""
    days = (sell_date - buy_date).days
    if days >= 365:
        return ">=1y", 332
    return "<1y", 332  # both gains go to 332; losses to 337 — casilla set later


def _get_real_buys(db: Session, isin: str) -> list[_BuySlice]:
    """Get all real BUY transactions for an ISIN across all accounts, sorted by date.

    Real = stored via _store_transaction (has import_id) with type BUY
    and NOT a synthetic buy created only for a TaxLot.
    We identify real buys as those NOT referenced by TaxLot.buy_tx_id.
    """
    # IDs of synthetic buy transactions (created for TaxLots)
    synthetic_buy_ids = (
        db.query(TaxLot.buy_tx_id)
        .filter(TaxLot.buy_tx_id.isnot(None))
        .scalar_subquery()
    )

    rows = (
        db.query(Transaction, Account.broker)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.isin == isin,
            Transaction.type == TransactionType.BUY.value,
            Transaction.id.notin_(synthetic_buy_ids),
        )
        .order_by(Transaction.trade_date.asc(), Transaction.id.asc())
        .all()
    )

    return [
        _BuySlice(
            tx_id=tx.id,
            broker=broker.value if hasattr(broker, 'value') else broker,
            trade_date=tx.trade_date,
            isin=tx.isin,
            name=tx.name or "",
            remaining=tx.quantity,
            price_eur=tx.net_amount_eur / tx.quantity if tx.quantity else Decimal("0"),
        )
        for tx, broker in rows
    ]


def _get_real_sells(db: Session, isin: str, fiscal_year: int) -> list[_SellRecord]:
    """Get all real SELL transactions for an ISIN in a fiscal year."""
    synthetic_sell_ids = (
        db.query(TaxLot.sell_tx_id)
        .filter(TaxLot.sell_tx_id.isnot(None))
        .scalar_subquery()
    )

    year_value = str(fiscal_year)
    rows = (
        db.query(Transaction, Account.broker)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.isin == isin,
            Transaction.type == TransactionType.SELL.value,
            Transaction.id.notin_(synthetic_sell_ids),
            _year_str(Transaction.trade_date) == year_value,
        )
        .order_by(Transaction.trade_date.asc(), Transaction.id.asc())
        .all()
    )

    return [
        _SellRecord(
            tx_id=tx.id,
            broker=broker.value if hasattr(broker, 'value') else broker,
            trade_date=tx.trade_date,
            isin=tx.isin,
            name=tx.name or "",
            quantity=abs(tx.quantity),
            price_eur=abs(tx.net_amount_eur / tx.quantity) if tx.quantity else Decimal("0"),
        )
        for tx, broker in rows
    ]


def _fifo_match(buys: list[_BuySlice], sells: list[_SellRecord]) -> list[_MatchedLot]:
    """Match sells to buys using strict FIFO (oldest buy first)."""
    matched: list[_MatchedLot] = []

    for sell in sells:
        qty_to_match = sell.quantity
        while qty_to_match > 0 and buys:
            buy = buys[0]
            if buy.remaining <= 0:
                buys.pop(0)
                continue

            match_qty = min(buy.remaining, qty_to_match)
            cost = match_qty * buy.price_eur
            proceeds = match_qty * sell.price_eur
            pl = proceeds - cost

            hp_label, _ = _holding_period_label(buy.trade_date, sell.trade_date)
            casilla = 332 if pl >= 0 else 337

            matched.append(_MatchedLot(
                buy_tx_id=buy.tx_id,
                sell_tx_id=sell.tx_id,
                buy_broker=buy.broker,
                sell_broker=sell.broker,
                isin=sell.isin,
                name=sell.name or buy.name,
                quantity=match_qty,
                cost_basis_eur=cost,
                proceeds_eur=proceeds,
                realized_pl_eur=pl,
                holding_period=hp_label,
                casilla=casilla,
            ))

            buy.remaining -= match_qty
            qty_to_match -= match_qty

            if buy.remaining <= 0:
                buys.pop(0)

    return matched


def _get_broker_pl_for_isin(db: Session, isin: str, fiscal_year: int) -> Decimal:
    """Sum broker-reported P&L for an ISIN from TaxLot table."""
    year_value = str(fiscal_year)
    result = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .filter(
            TaxLot.isin == isin,
            _year_str(TaxLot.close_date) == year_value,
        )
        .scalar()
    )
    return Decimal(str(result)) if result else Decimal("0")


def _find_multi_broker_isins(db: Session, fiscal_year: int) -> list[str]:
    """Find ISINs that have real BUY transactions in 2+ different accounts.

    These are the ISINs that could have different FIFO if bought at
    different brokers and then sold at one of them.
    """
    # All ISINs that have sells in this fiscal year
    year_value = str(fiscal_year)
    sell_isins = (
        db.query(Transaction.isin)
        .filter(
            Transaction.type == TransactionType.SELL.value,
            _year_str(Transaction.trade_date) == year_value,
        )
        .distinct()
        .scalar_subquery()
    )

    # Among those, find ISINs with buys in 2+ different accounts (any year)
    synthetic_buy_ids = (
        db.query(TaxLot.buy_tx_id)
        .filter(TaxLot.buy_tx_id.isnot(None))
        .scalar_subquery()
    )

    multi = (
        db.query(Transaction.isin)
        .filter(
            Transaction.type == TransactionType.BUY.value,
            Transaction.isin.in_(sell_isins),
            Transaction.id.notin_(synthetic_buy_ids),
        )
        .group_by(Transaction.isin)
        .having(func.count(func.distinct(Transaction.account_id)) >= 2)
        .all()
    )

    return [row[0] for row in multi]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def recalculate_cross_broker_fifo(db: Session, fiscal_year: int, user_id: int) -> dict:
    """Recalculate cross-broker FIFO for a fiscal year.

    1. Delete existing CrossBrokerLots and FIFOAdjustments for the year
    2. Find ISINs with real transactions in 2+ accounts
    3. FIFO-match sells to oldest buys across all accounts
    4. Compare with broker TaxLots → create FIFOAdjustment if different

    Returns summary dict with counts.
    """
    # Clean previous results for this year (scoped to user if provided)
    cbl_q = db.query(CrossBrokerLot).filter(CrossBrokerLot.fiscal_year == fiscal_year)
    adj_q = db.query(FIFOAdjustment).filter(FIFOAdjustment.fiscal_year == fiscal_year)
    if user_id:
        adj_q = adj_q.filter(FIFOAdjustment.user_id == user_id)
    cbl_q.delete(synchronize_session="fetch")
    adj_q.delete(synchronize_session="fetch")
    db.flush()

    multi_isins = _find_multi_broker_isins(db, fiscal_year)
    if not multi_isins:
        logger.info("No multi-broker ISINs found for %d", fiscal_year)
        return {"lots_created": 0, "adjustments": 0, "isins_analyzed": 0}

    lots_created = 0
    adjustments_created = 0

    for isin in multi_isins:
        buys = _get_real_buys(db, isin)
        sells = _get_real_sells(db, isin, fiscal_year)

        if not buys or not sells:
            continue

        matched = _fifo_match(buys, sells)

        fifo_pl = Decimal("0")
        name = ""
        for lot in matched:
            name = name or lot.name
            cbl = CrossBrokerLot(
                fiscal_year=fiscal_year,
                isin=isin,
                name=lot.name,
                buy_tx_id=lot.buy_tx_id,
                sell_tx_id=lot.sell_tx_id,
                buy_broker=lot.buy_broker,
                sell_broker=lot.sell_broker,
                quantity=lot.quantity,
                cost_basis_eur=lot.cost_basis_eur,
                proceeds_eur=lot.proceeds_eur,
                realized_pl_eur=lot.realized_pl_eur,
                holding_period=lot.holding_period,
                casilla=lot.casilla,
            )
            db.add(cbl)
            fifo_pl += lot.realized_pl_eur
            lots_created += 1

        # Compare with broker-reported P&L
        broker_pl = _get_broker_pl_for_isin(db, isin, fiscal_year)
        adjustment = fifo_pl - broker_pl

        if adjustment != Decimal("0"):
            adj = FIFOAdjustment(
                fiscal_year=fiscal_year,
                isin=isin,
                name=name,
                broker_pl_eur=broker_pl,
                fifo_pl_eur=fifo_pl,
                adjustment_eur=adjustment,
                user_id=user_id,
                note=(
                    f"FIFO cruzado difiere del broker: "
                    f"broker={broker_pl:.2f}€, FIFO={fifo_pl:.2f}€, "
                    f"ajuste={adjustment:+.2f}€"
                ),
            )
            db.add(adj)
            adjustments_created += 1

    db.flush()
    logger.info(
        "Cross-broker FIFO for %d: %d lots, %d adjustments, %d ISINs",
        fiscal_year, lots_created, adjustments_created, len(multi_isins),
    )
    return {
        "lots_created": lots_created,
        "adjustments": adjustments_created,
        "isins_analyzed": len(multi_isins),
    }
