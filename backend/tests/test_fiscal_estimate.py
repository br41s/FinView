"""Tests for the savings-estimate DB aggregation (broker casillas + manual entries).

Pins how `_aggregate_savings_inputs` folds TaxResult casillas, manual income
entries and withholdings into the estimator inputs. The pure tax math is
covered separately in test_tax_estimator.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from types import SimpleNamespace

from backend.api.fiscal import (
    _aggregate_savings_inputs,
    _manual_casillas,
    _savings_estimate_csv,
    list_casillas,
)
from backend.api.schemas import SavingsEstimateOut
from backend.models import (
    Account,
    Base,
    Broker,
    ManualSavingsIncome,
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
                    gross_amount=D("100"), withholding_tax=D("19"), net_amount_eur=D("81")),
        Transaction(account_id=acc.id, type=TransactionType.INTEREST.value,
                    trade_date=date(2024, 6, 1), quantity=D("1"), price=D("0"),
                    gross_amount=D("50"), withholding_tax=D("9"), net_amount_eur=D("41")),
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


def _sample_estimate(year=2024, rates_year=2024):
    return SavingsEstimateOut(
        fiscal_year=year, rates_year_used=rates_year,
        rcm_net=D("12500"), gp_net=D("0"), savings_base=D("12500"),
        rcm_carryforward=D("0"), gp_carryforward=D("0"),
        prior_rcm_loss_applied=D("0"), prior_gp_loss_applied=D("0"),
        personal_minimum=D("6700"), minimum_on_savings=D("6700"),
        gross_quota=D("2505"), quota=D("1218"), withholdings=D("2200"),
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
    cas, whg = _manual_casillas(db, 1, 2024)
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
