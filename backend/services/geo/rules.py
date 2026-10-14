"""Geo-economic correlation rules — Python port of WorldHawk's rules.ts.

84 fast rules + 49 geo-regions + the condition matcher.
Direction: ↑ = bullish, ↓ = bearish.

Counts, because the spec disagrees with itself: tasks/geo-rules-spec.md's headers say
"63 rules / 50 regions" but its own tables sum to 89 / 46. The tables were ported (89/46),
not the headers. The commodity-basin additions (cocoa / iron ore / lithium) take it to
93 / 49, and the India monsoon precipitation rule to 94. Treat the spec's prose counts
as historical, its tables as authoritative.

The 2026-09-20 audit found the table dishonest about reach: 61 of 94 rules pointed a
one-box physical event at an entirely global basket. Every rule now carries an explicit
``scope`` and a written ``chain``; eight whose chain could not be written to any
instrument were deleted (``vol-japan``, ``wx-heat-mediterranean``, ``wx-precip-china``,
``iceberg-shipping``, ``wx-lowpres-atlantic``, ``eq-indonesia-nickel``,
``vol-indonesia-palm``, ``gdelt-protest-southeast-asia``).

The 2026-10-04 country layer (``countries.py``) added what the hand-written table
cannot scale to: an event now carries the country its source reports, six
``TEMPLATE_RULES`` relate a damaging quake, cyclone or flood to that country's own
market and to the companies that earn only there, and ``allowed_symbols`` keeps
every path — rules, templates and both LLM calls — from relating an event to
another country's instrument. Beside a hand-written rule a template adds legs and
nothing else: it never enters the signal's confidence or risk (``scoring_rules``).

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

from .countries import (
    COUNTRIES,
    COUNTRY_ETF,
    COUNTRY_LOCALS,
    INSTRUMENT_COUNTRY,
    country_phrase,
)

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
    # Market-impact risk 1–10. 0 = inherit CATEGORY_RISK[category]. Independent of
    # confidence on purpose: importance = confidence × risk/10, and deriving risk
    # from confidence squared the same number and capped importance at 54 against
    # a notify gate of 60 (0 notifications in 1700 prod signals, 2026-09-20 audit).
    risk: int = 0
    # How far the event's *market impact* reaches — not where the trigger sits:
    # site (one port's throughput), local (a country's assets), regional (a
    # multi-country box), global (the whole curve re-prices, systemic risk-off).
    # A Hormuz closure is a 21-mile trigger with global reach; a Greek fire is
    # local however large. "" = inferred from the region box area (rule_scope).
    # A rule may only target instruments whose breadth its reach can plausibly
    # move — the 2026-09-20 audit found 61 of 94 rules pairing a one-box event
    # with an all-global basket — so claiming "global" is a claim the chain's
    # third clause must defend, and review reads it as such.
    scope: str = ""
    # (physical effect, price/flow it moves, why the instrument follows). Written
    # only where the transmission can actually be written down; a rule whose
    # chain cannot be written is the signal to drop it. Rendered as the thesis.
    chain: tuple[str, str, str] | None = None

    @property
    def thesis(self) -> str:
        return " → ".join(self.chain) if self.chain else self.direction


SCOPE_RANK = {"site": 0, "local": 1, "regional": 2, "global": 3}
# Breadth of an instrument's exposure: what fraction of its price a single
# region can plausibly move. A commodity future is the *direct* price of the
# thing a physical event disrupts, so it is narrow in the sense that matters,
# whatever the number of countries that trade it.
BREADTH_RANK = {"single_asset": 0, "commodity": 0, "national": 1, "sector": 2, "global": 3}
# Widest instrument breadth a scope may target without a penalty.
_MAX_BREADTH_FOR_SCOPE = {"site": 0, "local": 1, "regional": 2, "global": 3}
_SCOPE_PENALTY_PER_STEP = 0.10

# Per instrument. Every symbol in FAST_RULES must appear here (tested).
INSTRUMENT_BREADTH: dict[str, str] = {
    # commodity futures / ETCs: the price the event moves directly
    "CC=F": "commodity", "KC=F": "commodity", "LBR=F": "commodity", "ZC=F": "commodity",
    "HG=F": "commodity", "SB=F": "commodity", "ZS=F": "commodity", "TTF=F": "commodity",
    "USO": "commodity", "UNG": "commodity", "WEAT": "commodity",
    # single operating companies: one balance sheet, one asset base
    "PCG": "single_asset", "SQM": "single_asset", "ALB": "single_asset",
    "ZIM": "single_asset", "DAC": "single_asset", "CCJ": "single_asset",
    "ANTO.L": "single_asset",   # Antofagasta — Chilean copper pure play
    "SCCO": "single_asset",     # Southern Copper — Peru + Mexico, one company
    "FMG.AX": "single_asset",   # Fortescue — Pilbara iron ore pure play
    "IAG.MC": "single_asset", "RYA.IR": "single_asset", "ITX.MC": "single_asset",
    # single-country exposure: one country's economy can move the whole price.
    # An operating company domiciled and producing in one country belongs here
    # even when it sells worldwide (the TSM precedent), which is why Toyota is
    # national rather than global: a Japanese quake stops Japanese assembly.
    "005930.KS": "national", "TSM": "national", "TM": "national", "WY": "national",
    "TUR": "national", "EWG": "national", "EWJ": "national", "EWY": "national",
    "EWZ": "national", "FXI": "national", "INDA": "national",
    "DAL": "national", "UAL": "national", "AAL": "national",
    # US-only P&C carriers: a single national cat event is what moves them
    "ALL": "national", "TRV": "national", "HIG": "national",
    # European insurers / utility: their book and their fleet are European
    "MUV2.DE": "national", "ALV.DE": "national", "RWE.DE": "national",
    # sector ETFs and diversified sector proxies
    "ITA": "sector", "SOXX": "sector", "URA": "sector", "XLE": "sector", "DBA": "sector",
    "LMT": "sector", "RTX": "sector", "RCL": "sector", "CCL": "sector",
    "GLEN.L": "sector",  # Glencore — diversified miner + trading book
    # globally diversified
    "GLD": "global",
}

# Tradability for a Spanish retail account (TR / DEGIRO / IBKR / ING / eToro):
#   cash_eu       — buyable as a cash position
#   options_only  — US ETF without a PRIIPs KID: reachable via options at IBKR only
#   not_tradable  — no retail route (futures notionals, OTC, thin chains)
# with the nearest EU-listed alternative where one exists. Families, not
# verified ISINs: check the broker's product list before relying on one.
INSTRUMENT_TRADABILITY: dict[str, tuple[str, str]] = {
    "GLD": ("options_only", "SGLN / 4GLD (physical gold ETC)"),
    "USO": ("options_only", "CRUD (WisdomTree WTI ETC)"),
    "UNG": ("options_only", "NGAS (WisdomTree natural gas ETC)"),
    "XLE": ("options_only", "SXLE (SPDR S&P US Energy UCITS)"),
    "SOXX": ("options_only", "SMH (VanEck Semiconductor UCITS)"),
    "ITA": ("options_only", "DFNS (VanEck Defense UCITS)"),
    "FXI": ("options_only", "ICGA (iShares China Large Cap UCITS)"),
    "EWJ": ("options_only", "IJPA (iShares MSCI Japan UCITS)"),
    "EWY": ("options_only", "IKOR (iShares MSCI Korea UCITS)"),
    "EWZ": ("options_only", "IBZL (iShares MSCI Brazil UCITS)"),
    "EWG": ("options_only", "EXS1 (iShares Core DAX)"),
    "INDA": ("options_only", "NDIA (iShares MSCI India UCITS)"),
    "TUR": ("not_tradable", "IDTK (iShares MSCI Turkey UCITS)"),
    "URA": ("options_only", "U3O8 (Sprott Uranium Miners UCITS)"),
    "WEAT": ("not_tradable", "WisdomTree Wheat ETC"),
    "DBA": ("not_tradable", "WisdomTree Agriculture ETC"),
    # Futures: the right benchmark, no retail cash route at these notionals.
    "CC=F": ("not_tradable", "WisdomTree Cocoa ETC"),
    "KC=F": ("not_tradable", "WisdomTree Coffee ETC"),
    "ZC=F": ("not_tradable", "WisdomTree Corn ETC"),
    "ZS=F": ("not_tradable", "WisdomTree Soybeans ETC"),
    "SB=F": ("not_tradable", "WisdomTree Sugar ETC"),
    "HG=F": ("not_tradable", "WisdomTree Copper ETC"),
    "LBR=F": ("not_tradable", ""),
    # Dutch TTF is *the* European gas benchmark (Henry Hub is not: a European
    # cold snap or windstorm does not move US wellhead gas). It prices daily on
    # Yahoo but its 5-minute series is thin — ~36 bars in 5 days vs ~1000 for
    # NG=F — so intraday checkpoints on it will often resolve as "no data".
    "TTF=F": ("not_tradable", "NGAS (WisdomTree natural gas ETC, Henry Hub — wrong benchmark)"),
    "005930.KS": ("not_tradable", "Samsung GDR (SMSN.L)"),
    # Retired from every rule on 2026-09-21 but still on live signal rows: the
    # chip must not render them as cash-buyable. They age out with the signals.
    "JETS": ("not_tradable", "IAG.MC / RYA.IR (airlines, Madrid / Dublin)"),
    "BDRY": ("not_tradable", "GOGL.OL (Golden Ocean, Oslo)"),
    "XRT": ("not_tradable", "ITX.MC (Inditex)"),
    "SOYB": ("not_tradable", "WisdomTree Soybeans ETC"),
    "COPX": ("not_tradable", "VanEck Global Mining UCITS"),
    "REMX": ("not_tradable", "VanEck Rare Earth UCITS"),
    "LIT": ("options_only", "VOLT (WisdomTree Battery Solutions)"),
    "GDX": ("options_only", "VanEck Gold Miners UCITS"),
    # EU-listed cash names: buyable as cash at TR / DEGIRO / IBKR / ING
    **dict.fromkeys(
        ("ANTO.L", "GLEN.L", "IAG.MC", "ITX.MC", "RYA.IR", "RWE.DE", "MUV2.DE", "ALV.DE"),
        ("cash_eu", ""),
    ),
    "FMG.AX": ("not_tradable", "no EU line; ASX access is IBKR-only"),
    # US single stocks: cash at every broker
    **dict.fromkeys(
        (
            "AAL", "ALB", "ALL", "CCJ", "CCL", "DAC", "DAL", "HIG", "LMT", "PCG", "RCL",
            "RTX", "SCCO", "SQM", "TM", "TRV", "TSM", "UAL", "WY", "ZIM",
        ),
        ("cash_eu", ""),
    ),
}

# The country ETFs the country layer brought in (countries.py): national by
# construction, with the route measured there. The seven that were already rule
# legs keep the entries written above.
for _c in COUNTRIES:
    if _c.etf:
        INSTRUMENT_BREADTH.setdefault(_c.etf, "national")
        INSTRUMENT_TRADABILITY.setdefault(_c.etf, (_c.route, _c.alternate))
# The local companies: one country's economy moves the whole price (the TSM
# precedent), and a US-listed single stock is cash at every broker.
for _symbols in COUNTRY_LOCALS.values():
    for _symbol in _symbols:
        INSTRUMENT_BREADTH.setdefault(_symbol, "national")
        INSTRUMENT_TRADABILITY.setdefault(_symbol, ("cash_eu", ""))
_COUNTRY_ETFS = frozenset(COUNTRY_ETF.values())


def instrument_tier(symbol: str) -> str:
    """Where an instrument sits between the event and the world.

    local — a company bound to one country · national — that country's market ·
    international — a commodity, a sector, anything no single country owns.
    Derived from the country table, so a symbol is never tagged by hand twice.
    """
    if symbol in _COUNTRY_ETFS:
        return "national"
    return "local" if symbol in INSTRUMENT_COUNTRY else "international"


# Base market-impact risk per event category (1 = noise, 10 = systemic). This is
# "how much can this kind of event move a price", not "how sure are we" — that is
# base_confidence. A specific rule overrides it with FastRule.risk.
CATEGORY_RISK: dict[str, int] = {
    "nuclear": 10,
    "conflict": 8,
    "military_escalation": 8,
    "maritime_disruption": 8,
    # 6, not 8: "≥2 events touching an energy ticker" is a weak bar (a Texas heat
    # wave plus any Gulf storm), the id rotates daily, and at 8 all three compound
    # rules page every day. Raise it once the tally has earned that.
    "compound": 6,
    "armed_conflict": 7,
    "geopolitical_escalation": 7,
    "sanctions": 7,
    "maritime_rerouting": 7,
    "airspace_closure": 6,
    "military_surge": 6,
    "trade_dispute": 6,
    "earthquake": 6,
    "cyclone": 6,
    "drought": 5,
    "extreme_cold": 5,
    "maritime_congestion": 5,
    "mass_protest": 4,
    "volcano": 4,
    "storm": 4,
    "severe_storm": 4,
    "flood": 4,
    "fire": 4,
    "extreme_heat": 4,
    "deep_cyclone": 4,
    "diplomatic_cooperation": 3,
    "heavy_precipitation": 3,
    "iceberg": 2,
}
_DEFAULT_RISK = 5
_MAX_HEADROOM = 2


def base_risk(rule: FastRule) -> int:
    return rule.risk or CATEGORY_RISK.get(rule.category, _DEFAULT_RISK)


def severity_headroom(rule: FastRule, event) -> int:
    """0..2 — how far the event exceeds the rule's own trigger floor.

    A rule fires at its floor; the floor is the weakest event it accepts. Headroom
    is what separates an M8.5 from the M6.0 that trips the same rule.
    """
    cond = rule.condition
    m = _RE_MAGNITUDE.search(cond)
    mag = getattr(event, "magnitude", None)
    if m and mag is not None:
        return max(0, min(_MAX_HEADROOM, int((mag - float(m.group(1))) / 0.7)))
    m = _RE_CLUSTER.search(cond)
    size = (getattr(event, "raw_data", None) or {}).get("clusterSize")
    if m and size:
        ratio = size / int(m.group(1))
        return 2 if ratio >= 4 else 1 if ratio >= 2 else 0
    if getattr(event, "severity", None) == "red" and not _RE_SEVERITY.search(cond):
        return 1
    return 0


# Categories whose market impact is amplified by a risk-off regime: when the VIX,
# the curve, financial stress and credit spreads already say "fragile", the same
# chokepoint or conflict event moves more. Physical/agricultural events are not
# regime-sensitive in this sense (a drought is a drought). Compound is excluded
# on purpose: its risk is held at 6 so "≥2 events touching an energy ticker"
# stays off the phone, and +1 in risk_off would page it every day.
_REGIME_SENSITIVE = frozenset({
    "conflict", "armed_conflict", "military_escalation", "military_surge",
    "geopolitical_escalation", "sanctions", "trade_dispute", "maritime_disruption",
    "maritime_rerouting", "maritime_congestion", "airspace_closure", "nuclear",
})


def regime_headroom(rules: list[FastRule], regime: str | None) -> int:
    """+1 risk for a regime-sensitive rule in a risk-off macro regime (FRED)."""
    if regime != "risk_off":
        return 0
    return 1 if any(r.category in _REGIME_SENSITIVE for r in rules) else 0


def compute_risk(
    rules: list[FastRule], event, llm_risk: int | None, regime: str | None = None
) -> int:
    """Risk 1–10 for a signal: rule base risk + severity headroom (+ regime), LLM overrides.

    Decision 2026-09-20 (memories/decisions/finview.md): "a mix with the LLM
    allowed to override":
      - no rules and no LLM → _DEFAULT_RISK
      - rules → max base_risk (the riskiest matched thesis, not the mean — the
        mean would let a low-risk co-match dilute a Hormuz signal) + max headroom
      - a numeric LLM riskScore replaces the whole thing; a non-numeric one
        ("alto", "7/10", {}) is logged and ignored — the field comes straight
        out of json.loads and a bad value must cost one override, not the cycle
    """
    if llm_risk is not None:
        try:
            return max(1, min(10, int(llm_risk)))
        except (TypeError, ValueError):
            logger.warning("geo: ignoring non-numeric LLM riskScore %r", llm_risk)
    if not rules:
        return _DEFAULT_RISK
    risk = (
        max(base_risk(r) for r in rules)
        + max(severity_headroom(r, event) for r in rules)
        + regime_headroom(rules, regime)
    )
    return max(1, min(10, risk))


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
    "drc_mining": (-13, 2, 22, 32),  # Kivu tin/tantalum + Katanga copper-cobalt (Kolwezi -10.7)
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


# ── 84 fast rules ────────────────────────────────────────────────────
# Every rule carries an explicit ``scope`` and a written ``chain``:
# (physical effect, the price or flow it moves, why this instrument follows).
# A leg with no writable third clause is not in the basket.
FAST_RULES: tuple[FastRule, ...] = (
    # ── Earthquakes ──────────────────────────────────────────────────
    FastRule(
        "eq-chile-copper", "earthquake", "earthquake.magnitude>=6 && region=chile_mining",
        "Major Chilean earthquake disrupts copper supply", _t("HG=F+ ANTO.L-"),
        "Copper supply disruption → exchange copper up, the Chilean producer down", 0.82,
        scope="local",
        chain=(
            "an M6+ quake halts Atacama shafts, concentrators and the loading ports",
            "seaborne concentrate supply tightens and exchange copper is bid",
            "Antofagasta's mines are all Chilean, so the lost tonnes are its own output",
        ),
    ),
    FastRule(
        "eq-japan-industrial", "earthquake", "earthquake.magnitude>=6.5 && region=japan",
        "Major Japanese earthquake hits industrial base", _t("EWJ- TM-"),
        "Japanese industrial disruption → domestic equities and carmakers down", 0.75,
        scope="regional",
        chain=(
            "an M6.5+ quake halts assembly lines, rail and power across a Japanese prefecture",
            "domestic output and earnings for the quarter are cut and rebuild costs land",
            "Toyota assembles in Japan and the country index is the disruption itself",
        ),
    ),
    FastRule(
        "eq-taiwan-semi", "earthquake", "earthquake.magnitude>=6 && region=taiwan",
        "Taiwan earthquake threatens semiconductor production", _t("TSM- 005930.KS+"),
        "Fab downtime → TSMC loses wafers, the only substitute foundry gains", 0.78,
        scope="local",
        chain=(
            "an M6+ quake trips Hsinchu and Tainan fabs and scraps the wafers in process",
            "leading-edge foundry capacity is short for a quarter and spot pricing firms",
            "the affected fabs are one company's, and Samsung Foundry is the near-term substitute",
        ),
    ),
    FastRule(
        "eq-turkey", "earthquake", "earthquake.magnitude>=6.5 && region=turkey",
        "Major Turkish earthquake", _t("TUR-"),
        "Reconstruction cost and lost output are carried by Turkish assets", 0.70,
        scope="local",
        chain=(
            "an M6.5+ quake destroys housing and industry across several Turkish provinces",
            "the fiscal cost, the lira and lost regional output all move against Turkish assets",
            "the country index is the direct claim on that economy",
        ),
    ),
    FastRule(
        "eq-peru-copper", "earthquake", "earthquake.magnitude>=6 && region=peru_mining",
        "Peruvian earthquake disrupts copper supply", _t("HG=F+ SCCO-"),
        "Copper supply disruption → exchange copper up, the Peruvian producer down", 0.76,
        scope="local",
        chain=(
            "an M6+ quake halts southern Peruvian pits, concentrators and the coastal ports",
            "seaborne concentrate supply tightens and exchange copper is bid",
            "Toquepala and Cuajone are roughly half of Southern Copper's book",
        ),
    ),
    FastRule(
        "eq-lithium-triangle", "earthquake", "earthquake.magnitude>=6 && region=lithium_triangle",
        "Atacama/Puna earthquake disrupts lithium brine operations", _t("SQM- ALB-"),
        "Brine pond and port damage cuts both Atacama producers' output", 0.74,
        scope="local",
        chain=(
            "an M6+ quake breaches evaporation ponds and cuts the road and port link to Antofagasta",
            "months of brine inventory in the ponds is lost and shipments stop",
            "both listed producers pump the same salar, so the outage is shared",
        ),
    ),
    # ── Cyclones / hurricanes ────────────────────────────────────────
    FastRule(
        "cyc-gulf-oil", "cyclone", "region=gulf_of_mexico",
        "Hurricane threatens Gulf of Mexico oil/gas", _t("USO+ UNG+ XLE+"),
        "Gulf production shut-ins → crude, gas and US energy equity up", 0.85,
        scope="regional",
        chain=(
            "a hurricane track forces evacuation and shut-in of offshore platforms and coastal refineries",
            "US crude and gas supply drops for days to weeks while demand is unchanged",
            "the US energy sector's production and refining base sits in that box",
        ),
    ),
    FastRule(
        "cyc-florida-insurance", "cyclone", "region=florida",
        "Hurricane hits Florida", _t("ALL- TRV- HIG-"),
        "Insured cat losses land on US personal and commercial lines", 0.80,
        scope="local",
        chain=(
            "a landfalling hurricane destroys Florida housing and commercial property",
            "insured losses run to tens of billions and reserve strengthening follows",
            "these are US-only P&C carriers whose Florida book pays the claims",
        ),
    ),
    FastRule(
        "cyc-caribbean-tourism", "cyclone", "region=caribbean",
        "Hurricane disrupts Caribbean tourism", _t("DAL- RCL- CCL-"),
        "Itineraries and routes cancelled in peak season", 0.72,
        scope="regional",
        chain=(
            "a hurricane closes Caribbean airports, ports and resorts for days",
            "bookings are cancelled and refunded and capacity is redeployed at a loss",
            "Caribbean itineraries and routes are a large share of these carriers' season",
        ),
    ),
    FastRule(
        "cyc-southeast-asia", "cyclone", "region=southeast_asia",
        "Cyclone hits Southeast Asia", _t("KC=F+"),
        "Typhoon damage in the Vietnamese coffee belt lifts robusta", 0.65,
        scope="regional",
        chain=(
            "a landfalling typhoon strips cherries and floods the Central Highlands plantations",
            "the world's largest robusta crop is cut and export parity rises",
            "the coffee contract is the price of exactly that crop",
        ),
    ),
    FastRule(
        "cyc-india-agriculture", "cyclone", "region=india_coast",
        "Cyclone hits Indian coast agriculture", _t("SB=F+ INDA-"),
        "Coastal crop and port damage → sugar up, Indian equities down", 0.68,
        scope="regional",
        chain=(
            "a Bay of Bengal or Arabian Sea cyclone floods coastal cane and closes the export ports",
            "India is the second largest sugar exporter, so a lost crop tightens world supply",
            "the sugar contract prices that supply and the country index carries the damage",
        ),
    ),
    FastRule(
        "cyc-australia-ironore", "cyclone", "region=australia_pilbara",
        "Cyclone shuts in Pilbara iron-ore export ports", _t("FMG.AX-"),
        "Port Hedland shut-in costs the pure-play exporter its shipments", 0.80,
        scope="site",
        chain=(
            "a tropical cyclone closes Port Hedland and Dampier and stops the rail from the mines",
            "several days of export tonnage is deferred out of the quarter",
            "Fortescue ships only Pilbara ore through those two ports",
        ),
    ),
    # ── Wildfires ────────────────────────────────────────────────────
    FastRule(
        "fire-california", "fire", "fire.cluster>=50 && region=california",
        "Major California wildfires", _t("ALL- TRV- PCG-"),
        "Insured losses plus utility ignition liability", 0.78,
        scope="local",
        chain=(
            "a 50+ hotspot cluster burns through the wildland-urban interface",
            "insured property losses and inverse-condemnation liability for the igniting utility",
            "these carriers write the California homeowner book and PG&E owns the lines",
        ),
    ),
    FastRule(
        "fire-canada-lumber", "fire", "fire.cluster>=30 && region=canada_forest",
        "Canadian wildfires disrupt lumber", _t("LBR=F+ WY+"),
        "Harvest and mill shutdowns tighten the lumber benchmark", 0.74,
        scope="regional",
        chain=(
            "fires and evacuation orders stop harvesting and close sawmills across BC and Alberta",
            "the marginal supply of construction lumber into North America is cut",
            "the futures contract is that price and Weyerhaeuser's US timber re-prices with it",
        ),
    ),
    FastRule(
        "fire-amazon", "fire", "fire.cluster>=100 && region=amazon",
        "Major Amazon fires", _t("ZS=F+ EWZ-"),
        "Crop loss at the frontier plus the sanctions and financing overhang", 0.65,
        scope="regional",
        chain=(
            "a 100+ hotspot cluster burns the Mato Grosso and Pará crop frontier",
            "soybean supply from the world's largest exporter is questioned and trade sanction risk returns",
            "the soybean contract prices that supply and the country index carries the policy risk",
        ),
    ),
    FastRule(
        "fire-australia-mining", "fire", "fire.cluster>=30 && region=australia_pilbara",
        "Pilbara fires disrupt iron-ore haulage", _t("FMG.AX-"),
        "Spinifex fire across the rail corridor stops the mine-to-port link", 0.60,
        scope="site",
        chain=(
            "a 30+ hotspot cluster crosses the Pilbara rail corridor and mine access roads",
            "haulage to Port Hedland stops and shipments slip out of the quarter",
            "Fortescue's whole operation is that one corridor",
        ),
    ),
    FastRule(
        "fire-greece-tourism", "fire", "fire.cluster>=20 && region=mediterranean",
        "Mediterranean fires disrupt tourism", _t("IAG.MC- RYA.IR-"),
        "Evacuations and cancellations hit the southern-Europe leisure season", 0.55,
        scope="regional",
        chain=(
            "a 20+ hotspot cluster forces resort evacuations and repatriation flights mid-season",
            "forward leisure bookings and fares into southern Europe fall for the rest of the summer",
            "these two carriers' short-haul networks are concentrated on exactly those routes",
        ),
    ),
    # ── Volcanoes ────────────────────────────────────────────────────
    FastRule(
        "vol-iceland-aviation", "volcano", "region=iceland",
        "Icelandic volcano disrupts aviation", _t("IAG.MC- RYA.IR- DAL- UAL- AAL-"),
        "Ash cloud closes North Atlantic and European airspace", 0.83,
        scope="local",
        chain=(
            "an ash plume drifts into the North Atlantic tracks and the European upper airspace",
            "regulators close corridors and thousands of rotations are cancelled and re-accommodated",
            "these are the carriers that fly the transatlantic and intra-European networks affected",
        ),
    ),
    # ── Floods ───────────────────────────────────────────────────────
    FastRule(
        "flood-china-industry", "flood", "region=china_industrial",
        "Flooding hits Chinese industrial base", _t("FXI- DBA+"),
        "Industrial shutdown plus a domestic crop loss that pulls in imports", 0.72,
        scope="regional",
        chain=(
            "Yangtze-basin flooding shuts factories, rail and inland ports and drowns the crop",
            "domestic output is lost and China replaces the lost grain on the world market",
            "the country index is the disruption; the ag basket is the import bid",
        ),
    ),
    FastRule(
        "flood-bangladesh-textile", "flood", "region=bangladesh",
        "Flooding hits Bangladesh textiles", _t("ITX.MC-"),
        "Garment factory and port shutdown lands in the buyer's margin", 0.58,
        scope="local",
        chain=(
            "monsoon flooding closes Dhaka and Chattogram garment factories and the port",
            "lead times stretch and air freight replaces sea freight on the season's orders",
            "Inditex sources a large share of its volume from exactly those factories",
        ),
    ),
    FastRule(
        "flood-midwest-grain", "flood", "region=us_midwest",
        "Flooding hits US Midwest grain", _t("ZC=F+ WEAT+"),
        "Prevented plantings and drowned acres cut the crop", 0.80,
        scope="regional",
        chain=(
            "flooding drowns planted acres and blocks barge movement on the Mississippi system",
            "the US corn and wheat balance sheet tightens and basis widens",
            "these contracts are the price of that crop",
        ),
    ),
    FastRule(
        "flood-germany-rhine", "flood", "region=germany_rhine",
        "Rhine flooding disrupts logistics", _t("EWG- TTF=F+"),
        "Barge traffic stops, and the fuel that moves by barge is replaced by gas", 0.65,
        scope="local",
        chain=(
            "high water closes the Rhine to barges and floods riverside industrial sites",
            "coal and chemical feedstock stop moving and German plants burn more gas to cover",
            "the German index is the industrial damage and TTF is the European gas price",
        ),
    ),
    FastRule(
        "flood-westafrica-cocoa", "flood", "region=west_africa_cocoa",
        "West African flooding drives black-pod disease in cocoa", _t("CC=F+"),
        "Excess rain → black-pod harvest loss → cocoa bid", 0.62,
        scope="local",
        chain=(
            "sustained flooding in Ivorian and Ghanaian groves spreads black-pod rot through the main crop",
            "arrivals at the ports fall short of the forecast and the world balance tightens",
            "the cocoa contract is the price of that crop",
        ),
    ),
    # ── Conflicts / geopolitical (alert-zone driven, category conflict) ──
    FastRule(
        "conflict-mideast-oil", "conflict", "alert.severity=red && region=middle_east_oil",
        "Middle East oil conflict", _t("USO+ XLE+ LMT+ RTX+ ITA+ GLD+"),
        "Oil supply risk, defense demand, systemic risk-off", 0.88,
        scope="global",
        chain=(
            "a red-severity conflict puts Gulf production, refining and export terminals at risk",
            "a war premium is priced into crude, defense order books re-rate and reserve demand moves into gold",
            "energy carries the barrel, the primes carry the orders, and bullion is the systemic hedge",
        ),
    ),
    FastRule(
        "conflict-hormuz-strait", "conflict", "region=strait_of_hormuz",
        "Strait of Hormuz tension", _t("USO+ GLD+"),
        "A fifth of seaborne crude transits one 21-mile channel", 0.90,
        scope="global",
        chain=(
            "military action in the strait threatens the transit of roughly a fifth of seaborne crude",
            "there is no alternative route at that volume, so the whole crude curve re-prices and risk assets de-rate",
            "crude is the disrupted good and gold is the reserve asset bid in a systemic supply shock",
        ),
    ),
    FastRule(
        "conflict-ukraine-grain", "conflict", "region=ukraine_black_sea",
        "Ukraine/Black Sea conflict", _t("WEAT+ ZC=F+"),
        "Black Sea export corridor risk on a top-five grain origin", 0.82,
        scope="local",
        chain=(
            "fighting closes Odesa and the Black Sea corridor and leaves the crop unharvested",
            "a top-five wheat and corn origin is removed from the export balance",
            "these contracts are the price of the grain that no longer ships",
        ),
    ),
    FastRule(
        "conflict-south-china-sea", "conflict", "region=south_china_sea",
        "South China Sea tension", _t("FXI- TSM- LMT+ GLD+"),
        "Regional escalation risk, defense demand, systemic risk-off", 0.75,
        scope="global",
        chain=(
            "armed incident in the sea lane that carries a third of world trade and the Taiwan approaches",
            "a conflict premium is priced into the regional equity risk and into defense order books",
            "Chinese and Taiwanese assets are the exposure, and gold is the hedge against a great-power tail",
        ),
    ),
    FastRule(
        "conflict-korea", "conflict", "alert.severity=red && region=korean_peninsula",
        "Korean Peninsula conflict", _t("EWY- GLD+"),
        "Seoul is inside artillery range; a red alert is a systemic tail", 0.72,
        scope="global",
        chain=(
            "a red-severity incident on the DMZ puts Seoul's industrial belt at direct risk",
            "Korean assets carry a war discount and reserve demand moves into gold",
            "the country index is the exposure and bullion is the tail hedge",
        ),
    ),
    FastRule(
        "conflict-suez", "conflict", "region=suez_red_sea",
        "Suez/Red Sea disruption", _t("USO+ ZIM+ DAC+"),
        "Chokepoint closure reroutes Asia-Europe trade around Africa", 0.80,
        scope="site",
        chain=(
            "attacks in the Red Sea close the Suez approach to commercial traffic",
            "Asia-Europe voyages add ten days around the Cape, absorbing capacity and lifting freight rates",
            "the liner earns the spot rate and the lessor re-charters into it; crude carries the transit risk",
        ),
    ),
    FastRule(
        "conflict-iran-nuclear", "conflict", "alert.severity=red && region=iran",
        "Iran nuclear/military escalation", _t("USO+ GLD+ LMT+ ITA+"),
        "Oil supply risk, defense demand, systemic risk-off", 0.84,
        scope="global",
        chain=(
            "a red-severity escalation puts Iranian exports and the Gulf shipping lane at risk",
            "crude prices a war premium, defense procurement accelerates and reserve demand moves into gold",
            "crude is the disrupted good, the defense names take the orders, bullion is the systemic hedge",
        ),
    ),
    # ── Maritime (mixed) ─────────────────────────────────────────────
    FastRule(
        "maritime-panama-drought", "drought", "region=panama_canal",
        "Panama Canal drought restricts transit", _t("ZIM+ DAC+"),
        "Draft and slot restrictions remove effective container capacity", 0.75,
        scope="site",
        chain=(
            "low water in Gatún Lake cuts daily transit slots and the maximum draft",
            "ships wait, reroute or sail light, and effective container capacity on the route falls",
            "the liner earns the higher spot rate and the lessor re-charters tonnage into it",
        ),
    ),
    FastRule(
        "maritime-malacca-tension", "conflict", "region=malacca_strait",
        "Malacca Strait tension", _t("USO+ ZIM+ DAC+"),
        "The alternative straits cost days of steaming", 0.78,
        scope="site",
        chain=(
            "tension in the strait pushes traffic onto the Lombok and Sunda routes",
            "voyage days and war-risk premia rise on every Gulf-to-Asia crude and container sailing",
            "crude carries the transit risk and the box carriers earn the tighter effective capacity",
        ),
    ),
    # ── AIS-derived maritime ─────────────────────────────────────────
    FastRule(
        "ais-tanker-drop-hormuz", "maritime_disruption", "region=strait_of_hormuz",
        "Tanker traffic drop at Hormuz", _t("USO+ GLD+"),
        "Observed transits falling is the chokepoint closing in real time", 0.85,
        scope="global",
        chain=(
            "tanker transits through the strait fall below their normal daily count",
            "Gulf loadings are not reaching the market and the crude curve backwardates",
            "crude is the cargo that stopped moving and gold is the reserve bid in a supply shock",
        ),
    ),
    FastRule(
        "ais-tanker-drop-suez", "maritime_disruption", "region=suez_red_sea",
        "Tanker traffic drop at Suez", _t("USO+ ZIM+ DAC+"),
        "Observed transits falling means the reroute has begun", 0.82,
        scope="site",
        chain=(
            "tanker and box transits through the Suez approach fall below normal",
            "cargo is routing around the Cape, adding voyage days and lifting freight rates",
            "crude carries the delivery risk, the liner and the lessor earn the rate",
        ),
    ),
    FastRule(
        "ais-reroute-cape", "maritime_rerouting", "region=cape_good_hope",
        "Shipping reroutes via Cape of Good Hope", _t("USO+ ZIM+ DAC+"),
        "Traffic appearing at the Cape is absorbed capacity elsewhere", 0.80,
        scope="site",
        chain=(
            "vessel counts round the Cape rise above their baseline",
            "the same cargo now takes ten more days, so effective fleet capacity shrinks and rates rise",
            "the liner earns the spot rate, the lessor re-charters into it, bunker demand supports crude",
        ),
    ),
    FastRule(
        "ais-cargo-drop-malacca", "maritime_disruption", "region=malacca_strait",
        "Cargo traffic drop at Malacca", _t("ZIM+ DAC+"),
        "Traffic leaving the strait is capacity leaving the market", 0.80,
        scope="site",
        chain=(
            "box traffic through the strait falls below its normal daily count",
            "cargo diverts to longer routes and effective container capacity on Asia-Europe falls",
            "the liner earns the spot rate and the lessor re-charters tonnage into it",
        ),
    ),
    FastRule(
        "ais-congestion-suez", "maritime_congestion", "region=suez_red_sea",
        "Congestion at Suez", _t("ZIM+ DAC+"),
        "Ships queuing are ships not carrying the next cargo", 0.72,
        scope="site",
        chain=(
            "vessels accumulate at anchor at the canal approaches instead of transiting",
            "waiting days remove effective capacity from the Asia-Europe rotation and spot rates firm",
            "the liner earns the rate and the lessor re-charters idle tonnage into it",
        ),
    ),
    FastRule(
        "ais-cargo-drop-panama", "maritime_disruption", "region=panama_canal",
        "Cargo traffic drop at Panama", _t("ZIM+ DAC+"),
        "Fewer transits is less effective capacity on the Asia-US East Coast leg", 0.75,
        scope="site",
        chain=(
            "daily transits through the canal fall below their normal count",
            "Asia-to-US-East-Coast boxes route via Suez or rail, adding days and lifting rates",
            "the liner earns the spot rate and the lessor re-charters tonnage into it",
        ),
    ),
    # ── Storms ───────────────────────────────────────────────────────
    FastRule(
        "storm-us-winter", "storm", "region=us_northeast",
        "Winter storm hits US Northeast", _t("UNG+ DAL-"),
        "Heating load spikes, hub operations stop", 0.73,
        scope="local",
        chain=(
            "a winter storm drives heating degree days through the Northeast and closes the airports",
            "residential and commercial gas burn jumps while flights are cancelled outright",
            "Henry Hub is the price of that burn and the hub carrier eats the cancellations",
        ),
    ),
    FastRule(
        "storm-texas-freeze", "storm", "region=texas",
        "Texas freeze event", _t("UNG+ USO+"),
        "Wellhead freeze-offs cut supply while load peaks", 0.80,
        scope="local",
        chain=(
            "a hard freeze ices Permian wellheads and gathering lines while ERCOT load peaks",
            "gas and crude production is shut in at the moment demand is highest",
            "both benchmarks are the price of the barrels and mcf that stop flowing",
        ),
    ),
    FastRule(
        "storm-europe-energy", "storm", "region=northern_europe",
        "European windstorm hits energy", _t("TTF=F+ RWE.DE+"),
        "Above cut-out speed wind farms stop, and thermal plant covers the gap", 0.62,
        scope="regional",
        chain=(
            "a severe windstorm pushes turbines past cut-out speed and brings transmission lines down",
            "wind generation drops out unplanned and gas-fired plant is dispatched to cover it",
            "TTF is the European gas benchmark and RWE's thermal fleet captures the wider spread",
        ),
    ),
    # ── Drought / agriculture ────────────────────────────────────────
    FastRule(
        "drought-us-breadbasket", "drought", "region=us_great_plains",
        "US Great Plains drought", _t("WEAT+ ZC=F+"),
        "Yield loss in the hard red winter wheat belt", 0.82,
        scope="regional",
        chain=(
            "drought through the growing season cuts yields and raises abandonment in the Plains",
            "the US wheat and corn balance sheet tightens and export supply shrinks",
            "these contracts are the price of that crop",
        ),
    ),
    FastRule(
        "drought-brazil-coffee", "drought", "region=brazil_southeast",
        "Brazil drought hits coffee/soy", _t("KC=F+ ZS=F+ EWZ-"),
        "Flowering and pod fill fail in the world's largest origin", 0.78,
        scope="local",
        chain=(
            "drought during flowering and pod fill cuts yields across Minas Gerais and São Paulo",
            "the world's largest arabica and soybean origin ships less for two seasons",
            "these contracts price that crop and agribusiness is a large part of the Brazilian index",
        ),
    ),
    FastRule(
        "drought-india-monsoon", "drought", "region=india",
        "Indian monsoon failure", _t("SB=F+ INDA-"),
        "A failed monsoon cuts the cane crop and triggers export curbs", 0.70,
        scope="regional",
        chain=(
            "a deficient monsoon cuts cane and kharif yields across the main growing states",
            "India, the second largest sugar exporter, curbs exports and world supply tightens",
            "the sugar contract prices that supply and the country index carries the rural demand hit",
        ),
    ),
    FastRule(
        "drought-westafrica-cocoa", "drought", "region=west_africa_cocoa",
        "Ivory Coast/Ghana drought hits cocoa supply", _t("CC=F+"),
        "~60% of world cocoa comes out of this one box", 0.78,
        scope="local",
        chain=(
            "harmattan drought desiccates pods across the Ivorian and Ghanaian belt",
            "roughly 60% of world cocoa origin ships short and the balance goes into deficit",
            "the cocoa contract is the price of that crop",
        ),
    ),
    # ── Nuclear / infra (declared but dormant — see module docstring) ──
    FastRule(
        "nuclear-incident", "nuclear", "earthquake.magnitude>=5 && near_nuclear_plant",
        "Nuclear plant incident", _t("URA- CCJ-"),
        "A release event stops new build and reactor restarts worldwide", 0.70,
        scope="global",
        chain=(
            "seismic damage at a reactor site forces shutdown and a release investigation",
            "regulators pause restarts and new build worldwide and utility uranium demand is cut",
            "the miners sell into exactly that demand — Fukushima repriced the whole fuel cycle",
        ),
    ),
    # ── Extreme weather — Windy ──────────────────────────────────────
    FastRule(
        "wx-heat-texas", "extreme_heat", "region=texas",
        "Extreme heat in Texas", _t("UNG+"),
        "Record ERCOT cooling load is burned as gas", 0.78,
        scope="local",
        chain=(
            "a heat dome drives ERCOT cooling load to records for days on end",
            "gas-fired generation runs flat out and storage withdrawals run ahead of the seasonal norm",
            "Henry Hub is the price of exactly that burn",
        ),
    ),
    FastRule(
        "wx-heat-india", "extreme_heat", "region=india",
        "Extreme heat in India", _t("WEAT+ SB=F+ INDA-"),
        "Terminal heat stress shrivels grain and triggers export bans", 0.72,
        scope="regional",
        chain=(
            "a heat wave during grain fill shrivels the wheat crop and stresses standing cane",
            "India restricts wheat and sugar exports, removing supply from the world balance",
            "these contracts price that supply and the country index carries the power and rural shock",
        ),
    ),
    FastRule(
        "wx-cold-us-northeast", "extreme_cold", "region=us_northeast",
        "Extreme cold in US Northeast", _t("UNG+ DAL-"),
        "Heating load spikes into a constrained pipeline network", 0.80,
        scope="local",
        chain=(
            "an arctic outbreak drives heating demand across the Northeast and de-ices the airports",
            "gas burn spikes against a pipeline-constrained region and flights are cancelled",
            "Henry Hub is the price of that burn and the hub carrier eats the cancellations",
        ),
    ),
    FastRule(
        "wx-cold-northern-europe", "extreme_cold", "region=northern_europe",
        "Extreme cold in Northern Europe", _t("TTF=F+ EWG-"),
        "Cold snap pulls European storage down faster than the norm", 0.75,
        scope="regional",
        chain=(
            "an extended cold spell raises heating demand across northwest Europe",
            "storage withdrawals run ahead of schedule and the European gas curve firms",
            "TTF is that price, and German industry pays it as an input cost",
        ),
    ),
    FastRule(
        "wx-storm-gulf", "severe_storm", "region=gulf_of_mexico",
        "Severe storm in Gulf of Mexico", _t("USO+ XLE+"),
        "Offshore evacuation and refinery shutdown", 0.82,
        scope="regional",
        chain=(
            "a severe storm forces offshore evacuation and precautionary refinery shutdown on the coast",
            "crude and product supply is interrupted for days",
            "the barrel is the disrupted good and the US energy sector's plant is in that box",
        ),
    ),
    FastRule(
        "wx-storm-northern-europe", "severe_storm", "region=northern_europe",
        "Severe storm in Northern Europe", _t("MUV2.DE- ALV.DE-"),
        "European windstorm is a named cat peril on European books", 0.68,
        scope="regional",
        chain=(
            "a named windstorm crosses northwest Europe and damages roofs, vehicles and grid",
            "insured losses run into the billions and hit the retained layers first",
            "European windstorm is one of the core cat perils these two underwrite",
        ),
    ),
    FastRule(
        "wx-precip-us-midwest", "heavy_precipitation", "region=us_midwest",
        "Heavy precipitation in US Midwest", _t("ZC=F+ WEAT+"),
        "Waterlogged fields delay planting and rot standing crop", 0.77,
        scope="regional",
        chain=(
            "prolonged heavy rain waterlogs the Corn Belt inside the planting or harvest window",
            "acres go unplanted or the standing crop degrades and the balance sheet tightens",
            "these contracts are the price of that crop",
        ),
    ),
    FastRule(
        "wx-precip-india", "heavy_precipitation", "region=india",
        "Heavy precipitation in India (monsoon)", _t("SB=F+ INDA-"),
        "Excess monsoon rain lodges cane and blocks the crushing season", 0.70,
        scope="regional",
        chain=(
            "sustained monsoon excess floods the cane belt and lodges the standing crop",
            "recoverable sugar per tonne falls and India's exportable surplus shrinks",
            "the sugar contract prices that supply and the country index carries the logistics hit",
        ),
    ),
    # ── Flight anomalies — OpenSky / adsb.lol ────────────────────────
    FastRule(
        "air-closure-mideast", "airspace_closure", "region=middle_east_oil",
        "Airspace closure over Middle East", _t("USO+ LMT+ GLD+"),
        "Civil traffic clearing a corridor is the leading indicator of strikes", 0.85,
        scope="global",
        chain=(
            "civil traffic vacates a Gulf corridor, which precedes or accompanies military action",
            "a war premium is priced into crude and defense procurement expectations rise",
            "crude is the good at risk, the prime takes the orders, bullion is the systemic hedge",
        ),
    ),
    FastRule(
        "air-closure-ukraine", "airspace_closure", "region=ukraine_black_sea",
        "Airspace closure over Ukraine", _t("WEAT+ ZC=F+ TTF=F+"),
        "Escalation over the corridor that carries the grain and the gas", 0.82,
        scope="local",
        chain=(
            "airspace over the Black Sea corridor closes, marking a step up in the fighting",
            "grain export insurance and transit risk rise and European gas transit is questioned again",
            "these contracts price the grain that stops shipping and the gas that stops flowing",
        ),
    ),
    FastRule(
        "air-closure-taiwan", "airspace_closure", "region=taiwan",
        "Airspace closure over Taiwan", _t("TSM- FXI- GLD+"),
        "A closed Taiwan corridor is the systemic tail scenario", 0.88,
        scope="global",
        chain=(
            "civil aviation vacates the Taiwan approaches, which only happens around live exercises or worse",
            "leading-edge foundry supply and cross-strait trade are put in question at once",
            "the foundry and the mainland index are the exposure, and gold is the tail hedge",
        ),
    ),
    FastRule(
        "air-closure-korea", "airspace_closure", "region=korean_peninsula",
        "Airspace closure over Korea", _t("EWY- GLD+"),
        "A closed corridor over the DMZ is a systemic tail", 0.80,
        scope="global",
        chain=(
            "civil traffic vacates the peninsula corridor around a military event",
            "Korean assets carry a war discount and reserve demand moves into gold",
            "the country index is the exposure and bullion is the tail hedge",
        ),
    ),
    FastRule(
        "air-closure-iran", "airspace_closure", "region=iran",
        "Airspace closure over Iran", _t("USO+ LMT+ GLD+"),
        "Corridor closure over an OPEC producer precedes strikes", 0.86,
        scope="global",
        chain=(
            "civil traffic clears Iranian airspace, which precedes or accompanies military action",
            "Iranian export continuity is questioned, crude prices a premium, procurement accelerates",
            "crude is the good at risk, the prime takes the orders, bullion is the systemic hedge",
        ),
    ),
    FastRule(
        "air-military-mideast", "military_surge", "region=middle_east_oil",
        "Military flight surge in Middle East", _t("USO+ LMT+ GLD+"),
        "Tanker and transport surge is the buildup made visible", 0.83,
        scope="global",
        chain=(
            "military transport and tanker movements over the Gulf rise well above baseline",
            "the market prices a higher probability of strikes on production and export infrastructure",
            "crude is the good at risk, the prime takes the orders, bullion is the systemic hedge",
        ),
    ),
    FastRule(
        "air-military-europe", "military_surge", "region=northern_europe",
        "Military flight surge in Europe", _t("LMT+ ITA+"),
        "A visible NATO surge pulls procurement forward", 0.70,
        scope="regional",
        chain=(
            "military air activity over northern Europe rises well above its baseline",
            "NATO members bring munitions and air-defence procurement forward",
            "these are the order books that replenishment lands in",
        ),
    ),
    FastRule(
        "air-military-scs", "military_surge", "region=south_china_sea",
        "Military flight surge in South China Sea", _t("FXI- LMT+ TSM- GLD+"),
        "A surge over the sea lane raises the great-power tail", 0.75,
        scope="global",
        chain=(
            "military air activity over the sea lane and the Taiwan approaches rises above baseline",
            "regional equity risk premia widen, procurement accelerates and reserve demand moves into gold",
            "the regional indices are the exposure, the prime takes the orders, bullion is the tail hedge",
        ),
    ),
    # ── GDELT geopolitical ───────────────────────────────────────────
    FastRule(
        "gdelt-conflict-mideast", "armed_conflict", "region=middle_east_oil",
        "Armed conflict in Middle East (GDELT)", _t("USO+ XLE+ GLD+ LMT+"),
        "Oil supply risk, defense demand, systemic risk-off", 0.84,
        scope="global",
        chain=(
            "reported armed conflict in the Gulf puts production and export terminals at risk",
            "a war premium is priced into crude and defense order books re-rate",
            "energy carries the barrel, the prime takes the orders, bullion is the systemic hedge",
        ),
    ),
    FastRule(
        "gdelt-conflict-ukraine", "armed_conflict", "region=ukraine_black_sea",
        "Armed conflict in Ukraine (GDELT)", _t("WEAT+ ZC=F+ TTF=F+"),
        "Grain corridor and gas transit risk", 0.80,
        scope="local",
        chain=(
            "reported fighting around the Black Sea corridor and the transit infrastructure",
            "grain export insurance and gas transit continuity are both repriced",
            "these contracts are the price of the grain and the gas that stop moving",
        ),
    ),
    FastRule(
        "gdelt-military-taiwan", "military_escalation", "region=taiwan",
        "Military escalation Taiwan (GDELT)", _t("TSM- FXI- GLD+"),
        "Foundry supply and cross-strait trade at risk at once", 0.82,
        scope="global",
        chain=(
            "reported military escalation around the strait and the Taiwanese approaches",
            "leading-edge foundry continuity and cross-strait trade are questioned together",
            "the foundry and the mainland index are the exposure, gold is the tail hedge",
        ),
    ),
    FastRule(
        "gdelt-military-korea", "military_escalation", "region=korean_peninsula",
        "Military escalation Korea (GDELT)", _t("EWY- GLD+"),
        "Seoul's industrial belt is inside the risk radius", 0.76,
        scope="global",
        chain=(
            "reported military escalation on the peninsula",
            "Korean assets carry a war discount and reserve demand moves into gold",
            "the country index is the exposure and bullion is the tail hedge",
        ),
    ),
    FastRule(
        "gdelt-sanctions-iran", "sanctions", "region=iran",
        "Sanctions on Iran (GDELT)", _t("USO+ GLD+ XLE+"),
        "Barrels removed from the export balance", 0.78,
        scope="global",
        chain=(
            "tightened sanctions cut Iranian crude out of the legal export balance",
            "the marginal barrel gets more expensive and the geopolitical premium widens",
            "crude and the energy sector carry the barrel; bullion is the reserve-system hedge",
        ),
    ),
    FastRule(
        "gdelt-sanctions-china", "sanctions", "region=china_industrial",
        "Sanctions on China (GDELT)", _t("FXI- SOXX- TSM-"),
        "Export controls cut the semiconductor trade in both directions", 0.74,
        scope="regional",
        chain=(
            "export controls or entity listings restrict semiconductor and equipment trade with China",
            "Chinese industrial demand and the suppliers who sell into it both lose addressable revenue",
            "the mainland index, the chip sector and the foundry sit on the two ends of that trade",
        ),
    ),
    # OFAC actions carry a country, not a box: Iran and China designations land
    # in the boxes above through the capital they are matched at; these two are
    # the sanctioned producers with no box (see sentinel.analyze_ofac_actions).
    FastRule(
        "ofac-sanctions-russia", "sanctions", "country=russia",
        "OFAC designations on Russia", _t("USO+ XLE+ GLD+"),
        "Russian barrels and banks pushed further out of the dollar system", 0.74,
        scope="global",
        chain=(
            "OFAC designates Russian banks, producers or shadow-fleet vessels",
            "Russian crude needs a wider discount to clear and the sanctions premium on the marginal barrel widens",
            "crude and the energy sector carry the barrel; bullion is the reserve-system hedge",
        ),
    ),
    FastRule(
        "ofac-sanctions-venezuela", "sanctions", "country=venezuela",
        "OFAC designations on Venezuela", _t("USO+ XLE+"),
        "Heavy-sour barrels lose their licensed buyer", 0.70,
        scope="global",
        chain=(
            "OFAC designates Venezuelan oil entities or the counterparts that lift PDVSA cargoes",
            "those cargoes lose licensed buyers and the heavy-sour balance tightens",
            "crude and the energy sector are the claim on the barrels that no longer clear",
        ),
    ),
    # USTR tariff actions arrive through the Federal Register with a country and
    # no box; China lands in `china_industrial` and hits the GDELT trade rule.
    FastRule(
        "fedreg-trade-brazil", "trade_dispute", "country=brazil",
        "US tariff action on Brazil (Federal Register)", _t("EWZ-"),
        "Brazilian exporters lose price on their largest single market", 0.68,
        scope="regional",
        chain=(
            "USTR imposes or raises Section 301 duties on Brazilian exports",
            "Brazilian exporters lose US price competitiveness and the real weakens with the trade balance",
            "the country ETF is the exporters and the currency in one line",
        ),
    ),
    FastRule(
        "gdelt-protest-mideast", "mass_protest", "region=middle_east_oil",
        "Mass protest in Middle East (GDELT)", _t("USO+ XLE+"),
        "Instability in a producing state is a supply risk", 0.65,
        scope="regional",
        chain=(
            "sustained mass protest in a Gulf producing state threatens the stability of the regime",
            "a probability of export interruption is priced into the curve",
            "crude and the energy sector are the claim on those barrels",
        ),
    ),
    FastRule(
        "gdelt-trade-dispute-china", "trade_dispute", "region=china_industrial",
        "Trade dispute with China (GDELT)", _t("FXI- ZS=F-"),
        "Retaliation lands on the US farm export that China buys most of", 0.70,
        scope="regional",
        chain=(
            "a tariff or trade dispute escalates and China retaliates on US agricultural imports",
            "Chinese demand for US soybeans is redirected to Brazil and the US balance loosens",
            "the mainland index carries the dispute and the soybean contract carries the lost bid",
        ),
    ),
    FastRule(
        "gdelt-escalation-cluster", "geopolitical_escalation", "",
        "Geopolitical escalation cluster (GDELT)", _t("GLD+ LMT+ ITA+ USO+"),
        "Broad risk-off across unrelated theatres at once", 0.80,
        scope="global",
        chain=(
            "escalation is reported across several unrelated theatres inside the same window",
            "cross-asset risk premia widen together, which is what makes it systemic rather than local",
            "bullion is the reserve hedge, defense takes the procurement, crude takes the supply risk",
        ),
    ),
    FastRule(
        "gdelt-cooperation-mideast", "diplomatic_cooperation", "region=middle_east_oil",
        "Diplomatic cooperation Middle East (GDELT)", _t("USO-"),
        "De-escalation deflates the war premium in the curve", 0.60,
        scope="regional",
        chain=(
            "a ceasefire, accord or sanctions relief is reported between Gulf parties",
            "the geopolitical premium embedded in the crude curve deflates and barrels return",
            "crude is where that premium was priced",
        ),
    ),
    # News conflict / protest (GDELT), regions the first GDELT block does not cover.
    # These were the ACLED rules: the matcher never keyed on source, so they always
    # fired from GDELT too; ACLED itself was dropped 2026-09-20 (its API is not
    # available to a personal account) and the five exact twins were removed.
    FastRule(
        "gdelt-conflict-suez", "armed_conflict", "region=suez_red_sea",
        "Armed conflict Suez/Red Sea (GDELT)", _t("USO+ ZIM+ DAC+"),
        "Chokepoint attacks push Asia-Europe trade around Africa", 0.84,
        scope="site",
        chain=(
            "reported attacks on shipping close the Red Sea approach to commercial traffic",
            "voyages add ten days around the Cape, absorbing capacity and lifting freight rates",
            "the liner earns the spot rate, the lessor re-charters into it, crude carries transit risk",
        ),
    ),
    FastRule(
        "gdelt-conflict-sahel", "armed_conflict", "region=sahel",
        "Armed conflict Sahel (GDELT)", _t("URA+"),
        "Nigerien uranium is a real share of the convertible supply", 0.72,
        scope="regional",
        chain=(
            "armed conflict or a coup in the Sahel threatens Nigerien mine output and the export road",
            "a meaningful share of non-Russian uranium supply is put in doubt against contracted demand",
            "the uranium miners are the listed claim on exactly that supply",
        ),
    ),
    FastRule(
        "gdelt-conflict-nigeria", "armed_conflict", "region=nigeria_oil",
        "Armed conflict Nigeria Delta (GDELT)", _t("USO+"),
        "Delta militancy has historically shut in hundreds of kbd", 0.70,
        scope="local",
        chain=(
            "militant attacks on Delta pipelines and terminals force force-majeure declarations",
            "Nigerian light sweet barrels come off the export balance",
            "crude is the price of the barrels that stop loading",
        ),
    ),
    FastRule(
        "gdelt-conflict-horn-africa", "armed_conflict", "region=horn_of_africa",
        "Armed conflict Horn of Africa (GDELT)", _t("USO+ ZIM+ DAC+"),
        "The Bab-el-Mandeb approach runs along this coast", 0.74,
        scope="regional",
        chain=(
            "armed conflict on the Horn coast raises the threat to the Bab-el-Mandeb approach",
            "war-risk premia and reroute decisions on the Asia-Europe leg follow within days",
            "the box carriers earn the tighter capacity and crude carries the transit risk",
        ),
    ),
    FastRule(
        "gdelt-protest-china", "mass_protest", "region=china_industrial",
        "Mass protest China (GDELT)", _t("FXI-"),
        "Unrest in the industrial belt is a domestic risk premium", 0.66,
        scope="regional",
        chain=(
            "mass protest in the coastal industrial provinces is reported at scale",
            "policy and production continuity risk is repriced into Chinese domestic assets",
            "the mainland large-cap index is the direct claim on that economy",
        ),
    ),
    FastRule(
        "gdelt-conflict-drc-cobalt", "armed_conflict", "region=drc_mining",
        "Armed conflict DRC mining (GDELT)", _t("GLEN.L-"),
        "Congolese output is the producer's own tonnage, not a substitute's gain", 0.70,
        scope="regional",
        chain=(
            "armed conflict across the eastern Congolese mining belt closes sites and the export corridor",
            "Congolese cobalt and base-metal tonnage stops reaching the market",
            "Glencore is the listed producer whose Congolese volume those tonnes are",
        ),
    ),
    # ── Compound (evaluated by the orchestrator, NOT the per-event matcher) ──
    FastRule(
        "compound-energy-crisis", "compound", "multiple_energy_events>=2",
        "Compound energy crisis", _t("USO+ UNG+ XLE+ GLD+"),
        "Multiple simultaneous energy shocks", 0.88,
        scope="global",
        chain=(
            "two or more unrelated energy disruptions land inside the same window",
            "the supply cushion that absorbs any single one is gone, so the whole complex re-prices",
            "crude, gas and the energy sector are the complex; bullion is the inflation-shock hedge",
        ),
    ),
    FastRule(
        "compound-food-crisis", "compound", "multiple_food_events>=2",
        "Compound food crisis", _t("WEAT+ ZC=F+ ZS=F+"),
        "Multiple simultaneous food shocks", 0.85,
        scope="global",
        chain=(
            "two or more unrelated crop or export shocks land inside the same window",
            "importers cover early and exporters restrict, which turns a supply dip into a squeeze",
            "these three contracts are the calories that get substituted between",
        ),
    ),
    FastRule(
        "compound-geopolitical-escalation", "compound", "multiple_conflict_events>=2",
        "Compound geopolitical escalation", _t("GLD+ LMT+ ITA+"),
        "Multiple simultaneous conflicts", 0.82,
        scope="global",
        chain=(
            "two or more unrelated conflicts escalate inside the same window",
            "defense budgets move structurally and reserve demand rotates into gold",
            "bullion is the reserve hedge and these are the order books replenishment lands in",
        ),
    ),
)

RULES_BY_ID: dict[str, FastRule] = {r.id: r for r in FAST_RULES}

# Condition DSL token parsers.
_RE_REGION = re.compile(r"region=(\w+)")
_RE_MAGNITUDE = re.compile(r"earthquake\.magnitude>=(\d+\.?\d*)")
_RE_SEVERITY = re.compile(r"alert\.severity=(\w+)")
_RE_CLUSTER = re.compile(r"fire\.cluster>=(\d+)")
# Policy events name a country, not a point: OFAC stamps `raw_data.country` and
# a rule may gate on it where no region box exists (Russia, Venezuela).
_RE_COUNTRY = re.compile(r"country=(\w+)")


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
        if m and getattr(event, "severity", None) != m.group(1):
            continue

        m = _RE_CLUSTER.search(cond)
        if m:
            cluster_size = (event.raw_data or {}).get("clusterSize")
            if cluster_size is None or cluster_size < int(m.group(1)):
                continue

        m = _RE_COUNTRY.search(cond)
        if m and (getattr(event, "raw_data", None) or {}).get("country") != m.group(1):
            continue

        out.append(rule)

    return out


# ── Template rules: one written chain per (event category, tier), any covered country ──
# A hand-written rule names its region and its basket; writing one per country
# per event type would be some 300 rules, each firing too rarely to ever reach
# the ten resolutions the learning loop wants. A template is written once and
# applied to whichever country the event is in, and its id is shared by every
# country, so `geo_rule_stats` learns "a damaging quake moves the country's
# market" from all of them together.
#
# The chain is still written, not inferred — per event category rather than per
# country, with the country's name filled in. A template states only what holds
# for any country: the national market reprices, and the companies that earn
# only there take the loss first. What a quake does to one country's cement or
# copper is a hand-written rule's claim to make.
#
# National and local are separate templates, not two legs of one, so each tier
# keeps its own record: whether the local companies read an event better than
# the country's market is exactly what the ladder needs measured.
@dataclass(frozen=True)
class RuleTemplate:
    id: str
    category: str
    tier: str  # national — the country ETF · local — countries.COUNTRY_LOCALS
    description: str  # "{country}" is filled with the event's country
    chain: tuple[str, str, str]
    base_confidence: float


# base_confidence 0.50 on purpose: importance = confidence × risk/10 and the
# highest risk a template can reach is 8, so an unlearned template tops out at
# 40 against a notify gate of 60. It sits on the board; it reaches a phone only
# after its own record has lifted it (tested in test_geo_templates.py).
TEMPLATE_RULES: tuple[RuleTemplate, ...] = (
    RuleTemplate(
        "tpl-earthquake-national", "earthquake", "national",
        "Damaging earthquake in {country}",
        (
            "a damaging quake stops plants, ports and transport across the struck part of {country}",
            "lost output and uninsured losses are marked against the companies listed there",
            "the country ETF holds those companies and nothing outside {country}",
        ),
        0.50,
    ),
    RuleTemplate(
        "tpl-cyclone-national", "cyclone", "national",
        "Severe tropical cyclone hits {country}",
        (
            "a severe cyclone shuts ports, power and crops along the coast of {country}",
            "a quarter's output and the repair bill are marked against the companies listed there",
            "the country ETF holds those companies and nothing outside {country}",
        ),
        0.50,
    ),
    RuleTemplate(
        "tpl-flood-national", "flood", "national",
        "Severe flooding in {country}",
        (
            "severe flooding cuts roads, power and harvests in {country}",
            "lost output and the repair bill are marked against the companies listed there",
            "the country ETF holds those companies and nothing outside {country}",
        ),
        0.50,
    ),
    RuleTemplate(
        "tpl-earthquake-local", "earthquake", "local",
        "Damaging earthquake in {country}: the companies that earn only there",
        (
            "a damaging quake closes branches, cuts networks and grounds traffic in {country}",
            "the days lost and the repairs fall on whoever sells only inside the country",
            "a domestic bank, telecom, utility or airport operator has no revenue abroad to lean on",
        ),
        0.50,
    ),
    RuleTemplate(
        "tpl-cyclone-local", "cyclone", "local",
        "Severe tropical cyclone hits {country}: the companies that earn only there",
        (
            "a severe cyclone cuts power, networks and transport along the coast of {country}",
            "the days lost and the repairs fall on whoever sells only inside the country",
            "a domestic bank, telecom, utility or airport operator has no revenue abroad to lean on",
        ),
        0.50,
    ),
    RuleTemplate(
        "tpl-flood-local", "flood", "local",
        "Severe flooding in {country}: the companies that earn only there",
        (
            "severe flooding cuts roads, power and networks in {country}",
            "the days lost and the repairs fall on whoever sells only inside the country",
            "a domestic bank, telecom, utility or airport operator has no revenue abroad to lean on",
        ),
        0.50,
    ),
)
TEMPLATES_BY_ID: dict[str, RuleTemplate] = {t.id: t for t in TEMPLATE_RULES}

# A quake event carries no severity, so the generic red headroom never reaches
# it: PAGER's estimate of the damage is what separates one that shook a city
# from one that broke it.
_PAGER_HEADROOM = {"orange": 1, "red": 2}


def is_template(rule: FastRule) -> bool:
    return rule.id in TEMPLATES_BY_ID


def scoring_rules(rules: list[FastRule]) -> list[FastRule]:
    """The rules that set a signal's confidence and risk.

    Beside a hand-written rule a template adds its legs and nothing else. In the
    mean confidence and the max risk it would change the importance of events
    that have always been scored without it — an M7.2 under Tokyo is 52 and
    silent, and would page at 60. With no hand-written rule the templates are
    all there is, and they score.
    """
    return [r for r in rules if not is_template(r)] or rules


def template_legs(template: RuleTemplate, country: str | None) -> tuple[str, ...]:
    """The instruments a template resolves to in ``country``; empty when it has none."""
    if template.tier == "local":
        return COUNTRY_LOCALS.get(country or "", ())
    etf = COUNTRY_ETF.get(country or "")
    return (etf,) if etf else ()


def template_floor_met(event) -> bool:
    """Whether an event is big enough to be read against its country's market.

    This is the one judgement the templates rest on. Too low, and weekly events
    that never move a market teach the shared template that it is wrong — for
    every country at once. Too high, and it never gathers the ten resolutions
    the learning loop needs to say anything.

    What an event carries: ``event.type`` (earthquake | cyclone | flood),
    ``event.magnitude``, ``event.raw_data["depth"]`` (km) and
    ``event.raw_data["pagerAlert"]`` — USGS's own estimate of the damage, green |
    yellow | orange | red, None until it is computed — for a quake; and
    ``event.severity`` (GDACS: green | orange | red) for a cyclone or a flood.
    """
    # TODO(human): the floor below is a provisional default. Measured 2026-10-04:
    # all seven M≥5.8 quakes of the previous month were PAGER green, including an
    # M6.6 at 10 km depth, so "M≥6.0 and shallow" would have fired on quakes that
    # damaged nothing. PAGER yellow or worse is rarer — a few dozen a year
    # worldwide — which means a slower-learning template.
    raw = getattr(event, "raw_data", None) or {}
    if event.type == "earthquake":
        return raw.get("pagerAlert") in {"yellow", "orange", "red"}
    return getattr(event, "severity", None) in {"orange", "red"}


def resolve_rule(rule_id: str, country: str | None = None, event=None) -> FastRule | None:
    """The rule behind an id: a hand-written one as it stands, or a template
    made concrete for ``country``. None for an unknown id, an uncovered country,
    or a local template in a country with no local company listed.

    ``event`` only sets the risk of an earthquake template (PAGER headroom); a
    caller that renders the rule — the API — does not need it.
    """
    rule = RULES_BY_ID.get(rule_id)
    if rule is not None:
        return rule
    template = TEMPLATES_BY_ID.get(rule_id)
    legs = template_legs(template, country) if template else ()
    if not legs:
        return None
    name = country_phrase(country)
    chain = tuple(clause.format(country=name) for clause in template.chain)
    pager = (getattr(event, "raw_data", None) or {}).get("pagerAlert")
    return FastRule(
        id=template.id,
        category=template.category,
        condition=f"country={country}",
        description=template.description.format(country=name),
        tickers=tuple(RuleTicker(symbol, "bearish") for symbol in legs),
        direction=" → ".join(chain),
        base_confidence=template.base_confidence,
        risk=CATEGORY_RISK.get(template.category, _DEFAULT_RISK) + _PAGER_HEADROOM.get(pager, 0),
        scope="local",
        chain=chain,
    )


def match_templates(event) -> list[FastRule]:
    """The national and local readings of an event in a country with a market.

    They are legs for any event that clears the floor; whether they also score
    the signal is `scoring_rules`' call.
    """
    country = getattr(event, "country", None)
    if country not in COUNTRY_ETF or not template_floor_met(event):
        return []
    rendered = (
        resolve_rule(t.id, country, event) for t in TEMPLATE_RULES if t.category == event.type
    )
    return [rule for rule in rendered if rule is not None]


# ── The gate: which instruments an event may be related to ───────────
# What a hand-written rule already attaches to a region box is that box's
# neighbourhood: a Korean-peninsula event reaches EWY whichever side of the
# border it is geocoded on.
_REGION_SYMBOLS: dict[str, frozenset[str]] = {}
for _rule in FAST_RULES:
    _m = _RE_REGION.search(_rule.condition)
    if _m:
        _REGION_SYMBOLS[_m.group(1)] = _REGION_SYMBOLS.get(_m.group(1), frozenset()) | {
            t.symbol for t in _rule.tickers
        }
_CORE_SYMBOLS = frozenset(t.symbol for r in FAST_RULES for t in r.tickers)


def allowed_symbols(event) -> frozenset[str]:
    """The slice of the universe an event may be related to.

    An instrument bound to a country (countries.INSTRUMENT_COUNTRY) is admitted
    for an event in that country, or in a region box a hand-written rule already
    ties it to. Everything unbound — commodities, sectors, global — is admitted
    everywhere. An event in Brazil never reaches an Indonesian instrument,
    whoever proposes it: this is the check both LLM paths answer to.
    """
    country = getattr(event, "country", None)
    nearby: set[str] = set()
    for region in match_regions(event.latitude, event.longitude):
        nearby |= _REGION_SYMBOLS.get(region, frozenset())
    return frozenset(
        s for s in INSTRUMENT_BREADTH
        if s not in INSTRUMENT_COUNTRY or INSTRUMENT_COUNTRY[s] == country or s in nearby
    )


def fetch_order(symbols) -> list[str]:
    """The order to ask Yahoo in: the hand-written rules' symbols first.

    A stall spends the cycle's budget on whatever is asked first and leaves the
    rest unpriced (prices._STALL_CHUNK). Alphabetical order would put ECH, EIDO
    and the EW* country funds ahead of GLD, USO and XLE, so the baskets that
    have always priced would be the ones to go without.
    """
    return sorted(set(symbols), key=lambda s: (s not in _CORE_SYMBOLS, s))


_SCOPE_LOCAL_MAX_AREA = 200  # deg²; regions up to ~turkey / ukraine are "local"


def region_reach(region: str | None) -> str:
    """Scope inferred from a region box alone: no box → local, small box → local,
    large box → regional. Used to clamp what a generated thesis may target."""
    if not region or region not in GEO_REGIONS:
        return "local"
    la0, la1, lo0, lo1 = GEO_REGIONS[region]
    return "local" if (la1 - la0) * (lo1 - lo0) <= _SCOPE_LOCAL_MAX_AREA else "regional"


def rule_scope(rule: FastRule) -> str:
    """Explicit scope, or one inferred from the region box: compound and
    region-less rules are global, small boxes local, the rest regional."""
    if rule.scope:
        return rule.scope
    if rule.category == "compound":
        return "global"
    m = _RE_REGION.search(rule.condition)
    if not m or m.group(1) not in GEO_REGIONS:
        return "global"
    la0, la1, lo0, lo1 = GEO_REGIONS[m.group(1)]
    return "local" if (la1 - la0) * (lo1 - lo0) <= _SCOPE_LOCAL_MAX_AREA else "regional"


def scope_violations(rule: FastRule) -> list[tuple[str, int]]:
    """(symbol, steps over the scope's allowed breadth) for every leg too wide
    for the event the rule fires on."""
    allowed = _MAX_BREADTH_FOR_SCOPE[rule_scope(rule)]
    out: list[tuple[str, int]] = []
    for t in rule.tickers:
        breadth = INSTRUMENT_BREADTH.get(t.symbol, "global")
        over = BREADTH_RANK[breadth] - allowed
        if over > 0:
            out.append((t.symbol, over))
    return out


def scope_penalty(rule: FastRule) -> float:
    """Confidence penalty for the widest mismatch in the basket: a local event
    aimed at a worldwide instrument is a weaker claim than its base_confidence."""
    worst = max((over for _, over in scope_violations(rule)), default=0)
    return _SCOPE_PENALTY_PER_STEP * worst


def effective_confidence(rule: FastRule, stat: GeoRuleStat | None) -> float:
    """base_confidence + learned confidence_mod − scope penalty, clamped to [0, 1]."""
    mod = float(stat.confidence_mod) if stat and stat.confidence_mod is not None else 0.0
    return max(0.0, min(1.0, rule.base_confidence + mod - scope_penalty(rule)))


def seed_rule_stats(db: Session) -> int:
    """Idempotently seed geo_rule_stats from the static rule and template tables.

    Inserts any missing rule_id with its base_confidence; never overwrites learned
    tuning on existing rows. Returns the number of new rows inserted.
    """
    existing = {row.rule_id for row in db.query(GeoRuleStat.rule_id).all()}
    inserted = 0
    for rule in (*FAST_RULES, *TEMPLATE_RULES):
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
