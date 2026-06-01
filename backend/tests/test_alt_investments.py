"""Tests for alt-investments metrics and the ECB exchange-rate service."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.alt_investments import _allocation, _metrics, _to_out
from backend.models import AltInvestment, AltInvestmentType, Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── PE metrics ────────────────────────────────────────────────────────


def test_metrics_standard_case():
    # called=100, distributed=40, nav=120 → TVPI=1.6, DPI=0.4, RVPI=1.2
    tvpi, dpi, rvpi = _metrics(Decimal(100), Decimal(40), Decimal(120))
    assert tvpi == pytest.approx(1.6)
    assert dpi == pytest.approx(0.4)
    assert rvpi == pytest.approx(1.2)


def test_metrics_no_called_capital_is_none():
    assert _metrics(Decimal(0), Decimal(0), Decimal(0)) == (None, None, None)


def test_to_out_derives_unfunded_and_total_value():
    inv = AltInvestment(
        id=1,
        user_id=1,
        name="Fund I",
        type=AltInvestmentType.PRIVATE_EQUITY.value,
        status="ACTIVE",
        manager="",
        geography="",
        currency="EUR",
        notes="",
        committed_capital=Decimal(200),
        called_capital=Decimal(100),
        distributed_capital=Decimal(40),
        current_nav=Decimal(120),
    )
    out = _to_out(inv)
    assert out.unfunded == Decimal(100)  # 200 - 100
    assert out.total_value == Decimal(160)  # 40 + 120
    assert out.tvpi == pytest.approx(1.6)


def test_allocation_by_nav_sorted_and_pct():
    items = [
        AltInvestment(type="PRIVATE_EQUITY", current_nav=Decimal(60), geography="EU", currency="EUR"),
        AltInvestment(type="REAL_ESTATE", current_nav=Decimal(40), geography="US", currency="EUR"),
    ]
    slices = _allocation(items, lambda i: i.type)
    assert [s.label for s in slices] == ["PRIVATE_EQUITY", "REAL_ESTATE"]
    assert slices[0].pct == pytest.approx(60.0)
    assert slices[1].pct == pytest.approx(40.0)


# ── ECB exchange-rate service ─────────────────────────────────────────


def test_get_rate_and_to_eur(monkeypatch):
    import backend.services.exchange_rates as fx
    from backend.models import ExchangeRate

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    # Point the service at this in-memory DB
    monkeypatch.setattr(fx, "SessionLocal", Session)
    monkeypatch.setattr(fx, "engine", engine)

    with Session() as s:
        s.add(ExchangeRate(rate_date=date(2024, 1, 2), currency="USD", rate=Decimal("1.10")))
        s.commit()

    # EUR is always 1, no DB lookup
    assert fx.get_rate("EUR", "2024-01-02") == Decimal(1)
    # Exact-date hit
    assert fx.get_rate("USD", "2024-01-02") == Decimal("1.10")
    # ±7 day fallback (Jan 1 holiday → nearest Jan 2)
    assert fx.get_rate("USD", "2024-01-01") == Decimal("1.10")
    # Unknown currency
    assert fx.get_rate("JPY", "2024-01-02") is None
    # Convert 110 USD → 100 EUR
    assert fx.to_eur(Decimal(110), "USD", "2024-01-02") == pytest.approx(Decimal(100))
