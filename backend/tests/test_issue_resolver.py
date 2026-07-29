"""Multi-user isolation regressions for issue resolution."""

import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.imports import list_issues, resolve_issue
from backend.api.schemas import ResolveIssueRequest
from backend.models import (
    Account,
    Base,
    DataIssue,
    ImportRecord,
    Transaction,
    TransactionType,
    User,
)
from backend.services.issue_resolver import resolve_add_buy, resolve_apply_split, resolve_zero_price


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
    isin: str,
    *,
    quantity: str = "10",
    price: str = "10",
):
    tx = Transaction(
        account_id=account.id,
        import_id=record.id,
        type=TransactionType.BUY.value,
        trade_date=date(2020, 1, 10),
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


def _issue(db, record: ImportRecord, issue_type: str, isin: str, data: dict):
    issue = DataIssue(
        import_id=record.id,
        issue_type=issue_type,
        severity="warning",
        isin=isin,
        name=f"Asset {isin}",
        description="Needs resolution",
        status="needs_input",
        resolution_data=json.dumps(data),
    )
    db.add(issue)
    db.flush()
    return issue


def test_zero_price_rejects_transaction_owned_by_another_user(db):
    _, _, import1 = _owner(db, "one@example.com", "one")
    _, account2, import2 = _owner(db, "two@example.com", "two")
    tx2 = _transaction(db, account2, import2, "US0000000001", price="0")
    issue = _issue(db, import1, "zero_price", tx2.isin, {"tx_id": tx2.id})

    with pytest.raises(ValueError, match=f"Transaction {tx2.id} not found"):
        resolve_zero_price(db, issue, Decimal("12"))

    db.refresh(tx2)
    assert tx2.price == Decimal("0")
    assert issue.status == "needs_input"


def test_legacy_issue_without_direct_owner_is_hidden(db):
    user, _, record = _owner(db, "one@example.com", "one")
    issue = _issue(db, record, "missing_buy", "US0000000007", {})

    assert issue.user_id is None
    assert list_issues(db, user) == []


def test_rejects_issue_whose_direct_owner_disagrees_with_import(db):
    _, _, import1 = _owner(db, "one@example.com", "one")
    user2, account2, import2 = _owner(db, "two@example.com", "two")
    tx2 = _transaction(db, account2, import2, "US0000000008", price="0")
    issue = _issue(db, import1, "zero_price", tx2.isin, {"tx_id": tx2.id})
    issue.user_id = user2.id
    db.flush()

    with pytest.raises(ValueError, match="owner does not match its import"):
        resolve_zero_price(db, issue, Decimal("12"))

    db.refresh(tx2)
    assert tx2.price == Decimal("0")
    assert list_issues(db, user2) == []


def test_importless_zero_price_uses_direct_issue_owner(db):
    user, account, record = _owner(db, "one@example.com", "one")
    tx = _transaction(db, account, record, "US0000000004", price="0")
    issue = DataIssue(
        user_id=user.id,
        issue_type="zero_price",
        severity="warning",
        isin=tx.isin,
        name=tx.name,
        description="Needs resolution",
        status="needs_input",
        resolution_data=json.dumps({"tx_id": tx.id}),
    )
    db.add(issue)
    db.flush()

    resolve_zero_price(db, issue, Decimal("12"))

    assert tx.price == Decimal("12")
    assert issue.status == "resolved"


def test_resolve_endpoint_denies_other_user_before_mutation(db):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    user2, _, _ = _owner(db, "two@example.com", "two")
    tx = _transaction(db, account1, import1, "US0000000012", price="0")
    issue = _issue(db, import1, "zero_price", tx.isin, {"tx_id": tx.id})
    issue.user_id = user1.id
    db.flush()
    request = ResolveIssueRequest(action="set_price", data={"price": "12"})

    with pytest.raises(HTTPException) as exc_info:
        resolve_issue(issue.id, request, db, user2)

    assert exc_info.value.status_code == 404
    assert issue.status == "needs_input"
    assert tx.price == Decimal("0")

    resolved = resolve_issue(issue.id, request, db, user1)
    assert resolved.status == "resolved"
    assert tx.price == Decimal("12")


def test_add_buy_uses_issue_import_account(db):
    _, account1, import1 = _owner(db, "one@example.com", "one")
    _, account2, _ = _owner(db, "two@example.com", "two")
    issue = _issue(
        db,
        import1,
        "missing_buy",
        "US0000000002",
        {"account_id": account2.id},
    )

    resolve_add_buy(db, issue, Decimal("3"), Decimal("4"), date(2023, 5, 1))

    created_id = json.loads(issue.resolution_data)["created_tx_id"]
    created = db.query(Transaction).filter(Transaction.id == created_id).one()
    assert created.account_id == account1.id
    assert created.account_id != account2.id


def test_importless_add_buy_requires_and_uses_unique_owned_account(db):
    user, account, record = _owner(db, "one@example.com", "one")
    isin = "US0000000005"
    _transaction(db, account, record, isin)
    issue = DataIssue(
        user_id=user.id,
        issue_type="missing_buy",
        severity="warning",
        isin=isin,
        name=f"Asset {isin}",
        description="Needs resolution",
        status="needs_input",
    )
    db.add(issue)
    db.flush()

    resolve_add_buy(db, issue, Decimal("3"), Decimal("4"), date(2023, 5, 1))

    created = db.get(Transaction, json.loads(issue.resolution_data)["created_tx_id"])
    assert created.account_id == account.id
    assert created.import_id is None


def test_importless_add_buy_rejects_ambiguous_account(db):
    user, account1, import1 = _owner(db, "one@example.com", "one")
    account2 = Account(broker="TR", account_id="one-b", name="one-b", user_id=user.id)
    db.add(account2)
    db.flush()
    import2 = ImportRecord(
        account_id=account2.id,
        filename="one-b.pdf",
        file_hash="hash-one-b",
        broker="TR",
        fiscal_year=2024,
        record_count=1,
    )
    db.add(import2)
    db.flush()
    isin = "US0000000013"
    _transaction(db, account1, import1, isin)
    _transaction(db, account2, import2, isin)
    issue = DataIssue(
        user_id=user.id,
        issue_type="missing_buy",
        severity="warning",
        isin=isin,
        name=f"Asset {isin}",
        description="Needs resolution",
        status="needs_input",
    )
    db.add(issue)
    db.flush()
    count_before = db.query(Transaction).count()

    with pytest.raises(ValueError, match="no identifica una única cuenta"):
        resolve_add_buy(db, issue, Decimal("3"), Decimal("4"), date(2023, 5, 1))

    assert db.query(Transaction).count() == count_before
    assert issue.status == "needs_input"


def test_importless_add_buy_rejects_missing_account(db):
    user, _, _ = _owner(db, "one@example.com", "one")
    issue = DataIssue(
        user_id=user.id,
        issue_type="missing_buy",
        severity="warning",
        isin="US0000000014",
        name="Unknown asset",
        description="Needs resolution",
        status="needs_input",
    )
    db.add(issue)
    db.flush()

    with pytest.raises(ValueError, match="no identifica una única cuenta"):
        resolve_add_buy(db, issue, Decimal("3"), Decimal("4"), date(2023, 5, 1))

    assert issue.status == "needs_input"


def test_split_adjusts_all_accounts_for_owner_only(db):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    account1b = Account(broker="TR", account_id="one-b", name="one-b", user_id=user1.id)
    db.add(account1b)
    db.flush()
    import1b = ImportRecord(
        account_id=account1b.id,
        filename="one-b.pdf",
        file_hash="hash-one-b",
        broker="TR",
        fiscal_year=2024,
        record_count=1,
    )
    db.add(import1b)
    db.flush()
    _, account2, import2 = _owner(db, "two@example.com", "two")
    isin = "US0000000003"
    tx1a = _transaction(db, account1, import1, isin)
    tx1b = _transaction(db, account1b, import1b, isin, quantity="5", price="20")
    tx2 = _transaction(db, account2, import2, isin, quantity="7", price="30")
    issue = _issue(
        db,
        import1,
        "potential_split",
        isin,
        {"split_date": "2021-01-01", "ratio": "2"},
    )

    resolve_apply_split(db, issue)
    db.flush()

    for tx in (tx1a, tx1b, tx2):
        db.refresh(tx)
    assert (tx1a.quantity, tx1a.price) == (Decimal("20"), Decimal("5"))
    assert (tx1b.quantity, tx1b.price) == (Decimal("10"), Decimal("10"))
    assert (tx2.quantity, tx2.price) == (Decimal("7"), Decimal("30"))
    assert json.loads(issue.resolution_data)["transactions_adjusted"] == 2


def test_importless_split_uses_direct_owner_and_preserves_other_user(db):
    user1, account1, import1 = _owner(db, "one@example.com", "one")
    _, account2, import2 = _owner(db, "two@example.com", "two")
    isin = "US0000000006"
    tx1 = _transaction(db, account1, import1, isin)
    tx2 = _transaction(db, account2, import2, isin)
    issue = DataIssue(
        user_id=user1.id,
        issue_type="potential_split",
        severity="warning",
        isin=isin,
        name=f"Asset {isin}",
        description="Needs resolution",
        status="needs_input",
        resolution_data=json.dumps({"split_date": "2021-01-01", "ratio": "2"}),
    )
    db.add(issue)
    db.flush()

    resolve_apply_split(db, issue)

    assert (tx1.quantity, tx1.price) == (Decimal("20"), Decimal("5"))
    assert (tx2.quantity, tx2.price) == (Decimal("10"), Decimal("10"))
    assert json.loads(issue.resolution_data)["transactions_adjusted"] == 1
