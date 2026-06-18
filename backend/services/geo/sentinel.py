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
import time
from dataclasses import dataclass, field

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
# Objective (user-independent) rolling baselines: zone_id → list[(total, military, ts)].
_flight_history: dict[str, list[tuple[int, int, int]]] = {}


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
        mil_baseline = round(sum(h[1] for h in prior) / len(prior)) if len(prior) >= 2 else 2

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
        if military >= mil_thr and military > mil_baseline * 2:
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
_GDELT_ACTOR_PATTERNS = {
    "sanctions": ("SANCTION", "EMBARGO", "BAN", "RESTRICT", "TARIFF"),
    "military_escalation": ("MILITARY", "ARMY", "NAVY", "FORCE", "DEPLOY", "MISSILE", "NUCLEAR"),
    "protest": ("PROTEST", "DEMONSTRAT", "RIOT", "STRIKE", "UNREST"),
    "trade_dispute": ("TRADE", "TARIFF", "IMPORT", "EXPORT", "WTO"),
}
# category → (financial_type, max_goldstein, min_goldstein, min_mentions, min_sources)
_GDELT_FILTERS = {
    "armed_conflict": ("armed_conflict", -7, None, 10, 5),
    "military_escalation": ("military_escalation", -5, None, 8, 4),
    "sanctions": ("sanctions", -4, None, 10, 5),
    "protest": ("mass_protest", -3, None, 15, 5),
    "diplomatic_tension": ("diplomatic_tension", -4, None, 8, 3),
    "trade_dispute": ("trade_dispute", -3, None, 12, 5),
    "cooperation": ("diplomatic_cooperation", None, 6, 10, 4),
}


def _classify_gdelt(evt: GdeltEvent) -> str | None:
    text = f"{evt.title} {evt.actor1} {evt.actor2}".upper()
    for category, patterns in _GDELT_ACTOR_PATTERNS.items():
        if any(p in text for p in patterns):
            return category
    if evt.goldstein_scale <= -7:
        return "armed_conflict"
    if evt.goldstein_scale <= -5:
        return "military_escalation"
    if evt.goldstein_scale <= -3:
        return "diplomatic_tension"
    if evt.goldstein_scale >= 6:
        return "cooperation"
    return None


def analyze_gdelt_events(gdelt_events: list[GdeltEvent]) -> list[GeoEvent]:
    if not gdelt_events:
        return []
    now = _now_ms()
    out: list[GeoEvent] = []
    region_counts: dict[str, dict] = {}

    for evt in gdelt_events:
        if evt.num_mentions < 5 or evt.num_sources < 3:
            continue
        category = _classify_gdelt(evt)
        if not category or category not in _GDELT_FILTERS:
            continue
        ftype, max_g, min_g, min_m, min_s = _GDELT_FILTERS[category]
        if max_g is not None and evt.goldstein_scale > max_g:
            continue
        if min_g is not None and evt.goldstein_scale < min_g:
            continue
        if evt.num_mentions < min_m or evt.num_sources < min_s:
            continue

        regions = match_regions(evt.latitude, evt.longitude)
        region = regions[0] if regions else None
        region_key = region or f"{int(evt.latitude)}_{int(evt.longitude)}"
        day = (evt.date_added or "")[:8] or "today"

        tr = region_counts.setdefault(region_key, {"count": 0, "sum_g": 0.0})
        tr["count"] += 1
        tr["sum_g"] += evt.goldstein_scale

        severity = "red" if evt.goldstein_scale <= -7 else "orange" if evt.goldstein_scale <= -4 else None
        out.append(
            GeoEvent(
                id=f"gdelt-{category}-{region_key}-{day}",
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
                    "numMentions": evt.num_mentions,
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
                        severity="red",
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


# ── Specialist: AIS maritime (DEFERRED) ──────────────────────────────
def analyze_vessels(vessels: list[VesselSnapshot]) -> list[GeoEvent]:
    """Maritime chokepoint analysis — DEFERRED (see ingest/maritime.py).

    Needs a global AIS feed + cross-cycle vessel-count history; current data is
    Nordic-only and matches no rule chokepoint. Returns [] until the WS collector
    lands. The strait regions are covered meanwhile by conflict/GDELT/ACLED rules.
    """
    return []
