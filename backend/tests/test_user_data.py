"""A user's data can be exported in full and erased in full.

The pricing FAQ promised "puedes eliminar tu cuenta y todos tus datos" for
months while no endpoint did it. These tests pin the promise: every table is
classified, the export reaches every owned table, and a deletion leaves nothing
of the user and everything of everyone else.
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.users import router as users_router
from backend.database import get_db
from backend.models import (
    Account,
    Base,
    FiscalProfile,
    FollowedInstrument,
    ImportRecord,
    Transaction,
    User,
    ZonasClaveWatchlistItem,
)
from backend.services import billing_service, user_data
from backend.services.auth_service import create_access_token, hash_password
from backend.services.rate_limit import limiter

PASSWORD = "correct horse battery staple"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # SQLite ignores foreign keys unless told otherwise; production is Postgres,
    # which does not. Enforce them so a wrong deletion order fails here too.
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(users_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    limiter.reset()
    return TestClient(app)


def _seed(db, email: str) -> User:
    """A user with a row in direct, indirect and nullable-owner tables."""
    user = User(email=email, name="N", password_hash=hash_password(PASSWORD))
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id=f"acc-{email}", user_id=user.id)
    db.add(account)
    db.flush()
    imp = ImportRecord(
        account_id=account.id, filename="report.pdf", file_hash=f"hash-{email}",
        broker="TR", record_count=1,
    )
    db.add(imp)
    db.flush()
    db.add(Transaction(
        account_id=account.id, import_id=imp.id, trade_date=date(2025, 3, 1),
        type="DIVIDEND", isin="ES0113900J37", quantity=Decimal("1"), price=Decimal("10"),
        gross_amount=Decimal("10"), net_amount_eur=Decimal("10"),
    ))
    db.add(FiscalProfile(user_id=user.id, fiscal_year=2025, age=40, disability="general",
                         health_data_consent_at=datetime.now(timezone.utc)))
    db.add(FollowedInstrument(user_id=user.id, ticker="SAN.MC"))
    db.add(ZonasClaveWatchlistItem(user_id=user.id, ticker="ITX.MC"))
    db.commit()
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


def _rows_of(db, user_id: int) -> dict[str, int]:
    counts = {}
    for table in user_data.owned_tables():
        n = db.execute(
            select(func.count()).select_from(table).where(user_data._owned_rows(table, user_id))
        ).scalar()
        if n:
            counts[table.name] = n
    return counts


# ── classification ───────────────────────────────────────────────────


def test_every_table_is_either_user_owned_or_declared_global():
    """A new table must be classified, or a deletion would silently skip it."""
    unclassified = [
        t.name
        for t in Base.metadata.sorted_tables
        if t.name != "users"
        and not user_data.is_user_owned(t)
        and t.name not in user_data.GLOBAL_TABLES
    ]
    assert unclassified == []


def test_no_global_table_carries_a_user_column():
    """Listing a table as global must not be a way to exempt user data."""
    leaking = [
        name for name in user_data.GLOBAL_TABLES
        if "user_id" in Base.metadata.tables[name].c
    ]
    assert leaking == []


def test_global_tables_all_exist():
    """A renamed table must not leave a stale name that matches nothing."""
    assert set(Base.metadata.tables) >= user_data.GLOBAL_TABLES


def test_the_ledger_is_owned_through_its_account():
    """transactions has no user_id: ownership must follow the foreign keys."""
    owned = {t.name for t in user_data.owned_tables()}
    assert {"accounts", "import_records", "transactions", "tax_lots", "cross_broker_lots"} <= owned


# ── export ───────────────────────────────────────────────────────────


def test_export_contains_the_users_rows_and_nobody_elses(db, client):
    ana = _seed(db, "ana@example.com")
    _seed(db, "luis@example.com")

    res = client.get("/api/users/me/export", headers=_auth(ana))

    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    data = json.loads(res.text)
    assert data["users"][0]["email"] == "ana@example.com"
    assert [a["account_id"] for a in data["accounts"]] == ["acc-ana@example.com"]
    assert len(data["transactions"]) == 1
    assert data["fiscal_profiles"][0]["disability"] == "general"
    assert "luis@example.com" not in res.text


def test_export_lists_every_owned_table_even_when_empty(db, client):
    ana = _seed(db, "ana@example.com")

    data = json.loads(client.get("/api/users/me/export", headers=_auth(ana)).text)

    assert set(data) == {"users"} | {t.name for t in user_data.owned_tables()}


def test_export_never_includes_the_password_hash(db, client):
    ana = _seed(db, "ana@example.com")

    res = client.get("/api/users/me/export", headers=_auth(ana))

    assert "password_hash" not in res.text
    assert ana.password_hash not in res.text


def test_export_requires_a_session(client):
    assert client.get("/api/users/me/export").status_code == 401


# ── deletion ─────────────────────────────────────────────────────────


def test_deleting_an_account_leaves_nothing_of_the_user(db, client):
    ana = _seed(db, "ana@example.com")
    ana_id = ana.id
    assert _rows_of(db, ana_id)  # guards the test: there was something to delete

    res = client.post("/api/users/me/delete", json={"password": PASSWORD}, headers=_auth(ana))

    assert res.status_code == 204
    assert _rows_of(db, ana_id) == {}
    assert db.query(User).filter(User.id == ana_id).first() is None


def test_deleting_an_account_leaves_other_users_untouched(db, client):
    ana = _seed(db, "ana@example.com")
    luis = _seed(db, "luis@example.com")
    before = _rows_of(db, luis.id)

    client.post("/api/users/me/delete", json={"password": PASSWORD}, headers=_auth(ana))

    assert _rows_of(db, luis.id) == before
    assert db.query(User).filter(User.id == luis.id).first() is not None


def test_a_wrong_password_deletes_nothing(db, client):
    ana = _seed(db, "ana@example.com")
    before = _rows_of(db, ana.id)

    res = client.post("/api/users/me/delete", json={"password": "wrong"}, headers=_auth(ana))

    assert res.status_code == 403
    assert _rows_of(db, ana.id) == before


def test_the_old_token_stops_working_after_deletion(db, client):
    ana = _seed(db, "ana@example.com")
    headers = _auth(ana)

    client.post("/api/users/me/delete", json={"password": PASSWORD}, headers=headers)

    assert client.get("/api/users/me/export", headers=headers).status_code == 401


def test_deletion_closes_billing_first(db, client, monkeypatch):
    ana = _seed(db, "ana@example.com")
    ana.stripe_customer_id = "cus_123"
    db.commit()
    deleted = []
    monkeypatch.setattr(stripe.Customer, "delete", lambda cid: deleted.append(cid))

    res = client.post("/api/users/me/delete", json={"password": PASSWORD}, headers=_auth(ana))

    assert res.status_code == 204
    assert deleted == ["cus_123"]


def test_a_stripe_failure_aborts_the_deletion(db, client, monkeypatch):
    """Never erase an account whose subscription may still be charging."""
    ana = _seed(db, "ana@example.com")
    ana.stripe_customer_id = "cus_123"
    db.commit()
    before = _rows_of(db, ana.id)

    def boom(_cid):
        raise stripe.APIConnectionError("network down")

    monkeypatch.setattr(stripe.Customer, "delete", boom)

    res = client.post("/api/users/me/delete", json={"password": PASSWORD}, headers=_auth(ana))

    assert res.status_code == 502
    assert _rows_of(db, ana.id) == before
    assert db.query(User).filter(User.email == "ana@example.com").first() is not None


def test_a_customer_already_gone_at_stripe_does_not_block_deletion(db, monkeypatch):
    user = User(email="a@b.c", password_hash="x", stripe_customer_id="cus_gone")

    def missing(_cid):
        raise stripe.InvalidRequestError("No such customer", "id", code="resource_missing")

    monkeypatch.setattr(stripe.Customer, "delete", missing)

    billing_service.delete_stripe_customer(user)  # must not raise


def test_a_user_without_a_stripe_customer_never_calls_stripe(db, monkeypatch):
    user = User(email="a@b.c", password_hash="x")

    def fail(_cid):
        raise AssertionError("Stripe must not be called")

    monkeypatch.setattr(stripe.Customer, "delete", fail)

    billing_service.delete_stripe_customer(user)


# ── terms acceptance ─────────────────────────────────────────────────


def test_accepting_terms_records_version_and_time(db, client):
    ana = _seed(db, "ana@example.com")
    assert ana.terms_version is None

    res = client.post("/api/users/me/accept-terms", headers=_auth(ana))

    assert res.status_code == 200
    assert res.json()["terms_accepted"] is True
    db.refresh(ana)
    assert ana.terms_version is not None
    assert ana.terms_accepted_at is not None


def test_accepting_twice_keeps_the_first_timestamp(db, client):
    ana = _seed(db, "ana@example.com")
    client.post("/api/users/me/accept-terms", headers=_auth(ana))
    db.refresh(ana)
    first = ana.terms_accepted_at

    client.post("/api/users/me/accept-terms", headers=_auth(ana))

    db.refresh(ana)
    assert ana.terms_accepted_at == first
