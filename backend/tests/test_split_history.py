"""Tests for the split-history cache.

The distinction that carries the weight here is empty-vs-failed. Most tickers
have genuinely never split, so an empty list is a real answer worth caching. A
Yahoo outage is not — caching it would pin "never split" on a real security for
a month, and the supervisor would then miss the split it exists to catch.
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, SplitHistoryCache
from backend.services import split_history

SPLIT = [(date(2020, 6, 1), Decimal("4"))]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _fetches(monkeypatch, answer):
    calls: list[str] = []

    def _fetch(ticker):
        calls.append(ticker)
        return answer

    monkeypatch.setattr(split_history, "_fetch", _fetch)
    return calls


def _row(db, ticker):
    return db.query(SplitHistoryCache).filter(SplitHistoryCache.ticker == ticker).one_or_none()


# ── caching ──────────────────────────────────────────────────────────


def test_a_split_is_fetched_once_then_served_from_cache(db, monkeypatch):
    calls = _fetches(monkeypatch, SPLIT)

    assert split_history.prefetch(db, ["AENA.MC"]) == {"AENA.MC": SPLIT}
    db.flush()
    assert split_history.prefetch(db, ["AENA.MC"]) == {"AENA.MC": SPLIT}

    assert calls == ["AENA.MC"]


def test_no_splits_is_a_real_answer_and_is_cached(db, monkeypatch):
    """The common case — most tickers have never split. Not caching it would
    leave the loop calling Yahoo for every position on every import."""
    calls = _fetches(monkeypatch, [])

    split_history.prefetch(db, ["SAN.MC"])
    db.flush()
    split_history.prefetch(db, ["SAN.MC"])

    assert calls == ["SAN.MC"]
    assert _row(db, "SAN.MC").splits == "[]"


def test_a_failed_fetch_is_not_cached(db, monkeypatch):
    calls = _fetches(monkeypatch, None)

    assert split_history.prefetch(db, ["SAN.MC"]) == {"SAN.MC": []}
    db.flush()

    assert _row(db, "SAN.MC") is None
    split_history.prefetch(db, ["SAN.MC"])
    assert calls == ["SAN.MC", "SAN.MC"], "a failure should be retried, not remembered"


def test_a_failure_serves_the_stale_entry_rather_than_claiming_no_splits(db, monkeypatch):
    """Returning [] here would make the supervisor miss a real split."""
    _fetches(monkeypatch, SPLIT)
    split_history.prefetch(db, ["AENA.MC"])
    db.flush()
    _row(db, "AENA.MC").fetched_at = datetime.now(timezone.utc) - split_history.TTL * 2
    db.flush()

    _fetches(monkeypatch, None)

    assert split_history.prefetch(db, ["AENA.MC"]) == {"AENA.MC": SPLIT}


# ── freshness ────────────────────────────────────────────────────────


def test_a_stale_entry_is_refetched(db, monkeypatch):
    _fetches(monkeypatch, [])
    split_history.prefetch(db, ["SAN.MC"])
    db.flush()
    _row(db, "SAN.MC").fetched_at = datetime.now(timezone.utc) - split_history.TTL - timedelta(days=1)
    db.flush()

    calls = _fetches(monkeypatch, SPLIT)
    assert split_history.prefetch(db, ["SAN.MC"]) == {"SAN.MC": SPLIT}
    assert calls == ["SAN.MC"]
    assert _row(db, "SAN.MC").splits != "[]"


def test_an_entry_just_inside_the_ttl_is_not_refetched(db, monkeypatch):
    _fetches(monkeypatch, SPLIT)
    split_history.prefetch(db, ["AENA.MC"])
    db.flush()
    _row(db, "AENA.MC").fetched_at = datetime.now(timezone.utc) - split_history.TTL + timedelta(hours=1)
    db.flush()

    calls = _fetches(monkeypatch, [])
    assert split_history.prefetch(db, ["AENA.MC"]) == {"AENA.MC": SPLIT}
    assert calls == []


def test_an_unreadable_cached_payload_is_refetched(db, monkeypatch):
    """A 200 is not proof of a verdict, and neither is a row that exists."""
    db.add(SplitHistoryCache(ticker="SAN.MC", splits="{not json", fetched_at=datetime.now(timezone.utc)))
    db.flush()
    calls = _fetches(monkeypatch, SPLIT)

    assert split_history.prefetch(db, ["SAN.MC"]) == {"SAN.MC": SPLIT}
    assert calls == ["SAN.MC"]


# ── the batch shape ──────────────────────────────────────────────────


def test_every_ticker_is_read_in_one_query(db, monkeypatch):
    from sqlalchemy import event

    _fetches(monkeypatch, [])
    split_history.prefetch(db, ["A", "B", "C"])
    db.commit()

    seen: list[str] = []
    listener = lambda c, cur, s, p, ctx, m: seen.append(s)  # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        split_history.prefetch(db, ["A", "B", "C"])
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)

    assert len([s for s in seen if s.lstrip().upper().startswith("SELECT")]) == 1


def test_duplicate_tickers_are_asked_for_once(db, monkeypatch):
    calls = _fetches(monkeypatch, [])
    split_history.prefetch(db, ["SAN.MC", "SAN.MC", "SAN.MC"])
    assert calls == ["SAN.MC"]


def test_an_empty_request_touches_nothing(db, monkeypatch):
    _fetches(monkeypatch, None)
    assert split_history.prefetch(db, []) == {}
    assert split_history.prefetch(db, [None, ""]) == {}


def test_round_trip_preserves_dates_and_ratios(db, monkeypatch):
    history = [(date(2014, 6, 9), Decimal("7")), (date(2020, 8, 31), Decimal("4"))]
    _fetches(monkeypatch, history)
    split_history.prefetch(db, ["AAPL"])
    db.flush()

    assert json.loads(_row(db, "AAPL").splits) == [["2014-06-09", "7"], ["2020-08-31", "4"]]
    _fetches(monkeypatch, None)
    assert split_history.prefetch(db, ["AAPL"]) == {"AAPL": history}
