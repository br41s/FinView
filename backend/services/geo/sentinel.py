"""Sentinel + specialist analysts — normalize source data into GeoEvent objects.

Port of WorldHawk's sentinel.ts + the 5 specialist analysts (ais/weather/flight/
gdelt/acled). Each function turns a raw source feed into a list of GeoEvent with a
fine-grained ``type`` that the rule matcher keys on.

Difference from WorldHawk: the per-process "processed" dedup sets are dropped. The
pipeline runs per user, so cross-user suppression would be a bug; per-user
idempotency is handled by the advisor's DB dedup (unique user_id+source+external_id
+ confidence-shift re-notify). The only retained cross-cycle state is the flight
rolling baseline, which is objective (traffic counts, user-independent).
"""

import logging
import re
import time
from dataclasses import dataclass, field

from .chokepoints import CHOKEPOINTS, is_cargo, is_tanker
from .ingest.types import (
    AcledEvent,
    FireHotspot,
    FlightData,
    GdeltEvent,
    MeteoPoint,
    NaturalEvent,
    SeismicEvent,
    VesselSnapshot,
)
from .rules import match_regions

logger = logging.getLogger(__name__)


@dataclass
class GeoEvent:
    """A financially relevant event (WorldHawk's FinancialEvent)."""

    id: str
    type: str  # matcher category
    title: str
    latitude: float
    longitude: float
    source: str
    timestamp: int  # epoch ms
    magnitude: float | None = None
    severity: str | None = None
    region: str | None = None
    raw_data: dict = field(default_factory=dict)


# ── Relevance thresholds ─────────────────────────────────────────────
_MIN_EARTHQUAKE_MAG = 5.5
_MIN_FIRE_CLUSTER_SIZE = 15
_FIRE_GRID_DEG = 2

# Natural-event category → matcher type.
_NATURAL_TYPE = {
    "cyclone": "cyclone",
    "volcano": "volcano",
    "flood": "flood",
    "storm": "storm",
    "drought": "drought",
    "iceberg": "iceberg",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Sentinel: USGS earthquakes ───────────────────────────────────────
def analyze_earthquakes(quakes: list[SeismicEvent]) -> list[GeoEvent]:
    out: list[GeoEvent] = []
    for q in quakes:
        if q.magnitude < _MIN_EARTHQUAKE_MAG:
            continue
        regions = match_regions(q.latitude, q.longitude)
        if not regions:
            continue
        out.append(
            GeoEvent(
                id=f"eq-{q.id}",
                type="earthquake",
                title=f"M{q.magnitude:.1f} Earthquake — {q.place}",
                latitude=q.latitude,
                longitude=q.longitude,
                magnitude=q.magnitude,
                region=regions[0],
                source="usgs",
                timestamp=q.time or _now_ms(),
                raw_data={"depth": q.depth, "url": q.url},
            )
        )
    return out


# ── Sentinel: EONET / GDACS natural events ───────────────────────────
def analyze_natural_events(events: list[NaturalEvent]) -> list[GeoEvent]:
    out: list[GeoEvent] = []
    for e in events:
        regions = match_regions(e.latitude, e.longitude)
        if not regions and e.severity != "red":
            continue
        etype = _NATURAL_TYPE.get(e.category)
        if not etype:
            continue
        out.append(
            GeoEvent(
                id=f"evt-{e.id}",
                type=etype,
                title=e.title,
                latitude=e.latitude,
                longitude=e.longitude,
                severity=e.severity,
                region=regions[0] if regions else None,
                source=e.source,
                timestamp=_now_ms(),
                raw_data={"category": e.category, "url": e.url},
            )
        )
    return out


# ── Sentinel: FIRMS fire clusters ────────────────────────────────────
def analyze_fire_clusters(fires: list[FireHotspot]) -> list[GeoEvent]:
    if len(fires) < _MIN_FIRE_CLUSTER_SIZE:
        return []

    clusters: dict[str, list[FireHotspot]] = {}
    for f in fires:
        if f.confidence == "l":
            continue
        cell = f"{int(f.latitude // _FIRE_GRID_DEG)}_{int(f.longitude // _FIRE_GRID_DEG)}"
        clusters.setdefault(cell, []).append(f)

    out: list[GeoEvent] = []
    for cell, cluster in clusters.items():
        if len(cluster) < _MIN_FIRE_CLUSTER_SIZE:
            continue
        lat = sum(f.latitude for f in cluster) / len(cluster)
        lon = sum(f.longitude for f in cluster) / len(cluster)
        regions = match_regions(lat, lon)
        if not regions:
            continue
        out.append(
            GeoEvent(
                id=f"fire-cluster-{cell}",
                type="fire",
                title=f"Major Fire Cluster — {len(cluster)} hotspots near "
                f"{regions[0].replace('_', ' ')}",
                latitude=lat,
                longitude=lon,
                region=regions[0],
                source="firms",
                timestamp=_now_ms(),
                raw_data={
                    "clusterSize": len(cluster),
                    "avgFrp": sum(f.frp for f in cluster) / len(cluster),
                },
            )
        )
    return out


# ── Sentinel: alert zones (static geopolitical hotspots) ─────────────
# (id, name, type, severity, polygon[[lat, lon], ...])
ALERT_ZONES: tuple[tuple[str, str, str, str, tuple[tuple[float, float], ...]], ...] = (
    ("ukraine-russia", "Ukraine / Russia Front", "active-conflict", "red",
     ((52.4, 23.5), (52.4, 40.2), (44.3, 40.2), (44.3, 33.0), (46.0, 30.0), (48.5, 23.5))),
    ("gaza-israel", "Gaza / Israel", "active-conflict", "red",
     ((31.8, 34.0), (31.8, 34.7), (31.1, 34.7), (31.1, 34.0))),
    ("taiwan-strait", "Taiwan Strait", "tension-zone", "amber",
     ((26.5, 117.0), (26.5, 122.5), (22.0, 122.5), (22.0, 117.0))),
    ("south-china-sea", "South China Sea", "disputed-territory", "amber",
     ((23.0, 109.0), (23.0, 121.0), (15.0, 121.0), (7.0, 117.0), (3.0, 110.0), (7.0, 105.0), (15.0, 109.0))),
    ("korean-dmz", "Korean DMZ", "tension-zone", "amber",
     ((38.8, 124.5), (38.8, 128.5), (37.5, 128.5), (37.5, 124.5))),
    ("iran-israel", "Iran / Israel Tensions", "tension-zone", "amber",
     ((37.5, 44.0), (37.5, 60.0), (25.0, 60.0), (25.0, 44.0))),
    ("sudan", "Sudan", "active-conflict", "red",
     ((22.0, 21.8), (22.0, 38.6), (8.7, 38.6), (8.7, 21.8))),
    ("syria", "Syria", "active-conflict", "red",
     ((37.3, 35.7), (37.3, 42.4), (32.3, 42.4), (32.3, 35.7))),
)


def analyze_alert_zones() -> list[GeoEvent]:
    """Emit a conflict event per red-severity alert zone (centroid-located)."""
    out: list[GeoEvent] = []
    for zid, name, ztype, severity, polygon in ALERT_ZONES:
        if severity != "red":
            continue
        lat = sum(p[0] for p in polygon) / len(polygon)
        lon = sum(p[1] for p in polygon) / len(polygon)
        regions = match_regions(lat, lon)
        out.append(
            GeoEvent(
                id=f"alert-{zid}",
                type="conflict",
                title=f"Geopolitical Alert: {name}",
                latitude=lat,
                longitude=lon,
                severity=severity,
                region=regions[0] if regions else None,
                source="alerts",
                timestamp=_now_ms(),
                raw_data={"type": ztype},
            )
        )
    return out


def sentinel_scan(
    earthquakes: list[SeismicEvent],
    events: list[NaturalEvent],
    fires: list[FireHotspot],
) -> list[GeoEvent]:
    """Run the core sentinel scan (alert zones added separately, they need no data)."""
    out: list[GeoEvent] = []
    out.extend(analyze_earthquakes(earthquakes))
    out.extend(analyze_natural_events(events))
    out.extend(analyze_fire_clusters(fires))
    out.extend(analyze_alert_zones())
    return out


# ── Specialist: flight anomalies (OpenSky) ───────────────────────────
# (id, region, latMin, latMax, lonMin, lonMax, normalFlights, dropThreshold, milSurgeThreshold)
_AIRSPACE_ZONES = (
    ("middle-east", "middle_east_oil", 12, 38, 35, 60, 200, 0.4, 15),
    ("ukraine-blacksea", "ukraine_black_sea", 41, 52, 28, 42, 80, 0.5, 10),
    ("taiwan-strait", "taiwan", 21, 30, 117, 127, 150, 0.4, 12),
    ("korean-peninsula", "korean_peninsula", 33, 43, 124, 132, 100, 0.45, 10),
    ("south-china-sea", "south_china_sea", 4, 24, 105, 121, 250, 0.35, 15),
    ("iran-airspace", "iran", 25, 40, 44, 63, 60, 0.5, 8),
    ("hormuz-airspace", "strait_of_hormuz", 24, 28, 54, 58, 30, 0.5, 5),
    ("northern-europe", "northern_europe", 54, 72, 10, 30, 180, 0.45, 12),
)
_FLIGHT_MAX_HISTORY = 12
# Objective (user-independent) rolling baselines: zone_id → list[(total, military, ts_ms)].
# Hydrated from geo_flight_samples by the orchestrator before each analysis and
# written back after — process memory alone dies at scale-to-zero (see the model).
_flight_history: dict[str, list[tuple[int, int, int]]] = {}
_MIN_BASELINE_SAMPLES = 2


def analyze_flight_anomalies(flights: list[FlightData]) -> list[GeoEvent]:
    if not flights:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []

    for zid, region, lat_min, lat_max, lon_min, lon_max, normal, drop_thr, mil_thr in _AIRSPACE_ZONES:
        total = military = 0
        for f in flights:
            if f.on_ground:
                continue
            if lat_min <= f.latitude <= lat_max and lon_min <= f.longitude <= lon_max:
                total += 1
                if f.is_military:
                    military += 1

        hist = _flight_history.setdefault(zid, [])
        hist.append((total, military, now))
        if len(hist) > _FLIGHT_MAX_HISTORY:
            hist.pop(0)

        prior = hist[:-1]
        baseline = round(sum(h[0] for h in prior) / len(prior)) if len(prior) >= 1 else normal
        # No baseline, no surge: a default of 2 made any cold start with a
        # handful of tankers on station a "military surge".
        has_mil_baseline = len(prior) >= _MIN_BASELINE_SAMPLES
        mil_baseline = round(sum(h[1] for h in prior) / len(prior)) if has_mil_baseline else 0

        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2

        # Airspace evacuation / flight drop.
        if baseline > 10 and total > 0:
            drop_pct = (baseline - total) / baseline
            if drop_pct >= drop_thr:
                out.append(
                    GeoEvent(
                        id=f"air-drop-{zid}",
                        type="airspace_closure",
                        title=f"Flight Traffic Drop over {region.replace('_', ' ')}",
                        latitude=center_lat,
                        longitude=center_lon,
                        region=region,
                        source="opensky",
                        timestamp=now,
                        raw_data={
                            "zone": zid,
                            "currentFlights": total,
                            "baselineFlights": baseline,
                            "dropPercent": round(drop_pct * 100),
                            "militaryPresent": military,
                        },
                    )
                )

        # Military activity surge.
        if has_mil_baseline and military >= mil_thr and military > mil_baseline * 2:
            out.append(
                GeoEvent(
                    id=f"air-military-{zid}",
                    type="military_surge",
                    title=f"Military Flight Surge over {region.replace('_', ' ')}",
                    latitude=center_lat,
                    longitude=center_lon,
                    region=region,
                    source="opensky",
                    timestamp=now,
                    raw_data={
                        "zone": zid,
                        "militaryFlights": military,
                        "baselineMilitary": mil_baseline,
                        "totalFlights": total,
                    },
                )
            )
    return out


# ── Specialist: weather extremes (Windy) ─────────────────────────────
_WX = {
    "heat_c": 45, "cold_c": -30, "wind_kmh": 90,
    "gust_kmh": 120, "precip_mm3h": 50, "low_hpa": 970,
}


def analyze_weather_extremes(points: list[MeteoPoint]) -> list[GeoEvent]:
    if not points:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []
    for p in points:
        regions = match_regions(p.latitude, p.longitude)
        if not regions:
            continue
        region = regions[0]
        rlabel = region.replace("_", " ")
        key = f"{int(p.latitude)}_{int(p.longitude)}"

        def ev(suffix: str, etype: str, title: str, extra: dict) -> GeoEvent:
            return GeoEvent(
                id=f"wx-{suffix}-{key}", type=etype, title=title,
                latitude=p.latitude, longitude=p.longitude, region=region,
                source="windy", timestamp=now, raw_data=extra,
            )

        if p.temperature >= _WX["heat_c"]:
            out.append(ev("heat", "extreme_heat", f"Extreme Heatwave — {p.temperature}°C near {rlabel}",
                          {"temperature": p.temperature, "windSpeed": p.wind_speed}))
        if p.temperature <= _WX["cold_c"]:
            out.append(ev("cold", "extreme_cold", f"Extreme Cold Snap — {p.temperature}°C near {rlabel}",
                          {"temperature": p.temperature, "windSpeed": p.wind_speed}))
        if p.wind_speed >= _WX["wind_kmh"] or p.wind_gust >= _WX["gust_kmh"]:
            speed = round(max(p.wind_speed, p.wind_gust))
            out.append(ev("wind", "severe_storm", f"Severe Wind Storm — {speed} km/h near {rlabel}",
                          {"windSpeed": p.wind_speed, "windGust": p.wind_gust}))
        if p.precipitation >= _WX["precip_mm3h"]:
            out.append(ev("precip", "heavy_precipitation",
                          f"Heavy Precipitation — {p.precipitation}mm/3h near {rlabel}",
                          {"precipitation": p.precipitation}))
        if p.pressure <= _WX["low_hpa"]:
            out.append(ev("lowpres", "deep_cyclone",
                          f"Deep Low Pressure System — {p.pressure} hPa near {rlabel}",
                          {"pressure": p.pressure}))
    return out


# ── Specialist: GDELT geopolitical ───────────────────────────────────
# Matched as words, not substrings: "BAN" used to hit Lebanon, Albania,
# Bangladesh and "central bank", so sanctions swallowed most of the feed, and
# "STRIKE" claimed every airstrike for protest. A short suffix set keeps the
# stems working ("sanctions", "restrictions", "demonstrators") without the
# false positives. Order matters — first match wins: the most specific list
# (armed_conflict) is checked first so "airstrike" is never a protest and
# "sanctions on military exports" stays sanctions; the broadest list
# (trade_dispute: TRADE / IMPORT / EXPORT) is checked last. FORCE and DEPLOY
# are deliberately absent from military_escalation — "task force", "police
# forces" and "deploys capital" were paging the highest-risk category.
_GDELT_ACTOR_PATTERNS = {
    "armed_conflict": (
        "AIRSTRIKE", "INVASION", "INVAD", "OFFENSIVE", "SHELLING", "ARTILLERY", "BOMBARD", "CLASH",
    ),
    "sanctions": ("SANCTION", "EMBARGO", "BAN", "RESTRICT", "TARIFF"),
    "protest": ("PROTEST", "DEMONSTRAT", "RIOT", "STRIKE", "UNREST"),
    "military_escalation": ("MILITARY", "ARMY", "NAVY", "TROOP", "WARSHIP", "MISSILE", "NUCLEAR"),
    "trade_dispute": ("TRADE", "TARIFF", "IMPORT", "EXPORT", "WTO"),
}
_PATTERN_SUFFIX = r"(?:S|ES|ED|ING|ER|ERS|OR|ORS|ION|IONS|MENT|MENTS)?\b"
_GDELT_PATTERN_RE = {
    category: re.compile(r"\b(?:" + "|".join(patterns) + ")" + _PATTERN_SUFFIX, re.IGNORECASE)
    for category, patterns in _GDELT_ACTOR_PATTERNS.items()
}
# category → (financial_type, max_goldstein, min_goldstein)
# No mention/source floors: the Doc API supplies no counts (see ingest/gdelt.py),
# so the old 8–15 mention / 3–5 source floors could only ever be met by the
# fabricated constants they were written against — and those were below the
# floors, which is why prod holds 0 GDELT-sourced signals out of 1700.
# goldstein_scale is likewise the *query's* severity prior (-6 conflict, -4
# sanctions, -3 protest), not a per-article measurement, so a floor means
# "which query may supply this category": armed_conflict only from the conflict
# query, never from a protest headline. A floor below every query constant is
# unreachable — armed_conflict shipped dead at -7 for exactly that reason.
_GDELT_FILTERS = {
    "armed_conflict": ("armed_conflict", -6, None),
    "military_escalation": ("military_escalation", -4, None),
    "sanctions": ("sanctions", -3, None),
    "protest": ("mass_protest", -3, None),
    "diplomatic_tension": ("diplomatic_tension", -3, None),
    "trade_dispute": ("trade_dispute", -3, None),
    "cooperation": ("diplomatic_cooperation", None, 6),
}


def _classify_gdelt(evt: GdeltEvent) -> str | None:
    text = f"{evt.title} {evt.actor1} {evt.actor2}"
    for category, pattern in _GDELT_PATTERN_RE.items():
        if pattern.search(text):
            return category
    # No keyword: only the conflict query's prior (-6) says anything on its own —
    # "Ukraine war, day 900" is conflict news without a trigger word. The other
    # two priors are too weak to classify an unmatched headline.
    if evt.goldstein_scale <= -6:
        return "armed_conflict"
    return None


def analyze_gdelt_events(gdelt_events: list[GdeltEvent]) -> list[GeoEvent]:
    if not gdelt_events:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []
    region_counts: dict[str, dict] = {}
    seen: set[str] = set()

    for evt in gdelt_events:
        category = _classify_gdelt(evt)
        if not category or category not in _GDELT_FILTERS:
            continue
        ftype, max_g, min_g = _GDELT_FILTERS[category]
        if max_g is not None and evt.goldstein_scale > max_g:
            continue
        if min_g is not None and evt.goldstein_scale < min_g:
            continue

        regions = match_regions(evt.latitude, evt.longitude)
        region = regions[0] if regions else None
        region_key = region or f"{int(evt.latitude)}_{int(evt.longitude)}"
        day = (evt.date_added or "")[:8] or "today"

        tr = region_counts.setdefault(region_key, {"count": 0, "sum_g": 0.0})
        tr["count"] += 1
        tr["sum_g"] += evt.goldstein_scale

        # Ten headlines about one story are one event. The id is region+day
        # keyed on purpose, but emitting a GeoEvent per article let the compound
        # tally count article volume as "simultaneous events".
        event_id = f"gdelt-{category}-{region_key}-{day}"
        if event_id in seen:
            continue
        seen.add(event_id)
        # Never "red" from a query constant: red is what severity_headroom reads
        # as evidence the event exceeded its rule floor.
        severity = "orange" if evt.goldstein_scale <= -4 else None
        out.append(
            GeoEvent(
                id=event_id,
                type=ftype,
                title=f"{category.replace('_', ' ').title()}: {evt.title[:120]}",
                latitude=evt.latitude,
                longitude=evt.longitude,
                severity=severity,
                region=region,
                source="gdelt",
                timestamp=now,
                raw_data={
                    "goldsteinScale": evt.goldstein_scale,
                    "actor1": evt.actor1,
                    "category": category,
                },
            )
        )

    # Compound escalation: ≥3 events clustered in one real region, avg goldstein ≤ -5.
    region_ids = set(_iter_region_ids())
    for region_key, tr in region_counts.items():
        avg_g = tr["sum_g"] / tr["count"] if tr["count"] else 0
        if tr["count"] >= 3 and avg_g <= -5 and region_key in region_ids:
            sample = next(
                (e for e in gdelt_events if region_key in match_regions(e.latitude, e.longitude)),
                None,
            )
            if sample:
                out.append(
                    GeoEvent(
                        id=f"gdelt-escalation-{region_key}",
                        type="geopolitical_escalation",
                        title=f"Geopolitical Escalation Cluster — "
                        f"{region_key.replace('_', ' ')} ({tr['count']} events)",
                        latitude=sample.latitude,
                        longitude=sample.longitude,
                        # Article volume in one region is a real signal; the avg
                        # goldstein behind it is still a query constant, so it
                        # earns "orange", never the "red" severity_headroom reads.
                        severity="orange",
                        region=region_key,
                        source="gdelt",
                        timestamp=now,
                        raw_data={"eventCount": tr["count"], "avgGoldstein": avg_g},
                    )
                )
    return out


def _iter_region_ids():
    from .rules import GEO_REGIONS

    return GEO_REGIONS.keys()


# ── Specialist: ACLED conflict ───────────────────────────────────────
# acled_type → (financial_type, min_fatalities, red_thr, orange_thr)
_ACLED_MAPPINGS = {
    "Battles": ("armed_conflict", 5, 50, 10),
    "Explosions/Remote violence": ("armed_conflict", 3, 30, 5),
    "Violence against civilians": ("armed_conflict", 10, 100, 20),
    "Riots": ("mass_protest", 0, 20, 5),
    "Protests": ("mass_protest", 0, 10, 1),
    "Strategic developments": ("geopolitical_escalation", 0, 50, 10),
}
_ACLED_SUB_OVERRIDES = {
    "Air/drone strike": "military_escalation",
    "Shelling/artillery/missile attack": "military_escalation",
    "Chemical weapon": "military_escalation",
    "Headquarters or base established": "military_escalation",
    "Armed clash": "armed_conflict",
    "Remote explosive/landmine/IED": "armed_conflict",
    "Government regains territory": "armed_conflict",
    "Non-state actor overtakes territory": "armed_conflict",
    "Mob violence": "mass_protest",
    "Excessive force against protesters": "mass_protest",
    "Peaceful protest": "mass_protest",
    "Protest with intervention": "mass_protest",
    "Violent demonstration": "mass_protest",
    "Looting/property destruction": "mass_protest",
    "Agreement": "diplomatic_cooperation",
    "Arrests": "diplomatic_tension",
}


def analyze_acled_events(acled_events: list[AcledEvent]) -> list[GeoEvent]:
    if not acled_events:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []

    # Cluster by country + event_type + day.
    groups: dict[str, list[AcledEvent]] = {}
    for evt in acled_events:
        day = evt.event_date[:10]
        groups.setdefault(f"{evt.country}|{evt.event_type}|{day}", []).append(evt)

    region_intensity: dict[str, dict] = {}

    for gkey, group in groups.items():
        country, event_type, date = gkey.split("|")
        mapping = _ACLED_MAPPINGS.get(event_type)
        if not mapping:
            continue
        ftype_default, min_fat, red_thr, orange_thr = mapping

        total_fatalities = sum(e.fatalities for e in group)
        if total_fatalities < min_fat and len(group) < 3:
            continue

        lat = sum(e.latitude for e in group) / len(group)
        lon = sum(e.longitude for e in group) / len(group)

        sub_counts: dict[str, int] = {}
        for e in group:
            sub_counts[e.sub_event_type] = sub_counts.get(e.sub_event_type, 0) + 1
        dominant_sub = max(sub_counts, key=sub_counts.get) if sub_counts else ""
        ftype = _ACLED_SUB_OVERRIDES.get(dominant_sub, ftype_default)

        regions = match_regions(lat, lon)
        region = regions[0] if regions else None
        region_id = region or f"{country.lower().replace(' ', '_')}"
        admin1 = group[0].admin1
        location = f"{admin1}, {country}" if admin1 else country

        intensity = region_intensity.setdefault(region_id, {"events": 0, "fatalities": 0})
        intensity["events"] += len(group)
        intensity["fatalities"] += total_fatalities

        severity = "red" if total_fatalities >= red_thr else "orange" if total_fatalities >= orange_thr else None
        fat_str = f" ({total_fatalities} fatalities)" if total_fatalities else ""
        out.append(
            GeoEvent(
                id=f"acled-{region_id}-{ftype}-{date}",
                type=ftype,
                title=f"{event_type} in {location}{fat_str}",
                latitude=lat,
                longitude=lon,
                severity=severity,
                region=region,
                source="acled",
                timestamp=now,
                raw_data={
                    "eventType": event_type,
                    "subEventType": dominant_sub,
                    "eventCount": len(group),
                    "totalFatalities": total_fatalities,
                    "country": country,
                },
            )
        )

    # Escalation: high cumulative intensity per region.
    region_ids = set(_iter_region_ids())
    for region_id, intensity in region_intensity.items():
        if region_id not in region_ids:
            continue
        if intensity["events"] >= 10 and intensity["fatalities"] >= 50:
            sample = next(
                (g[0] for g in groups.values()
                 if region_id in match_regions(g[0].latitude, g[0].longitude)),
                None,
            )
            if sample:
                out.append(
                    GeoEvent(
                        id=f"acled-escalation-{region_id}",
                        type="geopolitical_escalation",
                        title=f"ACLED Conflict Escalation — {region_id.replace('_', ' ')} "
                        f"({intensity['events']} events, {intensity['fatalities']} fatalities)",
                        latitude=sample.latitude,
                        longitude=sample.longitude,
                        severity="red",
                        region=region_id,
                        source="acled",
                        timestamp=now,
                        raw_data={
                            "eventCount": intensity["events"],
                            "totalFatalities": intensity["fatalities"],
                        },
                    )
                )
    return out


# ── Specialist: AIS maritime chokepoint traffic ──────────────────────
_AIS_MAX_HISTORY = 10
# Objective rolling baselines: chokepoint id → list of {tankers,cargo,anchored,total}.
_ais_history: dict[str, list[dict]] = {}


def _count_in_chokepoint(vessels: list[VesselSnapshot], cp) -> dict:
    tankers = cargo = anchored = total = 0
    for v in vessels:
        if cp.lat_min <= v.latitude <= cp.lat_max and cp.lon_min <= v.longitude <= cp.lon_max:
            total += 1
            if is_tanker(v.ship_type):
                tankers += 1
            if is_cargo(v.ship_type):
                cargo += 1
            if v.nav_status == 1 or v.sog < 0.5:
                anchored += 1
    return {"tankers": tankers, "cargo": cargo, "anchored": anchored, "total": total}


def _rolling_avg(history: list[dict]) -> dict:
    n = len(history)
    if n == 0:
        return {"tankers": 0, "cargo": 0, "anchored": 0, "total": 0}
    return {k: round(sum(h[k] for h in history) / n) for k in ("tankers", "cargo", "anchored", "total")}


def analyze_vessels(vessels: list[VesselSnapshot]) -> list[GeoEvent]:
    """Detect chokepoint disruption / rerouting / congestion from live AIS traffic.

    Port of WorldHawk's analyzeVesselTraffic. Emits stable per-chokepoint event ids
    every cycle while a condition holds; the advisor handles per-user dedup.
    """
    if not vessels:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []

    for cp in CHOKEPOINTS:
        current = _count_in_chokepoint(vessels, cp)
        hist = _ais_history.setdefault(cp.id, [])
        hist.append(current)
        if len(hist) > _AIS_MAX_HISTORY:
            hist.pop(0)

        if len(hist) >= 2:
            baseline = _rolling_avg(hist[:-1])
        else:
            baseline = {
                "tankers": cp.normal_tankers, "cargo": cp.normal_cargo,
                "anchored": 0, "total": cp.normal_tankers + cp.normal_cargo,
            }

        clat = (cp.lat_min + cp.lat_max) / 2
        clon = (cp.lon_min + cp.lon_max) / 2

        def _ev(eid: str, etype: str, title: str, extra: dict) -> GeoEvent:
            return GeoEvent(
                id=eid, type=etype, title=title, latitude=clat, longitude=clon,
                region=cp.region, source="ais", timestamp=now, raw_data=extra,
            )

        # Tanker traffic drop.
        if baseline["tankers"] > 3 and current["tankers"] > 0:
            drop = (baseline["tankers"] - current["tankers"]) / baseline["tankers"]
            if drop >= cp.drop_threshold:
                out.append(_ev(
                    f"ais-tanker-drop-{cp.id}", "maritime_disruption",
                    f"Tanker Traffic Drop at {cp.name}",
                    {"chokepoint": cp.id, "currentTankers": current["tankers"],
                     "baselineTankers": baseline["tankers"], "dropPercent": round(drop * 100)},
                ))

        # Cargo traffic drop.
        if baseline["cargo"] > 5 and current["cargo"] > 0:
            drop = (baseline["cargo"] - current["cargo"]) / baseline["cargo"]
            if drop >= cp.drop_threshold:
                out.append(_ev(
                    f"ais-cargo-drop-{cp.id}", "maritime_disruption",
                    f"Cargo Traffic Drop at {cp.name}",
                    {"chokepoint": cp.id, "currentCargo": current["cargo"],
                     "baselineCargo": baseline["cargo"], "dropPercent": round(drop * 100)},
                ))

        # Rerouting spike (Cape of Good Hope).
        if cp.id == "cape-good-hope" and baseline["tankers"] > 0:
            spike = (current["tankers"] - baseline["tankers"]) / max(baseline["tankers"], 1)
            if spike >= cp.spike_threshold:
                out.append(_ev(
                    f"ais-reroute-{cp.id}", "maritime_rerouting",
                    "Tanker Rerouting via Cape of Good Hope",
                    {"currentTankers": current["tankers"], "baselineTankers": baseline["tankers"],
                     "spikePercent": round(spike * 100)},
                ))

        # Congestion (anchored vessel spike).
        normal_anchored = max(baseline["anchored"], 2)
        if current["anchored"] > normal_anchored * 2 and current["anchored"] >= 5:
            out.append(_ev(
                f"ais-congestion-{cp.id}", "maritime_congestion",
                f"Port Congestion at {cp.name}",
                {"anchoredVessels": current["anchored"], "baselineAnchored": baseline["anchored"],
                 "totalVessels": current["total"]},
            ))

    return out
