"""API endpoints for transactions, dividends, holdings."""

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func

from backend.api.schemas import (
    CapitalGainOut,
    DividendSummary,
    TransactionOut,
)
from backend.database import DbSession, LimitParam, OffsetParam
from backend.models import TaxLot, Transaction, TransactionType

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    db: DbSession,
    limit: LimitParam = 200,
    offset: OffsetParam = 0,
    fiscal_year: int | None = None,
    tx_type: str | None = None,
    isin: str | None = None,
):
    """List transactions with filters."""
    q = db.query(Transaction)

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    if isin:
        q = q.filter(Transaction.isin == isin)

    return q.order_by(Transaction.trade_date.desc()).offset(offset).limit(limit).all()


@router.get("/dividends/summary", response_model=list[DividendSummary])
def dividend_summary(db: DbSession, fiscal_year: int | None = None):
    """Aggregate dividends by ISIN."""
    q = db.query(
        Transaction.isin,
        Transaction.name,
        Transaction.country,
        func.sum(Transaction.gross_amount).label("total_gross_eur"),
        func.sum(Transaction.withholding_tax).label("total_withholding_eur"),
        func.sum(Transaction.net_amount_eur).label("total_net_eur"),
        func.count().label("payment_count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    rows = q.group_by(Transaction.isin, Transaction.name, Transaction.country).all()

    return [
        DividendSummary(
            isin=r.isin or "",
            name=r.name,
            country=r.country,
            total_gross_eur=r.total_gross_eur or Decimal("0"),
            total_withholding_eur=r.total_withholding_eur or Decimal("0"),
            total_net_eur=r.total_net_eur or Decimal("0"),
            payment_count=r.payment_count,
        )
        for r in rows
    ]


@router.get("/capital-gains", response_model=list[CapitalGainOut])
def capital_gains(db: DbSession, fiscal_year: int | None = None):
    """List realized capital gains/losses from FIFO lots."""
    q = db.query(TaxLot).filter(TaxLot.sell_tx_id.isnot(None))

    if fiscal_year:
        q = q.filter(func.strftime("%Y", TaxLot.close_date) == str(fiscal_year))

    lots = q.order_by(TaxLot.close_date.desc()).all()

    return [
        CapitalGainOut(
            id=lot.id,
            isin=lot.isin,
            name=lot.buy_tx.name,
            buy_date=lot.buy_tx.trade_date,
            sell_date=lot.close_date,
            quantity=lot.quantity_sold or Decimal("0"),
            cost_basis_eur=lot.cost_basis_eur,
            proceeds_eur=lot.proceeds_eur or Decimal("0"),
            realized_pl_eur=lot.realized_pl_eur or Decimal("0"),
            holding_period=lot.holding_period,
        )
        for lot in lots
    ]
