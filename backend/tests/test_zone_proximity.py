"""Tests for the technical-signal proximity gate."""

from backend.services.zone_proximity import (
    PROXIMITY_THRESHOLD,
    detect_proximity_candidates,
)


def zone(level: float, zone_type: str = "resistance", strength: float = 0.8, touches: int = 4):
    return {"level": level, "zone_type": zone_type, "strength": strength, "touches": touches}


def test_zone_within_threshold_is_a_candidate():
    got = detect_proximity_candidates([zone(101.0)], current_price=100.0)
    assert len(got) == 1
    assert got[0]["level"] == 101.0
    assert got[0]["distance_pct"] == 0.01


def test_zone_beyond_threshold_is_not():
    assert detect_proximity_candidates([zone(110.0)], current_price=100.0) == []


def test_threshold_boundary_is_inclusive():
    # Exactly 2% away still counts — the gate is "within", not "strictly inside".
    at_limit = 100.0 * (1 + PROXIMITY_THRESHOLD)
    assert len(detect_proximity_candidates([zone(at_limit)], current_price=100.0)) == 1
    just_past = 100.0 * (1 + PROXIMITY_THRESHOLD) + 0.01
    assert detect_proximity_candidates([zone(just_past)], current_price=100.0) == []


def test_price_below_level_implies_a_bullish_break():
    got = detect_proximity_candidates([zone(101.0)], current_price=100.0)
    assert got[0]["approach"] == "from_below"
    assert got[0]["direction"] == "BULLISH"


def test_price_above_level_implies_a_bearish_break():
    got = detect_proximity_candidates([zone(99.0)], current_price=100.0)
    assert got[0]["approach"] == "from_above"
    assert got[0]["direction"] == "BEARISH"


def test_direction_ignores_the_stale_zone_type_label():
    """A 'resistance' price already trades above is a flipped level: it acts as
    support and the pending move is a breakdown. Trusting the historical label
    would call this BULLISH and invert every flipped zone."""
    got = detect_proximity_candidates([zone(99.5, zone_type="resistance")], current_price=100.0)
    assert got[0]["direction"] == "BEARISH"
    # ...but the label survives as context for the scorer.
    assert got[0]["zone_type"] == "resistance"


def test_price_exactly_on_the_level_reads_as_bearish():
    got = detect_proximity_candidates([zone(100.0)], current_price=100.0)
    assert got[0]["distance_pct"] == 0.0
    assert got[0]["direction"] == "BEARISH"


def test_candidates_come_back_nearest_first():
    got = detect_proximity_candidates(
        [zone(101.5), zone(100.2), zone(99.0)], current_price=100.0
    )
    assert [c["level"] for c in got] == [100.2, 99.0, 101.5]


def test_zone_strength_and_touches_ride_along():
    got = detect_proximity_candidates(
        [zone(100.5, strength=0.42, touches=9)], current_price=100.0
    )
    assert got[0]["strength"] == 0.42
    assert got[0]["touches"] == 9


def test_no_zones_or_no_price_yields_nothing():
    assert detect_proximity_candidates([], current_price=100.0) == []
    assert detect_proximity_candidates([zone(100.0)], current_price=0.0) == []
    assert detect_proximity_candidates([zone(100.0)], current_price=-5.0) == []


def test_malformed_zones_are_skipped_not_raised():
    """Zones come out of a JSON column, so a missing/garbage level must not take
    down the whole analysis cycle."""
    got = detect_proximity_candidates(
        [
            {"zone_type": "support"},  # no level
            {"level": None},
            {"level": "not-a-number"},
            {"level": 0.0},
            {"level": -3.0},
            zone(100.5),
        ],
        current_price=100.0,
    )
    assert [c["level"] for c in got] == [100.5]


def test_threshold_is_overridable():
    assert detect_proximity_candidates([zone(105.0)], current_price=100.0) == []
    got = detect_proximity_candidates([zone(105.0)], current_price=100.0, threshold=0.10)
    assert len(got) == 1
