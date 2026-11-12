"""Living World read model: one building per ISIN, unknown stays unknown, no network."""

import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.living_world import router
from backend.database import get_db
from backend.models import (
    Account,
    Base,
    Broker,
    ListingProfile,
    PriceCache,
    SegmentReport,
    Transaction,
    TransactionType,
)
from backend.services import living_world as lw
from backend.services import portfolio_service as svc
from backend.services.auth_service import create_access_token, create_user

A = "ES0000000001"
B = "ES0000000002"
C = "IE0000000003"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.fixture
def prices(monkeypatch):
    """Prices the portfolio service 'fetches': set `prices.value` before the call."""
    box = type("Box", (), {"value": {}})()
    monkeypatch.setattr(svc, "fetch_and_cache_prices", lambda _db, _isins: dict(box.value))
    return box


def _user(db, email="ana@example.com"):
    return create_user(db, email=email, name="Ana", password="long enough", accepted_terms=True)


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


def _account(db, user, broker=Broker.ING, account_id="acct"):
    account = Account(user_id=user.id, broker=broker.value, account_id=account_id, name=account_id)
    db.add(account)
    db.flush()
    return account


def _buy(db, account, isin, net="100", qty="1"):
    db.add(
        Transaction(
            account_id=account.id,
            type=TransactionType.BUY.value,
            trade_date=date(2024, 1, 1),
            isin=isin,
            ticker="TST",
            name=f"Asset {isin}",
            country="España",
            quantity=Decimal(qty),
            price=Decimal("1"),
            currency="EUR",
            exchange_rate=Decimal("1"),
            gross_amount=abs(Decimal(net)),
            fees=Decimal("0"),
            withholding_tax=Decimal("0"),
            net_amount_eur=Decimal(net),
        )
    )


def _spinoff(db, account, isin):
    """A SPINOFF with zero amount is a holding whose cost is unknown."""
    db.add(
        Transaction(
            account_id=account.id,
            type=TransactionType.SPINOFF.value,
            trade_date=date(2024, 1, 1),
            isin=isin,
            ticker="TST",
            name=f"Asset {isin}",
            country="España",
            quantity=Decimal("1"),
            price=Decimal("0"),
            currency="EUR",
            exchange_rate=Decimal("1"),
            gross_amount=Decimal("0"),
            fees=Decimal("0"),
            withholding_tax=Decimal("0"),
            net_amount_eur=Decimal("0"),
        )
    )


def _world(client, user):
    res = client.get("/api/living-world/world", headers=_auth(user))
    assert res.status_code == 200, res.text
    return res.json()


def _by_isin(world):
    return {a["isin"]: a for a in world["assets"]}


def test_requires_a_session(client):
    assert client.get("/api/living-world/world").status_code == 401


def test_empty_portfolio_is_an_empty_world(db, client):
    user = _user(db)
    world = _world(client, user)
    assert world["assets"] == []
    assert world["summary"]["positions"] == 0
    assert world["summary"]["valuation_complete"] is True
    assert world["summary"]["total_market_value"] == 0.0  # known: nothing held, as the summary says
    assert world["summary"]["prices_as_of"] is None


def test_one_building_per_isin_across_brokers(db, client, prices):
    user = _user(db)
    _buy(db, _account(db, user, Broker.ING, "a"), A, "100")
    _buy(db, _account(db, user, Broker.TR, "b"), A, "300")
    db.commit()
    prices.value = {A: Decimal("200")}

    world = _world(client, user)

    [asset] = world["assets"]
    assert asset["isin"] == A
    assert asset["brokers"] == ["ING", "TR"]
    assert asset["market_value_eur"] == 400.0
    assert asset["total_cost_eur"] == 400.0
    assert asset["weight_pct"] == 100.0
    assert asset["day_change_pct"] is None  # Phase 2 stores the previous close


def test_unknown_cost_and_missing_price_stay_null(db, client, prices):
    user = _user(db)
    acct = _account(db, user)
    _buy(db, acct, A, "100")
    _spinoff(db, acct, B)
    _buy(db, acct, C, "50")
    db.commit()
    prices.value = {A: Decimal("150"), B: Decimal("10")}  # C has no price

    world = _world(client, user)
    assets = _by_isin(world)

    assert assets[B]["total_cost_eur"] is None
    assert assets[B]["unrealized_pl_eur"] is None
    assert assets[B]["market_value_eur"] == 10.0
    assert assets[C]["market_value_eur"] is None
    assert assets[C]["weight_pct"] is None
    assert assets[C]["total_cost_eur"] == 50.0
    summary = world["summary"]
    assert summary["valuation_complete"] is False
    assert summary["total_market_value"] is None  # one unknown price: no partial subtotal
    assert (summary["positions"], summary["valued"], summary["cost_known"]) == (3, 2, 2)


def test_complete_valuation_publishes_the_total_and_the_price_date(db, client, prices):
    user = _user(db)
    acct = _account(db, user)
    _buy(db, acct, A, "100")
    _buy(db, acct, B, "100")
    db.add(PriceCache(isin=A, price=Decimal("100"), fetched_date=date(2026, 11, 6)))
    db.add(PriceCache(isin=B, price=Decimal("50"), fetched_date=date(2026, 11, 7)))
    db.commit()
    prices.value = {A: Decimal("100"), B: Decimal("50")}

    summary = _world(client, user)["summary"]

    assert summary["valuation_complete"] is True
    assert summary["total_market_value"] == 150.0
    assert summary["prices_as_of"] == "2026-11-07"


def test_isin_without_any_sector_is_unclassified(db, client, prices):
    user = _user(db)
    _buy(db, _account(db, user), A)
    db.commit()
    prices.value = {A: Decimal("10")}

    [asset] = _world(client, user)["assets"]

    assert asset["classified"] is False
    assert asset["sector"] is None
    assert asset["asset_type"] == "equity"
    assert _world(client, user)["summary"]["classified"] == 0


def test_listing_profile_sets_type_and_sector(db, client, prices):
    user = _user(db)
    acct = _account(db, user)
    for isin in (A, B, C):
        _buy(db, acct, isin)
    db.add_all(
        [
            ListingProfile(isin=A, ticker="A", quote_type="EQUITY", sector="Technology"),
            ListingProfile(isin=B, ticker="B", quote_type="ETF", sector="Technology"),
            ListingProfile(isin=C, ticker="C", quote_type=None, sector=None),  # Yahoo gave nothing
        ]
    )
    db.commit()
    prices.value = {A: Decimal("10"), B: Decimal("10"), C: Decimal("10")}

    assets = _by_isin(_world(client, user))

    assert (assets[A]["asset_type"], assets[A]["sector"], assets[A]["classified"]) == (
        "equity",
        "Technology",
        True,
    )
    # An ETF's "sector" is not one: it is a fund pavilion, classified, with no sector.
    assert (assets[B]["asset_type"], assets[B]["sector"], assets[B]["classified"]) == (
        "etf",
        None,
        True,
    )
    assert assets[C]["classified"] is False


def test_annual_report_gives_the_sector_when_there_is_no_profile(db, client, prices):
    user = _user(db)
    _buy(db, _account(db, user), A)
    lines = [
        {"axis": "business", "label": "Stores", "category": "consumer_discretionary", "value": "80"},
        {"axis": "business", "label": "Online", "category": "technology", "value": "15"},
        {"axis": "business", "label": "Other", "category": "unassigned", "value": "5"},
        {"axis": "geography", "label": "Spain", "category": "spain", "value": "100"},
    ]
    db.add(
        SegmentReport(
            isin=A,
            fiscal_year=2025,
            period_end=date(2025, 12, 31),
            source="esef",
            filing_id="f1",
            source_url="https://example.com/f1",
            currency="EUR",
            total_revenue=Decimal("100"),
            lines=json.dumps(lines),
        )
    )
    db.commit()
    prices.value = {A: Decimal("10")}

    [asset] = _world(client, user)["assets"]

    assert asset["sector"] == "Consumer Cyclical"  # Yahoo spelling the classifier reads
    assert asset["classified"] is True


def test_curated_override_is_sent_and_counts_as_classified(db, client, prices, monkeypatch):
    user = _user(db)
    _buy(db, _account(db, user), A)
    db.commit()
    prices.value = {A: Decimal("10")}
    monkeypatch.setitem(lw.ARCHETYPE_OVERRIDES, A, "semis")

    [asset] = _world(client, user)["assets"]

    assert asset["archetype_override"] == "semis"
    assert asset["classified"] is True


def test_a_user_only_sees_their_own_world(db, client, prices):
    ana = _user(db)
    bob = _user(db, "bob@example.com")
    _buy(db, _account(db, ana, account_id="ana"), A)
    _buy(db, _account(db, bob, account_id="bob"), B)
    db.commit()
    prices.value = {A: Decimal("10"), B: Decimal("10")}

    assert [a["isin"] for a in _world(client, ana)["assets"]] == [A]
    assert [a["isin"] for a in _world(client, bob)["assets"]] == [B]


def test_no_yahoo_call_is_made_by_the_read_model(db, client, prices, monkeypatch):
    """The endpoint only reads: the sector lookup that needs Yahoo is the exposure refresh's."""
    user = _user(db)
    _buy(db, _account(db, user), A)
    db.commit()
    prices.value = {A: Decimal("10")}

    def boom(*_a, **_k):
        raise AssertionError("Living World must not call Yahoo")

    monkeypatch.setattr(lw.listing, "fetch", boom)
    monkeypatch.setattr(lw.listing, "refresh", boom)

    assert len(_world(client, user)["assets"]) == 1


D = "US0000000004"


def _row(isin, day, price, previous):
    return PriceCache(
        isin=isin,
        price=Decimal(price),
        original_price=Decimal(price),
        previous_close=Decimal(previous) if previous is not None else None,
        fetched_date=day,
    )


def test_day_change_comes_from_the_stored_previous_close(db, client, prices):
    user = _user(db)
    acct = _account(db, user)
    for isin in (A, B, C, D):
        _buy(db, acct, isin, "100")
    today, earlier = date(2026, 11, 12), date(2026, 11, 10)
    db.add_all([
        _row(A, earlier, "90", "99"),  # superseded by today's row below
        _row(A, today, "102", "100"),
        _row(B, earlier, "50", "40"),  # could not be refreshed today: another day's move
        _row(C, today, "10", None),  # written before the column existed
        _row(D, today, "200", "100"),  # +100 %: a Yahoo slip, not a session
    ])
    db.commit()
    prices.value = {A: Decimal("102"), B: Decimal("50"), C: Decimal("10"), D: Decimal("200")}

    assets = _by_isin(_world(client, user))

    assert assets[A]["day_change_pct"] == 2.0
    assert assets[B]["day_change_pct"] is None
    assert assets[C]["day_change_pct"] is None
    assert assets[D]["day_change_pct"] is None


def test_a_falling_day_is_negative_and_a_zero_previous_close_is_unknown():
    day = date(2026, 11, 12)
    assert lw._day_change_pct(_row(A, day, "97.5", "100"), day) == -2.5
    assert lw._day_change_pct(_row(A, day, "10", "0"), day) is None
    assert lw._day_change_pct(None, day) is None


# ── real events: the last week's facts, nothing invented ───────────────────────

TODAY = date(2026, 11, 12)


def _tx(db, account, isin, kind, day, qty="1", net="100", currency="EUR", ticker="TST"):
    db.add(
        Transaction(
            account_id=account.id,
            type=kind.value,
            trade_date=day,
            isin=isin,
            ticker=ticker,
            name=f"Asset {isin}",
            country="España",
            quantity=Decimal(qty),
            price=Decimal("1"),
            currency=currency,
            exchange_rate=Decimal("1"),
            gross_amount=abs(Decimal(net)),
            fees=Decimal("0"),
            withholding_tax=Decimal("0"),
            net_amount_eur=Decimal(net),
        )
    )


def _events(db, user):
    return {e["id"]: e for e in lw.build_world(db, user.id, today=TODAY)["events"]}


def test_ledger_entries_of_the_last_week_become_events(db, prices):
    user = _user(db)
    acct = _account(db, user, broker=Broker.IBKR)
    _tx(db, acct, A, TransactionType.BUY, date(2026, 11, 10), qty="10", net="-1000")
    _tx(db, acct, B, TransactionType.BUY, date(2026, 1, 1), qty="10", net="-500")
    _tx(db, acct, B, TransactionType.SELL, date(2026, 11, 11), qty="4", net="300")
    _tx(db, acct, C, TransactionType.BUY, date(2026, 1, 1), qty="2", net="-200")
    _tx(db, acct, C, TransactionType.SELL, date(2026, 11, 9), qty="2", net="250")
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2026, 11, 12), qty="0", net="8.10", currency="USD")
    _tx(db, acct, A, TransactionType.BUY, date(2026, 11, 4), qty="1", net="-10")  # 8 days ago
    db.commit()

    events = _events(db, user)
    by_type = {e["event_type"]: e for e in events.values()}

    assert set(by_type) == {"position_added", "position_reduced", "position_closed", "dividend_paid"}
    assert len(events) == 4  # the buy of 8 days ago is outside the week
    assert by_type["position_added"]["metrics"] == {"quantity": 10.0, "value_eur": 1000.0, "account": "IBKR"}
    assert by_type["position_reduced"]["isin"] == B  # 6 of 10 still held
    assert by_type["position_closed"]["isin"] == C  # nothing left anywhere
    dividend = by_type["dividend_paid"]
    assert dividend["metrics"]["net_eur"] == 8.1
    assert dividend["metrics"]["currency"] == "USD"
    assert dividend["confidence"] == "verified"
    # Newest first.
    assert [e["occurred_on"] for e in lw.build_world(db, user.id, today=TODAY)["events"]] == sorted(
        (e["occurred_on"] for e in events.values()), reverse=True
    )


def test_daily_moves_of_two_percent_or_more_become_derived_events(db, prices):
    user = _user(db)
    acct = _account(db, user)
    for isin in (A, B, C, D):
        _buy(db, acct, isin, "100")
    db.add_all([
        _row(A, TODAY, "103", "100"),  # +3 %: an event
        _row(A, date(2026, 11, 11), "95", "100"),  # −5 % yesterday: its own event
        _row(B, TODAY, "101", "100"),  # +1 %: noise
        _row(C, TODAY, "200", "100"),  # +100 %: a Yahoo slip, not an event
        _row(D, date(2026, 11, 1), "90", "100"),  # outside the week
    ])
    db.commit()
    prices.value = {A: Decimal("103"), B: Decimal("101"), C: Decimal("200"), D: Decimal("90")}

    events = _events(db, user)

    assert set(events) == {f"px:{A}:2026-11-12", f"px:{A}:2026-11-11"}
    up = events[f"px:{A}:2026-11-12"]
    assert up["event_type"] == "price_move_up"
    assert up["confidence"] == "derived"
    assert up["metrics"]["change_pct"] == 3.0
    assert events[f"px:{A}:2026-11-11"]["event_type"] == "price_move_down"


def test_events_are_the_users_own(db, client, prices):
    ana, bea = _user(db), _user(db, "bea@example.com")
    _tx(db, _account(db, bea, account_id="b"), A, TransactionType.BUY, date.today(), net="-10")
    db.commit()

    assert _world(client, ana)["events"] == []
    assert [e["event_type"] for e in _world(client, bea)["events"]] == ["position_added"]


# ── closed positions: kept as ruins, with the ledger's facts ────────────────────


def test_a_sold_out_position_comes_back_closed_with_its_ledger_figures(db, client, prices):
    user = _user(db)
    acct = _account(db, user, broker=Broker.IBKR)
    _tx(db, acct, A, TransactionType.BUY, date(2025, 1, 10), qty="10", net="-1000", ticker="AAA")
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2025, 6, 1), qty="0", net="25.50", ticker="AAA")
    _tx(db, acct, A, TransactionType.SELL, date(2025, 9, 3), qty="10", net="1200", ticker="AAA")
    _buy(db, acct, B, "100")
    db.commit()
    prices.value = {B: Decimal("100")}

    world = _world(client, user)
    assets = _by_isin(world)

    ruin = assets[A]
    assert ruin["status"] == "closed"
    assert ruin["closed_on"] == "2025-09-03"
    assert (ruin["invested_eur"], ruin["sold_eur"], ruin["dividends_eur"]) == (1000.0, 1200.0, 25.5)
    assert ruin["market_value_eur"] is None and ruin["weight_pct"] is None
    assert ruin["brokers"] == ["IBKR"]
    assert assets[B]["status"] == "open" and assets[B]["invested_eur"] is None
    assert world["summary"]["positions"] == 1
    assert world["summary"]["closed"] == 1


def test_a_new_isin_of_a_held_company_is_not_a_ruin(db, client, prices):
    """A split or an exchange gives the same ticker a new ISIN: the old one was not sold off."""
    user = _user(db)
    acct = _account(db, user)
    _tx(db, acct, A, TransactionType.BUY, date(2024, 1, 1), qty="1", net="-100")
    _tx(db, acct, A, TransactionType.SELL, date(2024, 6, 1), qty="1", net="110")
    _buy(db, acct, B, "100")  # same "TST" ticker as A, still held
    db.commit()
    prices.value = {B: Decimal("100")}

    assert set(_by_isin(_world(client, user))) == {B}


def test_a_position_that_left_without_a_sale_is_not_drawn(db, client, prices):
    user = _user(db)
    acct = _account(db, user)
    _tx(db, acct, A, TransactionType.BUY, date(2024, 1, 1), qty="1", net="-100")
    db.add(
        Transaction(
            account_id=acct.id, type=TransactionType.CORPORATE_ACTION.value,
            trade_date=date(2024, 3, 1), isin=A, ticker="OLD", name="Asset A", country="España",
            quantity=Decimal("-1"), price=Decimal("0"), currency="EUR", exchange_rate=Decimal("1"),
            gross_amount=Decimal("0"), fees=Decimal("0"), withholding_tax=Decimal("0"),
            net_amount_eur=Decimal("0"),
        )
    )
    db.commit()

    world = lw.build_world(db, user.id, today=TODAY)
    # No SELL: FinView cannot say when or how it closed, so it is not drawn as sold.
    assert all(a["isin"] != A or a["status"] == "open" for a in world["assets"])
    assert world["summary"]["closed"] == 0
