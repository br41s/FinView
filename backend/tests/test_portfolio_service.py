"""Regression tests for portfolio quantity, cost, and snapshot reconciliation."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import portfolio as portfolio_api
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
from backend.services import portfolio_service as svc


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, email="portfolio@example.com"))
    session.commit()
    yield session
    session.close()


def _account(db, *, account_id: str = "acct") -> Account:
    account = Account(
        user_id=1,
        broker=Broker.ING.value,
        account_id=account_id,
        name=account_id,
    )
    db.add(account)
    db.flush()
    return account


def _tx(
    db,
    account: Account,
    tx_type: TransactionType,
    trade_date: date,
    quantity: str,
    net_eur: str,
    *,
    isin: str = "ES0000000001",
) -> Transaction:
    tx = Transaction(
        account_id=account.id,
        type=tx_type.value,
        trade_date=trade_date,
        isin=isin,
        ticker="TEST.MC",
        name="Test asset",
        country="España",
        quantity=Decimal(quantity),
        price=Decimal("1"),
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=abs(Decimal(net_eur)),
        fees=Decimal("0"),
        withholding_tax=Decimal("0"),
        net_amount_eur=Decimal(net_eur),
    )
    db.add(tx)
    return tx


def _snapshot_import(
    db, account: Account, year: int, *, complete: bool | None = True
) -> ImportRecord:
    record = ImportRecord(
        account_id=account.id,
        filename=f"snapshot-{year}.pdf",
        file_hash=f"{account.id:02d}{year:062d}"[-64:],
        broker=Broker.ING.value,
        fiscal_year=year,
        record_count=0,
        portfolio_snapshot_complete=complete,
    )
    db.add(record)
    db.flush()
    return record


def _holding(
    db,
    account: Account,
    record: ImportRecord,
    year: int,
    quantity: str,
    *,
    isin: str = "ES0000000001",
) -> None:
    db.add(PortfolioHolding(
        import_id=record.id,
        account_id=account.id,
        fiscal_year=year,
        broker=Broker.ING.value,
        isin=isin,
        name="Test asset",
        country="España",
        currency="EUR",
        quantity=Decimal(quantity),
        price=Decimal("10"),
        value_eur=Decimal(quantity) * Decimal("10"),
    ))


def test_sales_consume_oldest_cost_lot(db):
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "1", "100")
    _tx(db, account, TransactionType.BUY, date(2024, 2, 1), "1", "200")
    _tx(db, account, TransactionType.SELL, date(2024, 3, 1), "1", "300")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("1")
    assert position.total_cost_eur == Decimal("200")
    assert position.avg_cost_eur == Decimal("200")


def test_spinoff_keeps_quantity_but_cost_unknown(db):
    account = _account(db)
    _tx(db, account, TransactionType.SPINOFF, date(2024, 1, 1), "3", "0")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("3")
    assert position.total_cost_eur is None
    assert position.avg_cost_eur is None


def test_spinoff_uses_cost_resolved_by_issue_workflow(db):
    account = _account(db)
    _tx(db, account, TransactionType.SPINOFF, date(2024, 1, 1), "3", "60")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("3")
    assert position.total_cost_eur == Decimal("60")
    assert position.avg_cost_eur == Decimal("20")


def test_empty_isin_never_becomes_a_position(db):
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "1", "100", isin="")
    db.commit()

    assert svc.get_open_positions(db, 1, skip_prices=True) == []


def test_snapshot_mismatch_preserves_post_snapshot_activity(db):
    account = _account(db)
    record = _snapshot_import(db, account, 2023)
    _holding(db, account, record, 2023, "100")
    _tx(db, account, TransactionType.BUY, date(2023, 1, 1), "50", "500")
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "10", "200")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("110")
    assert position.total_cost_eur is None


def test_complete_empty_snapshot_closes_old_position(db):
    account = _account(db)
    old_record = _snapshot_import(db, account, 2023)
    _holding(db, account, old_record, 2023, "10")
    _snapshot_import(db, account, 2024)
    _tx(db, account, TransactionType.BUY, date(2023, 1, 1), "10", "100")
    db.commit()

    assert svc.get_open_positions(db, 1, skip_prices=True) == []


def test_newer_legacy_holding_beats_older_explicit_snapshot(db):
    account = _account(db)
    _snapshot_import(db, account, 2023)
    legacy = ImportRecord(
        account_id=account.id,
        filename="legacy-2024.pdf",
        file_hash="legacy-2024".ljust(64, "0"),
        broker=Broker.ING.value,
        fiscal_year=2024,
        record_count=1,
        portfolio_snapshot_complete=None,
    )
    db.add(legacy)
    db.flush()
    _holding(db, account, legacy, 2024, "7")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("7")
    assert position.total_cost_eur is None


X_ISIN = "ES0000000001"
Y_ISIN = "ES0000000002"


@pytest.mark.parametrize(
    ("complete", "open_isins"),
    [
        (True, {Y_ISIN}),  # a complete snapshot closes what it omits
        (None, {Y_ISIN}),  # legacy rows stay authoritative, unchanged
        (False, {X_ISIN, Y_ISIN}),  # a partial list closes nothing
    ],
    ids=["complete", "legacy", "partial"],
)
def test_only_a_complete_snapshot_closes_an_omitted_position(db, complete, open_isins):
    """A holdings list that covers part of the account (IBKR keeps only
    `Stocks`) used to close every ledger position it did not list: any year
    with rows was authoritative, whatever the marker said."""
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2023, 1, 1), "10", "100", isin=X_ISIN)
    _tx(db, account, TransactionType.BUY, date(2023, 1, 1), "5", "50", isin=Y_ISIN)
    record = _snapshot_import(db, account, 2024, complete=complete)
    _holding(db, account, record, 2024, "5", isin=Y_ISIN)
    db.commit()

    positions = {p.isin: p for p in svc.get_open_positions(db, 1, skip_prices=True)}

    assert set(positions) == open_isins
    if complete is False:
        assert positions[X_ISIN].total_cost_eur == Decimal("100")


def test_partial_snapshot_does_not_rewrite_a_listed_quantity(db):
    """No authority means none: the ledger's quantity and known cost stand."""
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2023, 1, 1), "5", "50")
    record = _snapshot_import(db, account, 2024, complete=False)
    _holding(db, account, record, 2024, "7")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("5")
    assert position.total_cost_eur == Decimal("50")


def test_newer_partial_snapshot_does_not_displace_an_older_complete_one(db):
    """The authoritative year stays the complete one: a newer partial list
    must not move it forward and reopen what the complete year closed."""
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2022, 1, 1), "10", "100", isin=X_ISIN)
    _tx(db, account, TransactionType.BUY, date(2022, 1, 1), "5", "50", isin=Y_ISIN)
    complete = _snapshot_import(db, account, 2023)
    _holding(db, account, complete, 2023, "10", isin=X_ISIN)
    partial = _snapshot_import(db, account, 2024, complete=False)
    _holding(db, account, partial, 2024, "5", isin=Y_ISIN)
    db.commit()

    positions = {p.isin: p for p in svc.get_open_positions(db, 1, skip_prices=True)}

    assert set(positions) == {X_ISIN}
    assert positions[X_ISIN].total_cost_eur == Decimal("100")


def test_purchase_after_empty_snapshot_reopens_with_known_cost(db):
    account = _account(db)
    _snapshot_import(db, account, 2023)
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "2", "240")
    db.commit()

    [position] = svc.get_open_positions(db, 1, skip_prices=True)

    assert position.quantity == Decimal("2")
    assert position.total_cost_eur == Decimal("240")


def test_partial_unknown_cost_contaminates_aggregate_and_summary(db, monkeypatch):
    first = _account(db, account_id="known")
    second = _account(db, account_id="unknown")
    _tx(db, first, TransactionType.BUY, date(2024, 1, 1), "1", "100")
    _tx(
        db,
        second,
        TransactionType.SPINOFF,
        date(2024, 1, 1),
        "1",
        "0",
        isin="ES0000000002",
    )
    db.commit()
    monkeypatch.setattr(
        svc,
        "fetch_and_cache_prices",
        lambda _db, isins: {isin: Decimal("150") for isin in isins},
    )

    summary = svc.get_portfolio_summary(db, 1)

    assert summary["total_market_value"] == 300.0
    assert summary["total_invested"] is None
    assert summary["unrealized_pl"] is None
    assert summary["unrealized_pl_pct"] is None
    assert summary["cost_basis_complete"] is False
    assert summary["valuation_complete"] is True


def test_missing_price_does_not_publish_partial_portfolio_value(db, monkeypatch):
    account = _account(db)
    first_isin = "ES0000000001"
    second_isin = "ES0000000002"
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "1", "100", isin=first_isin)
    _tx(db, account, TransactionType.BUY, date(2024, 1, 2), "1", "200", isin=second_isin)
    db.commit()
    monkeypatch.setattr(
        svc,
        "fetch_and_cache_prices",
        lambda _db, _isins: {first_isin: Decimal("150")},
    )

    summary = svc.get_portfolio_summary(db, 1)

    assert summary["total_invested"] == 300.0
    assert summary["total_market_value"] is None
    assert summary["unrealized_pl"] is None
    assert summary["valuation_complete"] is False


def test_position_detail_keeps_missing_market_value_null(db, monkeypatch):
    account = _account(db)
    _tx(db, account, TransactionType.BUY, date(2024, 1, 1), "1", "100")
    db.commit()
    monkeypatch.setattr(svc, "fetch_and_cache_prices", lambda _db, _isins: {})

    detail = svc.get_position_detail(db, "ES0000000001", 1)

    assert detail is not None
    assert detail["total_cost_eur"] == 100.0
    assert detail["market_value_eur"] is None
    assert detail["unrealized_pl_eur"] is None


def test_zero_values_survive_api_serialization(monkeypatch):
    position = svc.Position(
        isin="ES0000000001",
        ticker="ZERO.MC",
        name="Zero",
        country="España",
        broker=Broker.ING.value,
        account_id=1,
        quantity=Decimal("1"),
        avg_cost_eur=Decimal("0"),
        total_cost_eur=Decimal("0"),
        current_price_eur=Decimal("0"),
        market_value_eur=Decimal("0"),
        unrealized_pl_eur=Decimal("0"),
        unrealized_pl_pct=Decimal("0"),
        weight_pct=Decimal("0"),
    )
    monkeypatch.setattr(portfolio_api, "get_open_positions", lambda *_args, **_kwargs: [position])

    [serialized] = portfolio_api.list_positions(object(), SimpleNamespace(id=1))

    assert serialized["current_price_eur"] == 0.0
    assert serialized["market_value_eur"] == 0.0
    assert serialized["unrealized_pl_eur"] == 0.0
    assert serialized["unrealized_pl_pct"] == 0.0
    assert serialized["weight_pct"] == 0.0
