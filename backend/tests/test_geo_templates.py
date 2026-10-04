"""Template rules — the national reading of an event no hand-written rule covers.

An event outside every region box used to be dropped in the sentinel, and seven
countries had an instrument of their own. A template is one written chain per
event category, applied to whichever country the event is in. What must hold:

- beside a hand-written rule it **adds legs and nothing else**: in the mean
  confidence or the max risk it would change that signal's importance and
  re-page live signals on deploy day;
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
from backend.services.geo.countries import COUNTRY_ETF, COUNTRY_LOCALS, INSTRUMENT_COUNTRY
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
    match_regions,
    match_rules,
    match_templates,
    resolve_rule,
    rule_scope,
    scope_violations,
    scoring_rules,
    seed_rule_stats,
    template_floor_met,
)
from backend.services.geo.sentinel import GeoEvent

MEXICO_CITY = (19.4, -99.1)  # inside no region box
TOKYO = (35.7, 139.7)  # inside `japan`, where eq-japan-industrial lives
SANTIAGO = (-33.4, -70.6)  # inside `chile_mining`, where eq-chile-copper lives


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
    assert [r.id for r in result.matched_rules] == [
        "tpl-earthquake-national", "tpl-earthquake-local",
    ]
    assert [(t.symbol, t.direction) for t in result.tickers] == [
        ("EWW", "bearish"), ("PAC", "bearish"), ("OMAB", "bearish"),
    ]
    rule = result.matched_rules[0]
    assert rule.description == "Damaging earthquake in Mexico"
    assert "Mexico" in rule.thesis and "{" not in rule.thesis
    assert (result.confidence, result.risk_score) == (50.0, 7)  # PAGER orange: 6 + 1


def test_a_country_with_no_local_company_gets_the_national_reading_only():
    japan = _quake(MEXICO_CITY, country="japan")  # the point is irrelevant here
    assert [r.id for r in match_templates(japan)] == ["tpl-earthquake-national"]
    assert resolve_rule("tpl-earthquake-local", "japan") is None


def test_a_flood_and_a_cyclone_have_their_own_chain():
    flood = match_templates(_natural("flood"))
    cyclone = match_templates(_natural("cyclone", severity="red"))
    assert [r.id for r in flood] == ["tpl-flood-national", "tpl-flood-local"]
    assert [r.id for r in cyclone] == ["tpl-cyclone-national", "tpl-cyclone-local"]
    assert len({r.chain for r in (*flood, *cyclone)}) == 4


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


# ── Beside a hand-written rule: legs, and nothing else ────────────────


def test_a_template_never_moves_a_written_rules_confidence_or_risk():
    """An M7.2 under Tokyo is eq-japan-industrial at 52 and silent. With a
    template in the max risk the same quake would page at 60."""
    before = analyze_event(_quake(TOKYO, country=None, magnitude=7.2, pager=None), stats={})
    after = analyze_event(_quake(TOKYO, country="japan", magnitude=7.2, pager="red"), stats={})
    assert (after.confidence, after.risk_score) == (before.confidence, before.risk_score)
    assert compute_importance(after.confidence, after.risk_score) < IMPORTANCE_THRESHOLD
    # Japan's fund is already a leg of the written rule: the template adds nothing.
    assert [(t.symbol, t.direction) for t in after.tickers] == [
        (t.symbol, t.direction) for t in before.tickers
    ]
    assert [r.id for r in after.matched_rules] == ["eq-japan-industrial", "tpl-earthquake-national"]


def test_a_template_adds_the_national_and_local_legs_after_the_written_ones():
    before = analyze_event(_quake(SANTIAGO, country=None, pager=None), stats={})
    after = analyze_event(_quake(SANTIAGO, country="chile", pager="red"), stats={})
    assert [r.id for r in before.matched_rules] == ["eq-chile-copper"]
    assert (after.confidence, after.risk_score) == (before.confidence, before.risk_score)
    assert [(t.symbol, t.direction) for t in after.tickers] == [
        ("HG=F", "bullish"), ("ANTO.L", "bearish"),  # the written rule, untouched
        ("ECH", "bearish"), ("BCH", "bearish"), ("ENIC", "bearish"),
    ]


def test_scoring_rules_are_the_written_ones_when_there_are_any():
    written = match_rules(_quake(SANTIAGO, country="chile"))
    templates = match_templates(_quake(SANTIAGO, country="chile", pager="red"))
    assert scoring_rules(written + templates) == written
    assert scoring_rules(templates) == templates  # nothing else to score with
    assert scoring_rules([]) == []


# ── Invariants for every country a template can be rendered for ───────


def test_every_rendering_obeys_what_the_hand_written_rules_obey():
    symbols = {t.symbol for r in FAST_RULES for t in r.tickers} | set(INSTRUMENT_COUNTRY)
    for template in TEMPLATE_RULES:
        for slug in COUNTRY_ETF:
            rule = resolve_rule(template.id, slug)
            where = f"{template.id} / {slug}"
            if rule is None:  # a local template in a country with no local company
                assert template.tier == "local" and slug not in COUNTRY_LOCALS, where
                continue
            assert rule_scope(rule) == "local" and rule.scope in SCOPE_RANK, where
            assert len(rule.chain) == 3 and all(c.strip() for c in rule.chain), where
            assert "{" not in " ".join((*rule.chain, rule.description)), where
            assert not [s for s in symbols for clause in rule.chain[:2] if s in clause], where
            assert scope_violations(rule) == [], where
            assert rule.thesis == " → ".join(rule.chain), where


def test_a_template_leg_is_always_the_events_own_country():
    """The gate, by construction: a Brazilian event cannot load Indonesia's market."""
    rendered = 0
    for template in TEMPLATE_RULES:
        for slug in COUNTRY_ETF:
            rule = resolve_rule(template.id, slug)
            for leg in rule.tickers if rule else ():
                rendered += 1
                assert INSTRUMENT_COUNTRY[leg.symbol] == slug
                assert instrument_tier(leg.symbol) == template.tier
                assert leg.direction == "bearish"
    locals_ = sum(len(v) for v in COUNTRY_LOCALS.values())
    assert rendered == 3 * (len(COUNTRY_ETF) + locals_)


def test_local_companies_are_few_listed_in_the_us_and_bound_to_a_covered_country():
    assert set(COUNTRY_LOCALS) <= set(COUNTRY_ETF)
    for slug, symbols in COUNTRY_LOCALS.items():
        assert 1 <= len(symbols) <= 2, slug
        for symbol in symbols:
            # A US listing has no exchange suffix: the +1h/+6h checkpoints are
            # measured on the US session.
            assert "." not in symbol and "=" not in symbol, symbol
            assert INSTRUMENT_BREADTH[symbol] == "national"
            assert instrument_tier(symbol) == "local"


def test_template_ids_do_not_collide_with_rule_ids():
    assert not {t.id for t in TEMPLATE_RULES} & {r.id for r in FAST_RULES}
    assert all(t.id.startswith("tpl-") for t in TEMPLATE_RULES)


# ── Importance: on the board, not on the phone ────────────────────────


def _worst_case(template_id: str) -> GeoEvent:
    if "earthquake" in template_id:
        return _quake(magnitude=8.4, pager="red")
    category = template_id.split("-")[1]
    return _natural(category, severity="red")


def test_an_unlearned_template_cannot_page_at_its_worst():
    for template in TEMPLATE_RULES:
        event = _worst_case(template.id)
        rule = next(r for r in match_templates(event) if r.id == template.id)
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
    rule = match_templates(event)[0]
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
    assert [t.symbol for t in result.tickers] == ["EWW", "PAC", "OMAB", "GLD"]


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


def test_a_big_quake_that_damaged_nothing_does_not_get_in_through_the_country_door():
    """No box used to mean no event. Admitting every M5.5+ in a covered country
    would hand an M7 that PAGER rates green to the generative LLM (it is
    "salient" on magnitude alone) — the case the floor exists to reject."""
    for alert in ("green", None):
        quake = _seismic("12 km S of Mexico City, Mexico", MEXICO_CITY, magnitude=7.2, alert=alert)
        assert sentinel.analyze_earthquakes([quake]) == [], alert


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
        stats={}, prices=prices, yahoo=None, attempted={"EWW", "PAC", "OMAB"},
    )
    monkeypatch.setattr(orchestrator, "_dispatch_notifications", lambda db, uid, results: (0, 0))
    return orchestrator.run_cycle(db, 1, inputs)


def test_a_template_signal_is_stored_with_its_country(db, monkeypatch):
    result = _run(db, monkeypatch, {"EWW": 61.2, "PAC": 190.0, "OMAB": 88.0})
    assert result.new_signals == 1
    (signal,) = db.query(GeoSignal).all()
    assert (signal.country, signal.location) == ("mexico", "Mexico")
    assert signal.matched_rule_ids == '["tpl-earthquake-national", "tpl-earthquake-local"]'
    assert signal.importance < IMPORTANCE_THRESHOLD
    assert [(t.symbol, float(t.price_at_signal)) for t in signal.tickers] == [
        ("EWW", 61.2), ("PAC", 190.0), ("OMAB", 88.0),
    ]


def test_a_template_signal_with_no_price_waits_for_the_next_cycle(db, monkeypatch):
    """No leg priced is a signal that can never be measured, holding the event's
    dedup row for seven days."""
    assert _run(db, monkeypatch, {}).new_signals == 0
    assert db.query(GeoSignal).count() == 0
    assert _run(db, monkeypatch, {"EWW": 61.2}).new_signals == 1


# ── A signal tracked before the damage was rated ──────────────────────


def _cycle(db, monkeypatch, event, prices):
    analysis = analyze_event(event, stats={})
    inputs = orchestrator.CycleInputs(
        bundle=_Bundle(), events=[event], analyses=[analysis], stats={}, prices=dict(prices),
        yahoo=None,
        # Every leg was "tried" by the shared fetch: an unpriced one must stay
        # unpriced rather than send the cycle to Yahoo for it.
        attempted={t.symbol for t in analysis.tickers},
    )
    monkeypatch.setattr(orchestrator, "_dispatch_notifications", lambda db, uid, results: (0, 0))
    return orchestrator.run_cycle(db, 1, inputs)


CHILE_PRICES = {"HG=F": 4.5, "ANTO.L": 3800.0, "ECH": 31.0, "BCH": 28.0, "ENIC": 3.6}


def test_a_signal_gains_the_template_legs_when_the_rating_arrives(db, monkeypatch):
    """USGS rates the damage some minutes after the quake. The cycle that tracked
    it first saw no rating, so the written rule matched alone; a basket only ever
    written at creation would never carry Chile's market or its companies."""
    first = _quake(SANTIAGO, country="chile", pager=None, event_id="eq-late")
    _cycle(db, monkeypatch, first, CHILE_PRICES)
    (signal,) = db.query(GeoSignal).all()
    before = (signal.importance, float(signal.confidence), float(signal.risk_score))
    assert [t.symbol for t in signal.tickers] == ["HG=F", "ANTO.L"]

    rated = _quake(SANTIAGO, country="chile", pager="orange", event_id="eq-late")
    result = _cycle(db, monkeypatch, rated, {**CHILE_PRICES, "ECH": 30.2})
    db.expire_all()
    (signal,) = db.query(GeoSignal).all()
    assert result.new_signals == 0, "the same signal, not a second one"
    assert [t.symbol for t in signal.tickers] == ["HG=F", "ANTO.L", "ECH", "BCH", "ENIC"]
    assert float(next(t for t in signal.tickers if t.symbol == "ECH").price_at_signal) == 30.2
    assert signal.matched_rule_ids == (
        '["eq-chile-copper", "tpl-earthquake-national", "tpl-earthquake-local"]'
    )
    assert (signal.importance, float(signal.confidence), float(signal.risk_score)) == before
    assert signal.direction.value == "bearish"  # one leg up, four down: the stored basket's

    _cycle(db, monkeypatch, rated, CHILE_PRICES)  # a third cycle adopts nothing twice
    db.expire_all()
    assert len(db.query(GeoSignal).one().tickers) == 5


def test_the_direction_is_the_stored_baskets_when_nothing_can_be_adopted(db, monkeypatch):
    """Before, the refresh took the analysis' direction — which now counts
    template legs the signal may not carry yet."""
    _cycle(db, monkeypatch, _quake(SANTIAGO, country="chile", pager=None, event_id="eq-np"),
           CHILE_PRICES)
    rated = _quake(SANTIAGO, country="chile", pager="orange", event_id="eq-np")
    _cycle(db, monkeypatch, rated, {"HG=F": 4.5, "ANTO.L": 3800.0})  # no price for the new legs
    db.expire_all()
    (signal,) = db.query(GeoSignal).all()
    assert [t.symbol for t in signal.tickers] == ["HG=F", "ANTO.L"]
    assert signal.direction.value == "neutral"  # one up, one down, as stored
    assert signal.matched_rule_ids == '["eq-chile-copper"]'


def test_a_template_whose_leg_the_signal_already_carries_only_joins_the_record(db, monkeypatch):
    """Japan's fund is a leg of the written rule: nothing to add, but the
    template must still be taught by it at +7d."""
    prices = {"EWJ": 70.0, "TM": 180.0}
    _cycle(db, monkeypatch, _quake(TOKYO, country="japan", magnitude=7.2, pager=None,
                                   event_id="eq-jp"), prices)
    _cycle(db, monkeypatch, _quake(TOKYO, country="japan", magnitude=7.2, pager="red",
                                   event_id="eq-jp"), prices)
    db.expire_all()
    (signal,) = db.query(GeoSignal).all()
    assert [t.symbol for t in signal.tickers] == ["EWJ", "TM"]
    assert signal.matched_rule_ids == '["eq-japan-industrial", "tpl-earthquake-national"]'


# ── Two fallbacks, one event ──────────────────────────────────────────


def test_an_event_a_template_reads_does_not_also_get_a_generated_thesis(monkeypatch):
    """Both are for events no written rule covers. The template is deterministic
    and measurable; the generative call is skipped for anything that already has
    legs. An M7+ in a box with no quake rule used to get a generated thesis that
    could page at 68 — it is now a template signal at 40 at most, until the
    template has a record. Decided, not accidental."""
    calls = []
    monkeypatch.setattr(orchestrator, "analyze_unmatched",
                        lambda event, regime=None: calls.append(event.id))
    manila = _quake((14.6, 121.0), country="philippines", magnitude=7.4, pager="red")
    assert match_regions(14.6, 121.0) and match_rules(manila) == []  # boxed, no quake rule
    analyses = [analyze_event(manila, stats={})]
    assert orchestrator._generative_pass(analyses, None) == 0 and calls == []
    assert [t.symbol for t in analyses[0].tickers] == ["EPHE", "PHI"]


# ── Price fetch order ─────────────────────────────────────────────────


def test_the_baskets_that_always_priced_are_asked_first():
    """A Yahoo stall leaves the tail unpriced; the tail must be the new funds."""
    order = fetch_order(["EIDO", "GLD", "ECH", "USO", "EWW", "XLE", "GLD"])
    assert order == ["GLD", "USO", "XLE", "ECH", "EIDO", "EWW"]
    assert fetch_order([]) == []
    assert set(COUNTRY_ETF.values()) <= set(INSTRUMENT_BREADTH)
