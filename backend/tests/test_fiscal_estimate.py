"""Tests for the savings-estimate DB aggregation (broker casillas + manual entries).

Pins how `_aggregate_savings_inputs` folds TaxResult casillas, manual income
entries and withholdings into the estimator inputs. The pure tax math is
covered separately in test_tax_estimator.
"""

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from types import SimpleNamespace

from backend.api.fiscal import (
    _aggregate_savings_inputs,
    _load_year_inputs,
    _savings_estimate_csv,
    cross_validation,
    dashboard_stats,
    fiscal_summary,
    list_casillas,
    list_fifo_adjustments,
    savings_estimate,
    yearly_comparison,
)
from backend.api.schemas import SavingsEstimateOut
from backend.models import (
    Account,
    Base,
    Broker,
    FIFOAdjustment,
    ManualSavingsIncome,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)

D = Decimal


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _casilla(user_id, year, casilla, amount, broker=Broker.TR):
    return TaxResult(
        user_id=user_id, fiscal_year=year, broker=broker, modelo=100,
        casilla=casilla, description="", amount_eur=D(amount),
    )


def _fifo_adjustment(user_id, year, broker_pl, fifo_pl):
    broker_value = D(broker_pl)
    fifo_value = D(fifo_pl)
    return FIFOAdjustment(
        user_id=user_id,
        fiscal_year=year,
        isin="US0000000001",
        name="Test",
        broker_pl_eur=broker_value,
        fifo_pl_eur=fifo_value,
        adjustment_eur=fifo_value - broker_value,
        broker_gains_eur=max(broker_value, D("0")),
        broker_losses_eur=min(broker_value, D("0")),
        fifo_gains_eur=max(fifo_value, D("0")),
        fifo_losses_eur=min(fifo_value, D("0")),
        calculation_version="2",
    )


def test_aggregates_broker_casillas(db):
    db.add_all([
        _casilla(1, 2024, 27, "500"),     # intereses
        _casilla(1, 2024, 29, "1500"),    # dividendos
        _casilla(1, 2024, 332, "800"),    # ganancias
        _casilla(1, 2024, 337, "-300"),   # pérdidas (stored ≤ 0)
        _casilla(1, 2024, 714, "99999"),  # patrimonio — must be ignored
    ])
    db.commit()

    inputs, casillas = _aggregate_savings_inputs(db, 1, 2024)
    assert inputs.rcm_net == D("2000")    # 500 + 1500
    assert inputs.gains == D("800")
    assert inputs.losses == D("-300")
    assert casillas["rcm"] == D("2000")


def test_scopes_by_user_and_year(db):
    db.add_all([
        _casilla(1, 2024, 29, "1000"),
        _casilla(2, 2024, 29, "5000"),    # other user
        _casilla(1, 2023, 29, "7000"),    # other year
    ])
    db.commit()

    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    assert inputs.rcm_net == D("1000")


def test_manual_entries_fold_in_with_sign(db):
    db.add_all([
        _casilla(1, 2024, 29, "1000"),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="RCM",
                            amount_eur=D("200"), withholding_eur=D("30")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="GAIN",
                            amount_eur=D("400")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="LOSS",
                            amount_eur=D("150")),  # positive magnitude → subtracts
    ])
    db.commit()

    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    assert inputs.rcm_net == D("1200")    # 1000 + 200
    assert inputs.gains == D("400")
    assert inputs.losses == D("-150")
    assert inputs.withholdings == D("30")  # manual withholding (no broker tx here)


def test_withholdings_from_dividend_and_interest_transactions(db):
    acc = Account(user_id=1, broker=Broker.TR, account_id="TR")
    db.add(acc)
    db.flush()
    db.add_all([
        Transaction(account_id=acc.id, type=TransactionType.DIVIDEND.value,
                    trade_date=date(2024, 5, 1), quantity=D("1"), price=D("0"),
                    gross_amount=D("100"), withholding_tax=D("19"),
                    domestic_withholding_tax=D("19"), foreign_withholding_tax=D("0"),
                    net_amount_eur=D("81")),
        Transaction(account_id=acc.id, type=TransactionType.INTEREST.value,
                    trade_date=date(2024, 6, 1), quantity=D("1"), price=D("0"),
                    gross_amount=D("50"), withholding_tax=D("9"),
                    domestic_withholding_tax=D("9"), foreign_withholding_tax=D("0"),
                    net_amount_eur=D("41")),
        Transaction(account_id=acc.id, type=TransactionType.BUY.value,
                    trade_date=date(2024, 7, 1), quantity=D("1"), price=D("10"),
                    gross_amount=D("10"), withholding_tax=D("5"), net_amount_eur=D("10")),
        # different year — excluded
        Transaction(account_id=acc.id, type=TransactionType.DIVIDEND.value,
                    trade_date=date(2023, 5, 1), quantity=D("1"), price=D("0"),
                    gross_amount=D("100"), withholding_tax=D("99"), net_amount_eur=D("1")),
    ])
    db.commit()

    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    assert inputs.withholdings == D("28")  # 19 + 9 (BUY and 2023 excluded)


def test_withholding_cash_domestic_and_foreign_credit_are_not_conflated(db):
    acc = Account(user_id=1, broker=Broker.TR, account_id="TR-ES")
    db.add(acc)
    db.flush()
    db.add(Transaction(
        account_id=acc.id,
        type=TransactionType.DIVIDEND.value,
        trade_date=date(2025, 5, 1),
        quantity=D("1"),
        price=D("100"),
        gross_amount=D("100"),
        withholding_tax=D("45"),
        domestic_withholding_tax=D("19"),
        foreign_withholding_tax=D("26"),
        double_taxation_amount=D("15"),
        net_amount_eur=D("55"),
    ))
    db.commit()

    inputs, casillas = _aggregate_savings_inputs(db, 1, 2025)
    shown = {row.casilla: row.amount_eur for row in list_casillas(
        db, user=_user(1), fiscal_year=2025
    )}

    assert inputs.withholdings == D("19")
    assert inputs.double_taxation_credit == D("15")
    assert casillas["cash_withholdings"] == D("45")
    assert casillas["domestic_withholdings"] == D("19")
    assert casillas["double_taxation_credit"] == D("15")
    assert shown[597] == D("19")
    assert shown[588] == D("15")


def test_legacy_foreign_withholding_is_visible_but_not_guessed(db):
    acc = Account(user_id=1, broker=Broker.IBKR, account_id="IBKR")
    db.add(acc)
    db.flush()
    db.add(Transaction(
        account_id=acc.id,
        type=TransactionType.DIVIDEND.value,
        trade_date=date(2024, 5, 1),
        quantity=D("1"),
        price=D("100"),
        gross_amount=D("100"),
        withholding_tax=D("-15"),  # legacy sign and no semantic split
        net_amount_eur=D("85"),
    ))
    db.commit()

    inputs, casillas = _aggregate_savings_inputs(db, 1, 2024)
    estimate = savings_estimate(db, user=_user(1), fiscal_year=2024)

    assert inputs.withholdings == D("0")
    assert casillas["cash_withholdings"] == D("15")
    assert estimate.withholding_breakdown_complete is False
    assert estimate.incomplete_withholding_transactions == 1


def test_signed_2025_asset_boxes_feed_economic_gains_and_losses(db):
    db.add_all([
        _casilla(1, 2025, 328, "-50"),
        _casilla(1, 2025, 380, "125"),
    ])
    db.commit()

    inputs, _ = _aggregate_savings_inputs(db, 1, 2025)
    summary = fiscal_summary(db, user=_user(1), fiscal_year=2025)

    assert inputs.gains == D("125")
    assert inputs.losses == D("-50")
    assert summary.total_gains == D("125")
    assert summary.total_losses == D("-50")


def _sample_estimate(year=2024, rates_year=2024):
    return SavingsEstimateOut(
        fiscal_year=year, rates_year_used=rates_year,
        rcm_net=D("12500"), gp_net=D("0"), savings_base=D("12500"),
        rcm_carryforward=D("0"), gp_carryforward=D("0"),
        prior_rcm_loss_applied=D("0"), prior_gp_loss_applied=D("0"),
        personal_minimum=D("6700"), minimum_on_savings=D("6700"),
        gross_quota=D("2505"), quota=D("1218"), withholdings=D("2200"),
        cash_withholdings=D("2200"), domestic_withholdings=D("2200"),
        double_taxation_credit=D("0"), withholding_breakdown_complete=True,
        incomplete_withholding_transactions=0,
        result=D("-982"),
        brackets=[
            {"from": D("0"), "to": D("6000"), "rate": D("0.19"), "tax": D("1140")},
            {"from": D("6000"), "to": D("12500"), "rate": D("0.21"), "tax": D("1365")},
        ],
        casillas={"rcm": D("12500"), "gains": D("0"), "losses": D("0"),
                  "withholdings": D("2200")},
    )


def test_estimate_csv_has_summary_and_brackets():
    csv_text = _savings_estimate_csv(_sample_estimate())
    assert "Base imponible del ahorro,12500" in csv_text
    assert "Cuota tras mínimo,1218" in csv_text
    assert "Resultado" in csv_text and "-982" in csv_text
    # per-bracket rows present with rate and tax
    assert "0,6000,0.19,1140" in csv_text
    assert "6000,12500,0.21,1365" in csv_text
    # no stale-year warning when rates match the year
    assert "Aviso: sin tablas" not in csv_text


def test_estimate_csv_warns_on_rates_year_mismatch():
    csv_text = _savings_estimate_csv(_sample_estimate(year=2030, rates_year=2025))
    assert "Aviso: sin tablas fiscales para 2030" in csv_text
    assert "se usaron las de 2025" in csv_text


# ── Casilla coherence: manual entries flow into the casilla-level views ──────
def _user(uid=1):
    return SimpleNamespace(id=uid)


def test_manual_casillas_maps_categories_to_boxes(db):
    db.add_all([
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="INTEREST",
                            amount_eur=D("500"), withholding_eur=D("50")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="DIVIDEND",
                            amount_eur=D("300"), withholding_eur=D("30")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="RCM",
                            amount_eur=D("100")),  # legacy → 29
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="GAIN",
                            amount_eur=D("800")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="LOSS",
                            amount_eur=D("200")),
    ])
    db.commit()
    inputs = _load_year_inputs(db, 1, 2024)
    cas, whg = inputs.manual_cas, inputs.manual_whg
    assert cas[27] == D("500")               # interest → 27
    assert cas[29] == D("400")               # 300 dividend + 100 legacy RCM → 29
    assert cas[332] == D("800")
    assert cas[337] == D("-200")             # loss stored negative
    assert whg[27] == D("50") and whg[29] == D("30")


def test_list_casillas_folds_manual_as_source(db):
    db.add_all([
        _casilla(1, 2024, 29, "1000"),       # broker dividends
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="DIVIDEND",
                            amount_eur=D("300")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="INTEREST",
                            amount_eur=D("500")),  # manual-only box (27)
    ])
    db.commit()
    by_box = {r.casilla: r for r in list_casillas(db, user=_user(1), fiscal_year=2024)}
    # broker 1000 + manual 300 = 1300, with a MANUAL source line
    assert by_box[29].amount_eur == D("1300")
    assert any(b.broker == "MANUAL" and b.amount_eur == D("300") for b in by_box[29].brokers)
    # casilla that exists only from manual data still appears
    assert by_box[27].amount_eur == D("500")
    assert by_box[27].brokers[0].broker == "MANUAL"


def test_casillas_and_estimate_agree(db):
    db.add_all([
        _casilla(1, 2024, 29, "2000"),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="DIVIDEND",
                            amount_eur=D("1000")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="INTEREST",
                            amount_eur=D("400")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="GAIN",
                            amount_eur=D("500")),
    ])
    db.commit()
    by_box = {r.casilla: r.amount_eur for r in list_casillas(db, user=_user(1), fiscal_year=2024)}
    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    # The estimate's RCM equals c27 + c29 shown in Casillas fiscales; gains = c332.
    assert inputs.rcm_net == by_box.get(27, D("0")) + by_box.get(29, D("0"))
    assert inputs.gains == by_box.get(332, D("0"))


def test_fifo_adjustment_flows_into_all_fiscal_totals(db):
    broker_box = _casilla(1, 2024, 332, "200")
    broker_box.tr_reference_amount = D("200")
    db.add_all([
        broker_box,
        _fifo_adjustment(1, 2024, "200", "600"),
    ])
    db.commit()

    by_box = {
        row.casilla: row
        for row in list_casillas(db, user=_user(1), fiscal_year=2024)
    }
    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    summary = fiscal_summary(db, user=_user(1), fiscal_year=2024)
    yearly = yearly_comparison(db, user=_user(1)).years[0]
    validation = cross_validation(db, user=_user(1), fiscal_year=2024).rows[0]

    assert by_box[332].amount_eur == D("600")
    assert by_box[332].fifo_adjustment_eur == D("400")
    assert inputs.gains == D("600")
    assert summary.total_gains == D("600")
    assert summary.net_capital_gains == D("600")
    assert yearly.gains == D("600")
    assert yearly.net_capital == D("600")
    assert validation.finview_amount == D("600")
    assert validation.compare_amount == D("600")
    assert validation.status == "no_independent_data"


def test_fifo_sign_change_moves_result_from_gains_to_losses(db):
    db.add_all([
        _casilla(1, 2024, 332, "200"),
        _fifo_adjustment(1, 2024, "200", "-100"),
    ])
    db.commit()

    by_box = {
        row.casilla: row
        for row in list_casillas(db, user=_user(1), fiscal_year=2024)
    }
    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)
    summary = fiscal_summary(db, user=_user(1), fiscal_year=2024)
    validation_by_box = {
        row.casilla: row
        for row in cross_validation(db, user=_user(1), fiscal_year=2024).rows
    }

    assert by_box[332].amount_eur == D("0")
    assert by_box[332].fifo_adjustment_eur == D("-200")
    assert by_box[337].amount_eur == D("-100")
    assert by_box[337].fifo_adjustment_eur == D("-100")
    assert validation_by_box[337].finview_amount == D("-100")
    assert inputs.gains == D("0")
    assert inputs.losses == D("-100")
    assert summary.total_gains == D("0")
    assert summary.total_losses == D("-100")
    assert summary.net_capital_gains == D("-100")


def test_legacy_fifo_adjustment_is_not_applied_without_recalculation(db):
    legacy = _fifo_adjustment(1, 2024, "200", "600")
    legacy.calculation_version = None
    db.add_all([_casilla(1, 2024, 332, "200"), legacy])
    db.commit()

    by_box = {
        row.casilla: row
        for row in list_casillas(db, user=_user(1), fiscal_year=2024)
    }
    inputs, _ = _aggregate_savings_inputs(db, 1, 2024)

    assert by_box[332].amount_eur == D("200")
    assert by_box[332].fifo_adjustment_eur is None
    assert inputs.gains == D("200")
    assert list_fifo_adjustments(db, user=_user(1), fiscal_year=2024) == []


def test_cross_validation_does_not_claim_tautological_match(db):
    tr_box = _casilla(1, 2024, 332, "100", broker=Broker.TR)
    tr_box.tr_reference_amount = D("100")
    db.add_all([
        tr_box,
        _casilla(1, 2024, 332, "50", broker=Broker.DEGIRO),
    ])
    db.commit()

    casilla = list_casillas(db, user=_user(1), fiscal_year=2024)[0]
    validation = cross_validation(db, user=_user(1), fiscal_year=2024).rows[0]

    assert casilla.amount_eur == D("150")
    assert casilla.validation_status is None
    assert validation.finview_amount == D("150")
    assert validation.compare_amount == D("150")
    assert validation.tr_amount is None
    assert validation.status == "no_independent_data"


def test_legacy_fifo_only_year_is_not_listed(db):
    legacy = _fifo_adjustment(1, 2023, "0", "50")
    legacy.calculation_version = None
    db.add(legacy)
    db.commit()

    assert yearly_comparison(db, user=_user(1)).years == []


def test_yearly_comparison_includes_fifo_only_year(db):
    db.add(_fifo_adjustment(1, 2024, "0", "50"))
    db.commit()

    yearly = yearly_comparison(db, user=_user(1)).years

    assert len(yearly) == 1
    assert yearly[0].fiscal_year == 2024
    assert yearly[0].gains == D("50")
    assert yearly[0].net_capital == D("50")


def test_dashboard_applies_fifo_adjustment(db):
    account = Account(user_id=1, broker=Broker.TR, account_id="TR-FIFO")
    db.add(account)
    db.flush()
    buy = Transaction(
        account_id=account.id,
        type=TransactionType.BUY.value,
        trade_date=date(2023, 1, 1),
        isin="US0000000001",
        quantity=D("1"),
        price=D("100"),
        gross_amount=D("100"),
        net_amount_eur=D("100"),
    )
    sell = Transaction(
        account_id=account.id,
        type=TransactionType.SELL.value,
        trade_date=date(2024, 1, 1),
        isin="US0000000001",
        quantity=D("1"),
        price=D("300"),
        gross_amount=D("300"),
        net_amount_eur=D("300"),
    )
    db.add_all([buy, sell])
    db.flush()
    db.add_all([
        TaxLot(
            buy_tx_id=buy.id,
            sell_tx_id=sell.id,
            isin="US0000000001",
            quantity_bought=D("1"),
            quantity_remaining=D("0"),
            cost_basis_eur=D("100"),
            quantity_sold=D("1"),
            proceeds_eur=D("300"),
            realized_pl_eur=D("200"),
            close_date=date(2024, 1, 1),
        ),
        _fifo_adjustment(1, 2024, "200", "600"),
    ])
    db.commit()

    stats = dashboard_stats(db, user=_user(1), fiscal_year=2024)

    assert stats.total_gains_eur == D("600")
    assert stats.net_pl_eur == D("600")


# ── Query budget: each per-year input is loaded once per request ─────────────
@contextmanager
def _counting_statements(db):
    """Collect every statement the session sends while the block runs."""
    engine = db.get_bind()
    seen: list[str] = []

    def _record(_conn, _cursor, statement, *_args, **_kwargs):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def test_fiscal_summary_loads_each_input_once(db):
    """One summary used to issue ~15 statements: the manual-income query ran four
    times and the full-year transaction scan twice, because it called the casillas
    endpoint internally and every withholding total re-ran the manual query. Six
    is the floor — manual, FIFO, withholding, box sums, dividend net, broker rows —
    and it is pinned so the duplication cannot creep back unnoticed.
    """
    db.add_all([
        _casilla(1, 2024, 29, "1500"),
        _casilla(1, 2024, 332, "800"),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="DIVIDEND",
                            amount_eur=D("300"), withholding_eur=D("30")),
        _fifo_adjustment(1, 2024, "100", "150"),
    ])
    db.commit()

    with _counting_statements(db) as statements:
        summary = fiscal_summary(db, user=_user(1), fiscal_year=2024)

    assert len(statements) == 6, "\n".join(statements)
    assert summary.total_dividends_gross == D("1800")
    assert summary.total_gains == D("850")  # 800 broker + 50 FIFO delta
    assert summary.total_withholdings == D("30")


def test_yearly_comparison_query_count_does_not_grow_with_years(db):
    """Three statements per year became three in total, so two years cost the same
    five statements as one: broker rows, positions per year, manual, FIFO, withholding.
    """
    db.add_all([
        _casilla(1, 2023, 29, "100"),
        _casilla(1, 2024, 29, "200"),
        ManualSavingsIncome(user_id=1, fiscal_year=2023, category="DIVIDEND",
                            amount_eur=D("10"), withholding_eur=D("1")),
        ManualSavingsIncome(user_id=1, fiscal_year=2024, category="GAIN", amount_eur=D("20")),
        _fifo_adjustment(1, 2024, "100", "150"),
    ])
    db.commit()

    with _counting_statements(db) as statements:
        result = yearly_comparison(db, user=_user(1))

    assert len(statements) == 5, "\n".join(statements)
    by_year = {m.fiscal_year: m for m in result.years}
    assert by_year[2023].dividends_gross == D("110")
    assert by_year[2023].withholdings == D("1")
    assert by_year[2024].gains == D("70")  # 20 manual + 50 FIFO delta
