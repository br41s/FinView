"""API endpoints for fiscal / tax data."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, func

from backend.api.schemas import (
    AggregatedCasillaOut,
    CasillaOut,
    CrossBrokerLotOut,
    DashboardStats,
    FIFOAdjustmentOut,
    FiscalSummary,
    OptionAssignmentOut,
)
from backend.database import DbSession
from backend.models import (
    Account,
    CrossBrokerLot,
    FIFOAdjustment,
    ImportRecord,
    OptionAssignmentRecord,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)

router = APIRouter(prefix="/fiscal", tags=["fiscal"])


@router.get("/casillas", response_model=list[AggregatedCasillaOut])
def list_casillas(db: DbSession, fiscal_year: int | None = None):
    """List tax casillas aggregated across all brokers."""
    q = db.query(TaxResult)
    if fiscal_year:
        q = q.filter(TaxResult.fiscal_year == fiscal_year)
    rows = q.order_by(TaxResult.modelo, TaxResult.casilla).all()

    # Aggregate by (modelo, casilla)
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    # Load FIFO adjustments for the fiscal year (if any)
    fifo_adj_by_casilla: dict[int, Decimal] = {}
    if fiscal_year:
        adjs = db.query(FIFOAdjustment).filter(
            FIFOAdjustment.fiscal_year == fiscal_year
        ).all()
        for adj in adjs:
            # Positive adjustment → more gains (332), negative → less gains / more losses (337)
            if adj.adjustment_eur > 0:
                fifo_adj_by_casilla[332] = fifo_adj_by_casilla.get(332, Decimal("0")) + adj.adjustment_eur
            elif adj.adjustment_eur < 0:
                fifo_adj_by_casilla[337] = fifo_adj_by_casilla.get(337, Decimal("0")) + adj.adjustment_eur

    result = []
    for (modelo, casilla), items in sorted(grouped.items()):
        total = sum(i.amount_eur for i in items)
        desc = items[0].description
        brokers = [
            {"broker": i.broker, "amount_eur": i.amount_eur}
            for i in items
        ]
        adj_val = fifo_adj_by_casilla.get(casilla)
        result.append(AggregatedCasillaOut(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            amount_eur=total,
            brokers=brokers,
            fifo_adjustment_eur=adj_val,
        ))
    return result


@router.get("/summary/{fiscal_year}", response_model=FiscalSummary)
def fiscal_summary(db: DbSession, fiscal_year: int):
    """Get complete fiscal summary for a year using TaxResult (broker truth)."""
    # Helper to sum a casilla across all brokers
    def _sum_casilla(casilla: int) -> Decimal:
        val = (
            db.query(func.coalesce(func.sum(TaxResult.amount_eur), 0))
            .filter(
                TaxResult.fiscal_year == fiscal_year,
                TaxResult.casilla == casilla,
            )
            .scalar()
        )
        return val or Decimal("0")

    # Dividends — from TaxResult (casilla 29) for gross, Transaction for net/withholdings
    div_gross = _sum_casilla(29)
    div_detail = (
        db.query(
            func.coalesce(func.sum(Transaction.net_amount_eur), 0).label("net"),
            func.coalesce(func.sum(Transaction.withholding_tax), 0).label("whg"),
        )
        .filter(
            Transaction.type == TransactionType.DIVIDEND.value,
            func.strftime("%Y", Transaction.trade_date) == str(fiscal_year),
        )
        .one()
    )

    gains_total = _sum_casilla(332)
    losses_total = _sum_casilla(337)

    # Aggregate casillas across brokers
    casilla_rows = (
        db.query(TaxResult)
        .filter(TaxResult.fiscal_year == fiscal_year)
        .order_by(TaxResult.modelo, TaxResult.casilla)
        .all()
    )
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in casilla_rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    aggregated_casillas = []
    for (modelo, casilla), items in sorted(grouped.items()):
        total = sum(i.amount_eur for i in items)
        brokers = [
            {"broker": i.broker, "amount_eur": i.amount_eur}
            for i in items
        ]
        aggregated_casillas.append(AggregatedCasillaOut(
            modelo=modelo,
            casilla=casilla,
            description=items[0].description,
            amount_eur=total,
            brokers=brokers,
        ))

    return FiscalSummary(
        fiscal_year=fiscal_year,
        total_dividends_gross=div_gross,
        total_dividends_net=div_detail.net,
        total_withholdings=div_detail.whg,
        total_gains=gains_total,
        total_losses=losses_total,
        net_capital_gains=gains_total + losses_total,
        casillas=aggregated_casillas,
    )


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(db: DbSession, fiscal_year: int | None = None):
    """Quick dashboard stats, optionally filtered by fiscal year.

    When a fiscal_year is selected, dividends/gains/losses come from
    TaxResult (broker PDF truth) instead of computed Transaction/TaxLot data.
    """
    tx_q = db.query(func.count(Transaction.id))
    if fiscal_year:
        tx_q = tx_q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))
    total_tx = tx_q.scalar() or 0

    if fiscal_year:
        # Use broker truth (TaxResult) for fiscal metrics
        def _sum_casilla(casilla: int) -> Decimal:
            val = (
                db.query(func.coalesce(func.sum(TaxResult.amount_eur), 0))
                .filter(
                    TaxResult.fiscal_year == fiscal_year,
                    TaxResult.casilla == casilla,
                )
                .scalar()
            )
            return val or Decimal("0")

        div_total = _sum_casilla(29)   # Dividendos brutos
        gains = _sum_casilla(332)      # Ganancias patrimoniales
        losses = _sum_casilla(337)     # Pérdidas patrimoniales
    else:
        # All-years view: compute from Transaction/TaxLot
        div_total = (
            db.query(func.coalesce(func.sum(Transaction.gross_amount), 0))
            .filter(Transaction.type == TransactionType.DIVIDEND.value)
            .scalar()
        ) or Decimal("0")

        gains = (
            db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
            .filter(TaxLot.realized_pl_eur > 0)
            .scalar()
        ) or Decimal("0")

        losses = (
            db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
            .filter(TaxLot.realized_pl_eur < 0)
            .scalar()
        ) or Decimal("0")

    accounts = db.query(func.count(Account.id)).scalar() or 0
    imports = db.query(func.count(ImportRecord.id)).scalar() or 0

    years = (
        db.query(ImportRecord.fiscal_year)
        .filter(ImportRecord.fiscal_year.isnot(None))
        .distinct()
        .order_by(ImportRecord.fiscal_year.desc())
        .all()
    )

    return DashboardStats(
        total_transactions=total_tx,
        total_dividends_eur=div_total,
        total_gains_eur=gains,
        total_losses_eur=losses,
        net_pl_eur=gains + losses,
        accounts=accounts,
        imports=imports,
        fiscal_years=[y[0] for y in years],
    )


@router.get("/cross-broker-lots", response_model=list[CrossBrokerLotOut])
def list_cross_broker_lots(db: DbSession, fiscal_year: int):
    """List cross-broker FIFO lots for a fiscal year."""
    lots = (
        db.query(CrossBrokerLot)
        .filter(CrossBrokerLot.fiscal_year == fiscal_year)
        .order_by(CrossBrokerLot.isin, CrossBrokerLot.id)
        .all()
    )
    return lots


@router.get("/fifo-adjustments", response_model=list[FIFOAdjustmentOut])
def list_fifo_adjustments(db: DbSession, fiscal_year: int):
    """List FIFO adjustments (cross-broker vs broker) for a fiscal year."""
    adjs = (
        db.query(FIFOAdjustment)
        .filter(FIFOAdjustment.fiscal_year == fiscal_year)
        .order_by(FIFOAdjustment.isin)
        .all()
    )
    return adjs


@router.get("/option-assignments", response_model=list[OptionAssignmentOut])
def list_option_assignments(db: DbSession, fiscal_year: int):
    """List detected option assignments for a fiscal year.

    Assignments are informational — IBKR's Realized P/L already embeds
    option premiums in the stock cost basis per Spanish IRPF rules.
    """
    records = (
        db.query(OptionAssignmentRecord)
        .filter(OptionAssignmentRecord.fiscal_year == fiscal_year)
        .order_by(OptionAssignmentRecord.assignment_date)
        .all()
    )
    return records
