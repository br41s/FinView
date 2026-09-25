"""Regression tests for the geo auditor's +7d resolution + rule-learning loop.

The bug (fixed): chk.horizon reads back from the DB as a GeoHorizon *member*
(Enum values_callable, no str mixin), so `chk.horizon == "7d"` was always False
and the +7d checkpoint never resolved the signal — every signal stayed ACTIVE
forever, and _update_rule_stats (same branch) never ran. The test MUST round-trip
the checkpoint through a DB read so horizon is a member; an in-session string
checkpoint would not reproduce the bug.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base,
    GeoCheckpoint,
    GeoHorizon,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
    GeoSignalTicker,
)
from backend.services.geo import auditor


def _status(signal) -> str:
    """signal.status reads back as a GeoSignalStatus member after a DB round-trip
    (same enum boundary as the bug under test) — normalize to its value."""
    return getattr(signal.status, "value", signal.status)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _mature_signal(db, monkeypatch, horizon: str, *, direction="bullish", price_now=110.0):
    """Create an active signal with one already-due checkpoint at `horizon`,
    round-tripped through the DB so checkpoint.horizon is an enum member.
    Stubs price fetch so the basket scores CORRECT (bull thesis, price up)."""
    past = datetime.now(timezone.utc) - timedelta(days=8)
    signal = GeoSignal(
        user_id=1,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id="ev-resolve",
        headline="M6.4 quake near Antofagasta",
        location="chile",
        lat=-23.0,
        lng=-70.0,
        importance=78,
        confidence=0.82,
        risk_score=7.6,
        direction="bearish",
        status=GeoSignalStatus.ACTIVE.value,
        created_at=past,
        matched_rule_ids=json.dumps(["eq-chile-copper"]),
    )
    db.add(signal)
    db.flush()
    signal.tickers.append(
        GeoSignalTicker(symbol="COPX", direction=direction, price_at_signal=100.0)
    )
    db.add(
        GeoCheckpoint(
            user_id=1,
            signal_id=signal.id,
            horizon=horizon,
            target_at=past + auditor._HORIZON_DELAYS[horizon],
        )
    )
    db.commit()
    # Force a fresh read so horizon comes back as GeoHorizon member (reproduces bug).
    db.expire_all()

    # Nine days of hourly bars sitting at price_now (± a hair, so a sigma exists
    # and the threshold calibrates at the floor): every horizon's target has a
    # bar, and a 10% move is readable while a 0% one is not.
    start = datetime.now(timezone.utc) - timedelta(days=9)
    bars = [
        (start + timedelta(hours=i), price_now * (1 + (0.0001 if i % 2 else -0.0001)))
        for i in range(9 * 24)
    ]
    monkeypatch.setattr(
        auditor, "fetch_price_series", lambda symbols, budget=None, **kw: {"COPX": bars}
    )
    return signal.id


def test_checkpoint_horizon_reads_back_as_enum_member(db, monkeypatch):
    """Guards the premise: a DB-read horizon is a GeoHorizon member, not a str,
    so the old `== "7d"` comparison is genuinely False."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value)
    chk = db.query(GeoCheckpoint).one()
    assert chk.horizon is GeoHorizon.D7
    assert chk.horizon != "7d"  # the exact trap the fix works around


def test_final_horizon_resolves_signal_and_updates_rule_stats(db, monkeypatch):
    db.add(
        GeoRuleStat(rule_id="eq-chile-copper", category="earthquake", base_confidence=0.82)
    )
    db.commit()
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D7.value)

    n = auditor.evaluate_pending(db, user_id=1)

    assert n == 1
    signal = db.get(GeoSignal, signal_id)
    assert _status(signal) == GeoSignalStatus.RESOLVED.value

    stat = db.get(GeoRuleStat, "eq-chile-copper")
    assert stat.total_signals == 1
    assert stat.correct_signals == 1  # bull thesis + price up = correct
    assert float(stat.accuracy) == 1.0
    # (1.0 − 0.5) × 0.6 × (1/10 of the evidence in) — one hit is not a promotion
    assert float(stat.confidence_mod) == pytest.approx(0.03)


def test_basket_scores_correct_on_db_read_direction(db, monkeypatch):
    """_score_basket compares t.direction, which reads back as a GeoDirection member;
    a bullish ticker whose price rose must score CORRECT (guards the same enum trap)."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value, direction="bullish", price_now=110.0)
    auditor.evaluate_pending(db, user_id=1)
    chk = db.query(GeoCheckpoint).one()
    assert float(chk.score) == 100.0  # 1/1 non-neutral tickers moved as predicted


def test_basket_scores_incorrect_when_price_moves_against_thesis(db, monkeypatch):
    """A bullish ticker whose price fell scores INCORRECT — proves direction is
    actually read, not that everything trivially passes."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value, direction="bullish", price_now=90.0)
    auditor.evaluate_pending(db, user_id=1)
    chk = db.query(GeoCheckpoint).one()
    assert float(chk.score) == 0.0


def test_non_final_horizon_evaluates_but_leaves_signal_active(db, monkeypatch):
    """A matured +1d checkpoint scores an outcome but must NOT resolve the signal."""
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D1.value)

    n = auditor.evaluate_pending(db, user_id=1)

    assert n == 1
    chk = db.query(GeoCheckpoint).one()
    assert chk.outcome is not None
    signal = db.get(GeoSignal, signal_id)
    assert _status(signal) == GeoSignalStatus.ACTIVE.value


# ── A flat price is undetermined, not wrong ──────────────────────────


def _ticker(symbol="XLE", direction="bullish", price_at_signal=100.0):
    return GeoSignalTicker(
        symbol=symbol, direction=direction, price_at_signal=price_at_signal, resolved=True
    )


def _basket(*tickers):
    signal = GeoSignal(
        user_id=1,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id="ev-score",
        headline="M6.4 quake",
        location="chile",
        lat=-23.0,
        lng=-70.0,
        importance=60,
        confidence=0.7,
        risk_score=6,
        direction="bullish",
        status="active",
    )
    for t in tickers:
        signal.tickers.append(t)
    return signal


def test_an_unmoved_price_is_not_scored_as_a_miss():
    """The +1h and +6h checkpoints were unwinnable.

    prices.py returns the last *daily close*, so an intraday checkpoint compares
    that close against itself: change is exactly 0.00%. That counted in the
    denominator without ever counting as correct, so every basket scored 0 and
    both intraday horizons went red by construction.
    """
    signal = _basket(_ticker(price_at_signal=100.0))

    score, detail, total = auditor._score_basket(signal, {"XLE": 100.0})

    assert score is None, "a flat close is undetermined, not incorrect"
    assert total == 0
    assert "XLE: +0.00%" in detail, "the move is still reported"


def test_a_move_inside_the_dead_zone_is_excluded_too():
    signal = _basket(_ticker(price_at_signal=100.0))
    score, _, total = auditor._score_basket(signal, {"XLE": 100.05})
    assert (score, total) == (None, 0)


def test_only_the_tickers_that_moved_form_the_denominator():
    """One real hit and one flat ticker is 100%, not 50%."""
    signal = _basket(
        _ticker("XLE", "bullish", 100.0),
        _ticker("USO", "bullish", 50.0),
    )

    score, _, total = auditor._score_basket(signal, {"XLE": 103.0, "USO": 50.0})

    assert total == 1
    assert score == 100.0


def test_a_real_move_the_wrong_way_still_counts_against_the_thesis():
    signal = _basket(_ticker("XLE", "bearish", 100.0))
    score, _, total = auditor._score_basket(signal, {"XLE": 104.0})
    assert (score, total) == (0.0, 1)


def test_an_unmeasurable_resolution_does_not_punish_the_rules(db, monkeypatch):
    """Silence is not failure: a +7d checkpoint that cannot be scored must leave
    confidence_mod alone rather than charging the rule 0.03 for it."""
    db.add(GeoRuleStat(rule_id="eq-chile-copper", category="earthquake",
                       base_confidence=0.7, confidence_mod=0))
    # price_now == price_at_signal: nothing moved, so nothing is measurable.
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value, price_now=100.0)

    auditor.evaluate_pending(db, user_id=1)

    stat = db.get(GeoRuleStat, "eq-chile-copper")
    assert float(stat.confidence_mod) == 0.0
    assert stat.total_signals == 0
    # The signal still resolves — it just teaches nothing.
    assert _status(db.query(GeoSignal).one()) == "resolved"


# ── v2: the bar at the target, noise-scaled thresholds, no burning ─────


def _series(start: datetime, step: timedelta, closes: list[float]):
    return [(start + step * i, c) for i, c in enumerate(closes)]


def test_the_checkpoint_reads_the_bar_at_its_target_not_the_last_bar():
    start = datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc)
    bars = _series(start, timedelta(minutes=5), [100.0, 101.0, 102.0, 103.0, 104.0])
    assert auditor._as_of(bars, start + timedelta(minutes=12)) == 102.0
    assert auditor._as_of(bars, start - timedelta(minutes=1)) is None
    assert auditor._as_of(bars, start + timedelta(days=3)) == 104.0


def test_threshold_scales_with_the_tickers_own_noise():
    start = datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc)
    quiet = _series(start, timedelta(minutes=5), [100 + 0.02 * (i % 3) for i in range(200)])
    wild = _series(start, timedelta(minutes=5), [100 + 3.0 * ((i % 7) - 3) for i in range(200)])
    q = auditor._threshold_pct(quiet, None, "1h")
    w = auditor._threshold_pct(wild, None, "1h")
    assert q == auditor._MIN_MOVE_PCT  # floor: quieter than the floor
    assert w > 1.0  # a ticker that swings 3% needs a real move to be readable
    # No series → no threshold, not the floor: uncalibrated is unmeasurable.
    assert auditor._threshold_pct(None, None, "3d") is None
    assert auditor._threshold_pct(wild[:5], None, "1h") is None
    # Daily horizons calibrate from the same intraday series (one session lag).
    assert auditor._threshold_pct(wild, None, "1d") is not None


def test_ties_are_neutral_not_correct():
    assert auditor._outcome(50.0) == "NEUTRAL"
    assert auditor._outcome(66.67) == "CORRECT"
    assert auditor._outcome(33.33) == "INCORRECT"
    assert auditor._outcome(None) == "NEUTRAL"


def test_intraday_horizons_are_in_trading_time(db):
    """A signal born on a Sunday gets its +1h checkpoint one session-hour into
    Monday, not at 04:00 Sunday against Friday's close."""
    signal = _basket(_ticker())
    signal.created_at = datetime(2026, 9, 20, 3, 0, tzinfo=timezone.utc)  # Sunday
    db.add(signal)
    db.flush()
    auditor.create_checkpoints(db, signal)
    db.commit()
    by = {getattr(c.horizon, "value", c.horizon): c.target_at for c in signal.checkpoints}
    h1 = by["1h"].replace(tzinfo=timezone.utc) if by["1h"].tzinfo is None else by["1h"]
    assert h1 == datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)  # Mon 10:30 ET
    assert by["1d"].replace(tzinfo=None) == datetime(2026, 9, 21, 3, 0)


def test_no_price_leaves_the_checkpoint_pending_until_give_up(db, monkeypatch):
    """A Yahoo stall used to burn every due window as NEUTRAL forever."""
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D1.value)
    monkeypatch.setattr(auditor, "fetch_price_series", lambda *a, **k: {})
    chk = db.query(GeoCheckpoint).one()
    chk.target_at = datetime.now(timezone.utc) - timedelta(hours=1)  # due, recently
    db.commit()

    assert auditor.evaluate_pending(db, user_id=1) == 0
    chk = db.query(GeoCheckpoint).one()
    assert chk.outcome is None and chk.evaluated_at is None

    # 7 days later with still no bars: recorded as unmeasurable, not retried forever.
    chk.target_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    assert auditor.evaluate_pending(db, user_id=1) == 1
    chk = db.query(GeoCheckpoint).one()
    assert getattr(chk.outcome, "value", chk.outcome) == "NEUTRAL"
    assert "sin datos" in chk.detail
    assert _status(db.get(GeoSignal, signal_id)) == "active"  # D1 never resolves


def test_the_daily_series_backs_a_target_older_than_the_intraday_window(db, monkeypatch):
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D7.value)
    now = datetime.now(timezone.utc)
    intraday = _series(now - timedelta(hours=10), timedelta(minutes=5), [120.0] * 50)
    daily = _series(now - timedelta(days=20), timedelta(days=1), [100.0] * 15 + [110.0] * 5)
    calls: list[tuple[str, list[str]]] = []

    def series(symbols, budget=None, *, period, interval):
        calls.append((interval, list(symbols)))
        return {"COPX": intraday if interval == "5m" else daily}

    monkeypatch.setattr(auditor, "fetch_price_series", series)
    auditor.evaluate_pending(db, user_id=1)
    chk = db.query(GeoCheckpoint).one()
    # target (+7d, i.e. yesterday) is before the intraday window → daily close 110, not 120
    assert "COPX: +10.00%" in chk.detail
    assert _status(db.get(GeoSignal, signal_id)) == "resolved"
    assert ("1d", ["COPX"]) in calls  # daily fetched because the target predates the window


def test_a_priced_ticker_without_a_calibrated_threshold_is_unmeasurable(db, monkeypatch):
    """Price from a 5-bar series, no sigma possible → pending, not a coin flip at 0.1%."""
    _mature_signal(db, monkeypatch, GeoHorizon.D1.value)
    chk = db.query(GeoCheckpoint).one()
    chk.target_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    now = datetime.now(timezone.utc)
    thin = _series(now - timedelta(hours=2), timedelta(minutes=5), [100.0, 101.0, 103.0, 104.0])
    monkeypatch.setattr(auditor, "fetch_price_series", lambda *a, **k: {"COPX": thin})
    assert auditor.evaluate_pending(db, user_id=1) == 0
    assert db.query(GeoCheckpoint).one().outcome is None


def test_the_daily_series_is_only_fetched_when_the_intraday_one_cannot_serve(db, monkeypatch):
    _mature_signal(db, monkeypatch, GeoHorizon.D1.value)
    chk = db.query(GeoCheckpoint).one()
    chk.target_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    now = datetime.now(timezone.utc)
    intraday = _series(now - timedelta(days=9), timedelta(minutes=5), [100.0 + (i % 5) * 0.3 for i in range(400)])
    calls: list[str] = []

    def series(symbols, budget=None, *, period, interval):
        calls.append(interval)
        return {"COPX": intraday}

    monkeypatch.setattr(auditor, "fetch_price_series", series)
    auditor.evaluate_pending(db, user_id=1)
    assert calls == ["5m"]


def test_checkpoint_targets_are_stored_naive_utc(db):
    signal = _basket(_ticker())
    signal.created_at = datetime(2026, 9, 20, 3, 0, tzinfo=timezone.utc)
    db.add(signal)
    db.flush()
    auditor.create_checkpoints(db, signal)
    assert all(c.target_at.tzinfo is None for c in signal.checkpoints)


def test_a_thin_intraday_series_falls_back_to_the_daily_sigma(db, monkeypatch):
    """TTF=F: ~36 five-minute bars in ten days. Without the daily fallback its
    daily horizons had no sigma and the leg never reached +7d."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value)
    now = datetime.now(timezone.utc)
    thin = _series(now - timedelta(days=9), timedelta(hours=6), [100.0 + (i % 3) * 0.4 for i in range(36)])
    daily = _series(now - timedelta(days=25), timedelta(days=1), [100.0 + (i % 4) * 0.8 for i in range(22)])
    calls: list[str] = []

    def series(symbols, budget=None, *, period, interval):
        calls.append(interval)
        return {"COPX": thin if interval == "5m" else daily}

    monkeypatch.setattr(auditor, "fetch_price_series", series)
    assert auditor._threshold_pct(thin, None, "7d") is None
    assert auditor._threshold_pct(thin, daily, "7d") is not None
    auditor.evaluate_pending(db, user_id=1)
    assert calls == ["5m", "1d"]
    assert db.query(GeoCheckpoint).one().outcome is not None
