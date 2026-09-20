"""Event scope vs instrument breadth — the "strong rain in one box, worldwide
ticker" invariant from the 2026-09-20 audit.

KNOWN_VIOLATIONS is the list to shrink: a rule leaves it by narrowing its
basket (a local instrument, a commodity future, a country ETF) or by being
dropped. A rule may not enter it: new mismatches fail the test.
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
    "air-closure-korea": ['GLD', 'LMT', 'NOC'],
    "air-closure-mideast": ['GLD'],
    "air-closure-taiwan": ['GLD', 'LMT', 'SOXX'],
    "air-closure-ukraine": ['JETS', 'LMT'],
    "air-military-mideast": ['GLD'],
    "air-military-scs": ['GLD'],
    "ais-cargo-drop-malacca": ['BDRY'],
    "ais-cargo-drop-panama": ['BDRY'],
    "ais-reroute-cape": ['BDRY'],
    "ais-tanker-drop-hormuz": ['GLD', 'XLE'],
    "conflict-hormuz-strait": ['CVX', 'XOM'],
    "conflict-iran-nuclear": ['GLD'],
    "conflict-korea": ['GLD', 'LMT', 'NOC'],
    "conflict-mideast-oil": ['GLD'],
    "conflict-south-china-sea": ['GLD'],
    "conflict-ukraine-grain": ['DBA', 'LMT', 'RTX'],
    "cyc-australia-ironore": ['BHP', 'RIO', 'VALE'],
    "cyc-florida-insurance": ['ALL', 'HD', 'HIG', 'LOW', 'TRV'],
    "cyc-gulf-oil": ['CVX', 'XOM'],
    "drought-brazil-coffee": ['DBA'],
    "drought-westafrica-cocoa": ['HSY', 'MDLZ'],
    "eq-chile-copper": ['COPX', 'FCX', 'SCCO'],
    "eq-indonesia-nickel": ['VALE'],
    "eq-japan-industrial": ['GLD', 'TM'],
    "eq-lithium-triangle": ['ALB', 'LIT'],
    "eq-peru-copper": ['COPX', 'FCX', 'SCCO'],
    "eq-taiwan-semi": ['INTC', 'SOXX'],
    "eq-turkey": ['GLD'],
    "fire-australia-mining": ['BHP', 'GLD', 'RIO'],
    "fire-california": ['ALL', 'HD', 'TRV'],
    "flood-bangladesh-textile": ['XRT'],
    "flood-westafrica-cocoa": ['HSY', 'MDLZ'],
    "gdelt-conflict-drc-cobalt": ['LIT', 'REMX'],
    "gdelt-conflict-mideast": ['GLD'],
    "gdelt-conflict-nigeria": ['XLE'],
    "gdelt-conflict-sahel": ['GLD'],
    "gdelt-conflict-suez": ['GLD'],
    "gdelt-conflict-ukraine": ['LMT', 'RTX'],
    "gdelt-cooperation-mideast": ['GLD'],
    "gdelt-military-korea": ['GLD', 'LMT', 'NOC'],
    "gdelt-military-taiwan": ['GLD', 'LMT', 'SOXX'],
    "gdelt-protest-china": ['GLD'],
    "gdelt-sanctions-china": ['GLD'],
    "gdelt-sanctions-iran": ['GLD'],
    "gdelt-trade-dispute-china": ['GLD'],
    "storm-texas-freeze": ['XLE'],
    "storm-us-winter": ['JETS'],
    "vol-iceland-aviation": ['JETS'],
    "vol-japan": ['GLD'],
    "wx-cold-us-northeast": ['JETS'],
    "wx-heat-texas": ['XLE'],
    "wx-storm-gulf": ['CVX', 'XOM'],
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
    rule = next(r for r in FAST_RULES if r.id == "fire-australia-mining")
    assert rule_scope(rule) == "regional"
    assert scope_penalty(rule) > 0  # BHP/RIO/GLD are global for an Australian fire box
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
    rule = next(r for r in FAST_RULES if r.id == "eq-turkey")  # TUR (national) + GLD (global)
    assert scope_penalty(rule) == 0.2  # local → global is two steps, once


def test_learned_mod_and_penalty_compose():
    rule = next(r for r in FAST_RULES if r.id == "fire-australia-mining")
    stat = GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=0.3)
    assert effective_confidence(rule, stat) == pytest.approx(
        min(1.0, rule.base_confidence + 0.3 - scope_penalty(rule))
    )
