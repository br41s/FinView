"""Normalized source-data shapes for the geo ingest layer.

One dataclass per raw signal source, mirroring the typed outputs of WorldHawk's
Next.js route handlers. The sentinel/analyst layer (P4) consumes these and emits
the unified financial events the rule matcher works on.
"""

from dataclasses import dataclass, field


@dataclass
class SeismicEvent:
    """USGS earthquake."""

    id: str
    magnitude: float
    place: str
    time: int  # epoch milliseconds
    latitude: float
    longitude: float
    depth: float = 0.0
    url: str = ""


@dataclass
class NaturalEvent:
    """EONET / GDACS natural event (cyclone, volcano, flood, drought, storm, iceberg)."""

    id: str
    title: str
    category: str  # cyclone|volcano|flood|drought|storm|iceberg|other
    latitude: float
    longitude: float
    date: str
    source: str  # EONET | GDACS
    severity: str | None = None  # red|orange|green|None
    url: str = ""


@dataclass
class FireHotspot:
    """NASA FIRMS VIIRS hotspot."""

    latitude: float
    longitude: float
    brightness: float
    frp: float  # fire radiative power
    confidence: str  # h|n|l
    acq_date: str = ""
    acq_time: str = ""
    daynight: str = ""
    satellite: str = ""


@dataclass
class MeteoPoint:
    """Windy GFS point forecast (one grid node)."""

    latitude: float
    longitude: float
    temperature: float  # °C
    wind_speed: float  # km/h
    wind_direction: int  # degrees
    wind_gust: float  # km/h
    precipitation: float  # mm / 3h
    pressure: int  # hPa


@dataclass
class FlightData:
    """OpenSky aircraft state vector with military classification."""

    icao24: str
    callsign: str
    origin_country: str
    latitude: float
    longitude: float
    altitude: float
    velocity: float
    heading: float
    vertical_rate: float
    on_ground: bool
    squawk: str | None
    is_military: bool
    aircraft_type: str  # military|commercial|unknown


@dataclass
class GdeltEvent:
    """GDELT 2.0 Doc-API derived geopolitical event.

    No ``num_mentions``/``num_sources``: the Doc API's ``artlist`` mode does not
    return them, and the placeholder constants that used to stand in for them
    sat below the sentinel's own floors, so every article was dropped.
    """

    id: str
    title: str
    event_code: str
    goldstein_scale: float
    avg_tone: float
    latitude: float
    longitude: float
    actor1: str
    actor2: str
    date_added: str
    source_url: str


@dataclass
class AcledEvent:
    """ACLED expert-coded armed-conflict / protest event."""

    id: str
    event_date: str
    event_type: str
    sub_event_type: str
    actor1: str
    actor2: str
    country: str
    admin1: str
    location: str
    latitude: float
    longitude: float
    fatalities: int
    notes: str
    source: str
    source_scale: str
    tags: str


@dataclass
class VesselSnapshot:
    """AIS vessel position snapshot (maritime chokepoint analysis)."""

    mmsi: int
    name: str
    latitude: float
    longitude: float
    sog: float  # speed over ground (knots)
    cog: float  # course over ground
    ship_type: int
    nav_status: int = 0


@dataclass
class SourceBundle:
    """Result of one ingest cycle — all sources gathered together."""

    earthquakes: list[SeismicEvent] = field(default_factory=list)
    events: list[NaturalEvent] = field(default_factory=list)
    fires: list[FireHotspot] = field(default_factory=list)
    meteo: list[MeteoPoint] = field(default_factory=list)
    flights: list[FlightData] = field(default_factory=list)
    gdelt: list[GdeltEvent] = field(default_factory=list)
    acled: list[AcledEvent] = field(default_factory=list)
    vessels: list[VesselSnapshot] = field(default_factory=list)
