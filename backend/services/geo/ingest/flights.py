"""OpenSky aircraft states over strategic regions → FlightData list.

WorldHawk's route was viewport-driven (adsb.fi primary, OpenSky fallback). The
server-side geo cycle has no viewport, so we scan the fixed set of regions the
airspace_closure / military_surge rules care about, via OpenSky's bounding-box
``states/all`` query, and dedup by icao24.

Auth is optional but close to mandatory in practice: anonymous OpenSky is rate-limited
hard enough that the source reads as "no flights" most cycles, which is
indistinguishable from a quiet sky. OpenSky issues **OAuth2 client credentials**
(client id + secret), exchanged here for a bearer token; the older
username/password basic auth is kept as a fallback for accounts that still have it.
"""

import asyncio
import logging
import time

from backend.config import settings

from .base import TTLCache, fetch_json
from .types import FlightData

logger = logging.getLogger(__name__)

_OPENSKY_API = "https://opensky-network.org/api/states/all"
# Keycloak client-credentials endpoint. If OpenSky moves it, this is the one line
# to change — a wrong URL degrades to anonymous rather than breaking the cycle.
_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)
_TOKEN_MARGIN = 60  # refresh this many seconds before the token actually expires
_DEFAULT_TOKEN_TTL = 1800  # OpenSky's tokens last ~30 min; used if expires_in is absent
_CACHE_TTL = 60  # 1 minute
_cache = TTLCache()
# (access_token, monotonic deadline). Process-local, like every other geo cache.
_token: tuple[str, float] | None = None

# Regions referenced by air-* rules: (lamin, lamax, lomin, lomax).
_SCAN_BOXES: dict[str, tuple[float, float, float, float]] = {
    "middle_east_oil": (12, 38, 35, 60),
    "ukraine_black_sea": (41, 52, 28, 42),
    "taiwan": (21, 26, 119, 123),
    "korean_peninsula": (33, 43, 124, 132),
    "iran": (25, 40, 44, 63),
    "northern_europe": (50, 72, -12, 30),
    "south_china_sea": (4, 24, 105, 121),
}

_MILITARY_PREFIXES = (
    "RCH", "EVAC", "REACH", "JAKE", "DUKE", "TOPCAT", "NCHO", "GORDO", "SPAR",
    "SAM", "EXEC", "VENUS", "MARKY", "HAVOC", "SHADY", "BISON", "IRON", "BOLT",
    "KNIFE", "BLADE", "DOOM", "VIPER", "GHOST", "RAGE", "POLO", "JEDI", "ETHYL",
    "CNV", "NAVY", "RRR", "ASCOT", "TARTN", "NATO", "MMF", "NAEW", "GAF", "FAF",
    "CTM", "COTAM", "FRAF", "IAM", "AME", "BRAVO", "CFC", "CANAF", "ASY", "TUAF",
    "IFC", "JASDF", "ROKAF", "FORTE", "LAGR", "HOMER", "REAPER", "SIGINT", "DRAGON",
)
_MILITARY_ICAO_RANGES: tuple[tuple[int, int], ...] = (
    (0xADF7C8, 0xAFFFFF), (0x3F4000, 0x3FFFFF), (0x43C000, 0x43FFFF),
    (0x3A8000, 0x3AFFFF), (0x33FF00, 0x33FFFF), (0x738000, 0x73FFFF),
    (0x400000, 0x4003FF), (0xE40000, 0xE40FFF), (0x7C0000, 0x7C0FFF),
    (0xC20000, 0xC20FFF),
)


def _is_military_squawk(squawk: str | None) -> bool:
    if not squawk:
        return False
    try:
        return int(squawk) == 7777
    except ValueError:
        return False


def _is_military_icao(icao24: str) -> bool:
    try:
        hex_val = int(icao24, 16)
    except ValueError:
        return False
    return any(lo <= hex_val <= hi for lo, hi in _MILITARY_ICAO_RANGES)


def _is_military_callsign(callsign: str) -> bool:
    trimmed = callsign.strip().upper()
    return bool(trimmed) and any(trimmed.startswith(p) for p in _MILITARY_PREFIXES)


def _transform(states: list[list]) -> list[FlightData]:
    out: list[FlightData] = []
    for s in states:
        if len(s) < 15:
            continue
        lon, lat = s[5], s[6]
        if lon is None or lat is None:
            continue
        icao24 = (s[0] or "") if isinstance(s[0], str) else ""
        callsign = (s[1] or "").strip() if isinstance(s[1], str) else ""
        altitude = s[13] if s[13] is not None else (s[7] or 0)
        squawk = s[14] if isinstance(s[14], str) else None
        velocity = s[9] or 0
        is_mil = (
            _is_military_callsign(callsign)
            or _is_military_squawk(squawk)
            or _is_military_icao(icao24)
        )
        if is_mil:
            aircraft_type = "military"
        elif altitude > 8000 and velocity > 150:
            aircraft_type = "commercial"
        else:
            aircraft_type = "unknown"
        out.append(
            FlightData(
                icao24=icao24,
                callsign=callsign,
                origin_country=s[2] or "",
                latitude=float(lat),
                longitude=float(lon),
                altitude=float(altitude),
                velocity=float(velocity),
                heading=float(s[10] or 0),
                vertical_rate=float(s[11] or 0),
                on_ground=bool(s[8]),
                squawk=squawk,
                is_military=is_mil,
                aircraft_type=aircraft_type,
            )
        )
    return out


async def _access_token() -> str | None:
    """OAuth2 client-credentials bearer token, cached until shortly before expiry.

    Returns None whenever credentials are absent or the exchange doesn't yield a
    usable token — the caller then falls back to legacy basic auth or anonymous.
    A token failure must degrade the source, never raise into the cycle.
    """
    global _token
    if not (settings.opensky_client_id and settings.opensky_client_secret):
        return None
    if _token is not None and time.monotonic() < _token[1]:
        return _token[0]

    body = await fetch_json(
        _TOKEN_URL,
        method="POST",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.opensky_client_id,
            "client_secret": settings.opensky_client_secret,
        },
    )
    # A 200 is not a token: validate the shape before trusting it (the same rule
    # that zone_scorer learned the hard way).
    if not isinstance(body, dict):
        logger.warning("OpenSky token exchange failed — falling back to anonymous")
        return None
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        logger.warning(
            "OpenSky token response carried no access_token (keys=%s)", sorted(body)
        )
        return None

    try:
        ttl = float(body.get("expires_in") or _DEFAULT_TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = _DEFAULT_TOKEN_TTL
    _token = (token, time.monotonic() + max(ttl - _TOKEN_MARGIN, 30))
    return token


async def _fetch_box(
    box: tuple[float, float, float, float], auth, headers: dict | None = None
) -> list[FlightData]:
    lamin, lamax, lomin, lomax = box
    params = {"lamin": lamin, "lamax": lamax, "lomin": lomin, "lomax": lomax}
    data = await fetch_json(_OPENSKY_API, params=params, auth=auth, headers=headers)
    if not data:
        return []
    return _transform(data.get("states") or [])


async def fetch_flights() -> list[FlightData]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    headers: dict | None = None
    auth = None
    token = await _access_token()
    if token:
        headers = {"Authorization": f"Bearer {token}"}
    elif settings.opensky_username and settings.opensky_password:
        auth = (settings.opensky_username, settings.opensky_password)

    settled = await asyncio.gather(
        *(_fetch_box(box, auth, headers) for box in _SCAN_BOXES.values()),
        return_exceptions=True,
    )

    # Dedup by icao24 (regions can overlap / aircraft cross boundaries).
    by_icao: dict[str, FlightData] = {}
    for r in settled:
        if isinstance(r, list):
            for flight in r:
                if flight.icao24:
                    by_icao[flight.icao24] = flight

    flights = list(by_icao.values())
    if not flights and _cache.stale is not None:
        return _cache.stale

    _cache.set(flights)
    return flights
