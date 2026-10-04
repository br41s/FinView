"""The country an event is in, read from what the source already says.

Three vocabularies, one slug: GDELT's export writes FIPS 10-4 (where "SP" is
Spain and "CH" is China), GDACS writes ISO3, and a USGS ``place`` is a sentence
that ends in the country. None of it comes from geometry, so the traps are all
in the names.
"""

from collections import Counter

import pytest

from backend.services.geo import countries
from backend.services.geo.countries import (
    COUNTRIES,
    COUNTRY_ETF,
    INSTRUMENT_COUNTRY,
    country_from_fips,
    country_from_iso3,
    country_from_place,
    country_name,
    country_phrase,
)
from backend.services.geo.ingest.ofac import COUNTRY_SLUGS
from backend.services.geo.rules import INSTRUMENT_BREADTH, INSTRUMENT_TRADABILITY


# ── USGS place strings (all taken from the live feed) ─────────────────


@pytest.mark.parametrize(
    "place,slug",
    [
        ("39 km WSW of Tambolaka, Indonesia", "indonesia"),
        ("38 km WSW of Palimbang, Philippines", "philippines"),
        ("21 km ESE of Feke, Turkey", "turkey"),
        ("Volcano Islands, Japan region", "japan"),
        ("off the east coast of Honshu, Japan", "japan"),
        ("near the coast of central Chile", "chile"),
        ("Philippine Islands region", "philippines"),
        ("Peru-Brazil border region", "peru"),  # the first country named
        ("12 km N of Hualien City, Taiwan", "taiwan"),
    ],
)
def test_a_place_ends_in_its_country(place, slug):
    assert country_from_place(place) == slug


@pytest.mark.parametrize(
    "place",
    [
        "10 km N of Truth or Consequences, New Mexico",  # a state, not Mexico
        "Gulf of Mexico",
        "West Chile Rise",  # a mid-ocean ridge a thousand km offshore
        "South China Sea",
        "East China Sea",
        "Sea of Japan",
        "Gulf of Thailand",
        "south of the Fiji Islands",  # a country with no market here
        "80 km ENE of Tadine, New Caledonia",
        "",
        None,
    ],
)
def test_a_name_that_is_not_the_country_resolves_to_nothing(place):
    assert country_from_place(place) is None


def test_only_the_last_part_is_read_because_towns_are_named_after_countries():
    assert country_from_place("5 km S of Chile Chico, Argentina") == "argentina"
    assert country_from_place("3 km W of Italy, Texas") is None


# ── GDELT (FIPS) and GDACS (ISO3) ─────────────────────────────────────


def test_fips_is_not_iso():
    assert country_from_fips("SP") == "spain"
    assert country_from_fips("CH") == "china"  # ISO "CH" is Switzerland
    assert country_from_fips("SZ") == "switzerland"
    assert country_from_fips("AS") == "australia"  # ISO "AS" is American Samoa
    assert country_from_fips("RP") == "philippines"
    assert country_from_fips(" ja ") == "japan"
    assert country_from_fips("ZZ") is None
    assert country_from_fips("") is None and country_from_fips(None) is None


def test_an_event_is_attributed_only_when_it_names_one_country():
    assert country_from_iso3(("THA",)) == "thailand"
    assert country_from_iso3(["mex"]) == "mexico"
    # A typhoon across three countries: which one it hit hardest is not in the feed.
    assert country_from_iso3(("PHL", "CHN", "JPN")) is None
    assert country_from_iso3(("NPL",)) is None  # no market listed for Nepal
    assert country_from_iso3(()) is None and country_from_iso3(None) is None


# ── The table itself ──────────────────────────────────────────────────


def test_every_code_and_every_etf_names_one_country():
    for field in ("slug", "fips", "iso3"):
        dupes = [k for k, n in Counter(getattr(c, field) for c in COUNTRIES).items() if n > 1]
        assert not dupes, f"duplicate {field}: {dupes}"
    etfs = [c.etf for c in COUNTRIES if c.etf]
    assert len(etfs) == len(set(etfs)) == len(COUNTRY_ETF)


def test_every_bound_instrument_is_in_the_universe_and_points_at_a_listed_country():
    assert set(INSTRUMENT_COUNTRY) <= set(INSTRUMENT_BREADTH)
    assert set(INSTRUMENT_COUNTRY) <= set(INSTRUMENT_TRADABILITY)
    assert set(INSTRUMENT_COUNTRY.values()) <= {c.slug for c in COUNTRIES}
    for slug, etf in COUNTRY_ETF.items():
        assert INSTRUMENT_COUNTRY[etf] == slug
        assert INSTRUMENT_BREADTH[etf] == "national"


def test_the_older_country_funds_keep_the_classification_they_had():
    """The table's default route must not overwrite what rules.py wrote by hand."""
    assert INSTRUMENT_TRADABILITY["TUR"][0] == "not_tradable"
    assert INSTRUMENT_TRADABILITY["EWZ"] == ("options_only", "IBZL (iShares MSCI Brazil UCITS)")
    assert INSTRUMENT_TRADABILITY["EPHE"][0] == "not_tradable"  # lists no options at all


def test_slugs_are_the_ones_the_country_rule_atom_already_reads():
    """`country=brazil` in a rule and a Brazilian event here must be the same word."""
    shared = {c.slug for c in COUNTRIES} & set(COUNTRY_SLUGS)
    assert {"brazil", "mexico", "japan", "germany", "turkey", "india", "china", "taiwan",
            "indonesia", "malaysia", "singapore", "switzerland", "united_kingdom"} <= shared


def test_the_ofac_name_table_was_not_extended():
    """`ofac._country_of` takes the earliest name: a new entry re-attributes designations."""
    assert len(COUNTRY_SLUGS) == 35
    assert not hasattr(countries, "COUNTRY_SLUGS")


def test_names_read_right_in_a_sentence():
    assert country_name("philippines") == "Philippines"
    assert country_phrase("philippines") == "the Philippines"
    assert country_phrase("chile") == "Chile"
    assert country_name("russia") == "Russia"  # not in the table: reads as itself
    assert country_name(None) == "" and country_phrase(None) == ""
