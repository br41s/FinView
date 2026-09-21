"""The FRED macro regime amplifies geopolitical risk; physical events are unmoved."""

import time

from backend.services.geo.analyst import analyze_event
from backend.services.geo.rules import FAST_RULES, base_risk, compute_risk, regime_headroom
from backend.services.geo.sentinel import GeoEvent


def _rule(rid):
    return next(r for r in FAST_RULES if r.id == rid)


def test_risk_off_adds_one_to_geopolitical_rules_only():
    hormuz, quake = _rule("conflict-hormuz-strait"), _rule("eq-chile-copper")
    assert regime_headroom([hormuz], "risk_off") == 1
    assert regime_headroom([quake], "risk_off") == 0
    assert regime_headroom([hormuz], "neutral") == 0
    assert regime_headroom([hormuz], "risk_on") == 0
    assert regime_headroom([hormuz], None) == 0


def test_compute_risk_applies_the_regime_and_stays_capped():
    hormuz = _rule("conflict-hormuz-strait")
    ev = GeoEvent(id="e", type="conflict", title="t", latitude=26.0, longitude=56.0,
                  source="alerts", timestamp=int(time.time() * 1000), severity="red")
    calm = compute_risk([hormuz], ev, None)
    fragile = compute_risk([hormuz], ev, None, "risk_off")
    assert fragile == min(10, calm + 1)
    assert compute_risk([hormuz], ev, 4, "risk_off") == 4  # the LLM still overrides


def test_analyze_event_threads_the_regime_through():
    ev = GeoEvent(id="e", type="conflict", title="t", latitude=26.0, longitude=56.0,
                  source="alerts", timestamp=int(time.time() * 1000))
    calm = analyze_event(ev, {}, use_llm=False)
    fragile = analyze_event(ev, {}, use_llm=False, regime="risk_off")
    assert fragile.risk_score == calm.risk_score + 1
    assert base_risk(_rule("conflict-hormuz-strait")) == calm.risk_score
