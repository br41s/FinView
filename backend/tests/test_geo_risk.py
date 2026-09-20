"""Risk is decoupled from confidence and the notify gate is reachable.

Before 2026-09-20 risk_score was min(round(conf/15), 10), so importance =
conf × risk/10 squared confidence and topped out at 54 against a gate of 60:
1700 prod signals, 0 notifications, LLM never invoked. These tests pin the
contract that fixes it, from real FAST_RULES and a synthetic event — never from
a hand-built signal the pipeline cannot produce.
"""

import time

from backend.services.geo.advisor import IMPORTANCE_THRESHOLD, compute_importance
from backend.services.geo.analyst import analyze_event
from backend.services.geo.rules import (
    CATEGORY_RISK,
    FAST_RULES,
    GeoRuleStat,
    base_risk,
    compute_risk,
    severity_headroom,
)
from backend.services.geo.sentinel import GeoEvent


def _event(**kw) -> GeoEvent:
    base = dict(
        id="evt-1",
        type="earthquake",
        title="test",
        latitude=-27.0,  # chile_mining box
        longitude=-70.0,
        source="usgs",
        timestamp=int(time.time() * 1000),
    )
    base.update(kw)
    return GeoEvent(**base)


def test_every_category_has_a_base_risk():
    missing = {r.category for r in FAST_RULES} - set(CATEGORY_RISK)
    assert not missing, f"categories without CATEGORY_RISK: {missing}"
    assert all(1 <= v <= 10 for v in CATEGORY_RISK.values())
    assert all(1 <= base_risk(r) <= 10 for r in FAST_RULES)


def test_some_rule_can_notify_on_first_sighting():
    """The gate must be reachable from the catalogue with confidence_mod=0.

    Otherwise notify and the LLM are dead code, whatever the channels say.
    """
    reachable = [
        r.id
        for r in FAST_RULES
        if compute_importance(r.base_confidence * 100, base_risk(r)) >= IMPORTANCE_THRESHOLD
    ]
    assert reachable, "no rule can reach IMPORTANCE_THRESHOLD on first sighting"
    assert "conflict-hormuz-strait" in reachable


def test_fires_do_not_notify_on_first_sighting():
    """78% of prod signals are FIRMS fires; a plain cluster must not page a phone."""
    for r in FAST_RULES:
        if r.category == "fire":
            assert compute_importance(r.base_confidence * 100, base_risk(r)) < IMPORTANCE_THRESHOLD


def test_magnitude_scales_risk_not_confidence():
    """M8.5 outranks M6.0 through risk; confidence stays what the rule says."""
    weak = analyze_event(_event(magnitude=6.0), {}, use_llm=False)
    strong = analyze_event(_event(magnitude=8.5), {}, use_llm=False)
    assert weak.matched_rules and weak.matched_rules == strong.matched_rules
    assert weak.confidence == strong.confidence
    assert strong.risk_score > weak.risk_score
    assert compute_importance(strong.confidence, strong.risk_score) > compute_importance(
        weak.confidence, weak.risk_score
    )


def test_headroom_is_bounded():
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    assert severity_headroom(rule, _event(magnitude=6.0)) == 0
    assert severity_headroom(rule, _event(magnitude=9.9)) == 2


def test_learned_confidence_does_not_move_risk():
    """The coupling this replaces: a confidence_mod shift changed risk too."""
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    low = {rule.id: GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=-0.3)}
    high = {rule.id: GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=0.3)}
    a = analyze_event(_event(magnitude=6.0), low, use_llm=False)
    b = analyze_event(_event(magnitude=6.0), high, use_llm=False)
    assert a.confidence < b.confidence
    assert a.risk_score == b.risk_score


def test_llm_risk_overrides_and_is_clamped():
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    ev = _event(magnitude=8.5)
    assert compute_risk([rule], ev, 3) == 3
    assert compute_risk([rule], ev, 42) == 10
    assert compute_risk([rule], ev, 0) == 1
    assert compute_risk([rule], ev, None) == base_risk(rule) + 2


def test_no_rules_no_llm_is_middle_of_the_road():
    assert compute_risk([], _event(), None) == 5


def test_llm_garbage_risk_falls_back_to_the_rules(caplog):
    """riskScore comes straight out of json.loads. A model answering "alto" must
    cost one override, not the user's whole cycle (analyze_event is unguarded
    in Phase C and a raise there skips the auditor too)."""
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    ev = _event(magnitude=6.0)
    for garbage in ("alto", "7/10", {}, [], "", object()):
        assert compute_risk([rule], ev, garbage) == base_risk(rule)
    assert "non-numeric LLM riskScore" in caplog.text
    assert compute_risk([rule], ev, "8") == 8  # a numeric string is still a number


def test_headroom_never_goes_negative():
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    assert severity_headroom(rule, _event(magnitude=1.0)) == 0


def test_fire_cluster_headroom_scales_with_the_floor():
    rule = next(r for r in FAST_RULES if r.category == "fire")
    floor = int(rule.condition.split("fire.cluster>=")[1].split()[0])
    fire = lambda n: _event(type="fire", raw_data={"clusterSize": n})  # noqa: E731
    assert severity_headroom(rule, fire(floor)) == 0
    assert severity_headroom(rule, fire(floor * 2)) == 1
    assert severity_headroom(rule, fire(floor * 4)) == 2
    assert severity_headroom(rule, _event(type="fire")) == 0  # no cluster size at all


def test_red_severity_counts_only_when_the_rule_did_not_demand_it():
    demanded = next(r for r in FAST_RULES if "alert.severity=red" in r.condition)
    plain = next(
        r for r in FAST_RULES
        if r.category == demanded.category and "alert.severity" not in r.condition
    )
    red = _event(type=demanded.category, severity="red")
    assert severity_headroom(demanded, red) == 0
    assert severity_headroom(plain, red) == 1
    assert severity_headroom(plain, _event(type=demanded.category, severity="orange")) == 0
