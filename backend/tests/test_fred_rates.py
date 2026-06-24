"""Tests for the FRED risk-free rate service and its wiring into Greeks."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, FredRate
from backend.services import fred_rates
from backend.services.fred_rates import (
    _FALLBACK,
    currency_for_ticker,
    get_rate,
    risk_free_rate,
    risk_free_rate_for_ticker,
)
from backend.services.greeks_calculator import enrich_options_with_greeks


@pytest.fixture
def fred_db(monkeypatch):
    """In-memory DB with the FredRate table, patched into the service."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(fred_rates, "SessionLocal", Session)
    return Session


# ── Currency resolution ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("AAPL", "USD"),          # plain US ticker
        ("SAN.MC", "EUR"),        # MEFF Spanish
        ("BMW.DE", "EUR"),        # Eurex euro venue
        ("MC.PA", "EUR"),         # Paris
        ("VOD.L", "USD"),         # London (no GBP series yet → USD fallback)
        ("US0378331005", "USD"),  # ISIN, no suffix
        (None, "USD"),
        ("", "USD"),
    ],
)
def test_currency_for_ticker(ticker, expected):
    assert currency_for_ticker(ticker) == expected


# ── Fallback (A) ─────────────────────────────────────────────────────────


def test_risk_free_rate_falls_back_to_constant(monkeypatch):
    monkeypatch.setattr(fred_rates, "get_rate", lambda *a, **k: None)
    assert risk_free_rate("USD") == _FALLBACK["USD"]
    assert risk_free_rate("EUR") == _FALLBACK["EUR"]
    # Unknown currency falls back to the USD constant.
    assert risk_free_rate("JPY") == _FALLBACK["USD"]


def test_risk_free_rate_uses_fred_when_available(monkeypatch):
    monkeypatch.setattr(fred_rates, "get_rate", lambda *a, **k: Decimal("0.0412"))
    assert risk_free_rate("USD") == pytest.approx(0.0412)


def test_for_ticker_resolves_currency(monkeypatch):
    monkeypatch.setattr(
        fred_rates, "get_rate", lambda ccy, on=None: Decimal("0.02") if ccy == "EUR" else None
    )
    assert risk_free_rate_for_ticker("SAN.MC") == pytest.approx(0.02)  # EUR from FRED
    assert risk_free_rate_for_ticker("AAPL") == _FALLBACK["USD"]       # USD fell back


# ── get_rate window logic ────────────────────────────────────────────────


def test_get_rate_returns_latest_on_or_before(fred_db):
    with fred_db() as db:
        db.add_all([
            FredRate(series_id="DGS3MO", rate_date=date(2026, 6, 10), rate=Decimal("0.0500")),
            FredRate(series_id="DGS3MO", rate_date=date(2026, 6, 15), rate=Decimal("0.0510")),
        ])
        db.commit()
    # Asking on the 16th (a date with no row) returns the 15th's value.
    assert get_rate("USD", date(2026, 6, 16)) == Decimal("0.0510")


def test_get_rate_respects_lookback_window(fred_db):
    with fred_db() as db:
        db.add(FredRate(series_id="DGS3MO", rate_date=date(2026, 6, 1), rate=Decimal("0.05")))
        db.commit()
    # 20 days later is outside the 14-day window → None (caller uses constant).
    assert get_rate("USD", date(2026, 6, 21)) is None


def test_get_rate_unknown_currency_is_none(fred_db):
    assert get_rate("JPY", date(2026, 6, 16)) is None


# ── Greeks wiring: r actually flows through ──────────────────────────────


def test_enrich_passes_risk_free_rate_through():
    def chain():
        return {
            "current_price": 100.0,
            "calls": [{"type": "call", "strike": 100, "impliedVolatility": 0.25,
                       "daysToExpiry": 365}],
            "puts": [],
        }

    low = enrich_options_with_greeks(chain(), r=0.01)["calls"][0]["greeks"]
    high = enrich_options_with_greeks(chain(), r=0.06)["calls"][0]["greeks"]
    # Rho and theoretical price are rate-sensitive — proves r reaches the model.
    assert low["rho"] != high["rho"]
    assert low["theoretical_price"] != high["theoretical_price"]
