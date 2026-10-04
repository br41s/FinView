"""The ladder — a basket read tier by tier instead of as one list.

A leg is stored with its own reading, a tier takes the state its legs give it,
and `/geo/accuracy` measures whether a confirmed narrow tier came with a
confirmed wider one. Nothing here moves a confidence: that lift is to be derived
from these measurements once there are enough of them, never set by hand.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import _ladder_accuracy, _serialize
from backend.database import _ADDITIVE_COLUMNS
from backend.models import (
    Base,
    GeoCheckpoint,
    GeoHorizon,
    GeoSignal,
    GeoSignalStatus,
    GeoSignalTicker,
)
from backend.services.geo import auditor, ladder
from backend.services.geo.ladder import leg_state, tier_states

# One instrument per tier: a Chilean bank, Chile's fund, exchange copper.
LOCAL, LOCAL_2, NATIONAL, WORLD = "BCH", "ENIC", "ECH", "HG=F"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── One leg ───────────────────────────────────────────────────────────


def test_a_leg_confirms_contradicts_or_says_nothing():
    assert leg_state("bearish", -3.0, 1.0) == "confirms"
    assert leg_state("bearish", +3.0, 1.0) == "contradicts"
    assert leg_state("bullish", +3.0, 1.0) == "confirms"
    assert leg_state("bullish", -3.0, 1.0) == "contradicts"


def test_a_move_inside_the_legs_own_noise_is_flat_not_wrong():
    assert leg_state("bearish", +0.9, 1.0) == "flat"
    assert leg_state("bearish", -1.0, 1.0) == "flat"  # at the threshold is still noise
    assert leg_state("neutral", -9.0, 1.0) == "flat"
    assert leg_state("", -9.0, 1.0) == "flat"


# ── One tier ──────────────────────────────────────────────────────────


def _states(*legs):
    return {s.tier: s.state for s in tier_states(legs)}


def test_tiers_come_narrowest_first_and_only_the_ones_the_basket_carries():
    got = tier_states([(WORLD, "confirms"), (NATIONAL, "confirms"), (LOCAL, "confirms")])
    assert [s.tier for s in got] == ["local", "national", "international"]
    assert [s.tier for s in tier_states([(WORLD, None)])] == ["international"]
    assert tier_states([]) == []


def test_a_tier_is_pending_until_one_of_its_legs_has_been_read():
    assert _states((LOCAL, None), (LOCAL_2, None)) == {"local": "pending"}
    assert _states((LOCAL, None), (LOCAL_2, "confirms")) == {"local": "confirmed"}


def test_a_tier_goes_the_way_most_of_its_legs_went():
    assert _states((LOCAL, "confirms"), (LOCAL_2, "flat")) == {"local": "confirmed"}
    assert _states((LOCAL, "contradicts"), (LOCAL_2, "flat")) == {"local": "contradicted"}
    (tier,) = tier_states([(LOCAL, "confirms"), (LOCAL_2, "confirms")])
    assert (tier.legs, tier.confirms, tier.contradicts) == (2, 2, 0)


def test_a_tie_or_a_tier_that_did_not_move_is_unreadable_not_confirmed():
    """The basket score's own rule: 1-for-2 is NEUTRAL, not half right."""
    assert _states((LOCAL, "confirms"), (LOCAL_2, "contradicts")) == {"local": "unreadable"}
    assert _states((LOCAL, "flat"), (LOCAL_2, "flat")) == {"local": "unreadable"}


def test_each_tier_is_read_on_its_own():
    assert _states((LOCAL, "confirms"), (NATIONAL, "contradicts"), (WORLD, None)) == {
        "local": "confirmed", "national": "contradicted", "international": "pending",
    }


def test_the_ladder_moves_no_confidence_yet():
    """The lift is derived from measured accuracy or not at all."""
    assert not [name for name in dir(ladder) if "lift" in name.lower() or "boost" in name.lower()]


# ── The auditor stores each leg's reading ─────────────────────────────


def _bars(level: float):
    start = datetime.now(timezone.utc) - timedelta(days=9)
    return [
        (start + timedelta(hours=i), level * (1 + (0.0001 if i % 2 else -0.0001)))
        for i in range(9 * 24)
    ]


def _signal(db, legs, *, age=timedelta(hours=30), with_final_checkpoint=False):
    """``legs`` is {symbol: direction}; every leg was priced at 100."""
    created = datetime.now(timezone.utc) - age
    signal = GeoSignal(
        user_id=1, event_type="earthquake", display_category="earthquake", source="usgs",
        external_id=f"ev-{created.timestamp()}", headline="quake", location="chile",
        country="chile", lat=-33.4, lng=-70.6, importance=50, confidence=0.8, risk_score=6,
        direction="bearish", status=GeoSignalStatus.ACTIVE.value, created_at=created,
        matched_rule_ids=json.dumps([]),
    )
    db.add(signal)
    db.flush()
    for symbol, direction in legs.items():
        signal.tickers.append(
            GeoSignalTicker(symbol=symbol, direction=direction, price_at_signal=100.0)
        )
    if with_final_checkpoint:
        db.add(GeoCheckpoint(
            user_id=1, signal_id=signal.id, horizon=GeoHorizon.D7.value,
            target_at=created + auditor._HORIZON_DELAYS[GeoHorizon.D7.value],
        ))
    db.commit()
    db.expire_all()
    return signal.id


def _prices(monkeypatch, levels):
    monkeypatch.setattr(
        auditor, "fetch_price_series",
        lambda symbols, budget=None, **kw: {s: _bars(v) for s, v in levels.items() if s in symbols},
    )


def _legs(db):
    return {
        t.symbol: (t.live_state, None if t.live_change_pct is None else float(t.live_change_pct),
                   t.final_state)
        for t in db.query(GeoSignalTicker).all()
    }


def test_every_audit_stores_how_each_leg_reads(db, monkeypatch):
    _signal(db, {LOCAL: "bearish", NATIONAL: "bearish", WORLD: "bullish"})
    _prices(monkeypatch, {LOCAL: 95.0, NATIONAL: 104.0, WORLD: 100.0})
    assert auditor.rate_active(db, user_id=1) == 1
    legs = _legs(db)
    assert legs[LOCAL][0] == "confirms" and legs[LOCAL][1] == pytest.approx(-5.0, abs=0.05)
    assert legs[NATIONAL][0] == "contradicts" and legs[NATIONAL][1] == pytest.approx(4.0, abs=0.05)
    assert legs[WORLD][0] == "flat"
    assert all(final is None for _s, _c, final in legs.values()), "+7d has not happened"


def test_a_leg_with_no_price_this_run_keeps_the_reading_it_had(db, monkeypatch):
    _signal(db, {LOCAL: "bearish", NATIONAL: "bearish"})
    _prices(monkeypatch, {LOCAL: 95.0, NATIONAL: 95.0})
    auditor.rate_active(db, user_id=1)
    _prices(monkeypatch, {LOCAL: 108.0})  # Yahoo returned nothing for the fund
    auditor.rate_active(db, user_id=1)
    legs = _legs(db)
    assert legs[LOCAL][0] == "contradicts"
    assert legs[NATIONAL][0] == "confirms", "a stall must not blank a leg"


def test_a_leg_never_read_is_null_which_is_not_flat(db, monkeypatch):
    _signal(db, {LOCAL: "bearish", NATIONAL: "bearish"})
    _prices(monkeypatch, {LOCAL: 95.0})
    auditor.rate_active(db, user_id=1)
    assert _legs(db)[NATIONAL] == (None, None, None)


def test_the_resolution_writes_each_legs_final_reading(db, monkeypatch):
    signal_id = _signal(
        db, {LOCAL: "bearish", NATIONAL: "bearish", WORLD: "bullish"},
        age=timedelta(days=8), with_final_checkpoint=True,
    )
    _prices(monkeypatch, {LOCAL: 94.0, NATIONAL: 97.0, WORLD: 93.0})
    assert auditor.evaluate_pending(db, user_id=1) == 1
    legs = _legs(db)
    assert {symbol: final for symbol, (_s, _c, final) in legs.items()} == {
        LOCAL: "confirms", NATIONAL: "confirms", WORLD: "contradicts",
    }
    assert db.get(GeoSignal, signal_id).status.value == "resolved"


# ── The API ───────────────────────────────────────────────────────────


def test_a_signal_is_served_with_its_ladder(db, monkeypatch):
    signal_id = _signal(db, {LOCAL: "bearish", LOCAL_2: "bearish", NATIONAL: "bearish",
                             WORLD: "bullish"})
    _prices(monkeypatch, {LOCAL: 95.0, LOCAL_2: 96.0, NATIONAL: 104.0})
    auditor.rate_active(db, user_id=1)
    out = _serialize(db.get(GeoSignal, signal_id), {})
    assert [(s.tier, s.state, s.legs, s.confirms, s.contradicts) for s in out.ladder] == [
        ("local", "confirmed", 2, 2, 0),
        ("national", "contradicted", 1, 0, 1),
        ("international", "pending", 1, 0, 0),
    ]
    by_symbol = {t.symbol: t for t in out.tickers}
    assert by_symbol[LOCAL].state == "confirms"
    assert by_symbol[LOCAL].liveChangePct == pytest.approx(-5.0, abs=0.05)
    assert by_symbol[WORLD].state is None and by_symbol[WORLD].liveChangePct is None


def test_once_resolved_the_final_reading_is_the_one_served(db):
    signal_id = _signal(db, {LOCAL: "bearish"})
    (leg,) = db.query(GeoSignalTicker).all()
    leg.live_state, leg.final_state = "contradicts", "confirms"
    db.commit()
    out = _serialize(db.get(GeoSignal, signal_id), {})
    assert out.tickers[0].state == "confirms"
    assert out.ladder[0].state == "confirmed"


def test_an_open_signal_not_read_yet_is_pending(db):
    out = _serialize(db.get(GeoSignal, _signal(db, {WORLD: "bullish"})), {})
    assert [(s.tier, s.state) for s in out.ladder] == [("international", "pending")]


def test_a_signal_resolved_before_legs_kept_a_reading_has_no_ladder(db):
    """It would otherwise show three rungs waiting for a price that never comes."""
    signal = db.get(GeoSignal, _signal(db, {LOCAL: "bearish", WORLD: "bullish"}))
    signal.status = GeoSignalStatus.RESOLVED.value
    db.commit()
    db.expire_all()
    assert _serialize(db.get(GeoSignal, signal.id), {}).ladder == []


def test_once_resolved_a_tier_never_read_is_unreadable_not_pending(db):
    signal_id = _signal(db, {LOCAL: "bearish", NATIONAL: "bearish"})
    signal = db.get(GeoSignal, signal_id)
    signal.status = GeoSignalStatus.RESOLVED.value
    next(t for t in signal.tickers if t.symbol == LOCAL).final_state = "confirms"
    db.commit()
    db.expire_all()
    out = _serialize(db.get(GeoSignal, signal_id), {})
    assert [(s.tier, s.state) for s in out.ladder] == [
        ("local", "confirmed"), ("national", "unreadable"),
    ]


# ── /geo/accuracy: what the ladder has measured ───────────────────────


def _resolved(db, finals):
    """A resolved signal whose legs ended as ``finals`` = {symbol: final_state}."""
    signal_id = _signal(db, {symbol: "bearish" for symbol in finals}, age=timedelta(days=8))
    for leg in db.query(GeoSignalTicker).filter(GeoSignalTicker.signal_id == signal_id):
        leg.final_state = finals[leg.symbol]
    db.get(GeoSignal, signal_id).status = GeoSignalStatus.RESOLVED.value
    db.commit()


def _measure(db):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None)
    return _ladder_accuracy(db, cutoff)


def test_accuracy_is_counted_per_tier_and_per_step(db, monkeypatch):
    monkeypatch.setattr("backend.api.geo.geo_owner_id", lambda db: 1)
    _resolved(db, {LOCAL: "confirms", NATIONAL: "confirms", WORLD: "contradicts"})
    _resolved(db, {LOCAL: "confirms", NATIONAL: "contradicts"})
    _resolved(db, {LOCAL: "contradicts", NATIONAL: "confirms"})
    _resolved(db, {LOCAL: "flat", NATIONAL: "confirms"})
    _signal(db, {LOCAL: "bearish", NATIONAL: "bearish"})  # still open: no say

    tiers, steps = _measure(db)
    assert (tiers["local"].confirmed, tiers["local"].contradicted, tiers["local"].unreadable) == (2, 1, 1)
    assert tiers["local"].accuracy == pytest.approx(2 / 3)
    assert (tiers["national"].confirmed, tiers["national"].contradicted) == (3, 1)
    assert tiers["international"].accuracy == 0.0

    local_to_national, national_to_world = steps
    assert (local_to_national.narrow, local_to_national.wide) == ("local", "national")
    # Local confirmed twice; the country's market followed once.
    assert (local_to_national.n, local_to_national.confirmed) == (2, 1)
    assert local_to_national.rate == 0.5
    assert local_to_national.baseline == pytest.approx(3 / 4)  # national over all four
    assert (national_to_world.n, national_to_world.confirmed, national_to_world.rate) == (1, 0, 0.0)


def test_with_nothing_resolved_there_is_no_rate_rather_than_a_zero(db, monkeypatch):
    monkeypatch.setattr("backend.api.geo.geo_owner_id", lambda db: 1)
    tiers, steps = _measure(db)
    assert all(t.accuracy is None for t in tiers.values())
    assert all(s.rate is None and s.baseline is None and s.n == 0 for s in steps)


# ── Schema ────────────────────────────────────────────────────────────


def test_the_new_columns_reach_an_existing_table():
    """`create_all` does not alter a table that already exists in prod."""
    registered = {(t, c) for t, c, _ in _ADDITIVE_COLUMNS}
    assert {
        ("geo_signals", "country"),
        ("geo_signal_tickers", "live_change_pct"),
        ("geo_signal_tickers", "live_state"),
        ("geo_signal_tickers", "final_state"),
    } <= registered
