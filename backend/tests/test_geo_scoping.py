"""Event scope vs instrument breadth — the "strong rain in one box, worldwide
ticker" invariant from the 2026-09-20 audit.

KNOWN_VIOLATIONS is the list to shrink: a rule leaves it by narrowing its
basket (a local instrument, a commodity future, a country ETF) or by being
dropped. A rule may not enter it: new mismatches fail the test.

After the 2026-09-21 rescope pass the list is empty. The ``GLD`` legs on the
conflict, chokepoint and escalation rules survive because those rules declare
``scope="global"``: scope is the reach of the *impact*, not the geography of the
trigger, and a Hormuz closure or a Taiwan corridor closure re-prices the whole
curve. The chain's third clause is where that claim is defended. Gold on a
Japanese volcano or a Turkish earthquake was not defensible and is gone.
"""

import pytest

from backend.services.geo.rules import (
    BREADTH_RANK,
    FAST_RULES,
    INSTRUMENT_BREADTH,
    INSTRUMENT_TRADABILITY,
    SCOPE_RANK,
    FastRule,
    _t,
    GeoRuleStat,
    RuleTicker,
    effective_confidence,
    rule_scope,
    scope_penalty,
    scope_violations,
)

KNOWN_VIOLATIONS: dict[str, list[str]] = {}


def test_every_symbol_is_classified():
    symbols = {t.symbol for r in FAST_RULES for t in r.tickers}
    assert symbols <= set(INSTRUMENT_BREADTH), symbols - set(INSTRUMENT_BREADTH)
    assert symbols <= set(INSTRUMENT_TRADABILITY), symbols - set(INSTRUMENT_TRADABILITY)
    assert set(INSTRUMENT_BREADTH.values()) <= set(BREADTH_RANK)
    assert {t for t, _ in INSTRUMENT_TRADABILITY.values()} <= {
        "cash_eu", "options_only", "not_tradable"
    }


def test_every_rule_has_a_scope():
    assert {rule_scope(r) for r in FAST_RULES} <= set(SCOPE_RANK)
    implicit = [r.id for r in FAST_RULES if not r.scope]
    assert not implicit, f"scope must be written down, not inferred from the box: {implicit}"


def test_every_rule_has_a_written_chain():
    """A rule whose transmission cannot be written to any instrument was dropped."""
    missing = [r.id for r in FAST_RULES if not r.chain]
    assert not missing, f"rules with no chain: {missing}"
    for rule in FAST_RULES:
        assert len(rule.chain) == 3, rule.id
        assert all(c.strip() for c in rule.chain), rule.id
        assert rule.thesis == " → ".join(rule.chain), rule.id


def test_the_chain_does_not_lean_on_a_ticker_to_explain_the_mechanism():
    """The physical effect and the price it moves are stated without symbols;
    only the third clause may reach for the instrument."""
    symbols = {t.symbol for r in FAST_RULES for t in r.tickers}
    for rule in FAST_RULES:
        for clause in rule.chain[:2]:
            hit = [s for s in symbols if s in clause]
            assert not hit, f"{rule.id}: ticker {hit} in a mechanism clause"


def test_scope_violations_only_shrink():
    """A rule that has been narrowed must leave the list; a new mismatch may not enter it."""
    current = {
        r.id: sorted({s for s, _ in scope_violations(r)}) for r in FAST_RULES if scope_violations(r)
    }
    entered = {k: v for k, v in current.items() if k not in KNOWN_VIOLATIONS}
    widened = {
        k: sorted(set(v) - set(KNOWN_VIOLATIONS[k]))
        for k, v in current.items()
        if k in KNOWN_VIOLATIONS and set(v) - set(KNOWN_VIOLATIONS[k])
    }
    assert not entered, f"new scope violations: {entered}"
    assert not widened, f"violations widened: {widened}"
    stale = {k: v for k, v in KNOWN_VIOLATIONS.items() if k not in current or set(current[k]) < set(v)}
    assert not stale, f"fixed — remove from KNOWN_VIOLATIONS: {stale}"


def _rule(scope: str, spec: str) -> FastRule:
    return FastRule(
        "x", "fire", "fire.cluster>=30 && region=australia", "d", _t(spec), "t", 0.60, scope=scope
    )


def test_a_local_event_on_a_global_basket_pays_a_confidence_penalty():
    rule = _rule("local", "BHP- RIO- GLD+")  # the pre-rescope fire-australia-mining basket
    assert scope_penalty(rule) > 0
    assert effective_confidence(rule, None) < rule.base_confidence


def test_a_commodity_basin_rule_pays_nothing():
    """The template: a narrow box and the commodity's own price."""
    rule = FastRule(
        "x-cocoa", "drought", "region=west_africa_cocoa", "Ivorian drought",
        (RuleTicker("CC=F", "bullish"),), "less cocoa → cocoa up", 0.78,
    )
    assert rule_scope(rule) == "local"
    assert scope_penalty(rule) == 0
    assert effective_confidence(rule, None) == rule.base_confidence


def test_penalty_is_bounded_by_the_widest_leg_not_summed():
    two_wide = _rule("local", "TUR- GLD+ BHP-")  # national + two global legs
    assert scope_penalty(two_wide) == pytest.approx(0.2)  # local → global is two steps, once


def test_declaring_global_reach_removes_the_penalty():
    """Scope is impact reach: the same basket with scope="global" pays nothing,
    and the chain's third clause is where that claim is defended."""
    assert scope_penalty(_rule("global", "USO+ GLD+")) == 0
    assert scope_penalty(_rule("site", "USO+ GLD+")) == pytest.approx(0.3)


def test_learned_mod_and_penalty_compose():
    rule = next(r for r in FAST_RULES if r.id == "conflict-korea")
    stat = GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=0.3)
    assert effective_confidence(rule, stat) == pytest.approx(
        min(1.0, rule.base_confidence + 0.3 - scope_penalty(rule))
    )


def test_the_scope_penalty_does_not_mute_the_chokepoint_rules():
    """Scope is impact reach, not trigger geography: with scope="site" on Hormuz
    the gold leg cost 0.30 and the highest-conviction rule in the file dropped
    from 72 to 48 — under the gate. The rules that must page on first sighting:"""
    from backend.services.geo.advisor import IMPORTANCE_THRESHOLD, compute_importance
    from backend.services.geo.rules import RULES_BY_ID, base_risk

    for rid in (
        "conflict-hormuz-strait", "ais-tanker-drop-hormuz", "conflict-mideast-oil",
        "conflict-iran-nuclear", "gdelt-military-taiwan", "gdelt-military-korea",
        "conflict-south-china-sea", "conflict-suez", "ais-cargo-drop-malacca",
    ):
        rule = RULES_BY_ID[rid]
        importance = compute_importance(effective_confidence(rule, None) * 100, base_risk(rule))
        assert importance >= IMPORTANCE_THRESHOLD, (rid, importance, scope_penalty(rule))
