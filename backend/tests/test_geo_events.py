"""GDACS through SEARCH, not MAP — and the countries it names.

``geteventlist/MAP`` started answering 400 "Eventtype is required." and nothing
noticed: the natural-events source counts EONET and GDACS together, and EONET
kept the number above zero. Without GDACS no natural event carried an alert
level, so nothing was ever "red". SEARCH takes the event types and a date
window in one request.
"""

import asyncio
import json
from datetime import date

from backend.services.geo.ingest import events


def _feature(**props):
    base = {
        "eventtype": "FL", "eventid": 1104169, "name": "Flood in Thailand",
        "alertlevel": "Orange", "iscurrent": "true", "fromdate": "2026-10-01T00:00:00",
        "url": {
            "geometry": "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventid=1104169",
            "report": "https://www.gdacs.org/report.aspx?eventid=1104169",
        },
        "affectedcountries": [{"iso2": "TH", "iso3": "THA", "countryname": "Thailand"}],
    }
    base.update(props)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [100.5, 13.7]},
            "properties": base}


def _payload(*features):
    return json.dumps({"type": "FeatureCollection", "features": list(features)})


def test_search_names_the_types_the_levels_and_an_activity_window():
    params = events._gdacs_params(date(2026, 10, 4))
    assert params == {
        "eventlist": "TC;FL;VO;DR",
        "alertlevel": "green;orange;red",
        "fromDate": "2026-10-01",
        "toDate": "2026-10-05",
    }


def test_an_event_carries_its_level_its_report_and_its_countries():
    (e,) = events._parse_gdacs(_payload(_feature()))
    assert (e.id, e.category, e.severity, e.source) == ("gdacs-1104169", "flood", "orange", "GDACS")
    assert (e.latitude, e.longitude) == (13.7, 100.5)
    # SEARCH nests the links; the report page is the one a reader can open.
    assert e.url == "https://www.gdacs.org/report.aspx?eventid=1104169"
    assert e.countries == ("THA",)


def test_a_cyclone_across_three_countries_names_all_three():
    affected = [{"iso3": "PHL"}, {"iso3": "chn"}, {"iso3": ""}, {"iso2": "JP"}, "junk", {"iso3": "JPN"}]
    (e,) = events._parse_gdacs(_payload(_feature(eventtype="TC", affectedcountries=affected)))
    assert e.category == "cyclone" and e.countries == ("PHL", "CHN", "JPN")


def test_an_event_that_already_ended_is_not_an_event():
    """SEARCH returns everything active inside the window, ended or not."""
    assert events._parse_gdacs(_payload(_feature(iscurrent="false"))) == []


def test_a_missing_current_flag_keeps_the_event():
    """A renamed field must not empty the feed — that is how the last outage hid."""
    feature = _feature()
    del feature["properties"]["iscurrent"]
    assert len(events._parse_gdacs(_payload(feature))) == 1


def test_earthquakes_and_wildfires_belong_to_other_sources():
    got = events._parse_gdacs(_payload(_feature(eventtype="EQ"), _feature(eventtype="WF")))
    assert got == []


def test_a_tsunami_is_not_a_storm():
    """GDACS "TS" is tsunami. It was mapped to "storm", one request change away
    from firing the storm rules on a wave. No rule reads a tsunami, so it is
    unmapped: "other", which the sentinel drops whatever the alert level."""
    from backend.services.geo import sentinel

    (e,) = events._parse_gdacs(_payload(_feature(eventtype="TS", alertlevel="Red")))
    assert e.category == "other"
    assert sentinel.analyze_natural_events([e]) == []


def test_a_200_that_is_not_a_payload_yields_nothing():
    for body in ('{"message":"Eventtype is required."}', "null", "[]", "", "<html>busy</html>"):
        assert events._parse_gdacs(body) == [], body


def test_a_feature_without_usable_coordinates_is_skipped():
    broken = _feature()
    broken["geometry"] = {"type": "Point", "coordinates": ["x", None]}
    missing = _feature()
    missing["geometry"] = None
    assert events._parse_gdacs(_payload(broken, missing)) == []


def test_an_empty_polygon_costs_its_own_feature_and_nothing_else():
    """`coordinates: [[]]` used to raise IndexError out of the parser."""
    empty = _feature(eventid=1)
    empty["geometry"] = {"type": "Polygon", "coordinates": [[]]}
    ring = _feature(eventid=2)
    ring["geometry"] = {"type": "Polygon", "coordinates": [[[100.5, 13.7], [100.6, 13.8]]]}
    got = events._parse_gdacs(_payload(empty, ring, _feature(eventid=3)))
    assert [e.id for e in got] == ["gdacs-2", "gdacs-3"]


def test_a_plain_string_url_still_reads():
    (e,) = events._parse_gdacs(_payload(_feature(url="https://www.gdacs.org/report.aspx?x=1")))
    assert e.url == "https://www.gdacs.org/report.aspx?x=1"


def test_fetch_asks_search_with_the_window(monkeypatch):
    monkeypatch.setattr(events, "_cache", events.TTLCache())
    seen = {}

    async def fake(url, *, params=None, **_):
        seen[url] = params
        return _payload(_feature()) if "gdacs" in url else '{"events": []}'

    monkeypatch.setattr(events, "fetch_text", fake)
    got = asyncio.run(events.fetch_events())
    assert [e.id for e in got] == ["gdacs-1104169"]
    assert events._GDACS_URL.endswith("/SEARCH")
    assert seen[events._GDACS_URL]["eventlist"] == "TC;FL;VO;DR"
