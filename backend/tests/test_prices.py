"""Regression tests for portfolio price resolution and currency handling."""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, PriceCache, SessionClose
from backend.services import prices as svc, ticker_map


def test_singapore_suffix_uses_sgd():
    assert ticker_map.currency_for_ticker("U11.SI") == "SGD"


def test_shared_yahoo_ticker_prices_every_requested_isin(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc, "_fetch_yahoo_prices", lambda _tickers, **_kw: {"AENA.MC": 20.5})
    old_isin = "ES0105046009"
    new_isin = "ES0105046017"

    result = svc.fetch_and_cache_prices(db, [old_isin, new_isin])

    assert result == {
        old_isin: Decimal("20.5"),
        new_isin: Decimal("20.5"),
    }
    assert {
        row.isin for row in db.query(PriceCache).order_by(PriceCache.isin).all()
    } == {old_isin, new_isin}
    db.close()


def test_singapore_price_is_converted_with_sgd_rate(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc, "_fetch_yahoo_prices", lambda _tickers, **_kw: {"U11.SI": 30.0})
    seen_currencies: list[str] = []

    def fake_rate(currency, _date):
        seen_currencies.append(currency)
        return Decimal("1.5")

    monkeypatch.setattr(svc.exchange_rates, "get_rate", fake_rate)

    result = svc.fetch_and_cache_prices(db, ["SG1M31001969"])

    assert seen_currencies == ["SGD"]
    assert result["SG1M31001969"] == Decimal("20.0")
    cached = db.query(PriceCache).one()
    assert cached.original_currency == "SGD"
    assert cached.original_price == Decimal("30")
    assert cached.fx_rate == Decimal("1.5")
    db.close()


# ── previous close: the session before, for Living World's daily move ──────────


def test_previous_close_is_each_tickers_own_bar_before_the_last():
    import pandas as pd

    frame = pd.DataFrame(
        {
            # USO did not trade in the last row (a holiday on its exchange): its previous
            # close is its own bar before, not the row before in the frame.
            ("Close", "XLE"): [89.0, 90.0, 91.5],
            ("Close", "USO"): [73.0, 74.0, float("nan")],
            # A single bar has a price and no previous close.
            ("Close", "NEW"): [float("nan"), float("nan"), 10.0],
        }
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    previous: dict[str, float] = {}

    last = svc._last_closes(frame, ["XLE", "USO", "NEW"], previous)

    assert last == {"XLE": 91.5, "USO": 74.0, "NEW": 10.0}
    assert previous == {"XLE": 90.0, "USO": 73.0}


def test_previous_close_from_a_single_ticker_series():
    import pandas as pd

    previous: dict[str, float] = {}
    svc._last_closes(pd.DataFrame({"Close": [90.0, 91.5]}), ["XLE"], previous)
    assert previous == {"XLE": 90.0}


def _fake_fetch(last: dict[str, float], prev: dict[str, float]):
    def fetch(_tickers, *, previous=None, **_kw):
        if previous is not None:
            previous.update(prev)
        return dict(last)

    return fetch


def test_the_previous_close_is_cached_in_the_listing_currency(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc.ticker_map, "currency_for_ticker", lambda _t: "GBP")
    monkeypatch.setattr(svc.exchange_rates, "get_rate", lambda _c, _d: Decimal("0.8"))
    monkeypatch.setattr(svc, "_resolve_ticker", lambda _isin, _db: "SHEL.L")
    monkeypatch.setattr(
        svc, "_fetch_yahoo_prices", _fake_fetch({"SHEL.L": 2500.0}, {"SHEL.L": 2450.0})
    )

    svc.fetch_and_cache_prices(db, ["GB00BP6MXD84"])

    row = db.query(PriceCache).one()
    # Pence divided for both, and neither converted to euros: the move is the listing's.
    assert row.original_price == Decimal("25")
    assert row.previous_close == Decimal("24.5")
    db.close()


def test_no_previous_bar_leaves_the_previous_close_unknown(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc, "_fetch_yahoo_prices", _fake_fetch({"AENA.MC": 20.5}, {}))

    svc.fetch_and_cache_prices(db, ["ES0105046017"])

    assert db.query(PriceCache).one().previous_close is None
    db.close()


# ── every session of the download, for Living World's moves ────────────────────


def test_sessions_are_each_tickers_own_dated_bars():
    import pandas as pd

    frame = pd.DataFrame(
        {("Close", "XLE"): [89.0, 90.0, 91.5], ("Close", "USO"): [73.0, 74.0, float("nan")]},
        index=pd.to_datetime(["2026-11-10", "2026-11-11", "2026-11-12"]),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    sessions: dict = {}

    svc._last_closes(frame, ["XLE", "USO"], None, sessions)

    d1, d2, d3 = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)
    assert sessions == {
        "XLE": [(d1, 89.0), (d2, 90.0), (d3, 91.5)],
        "USO": [(d1, 73.0), (d2, 74.0)],  # its own bars: the holiday is not a session
    }


def test_a_frame_without_dates_gives_no_sessions():
    import pandas as pd

    sessions: dict = {}
    svc._last_closes(pd.DataFrame({"Close": [90.0, 91.5]}), ["XLE"], None, sessions)
    assert sessions == {}


def test_the_valuation_stores_every_session_with_its_own_previous_close(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc.exchange_rates, "get_rate", lambda _c, _d: Decimal("0.8"))
    monkeypatch.setattr(svc, "_resolve_ticker", lambda _isin, _db: "SHEL.L")
    d1, d2, d3 = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)
    # An earlier download already knew d1's previous close.
    db.add(SessionClose(yahoo_ticker="SHEL.L", session_date=d1, close=Decimal("24"),
                        previous_close=Decimal("23.5")))
    db.commit()

    def fetch(_tickers, *, sessions=None, **_kw):
        sessions["SHEL.L"] = [(d1, 2400.0), (d2, 2450.0), (d3, 2500.0)]
        return {"SHEL.L": 2500.0}

    monkeypatch.setattr(svc, "_fetch_yahoo_prices", fetch)

    svc.fetch_and_cache_prices(db, ["GB00BP6MXD84"])

    rows = {r.session_date: r for r in db.query(SessionClose)}
    # Pence divided; each previous close is the bar before in the same download.
    assert (rows[d3].close, rows[d3].previous_close) == (Decimal("25"), Decimal("24.5"))
    assert (rows[d2].close, rows[d2].previous_close) == (Decimal("24.5"), Decimal("24"))
    # The oldest bar has no previous one here: the earlier download's is kept, not erased.
    assert rows[d1].previous_close == Decimal("23.5")
    db.close()


def test_a_newer_download_overwrites_a_live_close():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    d1, d2 = date(2026, 11, 11), date(2026, 11, 12)

    svc._store_sessions(db, {"SAN.MC": [(d1, 4.0), (d2, 4.1)]})  # d2 still trading
    svc._store_sessions(db, {"SAN.MC": [(d1, 4.0), (d2, 4.2)]})  # the next day's download
    db.commit()

    row = db.query(SessionClose).filter(SessionClose.session_date == d2).one()
    assert (row.close, row.previous_close) == (Decimal("4.2"), Decimal("4"))
    first = db.query(SessionClose).filter(SessionClose.session_date == d1).one()
    assert first.previous_close is None  # never known: unknown, not zero
    db.close()
