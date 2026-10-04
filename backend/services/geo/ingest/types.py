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
    # PAGER's estimate of the damage (green | yellow | orange | red), None until
    # USGS has computed it — usually within the hour, and only for larger quakes.
    alert: str | None = None


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
    # ISO3 codes of the countries GDACS lists as affected; EONET names none.
    countries: tuple[str, ...] = ()


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
    """One row of a GDELT 2.0 ``export.CSV`` batch (see ``ingest/gdelt.py``).

    Every field here is read off the export, not inferred: ``goldstein_scale``
    is CAMEO's own conflict/cooperation weight for the coded ``event_code``
    (constant per code, but per-event because the code is), and the mention
    counts and coordinates are the event's, not a query's. The Doc API this
    replaced supplied none of them, which is why the sentinel's mention floors
    and its red severity band had to be disabled while it was the source.

    ``title`` is synthesized ("Actor1 → Actor2: CAMEO description") — the export
    carries no headline, only ``source_url``.
    """

    id: str
    title: str
    event_code: str
    event_root_code: str
    quad_class: int
    goldstein_scale: float
    num_mentions: int
    num_sources: int
    num_articles: int
    avg_tone: float
    latitude: float
    longitude: float
    location: str
    actor1: str
    actor2: str
    date_added: str
    source_url: str
    # ActionGeo_CountryCode — FIPS 10-4, not ISO: "SP" is Spain, "CH" is China.
    country_code: str = ""


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
class OfacEntry:
    """One SDN list change on an OFAC recent-action page."""

    name: str
    kind: str  # individual|entity|vessel|aircraft
    programs: tuple[str, ...]  # bracketed tags, e.g. ("IRAN", "IRAN-EO13902")
    country: str | None  # slug from ingest.ofac.COUNTRY_SLUGS, None when unlisted
    action: str  # added|removed


@dataclass
class OfacAction:
    """One dated OFAC recent action (`/recent-actions/YYYYMMDD`)."""

    date: str  # YYYYMMDD
    url: str
    title: str
    entries: list[OfacEntry] = field(default_factory=list)


@dataclass
class FedRegDocument:
    """One Federal Register document that is a policy action (see ingest.fedreg)."""

    document_number: str
    publication_date: str  # YYYY-MM-DD
    title: str
    abstract: str
    url: str
    agency: str  # bis|ustr
    category: str  # sanctions|trade_dispute
    countries: tuple[str, ...]  # slugs from ingest.ofac.COUNTRY_SLUGS, in text order


@dataclass
class SourceBundle:
    """Result of one ingest cycle — all sources gathered together."""

    earthquakes: list[SeismicEvent] = field(default_factory=list)
    events: list[NaturalEvent] = field(default_factory=list)
    fires: list[FireHotspot] = field(default_factory=list)
    meteo: list[MeteoPoint] = field(default_factory=list)
    flights: list[FlightData] = field(default_factory=list)
    gdelt: list[GdeltEvent] = field(default_factory=list)
    vessels: list[VesselSnapshot] = field(default_factory=list)
    ofac: list[OfacAction] = field(default_factory=list)
    fedreg: list[FedRegDocument] = field(default_factory=list)
