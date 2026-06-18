"""Geo ingest layer — async clients for the 8 signal sources.

Each ``fetch_*`` coroutine is self-contained: it caches with a per-source TTL,
degrades to its last good payload (or empty) on failure, and never raises into
the cycle. ``fetch_all_sources()`` fans them out with asyncio.gather (the Python
analog of WorldHawk's Promise.allSettled).
"""

import asyncio
import logging

from .acled import fetch_acled
from .events import fetch_events
from .fires import fetch_fires
from .flights import fetch_flights
from .gdelt import fetch_gdelt
from .maritime import fetch_vessels
from .meteo import fetch_meteo
from .seismic import fetch_seismic
from .types import (
    AcledEvent,
    FireHotspot,
    FlightData,
    GdeltEvent,
    MeteoPoint,
    NaturalEvent,
    SeismicEvent,
    SourceBundle,
    VesselSnapshot,
)

logger = logging.getLogger(__name__)

__all__ = [
    "fetch_all_sources",
    "fetch_seismic",
    "fetch_events",
    "fetch_fires",
    "fetch_meteo",
    "fetch_flights",
    "fetch_gdelt",
    "fetch_acled",
    "fetch_vessels",
    "SourceBundle",
    "SeismicEvent",
    "NaturalEvent",
    "FireHotspot",
    "MeteoPoint",
    "FlightData",
    "GdeltEvent",
    "AcledEvent",
    "VesselSnapshot",
]


async def fetch_all_sources() -> SourceBundle:
    """Fetch all 8 sources concurrently. Per-source failures yield empty lists."""
    results = await asyncio.gather(
        fetch_seismic(),
        fetch_events(),
        fetch_fires(),
        fetch_meteo(),
        fetch_flights(),
        fetch_gdelt(),
        fetch_acled(),
        fetch_vessels(),
        return_exceptions=True,
    )
    keys = (
        "earthquakes", "events", "fires", "meteo",
        "flights", "gdelt", "acled", "vessels",
    )
    bundle = SourceBundle()
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("geo source %r failed: %s", key, result)
            continue
        setattr(bundle, key, result)
    return bundle
