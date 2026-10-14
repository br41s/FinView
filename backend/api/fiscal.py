"""API endpoints for fiscal / tax data."""

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
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


def _fifo_rows(db, user_id: int, year: int | None = None) -> list[FIFOAdjustment]:
    """Versioned FIFO corrections for one year, or for every year when *year* is None."""
    q = db.query(FIFOAdjustment).filter(
        FIFOAdjustment.user_id == user_id,
        FIFOAdjustment.calculation_version == FIFO_CALCULATION_VERSION,
    )
    if year is not None:
        q = q.filter(FIFOAdjustment.fiscal_year == year)
    return q.all()


def _casilla_sums(
    db, user_id: int, year: int, casillas: tuple[int, ...], modelo: int | None = None
) -> dict[int, Decimal]:
    """Broker totals per box for one year: one GROUP BY instead of a query per box."""
    q = db.query(TaxResult.casilla, func.sum(TaxResult.amount_eur)).filter(
        TaxResult.user_id == user_id,
        TaxResult.fiscal_year == year,
        TaxResult.casilla.in_(casillas),
    )
    if modelo is not None:
        q = q.filter(TaxResult.modelo == modelo)
    return {c: (a or Decimal("0")) for c, a in q.group_by(TaxResult.casilla).all()}


_CAPITAL_CASILLAS = (328, 332, 337, 380)


def _capital_totals(casillas: dict[int, Decimal]) -> tuple[Decimal, Decimal]:
    """Return positive gains and negative losses across year-specific boxes."""
    amounts = [casillas.get(box, Decimal("0")) for box in _CAPITAL_CASILLAS]
    return (
        sum((amount for amount in amounts if amount > 0), Decimal("0")),
        sum((amount for amount in amounts if amount < 0), Decimal("0")),
    )


def _withholding_rows(db, user_id: int, year: int | None = None):
    """Transactions that can move a withholding total, as bare columns.

    A row with no withholding, no explicit domestic/foreign amount and no
    double-taxation credit adds zero to every accumulator in
    ``_fold_withholding``, so it is filtered out here instead of being loaded
    as a full ORM object: BUY/SELL rows are most of the ledger and carry none.
    """
    q = (
        db.query(
            year_str(Transaction.trade_date).label("yr"),
            Transaction.withholding_tax,
            Transaction.domestic_withholding_tax,
            Transaction.foreign_withholding_tax,
            Transaction.double_taxation_amount,
            Transaction.gross_amount,
            Account.broker,
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            or_(
                func.coalesce(Transaction.withholding_tax, 0) != 0,
                func.coalesce(Transaction.domestic_withholding_tax, 0) != 0,
                func.coalesce(Transaction.foreign_withholding_tax, 0) != 0,
                func.coalesce(Transaction.double_taxation_amount, 0) != 0,
            ),
        )
    )
    if year is not None:
        q = q.filter(year_range(Transaction.trade_date, year))
    return q.all()


def _fold_withholding(rows, manual_whg: dict[int, Decimal]) -> dict[str, Decimal | int | bool]:
    """Aggregate cash withheld and the two independently deductible amounts.

    Rows imported before the explicit domestic/foreign split stay visible in
    cash totals but do not reduce estimated tax unless their meaning is
    unambiguous (ING/BBVA Spanish withholding) or they carry an explicit
    double-taxation credit. Manual entries' withholding is Spanish by definition.
    """
    cash = domestic = foreign = credit = foreign_income = Decimal("0")
    incomplete = 0
    for row in rows:
        total = abs(row.withholding_tax or Decimal("0"))
        explicit = (
            row.domestic_withholding_tax is not None
            and row.foreign_withholding_tax is not None
        )
        cash += total
        tx_credit = abs(row.double_taxation_amount or Decimal("0"))
        credit += tx_credit
        if tx_credit:
            foreign_income += max(row.gross_amount or Decimal("0"), Decimal("0"))
        if explicit:
            domestic += abs(row.domestic_withholding_tax or Decimal("0"))
            foreign += abs(row.foreign_withholding_tax or Decimal("0"))
        elif total and row.broker in (Broker.ING, Broker.BBVA):
            domestic += total
        elif total:
            incomplete += 1

    manual = sum(manual_whg.values(), Decimal("0"))
    cash += manual
    domestic += manual
    return {
        "cash": cash,
        "domestic": domestic,
        "foreign": foreign,
        "credit": credit,
        "foreign_income": foreign_income,
        "deductible": domestic + credit,
        "incomplete_count": incomplete,
        "complete": incomplete == 0,
    }


@dataclass(frozen=True)
class _YearInputs:
    """Everything beyond TaxResult that a casilla-level view needs for one year.

    Loaded once per request and handed down. ``fiscal_summary`` used to call
    the ``list_casillas`` endpoint internally and every withholding total
    re-ran the manual-income query, so one summary issued ~15 queries where 6
    do, and the yearly comparison ran three more per year.
    """

    manual_cas: dict[int, Decimal]  # manual entries by box, LOSS negative
    manual_whg: dict[int, Decimal]  # their withholding by box
    fifo_cas: dict[int, Decimal]  # versioned FIFO deltas by box
    withholding: dict[str, Decimal | int | bool]  # see _fold_withholding


def _year_inputs(manual_rows, fifo_rows, withholding_rows) -> _YearInputs:
    manual_cas, manual_whg = _fold_manual(manual_rows)
    return _YearInputs(
        manual_cas=manual_cas,
        manual_whg=manual_whg,
        fifo_cas=_fifo_casilla_deltas(fifo_rows),
        withholding=_fold_withholding(withholding_rows, manual_whg),
    )


def _load_year_inputs(db, user_id: int, year: int) -> _YearInputs:
    return _year_inputs(
        _manual_rows(db, user_id, year),
        _fifo_rows(db, user_id, year),
        _withholding_rows(db, user_id, year),
    )


def _by_year(rows, year_of) -> dict[int, list]:
    grouped: dict[int, list] = defaultdict(list)
    for row in rows:
        grouped[year_of(row)].append(row)
    return grouped


def _load_inputs_by_year(db, user_id: int) -> dict[int, _YearInputs]:
    """Inputs for every year that has any: three queries instead of three per year."""
    manual = _by_year(_manual_rows(db, user_id), lambda r: r.fiscal_year)
    fifo = _by_year(_fifo_rows(db, user_id), lambda r: r.fiscal_year)
    withholding = _by_year(_withholding_rows(db, user_id), lambda r: int(r.yr))
    return {
        year: _year_inputs(manual.get(year, []), fifo.get(year, []), withholding.get(year, []))
        for year in set(manual) | set(fifo) | set(withholding)
    }


@router.get("/casillas", response_model=list[AggregatedCasillaOut])
def list_casillas(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """List tax casillas aggregated across all brokers."""
    inputs = _load_year_inputs(db, user.id, fiscal_year) if fiscal_year else None
    return _aggregate_casillas(db, user.id, fiscal_year, inputs)


def _aggregate_casillas(
    db, user_id: int, fiscal_year: int | None, inputs: _YearInputs | None
) -> list[AggregatedCasillaOut]:
    """Broker rows per (modelo, casilla) plus the manual, FIFO and derived boxes.

    Manual entries, FIFO deltas and the withholding-derived boxes (588/597) are
    folded in only for a single year (*inputs* given): across all years they
    have no one box to land in.
    """
    q = db.query(TaxResult).filter(TaxResult.user_id == user_id)
    if fiscal_year:
        q = q.filter(TaxResult.fiscal_year == fiscal_year)
    rows = q.order_by(TaxResult.modelo, TaxResult.casilla).all()

    # Aggregate by (modelo, casilla)
    grouped: dict[tuple[int, int], list[TaxResult]] = {}
    for r in rows:
        key = (r.modelo, r.casilla)
        grouped.setdefault(key, []).append(r)

    man_cas = inputs.manual_cas if inputs else {}
    fifo_adj_by_casilla = inputs.fifo_cas if inputs else {}
    withholding_cas: dict[int, Decimal] = {}
    if inputs:
        whg = inputs.withholding
        withholding_cas = {
            box: amount
            for box, amount in {
                588: whg["credit"],
                597: whg["domestic"],
            }.items()
            if amount
        }

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
        result.append(AggregatedCasillaOut(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            amount_eur=total,
            brokers=brokers,
            fifo_adjustment_eur=adj_val or None,
            tr_reference_amount=None,
            validation_status=None,
        ))

    # Casillas that exist only from manual or FIFO data (no broker rows this year).
    for casilla in sorted(set(man_cas) | set(fifo_adj_by_casilla) | set(withholding_cas)):
        amt = man_cas.get(casilla, Decimal("0"))
        adj_val = fifo_adj_by_casilla.get(casilla, Decimal("0"))
        if (100, casilla) in grouped:
            continue
        brokers = []
        if amt:
            brokers.append({"broker": "MANUAL", "amount_eur": amt})
        derived = withholding_cas.get(casilla, Decimal("0"))
        if derived:
            brokers.append({"broker": "CALCULATED", "amount_eur": derived})
        result.append(AggregatedCasillaOut(
            modelo=100,
            casilla=casilla,
            description=_MANUAL_CASILLA_DESC.get(casilla, ""),
            amount_eur=amt + adj_val + derived,
            brokers=brokers,
            fifo_adjustment_eur=adj_val or None,
        ))

    result.sort(key=lambda c: (c.modelo, c.casilla))
    return result


@router.get("/summary/{fiscal_year}", response_model=FiscalSummary)
def fiscal_summary(db: DbSession, user: CurrentUser, fiscal_year: int):
    """Get complete fiscal summary for a year using TaxResult (broker truth)."""
    # Manual savings entries mapped to casillas — folded into every total below
    # so the summary matches Casillas fiscales and Mi declaración.
    inputs = _load_year_inputs(db, user.id, fiscal_year)
    man_cas = inputs.manual_cas
    sums = _casilla_sums(db, user.id, fiscal_year, (29, *_CAPITAL_CASILLAS))

    # Dividends — casilla 29 (broker + manual) for gross; Transaction for net/whg.
    div_gross = sums.get(29, Decimal("0")) + man_cas.get(29, Decimal("0"))
    div_detail = (
        db.query(
            func.coalesce(func.sum(Transaction.net_amount_eur), 0).label("net"),
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
    manual_div_net = man_cas.get(29, Decimal("0")) - inputs.manual_whg.get(29, Decimal("0"))
    capital_cas = {
        box: sums.get(box, Decimal("0")) + man_cas.get(box, Decimal("0"))
        for box in _CAPITAL_CASILLAS
    }
    for box, amount in inputs.fifo_cas.items():
        capital_cas[box] = capital_cas.get(box, Decimal("0")) + amount
    gains_total, losses_total = _capital_totals(capital_cas)

    # Same aggregation as the Casillas fiscales view, from the same loaded
    # inputs, so the summary's casillas are byte-identical to it.
    aggregated_casillas = _aggregate_casillas(db, user.id, fiscal_year, inputs)

    return FiscalSummary(
        fiscal_year=fiscal_year,
        total_dividends_gross=div_gross,
        total_dividends_net=div_detail.net + manual_div_net,
        total_withholdings=inputs.withholding["cash"],
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
    # 0 reads as "all years" here, like _with_year above.
    fifo_cas = _fifo_casilla_deltas(_fifo_rows(db, user.id, fiscal_year or None))
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
    """Describe whether each broker casilla has independent validation data."""
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

    fifo_adj = _fifo_casilla_deltas(_fifo_rows(db, user.id, fiscal_year))

    result_rows: list[CrossValidationRow] = []
    no_ref_count = 0

    keys = set(grouped)
    keys.update((100, casilla) for casilla in fifo_adj)
    for modelo, casilla in sorted(keys):
        items = grouped.get((modelo, casilla), [])
        total = sum(i.amount_eur for i in items)
        adj_val = fifo_adj.get(casilla, Decimal("0"))
        adjusted_total = total + adj_val
        desc = items[0].description if items else _MANUAL_CASILLA_DESC.get(casilla, "")
        brokers = [{"broker": i.broker, "amount_eur": i.amount_eur} for i in items]

        broker_count = len({item.broker for item in items})
        # TaxResult is copied from the broker report. Comparing it with the
        # same copied value previously produced a guaranteed false "match".
        diff = None
        compare_amount = adjusted_total
        status = "no_independent_data"
        no_ref_count += 1

        result_rows.append(CrossValidationRow(
            modelo=modelo,
            casilla=casilla,
            description=desc,
            finview_amount=adjusted_total,
            compare_amount=compare_amount,
            tr_amount=None,
            difference=diff,
            status=status,
            is_multi_broker=broker_count > 1 or bool(adj_val),
            brokers=brokers,
        ))

    return CrossValidationResult(
        fiscal_year=fiscal_year,
        rows=result_rows,
        total_match=0,
        total_mismatch=0,
        total_no_ref=no_ref_count,
    )


@router.get("/yearly-comparison", response_model=YearlyComparisonResult)
def yearly_comparison(db: DbSession, user: CurrentUser):
    """Get fiscal metrics aggregated per year for multi-year comparison."""
    # The Modelo 100 changed from legacy gain/loss boxes (332/337) to signed
    # asset-category boxes (328/380), so rows are folded by year in Python.
    tax_rows = db.query(TaxResult).filter(TaxResult.user_id == user.id).all()
    tax_by_year: dict[int, dict[int, Decimal]] = {}
    brokers_by_year: dict[int, set[str]] = {}
    for row in tax_rows:
        year_cas = tax_by_year.setdefault(row.fiscal_year, {})
        year_cas[row.casilla] = year_cas.get(row.casilla, Decimal("0")) + row.amount_eur
        if row.broker:
            brokers_by_year.setdefault(row.fiscal_year, set()).add(str(row.broker))

    tx_rows = (
        db.query(
            year_str(Transaction.trade_date).label("yr"),
            func.count(func.distinct(Transaction.isin)).label("pos_count"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(Account.user_id == user.id)
        .group_by(year_str(Transaction.trade_date))
        .all()
    )
    positions_by_year = {int(row.yr): row.pos_count for row in tx_rows}

    inputs_by_year = _load_inputs_by_year(db, user.id)
    metrics = []
    years = set(tax_by_year) | set(positions_by_year) | set(inputs_by_year)
    for year in sorted(years):
        inputs = inputs_by_year.get(year) or _year_inputs([], [], [])
        cas = dict(tax_by_year.get(year, {}))
        for extra in (inputs.manual_cas, inputs.fifo_cas):
            for box, amount in extra.items():
                cas[box] = cas.get(box, Decimal("0")) + amount
        gains, losses = _capital_totals(cas)
        metrics.append(YearlyMetrics(
            fiscal_year=year,
            dividends_gross=cas.get(29, Decimal("0")),
            gains=gains,
            losses=losses,
            net_capital=gains + losses,
            withholdings=inputs.withholding["cash"],
            brokers=len(brokers_by_year.get(year, set())),
            positions=positions_by_year.get(year, 0),
        ))
    return YearlyComparisonResult(years=metrics)


# ── Fiscal onboarding: savings-base estimate (v1 individual) ─────────────────
_SAVINGS_CASILLAS = (27, 29, 328, 332, 337, 380)


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
    588: "Deducción por doble imposición internacional",
    597: "Retenciones por rendimientos del capital mobiliario",
}


def _manual_rows(db, user_id: int, year: int | None = None) -> list[ManualSavingsIncome]:
    """Manual savings entries for one year, or for every year when *year* is None."""
    q = db.query(ManualSavingsIncome).filter(ManualSavingsIncome.user_id == user_id)
    if year is not None:
        q = q.filter(ManualSavingsIncome.fiscal_year == year)
    return q.all()


def _fold_manual(rows) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """Manual savings entries mapped to Modelo 100 casillas.

    Returns (amount_by_casilla {LOSS negative}, withholding_by_casilla). Single
    source behind list_casillas, fiscal_summary and the estimate so the
    manually-entered income shows up identically everywhere.
    """
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


def _aggregate_savings_inputs(
    db, user_id: int, year: int, inputs: _YearInputs | None = None
) -> tuple[SavingsInputs, dict]:
    """Sum savings components from broker casillas + manual entries + withholdings.

    *inputs* is the year's loaded inputs when the caller already has them
    (``savings_estimate`` reuses the withholding breakdown); loaded here otherwise.
    """
    if inputs is None:
        inputs = _load_year_inputs(db, user_id, year)
    cas = _casilla_sums(db, user_id, year, _SAVINGS_CASILLAS, modelo=100)

    # Fold in manual entries and FIFO deltas mapped to the same casillas.
    for extra in (inputs.manual_cas, inputs.fifo_cas):
        for box, amt in extra.items():
            cas[box] = cas.get(box, Decimal("0")) + amt
    rcm = cas.get(27, Decimal("0")) + cas.get(29, Decimal("0"))
    gains, losses = _capital_totals(cas)

    whg = inputs.withholding
    casillas = {
        "rcm": rcm,
        "gains": gains,
        "losses": losses,
        "withholdings": whg["deductible"],
        "cash_withholdings": whg["cash"],
        "domestic_withholdings": whg["domestic"],
        "double_taxation_credit": whg["credit"],
    }
    return (
        SavingsInputs(
            rcm_net=rcm,
            gains=gains,
            losses=losses,
            withholdings=whg["domestic"],
            double_taxation_credit=whg["credit"],
            foreign_taxed_income=whg["foreign_income"],
        ),
        casillas,
    )


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
        health_data_consent=p.health_data_consent_at is not None,
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
    if body.disability is not None and not body.health_data_consent:
        raise HTTPException(
            status_code=422,
            detail="Para guardar el grado de discapacidad necesitamos tu consentimiento expreso",
        )
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
    if body.disability is None:
        p.health_data_consent_at = None  # clearing the field withdraws consent
    elif p.health_data_consent_at is None:
        p.health_data_consent_at = datetime.now(timezone.utc)
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
        health_data_consent=p.health_data_consent_at is not None,
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
    year_inputs = _load_year_inputs(db, user.id, fiscal_year)
    inputs, casillas = _aggregate_savings_inputs(db, user.id, fiscal_year, year_inputs)

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
    withholding = year_inputs.withholding
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
        cash_withholdings=withholding["cash"],
        domestic_withholdings=est.domestic_withholdings,
        double_taxation_credit=withholding["credit"],
        double_taxation_credit_applied=est.double_taxation_credit_applied,
        withholding_breakdown_complete=withholding["complete"],
        incomplete_withholding_transactions=withholding["incomplete_count"],
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
        ("Retenido en efectivo", est.cash_withholdings),
        ("Pago a cuenta español (casilla 0597)", est.domestic_withholdings),
        ("Crédito exterior informado (límite 0588)", est.double_taxation_credit),
        ("Doble imposición aplicada (casilla 0588)", est.double_taxation_credit_applied),
        ("Total de pagos y deducciones aplicado", est.withholdings),
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
    if not est.withholding_breakdown_complete:
        writer.writerow([])
        writer.writerow([
            "Aviso: "
            f"{est.incomplete_withholding_transactions} retenciones antiguas no tienen "
            "desglose origen/destino y no reducen la estimación hasta reimportarlas."
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
