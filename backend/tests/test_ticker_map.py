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


# ── what Yahoo's ISIN lookup returns is checked before it is learned ──


class _FakeTicker:
    """`yfinance.Ticker` with a canned `.info`, keyed by the ISIN asked for."""

    answers: dict = {}

    def __init__(self, isin):
        self.isin = isin

    @property
    def info(self):
        answer = self.answers[self.isin]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def yahoo(monkeypatch):
    import yfinance

    _FakeTicker.answers = {}
    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    return _FakeTicker.answers


def _info(symbol, currency, price=10.0):
    return {"symbol": symbol, "currency": currency, "regularMarketPrice": price}


@pytest.mark.parametrize(
    "symbol,currency",
    [
        ("SOLV", "USD"),
        ("URW.PA", "EUR"),
        ("MNDI.L", "GBp"),      # London in pence: prices.py divides by 100
        ("1211.HK", "HKD"),     # BYD
    ],
)
def test_a_listing_the_price_layer_can_value_is_accepted(yahoo, symbol, currency):
    yahoo[UNKNOWN_ISIN] = _info(symbol, currency)

    assert ticker_map.lookup(UNKNOWN_ISIN) == symbol


@pytest.mark.parametrize(
    "symbol,currency",
    [
        ("MLPD.L", "USD"),               # a USD line on LSE would be divided by 100
        ("XYLP.L", "GBP"),               # pounds, not pence: same division
        ("IE0002L5QB31.SG", "EUR"),      # unknown suffix is valued as USD
        ("LU0659578842-USD.LU", "EUR"),
        ("SOLV", None),                  # no currency at all
    ],
)
def test_a_listing_valued_in_the_wrong_currency_is_refused(yahoo, symbol, currency):
    """A wrong price is worse than none: BYD as 1211.HK used to read HKD as USD."""
    yahoo[UNKNOWN_ISIN] = _info(symbol, currency)

    assert ticker_map.lookup(UNKNOWN_ISIN) is None


@pytest.mark.parametrize(
    "answer",
    [
        ValueError("Invalid ISIN number"),     # yfinance's "search found nothing"
        ConnectionError("Yahoo stalled"),
        {},
        None,
        "not a dict",
        {"symbol": "SOLV", "currency": "USD"},                    # no price: dead listing
        {"symbol": None, "currency": "USD", "regularMarketPrice": 1.0},
        {"symbol": 42, "currency": "USD", "regularMarketPrice": 1.0},
    ],
)
def test_a_failed_or_malformed_lookup_resolves_to_nothing(yahoo, answer):
    yahoo[UNKNOWN_ISIN] = answer

    assert ticker_map.lookup(UNKNOWN_ISIN) is None


def test_hong_kong_is_valued_in_hkd():
    assert ticker_map.currency_for_ticker("1211.HK") == "HKD"


@pytest.mark.parametrize(
    "isin,ticker",
    [
        ("ES0112320009", "COM.MC"),   # Catenon: CNTE.MC has no data on Yahoo
        ("IE00B8CJW150", "MLPD.MI"),  # the ISIN lookup returns MLPD.L (USD on LSE)
        ("IE0002L5QB31", "XY7D.DE"),  # the ISIN lookup returns a Stuttgart line, no bars
    ],
)
def test_curated_listings_are_ones_the_price_layer_values_in_euros(db, isin, ticker):
    assert ticker_map.resolve(db, isin) == ticker
    assert ticker_map.currency_for_ticker(ticker) == "EUR"


# ── a valuation learns what the import never did ─────────────────────


def _price_everything(monkeypatch, fetched):
    def _fetch(tickers, **_kw):
        fetched.append(list(tickers))
        return dict.fromkeys(tickers, 50.0)

    monkeypatch.setattr(prices, "_fetch_yahoo_prices", _fetch)
    monkeypatch.setattr(prices.exchange_rates, "get_rate", lambda _c, _d: Decimal("1"))


def test_the_days_first_valuation_learns_and_prices_an_unknown_isin(db, yahoo, monkeypatch):
    """Before, only an import looked tickers up — and annual reports are imported
    once a year, so an ISIN whose lookup missed (or predated ticker_map) stayed
    unpriced for that long."""
    yahoo[UNKNOWN_ISIN] = _info("AAPL", "USD")
    fetched: list[list[str]] = []
    _price_everything(monkeypatch, fetched)

    out = prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])

    assert out[UNKNOWN_ISIN] == Decimal("50")
    assert sorted(fetched[0]) == ["AAPL", CURATED_TICKER]
    row = db.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).one()
    assert (row.yahoo_ticker, row.source) == ("AAPL", ticker_map.YFINANCE)


def test_a_missed_lookup_is_not_stored_and_is_asked_again(db, yahoo, monkeypatch):
    yahoo[UNKNOWN_ISIN] = ConnectionError("Yahoo stalled")
    _price_everything(monkeypatch, [])

    out = prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])

    assert UNKNOWN_ISIN not in out
    assert db.query(TickerMap).count() == 0
    assert db.query(PriceCache).filter(PriceCache.isin == UNKNOWN_ISIN).count() == 0

    # Tomorrow: the curated ISIN needs a price again, so the lookup rides along.
    db.query(PriceCache).delete()
    yahoo[UNKNOWN_ISIN] = _info("AAPL", "USD")

    assert prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])[UNKNOWN_ISIN]


def test_no_lookup_once_everything_with_a_ticker_is_priced_today(db, yahoo, monkeypatch):
    """Otherwise a bond or a right with no listing costs a Yahoo call per page view."""
    yahoo[UNKNOWN_ISIN] = ValueError("Invalid ISIN number")
    _price_everything(monkeypatch, [])
    prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])

    calls: list[str] = []
    monkeypatch.setattr(ticker_map, "lookup", lambda isin: calls.append(isin))
    prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])

    assert calls == []


def test_a_curated_or_manual_isin_is_never_looked_up(db, yahoo, monkeypatch):
    ticker_map.remember(db, UNKNOWN_ISIN, "AAPL", source=ticker_map.MANUAL)
    db.flush()
    calls: list[str] = []
    monkeypatch.setattr(ticker_map, "lookup", lambda isin: calls.append(isin))
    _price_everything(monkeypatch, [])

    prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])

    assert calls == []
