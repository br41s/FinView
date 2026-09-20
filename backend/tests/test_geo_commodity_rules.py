"""Coverage tests for the commodity-basin regions and their rules.

These four rules gate real signals (cocoa, iron ore, lithium), so per repo rule
they get a test. Each case asserts three things that can silently rot:

1. An event inside the new box matches the new rule with the expected basket
   AND the expected per-ticker direction — a typo in the ``_t`` spec flips a
   thesis without failing anything else.
2. An event just OUTSIDE the box does not match. For Pilbara and the lithium
   triangle the "outside" point is deliberately still inside a *broader* region
   (``australia`` / ``chile_mining``), so the test pins the new box's edges
   rather than merely proving "unmapped ocean matches nothing".
3. The lithium box overlaps ``chile_mining`` ON PURPOSE — one Atacama quake
   carries both the copper and the lithium thesis. That dual match is asserted,
   not tolerated, so a future de-overlap has to be a deliberate change.
"""

import time

import pytest

from backend.services.geo.rules import RULES_BY_ID, match_regions, match_rules
from backend.services.geo.sentinel import GeoEvent


def _event(etype: str, lat: float, lon: float, magnitude: float | None = None) -> GeoEvent:
    return GeoEvent(
        id=f"test-{etype}-{lat}-{lon}",
        type=etype,
        title=f"synthetic {etype}",
        latitude=lat,
        longitude=lon,
        source="test",
        timestamp=int(time.time() * 1000),
        magnitude=magnitude,
    )


def _basket(rule_id: str) -> dict[str, str]:
    return {t.symbol: t.direction for t in RULES_BY_ID[rule_id].tickers}


# ── Inside the box: rule fires with the right basket ─────────────────
@pytest.mark.parametrize(
    "rule_id, etype, lat, lon, magnitude, expected",
    [
        # Ivory Coast (Yamoussoukro) — ~60% of world cocoa with Ghana.
        (
            "drought-westafrica-cocoa",
            "drought",
            6.8,
            -5.3,
            None,
            {"CC=F": "bullish"},
        ),
        (
            "flood-westafrica-cocoa",
            "flood",
            6.8,
            -5.3,
            None,
            {"CC=F": "bullish"},
        ),
        # Port Hedland — world's largest iron-ore export port.
        (
            "cyc-australia-ironore",
            "cyclone",
            -20.3,
            118.6,
            None,
            {"FMG.AX": "bearish"},
        ),
        # Salar de Atacama — brine lithium.
        (
            "eq-lithium-triangle",
            "earthquake",
            -23.5,
            -68.2,
            6.5,
            {"SQM": "bearish", "ALB": "bearish"},
        ),
    ],
)
def test_new_rule_matches_inside_box(rule_id, etype, lat, lon, magnitude, expected):
    matched = {r.id for r in match_rules(_event(etype, lat, lon, magnitude))}
    assert rule_id in matched
    assert _basket(rule_id) == expected


# ── Outside the box: rule stays silent ───────────────────────────────
@pytest.mark.parametrize(
    "rule_id, etype, lat, lon, magnitude",
    [
        # Atlantic, west of the cocoa belt.
        ("drought-westafrica-cocoa", "drought", 6.8, -20.0, None),
        ("flood-westafrica-cocoa", "flood", 6.8, -20.0, None),
        # Sydney: inside `australia`, far outside the Pilbara box.
        ("cyc-australia-ironore", "cyclone", -33.9, 151.2, None),
        # Below the triangle's southern edge but still inside `chile_mining`.
        ("eq-lithium-triangle", "earthquake", -30.0, -68.5, 6.5),
    ],
)
def test_new_rule_does_not_match_outside_box(rule_id, etype, lat, lon, magnitude):
    matched = {r.id for r in match_rules(_event(etype, lat, lon, magnitude))}
    assert rule_id not in matched


# ── Sentinel-gate + overlap invariants ───────────────────────────────
def test_lithium_quake_below_magnitude_gate_does_not_match():
    """The rule's own `magnitude>=6` gate, independent of the sentinel's 5.5 floor."""
    matched = {r.id for r in match_rules(_event("earthquake", -23.5, -68.2, 5.9))}
    assert "eq-lithium-triangle" not in matched


def test_atacama_quake_carries_both_copper_and_lithium_theses():
    """Overlap with chile_mining is intentional — assert it, don't just allow it."""
    regions = match_regions(-23.5, -68.2)
    assert {"lithium_triangle", "chile_mining"} <= set(regions)

    matched = {r.id for r in match_rules(_event("earthquake", -23.5, -68.2, 6.5))}
    assert {"eq-lithium-triangle", "eq-chile-copper"} <= matched


def test_cocoa_box_does_not_pull_in_neighbouring_region_rules():
    """west_africa_cocoa clips sahel/nigeria_oil, but those carry only
    armed_conflict rules — a drought there must not fire a conflict thesis."""
    matched = match_rules(_event("drought", 6.8, -5.3))
    assert {r.id for r in matched} == {"drought-westafrica-cocoa"}
