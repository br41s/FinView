"""Tests for persisted ISIN → Yahoo ticker resolution.

The behaviour under test is the one that did not exist: a ticker resolved once
must be remembered. Before this, the data supervisor looked a ticker up via
yfinance, wrote it into a DataIssue description, and dropped it — so the price
stayed "—", the lookup repeated on every import, and split detection never saw
the security.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, PriceCache, TickerMap
from backend.services import prices, ticker_map

CURATED_ISIN = "ES0113900J37"   # Banco Santander, in the curated map
CURATED_TICKER = "SAN.MC"
UNKNOWN_ISIN = "US0378331005"   # not curated


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── resolve ──────────────────────────────────────────────────────────


def test_an_unknown_isin_resolves_to_nothing(db):
    assert ticker_map.resolve(db, UNKNOWN_ISIN) is None


def test_a_curated_isin_resolves_without_any_stored_row(db):
    assert ticker_map.resolve(db, CURATED_ISIN) == CURATED_TICKER


def test_a_remembered_isin_resolves(db):
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")

    assert ticker_map.resolve(db, UNKNOWN_ISIN) == "AAPL"


def test_curated_beats_an_automatic_lookup(db):
    """A symbol lookup must not overwrite a curated corporate-action mapping."""
    ticker_map.remember(db, CURATED_ISIN, "WRONG.XX", source=ticker_map.YFINANCE)

    assert ticker_map.resolve(db, CURATED_ISIN) == CURATED_TICKER


def test_a_manual_correction_beats_curated(db):
    """Otherwise a wrongly curated ISIN could only be fixed by a deploy."""
    ticker_map.remember(db, CURATED_ISIN, "SAN", source=ticker_map.MANUAL)

    assert ticker_map.resolve(db, CURATED_ISIN) == "SAN"


# ── remember ─────────────────────────────────────────────────────────


def test_remembering_twice_updates_rather_than_duplicates(db):
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL.MX")
    db.flush()

    rows = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).all()
    assert len(rows) == 1
    assert rows[0].yahoo_ticker == "AAPL.MX"


def test_an_automatic_lookup_never_overwrites_a_manual_correction(db):
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL", source=ticker_map.MANUAL)
    ticker_map.remember(db, UNKNOWN_ISIN, "GARBAGE", source=ticker_map.YFINANCE)
    db.flush()

    row = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).one()
    assert row.yahoo_ticker == "AAPL"
    assert row.source == ticker_map.MANUAL


def test_a_manual_correction_overwrites_a_learned_row(db):
    ticker_map.remember(db, UNKNOWN_ISIN, "WRONG", source=ticker_map.YFINANCE)
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL", source=ticker_map.MANUAL)
    db.flush()

    row = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).one()
    assert row.yahoo_ticker == "AAPL"
    assert row.source == ticker_map.MANUAL


def test_remember_does_not_commit(db):
    """The caller owns the transaction, so a resolution rolls back with it."""
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")
    db.rollback()

    assert db.query(TickerMap).count() == 0


# ── effective_map ────────────────────────────────────────────────────


def test_the_effective_map_contains_the_curated_entries(db):
    assert ticker_map.effective_map(db)[CURATED_ISIN] == CURATED_TICKER


def test_the_effective_map_widens_as_the_app_learns(db):
    before = ticker_map.effective_map(db)
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")
    db.flush()
    after = ticker_map.effective_map(db)

    assert UNKNOWN_ISIN not in before
    assert after[UNKNOWN_ISIN] == "AAPL"
    assert len(after) == len(before) + 1


def test_the_effective_map_applies_the_same_precedence_as_resolve(db):
    ticker_map.remember(db, CURATED_ISIN, "WRONG.XX", source=ticker_map.YFINANCE)
    db.flush()
    assert ticker_map.effective_map(db)[CURATED_ISIN] == CURATED_TICKER

    ticker_map.remember(db, CURATED_ISIN, "SAN", source=ticker_map.MANUAL)
    db.flush()
    assert ticker_map.effective_map(db)[CURATED_ISIN] == "SAN"


# ── the price layer actually uses it ─────────────────────────────────


def test_a_learned_ticker_makes_prices_fetchable(db, monkeypatch):
    """The whole point: an ISIN outside the curated map used to be a dead end."""
    assert prices._resolve_ticker(UNKNOWN_ISIN, db) is None

    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL")
    db.flush()

    assert prices._resolve_ticker(UNKNOWN_ISIN, db) == "AAPL"

    monkeypatch.setattr(prices, "_fetch_yahoo_prices", lambda _t, **_kw: {"AAPL": 190.0})
    monkeypatch.setattr(prices.exchange_rates, "get_rate", lambda _c, _d: Decimal("2"))

    assert prices.fetch_and_cache_prices(db, [UNKNOWN_ISIN]) == {UNKNOWN_ISIN: Decimal("95")}


def test_the_price_cache_fallback_still_works(db):
    """Installations whose cache predates the ticker map keep resolving."""
    from datetime import date

    db.add(PriceCache(
        isin=UNKNOWN_ISIN, yahoo_ticker="LEGACY", price=Decimal("1"),
        fetched_date=date(2020, 1, 1),
    ))
    db.flush()

    assert prices._resolve_ticker(UNKNOWN_ISIN, db) == "LEGACY"


def test_the_ticker_map_wins_over_a_stale_cache_row(db):
    from datetime import date

    db.add(PriceCache(
        isin=UNKNOWN_ISIN, yahoo_ticker="STALE", price=Decimal("1"),
        fetched_date=date(2020, 1, 1),
    ))
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL", source=ticker_map.MANUAL)
    db.flush()

    assert prices._resolve_ticker(UNKNOWN_ISIN, db) == "AAPL"


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("ENI.MI", "EUR"),   # Milan — priced as USD before the table was shared
        ("NOKIA.HE", "EUR"),
        ("KBC.BR", "EUR"),
        ("NESN.SW", "CHF"),
        ("VOLV-B.ST", "SEK"),
        ("VOD.L", "GBP"),
        ("AAPL", "USD"),
        (None, "USD"),
    ],
)
def test_currency_for_ticker_covers_every_venue_the_portfolio_prices(ticker, expected):
    assert ticker_map.currency_for_ticker(ticker) == expected
