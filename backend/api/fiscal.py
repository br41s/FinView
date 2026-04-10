"""API endpoints for fiscal / tax data."""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func

from backend.api.schemas import (
    AggregatedCasillaOut,
    CasillaOut,
    CrossBrokerLotOut,
    CrossValidationResult,
    CrossValidationRow,
    DashboardStats,
    FIFOAdjustmentOut,
    FiscalSummary,
    OptionAssignmentOut,
    YearlyComparisonResult,
    YearlyMetrics,
)
from backend.database import DbSession
from backend.models import (
    Account,
    Broker,
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

        # TR validation: find TR broker's reference amount for this casilla
        tr_ref = None
        validation = None
        for i in items:
            if i.broker == Broker.TR and i.tr_reference_amount is not None:
                tr_ref = i.tr_reference_amount
                # Compare aggregated total against TR reference
                validation = "match" if abs(total - tr_ref) < Decimal("0.02") else "mismatch"
                break

        result.append(AggregatedCasillaOut(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            amount_eur=total,
            brokers=brokers,
            fifo_adjustment_eur=adj_val,
            tr_reference_amount=tr_ref,
            validation_status=validation,
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


@router.get("/export/{fiscal_year}")
def export_fiscal_data(
    db: DbSession,
    fiscal_year: int,
    format: str = "json",
):
    """Export fiscal data for a year. Supports format=json or format=csv."""
    casillas = list_casillas(db, fiscal_year=fiscal_year)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "modelo", "casilla", "descripcion", "importe_eur",
            "brokers", "ajuste_fifo_eur", "referencia_tr_eur", "validacion",
        ])
        for c in casillas:
            brokers_str = "; ".join(
                f"{b.broker}: {b.amount_eur}" for b in c.brokers
            )
            writer.writerow([
                c.modelo,
                c.casilla,
                c.description,
                str(c.amount_eur),
                brokers_str,
                str(c.fifo_adjustment_eur) if c.fifo_adjustment_eur else "",
                str(c.tr_reference_amount) if c.tr_reference_amount else "",
                c.validation_status or "",
            ])
        output.seek(0)
        filename = f"finview_casillas_{fiscal_year}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # Default: JSON
    return {
        "fiscal_year": fiscal_year,
        "casillas": [c.model_dump() for c in casillas],
    }


@router.get("/cross-validation/{fiscal_year}", response_model=CrossValidationResult)
def cross_validation(db: DbSession, fiscal_year: int):
    """Compare FinView-calculated casillas against TR reference values."""
    rows = (
        db.query(TaxResult)
        .filter(TaxResult.fiscal_year == fiscal_year)
        .order_by(TaxResult.modelo, TaxResult.casilla)
        .all()
    )

    # Group by (modelo, casilla)
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    # Load FIFO adjustments
    fifo_adj: dict[int, Decimal] = {}
    adjs = db.query(FIFOAdjustment).filter(
        FIFOAdjustment.fiscal_year == fiscal_year,
    ).all()
    for adj in adjs:
        target = 332 if adj.adjustment_eur > 0 else 337
        fifo_adj[target] = fifo_adj.get(target, Decimal("0")) + adj.adjustment_eur

    result_rows: list[CrossValidationRow] = []
    match_count = mismatch_count = no_ref_count = 0

    for (modelo, casilla), items in sorted(grouped.items()):
        total = sum(i.amount_eur for i in items)
        adj_val = fifo_adj.get(casilla, Decimal("0"))
        adjusted_total = total + adj_val
        desc = items[0].description
        brokers = [{"broker": i.broker, "amount_eur": i.amount_eur} for i in items]

        # Find TR reference and TR's own amount
        tr_ref = None
        tr_own_amount = None
        for i in items:
            if i.broker == Broker.TR:
                tr_own_amount = i.amount_eur
                if i.tr_reference_amount is not None:
                    tr_ref = i.tr_reference_amount

        if tr_ref is not None:
            # For multi-broker casillas (29, 332, 337), compare TR amount vs TR reference
            # For TR-only casillas (27, 714), compare total vs TR reference
            is_multi_broker = len(items) > 1
            compare_amount = tr_own_amount if is_multi_broker and tr_own_amount is not None else adjusted_total
            diff = compare_amount - tr_ref
            status = "match" if abs(diff) < Decimal("1.00") else "mismatch"
            if status == "match":
                match_count += 1
            else:
                mismatch_count += 1
        else:
            diff = None
            compare_amount = adjusted_total
            status = "no_tr_data"
            no_ref_count += 1

        result_rows.append(CrossValidationRow(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            finview_amount=adjusted_total,
            compare_amount=compare_amount,
            tr_amount=tr_ref,
            difference=diff,
            status=status,
            is_multi_broker=len(items) > 1,
            brokers=brokers,
        ))

    return CrossValidationResult(
        fiscal_year=fiscal_year,
        rows=result_rows,
        total_match=match_count,
        total_mismatch=mismatch_count,
        total_no_ref=no_ref_count,
    )


@router.get("/yearly-comparison", response_model=YearlyComparisonResult)
def yearly_comparison(db: DbSession):
    """Get fiscal metrics aggregated per year for multi-year comparison."""
    # Get all distinct fiscal years
    years = (
        db.query(TaxResult.fiscal_year)
        .distinct()
        .order_by(TaxResult.fiscal_year)
        .all()
    )

    metrics: list[YearlyMetrics] = []
    for (year,) in years:
        def _sum_casilla(c: int) -> Decimal:
            val = (
                db.query(func.coalesce(func.sum(TaxResult.amount_eur), 0))
                .filter(TaxResult.fiscal_year == year, TaxResult.casilla == c)
                .scalar()
            )
            return val or Decimal("0")

        dividends = _sum_casilla(29)
        gains = _sum_casilla(332)
        losses = _sum_casilla(337)

        # Withholdings from transactions
        whg = (
            db.query(func.coalesce(func.sum(Transaction.withholding_tax), 0))
            .filter(
                Transaction.type == TransactionType.DIVIDEND.value,
                func.strftime("%Y", Transaction.trade_date) == str(year),
            )
            .scalar()
        ) or Decimal("0")

        # Number of distinct brokers with data this year
        broker_count = (
            db.query(func.count(func.distinct(TaxResult.broker)))
            .filter(TaxResult.fiscal_year == year)
            .scalar()
        ) or 0

        # Number of distinct ISINs with dividends this year
        pos_count = (
            db.query(func.count(func.distinct(Transaction.isin)))
            .filter(
                Transaction.type == TransactionType.DIVIDEND.value,
                func.strftime("%Y", Transaction.trade_date) == str(year),
            )
            .scalar()
        ) or 0

        metrics.append(YearlyMetrics(
            fiscal_year=year,
            dividends_gross=dividends,
            gains=gains,
            losses=losses,
            net_capital=gains + losses,
            withholdings=whg,
            brokers=broker_count,
            positions=pos_count,
        ))

    return YearlyComparisonResult(years=metrics)
