"""Yield-on-cost must read the same open lots as the portfolio page.

``/charts/dividend-yield`` used to run its own FIFO per ISIN over BUY/SELL rows,
pooling every account into one queue and ignoring snapshots. After an ISIN
change or a sale in a second account it reported a quantity and cost the
portfolio page did not, so the dashboard's yield-on-cost and the portfolio's
cost for the same holding could not both be right. It now takes quantity and
cost from ``portfolio_service.get_open_positions``; these tests pin agreement
on the two shapes where the old path diverged.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import charts
from backend.api.schemas import DividendYieldOut
from backend.models import (
    Account,
    Base,
    Broker,
    ImportRecord,
    PortfolioHolding,
    Transaction,
    TransactionType,
    User,
)
from backend.services import portfolio_service

AENA_OLD = "ES0105046009"  # pre-split ISIN, curated to AENA.MC
AENA_NEW = "ES0105046017"  # post-split ISIN (2025), curated to AENA.MC


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user(db):
    u = User(email="yield@example.com", name="Yield")
    db.add(u)
    db.flush()
    return u


def _account(db, user, name: str) -> Account:
    account = Account(user_id=user.id, broker=Broker.ING.value, account_id=name, name=name)
    db.add(account)
    db.flush()
    return account


def _tx(db, account, tx_type, trade_date, isin, quantity, net_eur, *, price="1"):
    db.add(Transaction(
        account_id=account.id,
        type=tx_type.value,
        trade_date=trade_date,
        isin=isin,
        ticker=None,
        name="Asset",
        country="España",
        quantity=Decimal(quantity),
        price=Decimal(price),
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=abs(Decimal(net_eur)),
        fees=Decimal("0"),
        withholding_tax=Decimal("0"),
        net_amount_eur=Decimal(net_eur),
    ))


def _rows(db, user) -> list[dict]:
    rows = charts.dividend_yield(db=db, user=user, fiscal_year=None)
    for row in rows:
        DividendYieldOut.model_validate(row)
    return rows


def test_isin_change_split_agrees_with_the_portfolio_page(db, user):
    """AENA's 2025 split: 10 shares under the old ISIN, 100 held under the new.

    The broker never records the exchange, so the ledger has a buy of the old
    ISIN and a complete 2025 snapshot of the new one. The old path left the old
    ISIN open and merged both by ticker: 110 shares at the old cost. The
    portfolio page closes the old ISIN (absent from a complete snapshot) and
    seeds the new one with unknown cost. The dashboard must say the same.
    """
    ing = _account(db, user, "ing")
    _tx(db, ing, TransactionType.BUY, date(2020, 5, 4), AENA_OLD, "10", "1295", price="129.5")
    _tx(db, ing, TransactionType.DIVIDEND, date(2021, 6, 1), AENA_OLD, "10", "40")
    _tx(db, ing, TransactionType.DIVIDEND, date(2025, 6, 1), AENA_NEW, "100", "90")
    record = ImportRecord(
        account_id=ing.id, filename="ing-2025.pdf", file_hash="a" * 64,
        broker=Broker.ING.value, fiscal_year=2025, record_count=0,
        portfolio_snapshot_complete=True,
    )
    db.add(record)
    db.flush()
    db.add(PortfolioHolding(
        import_id=record.id, account_id=ing.id, fiscal_year=2025, broker=Broker.ING.value,
        isin=AENA_NEW, name="AENA", country="España", currency="EUR",
        quantity=Decimal("100"), price=Decimal("20"), value_eur=Decimal("2000"),
    ))
    db.commit()

    portfolio = portfolio_service.get_open_positions(db, user.id, skip_prices=True)
    [held] = [p for p in portfolio if p.isin in (AENA_OLD, AENA_NEW)]
    assert (held.isin, held.quantity, held.total_cost_eur) == (AENA_NEW, Decimal("100"), None)

    [row] = _rows(db, user)
    assert Decimal(row["qty_remaining"]) == held.quantity
    assert row["total_invested"] is None
    assert row["yield_on_cost"] is None
    # Valued at the snapshot's EUR price: nothing has priced the new ISIN yet.
    assert Decimal(row["current_value"]) == Decimal("2000.00")
    assert Decimal(row["total_dividends"]) == Decimal("130")


def test_sale_in_one_account_does_not_consume_another_accounts_lot(db, user):
    """One global FIFO queue let account B's sale eat account A's cheaper lot."""
    isin = "US0000000001"
    a = _account(db, user, "a")
    b = _account(db, user, "b")
    _tx(db, a, TransactionType.BUY, date(2023, 1, 2), isin, "10", "1000")
    _tx(db, b, TransactionType.BUY, date(2023, 2, 1), isin, "10", "2000")
    _tx(db, b, TransactionType.SELL, date(2023, 6, 1), isin, "10", "2500")
    _tx(db, a, TransactionType.DIVIDEND, date(2023, 9, 1), isin, "10", "50")
    db.commit()

    [held] = portfolio_service.get_open_positions(db, user.id, skip_prices=True)
    assert (held.quantity, held.total_cost_eur) == (Decimal("10"), Decimal("1000"))

    [row] = _rows(db, user)
    assert Decimal(row["qty_remaining"]) == held.quantity
    assert Decimal(row["total_invested"]) == held.total_cost_eur
    assert Decimal(row["yield_on_cost"]) == Decimal("5.00")


def test_closed_position_keeps_zero_cost_not_unknown(db, user):
    """Nothing held is a known zero, distinct from an unknown basis."""
    isin = "US0000000002"
    a = _account(db, user, "a")
    _tx(db, a, TransactionType.BUY, date(2023, 1, 2), isin, "10", "1000")
    _tx(db, a, TransactionType.DIVIDEND, date(2023, 3, 1), isin, "10", "20")
    _tx(db, a, TransactionType.SELL, date(2023, 6, 1), isin, "10", "1200")
    db.commit()

    [row] = _rows(db, user)
    assert Decimal(row["qty_remaining"]) == 0
    assert row["total_invested"] is not None and Decimal(row["total_invested"]) == 0
    assert row["yield_on_cost"] is not None and Decimal(row["yield_on_cost"]) == 0
    assert Decimal(row["current_value"]) == 0
