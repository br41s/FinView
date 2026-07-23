"""Structural invariant: the Windy sample set must cover every weather rule.

The bug this guards against was silent and total. ``meteo.py`` sampled a fixed
global 6×6 grid that had no relationship to the regions its own rules watch:
27 of 36 points fell outside every ``GEO_REGIONS`` box (and
``analyze_weather_extremes`` drops those), while four rules — texas,
mediterranean, us_northeast, china_industrial — had no sample point anywhere in
their region and so could never fire, no matter the weather. The source
ingested events every cycle and produced zero signals for its entire life.

Nothing failed. The rules were well-formed, the ingest worked, the matcher
worked; the two halves simply pointed at different parts of the planet. That is
exactly the kind of mismatch a unit test of either half alone cannot see, so the
invariant is asserted across the seam:

    every weather rule's region contains at least one sampled point

``test_every_weather_rule_region_is_sampled`` fails on the old grid and passes
on the derived set. The budget and reachability tests pin the two properties
that make the fix *good* rather than merely correct — a future "just sample
more points" regression would restore coverage while blowing the API quota.
"""

import re

import pytest

from backend.services.geo.ingest import meteo
from backend.services.geo.rules import FAST_RULES, GEO_REGIONS, match_regions

_RE_REGION = re.compile(r"region=(\w+)")

# _CACHE_TTL is 30 min and the geo cron runs every 10 min, so the source really
# fetches ~48×/day. One Windy point-forecast call per point per fetch.
_FETCHES_PER_DAY = 48
# The old 36-point grid cost ~1728 calls/day. The fix must not creep back up to
# it while adding multi-point regions; 16 leaves room for a few new rules.
_MAX_SAMPLE_POINTS = 16


def _weather_rules():
    return [r for r in FAST_RULES if r.category in meteo._WEATHER_CATEGORIES]


def _region_of(rule) -> str:
    m = _RE_REGION.search(rule.condition)
    assert m, f"weather rule {rule.id} has no region= condition"
    return m.group(1)


def test_weather_rules_exist():
    """Guard the guard: a typo in _WEATHER_CATEGORIES would empty every case."""
    assert len(_weather_rules()) >= 10


@pytest.mark.parametrize("rule", _weather_rules(), ids=lambda r: r.id)
def test_every_weather_rule_region_is_sampled(rule):
    """THE invariant. Fails on the old grid for 4 rules; passes on the derived set."""
    region = _region_of(rule)
    assert region in GEO_REGIONS, f"{rule.id} targets unknown region {region}"
    hits = [p for p in meteo.SAMPLE_POINTS if region in match_regions(*p)]
    assert hits, (
        f"{rule.id} ({rule.category}) watches region {region!r} but no Windy sample "
        f"point falls inside it — the rule can never fire. Add a point via "
        f"meteo._REGION_POINTS or check the region's box."
    )


def test_sample_points_derive_from_rules():
    """No point exists that no weather rule asked for (the old grid's 27 wasted calls)."""
    wanted = {_region_of(r) for r in _weather_rules()}
    for pt in meteo.SAMPLE_POINTS:
        regions = set(match_regions(*pt))
        assert regions, f"sample point {pt} is outside every region — sentinel drops it"
        assert regions & wanted, (
            f"sample point {pt} matches {sorted(regions)}, none of which has a "
            f"weather rule — it is a wasted API call every cycle"
        )


def test_api_budget_not_inflated():
    assert len(meteo.SAMPLE_POINTS) <= _MAX_SAMPLE_POINTS, (
        f"{len(meteo.SAMPLE_POINTS)} points × {_FETCHES_PER_DAY} fetches/day = "
        f"{len(meteo.SAMPLE_POINTS) * _FETCHES_PER_DAY} Windy calls/day"
    )


def test_no_duplicate_sample_points():
    """Regions overlap; the same coordinate must not be fetched twice per cycle."""
    assert len(meteo.SAMPLE_POINTS) == len(set(meteo.SAMPLE_POINTS))


def test_sample_points_yield_distinct_event_ids():
    """analyze_weather_extremes keys event ids on int(lat)_int(lon).

    Two points truncating to the same key would collide into one event id, and
    the advisor dedups ACTIVE signals by (source, external_id) — one region's
    weather would silently suppress another's.
    """
    keys = [f"{int(lat)}_{int(lon)}" for lat, lon in meteo.SAMPLE_POINTS]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("region,points", sorted(meteo._REGION_POINTS.items()))
def test_override_points_lie_inside_their_region(region, points):
    """An override exists to be more representative than the centroid, not to
    escape the box: a point outside it is worse than the centroid it replaced."""
    assert region in GEO_REGIONS
    for pt in points:
        assert region in match_regions(*pt), f"override {pt} is outside {region}"
