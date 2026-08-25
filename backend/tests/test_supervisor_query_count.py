"""The supervisor's cost must not scale with portfolio size.

It ran on the import path inside one HTTP request, on a Cloud Run revision with
CPU throttling and a single instance, and did work per position: two aggregate
queries per holding, four more per ISIN missing a buy, and — the expensive part
— one uncached yfinance call per distinct ticker.

These count actual statements rather than asserting a number, so the guard is
"does not grow with N", which is the property that matters.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Account,
    Base,
    ImportRecord,
    PortfolioHolding,
    Transaction,
    TransactionType,
    User,
)
from backend.services import data_supervisor, split_history, ticker_map


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Nothing here may reach Yahoo; a test that does is a test that lies."""
    monkeypatch.setattr(
        split_history, "_fetch",
        lambda ticker: pytest.fail(f"unexpected network fetch for {ticker}"),
    )
    monkeypatch.setattr(
        data_supervisor, "_try_resolve_ticker",
        lambda isin: pytest.fail(f"unexpected ticker lookup for {isin}"),
    )


def _portfolio(n_isins: int, with_buys: bool = True):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="a@b.c", name="a", password_hash="x")
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id="acc", user_id=user.id)
    db.add(account)
    db.flush()
    record = ImportRecord(
        account_id=account.id, filename="f", file_hash="h", broker="TR",
        fiscal_year=2024, record_count=1,
    )
    db.add(record)
    db.flush()

    for i in range(n_isins):
        isin = f"ES{i:010d}"
        db.add(PortfolioHolding(
            account_id=account.id, import_id=record.id, broker="TR", isin=isin,
            name=f"Co {i}", quantity=Decimal("10"), price=Decimal("1"),
            value_eur=Decimal("10"), fiscal_year=2024,
        ))
        db.add(Transaction(
            account_id=account.id, import_id=record.id,
            type=TransactionType.DIVIDEND.value, trade_date=date(2024, 3, 1),
            isin=isin, name=f"Co {i}", quantity=Decimal("0"), price=Decimal("0"),
            gross_amount=Decimal("5"), net_amount_eur=Decimal("5"),
        ))
        if with_buys:
            db.add(Transaction(
                account_id=account.id, import_id=record.id,
                type=TransactionType.BUY.value, trade_date=date(2023, 1, 2),
                isin=isin, name=f"Co {i}", quantity=Decimal("7"), price=Decimal("1"),
                gross_amount=Decimal("7"), net_amount_eur=Decimal("7"),
            ))
        # A known ticker, and a warm split cache, so the run is the steady state
        # rather than the one-off that populates them.
        ticker_map.remember(db, isin, f"T{i}")
    db.commit()
    return db, user, record


def _warm_split_cache(db, n_isins, monkeypatch):
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])
    split_history.prefetch(db, [f"T{i}" for i in range(n_isins)])
    db.commit()
    monkeypatch.setattr(
        split_history, "_fetch",
        lambda ticker: pytest.fail(f"unexpected network fetch for {ticker}"),
    )


def _count_reads(db, user, record) -> int:
    """SELECTs only.

    Writes are proportional to what the run *finds* — a portfolio with 25 real
    problems legitimately writes 25 issue rows. An N+1 is about reads, and reads
    are what must stay flat.
    """
    seen: list[str] = []
    listener = lambda c, cur, s, p, ctx, m: seen.append(s)  # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        data_supervisor.run_checks(db, import_id=record.id, user_id=user.id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    return sum(1 for s in seen if s.lstrip().upper().startswith("SELECT"))


@pytest.mark.parametrize("with_buys", [True, False])
def test_query_count_does_not_grow_with_the_portfolio(monkeypatch, with_buys):
    counts = {}
    for n in (5, 25):
        db, user, record = _portfolio(n, with_buys)
        _warm_split_cache(db, n, monkeypatch)
        counts[n] = _count_reads(db, user, record)
        db.close()

    assert counts[5] == counts[25], (
        f"supervisor reads scale with portfolio size: {counts[5]} SELECTs for 5 ISINs, "
        f"{counts[25]} for 25"
    )


def test_a_warm_run_makes_no_network_calls(monkeypatch):
    """`_no_network` fails the test if anything reaches out; this asserts it runs."""
    db, user, record = _portfolio(25)
    _warm_split_cache(db, 25, monkeypatch)

    issues = data_supervisor.run_checks(db, import_id=record.id, user_id=user.id)

    assert isinstance(issues, list)
    db.close()


def test_split_history_is_fetched_once_per_ticker_then_cached(monkeypatch):
    db, user, record = _portfolio(10)
    fetched: list[str] = []
    monkeypatch.setattr(split_history, "_fetch", lambda t: fetched.append(t) or [])

    data_supervisor.run_checks(db, import_id=record.id, user_id=user.id)
    db.commit()
    first = len(fetched)

    data_supervisor.run_checks(db, import_id=record.id, user_id=user.id)

    assert first == 10, f"expected one fetch per ticker, got {first}"
    assert len(fetched) == 10, "a second run re-fetched what it had already cached"
    db.close()
