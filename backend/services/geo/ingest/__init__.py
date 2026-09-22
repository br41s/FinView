"""Geo ingest layer — async clients for the 8 signal sources.

Each ``fetch_*`` coroutine is self-contained: it caches with a per-source TTL,
degrades to its last good payload (or empty) on failure, and never raises into
the cycle. ``fetch_all_sources()`` fans them out with asyncio.gather (the Python
analog of WorldHawk's Promise.allSettled).
"""

import asyncio
import logging

from .events import fetch_events
from .fedreg import fetch_fedreg
from .fires import fetch_fires
from .flights import fetch_flights
from .gdelt import fetch_gdelt
from .maritime import fetch_vessels
from .meteo import fetch_meteo
from .ofac import fetch_ofac
from .seismic import fetch_seismic
from .types import (
    FedRegDocument,
    FireHotspot,
    FlightData,
    GdeltEvent,
    MeteoPoint,
    NaturalEvent,
    OfacAction,
    OfacEntry,
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
    "fetch_vessels",
    "fetch_ofac",
    "fetch_fedreg",
    "SourceBundle",
    "SeismicEvent",
    "NaturalEvent",
    "FireHotspot",
    "MeteoPoint",
    "FlightData",
    "GdeltEvent",
    "VesselSnapshot",
    "OfacAction",
    "OfacEntry",
    "FedRegDocument",
]


async def fetch_all_sources() -> SourceBundle:
    """Fetch all 9 sources concurrently. Per-source failures yield empty lists."""
    results = await asyncio.gather(
        fetch_seismic(),
        fetch_events(),
        fetch_fires(),
        fetch_meteo(),
        fetch_flights(),
        fetch_gdelt(),
        fetch_vessels(),
        fetch_ofac(),
        fetch_fedreg(),
        return_exceptions=True,
    )
    keys = (
        "earthquakes", "events", "fires", "meteo",
        "flights", "gdelt", "vessels", "ofac", "fedreg",
    )
    bundle = SourceBundle()
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("geo source %r failed: %s", key, result)
            continue
        setattr(bundle, key, result)
    return bundle
