"""Contract tests for the chart endpoints.

The dashboard's ten chart endpoints returned bare dicts. Their shapes lived only
in frontend/src/lib/types.ts, hand-written and hand-cast, so renaming a label in
a SQL aggregate produced blank widgets with no type error, no failing test and a
green build. They now declare response models.

These tests exist to prove the models describe what the endpoints actually emit:
each one runs against a seeded database and validates every row through the
model FastAPI would use. A model that drifts from its query fails here rather
than as a 500 in production, where response validation runs too late to help.
"""

import inspect
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import charts
from backend.api.schemas import (
    CapitalGainsBreakdownOut,
    CompanyDividendsYearlyOut,
    DividendsByCountryOut,
    DividendsMonthlyOut,
    DividendYieldOut,
    FundamentalsOut,
    OhlcBarOut,
    PatrimonioCompositionOut,
    TopDividendPayerOut,
    WithholdingsByCountryOut,
)
from backend.models import (
    Account,
    Base,
    Broker,
    PortfolioHolding,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
    User,
)

YEAR = 2024


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user(db):
    u = User(email="brais@example.com", name="Brais")
    db.add(u)
    db.flush()
    return u


def _tx(account_id: int, **kw) -> Transaction:
    defaults = dict(
        account_id=account_id,
        type=TransactionType.DIVIDEND.value,
        trade_date=date(YEAR, 3, 14),
        isin="ES0113900J37",
        name="Banco Santander",
        country="España",
        quantity=Decimal("100"),
        price=Decimal("4.21"),
        gross_amount=Decimal("42.10"),
        fees=Decimal("0"),
        withholding_tax=Decimal("7.99"),
        net_amount_eur=Decimal("34.11"),
    )
    defaults.update(kw)
    return Transaction(**defaults)


@pytest.fixture
def seeded(db, user):
    """One account with dividends, a buy, a sell, a closed lot and a 714 row.

    Deliberately includes the awkward cases the models have to survive: a
    dividend with no country (so the coalesce path is exercised) and a holding
    that never had a buy.
    """
    account = Account(user_id=user.id, broker=Broker.DEGIRO.value, account_id="DG-1")
    db.add(account)
    db.flush()

    buy = _tx(
        account.id,
        type=TransactionType.BUY.value,
        trade_date=date(YEAR, 1, 10),
        quantity=Decimal("100"),
        price=Decimal("3.80"),
        gross_amount=Decimal("380"),
        net_amount_eur=Decimal("380"),
        withholding_tax=Decimal("0"),
    )
    sell = _tx(
        account.id,
        type=TransactionType.SELL.value,
        trade_date=date(YEAR, 11, 2),
        quantity=Decimal("40"),
        price=Decimal("4.50"),
        gross_amount=Decimal("180"),
        net_amount_eur=Decimal("180"),
        withholding_tax=Decimal("0"),
    )
    db.add_all([
        buy,
        sell,
        _tx(account.id),
        _tx(account.id, trade_date=date(YEAR, 9, 1), country=None),
        _tx(
            account.id,
            isin="US0378331005",
            name="Apple Inc",
            country="Estados Unidos",
            trade_date=date(YEAR, 6, 5),
        ),
    ])
    db.flush()

    db.add(
        TaxLot(
            buy_tx_id=buy.id,
            sell_tx_id=sell.id,
            isin="ES0113900J37",
            quantity_bought=Decimal("100"),
            quantity_remaining=Decimal("60"),
            cost_basis_eur=Decimal("152"),
            quantity_sold=Decimal("40"),
            proceeds_eur=Decimal("180"),
            realized_pl_eur=Decimal("28"),
            close_date=date(YEAR, 11, 2),
            holding_period=">=1y",
        )
    )
    db.add(
        TaxResult(
            user_id=user.id,
            fiscal_year=YEAR,
            modelo=714,
            casilla=1,
            description="Acciones cotizadas",
            amount_eur=Decimal("1234.56"),
        )
    )
    db.add(
        PortfolioHolding(
            import_id=1,
            account_id=account.id,
            fiscal_year=YEAR,
            broker=Broker.DEGIRO.value,
            isin="US0378331005",
            name="Apple Inc",
            quantity=Decimal("10"),
            price=Decimal("190"),
            value_eur=Decimal("1900"),
        )
    )
    db.commit()
    return account


# ── Endpoints backed purely by the database ─────────────────────────
#
# Parametrised so a new chart endpoint added without a model shows up as a
# missing entry here rather than passing silently.

def call(endpoint, db, user, fiscal_year=YEAR):
    """Call a chart endpoint, passing fiscal_year only where it is accepted.

    dividends_by_company_yearly is deliberately multi-year and takes no filter.
    """
    if "fiscal_year" in inspect.signature(endpoint).parameters:
        return endpoint(db=db, user=user, fiscal_year=fiscal_year)
    return endpoint(db=db, user=user)


DB_ENDPOINTS = [
    (charts.dividends_by_country, DividendsByCountryOut),
    (charts.dividends_monthly, DividendsMonthlyOut),
    (charts.top_dividend_payers, TopDividendPayerOut),
    (charts.capital_gains_breakdown, CapitalGainsBreakdownOut),
    (charts.patrimonio_composition, PatrimonioCompositionOut),
    (charts.dividend_yield, DividendYieldOut),
    (charts.withholdings_by_country, WithholdingsByCountryOut),
    (charts.dividends_by_company_yearly, CompanyDividendsYearlyOut),
]


@pytest.mark.parametrize(
    ("endpoint", "model"), DB_ENDPOINTS, ids=lambda v: getattr(v, "__name__", "")
)
def test_rows_satisfy_the_declared_response_model(db, user, seeded, endpoint, model):
    rows = call(endpoint, db, user)

    assert rows, f"{endpoint.__name__} returned nothing — the fixture no longer exercises it"
    for row in rows:
        model.model_validate(row)


@pytest.mark.parametrize(
    ("endpoint", "model"), DB_ENDPOINTS, ids=lambda v: getattr(v, "__name__", "")
)
def test_models_hold_without_a_year_filter(db, user, seeded, endpoint, model):
    """Where fiscal_year is accepted it is optional; the shape must not change."""
    for row in call(endpoint, db, user, fiscal_year=None):
        model.model_validate(row)


def test_endpoints_return_nothing_for_a_different_user(db, user, seeded):
    """Tenant scoping: another user's dashboard must be empty, not shared."""
    stranger = User(email="someone@else.com", name="Stranger")
    db.add(stranger)
    db.flush()

    for endpoint, _ in DB_ENDPOINTS:
        assert call(endpoint, db, stranger) == [], endpoint.__name__


def test_missing_country_survives_as_a_labelled_bucket(db, user, seeded):
    """A dividend with no country is coalesced, never emitted as null."""
    rows = charts.dividends_by_country(db=db, user=user, fiscal_year=YEAR)

    countries = {r["country"] for r in rows}
    assert "Desconocido" in countries
    assert None not in countries


def test_effective_withholding_rate_is_computed_not_crashed(db, user, seeded):
    """Regression: this endpoint used to 500 on SQLite.

    SUM(ABS(x)) comes back as a float there while SUM(x) is a Decimal, so
    `withholding / gross` raised TypeError — meaning the whole endpoint was
    broken in local development and nothing noticed, because it had no test.
    """
    rows = charts.withholdings_by_country(db=db, user=user, fiscal_year=YEAR)

    assert rows
    for row in rows:
        rate = Decimal(row["effective_rate"])
        gross = Decimal(row["gross"])
        withholding = Decimal(row["withholding"])
        assert Decimal("0") <= rate <= Decimal("100")
        # 7.99 withheld on 42.10 gross is 18.98%.
        assert rate == round(withholding / gross * 100, 2)


def test_every_chart_route_declares_a_response_model():
    """A new chart endpoint without a model is the exact drift this prevents."""
    undeclared = [
        route.path
        for route in charts.router.routes
        if getattr(route, "methods", set()) == {"GET"} and route.response_model is None
    ]

    assert not undeclared, f"chart routes without a response_model: {undeclared}"


# ── Endpoints that read yfinance ────────────────────────────────────
#
# Not called here: they fetch over the network and return [] / {} on any
# failure, so calling them would test Yahoo's availability. What matters is that
# the model accepts the row shape the endpoint builds.


def test_ohlc_model_accepts_a_daily_bar():
    """Daily bars carry no `time`; only intraday intervals add one."""
    bar = OhlcBarOut.model_validate(
        {
            "date": "2024-03-14",
            "open": 4.11,
            "high": 4.25,
            "low": 4.08,
            "close": 4.21,
            "volume": 1_234_567,
        }
    )

    assert bar.time is None


def test_ohlc_model_accepts_an_intraday_bar():
    bar = OhlcBarOut.model_validate(
        {
            "date": "2024-03-14",
            "time": 1_710_400_000,
            "open": 4.11,
            "high": 4.25,
            "low": 4.08,
            "close": 4.21,
            "volume": 1_000,
        }
    )

    assert bar.time == 1_710_400_000


def test_fundamentals_model_accepts_the_empty_snapshot():
    """`.info` is scraped and often near-empty; {} means "nothing to show"."""
    assert FundamentalsOut.model_validate({}).name is None


def test_fundamentals_model_accepts_a_partial_snapshot():
    fundamentals = FundamentalsOut.model_validate(
        {"name": "Banco Santander", "sector": "Financial Services", "trailing_pe": 6.4}
    )

    assert fundamentals.trailing_pe == 6.4
    assert fundamentals.beta is None
