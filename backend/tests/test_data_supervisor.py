"""Multi-user isolation regressions for the data supervisor."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Account,
    Base,
    DataIssue,
    ImportRecord,
    PortfolioHolding,
    Transaction,
    TransactionType,
    User,
)
from backend.services import data_supervisor


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _owner(db, email: str, account_ref: str):
    user = User(email=email, name=email, password_hash="x")
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id=account_ref, name=account_ref, user_id=user.id)
    db.add(account)
    db.flush()
    record = ImportRecord(
        account_id=account.id,
        filename=f"{account_ref}.pdf",
        file_hash=f"hash-{account_ref}",
        broker="TR",
        fiscal_year=2024,
        record_count=1,
    )
    db.add(record)
    db.flush()
    return user, account, record


def _transaction(
    db,
    account: Account,
    record: ImportRecord,
    tx_type: str,
    isin: str,
    *,
    quantity: str = "1",
    price: str = "10",
    trade_date: date = date(2024, 1, 10),
):
    tx = Transaction(
        account_id=account.id,
        import_id=record.id,
        type=tx_type,
        trade_date=trade_date,
        isin=isin,
        name=f"Asset {isin}",
        quantity=Decimal(quantity),
        price=Decimal(price),
        gross_amount=Decimal(quantity) * Decimal(price),
        fees=Decimal("0"),
        net_amount_eur=Decimal(quantity) * Decimal(price),
    )
    db.add(tx)
    db.flush()
    return tx


def test_import_run_derives_owner_for_cross_dataset_checks(db, monkeypatch):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    user2, account2, import2 = _owner(db, "two@example.com", "two")
    isin = "US0000000001"
    _transaction(db, account1, import1, TransactionType.BUY.value, isin)
    _transaction(db, account2, import2, TransactionType.DIVIDEND.value, isin)

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(data_supervisor, "_get_splits_from_yfinance", lambda _ticker: [])

    issues1 = data_supervisor.run_checks(db, import_id=import1.id)
    issues2 = data_supervisor.run_checks(db, import_id=import2.id)

    assert not any(issue.issue_type == "missing_buy" for issue in issues1)
    assert any(issue.issue_type == "missing_buy" and issue.isin == isin for issue in issues2)
    assert user1.id != user2.id


def test_run_checks_rejects_missing_or_mismatched_owner_scope(db):
    user1, _, import1 = _owner(db, "one@example.com", "one")
    user2, _, _ = _owner(db, "two@example.com", "two")

    with pytest.raises(ValueError, match="requires import_id or user_id"):
        data_supervisor.run_checks(db)
    with pytest.raises(ValueError, match=f"does not belong to user {user2.id}"):
        data_supervisor.run_checks(db, import_id=import1.id, user_id=user2.id)
    assert user1.id != user2.id


def test_issue_deduplication_is_scoped_to_owner(db, monkeypatch):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    _, _, import2 = _owner(db, "two@example.com", "two")
    isin = "US0000000002"
    _transaction(db, account1, import1, TransactionType.DIVIDEND.value, isin)
    db.add(
        DataIssue(
            import_id=import2.id,
            issue_type="missing_buy",
            severity="warning",
            isin=isin,
            name="Other user's issue",
            description="Existing issue for another owner",
            status="needs_input",
        )
    )
    db.flush()

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(data_supervisor, "_get_splits_from_yfinance", lambda _ticker: [])

    issues = data_supervisor.run_checks(db, import_id=import1.id, user_id=user1.id)

    assert any(issue.issue_type == "missing_buy" and issue.isin == isin for issue in issues)


def test_full_audit_issues_keep_owner_and_deduplicate(db, monkeypatch):
    user, account, record = _owner(db, "one@example.com", "one")
    isin = "US0000000009"
    _transaction(db, account, record, TransactionType.DIVIDEND.value, isin)

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(data_supervisor, "_get_splits_from_yfinance", lambda _ticker: [])

    first = data_supervisor.run_checks(db, user_id=user.id)
    second = data_supervisor.run_checks(db, user_id=user.id)

    missing = [issue for issue in first if issue.issue_type == "missing_buy"]
    assert len(missing) == 1
    assert missing[0].import_id is None
    assert missing[0].user_id == user.id
    assert not any(issue.issue_type == "missing_buy" for issue in second)


def test_full_audit_does_not_include_other_users_active_isins(db, monkeypatch):
    user1, _, _ = _owner(db, "one@example.com", "one")
    _, account2, import2 = _owner(db, "two@example.com", "two")
    other_buy_isin = "US0000000010"
    other_holding_isin = "US0000000011"
    _transaction(db, account2, import2, TransactionType.BUY.value, other_buy_isin)
    db.add(
        PortfolioHolding(
            import_id=import2.id,
            account_id=account2.id,
            fiscal_year=2024,
            broker="TR",
            isin=other_holding_isin,
            name="Other holding",
            currency="EUR",
            quantity=Decimal("1"),
            price=Decimal("10"),
            value_eur=Decimal("10"),
        )
    )
    db.flush()

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(data_supervisor, "_get_splits_from_yfinance", lambda _ticker: [])

    issues = data_supervisor.run_checks(db, user_id=user1.id)

    assert all(issue.isin not in {other_buy_isin, other_holding_isin} for issue in issues)


def test_auto_split_only_adjusts_transactions_owned_by_user(db, monkeypatch):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    _, account2, import2 = _owner(db, "two@example.com", "two")
    isin = "ES0130960018"
    tx1 = _transaction(
        db,
        account1,
        import1,
        TransactionType.BUY.value,
        isin,
        quantity="10",
        trade_date=date(2020, 1, 10),
    )
    tx2 = _transaction(
        db,
        account2,
        import2,
        TransactionType.BUY.value,
        isin,
        quantity="7",
        trade_date=date(2020, 1, 10),
    )
    db.add(
        PortfolioHolding(
            import_id=import1.id,
            account_id=account1.id,
            fiscal_year=2024,
            broker="TR",
            isin=isin,
            name="Enagas",
            currency="EUR",
            quantity=Decimal("20"),
            price=Decimal("12"),
            value_eur=Decimal("240"),
        )
    )
    db.flush()
    monkeypatch.setattr(
        data_supervisor,
        "_get_splits_from_yfinance",
        lambda _ticker: [(date(2020, 6, 1), Decimal("2"))],
    )

    issues = data_supervisor._check_split_candidates(db, import1.id, user1.id)

    db.refresh(tx1)
    db.refresh(tx2)
    assert any(issue.status == "auto_resolved" for issue in issues)
    assert tx1.quantity == Decimal("20")
    assert tx1.price == Decimal("5")
    assert tx2.quantity == Decimal("7")
    assert tx2.price == Decimal("10")
