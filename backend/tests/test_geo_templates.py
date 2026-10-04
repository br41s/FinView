"""Template rules — the national reading of an event no hand-written rule covers.

An event outside every region box used to be dropped in the sentinel, and seven
countries had an instrument of their own. A template is one written chain per
event category, applied to whichever country the event is in. What must hold:

- it is a **fallback**: next to a hand-written rule it would change that
  signal's confidence and risk, and re-page live signals on deploy day;
- an event only ever reaches **its own country's** market;
- it cannot reach a phone until its own record has earned it.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, GeoRuleStat, GeoSignal
from backend.services.geo import analyst, orchestrator, sentinel
from backend.services.geo.advisor import IMPORTANCE_THRESHOLD, compute_importance
from backend.services.geo.analyst import analyze_event
from backend.services.geo.countries import COUNTRY_ETF, INSTRUMENT_COUNTRY
from backend.services.geo.ingest.types import NaturalEvent, SeismicEvent
from backend.services.geo.rules import (
    FAST_RULES,
    INSTRUMENT_BREADTH,
    SCOPE_RANK,
    TEMPLATE_RULES,
    allowed_symbols,
    compute_risk,
    effective_confidence,
    fetch_order,
    instrument_tier,
    is_template,
    match_regions,
    match_rules,
    match_templates,
    resolve_rule,
    rule_scope,
    scope_violations,
    seed_rule_stats,
    template_floor_met,
)
from backend.services.geo.sentinel import GeoEvent

MEXICO_CITY = (19.4, -99.1)  # inside no region box
TOKYO = (35.7, 139.7)  # inside `japan`, where eq-japan-industrial lives


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _quake(point=MEXICO_CITY, country="mexico", magnitude=7.1, pager="orange", event_id="eq-1"):
    return GeoEvent(
        id=event_id, type="earthquake", title=f"M{magnitude} Earthquake", latitude=point[0],
        longitude=point[1], source="usgs", timestamp=0, magnitude=magnitude,
        raw_data={"depth": 20.0, "pagerAlert": pager}, country=country,
    )


def _natural(etype="flood", severity="orange", country="mexico", point=MEXICO_CITY):
    return GeoEvent(
        id="evt-gdacs-1", type=etype, title="Flood", latitude=point[0], longitude=point[1],
        source="GDACS", timestamp=0, severity=severity, raw_data={}, country=country,
    )


# ── What a template produces ──────────────────────────────────────────


def test_a_quake_outside_every_box_reaches_its_own_countrys_market():
    assert match_regions(*MEXICO_CITY) == [] and match_rules(_quake()) == []
    result = analyze_event(_quake(), stats={})
    assert [r.id for r in result.matched_rules] == ["tpl-earthquake-national"]
    assert [(t.symbol, t.direction) for t in result.tickers] == [("EWW", "bearish")]
    rule = result.matched_rules[0]
    assert rule.description == "Damaging earthquake in Mexico"
    assert "Mexico" in rule.thesis and "{" not in rule.thesis


def test_a_flood_and_a_cyclone_have_their_own_chain():
    (flood,) = match_templates(_natural("flood"))
    (cyclone,) = match_templates(_natural("cyclone", severity="red"))
    assert (flood.id, cyclone.id) == ("tpl-flood-national", "tpl-cyclone-national")
    assert flood.chain != cyclone.chain


def test_a_category_with_no_template_gets_nothing():
    assert match_templates(_natural("volcano", severity="red")) == []
    assert match_templates(_natural("drought")) == []


def test_a_country_without_a_market_gets_nothing():
    assert match_templates(_quake(country="russia")) == []
    assert match_templates(_quake(country=None)) == []
    assert resolve_rule("tpl-earthquake-national", "russia") is None
    assert resolve_rule("no-such-rule", "mexico") is None


def test_the_article_reads_right_in_the_rendered_rule():
    rule = resolve_rule("tpl-earthquake-national", "philippines")
    assert rule.description == "Damaging earthquake in the Philippines"
    assert rule.tickers[0].symbol == "EPHE"


# ── The floor ─────────────────────────────────────────────────────────


def test_an_event_below_the_floor_is_not_read_against_a_market():
    """Whatever the floor is tuned to, these two ends of it must hold."""
    assert template_floor_met(_quake(pager="red"))
    assert not template_floor_met(_quake(magnitude=5.6, pager="green"))
    assert template_floor_met(_natural(severity="red"))
    assert not template_floor_met(_natural(severity="green"))
    assert match_templates(_quake(magnitude=5.6, pager="green")) == []


# ── A fallback, never an addition ─────────────────────────────────────


def test_a_hand_written_rule_keeps_its_signal_exactly_as_it_was():
    """An M7.2 under Tokyo is eq-japan-industrial at 52 and silent. With a
    template beside it the max headroom would rise and the same quake page."""
    before = analyze_event(_quake(TOKYO, country=None, magnitude=7.2, pager=None), stats={})
    after = analyze_event(_quake(TOKYO, country="japan", magnitude=7.2, pager="red"), stats={})
    assert [r.id for r in after.matched_rules] == [r.id for r in before.matched_rules]
    assert not any(is_template(r) for r in after.matched_rules)
    assert (after.confidence, after.risk_score) == (before.confidence, before.risk_score)
    assert [(t.symbol, t.direction) for t in after.tickers] == [
        (t.symbol, t.direction) for t in before.tickers
    ]


# ── Invariants for every country a template can be rendered for ───────


def test_every_rendering_obeys_what_the_hand_written_rules_obey():
    symbols = {t.symbol for r in FAST_RULES for t in r.tickers} | set(COUNTRY_ETF.values())
    for template in TEMPLATE_RULES:
        for slug in COUNTRY_ETF:
            rule = resolve_rule(template.id, slug)
            where = f"{template.id} / {slug}"
            assert rule_scope(rule) == "local" and rule.scope in SCOPE_RANK, where
            assert len(rule.chain) == 3 and all(c.strip() for c in rule.chain), where
            assert "{" not in " ".join((*rule.chain, rule.description)), where
            assert not [s for s in symbols for clause in rule.chain[:2] if s in clause], where
            assert scope_violations(rule) == [], where
            assert rule.thesis == " → ".join(rule.chain), where


def test_a_template_leg_is_always_the_events_own_country():
    """The gate, by construction: a Brazilian event cannot load Indonesia's market."""
    for template in TEMPLATE_RULES:
        for slug in COUNTRY_ETF:
            (leg,) = resolve_rule(template.id, slug).tickers
            assert INSTRUMENT_COUNTRY[leg.symbol] == slug
            assert instrument_tier(leg.symbol) == "national"
            assert leg.direction == "bearish"


def test_template_ids_do_not_collide_with_rule_ids():
    assert not {t.id for t in TEMPLATE_RULES} & {r.id for r in FAST_RULES}
    assert all(t.id.startswith("tpl-") for t in TEMPLATE_RULES)


# ── Importance: on the board, not on the phone ────────────────────────


def _worst_case(template_id: str) -> GeoEvent:
    if template_id == "tpl-earthquake-national":
        return _quake(magnitude=8.4, pager="red")
    category = template_id.split("-")[1]
    return _natural(category, severity="red")


def test_an_unlearned_template_cannot_page_at_its_worst():
    for template in TEMPLATE_RULES:
        event = _worst_case(template.id)
        (rule,) = match_templates(event)
        risk = compute_risk([rule], event, None, "risk_off")
        importance = compute_importance(effective_confidence(rule, None) * 100, risk)
        assert importance < IMPORTANCE_THRESHOLD, (template.id, importance)


def test_pager_separates_a_quake_that_shook_from_one_that_broke():
    risks = {
        pager: compute_risk(match_templates(_quake(pager=pager)), _quake(pager=pager), None)
        for pager in ("yellow", "orange", "red")
    }
    assert risks == {"yellow": 6, "orange": 7, "red": 8}


def test_a_template_with_a_record_can_earn_the_page():
    """The gate must be reachable, or the template is decoration (cf. test_geo_risk)."""
    event = _quake(pager="red")
    (rule,) = match_templates(event)
    proven = GeoRuleStat(rule_id=rule.id, category="earthquake", base_confidence=0.5,
                         confidence_mod=0.30)
    importance = compute_importance(
        effective_confidence(rule, proven) * 100, compute_risk([rule], event, None)
    )
    assert importance >= IMPORTANCE_THRESHOLD


def test_templates_are_seeded_once_under_their_shared_id(db):
    seed_rule_stats(db)
    assert seed_rule_stats(db) == 0
    ids = {row.rule_id for row in db.query(GeoRuleStat).all()}
    assert {t.id for t in TEMPLATE_RULES} <= ids
    assert len(ids) == len(FAST_RULES) + len(TEMPLATE_RULES)


# ── The gate on what an event may be related to ───────────────────────


def test_an_event_reaches_its_own_country_and_never_another():
    allowed = allowed_symbols(_quake(country="mexico"))
    assert "EWW" in allowed
    assert not {"EIDO", "EWZ", "EPHE", "TSM", "ALL"} & allowed
    assert {"GLD", "USO", "HG=F", "LMT"} <= allowed  # nobody's country: always admitted


def test_a_region_box_keeps_the_instruments_its_rules_already_use():
    """Geocoded north of the border or with no country at all, a Korean-peninsula
    event still reaches the instrument the hand-written rules relate it to."""
    korea = GeoEvent(id="g", type="military_escalation", title="t", latitude=38.5,
                     longitude=127.0, source="gdelt", timestamp=0)
    allowed = allowed_symbols(korea)
    assert "EWY" in allowed and "EWZ" not in allowed


def test_an_event_with_no_country_and_no_box_reaches_only_unbound_instruments():
    nowhere = GeoEvent(id="g", type="flood", title="t", latitude=-45.0, longitude=-120.0,
                       source="EONET", timestamp=0)
    assert not set(INSTRUMENT_COUNTRY) & allowed_symbols(nowhere)


def test_the_enrichment_drops_what_the_event_may_not_reach(monkeypatch):
    """It used to append whatever the model named, in or out of the universe."""
    monkeypatch.setattr(analyst, "_llm_analyze", lambda event, existing: {
        "affectedTickers": [
            {"symbol": "EIDO", "direction": "bearish"},  # another country's market
            {"symbol": "NVDA", "direction": "bearish"},  # outside the universe
            {"symbol": "GLD", "direction": "bullish"},
            "junk",
        ],
        "narrative": "n", "riskScore": 6,
    })
    result = analyze_event(_quake(), stats={}, use_llm=True)
    assert [t.symbol for t in result.tickers] == ["EWW", "GLD"]


def test_the_prompt_lists_only_what_the_event_may_reach():
    block = analyst._universe_block(allowed_symbols(_quake(country="mexico")))
    assert "EWW (national" in block and "EIDO" not in block and "GLD (global" in block


# ── Sentinel: which events now exist ──────────────────────────────────


def _seismic(place, point, magnitude=6.4, alert="yellow"):
    return SeismicEvent(id="us1", magnitude=magnitude, place=place, time=1, latitude=point[0],
                        longitude=point[1], depth=15.0, alert=alert)


def test_usgs_carries_its_own_estimate_of_the_damage():
    """PAGER's alert is in the feed the ingest already reads; None until computed."""
    from backend.services.geo.ingest import seismic

    def feature(fid, **props):
        return {"id": fid, "properties": {"mag": 6.4, "place": "p", "time": 1, **props},
                "geometry": {"coordinates": [-99.1, 19.4, 15.0]}}

    red, pending = seismic._parse({"features": [feature("a", alert="red"), feature("b", alert=None)]})
    assert (red.alert, pending.alert) == ("red", None)


def test_a_quake_outside_every_box_exists_when_its_country_has_a_market():
    (event,) = sentinel.analyze_earthquakes([_seismic("12 km S of Mexico City, Mexico", MEXICO_CITY)])
    assert (event.country, event.region) == ("mexico", None)
    assert event.raw_data["pagerAlert"] == "yellow" and event.raw_data["depth"] == 15.0


def test_a_quake_outside_every_box_in_an_unlisted_country_is_still_dropped():
    assert sentinel.analyze_earthquakes([_seismic("south of the Fiji Islands", (-18.0, 178.0))]) == []
    assert sentinel.analyze_earthquakes(
        [_seismic("12 km S of Mexico City, Mexico", MEXICO_CITY, magnitude=5.2)]
    ) == []  # the magnitude floor is unchanged


def test_a_boxed_quake_carries_its_country_too():
    (event,) = sentinel.analyze_earthquakes([_seismic("3 km E of Chiba, Japan", TOKYO, 6.8)])
    assert (event.country, event.region) == ("japan", "japan")


def _gdacs(severity, countries, point=MEXICO_CITY, category="flood"):
    return NaturalEvent(id="gdacs-1", title="Flood", category=category, latitude=point[0],
                        longitude=point[1], date="", source="GDACS", severity=severity,
                        countries=countries)


def test_an_orange_event_outside_every_box_exists_for_a_country_with_a_market():
    (event,) = sentinel.analyze_natural_events([_gdacs("orange", ("MEX",))])
    assert event.country == "mexico" and event.severity == "orange"


def test_orange_is_not_enough_without_one_listed_country():
    assert sentinel.analyze_natural_events([_gdacs("orange", ("MEX", "GTM"))]) == []
    assert sentinel.analyze_natural_events([_gdacs("orange", ("NPL",))]) == []
    assert sentinel.analyze_natural_events([_gdacs("green", ("MEX",))]) == []


def test_red_still_passes_anywhere_as_before():
    (event,) = sentinel.analyze_natural_events([_gdacs("red", ())])
    assert event.country is None


# ── The cycle ─────────────────────────────────────────────────────────


class _Bundle:
    def __getattr__(self, name):  # pragma: no cover - trivial
        return []


def _run(db, monkeypatch, prices):
    event = _quake()
    inputs = orchestrator.CycleInputs(
        bundle=_Bundle(), events=[event], analyses=[analyze_event(event, stats={})],
        stats={}, prices=prices, yahoo=None, attempted={"EWW"},
    )
    monkeypatch.setattr(orchestrator, "_dispatch_notifications", lambda db, uid, results: (0, 0))
    return orchestrator.run_cycle(db, 1, inputs)


def test_a_template_signal_is_stored_with_its_country(db, monkeypatch):
    result = _run(db, monkeypatch, {"EWW": 61.2})
    assert result.new_signals == 1
    (signal,) = db.query(GeoSignal).all()
    assert (signal.country, signal.location) == ("mexico", "Mexico")
    assert signal.matched_rule_ids == '["tpl-earthquake-national"]'
    assert signal.importance < IMPORTANCE_THRESHOLD
    assert [(t.symbol, float(t.price_at_signal)) for t in signal.tickers] == [("EWW", 61.2)]


def test_a_template_signal_with_no_price_waits_for_the_next_cycle(db, monkeypatch):
    """One leg and no price is a signal that can never be measured, holding the
    event's dedup row for seven days."""
    assert _run(db, monkeypatch, {}).new_signals == 0
    assert db.query(GeoSignal).count() == 0
    assert _run(db, monkeypatch, {"EWW": 61.2}).new_signals == 1


# ── Price fetch order ─────────────────────────────────────────────────


def test_the_baskets_that_always_priced_are_asked_first():
    """A Yahoo stall leaves the tail unpriced; the tail must be the new funds."""
    order = fetch_order(["EIDO", "GLD", "ECH", "USO", "EWW", "XLE", "GLD"])
    assert order == ["GLD", "USO", "XLE", "ECH", "EIDO", "EWW"]
    assert fetch_order([]) == []
    assert set(COUNTRY_ETF.values()) <= set(INSTRUMENT_BREADTH)
