"""API endpoints for transactions, dividends, holdings."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    CapitalGainOut,
    DividendSummary,
    TransactionOut,
)
from backend.database import DbSession, LimitParam, OffsetParam
from backend.models import Account, TaxLot, Transaction, TransactionType
from backend.services.sql_compat import year_range

router = APIRouter(prefix="/transactions", tags=["transactions"])


# --------------- manual transaction schemas ---------------


class TransactionCreate(BaseModel):
    account_id: int
    type: str  # BUY, SELL, DIVIDEND, etc.
    trade_date: date
    isin: str | None = None
    ticker: str | None = None
    name: str = ""
    country: str | None = None
    quantity: Decimal
    price: Decimal
    currency: str = "EUR"
    exchange_rate: Decimal = Decimal("1")
    fees: Decimal = Decimal("0")
    withholding_tax: Decimal = Decimal("0")


class TransactionUpdate(BaseModel):
    name: str | None = None
    ticker: str | None = None
    country: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fees: Decimal | None = None


@router.get("", response_model=list[TransactionOut], include_in_schema=False)
@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    db: DbSession,
    user: CurrentUser,
    limit: LimitParam = 200,
    offset: OffsetParam = 0,
    fiscal_year: int | None = None,
    tx_type: str | None = None,
    isin: str | None = None,
):
    """List transactions with filters."""
    q = db.query(Transaction).join(Account).filter(Account.user_id == user.id)

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    if isin:
        q = q.filter(Transaction.isin == isin)

    return q.order_by(Transaction.trade_date.desc()).offset(offset).limit(limit).all()


@router.get("/dividends/summary", response_model=list[DividendSummary])
def dividend_summary(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """Aggregate dividends by ISIN."""
    q = db.query(
        Transaction.isin,
        func.min(Transaction.name).label("name"),
        func.max(Transaction.country).label("country"),
        func.sum(Transaction.gross_amount).label("total_gross_eur"),
        func.sum(Transaction.withholding_tax).label("total_withholding_eur"),
        func.sum(Transaction.net_amount_eur).label("total_net_eur"),
        func.count().label("payment_count"),
    ).join(Account).filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))

    rows = q.group_by(Transaction.isin).all()

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
def capital_gains(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """List realized capital gains/losses from FIFO lots."""
    q = (
        db.query(TaxLot)
        .join(Transaction, TaxLot.buy_tx_id == Transaction.id)
        .join(Account)
        .filter(Account.user_id == user.id, TaxLot.sell_tx_id.isnot(None))
    )

    if fiscal_year:
        q = q.filter(year_range(TaxLot.close_date, fiscal_year))

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


# --------------- manual transaction CRUD ---------------


@router.post("/", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(data: TransactionCreate, db: DbSession, user: CurrentUser):
    """Manually add a transaction."""
    # Validate account ownership
    account = (
        db.query(Account)
        .filter(Account.id == data.account_id, Account.user_id == user.id)
        .first()
    )
    if not account:
        raise HTTPException(404, "Account not found")

    # Validate type
    valid_types = [t.value for t in TransactionType]
    if data.type not in valid_types:
        raise HTTPException(400, f"Invalid type. Must be one of: {valid_types}")

    gross = data.quantity * data.price
    net_eur = (gross - data.fees - data.withholding_tax) * data.exchange_rate

    tx = Transaction(
        account_id=data.account_id,
        import_id=None,  # manual entry
        type=data.type,
        trade_date=data.trade_date,
        isin=data.isin,
        ticker=data.ticker,
        name=data.name,
        country=data.country,
        quantity=data.quantity,
        price=data.price,
        currency=data.currency,
        exchange_rate=data.exchange_rate,
        gross_amount=gross,
        fees=data.fees,
        withholding_tax=data.withholding_tax,
        net_amount_eur=net_eur,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.patch("/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, data: TransactionUpdate, db: DbSession, user: CurrentUser):
    """Update a manually-added transaction (import_id must be NULL)."""
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")

    # Verify ownership
    account = (
        db.query(Account)
        .filter(Account.id == tx.account_id, Account.user_id == user.id)
        .first()
    )
    if not account:
        raise HTTPException(404, "Transaction not found")

    if tx.import_id is not None:
        raise HTTPException(409, "Cannot edit imported transactions. Delete the import instead.")

    if data.name is not None:
        tx.name = data.name
    if data.ticker is not None:
        tx.ticker = data.ticker
    if data.country is not None:
        tx.country = data.country
    if data.quantity is not None:
        tx.quantity = data.quantity
    if data.price is not None:
        tx.price = data.price
    if data.fees is not None:
        tx.fees = data.fees

    # Recompute amounts
    tx.gross_amount = tx.quantity * tx.price
    tx.net_amount_eur = (tx.gross_amount - tx.fees - tx.withholding_tax) * tx.exchange_rate

    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(tx_id: int, db: DbSession, user: CurrentUser):
    """Delete a manually-added transaction."""
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")

    account = (
        db.query(Account)
        .filter(Account.id == tx.account_id, Account.user_id == user.id)
        .first()
    )
    if not account:
        raise HTTPException(404, "Transaction not found")

    if tx.import_id is not None:
        raise HTTPException(409, "Cannot delete imported transactions. Delete the import instead.")

    db.delete(tx)
    db.commit()
