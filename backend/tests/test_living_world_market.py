"""Living World events read from other features' stored data: each fires on its fact and
stays silent when the stored data cannot back it (a gap is never read as "it happened")."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import (
    Account,
    Base,
    Broker,
    GeoSignal,
    GeoSignalStatus,
    GeoSignalTicker,
    SegmentReport,
    SplitHistoryCache,
    TechnicalSignal,
    Transaction,
    TransactionType,
    ZonasClaveAnalysis,
    ZonasClaveWatchlistItem,
)
from backend.services.auth_service import create_user
from backend.services.geo.owner import geo_owner_id
from backend.services.living_world_market import market_events

TODAY = date(2026, 11, 12)
SINCE = TODAY - timedelta(days=7)
A, B = "ES0000000001", "ES0000000002"
NAMES = {A: "Alfa SA", B: "Beta SA"}
YAHOO = {A: "ALF.MC", B: "BET.MC"}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user(db):
    return create_user(db, email="ana@example.com", name="Ana", password="long enough", accepted_terms=True)


def _events(db, user, names=NAMES, yahoo=YAHOO):
    return market_events(db, user.id, names, yahoo, SINCE, TODAY)


def _types(events):
    return sorted((e["event_type"], e["isin"]) for e in events)


def _history(db, user, ticker, closes, volumes=None, end=TODAY):
    item = ZonasClaveWatchlistItem(user_id=user.id, ticker=ticker, name=ticker)
    db.add(item)
    db.flush()
    n = len(closes)
    bars = [
        {
            "date": (end - timedelta(days=round((n - 1 - i) * 365 / 252))).isoformat(),
            "open": c, "high": c, "low": c, "close": c,
            "volume": (volumes[i] if volumes else 1000),
        }
        for i, c in enumerate(closes)
    ]
    db.add(ZonasClaveAnalysis(watchlist_item_id=item.id, price_history=json.dumps(bars)))
    db.commit()


def _account(db, user, broker=Broker.IBKR):
    acct = Account(user_id=user.id, broker=broker.value, account_id="acct", name="acct")
    db.add(acct)
    db.flush()
    return acct


def _tx(db, acct, isin, kind, day, qty="0", net="0"):
    db.add(Transaction(
        account_id=acct.id, type=kind.value, trade_date=day, isin=isin, ticker="T", name=NAMES.get(isin, isin),
        country="España", quantity=Decimal(qty), price=Decimal("1"), currency="EUR",
        exchange_rate=Decimal("1"), gross_amount=abs(Decimal(net)), fees=Decimal("0"),
        withholding_tax=Decimal("0"), net_amount_eur=Decimal(net),
    ))


# ── 52-week extremes and volume, from Zonas Clave's stored history ─────────────


def test_a_close_above_a_full_year_is_a_52_week_high(db, user):
    _history(db, user, "ALF.MC", [10.0 + (i % 5) for i in range(260)] + [20.0])
    _history(db, user, "BET.MC", [10.0 + (i % 5) for i in range(260)] + [5.0])

    events = _events(db, user)

    assert ("week52_high", A) in _types(events)
    assert ("week52_low", B) in _types(events)
    high = next(e for e in events if e["event_type"] == "week52_high")
    assert high["metrics"]["close"] == 20.0 and high["metrics"]["previous_extreme"] == 14.0
    assert high["confidence"] == "derived"


def test_less_than_a_year_of_closes_says_nothing_about_52_weeks(db, user):
    _history(db, user, "ALF.MC", [10.0] * 100 + [20.0])
    assert not [e for e in _events(db, user) if e["event_type"].startswith("week52")]


def test_history_that_ended_before_the_week_raises_nothing(db, user):
    _history(db, user, "ALF.MC", [10.0] * 260 + [20.0], end=TODAY - timedelta(days=20))
    assert _events(db, user) == []


def test_unusual_volume_is_measured_against_the_sessions_before(db, user):
    _history(db, user, "ALF.MC", [10.0] * 30, volumes=[1000] * 29 + [3000])
    _history(db, user, "BET.MC", [10.0] * 30, volumes=[1000] * 29 + [2000])

    spikes = [e for e in _events(db, user) if e["event_type"] == "volume_spike"]

    assert [e["isin"] for e in spikes] == [A]
    assert spikes[0]["metrics"]["volume_ratio"] == 3.0


def test_a_ticker_outside_the_zonas_watchlist_gets_no_history_events(db, user):
    _history(db, user, "OTHER.MC", [10.0] * 260 + [20.0])
    assert _events(db, user) == []


# ── splits, shares received, dividends per share ──────────────────────────────


def test_a_split_in_the_week_is_an_event_for_every_isin_on_that_ticker(db, user):
    db.add(SplitHistoryCache(
        ticker="ALF.MC",
        splits=json.dumps([["2020-01-01", "2"], [(TODAY - timedelta(days=2)).isoformat(), "4"]]),
        fetched_at=datetime(2026, 11, 11),
    ))
    db.commit()

    splits = [e for e in _events(db, user) if e["event_type"] == "stock_split"]

    assert [(e["isin"], e["metrics"]["ratio"]) for e in splits] == [(A, 4.0)]
    assert splits[0]["confidence"] == "reported"


def test_shares_of_a_new_company_received_without_a_purchase(db, user):
    acct = _account(db, user)
    _tx(db, acct, A, TransactionType.SPINOFF, TODAY - timedelta(days=1), qty="12")
    # A reinvested dividend: shares of an ISIN already held, not a new company.
    _tx(db, acct, B, TransactionType.BUY, date(2025, 1, 1), qty="10", net="-100")
    _tx(db, acct, B, TransactionType.SPINOFF, TODAY - timedelta(days=1), qty="1")
    # Rights already sold off: not held any more.
    _tx(db, acct, "ES0000000099", TransactionType.SPINOFF, TODAY - timedelta(days=2), qty="5")
    db.commit()

    received = [e for e in _events(db, user) if e["event_type"] == "shares_received"]

    assert [(e["isin"], e["metrics"]["quantity"]) for e in received] == [(A, 12.0)]


def test_a_dividend_per_share_well_above_last_years_is_a_raise(db, user):
    acct = _account(db, user)
    _tx(db, acct, A, TransactionType.BUY, date(2024, 1, 1), qty="100", net="-1000")
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2025, 11, 10), net="50")  # 0.50 a share
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2026, 6, 10), net="20")  # interim: not compared
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2026, 11, 10), net="60")  # 0.60 a share
    _tx(db, acct, B, TransactionType.BUY, date(2024, 1, 1), qty="100", net="-1000")
    _tx(db, acct, B, TransactionType.DIVIDEND, date(2025, 11, 10), net="50")
    _tx(db, acct, B, TransactionType.DIVIDEND, date(2026, 11, 10), net="52")  # +4 %: noise
    db.commit()

    changes = [e for e in _events(db, user) if e["event_type"].startswith("dividend_")]

    assert [(e["event_type"], e["isin"]) for e in changes] == [("dividend_raised", A)]
    m = changes[0]["metrics"]
    assert (m["per_share_eur"], m["previous_per_share_eur"], m["change_pct"]) == (0.6, 0.5, 20.0)


def test_more_shares_is_not_a_bigger_dividend(db, user):
    """Twice the shares, twice the money: the same dividend per share, no event."""
    acct = _account(db, user)
    _tx(db, acct, A, TransactionType.BUY, date(2024, 1, 1), qty="100", net="-1000")
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2025, 11, 10), net="50")
    _tx(db, acct, A, TransactionType.BUY, date(2026, 3, 1), qty="100", net="-1200")
    _tx(db, acct, A, TransactionType.DIVIDEND, date(2026, 11, 10), net="100")
    db.commit()

    assert not [e for e in _events(db, user) if e["event_type"].startswith("dividend_")]


# ── annual reports, geo signals, Zonas Clave alerts ───────────────────────────


def test_an_annual_report_stored_this_week(db, user):
    db.add_all([
        SegmentReport(
            isin=A, fiscal_year=2025, period_end=date(2025, 12, 31), source="esef", filing_id="f",
            source_url="https://example.com/f", currency="EUR", total_revenue=Decimal("1"),
            lines="[]", created_at=datetime(2026, 11, 10, 9, 0),
        ),
        SegmentReport(
            isin=B, fiscal_year=2025, period_end=date(2025, 12, 31), source="esef", filing_id="g",
            source_url="https://example.com/g", currency="EUR", total_revenue=Decimal("1"),
            lines="[]", created_at=datetime(2026, 9, 1, 9, 0),
        ),
    ])
    db.commit()

    reports = [e for e in _events(db, user) if e["event_type"] == "annual_report"]

    assert [(e["isin"], e["metrics"]["fiscal_year"]) for e in reports] == [(A, 2025)]


def _geo(db, *, symbol, notified_at, headline="Huelga en el puerto", owner=None, direction="bearish"):
    signal = GeoSignal(
        user_id=owner if owner is not None else geo_owner_id(db), event_type="strike", display_category="conflict", source="gdelt",
        external_id=f"ev-{symbol}-{notified_at}", headline=headline, location="spain", country="spain",
        lat=40.0, lng=-3.0, importance=80, confidence=0.8, risk_score=7, direction="bearish",
        status=GeoSignalStatus.ACTIVE.value, created_at=datetime(2026, 11, 11, 8, 0),
        notified_at=notified_at, matched_rule_ids="[]",
    )
    db.add(signal)
    db.flush()
    signal.tickers.append(GeoSignalTicker(symbol=symbol, direction=direction, price_at_signal=10.0))


def test_a_geo_alert_sent_about_a_holding_keeps_its_moment(db, user):
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 11, 8, 30))
    _geo(db, symbol="BET.MC", notified_at=None)  # never sent out
    _geo(db, symbol="ZZZ", notified_at=datetime(2026, 11, 11, 8, 30))  # not a holding
    # Another account's own copy (pre-shared-owner history): /geo never reads it, nor does the town.
    _geo(db, symbol="BET.MC", notified_at=datetime(2026, 11, 11, 9, 0), owner=user.id)
    db.commit()

    geo = [e for e in _events(db, user) if e["event_type"] == "geo_alert"]

    assert [e["isin"] for e in geo] == [A]
    assert geo[0]["occurred_at"] == "2026-11-11T08:30:00Z"
    assert geo[0]["metrics"]["headline"] == "Huelga en el puerto"


def test_several_geo_alerts_about_one_holding_on_one_day_are_one_event(db, user):
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 10, 7, 0), headline="Huelga")
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 10, 15, 0), headline="Arancel",
         direction="bullish")
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 10, 11, 0), headline="Sequía")
    # Another day stays its own event.
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 11, 9, 0), headline="Cierre")
    db.commit()

    geo = {e["occurred_on"]: e for e in _events(db, user) if e["event_type"] == "geo_alert"}

    assert set(geo) == {date(2026, 11, 10), date(2026, 11, 11)}
    grouped = geo[date(2026, 11, 10)]
    assert grouped["id"] == f"geo:{A}:2026-11-10"
    assert grouped["occurred_at"] == "2026-11-10T15:00:00Z"  # the latest sending
    m = grouped["metrics"]
    assert m["signal_count"] == 3
    assert m["headline"] == "Arancel"
    assert m["headlines"] == "Arancel\nSequía\nHuelga"
    assert m["country"] == "spain" and m["importance"] == 80
    # The signals disagree on direction: unknown, not one of them picked.
    assert m["direction"] is None
    single = geo[date(2026, 11, 11)]["metrics"]
    assert single["signal_count"] == 1 and single["direction"] == "bearish"


def test_only_zonas_clave_alerts_the_user_was_sent(db, user):
    other = create_user(db, email="bea@example.com", name="Bea", password="long enough", accepted_terms=True)

    def signal(owner, ticker, alerted):
        db.add(TechnicalSignal(
            user_id=owner.id, ticker=ticker, zone_level=Decimal("10"), zone_type="soporte",
            price_at_signal=Decimal("10.1"), distance_pct=Decimal("1"), approach="from_above",
            direction="BEARISH", alerted=alerted, created_at=datetime(2026, 11, 11, 15, 0),
        ))

    signal(user, "ALF.MC", True)
    signal(user, "BET.MC", False)  # scored, never shown as an alert
    signal(other, "BET.MC", True)  # someone else's
    db.commit()

    zones = [e for e in _events(db, user) if e["event_type"] == "technical_signal"]

    assert [e["isin"] for e in zones] == [A]
    assert zones[0]["metrics"]["zone"] == "soporte"
    assert zones[0]["occurred_at"] == "2026-11-11T15:00:00Z"


def test_a_line_break_inside_a_headline_cannot_pose_as_another_signal(db, user):
    """Headlines are external text joined one per line: each is flattened first."""
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 11, 8, 0), headline="Huelga\nen el puerto")
    _geo(db, symbol="ALF.MC", notified_at=datetime(2026, 11, 11, 9, 0), headline="Cierre de frontera")
    db.commit()

    [geo] = [e for e in _events(db, user) if e["event_type"] == "geo_alert"]

    assert geo["metrics"]["signal_count"] == 2
    assert geo["metrics"]["headlines"].split("\n") == ["Cierre de frontera", "Huelga en el puerto"]
