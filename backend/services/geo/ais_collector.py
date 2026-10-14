"""Global AIS vessel collector (aisstream.io WebSocket) — the deferred maritime piece.

Runs a long-lived WebSocket in a dedicated daemon thread with its own asyncio loop,
accumulating live vessel positions for the rule chokepoints into an in-memory store
(thread-safe). The ingest layer reads a snapshot each cycle.

Lifecycle note (Cloud Run): a persistent WS only stays warm while the instance is
alive. On scale-to-zero the collector dies and restarts cold (losing accumulated
history) — set min-instances >= 1 for full coverage. Without AISSTREAM_KEY it never
starts and maritime falls back to Digitraffic. State is in-memory only (never persisted).
"""

import asyncio
import json
import logging
import threading
import time

import aiohttp

from backend.config import settings

from .chokepoints import CHOKEPOINTS
from .ingest.types import VesselSnapshot

logger = logging.getLogger(__name__)

_WS_URL = "wss://stream.aisstream.io/v0/stream"
_VESSEL_EXPIRY_S = 10 * 60
_RECONNECT_DELAY_S = 5

_lock = threading.Lock()
_vessels: dict[int, dict] = {}  # mmsi -> {lat, lon, sog, cog, ship_type, nav_status, name, ts}
_names: dict[int, dict] = {}  # mmsi -> {name, ship_type}
_thread: threading.Thread | None = None
_started = False
_connected = False


def _bounding_boxes() -> list:
    """aisstream BoundingBoxes: [[[latMin, lonMin], [latMax, lonMax]], ...] per chokepoint."""
    return [
        [[cp.lat_min, cp.lon_min], [cp.lat_max, cp.lon_max]] for cp in CHOKEPOINTS
    ]


def _process(msg: dict) -> None:
    if msg.get("error"):
        logger.warning("AIS stream error: %s", msg["error"])
        return
    mtype = msg.get("MessageType")
    meta = msg.get("MetaData") or {}
    mmsi = meta.get("MMSI")
    if not mmsi:
        return

    if meta.get("ShipName"):
        existing = _names.get(mmsi, {})
        _names[mmsi] = {"name": meta["ShipName"].strip(), "ship_type": existing.get("ship_type", 0)}

    if mtype == "ShipStaticData":
        data = (msg.get("Message") or {}).get("ShipStaticData")
        if data:
            _names[mmsi] = {"name": (data.get("Name") or "").strip(), "ship_type": data.get("Type", 0)}
        return

    lat = lon = None
    sog = cog = 0.0
    nav_status = 0
    if mtype == "PositionReport":
        d = (msg.get("Message") or {}).get("PositionReport")
        if not d:
            return
        lat, lon = d.get("Latitude"), d.get("Longitude")
        sog, cog = d.get("Sog", 0) or 0, d.get("Cog", 0) or 0
        nav_status = d.get("NavigationalStatus", 0) or 0
    elif mtype == "StandardClassBPositionReport":
        d = (msg.get("Message") or {}).get("StandardClassBPositionReport")
        if not d:
            return
        lat, lon = d.get("Latitude"), d.get("Longitude")
        sog, cog = d.get("Sog", 0) or 0, d.get("Cog", 0) or 0
    else:
        lat, lon = meta.get("latitude"), meta.get("longitude")

    if lat is None or lon is None or lat == 0 or lon == 0:
        return
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return

    info = _names.get(mmsi, {})
    with _lock:
        _vessels[mmsi] = {
            "lat": lat, "lon": lon, "sog": sog, "cog": cog,
            "ship_type": info.get("ship_type", 0),
            "name": info.get("name") or (meta.get("ShipName") or "").strip() or f"MMSI-{mmsi}",
            "nav_status": nav_status,
            "ts": time.monotonic(),
        }


def _purge() -> None:
    cutoff = time.monotonic() - _VESSEL_EXPIRY_S
    with _lock:
        stale = [m for m, v in _vessels.items() if v["ts"] < cutoff]
        for m in stale:
            del _vessels[m]


async def _run_forever(api_key: str) -> None:
    global _connected
    sub = {
        "APIKey": api_key,
        "BoundingBoxes": _bounding_boxes(),
        "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ShipStaticData"],
    }
    while True:
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.ws_connect(_WS_URL, heartbeat=30) as ws,
            ):
                await ws.send_str(json.dumps(sub))
                _connected = True
                logger.info("AIS stream connected (%d chokepoint boxes)", len(CHOKEPOINTS))
                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        try:
                            _process(json.loads(raw.data))
                        except (ValueError, KeyError):
                            continue
                    elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        except Exception:
            logger.warning("AIS stream connection failed", exc_info=True)
        finally:
            _connected = False
        await asyncio.sleep(_RECONNECT_DELAY_S)


def _thread_main(api_key: str) -> None:
    try:
        asyncio.run(_run_forever(api_key))
    except Exception:
        logger.exception("AIS collector thread crashed")


def start() -> None:
    """Idempotently start the collector (no-op without AISSTREAM_KEY)."""
    global _thread, _started
    if _started:
        return
    api_key = settings.aisstream_key
    if not api_key:
        logger.info("AISSTREAM_KEY not set — AIS collector disabled (Digitraffic fallback)")
        _started = True  # don't re-check every call
        return
    _started = True
    _thread = threading.Thread(target=_thread_main, args=(api_key,), name="ais-collector", daemon=True)
    _thread.start()
    logger.info("AIS collector started")


def is_connected() -> bool:
    return _connected


def vessel_count() -> int:
    with _lock:
        return len(_vessels)


def get_vessels() -> list[VesselSnapshot]:
    """Return a snapshot of currently-tracked vessels (purges stale first)."""
    _purge()
    with _lock:
        return [
            VesselSnapshot(
                mmsi=mmsi,
                name=v["name"],
                latitude=v["lat"],
                longitude=v["lon"],
                sog=v["sog"],
                cog=v["cog"],
                ship_type=v["ship_type"],
                nav_status=v["nav_status"],
            )
            for mmsi, v in _vessels.items()
        ]
