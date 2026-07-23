"""Geo-economic correlation rules — Python port of WorldHawk's rules.ts.

63 fast rules across 22 categories + 50 geo-regions + the condition matcher.
See tasks/geo-rules-spec.md for the authoritative spec. Direction: ↑ = bullish, ↓ = bearish.

Port decisions (flagged in the spec as un-enforced in the JS matcher):
- ``fire.cluster>=N``: IMPLEMENTED here (the sentinel computes cluster size; gating
  on it makes the fire rules behave as written — only major clusters move markets).
- ``near_nuclear_plant`` (rule ``nuclear-incident``): KEPT AS-IS / dormant. The
  sentinel never emits a ``nuclear`` event type (earthquakes are tagged
  ``earthquake``), so this rule never matches in production either. Implementing a
  real plant-proximity check needs an external plant database — out of scope.
"""

import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models import GeoRuleStat

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleTicker:
    symbol: str
    direction: str  # bullish | bearish | neutral


@dataclass(frozen=True)
class FastRule:
    id: str
    category: str  # must equal event.type to match (except "compound")
    condition: str
    description: str
    tickers: tuple[RuleTicker, ...]
    direction: str  # thesis / rationale (free text)
    base_confidence: float


def _t(spec: str) -> tuple[RuleTicker, ...]:
    """Parse a compact 'SYM+ SYM- ...' ticker spec (+=bullish, -=bearish)."""
    out: list[RuleTicker] = []
    for tok in spec.split():
        if tok.endswith("+"):
            out.append(RuleTicker(tok[:-1], "bullish"))
        elif tok.endswith("-"):
            out.append(RuleTicker(tok[:-1], "bearish"))
        else:
            out.append(RuleTicker(tok, "neutral"))
    return tuple(out)


# ── 50 geo-regions (axis-aligned lat/lon boxes) ──────────────────────
# (latMin, latMax, lonMin, lonMax)
GEO_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "chile_mining": (-35, -18, -72, -68),
    "peru_mining": (-18, -5, -80, -68),
    "japan": (24, 46, 122, 146),
    "taiwan": (21, 26, 119, 123),
    "turkey": (36, 42, 26, 45),
    "indonesia_mining": (-8, 2, 95, 141),
    "gulf_of_mexico": (18, 31, -98, -80),
    "florida": (24, 31, -88, -79),
    "caribbean": (10, 24, -86, -59),
    "southeast_asia": (-10, 23, 95, 145),
    "india_coast": (5, 25, 68, 92),
    "california": (32, 42, -125, -114),
    "canada_forest": (45, 65, -130, -60),
    "amazon": (-15, 5, -75, -45),
    "australia": (-40, -10, 110, 155),
    "mediterranean": (34, 44, -10, 36),
    "iceland": (63, 67, -25, -13),
    "china_industrial": (20, 42, 100, 125),
    "bangladesh": (20, 27, 88, 93),
    "us_midwest": (36, 49, -104, -80),
    "germany_rhine": (47, 52, 6, 10),
    "middle_east_oil": (12, 38, 35, 60),
    "strait_of_hormuz": (24, 28, 54, 58),
    "ukraine_black_sea": (41, 52, 28, 42),
    "south_china_sea": (4, 24, 105, 121),
    "korean_peninsula": (33, 43, 124, 132),
    "suez_red_sea": (12, 32, 32, 44),
    "malacca_strait": (-2, 7, 98, 106),
    "panama_canal": (7, 10, -81, -78),
    "us_northeast": (38, 47, -80, -67),
    "texas": (25, 37, -107, -93),
    "northern_europe": (50, 72, -12, 30),
    "us_great_plains": (30, 49, -106, -90),
    "brazil_southeast": (-25, -15, -52, -39),
    "india": (6, 36, 68, 97),
    "iran": (25, 40, 44, 63),
    "north_atlantic_shipping": (40, 60, -60, -10),
    "cape_good_hope": (-40, -32, 16, 22),
    "indonesia": (-10, 5, 95, 141),
    "east_china_sea": (24, 34, 120, 130),
    "sahel": (10, 20, -17, 24),
    "nigeria_oil": (4, 10, 2, 9),
    "horn_of_africa": (-2, 18, 32, 52),
    "drc_mining": (-8, 2, 22, 32),
    "libya": (19, 34, 9, 25),
    "myanmar": (9, 29, 92, 102),
    # Commodity-basin boxes: narrow, single-commodity chokepoints where one
    # physical event moves one price. Deliberately overlap the broader boxes
    # above — match_regions returns every containing box, so an event can carry
    # both theses (e.g. an Atacama quake is copper AND lithium).
    "west_africa_cocoa": (4, 11, -8, 2),
    "australia_pilbara": (-24, -18, 114, 122),
    "lithium_triangle": (-27, -20, -70, -64),
}


def match_regions(lat: float, lon: float) -> list[str]:
    """Return every region whose bounding box contains the point (overlap is intentional)."""
    out: list[str] = []
    for rid, (lat_min, lat_max, lon_min, lon_max) in GEO_REGIONS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            out.append(rid)
    return out


# ── 63 fast rules ────────────────────────────────────────────────────
FAST_RULES: tuple[FastRule, ...] = (
    # Earthquakes
    FastRule("eq-chile-copper", "earthquake", "earthquake.magnitude>=6 && region=chile_mining", "Major Chilean earthquake disrupts copper supply", _t("COPX+ FCX- SCCO-"), "Copper supply disruption → COPX up, miners down", 0.82),
    FastRule("eq-japan-industrial", "earthquake", "earthquake.magnitude>=6.5 && region=japan", "Major Japanese earthquake hits industrial base", _t("EWJ- TM- GLD+"), "Japanese industrial disruption → equities down, gold up", 0.75),
    FastRule("eq-taiwan-semi", "earthquake", "earthquake.magnitude>=6 && region=taiwan", "Taiwan earthquake threatens semiconductor production", _t("TSM- SOXX- INTC+ SSNLF+"), "Semi supply shock → TSMC down, competitors up", 0.78),
    FastRule("eq-turkey", "earthquake", "earthquake.magnitude>=6.5 && region=turkey", "Major Turkish earthquake", _t("TUR- X+ GLD+"), "Turkish disruption, reconstruction demand for steel", 0.70),
    FastRule("eq-indonesia-nickel", "earthquake", "earthquake.magnitude>=6 && region=indonesia_mining", "Indonesian earthquake disrupts nickel mining", _t("VALE- NI=F+"), "Nickel supply disruption", 0.68),
    FastRule("eq-peru-copper", "earthquake", "earthquake.magnitude>=6 && region=peru_mining", "Peruvian earthquake disrupts copper supply", _t("COPX+ FCX- SCCO-"), "Copper supply disruption", 0.76),
    FastRule("eq-lithium-triangle", "earthquake", "earthquake.magnitude>=6 && region=lithium_triangle", "Atacama/Puna earthquake disrupts lithium brine operations", _t("LIT+ ALB+ SQM-"), "Brine/port disruption → lithium price up, local producer SQM hit", 0.74),
    # Cyclones / hurricanes
    FastRule("cyc-gulf-oil", "cyclone", "region=gulf_of_mexico", "Hurricane threatens Gulf of Mexico oil/gas", _t("USO+ UNG+ XLE+ XOM+ CVX+"), "Gulf production shut-ins → energy up", 0.85),
    FastRule("cyc-florida-insurance", "cyclone", "region=florida", "Hurricane hits Florida", _t("ALL- TRV- HIG- HD+ LOW+"), "Insurance losses, rebuilding demand", 0.80),
    FastRule("cyc-caribbean-tourism", "cyclone", "region=caribbean", "Hurricane disrupts Caribbean tourism", _t("JETS- DAL- RCL- CCL-"), "Tourism/cruise disruption", 0.72),
    FastRule("cyc-southeast-asia", "cyclone", "region=southeast_asia", "Cyclone hits Southeast Asia", _t("EWY- DBA+"), "Regional disruption, agri prices", 0.65),
    FastRule("cyc-india-agriculture", "cyclone", "region=india_coast", "Cyclone hits Indian coast agriculture", _t("DBA+ INDA-"), "Agricultural disruption", 0.68),
    FastRule("cyc-australia-ironore", "cyclone", "region=australia_pilbara", "Cyclone shuts in Pilbara iron-ore export ports", _t("BHP- RIO- VALE+"), "Port Hedland shut-in → Australian export volume lost, Vale gains on tighter seaborne supply", 0.80),
    # Wildfires
    FastRule("fire-california", "fire", "fire.cluster>=50 && region=california", "Major California wildfires", _t("ALL- TRV- PCG- HD+"), "Insurance losses, utility liability", 0.78),
    FastRule("fire-canada-lumber", "fire", "fire.cluster>=30 && region=canada_forest", "Canadian wildfires disrupt lumber", _t("LBS=F+ WY+"), "Lumber supply disruption", 0.74),
    FastRule("fire-amazon", "fire", "fire.cluster>=100 && region=amazon", "Major Amazon fires", _t("DBA+ SOYB+ EWZ-"), "Agricultural / soy supply impact", 0.65),
    FastRule("fire-australia-mining", "fire", "fire.cluster>=30 && region=australia", "Australian fires disrupt mining", _t("BHP- RIO- GLD+"), "Mining disruption", 0.60),
    FastRule("fire-greece-tourism", "fire", "fire.cluster>=20 && region=mediterranean", "Mediterranean fires disrupt tourism", _t("JETS-"), "Tourism disruption", 0.55),
    # Volcanoes
    FastRule("vol-iceland-aviation", "volcano", "region=iceland", "Icelandic volcano disrupts aviation", _t("JETS- DAL- UAL- AAL-"), "Ash cloud grounds flights", 0.83),
    FastRule("vol-indonesia-palm", "volcano", "region=indonesia", "Indonesian volcano disrupts palm oil", _t("DBA+"), "Palm oil / agri disruption", 0.55),
    FastRule("vol-japan", "volcano", "region=japan", "Japanese volcanic activity", _t("EWJ- JETS- GLD+"), "Regional disruption", 0.65),
    # Floods
    FastRule("flood-china-industry", "flood", "region=china_industrial", "Flooding hits Chinese industrial base", _t("FXI- DBA+ SOXX-"), "Industrial / supply disruption", 0.72),
    FastRule("flood-bangladesh-textile", "flood", "region=bangladesh", "Flooding hits Bangladesh textiles", _t("XRT-"), "Textile supply disruption", 0.58),
    FastRule("flood-midwest-grain", "flood", "region=us_midwest", "Flooding hits US Midwest grain", _t("WEAT+ ZC=F+ DBA+"), "Grain supply disruption", 0.80),
    FastRule("flood-germany-rhine", "flood", "region=germany_rhine", "Rhine flooding disrupts logistics", _t("EWG- UNG+"), "Logistics / energy disruption", 0.65),
    FastRule("flood-westafrica-cocoa", "flood", "region=west_africa_cocoa", "West African flooding drives black-pod disease in cocoa", _t("CC=F+ HSY- MDLZ-"), "Excess rain → black-pod harvest loss → cocoa up, chocolate makers squeezed on input cost", 0.62),
    # Conflicts / geopolitical (alert-zone driven, category conflict)
    FastRule("conflict-mideast-oil", "conflict", "alert.severity=red && region=middle_east_oil", "Middle East oil conflict", _t("USO+ UNG+ XLE+ LMT+ RTX+ NOC+ ITA+ GLD+"), "Oil supply risk, defense demand", 0.88),
    FastRule("conflict-hormuz-strait", "conflict", "region=strait_of_hormuz", "Strait of Hormuz tension", _t("USO+ XOM+ CVX+"), "Oil chokepoint risk", 0.90),
    FastRule("conflict-ukraine-grain", "conflict", "region=ukraine_black_sea", "Ukraine/Black Sea conflict", _t("WEAT+ DBA+ UNG+ LMT+ RTX+"), "Grain export risk, defense demand", 0.82),
    FastRule("conflict-south-china-sea", "conflict", "region=south_china_sea", "South China Sea tension", _t("FXI- TSM- LMT+ GLD+"), "Regional risk, defense demand", 0.75),
    FastRule("conflict-korea", "conflict", "alert.severity=red && region=korean_peninsula", "Korean Peninsula conflict", _t("EWY- LMT+ NOC+ GLD+"), "Regional risk, defense demand", 0.72),
    FastRule("conflict-suez", "conflict", "region=suez_red_sea", "Suez/Red Sea disruption", _t("USO+ ZIM+ DAC+"), "Shipping chokepoint risk", 0.80),
    FastRule("conflict-iran-nuclear", "conflict", "alert.severity=red && region=iran", "Iran nuclear/military escalation", _t("USO+ GLD+ LMT+ RTX+ ITA+"), "Oil risk, defense demand", 0.84),
    # Maritime (mixed)
    FastRule("maritime-panama-drought", "drought", "region=panama_canal", "Panama Canal drought restricts transit", _t("ZIM+ DAC+ USO+"), "Shipping capacity reduction", 0.75),
    FastRule("maritime-malacca-tension", "conflict", "region=malacca_strait", "Malacca Strait tension", _t("USO+ FXI- EWJ-"), "Shipping chokepoint risk", 0.78),
    # AIS-derived maritime
    FastRule("ais-tanker-drop-hormuz", "maritime_disruption", "region=strait_of_hormuz", "Tanker traffic drop at Hormuz", _t("USO+ XLE+ GLD+ UNG+"), "Oil chokepoint disruption", 0.85),
    FastRule("ais-tanker-drop-suez", "maritime_disruption", "region=suez_red_sea", "Tanker traffic drop at Suez", _t("USO+ ZIM+ DAC+"), "Shipping disruption", 0.82),
    FastRule("ais-reroute-cape", "maritime_rerouting", "region=cape_good_hope", "Shipping reroutes via Cape of Good Hope", _t("USO+ ZIM+ DAC+ BDRY+"), "Longer routes, higher freight", 0.80),
    FastRule("ais-cargo-drop-malacca", "maritime_disruption", "region=malacca_strait", "Cargo traffic drop at Malacca", _t("FXI- EWJ- TSM- BDRY+"), "Asian trade disruption", 0.80),
    FastRule("ais-congestion-suez", "maritime_congestion", "region=suez_red_sea", "Congestion at Suez", _t("ZIM+ DAC+ USO+"), "Shipping delays", 0.72),
    FastRule("ais-cargo-drop-panama", "maritime_disruption", "region=panama_canal", "Cargo traffic drop at Panama", _t("ZIM+ DAC+ BDRY+"), "Shipping disruption", 0.75),
    # Storms
    FastRule("storm-us-winter", "storm", "region=us_northeast", "Winter storm hits US Northeast", _t("UNG+ JETS- DAL-"), "Heating demand, flight disruption", 0.73),
    FastRule("storm-texas-freeze", "storm", "region=texas", "Texas freeze event", _t("UNG+ USO+ XLE+"), "Energy demand spike, production freeze", 0.80),
    FastRule("storm-europe-energy", "storm", "region=northern_europe", "European storm hits energy", _t("UNG+ JETS-"), "Energy demand, flight disruption", 0.62),
    # Drought / agriculture
    FastRule("drought-us-breadbasket", "drought", "region=us_great_plains", "US Great Plains drought", _t("WEAT+ ZC=F+ DBA+"), "Grain supply reduction", 0.82),
    FastRule("drought-brazil-coffee", "drought", "region=brazil_southeast", "Brazil drought hits coffee/soy", _t("KC=F+ SOYB+ DBA+ EWZ-"), "Coffee/soy supply reduction", 0.78),
    FastRule("drought-india-monsoon", "drought", "region=india", "Indian monsoon failure", _t("DBA+ INDA-"), "Agricultural disruption", 0.70),
    FastRule("drought-westafrica-cocoa", "drought", "region=west_africa_cocoa", "Ivory Coast/Ghana drought hits cocoa supply", _t("CC=F+ HSY- MDLZ-"), "~60% of world cocoa → supply shock lifts cocoa, chocolate makers down on input cost", 0.78),
    # Nuclear / infra (declared but dormant — see module docstring)
    FastRule("nuclear-incident", "nuclear", "earthquake.magnitude>=5 && near_nuclear_plant", "Nuclear plant incident", _t("URA- CCJ- XLE+ UNG+"), "Nuclear supply risk, alt-energy demand", 0.70),
    # Iceberg / Arctic
    FastRule("iceberg-shipping", "iceberg", "region=north_atlantic_shipping", "Iceberg threatens North Atlantic shipping", _t("ZIM- JETS-"), "Shipping route risk", 0.45),
    # Extreme weather — Windy
    FastRule("wx-heat-texas", "extreme_heat", "region=texas", "Extreme heat in Texas", _t("UNG+ USO+ XLE+"), "Cooling demand spike", 0.78),
    FastRule("wx-heat-india", "extreme_heat", "region=india", "Extreme heat in India", _t("DBA+ INDA- WEAT+"), "Crop stress, demand", 0.72),
    FastRule("wx-heat-mediterranean", "extreme_heat", "region=mediterranean", "Extreme heat in Mediterranean", _t("JETS- DBA+"), "Tourism/agri impact", 0.60),
    FastRule("wx-cold-us-northeast", "extreme_cold", "region=us_northeast", "Extreme cold in US Northeast", _t("UNG+ USO+ JETS- DAL-"), "Heating demand, disruption", 0.80),
    FastRule("wx-cold-northern-europe", "extreme_cold", "region=northern_europe", "Extreme cold in Northern Europe", _t("UNG+ EWG-"), "Heating demand", 0.75),
    FastRule("wx-storm-gulf", "severe_storm", "region=gulf_of_mexico", "Severe storm in Gulf of Mexico", _t("USO+ XLE+ XOM+ CVX+"), "Energy production risk", 0.82),
    FastRule("wx-storm-northern-europe", "severe_storm", "region=northern_europe", "Severe storm in Northern Europe", _t("ALL- TRV- JETS-"), "Insurance losses, disruption", 0.68),
    FastRule("wx-precip-us-midwest", "heavy_precipitation", "region=us_midwest", "Heavy precipitation in US Midwest", _t("WEAT+ ZC=F+ DBA+"), "Crop disruption", 0.77),
    FastRule("wx-precip-china", "heavy_precipitation", "region=china_industrial", "Heavy precipitation in China", _t("FXI- SOXX-"), "Industrial disruption", 0.70),
    FastRule("wx-lowpres-atlantic", "deep_cyclone", "region=north_atlantic_shipping", "Deep cyclone in North Atlantic", _t("ZIM- BDRY- JETS-"), "Shipping disruption", 0.60),
    # Flight anomalies — OpenSky
    FastRule("air-closure-mideast", "airspace_closure", "region=middle_east_oil", "Airspace closure over Middle East", _t("USO+ GLD+ LMT+ RTX+ JETS-"), "Conflict signal, oil risk", 0.85),
    FastRule("air-closure-ukraine", "airspace_closure", "region=ukraine_black_sea", "Airspace closure over Ukraine", _t("WEAT+ UNG+ LMT+ JETS-"), "Conflict escalation", 0.82),
    FastRule("air-closure-taiwan", "airspace_closure", "region=taiwan", "Airspace closure over Taiwan", _t("TSM- SOXX- FXI- LMT+ GLD+"), "Semi supply + conflict risk", 0.88),
    FastRule("air-closure-korea", "airspace_closure", "region=korean_peninsula", "Airspace closure over Korea", _t("EWY- LMT+ NOC+ GLD+"), "Conflict risk", 0.80),
    FastRule("air-closure-iran", "airspace_closure", "region=iran", "Airspace closure over Iran", _t("USO+ GLD+ LMT+ ITA+"), "Oil + conflict risk", 0.86),
    FastRule("air-military-mideast", "military_surge", "region=middle_east_oil", "Military flight surge in Middle East", _t("USO+ LMT+ RTX+ NOC+ GLD+"), "Military buildup", 0.83),
    FastRule("air-military-europe", "military_surge", "region=northern_europe", "Military flight surge in Europe", _t("LMT+ RTX+ UNG+"), "Military buildup", 0.70),
    FastRule("air-military-scs", "military_surge", "region=south_china_sea", "Military flight surge in South China Sea", _t("FXI- LMT+ TSM- GLD+"), "Military buildup", 0.75),
    # GDELT geopolitical
    FastRule("gdelt-conflict-mideast", "armed_conflict", "region=middle_east_oil", "Armed conflict in Middle East (GDELT)", _t("USO+ XLE+ GLD+ LMT+"), "Oil risk, defense demand", 0.84),
    FastRule("gdelt-conflict-ukraine", "armed_conflict", "region=ukraine_black_sea", "Armed conflict in Ukraine (GDELT)", _t("WEAT+ UNG+ LMT+ RTX+"), "Grain + defense", 0.80),
    FastRule("gdelt-military-taiwan", "military_escalation", "region=taiwan", "Military escalation Taiwan (GDELT)", _t("TSM- SOXX- FXI- LMT+ GLD+"), "Semi + defense", 0.82),
    FastRule("gdelt-military-korea", "military_escalation", "region=korean_peninsula", "Military escalation Korea (GDELT)", _t("EWY- LMT+ NOC+ GLD+"), "Defense demand", 0.76),
    FastRule("gdelt-sanctions-iran", "sanctions", "region=iran", "Sanctions on Iran (GDELT)", _t("USO+ GLD+ XLE+"), "Oil supply risk", 0.78),
    FastRule("gdelt-sanctions-china", "sanctions", "region=china_industrial", "Sanctions on China (GDELT)", _t("FXI- SOXX- TSM- GLD+"), "Trade/tech disruption", 0.74),
    FastRule("gdelt-protest-mideast", "mass_protest", "region=middle_east_oil", "Mass protest in Middle East (GDELT)", _t("USO+ XLE+"), "Instability, oil risk", 0.65),
    FastRule("gdelt-trade-dispute-china", "trade_dispute", "region=china_industrial", "Trade dispute with China (GDELT)", _t("FXI- DBA+ GLD+"), "Trade disruption", 0.70),
    FastRule("gdelt-escalation-cluster", "geopolitical_escalation", "", "Geopolitical escalation cluster (GDELT)", _t("GLD+ LMT+ RTX+ ITA+ USO+"), "Broad risk-off", 0.80),
    FastRule("gdelt-cooperation-mideast", "diplomatic_cooperation", "region=middle_east_oil", "Diplomatic cooperation Middle East (GDELT)", _t("USO- GLD-"), "De-escalation, risk-on", 0.60),
    # ACLED conflict
    FastRule("acled-conflict-mideast-oil", "armed_conflict", "region=middle_east_oil", "Armed conflict Middle East (ACLED)", _t("USO+ XLE+ GLD+ LMT+ RTX+"), "Oil risk, defense", 0.86),
    FastRule("acled-conflict-suez", "armed_conflict", "region=suez_red_sea", "Armed conflict Suez/Red Sea (ACLED)", _t("USO+ ZIM+ DAC+ GLD+"), "Shipping + oil risk", 0.84),
    FastRule("acled-conflict-sahel", "armed_conflict", "region=sahel", "Armed conflict Sahel (ACLED)", _t("URA+ GLD+ GDX+"), "Uranium/gold supply risk", 0.72),
    FastRule("acled-conflict-nigeria", "armed_conflict", "region=nigeria_oil", "Armed conflict Nigeria Delta (ACLED)", _t("USO+ XLE+"), "Oil supply risk", 0.70),
    FastRule("acled-conflict-ukraine", "armed_conflict", "region=ukraine_black_sea", "Armed conflict Ukraine (ACLED)", _t("WEAT+ UNG+ LMT+ RTX+ NOC+"), "Grain + defense", 0.82),
    FastRule("acled-conflict-horn-africa", "armed_conflict", "region=horn_of_africa", "Armed conflict Horn of Africa (ACLED)", _t("USO+ ZIM+ DBA+"), "Shipping + supply risk", 0.74),
    FastRule("acled-military-taiwan", "military_escalation", "region=taiwan", "Military escalation Taiwan (ACLED)", _t("TSM- SOXX- LMT+ GLD+"), "Semi + defense", 0.84),
    FastRule("acled-protest-mideast", "mass_protest", "region=middle_east_oil", "Mass protest Middle East (ACLED)", _t("USO+ XLE+ GLD+"), "Instability, oil risk", 0.68),
    FastRule("acled-protest-china", "mass_protest", "region=china_industrial", "Mass protest China (ACLED)", _t("FXI- SOXX- GLD+"), "Instability", 0.66),
    FastRule("acled-protest-southeast-asia", "mass_protest", "region=southeast_asia", "Mass protest Southeast Asia (ACLED)", _t("EWY- DBA+"), "Regional instability", 0.60),
    FastRule("acled-escalation-cluster", "geopolitical_escalation", "", "Geopolitical escalation cluster (ACLED)", _t("GLD+ LMT+ RTX+ ITA+ USO+"), "Broad risk-off", 0.82),
    FastRule("acled-conflict-drc-cobalt", "armed_conflict", "region=drc_mining", "Armed conflict DRC mining (ACLED)", _t("LIT+ REMX+"), "Cobalt/lithium supply risk", 0.70),
    # Compound (evaluated by the orchestrator, NOT the per-event matcher)
    FastRule("compound-energy-crisis", "compound", "multiple_energy_events>=2", "Compound energy crisis", _t("USO+ UNG+ XLE+ GLD+"), "Multiple simultaneous energy shocks", 0.88),
    FastRule("compound-food-crisis", "compound", "multiple_food_events>=2", "Compound food crisis", _t("DBA+ WEAT+ SOYB+"), "Multiple simultaneous food shocks", 0.85),
    FastRule("compound-geopolitical-escalation", "compound", "multiple_conflict_events>=2", "Compound geopolitical escalation", _t("GLD+ LMT+ RTX+ NOC+ ITA+"), "Multiple simultaneous conflicts", 0.82),
)

RULES_BY_ID: dict[str, FastRule] = {r.id: r for r in FAST_RULES}

# Condition DSL token parsers.
_RE_REGION = re.compile(r"region=(\w+)")
_RE_MAGNITUDE = re.compile(r"earthquake\.magnitude>=(\d+\.?\d*)")
_RE_SEVERITY = re.compile(r"alert\.severity=(\w+)")
_RE_CLUSTER = re.compile(r"fire\.cluster>=(\d+)")


def match_rules(event) -> list[FastRule]:
    """Return rules matching a single financial event (see GeoEvent in sentinel).

    Mirrors WorldHawk's matchRules + the spec's two enforced port decisions:
    region / magnitude / severity (as in JS) PLUS fire.cluster gating (new).
    Compound rules are skipped here (handled by the orchestrator).
    """
    regions = match_regions(event.latitude, event.longitude)
    out: list[FastRule] = []

    for rule in FAST_RULES:
        if rule.category == "compound":
            continue
        if rule.category != event.type:
            continue

        cond = rule.condition

        m = _RE_REGION.search(cond)
        if m and m.group(1) not in regions:
            continue

        m = _RE_MAGNITUDE.search(cond)
        if m:
            mag = getattr(event, "magnitude", None)
            if mag is None or mag < float(m.group(1)):
                continue

        m = _RE_SEVERITY.search(cond)
        if m:
            if getattr(event, "severity", None) != m.group(1):
                continue

        m = _RE_CLUSTER.search(cond)
        if m:
            cluster_size = (event.raw_data or {}).get("clusterSize")
            if cluster_size is None or cluster_size < int(m.group(1)):
                continue

        out.append(rule)

    return out


def effective_confidence(rule: FastRule, stat: GeoRuleStat | None) -> float:
    """base_confidence + learned confidence_mod, clamped to [0, 1]."""
    mod = float(stat.confidence_mod) if stat and stat.confidence_mod is not None else 0.0
    return max(0.0, min(1.0, rule.base_confidence + mod))


def seed_rule_stats(db: Session) -> int:
    """Idempotently seed geo_rule_stats from the static FAST_RULES table.

    Inserts any missing rule_id with its base_confidence; never overwrites learned
    tuning on existing rows. Returns the number of new rows inserted.
    """
    existing = {row.rule_id for row in db.query(GeoRuleStat.rule_id).all()}
    inserted = 0
    for rule in FAST_RULES:
        if rule.id in existing:
            continue
        db.add(
            GeoRuleStat(
                rule_id=rule.id,
                category=rule.category,
                base_confidence=rule.base_confidence,
            )
        )
        inserted += 1
    if inserted:
        db.commit()
        logger.info("Seeded %d geo rule stats", inserted)
    return inserted


def dumps_rule_ids(rules: list[FastRule]) -> str:
    return json.dumps([r.id for r in rules])
