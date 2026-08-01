"""Regression tests for fee-aware acquisition and disposal amounts."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.importers.base import ParsedGainLoss, ParsedTransaction, TxType
from backend.importers.dg import SEC_TRANSACTIONS, _parse_transactions
from backend.models import Account, Base, ImportRecord, TaxLot, TransactionType, User
from backend.services.import_service import _create_dg_tax_lots
from backend.services.transaction_amounts import trade_net_amount


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _dg_import(db) -> tuple[Account, ImportRecord]:
    user = User(email="fees@example.com", name="Fees", password_hash="x")
    db.add(user)
    db.flush()
    account = Account(
        broker="DEGIRO",
        account_id="fees",
        name="Fees",
        user_id=user.id,
    )
    db.add(account)
    db.flush()
    record = ImportRecord(
        account_id=account.id,
        filename="fees.pdf",
        file_hash="fees-hash",
        broker="DEGIRO",
        fiscal_year=2024,
        record_count=1,
    )
    db.add(record)
    db.flush()
    return account, record


def test_trade_net_amount_capitalizes_buy_fees_and_reduces_sell_proceeds():
    assert trade_net_amount(
        TransactionType.BUY.value,
        Decimal("1000"),
        Decimal("10"),
    ) == Decimal("1010")
    assert trade_net_amount(
        TransactionType.BUY,
        Decimal("1000"),
        Decimal("10"),
    ) == Decimal("1010")
    assert trade_net_amount(
        TransactionType.SELL.value,
        Decimal("1200"),
        Decimal("10"),
    ) == Decimal("1190")
    assert trade_net_amount(
        TransactionType.SPINOFF.value,
        Decimal("0"),
        Decimal("5"),
    ) == Decimal("5")


def test_degiro_detailed_transactions_include_commissions_in_net_amount():
    text = "\n".join([
        SEC_TRANSACTIONS,
        "01/01/2024 Bayer AG DE000BAY0017 C 10 265,40 -2.654,00 2.654,00 4,90 1,00",
        "01/06/2024 Bayer AG DE000BAY0017 V 10 275,00 2.750,00 2.750,00 1,50 1,00 96,00",
        "Informe anual de flatex",
    ])

    buy, sell = _parse_transactions(text)

    assert buy.net_amount_eur == Decimal("2658.90")
    assert sell.net_amount_eur == Decimal("2748.50")


def test_degiro_tax_lot_uses_gain_after_commission_and_transaction_tax(db):
    account, record = _dg_import(db)
    gain = ParsedGainLoss(
        isin="DE000BAY0017",
        name="Bayer AG",
        realized_pl_eur=Decimal("96"),
        commission_eur=Decimal("4.90"),
        transaction_tax_eur=Decimal("0"),
    )
    sell = ParsedTransaction(
        tx_type=TxType.SELL,
        trade_date=date(2024, 6, 1),
        isin=gain.isin,
        name=gain.name,
        country="Alemania",
        quantity=Decimal("10"),
        price=Decimal("275"),
        gross_amount=Decimal("2750"),
        net_amount_eur=Decimal("2750"),
    )

    _create_dg_tax_lots(
        db,
        [gain],
        [sell],
        account.id,
        record.id,
        2024,
    )
    lot = db.query(TaxLot).one()

    assert lot.cost_basis_eur == Decimal("2658.90")
    assert lot.realized_pl_eur == Decimal("91.10")


def test_degiro_small_gross_gain_can_become_taxable_loss(db):
    account, record = _dg_import(db)
    gain = ParsedGainLoss(
        isin="DE0000000001",
        name="Small gain",
        realized_pl_eur=Decimal("1"),
        commission_eur=Decimal("1.50"),
        transaction_tax_eur=Decimal("0.25"),
    )

    _create_dg_tax_lots(db, [gain], [], account.id, record.id, 2024)

    assert db.query(TaxLot).one().realized_pl_eur == Decimal("-0.75")


def test_degiro_report_contract_deducts_all_documented_costs():
    gross_realized = Decimal("576.46")
    commissions = Decimal("38.63")
    transaction_tax = Decimal("0.82")

    assert gross_realized - commissions - transaction_tax == Decimal("537.01")
