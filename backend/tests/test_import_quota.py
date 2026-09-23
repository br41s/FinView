"""The monthly import allowance must actually stop an import.

`max_imports_per_month` was defined in PLAN_LIMITS, returned by
/billing/subscription and printed on the billing page — and consulted by
nothing. All six upload endpoints accepted files regardless of plan, so the
number shown to a Free user was decoration.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import Account, Base, ImportRecord, SubscriptionTier, User
from backend.services import billing_service

FREE_LIMIT = billing_service.PLAN_LIMITS[SubscriptionTier.FREE.value]["max_imports_per_month"]


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, email="a@b.c", tier=SubscriptionTier.FREE.value):
    user = User(email=email, name=email, password_hash="x", subscription_tier=tier)
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id=f"acc-{email}", user_id=user.id)
    db.add(account)
    db.flush()
    return user, account


def _imports(db, account, n, when=None):
    when = when or datetime.now(timezone.utc)
    for i in range(n):
        db.add(ImportRecord(
            account_id=account.id, filename=f"f{i}.pdf",
            file_hash=f"{account.id}-{when.isoformat()}-{i}",
            broker="TR", record_count=1, imported_at=when,
        ))
    db.flush()


# ── counting ─────────────────────────────────────────────────────────


def test_a_new_user_has_used_nothing(db):
    user, _ = _user(db)
    assert billing_service.count_imports_this_month(db, user) == 0


def test_this_months_imports_are_counted(db):
    user, account = _user(db)
    _imports(db, account, 3)
    assert billing_service.count_imports_this_month(db, user) == 3


def test_last_months_imports_are_not(db):
    """The allowance resets — otherwise a Free user is blocked forever."""
    user, account = _user(db)
    now = datetime.now(timezone.utc)
    last_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    _imports(db, account, 10, when=last_month)

    assert billing_service.count_imports_this_month(db, user) == 0
    assert billing_service.check_import_limit(db, user) is True


def test_the_first_instant_of_the_month_counts(db):
    user, account = _user(db)
    now = datetime.now(timezone.utc)
    _imports(db, account, 1, when=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    assert billing_service.count_imports_this_month(db, user) == 1


def test_another_users_imports_do_not_count_against_you(db):
    user, _ = _user(db, "mine@x.com")
    _, other_account = _user(db, "theirs@x.com")
    _imports(db, other_account, 20)

    assert billing_service.count_imports_this_month(db, user) == 0
    assert billing_service.check_import_limit(db, user) is True


def test_imports_across_a_users_own_accounts_all_count(db):
    user, account = _user(db)
    second = Account(broker="IBKR", account_id="acc2", user_id=user.id)
    db.add(second)
    db.flush()
    _imports(db, account, 2)
    _imports(db, second, 2)

    assert billing_service.count_imports_this_month(db, user) == 4


# ── the limit ────────────────────────────────────────────────────────


def test_under_the_limit_is_allowed(db):
    user, account = _user(db)
    _imports(db, account, FREE_LIMIT - 1)
    assert billing_service.check_import_limit(db, user) is True


def test_at_the_limit_is_refused(db):
    user, account = _user(db)
    _imports(db, account, FREE_LIMIT)
    assert billing_service.check_import_limit(db, user) is False


def test_a_paid_plan_gets_its_larger_allowance(db):
    user, account = _user(db, tier=SubscriptionTier.PRO.value)
    _imports(db, account, FREE_LIMIT + 1)

    assert billing_service.check_import_limit(db, user) is True


def test_an_unknown_tier_falls_back_to_the_free_allowance(db):
    """Never fail open: a tier we cannot read must not become unlimited."""
    user, account = _user(db, tier="LEGENDARY")
    _imports(db, account, FREE_LIMIT)

    assert billing_service.check_import_limit(db, user) is False


# ── what the user is shown ───────────────────────────────────────────


def test_usage_is_reported_alongside_the_limit(db):
    user, account = _user(db)
    _imports(db, account, 2)

    info = billing_service.get_user_subscription(user, db)
    assert info["imports_this_month"] == 2
    assert info["max_imports_per_month"] == FREE_LIMIT


def test_usage_is_none_without_a_session_rather_than_a_wrong_zero(db):
    user, account = _user(db)
    _imports(db, account, 2)

    assert billing_service.get_user_subscription(user)["imports_this_month"] is None


# ── the endpoints actually refuse ────────────────────────────────────


def test_every_upload_route_is_quota_gated():
    """Structural: a new import endpoint must not silently skip the check.

    The gate is a route dependency rather than a line in each handler body
    precisely so that this is checkable.
    """
    from backend.api import imports as imports_api

    upload_paths = {"/tr", "/degiro", "/ibkr", "/ing", "/bbva", "/etoro"}
    gated = {
        route.path.removeprefix("/imports")
        for route in imports_api.router.routes
        if any(
            getattr(d.dependency, "__name__", "") == "enforce_import_quota"
            for d in getattr(route, "dependencies", [])
        )
    }
    assert upload_paths <= gated, f"ungated upload routes: {upload_paths - gated}"


def _client(db_session_factory, uid):
    from fastapi.testclient import TestClient

    from backend.api.auth import get_current_user
    from backend.app import app
    from backend.database import get_db

    def _override_db():
        s = db_session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: db_session_factory().get(User, uid)
    return TestClient(app), app


@pytest.mark.parametrize("path", ["/tr", "/degiro", "/ibkr", "/ing", "/bbva", "/etoro"])
def test_an_upload_past_the_limit_is_refused_with_403(path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, account = _user(s)
        _imports(s, account, FREE_LIMIT)
        s.commit()
        uid = user.id

    client, app = _client(Session, uid)
    try:
        field = "files" if path == "/bbva" else "file"
        r = client.post(f"/api/imports{path}", files={field: ("x.pdf", b"%PDF-1.4", "application/pdf")})

        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert str(FREE_LIMIT) in detail
    finally:
        app.dependency_overrides.clear()


def test_under_the_limit_the_upload_reaches_the_parser():
    """A 422 means the quota let it through and the (garbage) file failed to parse."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, account = _user(s)
        _imports(s, account, FREE_LIMIT - 1)
        s.commit()
        uid = user.id

    client, app = _client(Session, uid)
    try:
        r = client.post("/api/imports/tr", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
        assert r.status_code == 422, r.text
    finally:
        app.dependency_overrides.clear()


def test_the_subscription_endpoint_reports_usage():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, account = _user(s)
        _imports(s, account, 2)
        s.commit()
        uid = user.id

    client, app = _client(Session, uid)
    try:
        r = client.get("/api/billing/subscription")
        assert r.status_code == 200, r.text
        assert r.json()["imports_this_month"] == 2
    finally:
        app.dependency_overrides.clear()


def test_an_oversized_upload_is_refused_before_parsing(monkeypatch):
    """The routes used to read the whole body into memory with no limit."""
    from backend.api import imports as imports_api

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, _account = _user(s)
        s.commit()
        uid = user.id

    monkeypatch.setattr(imports_api, "MAX_UPLOAD_BYTES", 10)
    client, app = _client(Session, uid)
    try:
        r = client.post("/api/imports/tr", files={"file": ("x.pdf", b"x" * 11, "application/pdf")})
        assert r.status_code == 413, r.text
    finally:
        app.dependency_overrides.clear()


def test_a_failure_after_parsing_is_a_logged_500_not_a_422(monkeypatch, caplog):
    """A FIFO or DB error is ours, not the user's file — it must not read as a bad PDF."""
    from backend.api import imports as imports_api

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, _account = _user(s)
        s.commit()
        uid = user.id

    monkeypatch.setattr(imports_api, "parse_tr_tax_report", lambda _p: object())

    def boom(*_a, **_k):
        raise RuntimeError("fifo exploded")

    monkeypatch.setattr(imports_api, "import_tr_report", boom)
    client, app = _client(Session, uid)
    try:
        with caplog.at_level("ERROR"):
            r = client.post("/api/imports/tr", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
        assert r.status_code == 500, r.text
        assert "fifo exploded" not in r.text
        assert "fifo exploded" in caplog.text
    finally:
        app.dependency_overrides.clear()
