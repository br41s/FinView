"""Manual transaction CRUD regressions for FIFO integrity."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.transactions import (
    TransactionCreate,
    TransactionUpdate,
    create_transaction,
    delete_transaction,
    update_transaction,
)
from backend.models import Account, Base, CrossBrokerLot, FIFOAdjustment, User


@pytest.fixture
def context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="manual@example.com", name="Manual", password_hash="x")
    db.add(user)
    db.flush()
    tr = Account(broker="TR", account_id="manual-tr", name="TR", user_id=user.id)
    dg = Account(
        broker="DEGIRO",
        account_id="manual-dg",
        name="DEGIRO",
        user_id=user.id,
    )
    db.add_all([tr, dg])
    db.commit()
    yield db, user, tr, dg
    db.close()


def _create(
    db,
    user,
    account: Account,
    tx_type: str,
    trade_date: date,
    price: str,
    *,
    fees: str = "0",
):
    return create_transaction(
        TransactionCreate(
            account_id=account.id,
            type=tx_type,
            trade_date=trade_date,
            isin="US0000000501",
            name="Manual stock",
            quantity=Decimal("10"),
            price=Decimal(price),
            currency="USD",
            exchange_rate=Decimal("0.9"),
            fees=Decimal(fees),
        ),
        db,
        user,
    )


def test_manual_buy_and_sell_use_directional_fee_semantics(context):
    db, user, tr, _ = context

    buy = _create(db, user, tr, "BUY", date(2024, 1, 1), "100", fees="10")
    sell = _create(db, user, tr, "SELL", date(2024, 6, 1), "120", fees="10")

    assert buy.net_amount_eur == Decimal("909")
    assert sell.net_amount_eur == Decimal("1071")

    updated_buy = update_transaction(
        buy.id,
        TransactionUpdate(fees=Decimal("20")),
        db,
        user,
    )
    assert updated_buy.net_amount_eur == Decimal("918")

    updated = update_transaction(
        sell.id,
        TransactionUpdate(fees=Decimal("20")),
        db,
        user,
    )
    assert updated.net_amount_eur == Decimal("1062")


def test_historical_manual_edit_recalculates_later_fifo(context):
    db, user, tr, dg = context
    old_buy = _create(db, user, tr, "BUY", date(2023, 1, 1), "50")
    _create(db, user, dg, "BUY", date(2023, 6, 1), "70")
    _create(db, user, dg, "SELL", date(2025, 6, 1), "80")

    assert db.query(FIFOAdjustment).one().adjustment_eur == Decimal("270")

    update_transaction(
        old_buy.id,
        TransactionUpdate(price=Decimal("60")),
        db,
        user,
    )

    assert db.query(FIFOAdjustment).one().adjustment_eur == Decimal("180")


def test_deleting_last_manual_sale_clears_fifo_rows(context):
    db, user, tr, dg = context
    _create(db, user, tr, "BUY", date(2023, 1, 1), "50")
    _create(db, user, dg, "BUY", date(2023, 6, 1), "70")
    sale = _create(db, user, dg, "SELL", date(2025, 6, 1), "80")
    assert db.query(CrossBrokerLot).count() == 1
    assert db.query(FIFOAdjustment).count() == 1

    delete_transaction(sale.id, db, user)

    assert db.query(CrossBrokerLot).count() == 0
    assert db.query(FIFOAdjustment).count() == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Decimal("0")),
        ("price", Decimal("-1")),
        ("exchange_rate", Decimal("0")),
        ("fees", Decimal("-1")),
        ("withholding_tax", Decimal("-1")),
    ],
)
def test_manual_create_rejects_invalid_financial_values(field, value):
    payload = {
        "account_id": 1,
        "type": "BUY",
        "trade_date": date(2024, 1, 1),
        "quantity": Decimal("1"),
        "price": Decimal("1"),
        "exchange_rate": Decimal("1"),
        "fees": Decimal("0"),
        "withholding_tax": Decimal("0"),
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        TransactionCreate(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Decimal("0")),
        ("price", Decimal("-1")),
        ("fees", Decimal("-1")),
    ],
)
def test_manual_update_rejects_invalid_financial_values(field, value):
    with pytest.raises(ValidationError):
        TransactionUpdate(**{field: value})
