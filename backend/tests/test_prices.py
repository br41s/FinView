"""Regression tests for portfolio price resolution and currency handling."""

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, PriceCache
from backend.services import prices as svc


def test_singapore_suffix_uses_sgd():
    assert svc._ticker_currency("U11.SI") == "SGD"


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
