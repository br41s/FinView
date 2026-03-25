"""API endpoints for fiscal / tax data."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.api.schemas import CasillaOut, DashboardStats, FiscalSummary
from backend.database import get_db
from backend.models import (
    Account,
    ImportRecord,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)

router = APIRouter(prefix="/fiscal", tags=["fiscal"])


@router.get("/casillas", response_model=list[CasillaOut])
def list_casillas(fiscal_year: int | None = None, db: Session = Depends(get_db)):
    """List all pre-calculated tax casillas."""
    q = db.query(TaxResult)
    if fiscal_year:
        q = q.filter(TaxResult.fiscal_year == fiscal_year)
    return q.order_by(TaxResult.modelo, TaxResult.casilla).all()


@router.get("/summary/{fiscal_year}", response_model=FiscalSummary)
def fiscal_summary(fiscal_year: int, db: Session = Depends(get_db)):
    """Get complete fiscal summary for a year."""
    # Dividends — use strftime for SQLite compatibility
    div_row = (
        db.query(
            func.coalesce(func.sum(Transaction.gross_amount), 0).label("gross"),
            func.coalesce(func.sum(Transaction.net_amount_eur), 0).label("net"),
            func.coalesce(func.sum(Transaction.withholding_tax), 0).label("whg"),
        )
        .filter(
            Transaction.type == TransactionType.DIVIDEND.value,
            func.strftime("%Y", Transaction.trade_date) == str(fiscal_year),
        )
        .one()
    )

    # Capital gains/losses — separate queries for clarity
    gains_total = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .filter(
            TaxLot.realized_pl_eur > 0,
            func.strftime("%Y", TaxLot.close_date) == str(fiscal_year),
        )
        .scalar()
    )

    losses_total = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .filter(
            TaxLot.realized_pl_eur < 0,
            func.strftime("%Y", TaxLot.close_date) == str(fiscal_year),
        )
        .scalar()
    )

    casillas = (
        db.query(TaxResult)
        .filter(TaxResult.fiscal_year == fiscal_year)
        .order_by(TaxResult.modelo, TaxResult.casilla)
        .all()
    )

    return FiscalSummary(
        fiscal_year=fiscal_year,
        total_dividends_gross=div_row.gross,
        total_dividends_net=div_row.net,
        total_withholdings=div_row.whg,
        total_gains=gains_total or Decimal("0"),
        total_losses=losses_total or Decimal("0"),
        net_capital_gains=(gains_total or Decimal("0")) + (losses_total or Decimal("0")),
        casillas=[
            CasillaOut(
                modelo=c.modelo,
                casilla=c.casilla,
                description=c.description,
                amount_eur=c.amount_eur,
                broker=c.broker,
            )
            for c in casillas
        ],
    )


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    """Quick dashboard stats."""
    total_tx = db.query(func.count(Transaction.id)).scalar() or 0

    div_total = (
        db.query(func.coalesce(func.sum(Transaction.gross_amount), 0))
        .filter(Transaction.type == TransactionType.DIVIDEND.value)
        .scalar()
    )

    gains = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .filter(TaxLot.realized_pl_eur > 0)
        .scalar()
    )
    losses = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .filter(TaxLot.realized_pl_eur < 0)
        .scalar()
    )

    accounts = db.query(func.count(Account.id)).scalar() or 0
    imports = db.query(func.count(ImportRecord.id)).scalar() or 0

    years = (
        db.query(TaxResult.fiscal_year).distinct().order_by(TaxResult.fiscal_year.desc()).all()
    )

    return DashboardStats(
        total_transactions=total_tx,
        total_dividends_eur=div_total or Decimal("0"),
        total_gains_eur=gains or Decimal("0"),
        total_losses_eur=losses or Decimal("0"),
        net_pl_eur=(gains or Decimal("0")) + (losses or Decimal("0")),
        accounts=accounts,
        imports=imports,
        fiscal_years=[y[0] for y in years],
    )
