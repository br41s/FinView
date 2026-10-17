"""Two valuations of the same portfolio at once must not fail each other.

/portfolio fires several API calls in parallel and each one prices the portfolio.
On the first view of the day every one of them finds no cached price, so two of
them insert the same (isin, fetched_date) row and the later commit raised
UniqueViolation: a 500 in production (2026-10-17 07:55). A ticker learned during
the valuation (ticker_map, unique on isin) collides the same way.

The other writer is simulated deterministically: just before this session's
INSERT reaches the database, a second connection writes and commits the same row.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import sessionmaker

from backend.models import Base, PriceCache, TickerMap
from backend.services import prices, ticker_map

CURATED_ISIN = "ES0113900J37"   # Banco Santander → SAN.MC
UNKNOWN_ISIN = "US0378331005"


@pytest.fixture
def engine(tmp_path):
    # A file, not :memory:, so the "other request" has its own connection.
    eng = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _another_writer_first(engine, table: str, write) -> list[bool]:
    """Run `write` on its own connection just before our first INSERT into `table`."""
    fired: list[bool] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _race(conn, cursor, statement, params, context, executemany):
        if fired or not statement.lstrip().upper().startswith(f"INSERT INTO {table.upper()}"):
            return
        fired.append(True)
        with engine.begin() as other:
            write(other)

    return fired


def _stub_yahoo(monkeypatch, price=20.0):
    monkeypatch.setattr(
        prices, "_fetch_yahoo_prices", lambda tickers, **_kw: dict.fromkeys(tickers, price)
    )
    monkeypatch.setattr(prices.exchange_rates, "get_rate", lambda _c, _d: Decimal("1"))


def test_a_price_row_written_by_a_parallel_valuation_does_not_fail_this_one(
    engine, monkeypatch
):
    _stub_yahoo(monkeypatch, price=20.0)
    fired = _another_writer_first(engine, "price_cache", lambda other: other.execute(
        insert(PriceCache).values(
            isin=CURATED_ISIN, yahoo_ticker="SAN.MC", price=Decimal("19"),
            currency="EUR", original_currency="EUR", fetched_date=date.today(),
        )
    ))
    db = sessionmaker(bind=engine)()
    try:
        out = prices.fetch_and_cache_prices(db, [CURATED_ISIN])
    finally:
        db.close()

    assert fired
    assert out == {CURATED_ISIN: Decimal("20")}
    with sessionmaker(bind=engine)() as check:
        rows = check.query(PriceCache).filter(PriceCache.isin == CURATED_ISIN).all()
        # One row for the day, carrying this fetch's price.
        assert [(r.price, r.fetched_date) for r in rows] == [(Decimal("20"), date.today())]


def test_a_ticker_learned_by_a_parallel_valuation_does_not_fail_this_one(
    engine, monkeypatch
):
    _stub_yahoo(monkeypatch, price=50.0)
    monkeypatch.setattr(ticker_map, "lookup", lambda _isin: "AAPL")
    fired = _another_writer_first(engine, "ticker_map", lambda other: other.execute(
        insert(TickerMap).values(isin=UNKNOWN_ISIN, yahoo_ticker="AAPL", source="yfinance")
    ))
    db = sessionmaker(bind=engine)()
    try:
        out = prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])
    finally:
        db.close()

    assert fired
    # The other writer's answer stands, and this valuation still prices the ISIN.
    assert out == {CURATED_ISIN: Decimal("50"), UNKNOWN_ISIN: Decimal("50")}
    with sessionmaker(bind=engine)() as check:
        assert check.query(TickerMap).filter(TickerMap.isin == UNKNOWN_ISIN).count() == 1


def test_a_parallel_manual_correction_wins_over_this_lookup(engine, monkeypatch):
    """If the row that won the race is a human's, it is what gets priced."""
    _stub_yahoo(monkeypatch, price=50.0)
    monkeypatch.setattr(ticker_map, "lookup", lambda _isin: "WRONG")
    _another_writer_first(engine, "ticker_map", lambda other: other.execute(
        insert(TickerMap).values(isin=UNKNOWN_ISIN, yahoo_ticker="AAPL", source="manual")
    ))
    fetched: list[list[str]] = []

    def _fetch(tickers, **_kw):
        fetched.append(sorted(tickers))
        return dict.fromkeys(tickers, 50.0)

    monkeypatch.setattr(prices, "_fetch_yahoo_prices", _fetch)
    db = sessionmaker(bind=engine)()
    try:
        prices.fetch_and_cache_prices(db, [CURATED_ISIN, UNKNOWN_ISIN])
    finally:
        db.close()

    assert fetched == [["AAPL", "SAN.MC"]]
