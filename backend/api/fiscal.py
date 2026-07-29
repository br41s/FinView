"""API endpoints for fiscal / tax data."""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import aliased

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    AggregatedCasillaOut,
    CrossBrokerLotOut,
    CrossValidationResult,
    CrossValidationRow,
    DashboardStats,
    FIFOAdjustmentOut,
    FiscalProfileIn,
    FiscalProfileOut,
    FiscalSummary,
    ManualSavingsIncomeIn,
    ManualSavingsIncomeOut,
    OptionAssignmentOut,
    SavingsEstimateOut,
    YearlyComparisonResult,
    YearlyMetrics,
)
from backend.database import DbSession
from backend.services.sql_compat import year_range, year_str
from backend.services.tax_estimator import (
    SavingsInputs,
    TaxpayerProfile,
    estimate_savings,
)
from backend.services.fifo_engine import FIFO_CALCULATION_VERSION
from backend.models import (
    Account,
    Broker,
    CrossBrokerLot,
    FIFOAdjustment,
    FiscalProfile,
    ImportRecord,
    ManualSavingsIncome,
    OptionAssignmentRecord,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)

router = APIRouter(prefix="/fiscal", tags=["fiscal"])


def _fifo_casilla_deltas(adjustments: list[FIFOAdjustment]) -> dict[int, Decimal]:
    """Split FIFO corrections between gains (332) and losses (337).

    Legacy rows are deliberately ignored: they were calculated before the
    chronological FIFO fix and do not contain a reliable per-box breakdown.
    """
    deltas = {332: Decimal("0"), 337: Decimal("0")}
    for adj in adjustments:
        if adj.calculation_version != FIFO_CALCULATION_VERSION:
            continue
        deltas[332] += (
            (adj.fifo_gains_eur or Decimal("0"))
            - (adj.broker_gains_eur or Decimal("0"))
        )
        deltas[337] += (
            (adj.fifo_losses_eur or Decimal("0"))
            - (adj.broker_losses_eur or Decimal("0"))
        )

    return {casilla: amount for casilla, amount in deltas.items() if amount}


def _fifo_adjustments_by_casilla(
    db: DbSession, user_id: int, fiscal_year: int
) -> dict[int, Decimal]:
    rows = (
        db.query(FIFOAdjustment)
        .filter(
            FIFOAdjustment.user_id == user_id,
            FIFOAdjustment.fiscal_year == fiscal_year,
        )
        .all()
    )
    return _fifo_casilla_deltas(rows)


@router.get("/casillas", response_model=list[AggregatedCasillaOut])
def list_casillas(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """List tax casillas aggregated across all brokers."""
    q = db.query(TaxResult).filter(TaxResult.user_id == user.id)
    if fiscal_year:
        q = q.filter(TaxResult.fiscal_year == fiscal_year)
    rows = q.order_by(TaxResult.modelo, TaxResult.casilla).all()

    # Aggregate by (modelo, casilla)
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    # Load FIFO adjustments for the fiscal year (if any)
    fifo_adj_by_casilla = (
        _fifo_adjustments_by_casilla(db, user.id, fiscal_year)
        if fiscal_year
        else {}
    )

    # Manual savings entries (per-year) mapped to their casillas, folded in as a
    # "MANUAL" source so the boxes match Mi declaración. Only when a year is set.
    man_cas: dict[int, Decimal] = {}
    if fiscal_year:
        man_cas, _ = _manual_casillas(db, user.id, fiscal_year)

    result = []
    for (modelo, casilla), items in sorted(grouped.items()):
        broker_total = sum(i.amount_eur for i in items)
        manual_amt = man_cas.get(casilla, Decimal("0")) if modelo == 100 else Decimal("0")
        adj_val = (
            fifo_adj_by_casilla.get(casilla, Decimal("0"))
            if modelo == 100
            else Decimal("0")
        )
        total = broker_total + manual_amt + adj_val
        desc = items[0].description
        brokers = [
            {"broker": i.broker, "amount_eur": i.amount_eur}
            for i in items
        ]
        if manual_amt:
            brokers.append({"broker": "MANUAL", "amount_eur": manual_amt})
        # TR validation: sum both TR amounts and references. Migration years
        # can have multiple TR fragments; other brokers/manual/FIFO are outside
        # this broker-specific check.
        tr_items = [item for item in items if item.broker == Broker.TR]
        tr_refs = [
            item.tr_reference_amount
            for item in tr_items
            if item.tr_reference_amount is not None
        ]
        tr_ref = None
        validation = None
        if tr_refs:
            tr_ref = sum(tr_refs)
            tr_amount = sum(item.amount_eur for item in tr_items)
            validation = "match" if abs(tr_amount - tr_ref) < Decimal("0.02") else "mismatch"

        result.append(AggregatedCasillaOut(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            amount_eur=total,
            brokers=brokers,
            fifo_adjustment_eur=adj_val or None,
            tr_reference_amount=tr_ref,
            validation_status=validation,
        ))

    # Casillas that exist only from manual or FIFO data (no broker rows this year).
    for casilla in sorted(set(man_cas) | set(fifo_adj_by_casilla)):
        amt = man_cas.get(casilla, Decimal("0"))
        adj_val = fifo_adj_by_casilla.get(casilla, Decimal("0"))
        if (100, casilla) in grouped:
            continue
        brokers = []
        if amt:
            brokers.append({"broker": "MANUAL", "amount_eur": amt})
        result.append(AggregatedCasillaOut(
            modelo=100,
            casilla=casilla,
            description=_MANUAL_CASILLA_DESC.get(casilla, ""),
            amount_eur=amt + adj_val,
            brokers=brokers,
            fifo_adjustment_eur=adj_val or None,
        ))

    result.sort(key=lambda c: (c.modelo, c.casilla))
    return result


@router.get("/summary/{fiscal_year}", response_model=FiscalSummary)
def fiscal_summary(db: DbSession, user: CurrentUser, fiscal_year: int):
    """Get complete fiscal summary for a year using TaxResult (broker truth)."""
    # Helper to sum a casilla across all brokers
    def _sum_casilla(casilla: int) -> Decimal:
        val = (
            db.query(func.coalesce(func.sum(TaxResult.amount_eur), 0))
            .filter(
                TaxResult.user_id == user.id,
                TaxResult.fiscal_year == fiscal_year,
                TaxResult.casilla == casilla,
            )
            .scalar()
        )
        return val or Decimal("0")

    # Manual savings entries mapped to casillas — folded into every total below
    # so the summary matches Casillas fiscales and Mi declaración.
    man_cas, man_whg = _manual_casillas(db, user.id, fiscal_year)

    # Dividends — casilla 29 (broker + manual) for gross; Transaction for net/whg.
    div_gross = _sum_casilla(29) + man_cas.get(29, Decimal("0"))
    div_detail = (
        db.query(
            func.coalesce(func.sum(Transaction.net_amount_eur), 0).label("net"),
            func.coalesce(func.sum(Transaction.withholding_tax), 0).label("whg"),
        )
        .join(Account)
        .filter(
            Account.user_id == user.id,
            Transaction.type == TransactionType.DIVIDEND.value,
            year_range(Transaction.trade_date, fiscal_year),
        )
        .one()
    )
    # Manual dividend net = manual dividend gross − its withholding.
    manual_div_net = man_cas.get(29, Decimal("0")) - man_whg.get(29, Decimal("0"))
    manual_whg_total = sum(man_whg.values(), Decimal("0"))

    fifo_cas = _fifo_adjustments_by_casilla(db, user.id, fiscal_year)
    gains_total = (
        _sum_casilla(332)
        + man_cas.get(332, Decimal("0"))
        + fifo_cas.get(332, Decimal("0"))
    )
    losses_total = (
        _sum_casilla(337)
        + man_cas.get(337, Decimal("0"))
        + fifo_cas.get(337, Decimal("0"))
    )

    # Reuse list_casillas so the summary's casillas are byte-identical to the
    # Casillas fiscales view (broker + manual, same sources, same boxes).
    aggregated_casillas = list_casillas(db, user=user, fiscal_year=fiscal_year)

    return FiscalSummary(
        fiscal_year=fiscal_year,
        total_dividends_gross=div_gross,
        total_dividends_net=div_detail.net + manual_div_net,
        total_withholdings=div_detail.whg + manual_whg_total,
        total_gains=gains_total,
        total_losses=losses_total,
        net_capital_gains=gains_total + losses_total,
        casillas=aggregated_casillas,
    )


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """Quick dashboard stats, optionally filtered by fiscal year.

    Dividendos, ganancias y pérdidas se calculan siempre desde
    Transaction/TaxLot para que los totales del dashboard cuadren con
    los desgloses (por país, por compañía, etc.), que usan la misma
    fuente.
    """
    def _with_year(q):
        return q.filter(year_range(Transaction.trade_date, fiscal_year)) if fiscal_year else q

    total_tx = _with_year(
        db.query(func.count(Transaction.id)).join(Account).filter(Account.user_id == user.id)
    ).scalar() or 0

    div_total = _with_year(
        db.query(func.coalesce(func.sum(Transaction.gross_amount), 0))
        .join(Account)
        .filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)
    ).scalar() or Decimal("0")

    def _sum_realized_pl(positive: bool) -> Decimal:
        cond = TaxLot.realized_pl_eur > 0 if positive else TaxLot.realized_pl_eur < 0
        q = (
            db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
            .join(Transaction, TaxLot.sell_tx_id == Transaction.id)
            .join(Account)
            .filter(Account.user_id == user.id, cond)
        )
        return _with_year(q).scalar() or Decimal("0")

    gains = _sum_realized_pl(positive=True)
    losses = _sum_realized_pl(positive=False)
    if fiscal_year:
        fifo_cas = _fifo_adjustments_by_casilla(db, user.id, fiscal_year)
    else:
        fifo_cas = _fifo_casilla_deltas(
            db.query(FIFOAdjustment)
            .filter(FIFOAdjustment.user_id == user.id)
            .all()
        )
    gains += fifo_cas.get(332, Decimal("0"))
    losses += fifo_cas.get(337, Decimal("0"))

    accounts = db.query(func.count(Account.id)).filter(Account.user_id == user.id).scalar() or 0
    imports = (
        db.query(func.count(ImportRecord.id))
        .join(Account)
        .filter(Account.user_id == user.id)
        .scalar()
    ) or 0

    years = (
        db.query(ImportRecord.fiscal_year)
        .join(Account)
        .filter(Account.user_id == user.id, ImportRecord.fiscal_year.isnot(None))
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
def list_cross_broker_lots(db: DbSession, user: CurrentUser, fiscal_year: int):
    """List cross-broker FIFO lots for a fiscal year."""
    buy_tx = aliased(Transaction)
    sell_tx = aliased(Transaction)
    buy_account = aliased(Account)
    sell_account = aliased(Account)
    lots = (
        db.query(CrossBrokerLot)
        .join(buy_tx, CrossBrokerLot.buy_tx_id == buy_tx.id)
        .join(buy_account, buy_tx.account_id == buy_account.id)
        .join(sell_tx, CrossBrokerLot.sell_tx_id == sell_tx.id)
        .join(sell_account, sell_tx.account_id == sell_account.id)
        .filter(
            buy_account.user_id == user.id,
            sell_account.user_id == user.id,
            CrossBrokerLot.fiscal_year == fiscal_year,
            CrossBrokerLot.calculation_version == FIFO_CALCULATION_VERSION,
        )
        .order_by(CrossBrokerLot.isin, CrossBrokerLot.id)
        .all()
    )
    return lots


@router.get("/fifo-adjustments", response_model=list[FIFOAdjustmentOut])
def list_fifo_adjustments(db: DbSession, user: CurrentUser, fiscal_year: int):
    """List FIFO adjustments (cross-broker vs broker) for a fiscal year."""
    adjs = (
        db.query(FIFOAdjustment)
        .filter(
            FIFOAdjustment.user_id == user.id,
            FIFOAdjustment.fiscal_year == fiscal_year,
            FIFOAdjustment.calculation_version == FIFO_CALCULATION_VERSION,
        )
        .order_by(FIFOAdjustment.isin)
        .all()
    )
    return adjs


@router.get("/option-assignments", response_model=list[OptionAssignmentOut])
def list_option_assignments(db: DbSession, user: CurrentUser, fiscal_year: int):
    """List detected option assignments for a fiscal year.

    Assignments are informational — IBKR's Realized P/L already embeds
    option premiums in the stock cost basis per Spanish IRPF rules.
    """
    records = (
        db.query(OptionAssignmentRecord)
        .join(ImportRecord, OptionAssignmentRecord.import_id == ImportRecord.id)
        .join(Account, ImportRecord.account_id == Account.id)
        .filter(Account.user_id == user.id, OptionAssignmentRecord.fiscal_year == fiscal_year)
        .order_by(OptionAssignmentRecord.assignment_date)
        .all()
    )
    return records


@router.get("/export/{fiscal_year}")
def export_fiscal_data(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int,
    format: str = "json",
):
    """Export fiscal data for a year. Supports format=json or format=csv."""
    casillas = list_casillas(db, user=user, fiscal_year=fiscal_year)

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


@router.get("/fx-rate")
def fx_rate(user: CurrentUser, currency: str, on: str):
    """Official ECB reference rate for a currency on a date (YYYY-MM-DD).

    Returns units of `currency` per 1 EUR, with ±7-day fallback for
    weekends/holidays. 404 if the date/currency isn't cached.
    """
    from backend.services.exchange_rates import get_rate

    rate = get_rate(currency.upper(), on)
    if rate is None:
        raise HTTPException(404, f"No cached ECB rate for {currency} on {on}")
    return {"currency": currency.upper(), "date": on, "rate": float(rate), "source": "ECB"}


@router.get("/cross-validation/{fiscal_year}", response_model=CrossValidationResult)
def cross_validation(db: DbSession, user: CurrentUser, fiscal_year: int):
    """Compare FinView-calculated casillas against TR reference values."""
    rows = (
        db.query(TaxResult)
        .filter(TaxResult.user_id == user.id, TaxResult.fiscal_year == fiscal_year)
        .order_by(TaxResult.modelo, TaxResult.casilla)
        .all()
    )

    # Group by (modelo, casilla)
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    fifo_adj = _fifo_adjustments_by_casilla(db, user.id, fiscal_year)

    result_rows: list[CrossValidationRow] = []
    match_count = mismatch_count = no_ref_count = 0

    keys = set(grouped)
    keys.update((100, casilla) for casilla in fifo_adj)
    for modelo, casilla in sorted(keys):
        items = grouped.get((modelo, casilla), [])
        total = sum(i.amount_eur for i in items)
        adj_val = fifo_adj.get(casilla, Decimal("0"))
        adjusted_total = total + adj_val
        desc = items[0].description if items else _MANUAL_CASILLA_DESC.get(casilla, "")
        brokers = [{"broker": i.broker, "amount_eur": i.amount_eur} for i in items]

        # TR references validate broker-reported amounts, not FIFO/manual
        # corrections. Sum migration fragments instead of keeping the last one.
        tr_refs = [
            item.tr_reference_amount
            for item in items
            if item.broker == Broker.TR and item.tr_reference_amount is not None
        ]
        tr_ref = sum(tr_refs, Decimal("0")) if tr_refs else None
        tr_amount = sum(
            (item.amount_eur for item in items if item.broker == Broker.TR),
            Decimal("0"),
        )
        broker_count = len({item.broker for item in items})

        if tr_ref is not None:
            compare_amount = tr_amount
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
            is_multi_broker=broker_count > 1 or bool(adj_val),
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
def yearly_comparison(db: DbSession, user: CurrentUser):
    """Get fiscal metrics aggregated per year for multi-year comparison."""
    # All TaxResult aggregates per year in one query (was 4 queries × N years)
    tax_rows = (
        db.query(
            TaxResult.fiscal_year,
            func.coalesce(
                func.sum(case((TaxResult.casilla == 29, TaxResult.amount_eur), else_=Decimal("0"))),
                Decimal("0"),
            ).label("dividends"),
            func.coalesce(
                func.sum(case((TaxResult.casilla == 332, TaxResult.amount_eur), else_=Decimal("0"))),
                Decimal("0"),
            ).label("gains"),
            func.coalesce(
                func.sum(case((TaxResult.casilla == 337, TaxResult.amount_eur), else_=Decimal("0"))),
                Decimal("0"),
            ).label("losses"),
            func.count(func.distinct(TaxResult.broker)).label("broker_count"),
        )
        .filter(TaxResult.user_id == user.id)
        .group_by(TaxResult.fiscal_year)
        .order_by(TaxResult.fiscal_year)
        .all()
    )

    # Withholdings and distinct-ISIN count per year in one query (was 2 queries × N years)
    tx_rows = (
        db.query(
            year_str(Transaction.trade_date).label("yr"),
            func.coalesce(func.sum(Transaction.withholding_tax), Decimal("0")).label("whg"),
            func.count(func.distinct(Transaction.isin)).label("pos_count"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user.id,
            Transaction.type == TransactionType.DIVIDEND.value,
        )
        .group_by(year_str(Transaction.trade_date))
        .all()
    )
    tx_map = {int(row.yr): (row.whg or Decimal("0"), row.pos_count) for row in tx_rows}

    fifo_rows = (
        db.query(FIFOAdjustment)
        .filter(
            FIFOAdjustment.user_id == user.id,
            FIFOAdjustment.calculation_version == FIFO_CALCULATION_VERSION,
        )
        .all()
    )
    fifo_by_year: dict[int, list[FIFOAdjustment]] = {}
    for adjustment in fifo_rows:
        fifo_by_year.setdefault(adjustment.fiscal_year, []).append(adjustment)
    fifo_map = {
        year: _fifo_casilla_deltas(adjustments)
        for year, adjustments in fifo_by_year.items()
    }

    tax_map = {row.fiscal_year: row for row in tax_rows}
    metrics = []
    for year in sorted(set(tax_map) | set(fifo_map)):
        row = tax_map.get(year)
        fifo = fifo_map.get(year, {})
        gains = (row.gains if row else Decimal("0")) + fifo.get(332, Decimal("0"))
        losses = (row.losses if row else Decimal("0")) + fifo.get(337, Decimal("0"))
        metrics.append(YearlyMetrics(
            fiscal_year=year,
            dividends_gross=row.dividends if row else Decimal("0"),
            gains=gains,
            losses=losses,
            net_capital=gains + losses,
            withholdings=tx_map.get(year, (Decimal("0"), 0))[0],
            brokers=row.broker_count if row else 0,
            positions=tx_map.get(year, (Decimal("0"), 0))[1],
        ))
    return YearlyComparisonResult(years=metrics)


# ── Fiscal onboarding: savings-base estimate (v1 individual) ─────────────────
_SAVINGS_CASILLAS = (27, 29, 332, 337)


# Manual savings entries map to real Modelo 100 boxes so every casilla-level
# view (Casillas fiscales, IRPF summary, Mi declaración) agrees. Legacy "RCM"
# rows (before the interest/dividend split) fall back to dividends (c29).
_MANUAL_CATEGORY_CASILLA = {
    "INTEREST": 27,
    "DIVIDEND": 29,
    "RCM": 29,       # legacy generic RCM
    "GAIN": 332,
    "LOSS": 337,
}
_MANUAL_CATEGORIES = ("INTEREST", "DIVIDEND", "GAIN", "LOSS")
_MANUAL_CASILLA_DESC = {
    27: "Intereses y otros rendimientos del capital mobiliario",
    29: "Dividendos y demás rendimientos",
    332: "Ganancias patrimoniales",
    337: "Pérdidas patrimoniales",
}


def _manual_casillas(db, user_id: int, year: int) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """Manual savings entries mapped to Modelo 100 casillas.

    Returns (amount_by_casilla {LOSS negative}, withholding_by_casilla). Single
    source used by list_casillas, fiscal_summary and the estimate so the
    manually-entered income shows up identically everywhere.
    """
    rows = (
        db.query(ManualSavingsIncome)
        .filter(
            ManualSavingsIncome.user_id == user_id,
            ManualSavingsIncome.fiscal_year == year,
        )
        .all()
    )
    cas: dict[int, Decimal] = {}
    whg: dict[int, Decimal] = {}
    for m in rows:
        box = _MANUAL_CATEGORY_CASILLA.get(m.category)
        if box is None:
            continue
        amt = -m.amount_eur if m.category == "LOSS" else m.amount_eur
        cas[box] = cas.get(box, Decimal("0")) + amt
        whg[box] = whg.get(box, Decimal("0")) + (m.withholding_eur or Decimal("0"))
    return cas, whg


def _aggregate_savings_inputs(db, user_id: int, year: int) -> tuple[SavingsInputs, dict]:
    """Sum savings components from broker casillas + manual entries + withholdings."""
    rows = (
        db.query(TaxResult.casilla, func.sum(TaxResult.amount_eur))
        .filter(
            TaxResult.user_id == user_id,
            TaxResult.fiscal_year == year,
            TaxResult.modelo == 100,
            TaxResult.casilla.in_(_SAVINGS_CASILLAS),
        )
        .group_by(TaxResult.casilla)
        .all()
    )
    cas = {c: (a or Decimal("0")) for c, a in rows}

    # Fold in manual entries mapped to the same casillas (shared helper).
    man_cas, man_whg = _manual_casillas(db, user_id, year)
    for box, amt in man_cas.items():
        cas[box] = cas.get(box, Decimal("0")) + amt
    for box, amt in _fifo_adjustments_by_casilla(db, user_id, year).items():
        cas[box] = cas.get(box, Decimal("0")) + amt
    man_whg_total = sum(man_whg.values(), Decimal("0"))

    rcm = cas.get(27, Decimal("0")) + cas.get(29, Decimal("0"))
    gains = cas.get(332, Decimal("0"))
    losses = cas.get(337, Decimal("0"))  # stored ≤ 0

    # Withholdings on savings income: broker transactions + manual entries.
    whg = (
        db.query(func.coalesce(func.sum(Transaction.withholding_tax), Decimal("0")))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.type.in_(
                [TransactionType.DIVIDEND.value, TransactionType.INTEREST.value]
            ),
            year_range(Transaction.trade_date, year),
        )
        .scalar()
    ) or Decimal("0")
    whg += man_whg_total

    casillas = {"rcm": rcm, "gains": gains, "losses": losses, "withholdings": whg}
    return SavingsInputs(rcm_net=rcm, gains=gains, losses=losses, withholdings=whg), casillas


@router.get("/profile/{fiscal_year}", response_model=FiscalProfileOut)
def get_fiscal_profile(db: DbSession, user: CurrentUser, fiscal_year: int):
    """Taxpayer profile for the year; returns defaults if none saved yet."""
    p = (
        db.query(FiscalProfile)
        .filter(FiscalProfile.user_id == user.id, FiscalProfile.fiscal_year == fiscal_year)
        .first()
    )
    if p is None:
        return FiscalProfileOut(fiscal_year=fiscal_year)
    return FiscalProfileOut(
        fiscal_year=p.fiscal_year,
        age=p.age,
        disability=p.disability,
        descendants=p.descendants,
        general_base=p.general_base,
        prior_rcm_loss=p.prior_rcm_loss,
        prior_gp_loss=p.prior_gp_loss,
        updated_at=p.updated_at,
    )


@router.put("/profile/{fiscal_year}", response_model=FiscalProfileOut)
def upsert_fiscal_profile(
    db: DbSession, user: CurrentUser, fiscal_year: int, body: FiscalProfileIn
):
    """Create or update the taxpayer profile for the year."""
    if body.disability not in (None, "general", "severe"):
        raise HTTPException(422, "disability must be null, 'general' or 'severe'")
    if body.prior_rcm_loss < 0 or body.prior_gp_loss < 0:
        raise HTTPException(422, "prior losses must be ≥ 0 (enter as positive magnitudes)")
    p = (
        db.query(FiscalProfile)
        .filter(FiscalProfile.user_id == user.id, FiscalProfile.fiscal_year == fiscal_year)
        .first()
    )
    if p is None:
        p = FiscalProfile(user_id=user.id, fiscal_year=fiscal_year)
        db.add(p)
    p.age = body.age
    p.disability = body.disability
    p.descendants = max(body.descendants, 0)
    p.general_base = body.general_base
    p.prior_rcm_loss = body.prior_rcm_loss
    p.prior_gp_loss = body.prior_gp_loss
    db.commit()
    db.refresh(p)
    return FiscalProfileOut(
        fiscal_year=p.fiscal_year,
        age=p.age,
        disability=p.disability,
        descendants=p.descendants,
        general_base=p.general_base,
        prior_rcm_loss=p.prior_rcm_loss,
        prior_gp_loss=p.prior_gp_loss,
        updated_at=p.updated_at,
    )


@router.get("/manual-income/{fiscal_year}", response_model=list[ManualSavingsIncomeOut])
def list_manual_income(db: DbSession, user: CurrentUser, fiscal_year: int):
    return (
        db.query(ManualSavingsIncome)
        .filter(
            ManualSavingsIncome.user_id == user.id,
            ManualSavingsIncome.fiscal_year == fiscal_year,
        )
        .order_by(ManualSavingsIncome.id)
        .all()
    )


@router.post("/manual-income", response_model=ManualSavingsIncomeOut)
def create_manual_income(db: DbSession, user: CurrentUser, body: ManualSavingsIncomeIn):
    if body.category not in _MANUAL_CATEGORIES:
        raise HTTPException(
            422, "category must be 'INTEREST', 'DIVIDEND', 'GAIN' or 'LOSS'"
        )
    if body.amount_eur < 0 or body.withholding_eur < 0:
        raise HTTPException(422, "amount_eur and withholding_eur must be ≥ 0")
    m = ManualSavingsIncome(
        user_id=user.id,
        fiscal_year=body.fiscal_year,
        category=body.category,
        label=body.label,
        amount_eur=body.amount_eur,
        withholding_eur=body.withholding_eur,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/manual-income/{entry_id}")
def delete_manual_income(db: DbSession, user: CurrentUser, entry_id: int):
    m = (
        db.query(ManualSavingsIncome)
        .filter(ManualSavingsIncome.id == entry_id, ManualSavingsIncome.user_id == user.id)
        .first()
    )
    if m is None:
        raise HTTPException(404, "Manual income entry not found")
    db.delete(m)
    db.commit()
    return {"status": "deleted", "id": entry_id}


@router.get("/estimate/{fiscal_year}", response_model=SavingsEstimateOut)
def savings_estimate(db: DbSession, user: CurrentUser, fiscal_year: int):
    """Estimated savings-base IRPF result (casillas + final number)."""
    inputs, casillas = _aggregate_savings_inputs(db, user.id, fiscal_year)

    p = (
        db.query(FiscalProfile)
        .filter(FiscalProfile.user_id == user.id, FiscalProfile.fiscal_year == fiscal_year)
        .first()
    )
    profile = TaxpayerProfile(
        age=p.age if p else None,
        disability=p.disability if p else None,
        descendants=p.descendants if p else 0,
        general_base=p.general_base if p else Decimal("0"),
    )
    if p:
        inputs.prior_rcm_loss = p.prior_rcm_loss or Decimal("0")
        inputs.prior_gp_loss = p.prior_gp_loss or Decimal("0")

    est = estimate_savings(inputs, profile, fiscal_year)
    return SavingsEstimateOut(
        fiscal_year=fiscal_year,
        rates_year_used=est.rates_year_used,
        rcm_net=est.rcm_net,
        gp_net=est.gp_net,
        savings_base=est.savings_base,
        rcm_carryforward=est.rcm_carryforward,
        gp_carryforward=est.gp_carryforward,
        prior_rcm_loss_applied=est.prior_rcm_loss_applied,
        prior_gp_loss_applied=est.prior_gp_loss_applied,
        personal_minimum=est.personal_minimum,
        minimum_on_savings=est.minimum_on_savings,
        gross_quota=est.gross_quota,
        quota=est.quota,
        withholdings=est.withholdings,
        result=est.result,
        brackets=est.breakdown,
        casillas=casillas,
    )


def _savings_estimate_csv(est: SavingsEstimateOut) -> str:
    """Render a savings-base estimate as a CSV string (summary + per-bracket)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["FinView — Estimación base del ahorro", f"Ejercicio {est.fiscal_year}"])
    writer.writerow([])
    writer.writerow(["concepto", "importe_eur"])
    for label, val in [
        ("RCM neto (intereses + dividendos)", est.rcm_net),
        ("Ganancias/pérdidas netas", est.gp_net),
        ("Pérdidas RCM años anteriores aplicadas", est.prior_rcm_loss_applied),
        ("Pérdidas patrimoniales años anteriores aplicadas", est.prior_gp_loss_applied),
        ("Base imponible del ahorro", est.savings_base),
        ("Mínimo personal y familiar", est.personal_minimum),
        ("Mínimo aplicado al ahorro", est.minimum_on_savings),
        ("Cuota íntegra del ahorro", est.gross_quota),
        ("Cuota tras mínimo", est.quota),
        ("Retenciones soportadas", est.withholdings),
        ("Resultado (>0 a ingresar · <0 a devolver)", est.result),
    ]:
        writer.writerow([label, str(val)])

    writer.writerow([])
    writer.writerow(["tramo_desde", "tramo_hasta", "tipo", "cuota_tramo_eur"])
    for b in est.brackets:
        writer.writerow([str(b["from"]), str(b["to"]), str(b["rate"]), str(b["tax"])])

    if est.rates_year_used != est.fiscal_year:
        writer.writerow([])
        writer.writerow([
            f"Aviso: sin tablas fiscales para {est.fiscal_year}; "
            f"se usaron las de {est.rates_year_used}."
        ])
    writer.writerow([])
    writer.writerow([
        "Estimación orientativa de la base del ahorro. No es asesoramiento fiscal "
        "ni incluye la base general (trabajo, inmuebles…)."
    ])
    return output.getvalue()


@router.get("/estimate/{fiscal_year}/export")
def export_savings_estimate(
    db: DbSession, user: CurrentUser, fiscal_year: int, format: str = "csv"
):
    """Export the savings-base estimate: summary + per-bracket breakdown as CSV."""
    est = savings_estimate(db, user=user, fiscal_year=fiscal_year)
    if format != "csv":
        return est
    filename = f"finview_estimacion_ahorro_{fiscal_year}.csv"
    return StreamingResponse(
        iter([_savings_estimate_csv(est)]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
