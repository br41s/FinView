"""Regression tests for the index-friendly year_range filter.

year_range replaced `year_str(col) == str(year)` across the charts/fiscal/
transactions endpoints (perf: the function-wrapped column defeated the date
index). These tests pin the filter semantics — same rows as the old string
comparison, with correct half-open boundaries (Jan 1 in, next Jan 1 out).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from backend.models import Account, Base, Transaction, TransactionType
from backend.services.sql_compat import year_range, year_str


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_tx(db, account_id: int, trade_date: date) -> None:
    db.add(
        Transaction(
            account_id=account_id,
            type=TransactionType.DIVIDEND,
            trade_date=trade_date,
            isin="US0000000001",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_amount=Decimal("1"),
            net_amount_eur=Decimal("1"),
        )
    )


@pytest.fixture
def account_id(db) -> int:
    acct = Account(broker="TR", account_id="test", name="Test")
    db.add(acct)
    db.flush()
    return acct.id


# Dates straddling both ends of fiscal year 2024.
_DATES = [
    date(2023, 12, 31),  # previous year — excluded
    date(2024, 1, 1),  # first day — included
    date(2024, 6, 15),  # mid year — included
    date(2024, 12, 31),  # last day — included
    date(2025, 1, 1),  # next year — excluded
]


def test_year_range_selects_exactly_the_fiscal_year(db, account_id):
    for d in _DATES:
        _add_tx(db, account_id, d)
    db.flush()

    rows = (
        db.query(Transaction.trade_date)
        .filter(year_range(Transaction.trade_date, 2024))
        .all()
    )
    got = sorted(r.trade_date for r in rows)
    assert got == [date(2024, 1, 1), date(2024, 6, 15), date(2024, 12, 31)]


def test_year_range_matches_legacy_year_str(db, account_id):
    """year_range must return the same set as the old year_str comparison."""
    for d in _DATES:
        _add_tx(db, account_id, d)
    db.flush()

    for year in (2023, 2024, 2025):
        legacy = {
            r.trade_date
            for r in db.query(Transaction.trade_date)
            .filter(year_str(Transaction.trade_date) == str(year))
            .all()
        }
        ranged = {
            r.trade_date
            for r in db.query(Transaction.trade_date)
            .filter(year_range(Transaction.trade_date, year))
            .all()
        }
        assert ranged == legacy, f"mismatch for {year}"


def test_year_range_empty_when_no_match(db, account_id):
    _add_tx(db, account_id, date(2024, 6, 15))
    db.flush()
    count = (
        db.query(func.count())
        .select_from(Transaction)
        .filter(year_range(Transaction.trade_date, 2022))
        .scalar()
    )
    assert count == 0
