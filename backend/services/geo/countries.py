"""Country layer — which country an event is in, and which instruments are that country's.

An event used to know only which hand-drawn region box it fell in, and the boxes
were drawn for commodity and chokepoint theses: an earthquake outside every box
was dropped before a rule saw it, and seven countries had an instrument of their
own. This table is what lets an event that matters to one country and to nobody
else relate to that country's market.

The country comes from what the sources already publish, never from geometry:
GDELT's export carries ``ActionGeo_CountryCode`` (FIPS 10-4), a USGS ``place``
ends in the country — including the offshore quakes a polygon would miss — and
GDACS lists the countries an event affects (ISO3).

Slugs are the vocabulary ``ingest/ofac.COUNTRY_SLUGS`` already uses, because the
``country=`` rule atom reads them. That table is deliberately **not** extended:
``ofac._country_of`` takes the earliest name it finds, so every name added there
can re-attribute an SDN designation.

Static data and pure functions: no I/O, no imports from the rest of geo.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    slug: str
    name: str
    fips: str  # GDELT ActionGeo_CountryCode — FIPS 10-4, not ISO ("SP" is Spain)
    iso3: str  # GDACS affectedcountries
    # US-listed single-country ETF, or None for a country that only hosts
    # instruments (the US: its insurers and airlines are bound to it, but its
    # market is not a "national" leg of anything).
    etf: str | None = None
    # Tradability of the ETF for a Spanish retail account (see
    # rules.INSTRUMENT_TRADABILITY) and the nearest UCITS family. A US ETF has no
    # PRIIPs KID, so the only route is its options at IBKR — where there are any.
    route: str = "options_only"
    alternate: str = ""
    aliases: tuple[str, ...] = ()  # other spellings a USGS place string uses


# The ETFs added on 2026-10-04 were each checked that day: all return 5-minute
# bars on Yahoo. `route` is options_only where the two nearest expiries held more
# than ~1000 contracts of open interest and not_tradable otherwise (EPHE and EIS
# list no options at all). ENZL (New Zealand) was left out: 69 bars in five
# sessions, too thin for the intraday checkpoints. The seven older ones (EWJ,
# EWG, EWY, EWZ, FXI, INDA, TUR) keep the classification rules.py gave them.
COUNTRIES: tuple[Country, ...] = (
    # Americas
    Country("united_states", "United States", "US", "USA"),
    Country("canada", "Canada", "CA", "CAN", "EWC", alternate="iShares MSCI Canada UCITS"),
    Country("mexico", "Mexico", "MX", "MEX", "EWW", alternate="iShares MSCI Mexico Capped UCITS"),
    Country("brazil", "Brazil", "BR", "BRA", "EWZ"),
    Country("chile", "Chile", "CI", "CHL", "ECH"),
    Country("peru", "Peru", "PE", "PER", "EPU", "not_tradable"),
    Country("argentina", "Argentina", "AR", "ARG", "ARGT"),
    # Europe
    Country("united_kingdom", "United Kingdom", "UK", "GBR", "EWU",
            alternate="iShares Core FTSE 100 UCITS"),
    Country("germany", "Germany", "GM", "DEU", "EWG"),
    Country("france", "France", "FR", "FRA", "EWQ", "not_tradable", "Amundi CAC 40 UCITS"),
    Country("italy", "Italy", "IT", "ITA", "EWI", alternate="iShares FTSE MIB UCITS"),
    Country("spain", "Spain", "SP", "ESP", "EWP", "not_tradable", "Amundi IBEX 35 UCITS"),
    Country("switzerland", "Switzerland", "SZ", "CHE", "EWL", "not_tradable"),
    Country("netherlands", "Netherlands", "NL", "NLD", "EWN", "not_tradable", "iShares AEX UCITS"),
    Country("sweden", "Sweden", "SW", "SWE", "EWD", "not_tradable",
            "iShares OMX Stockholm Capped UCITS"),
    Country("poland", "Poland", "PL", "POL", "EPOL", alternate="iShares MSCI Poland UCITS"),
    Country("greece", "Greece", "GR", "GRC", "GREK", "not_tradable", "Amundi MSCI Greece UCITS"),
    Country("turkey", "Turkey", "TU", "TUR", "TUR", aliases=("Türkiye", "Turkiye")),
    # Middle East and Africa
    Country("israel", "Israel", "IS", "ISR", "EIS", "not_tradable"),
    Country("saudi_arabia", "Saudi Arabia", "SA", "SAU", "KSA", "not_tradable",
            "iShares MSCI Saudi Arabia Capped UCITS"),
    Country("south_africa", "South Africa", "SF", "ZAF", "EZA", "not_tradable",
            "iShares MSCI South Africa UCITS"),
    # Asia-Pacific
    Country("japan", "Japan", "JA", "JPN", "EWJ"),
    Country("south_korea", "South Korea", "KS", "KOR", "EWY"),
    Country("china", "China", "CH", "CHN", "FXI"),
    Country("taiwan", "Taiwan", "TW", "TWN", "EWT", alternate="iShares MSCI Taiwan UCITS"),
    Country("hong_kong", "Hong Kong", "HK", "HKG", "EWH", "not_tradable"),
    Country("india", "India", "IN", "IND", "INDA"),
    Country("indonesia", "Indonesia", "ID", "IDN", "EIDO", alternate="HSBC MSCI Indonesia UCITS"),
    Country("philippines", "Philippines", "RP", "PHL", "EPHE", "not_tradable",
            "Xtrackers MSCI Philippines UCITS", aliases=("Philippine Islands",)),
    Country("thailand", "Thailand", "TH", "THA", "THD", "not_tradable",
            "Xtrackers MSCI Thailand UCITS"),
    Country("vietnam", "Vietnam", "VM", "VNM", "VNM", "not_tradable",
            "Xtrackers Vietnam Swap UCITS", aliases=("Viet Nam",)),
    Country("malaysia", "Malaysia", "MY", "MYS", "EWM", "not_tradable",
            "Xtrackers MSCI Malaysia UCITS"),
    Country("singapore", "Singapore", "SN", "SGP", "EWS", "not_tradable",
            "Xtrackers MSCI Singapore UCITS"),
    Country("australia", "Australia", "AS", "AUS", "EWA", alternate="iShares MSCI Australia UCITS"),
)

COUNTRY_BY_SLUG: dict[str, Country] = {c.slug: c for c in COUNTRIES}
_BY_FIPS = {c.fips: c.slug for c in COUNTRIES}
_BY_ISO3 = {c.iso3: c.slug for c in COUNTRIES}

# A country's market: the one instrument a national event is read against.
COUNTRY_ETF: dict[str, str] = {c.slug: c.etf for c in COUNTRIES if c.etf}

# The local tier: companies whose revenue or assets sit inside one country — a
# domestic bank, a telecom, a utility, an airport operator, a miner with every
# mine there. Up to two per country, and US-listed on purpose: the +1h and +6h
# checkpoints are measured on the US session, and a Jakarta or Santiago listing
# would be read at a bar its own exchange never traded. Each returned 5-minute
# bars on 2026-10-04. A company with a large book abroad is not here (Japan's
# megabanks, Spain's banks, the global miners): bound to a country it does not
# depend on, it would teach the local template the wrong thing.
COUNTRY_LOCALS: dict[str, tuple[str, ...]] = {
    "mexico": ("PAC", "OMAB"),          # airport operators
    "brazil": ("BBD", "VIV"),           # Bradesco, Telefônica Brasil
    "chile": ("BCH", "ENIC"),           # Banco de Chile, Enel Chile
    "peru": ("BAP", "BVN"),             # Credicorp, Buenaventura
    "argentina": ("GGAL", "YPF"),       # Grupo Galicia, YPF
    "canada": ("BCE", "CM"),            # BCE, CIBC
    "united_kingdom": ("LYG", "NWG"),   # Lloyds, NatWest
    "turkey": ("TKC",),                 # Turkcell
    "india": ("HDB", "IBN"),            # HDFC Bank, ICICI Bank
    "indonesia": ("TLK",),              # Telkom Indonesia
    "philippines": ("PHI",),            # PLDT
    "south_korea": ("KB", "KT"),        # KB Financial, KT Corp
    "taiwan": ("CHT", "UMC"),           # Chunghwa Telecom, UMC
}

# Which country an instrument belongs to. An ETF belongs to its market; a company
# belongs to the country it is domiciled *and* operates in (the TSM precedent in
# rules.INSTRUMENT_BREADTH) — so Southern Copper (Peru and Mexico), Albemarle and
# the pan-European airlines are bound to nothing and stay available everywhere.
# This is the gate: an event may load its own country's instruments, never
# another's (see rules.allowed_symbols).
INSTRUMENT_COUNTRY: dict[str, str] = {
    **{etf: slug for slug, etf in COUNTRY_ETF.items()},
    **{symbol: slug for slug, symbols in COUNTRY_LOCALS.items() for symbol in symbols},
    "TSM": "taiwan", "TM": "japan", "005930.KS": "south_korea",
    "ANTO.L": "chile", "SQM": "chile", "FMG.AX": "australia",
    "MUV2.DE": "germany", "ALV.DE": "germany", "RWE.DE": "germany",
    "ALL": "united_states", "TRV": "united_states", "HIG": "united_states",
    "DAL": "united_states", "UAL": "united_states", "AAL": "united_states",
    "PCG": "united_states", "WY": "united_states",
}

# Names inside a USGS place that are not the country: a state, a sea, a ridge.
_PLACE_TRAPS = re.compile(
    r"New Mexico|Gulf of Mexico|Chile Rise|South China Sea|East China Sea|Sea of Japan"
    r"|Gulf of Thailand",
    re.IGNORECASE,
)
# Longest name first, so the alternation prefers "South Africa" to a shorter name
# starting at the same character; the search itself returns the leftmost match.
_NAMES = sorted(
    ((name, c.slug) for c in COUNTRIES for name in (c.name, *c.aliases)),
    key=lambda pair: -len(pair[0]),
)
_PLACE_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name, _ in _NAMES) + r")\b", re.IGNORECASE
)
_SLUG_BY_NAME = {name.lower(): slug for name, slug in _NAMES}


def country_from_place(place: str | None) -> str | None:
    """The country a USGS ``place`` names, or None.

    "39 km WSW of Tambolaka, Indonesia", "Volcano Islands, Japan region", "near
    the coast of central Chile". Only the last comma-separated part is read: the
    part before it is a town, and towns are named after countries ("Chile Chico,
    Argentina").
    """
    if not place:
        return None
    tail = _PLACE_TRAPS.sub(" ", place.rsplit(",", 1)[-1])
    m = _PLACE_RE.search(tail)
    return _SLUG_BY_NAME[m.group(1).lower()] if m else None


def country_from_fips(code: str | None) -> str | None:
    """Slug for a GDELT ``ActionGeo_CountryCode``, or None for a country not listed."""
    return _BY_FIPS.get((code or "").strip().upper())


def country_from_iso3(codes: tuple[str, ...] | list[str] | None) -> str | None:
    """Slug when an event names exactly one country, and that country is listed.

    A cyclone that GDACS lists against three countries is not attributed to the
    first of them: which one it hit hardest is not in the feed, and a guess here
    is a signal on the wrong market.
    """
    if not codes or len(codes) != 1:
        return None
    return _BY_ISO3.get(str(codes[0]).strip().upper())


def country_name(slug: str | None) -> str:
    """Display name for a slug; a slug this table does not list reads as itself."""
    if not slug:
        return ""
    known = COUNTRY_BY_SLUG.get(slug)
    return known.name if known else slug.replace("_", " ").title()


_WITH_ARTICLE = frozenset({"philippines", "netherlands", "united_states", "united_kingdom"})


def country_phrase(slug: str | None) -> str:
    """The name as it reads inside a sentence: "the Philippines", "Chile"."""
    name = country_name(slug)
    return f"the {name}" if slug in _WITH_ARTICLE else name
