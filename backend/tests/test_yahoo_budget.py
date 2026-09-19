"""The Yahoo wall-clock budget, and the loops it is there to stop.

These tests deliberately do not assert "a timeout is configured somewhere".
That assertion would pass today and still leave production hanging: yfinance
takes a `timeout` argument and ignores it for the leg that matters — measured,
`yf.download(..., timeout=3)` needs 30s against an endpoint that accepts the
connection and never answers, because `YfData._make_request` fetches the
cookie/crumb with a hardcoded 30s default first. `yf.Ticker(...).info` takes no
timeout at all.

So what is pinned here is the property that actually bounds the work: once the
allowance is gone, the loop stops calling Yahoo. Delete the budget check and
these fail.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Account,
    Base,
    ImportRecord,
    SplitHistoryCache,
    Transaction,
    TransactionType,
    User,
)
from backend.services import data_supervisor, prices, split_history, yahoo_budget
from backend.services.yahoo_budget import GEO_CYCLE_SECONDS, IMPORT_SECONDS, Budget

# What one stalled Yahoo call costs, measured against a socket that accepts and
# never answers. The number is the whole reason a budget exists.
STALLED_CALL = 30.0


class _Clock:
    """Stand-in for `time`, so a test can burn an hour without sleeping."""

    def __init__(self, start: float = 1000.0):
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(yahoo_budget, "time", c)
    return c


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── the budget itself ────────────────────────────────────────────────


def test_budget_is_unspent_until_the_deadline_passes(clock):
    budget = Budget(60.0, "test")
    assert not budget.spent()
    clock.advance(59.9)
    assert not budget.spent()
    clock.advance(0.1)
    assert budget.spent()


def test_budget_stays_spent(clock):
    budget = Budget(10.0, "test")
    clock.advance(11)
    assert budget.spent()
    assert budget.spent()


# ── supervisor: one Yahoo lookup per unresolved ISIN ─────────────────


def _owner(db):
    user = User(email="a@example.com", name="a", password_hash="x")
    db.add(user)
    db.flush()
    account = Account(broker="TR", account_id="a", name="a", user_id=user.id)
    db.add(account)
    db.flush()
    record = ImportRecord(
        account_id=account.id,
        filename="a.pdf",
        file_hash="hash-a",
        broker="TR",
        fiscal_year=2024,
        record_count=1,
    )
    db.add(record)
    db.flush()
    return account, record


def _buy(db, account, record, isin):
    db.add(
        Transaction(
            account_id=account.id,
            import_id=record.id,
            type=TransactionType.BUY.value,
            trade_date=date(2024, 1, 10),
            isin=isin,
            name=f"Asset {isin}",
            quantity=Decimal("1"),
            price=Decimal("10"),
            gross_amount=Decimal("10"),
            fees=Decimal("0"),
            net_amount_eur=Decimal("10"),
        )
    )
    db.flush()


def test_supervisor_stops_resolving_isins_once_the_budget_is_spent(db, clock, monkeypatch):
    """The 45-minute import: ~90 unresolved ISINs, 30s of stalled Yahoo each.

    Ten ISINs against a stalled Yahoo is five minutes of import without a
    budget. With one, the run gives up after the allowance and flags the rest.
    """
    account, record = _owner(db)
    isins = [f"US000000{i:04d}" for i in range(10)]
    for isin in isins:
        _buy(db, account, record, isin)

    looked_up: list[str] = []

    def _stalled(isin: str):
        looked_up.append(isin)
        clock.advance(STALLED_CALL)
        return None

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", _stalled)
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])

    issues = data_supervisor.run_checks(db, import_id=record.id)

    # 60s of allowance buys exactly two 30s lookups; the other eight are skipped.
    assert len(looked_up) == int(IMPORT_SECONDS // STALLED_CALL) == 2

    # Skipping is not silence: every ISIN still gets flagged for the user, which
    # is what an unresolvable ISIN already produced before the budget existed.
    flagged = {i.isin for i in issues if i.issue_type == "missing_ticker"}
    assert flagged == set(isins)


def test_supervisor_resolves_everything_when_yahoo_is_healthy(db, clock, monkeypatch):
    """The budget must not bite on the happy path — ~1.5s per healthy lookup."""
    account, record = _owner(db)
    isins = [f"US000000{i:04d}" for i in range(10)]
    for isin in isins:
        _buy(db, account, record, isin)

    looked_up: list[str] = []

    def _healthy(isin: str):
        looked_up.append(isin)
        clock.advance(1.5)
        return None

    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", _healthy)
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])

    data_supervisor.run_checks(db, import_id=record.id)

    assert looked_up == isins


# ── split history: one Yahoo lookup per uncached ticker ──────────────


def test_split_prefetch_stops_fetching_once_the_budget_is_spent(db, clock, monkeypatch):
    fetched: list[str] = []

    def _stalled(ticker: str):
        fetched.append(ticker)
        clock.advance(STALLED_CALL)
        return []

    monkeypatch.setattr(split_history, "_fetch", _stalled)

    budget = Budget(IMPORT_SECONDS, "test")
    tickers = [f"T{i}" for i in range(10)]
    out = split_history.prefetch(db, tickers, budget)

    assert len(fetched) == 2
    # Every ticker still gets an answer, so the caller's loop is unaffected.
    assert set(out) == set(tickers)


def test_a_skipped_split_lookup_is_never_cached(db, clock, monkeypatch):
    """A skipped lookup must not pin "never split" on a security for 30 days.

    Same reasoning as a failed fetch: nothing is written, so the next import
    retries. Caching the skip would make the supervisor blind to a real split.
    """
    monkeypatch.setattr(split_history, "_fetch", lambda _t: pytest.fail("budget was spent"))

    budget = Budget(IMPORT_SECONDS, "test")
    clock.advance(IMPORT_SECONDS + 1)

    assert split_history.prefetch(db, ["AAPL"], budget) == {"AAPL": []}
    assert db.query(SplitHistoryCache).count() == 0


def test_a_spent_budget_still_serves_a_stale_split_row(db, clock, monkeypatch):
    """Stale knowledge beats no knowledge, exactly as on a Yahoo outage."""
    stale = datetime.now(timezone.utc) - split_history.TTL - timedelta(days=1)
    db.add(
        SplitHistoryCache(
            ticker="AAPL",
            splits=split_history._encode([(date(2020, 8, 31), Decimal("4"))]),
            fetched_at=stale.replace(tzinfo=None),
        )
    )
    db.flush()
    monkeypatch.setattr(split_history, "_fetch", lambda _t: pytest.fail("budget was spent"))

    budget = Budget(IMPORT_SECONDS, "test")
    clock.advance(IMPORT_SECONDS + 1)

    assert split_history.prefetch(db, ["AAPL"], budget) == {
        "AAPL": [(date(2020, 8, 31), Decimal("4"))]
    }


# ── prices: one stalled batch is worse than one stalled request ──────


@pytest.fixture
def yahoo(monkeypatch):
    """Record each yf.download batch; prices resolve to 1.0 per symbol."""
    calls: list[list[str]] = []

    def _download(tickers, **kwargs):
        calls.append(list(tickers))
        return object()

    import yfinance

    monkeypatch.setattr(yfinance, "download", _download)
    monkeypatch.setattr(prices, "_last_closes", lambda _d, group: {t: 1.0 for t in group})
    return calls


def test_without_a_budget_prices_are_one_batch(yahoo):
    """The portfolio path must keep its single round trip.

    Chunking exists to give a budget somewhere to look. With no budget there is
    nothing to check between chunks, so splitting would only add round trips to a
    request a user is waiting on.
    """
    out = prices._fetch_yahoo_prices([f"S{i}" for i in range(10)])

    assert len(yahoo) == 1
    assert len(out) == 10


def test_with_a_budget_prices_are_chunked(clock, yahoo):
    budget = Budget(GEO_CYCLE_SECONDS, "test")
    out = prices._fetch_yahoo_prices([f"S{i}" for i in range(10)], budget=budget)

    assert [len(c) for c in yahoo] == [3, 3, 3, 1]
    assert len(out) == 10


def test_chunks_stop_once_the_budget_is_spent(clock, monkeypatch):
    """A stalled chunk costs ~120s, so 120s of allowance buys one, then stops."""
    import yfinance

    calls: list[list[str]] = []

    def _stalled_download(tickers, **kwargs):
        calls.append(list(tickers))
        clock.advance(120.0)
        return object()

    monkeypatch.setattr(yfinance, "download", _stalled_download)
    monkeypatch.setattr(prices, "_last_closes", lambda _d, g: {t: 1.0 for t in g})

    out = prices._fetch_yahoo_prices(
        [f"S{i}" for i in range(21)], budget=Budget(GEO_CYCLE_SECONDS, "test")
    )

    # One chunk fits the allowance; the remaining six are skipped, not attempted.
    assert len(calls) == 1
    assert len(out) == 3


def test_a_failing_chunk_does_not_drop_the_others(clock, monkeypatch):
    """A batch used to return {} on any exception, losing every symbol in it."""
    import yfinance

    def _download(tickers, **kwargs):
        if "S3" in list(tickers):
            raise RuntimeError("Yahoo said no")
        return object()

    monkeypatch.setattr(yfinance, "download", _download)
    monkeypatch.setattr(prices, "_last_closes", lambda _d, g: {t: 1.0 for t in g})

    out = prices._fetch_yahoo_prices(
        [f"S{i}" for i in range(6)], budget=Budget(GEO_CYCLE_SECONDS, "test")
    )

    assert set(out) == {"S0", "S1", "S2"}


def test_a_cycle_budget_is_shared_not_renewed(clock, yahoo):
    """Both geo callers pass the cycle's budget, so 120s means 120s per cycle."""
    budget = Budget(GEO_CYCLE_SECONDS, "cycle")
    clock.advance(GEO_CYCLE_SECONDS + 1)

    assert prices.fetch_ticker_prices(["AAPL"], budget) == {}
    assert yahoo == []
