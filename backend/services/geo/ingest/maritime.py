"""AIS maritime vessel positions → VesselSnapshot list.

DEFERRED — global coverage gap, flagged for the owner:

WorldHawk's maritime signal (chokepoint disruption/rerouting/congestion) needs a
*global* AIS feed plus cross-cycle vessel-count history. It got that from a
long-lived ``aisstream.io`` WebSocket; the only HTTP fallback (Digitraffic) covers
Nordic/Baltic waters only — none of the rule chokepoints (Hormuz, Suez, Malacca,
Panama, Cape). A persistent WebSocket also does not fit Cloud Run's scale-to-zero
model, so the global collector is a separate piece of work.

This module ships the Digitraffic HTTP client (the faithful port of the route's
fallback path) so the source is wired and swappable, but it returns no chokepoint
coverage. Until the WS collector lands, the maritime_* rules stay dormant — the
same strait regions are still covered by the conflict / GDELT / ACLED rules.
"""

import logging

from .base import TTLCache, fetch_json
from .types import VesselSnapshot

logger = logging.getLogger(__name__)

# Digitraffic (Finnish Transport Agency) — Nordic/Baltic AIS only.
_LOCATIONS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
_VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"
_LOC_TTL = 60
_NAMES_TTL = 600

_loc_cache = TTLCache()
_names_cache = TTLCache()


async def _fetch_names() -> dict[int, dict]:
    cached = _names_cache.get(_NAMES_TTL)
    if cached is not None:
        return cached
    data = await fetch_json(_VESSELS_URL, headers={"Accept-Encoding": "gzip"})
    names: dict[int, dict] = {}
    if isinstance(data, list):
        for v in data:
            names[v.get("mmsi")] = {"name": v.get("name") or "", "ship_type": v.get("shipType") or 0}
    _names_cache.set(names)
    return names


async def fetch_vessels() -> list[VesselSnapshot]:
    """Return AIS vessel snapshots (Digitraffic / Nordic-Baltic only — see module docstring)."""
    cached = _loc_cache.get(_LOC_TTL)
    if cached is not None:
        return cached

    names = await _fetch_names()
    geojson = await fetch_json(_LOCATIONS_URL, headers={"Accept-Encoding": "gzip"}, timeout=20.0)
    if not geojson:
        return _loc_cache.stale or []

    vessels: list[VesselSnapshot] = []
    for f in geojson.get("features", []) or []:
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates")
        if not coords or len(coords) < 2 or coords[0] is None or coords[1] is None:
            continue
        mmsi = p.get("mmsi")
        info = names.get(mmsi, {})
        heading = p.get("heading")
        cog = p.get("cog") or 0
        vessels.append(
            VesselSnapshot(
                mmsi=mmsi,
                name=info.get("name") or f"MMSI-{mmsi}",
                latitude=float(coords[1]),
                longitude=float(coords[0]),
                sog=float(p.get("sog") or 0),
                cog=float(heading if heading is not None and heading < 360 else cog),
                ship_type=int(info.get("ship_type") or 0),
                nav_status=int(p.get("navStat") or 0),
            )
        )

    _loc_cache.set(vessels)
    return vessels
