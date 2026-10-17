"""The data supervisor and the issue resolver must persist what they resolve.

`_check_missing_ticker` already asked yfinance for a ticker and already knew the
answer — it just wrote it into a DataIssue description and dropped it. These
tests pin the two ends of the loop: the supervisor stores what it learns, and a
`missing_ticker` issue can be resolved by hand instead of only dismissed.
"""

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
    TickerMap,
    Transaction,
    TransactionType,
    User,
)
from backend.services import data_supervisor, issue_resolver, split_history, ticker_map

UNKNOWN_ISIN = "US0378331005"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _owner(db):
    user = User(email="a@b.c", name="a", password_hash="x")
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id="acc", name="acc", user_id=user.id)
    db.add(account)
    db.flush()
    record = ImportRecord(
        account_id=account.id, filename="f.pdf", file_hash="h",
        broker="TR", fiscal_year=2024, record_count=1,
    )
    db.add(record)
    db.flush()
    return user, account, record


def _holding(db, account, record, isin, name="Apple Inc"):
    db.add(PortfolioHolding(
        account_id=account.id, import_id=record.id, broker="TR", isin=isin, name=name,
        quantity=Decimal("10"), price=Decimal("100"), value_eur=Decimal("1000"),
        fiscal_year=2024,
    ))
    db.add(Transaction(
        account_id=account.id, import_id=record.id, type=TransactionType.BUY.value,
        trade_date=date(2024, 1, 2), isin=isin, name=name,
        quantity=Decimal("10"), price=Decimal("100"),
        gross_amount=Decimal("1000"), net_amount_eur=Decimal("1000"),
    ))
    db.flush()


# ── the supervisor remembers ─────────────────────────────────────────


def test_a_resolved_ticker_is_persisted(db, monkeypatch):
    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN)
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: "AAPL")

    issues = data_supervisor._check_missing_ticker(db, record.id, user.id)
    db.flush()

    assert [i.status for i in issues] == ["auto_resolved"]
    row = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).one()
    assert row.yahoo_ticker == "AAPL"
    assert row.source == ticker_map.YFINANCE
    assert row.name == "Apple Inc"


def test_the_lookup_is_not_repeated_on_the_next_run(db, monkeypatch):
    """The expensive part is the yfinance call, once per unknown ISIN per run."""
    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN)
    calls: list[str] = []

    def _resolve(isin):
        calls.append(isin)
        return "AAPL"

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", _resolve)

    data_supervisor._check_missing_ticker(db, record.id, user.id)
    db.flush()
    second = data_supervisor._check_missing_ticker(db, record.id, user.id)

    assert calls == [UNKNOWN_ISIN]
    assert second == []


def test_an_unresolvable_isin_is_not_persisted(db, monkeypatch):
    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN)
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)

    issues = data_supervisor._check_missing_ticker(db, record.id, user.id)
    db.flush()

    assert [i.status for i in issues] == ["needs_input"]
    assert db.query(TickerMap).count() == 0


def test_the_supervisor_does_not_learn_a_listing_valued_in_the_wrong_currency(db, monkeypatch):
    """MLPD.L is a USD line on LSE; prices.py would divide it by 100 as pence."""
    import yfinance

    class _Ticker:
        def __init__(self, _isin):
            self.info = {"symbol": "MLPD.L", "currency": "USD", "regularMarketPrice": 55.7}

    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN, name="US Energy Infrastructure MLP")
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    issues = data_supervisor._check_missing_ticker(db, record.id, user.id)
    db.flush()

    assert [i.status for i in issues] == ["needs_input"]
    assert db.query(TickerMap).count() == 0


def test_split_detection_sees_a_learned_ticker(db, monkeypatch):
    """This check walked the curated map only, so learned ISINs were invisible."""
    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN)
    seen: list[str] = []
    monkeypatch.setattr(split_history, "_fetch",
                        lambda ticker: seen.append(ticker) or [])

    data_supervisor._check_split_candidates(db, record.id, user.id)
    assert seen == []

    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")
    db.flush()
    data_supervisor._check_split_candidates(db, record.id, user.id)

    assert seen == ["AAPL"]


# ── the resolver closes the loop ─────────────────────────────────────


def _ticker_issue(db, user, record, status="needs_input"):
    issue = DataIssue(
        import_id=record.id, user_id=user.id, issue_type="missing_ticker",
        severity="warning", isin=UNKNOWN_ISIN, name="Apple Inc", status=status,
        description="sin ticker",
    )
    db.add(issue)
    db.flush()
    return issue


def test_setting_a_ticker_by_hand_stores_it_as_manual(db):
    user, account, record = _owner(db)
    issue = _ticker_issue(db, user, record)

    issue_resolver.resolve_set_ticker(db, issue, "aapl")
    db.flush()

    row = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).one()
    assert row.yahoo_ticker == "AAPL"       # normalised
    assert row.source == ticker_map.MANUAL
    assert issue.status == "resolved"


def test_a_market_suffix_is_accepted(db):
    user, account, record = _owner(db)
    issue = _ticker_issue(db, user, record)

    issue_resolver.resolve_set_ticker(db, issue, " san.mc ")
    db.flush()

    assert db.query(TickerMap).one().yahoo_ticker == "SAN.MC"


@pytest.mark.parametrize("bad", ["", "   ", "AA PL", "AAPL;DROP", "<script>", "TOOLONGTICKERNAME"])
def test_a_malformed_ticker_is_rejected(db, bad):
    user, account, record = _owner(db)
    issue = _ticker_issue(db, user, record)

    with pytest.raises(ValueError):
        issue_resolver.resolve_set_ticker(db, issue, bad)
    assert db.query(TickerMap).count() == 0


def test_only_a_missing_ticker_issue_can_set_a_ticker(db):
    user, account, record = _owner(db)
    issue = _ticker_issue(db, user, record)
    issue.issue_type = "zero_price"
    db.flush()

    with pytest.raises(ValueError, match="no permite fijar un ticker"):
        issue_resolver.resolve_set_ticker(db, issue, "AAPL")


def test_an_issue_without_an_isin_is_rejected(db):
    user, account, record = _owner(db)
    issue = _ticker_issue(db, user, record)
    issue.isin = None
    db.flush()

    with pytest.raises(ValueError, match="no tiene ISIN"):
        issue_resolver.resolve_set_ticker(db, issue, "AAPL")


def test_a_hand_set_ticker_survives_the_next_supervisor_run(db, monkeypatch):
    user, account, record = _owner(db)
    _holding(db, account, record, UNKNOWN_ISIN)
    issue_resolver.resolve_set_ticker(db, _ticker_issue(db, user, record), "AAPL.MX")
    db.flush()
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: "AAPL")

    data_supervisor._check_missing_ticker(db, record.id, user.id)
    db.flush()

    assert db.query(TickerMap).one().yahoo_ticker == "AAPL.MX"


# ── the full HTTP path ───────────────────────────────────────────────


def test_set_ticker_over_http():
    """The endpoint offered no way to resolve a missing_ticker issue at all."""
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool

    from backend.api.auth import get_current_user
    from backend.app import app
    from backend.database import get_db

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user, account, record = _owner(s)
        issue = DataIssue(
            import_id=record.id, user_id=user.id, issue_type="missing_ticker",
            severity="warning", isin=UNKNOWN_ISIN, name="Apple Inc",
            status="needs_input", description="sin ticker",
        )
        s.add(issue)
        s.commit()
        uid, issue_id = user.id, issue.id

    def _override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: Session().get(User, uid)
    try:
        client = TestClient(app)

        bad = client.post(f"/api/imports/issues/{issue_id}/resolve",
                          json={"action": "set_ticker", "data": {"ticker": "AA PL"}})
        assert bad.status_code == 400

        missing = client.post(f"/api/imports/issues/{issue_id}/resolve",
                              json={"action": "set_ticker"})
        assert missing.status_code == 400

        ok = client.post(f"/api/imports/issues/{issue_id}/resolve",
                         json={"action": "set_ticker", "data": {"ticker": "aapl"}})
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "resolved"

        with Session() as s:
            row = s.query(TickerMap).one()
            assert (row.isin, row.yahoo_ticker, row.source) == (
                UNKNOWN_ISIN, "AAPL", ticker_map.MANUAL,
            )

        # An already-resolved issue cannot be resolved twice.
        again = client.post(f"/api/imports/issues/{issue_id}/resolve",
                            json={"action": "set_ticker", "data": {"ticker": "MSFT"}})
        assert again.status_code == 400
    finally:
        app.dependency_overrides.clear()
