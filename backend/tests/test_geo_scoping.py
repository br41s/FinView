"""Event scope vs instrument breadth — the "strong rain in one box, worldwide
ticker" invariant from the 2026-09-20 audit.

KNOWN_VIOLATIONS is the list to shrink: a rule leaves it by narrowing its
basket (a local instrument, a commodity future, a country ETF) or by being
dropped. A rule may not enter it: new mismatches fail the test.

After the 2026-09-21 rescope pass the only entries left are ``GLD`` on the
conflict, chokepoint and escalation rules, where the chain names the reason a
worldwide instrument follows a one-box event: a Hormuz closure, a DMZ incident
or a Taiwan corridor closure is a systemic risk-off event and bullion is the
reserve asset bid in one. Gold on a Japanese volcano or a Turkish earthquake was
not defensible and is gone, along with the rules that could not be written down.
"""

import pytest

from backend.services.geo.rules import (
    BREADTH_RANK,
    FAST_RULES,
    INSTRUMENT_BREADTH,
    INSTRUMENT_TRADABILITY,
    SCOPE_RANK,
    FastRule,
    GeoRuleStat,
    RuleTicker,
    effective_confidence,
    rule_scope,
    scope_penalty,
    scope_violations,
)

KNOWN_VIOLATIONS: dict[str, list[str]] = {
    "air-closure-iran": ['GLD'],
    "air-closure-korea": ['GLD'],
    "air-closure-mideast": ['GLD'],
    "air-closure-taiwan": ['GLD'],
    "air-military-mideast": ['GLD'],
    "air-military-scs": ['GLD'],
    "ais-tanker-drop-hormuz": ['GLD'],
    "conflict-hormuz-strait": ['GLD'],
    "conflict-iran-nuclear": ['GLD'],
    "conflict-korea": ['GLD'],
    "conflict-mideast-oil": ['GLD'],
    "conflict-south-china-sea": ['GLD'],
    "gdelt-conflict-mideast": ['GLD'],
    "gdelt-military-korea": ['GLD'],
    "gdelt-military-taiwan": ['GLD'],
    "gdelt-sanctions-iran": ['GLD'],
}


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


def test_a_local_event_on_a_global_basket_pays_a_confidence_penalty():
    rule = next(r for r in FAST_RULES if r.id == "conflict-hormuz-strait")
    assert rule_scope(rule) == "site"
    assert scope_penalty(rule) > 0  # the gold leg is worldwide, the event is one strait
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
    rule = next(r for r in FAST_RULES if r.id == "conflict-korea")  # EWY (national) + GLD (global)
    assert scope_penalty(rule) == 0.2  # local → global is two steps, once


def test_learned_mod_and_penalty_compose():
    rule = next(r for r in FAST_RULES if r.id == "conflict-korea")
    stat = GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=0.3)
    assert effective_confidence(rule, stat) == pytest.approx(
        min(1.0, rule.base_confidence + 0.3 - scope_penalty(rule))
    )
