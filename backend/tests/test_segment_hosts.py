"""The annual-report hosts: a 429 closes one for the run, filings.xbrl.org is paced.

Measured on 2026-11-06: filings.xbrl.org answers the 11th request inside about 30 s with
429 (no Retry-After), whichever URLs they are. Before `hosts.py` each reader made one
request per ISIN every 0.15 s: ten answers a night, then a log line per skipped ISIN,
the AI reader starting second on an address the first had just exhausted. These tests
pin the behaviour the nightly run needs: a 429 stops that host for the rest of the run
and writes nothing, the SEC's ISINs carry on, and the second reader does not start over.
"""

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import AiMentionCheck, Base, SegmentCheck
from backend.services.segments import ai_mentions as am
from backend.services.segments import esef, hosts, listing, refresh, sec
from backend.services.segments.hosts import SourceUnavailable


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class Clock:
    """A clock the pacing runs on: sleeping moves it and is recorded."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(hosts, "_now", lambda: c.now)
    monkeypatch.setattr(hosts, "_sleep", c.sleep)
    hosts._next_slot.clear()
    yield c
    hosts._next_slot.clear()


LISTING = {
    "data": [
        {
            "attributes": {
                "fxo_id": "F-2024",
                "period_end": "2024-12-31",
                "date_added": "2025-02-01",
                "json_url": "/f.json",
                "viewer_url": "/v.html",
                "report_url": "/r.xhtml",
            }
        }
    ]
}


class Web:
    """Mock transport for GLEIF and filings.xbrl.org that counts what it was asked."""

    def __init__(self, filings_status=(200,)) -> None:
        self.calls: list[str] = []
        self._filings = list(filings_status)

    def count(self, host: str) -> int:
        return sum(1 for url in self.calls if host in url)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        if request.url.host == "api.gleif.org":
            isin = request.url.params.get("filter[isin]", "X")
            return httpx.Response(200, json={"data": [{"id": "LEI-" + isin}]})
        status = self._filings.pop(0) if len(self._filings) > 1 else self._filings[0]
        if status != 200:
            return httpx.Response(status, text="refused")
        return httpx.Response(200, json=LISTING)

    def client(self) -> hosts.Client:
        return hosts.Client(transport=httpx.MockTransport(self), follow_redirects=True)


def _refuse_everything(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url}")


# ── hosts.Client ─────────────────────────────────────────────────────


def test_filings_xbrl_org_is_paced_and_other_hosts_are_not(clock):
    web = Web()
    http = web.client()
    for _ in range(3):
        http.get("https://filings.xbrl.org/api/entities/X/filings")
    for _ in range(3):
        http.get("https://api.gleif.org/api/v1/lei-records")
    assert clock.sleeps == [hosts.PACE["filings.xbrl.org"]] * 2


def test_the_pace_belongs_to_the_process_not_to_the_client(clock):
    """The AI reader opens its own client after the segment reader's: without a shared
    pace it would start a fresh burst of ten on an address that has just spent its own."""
    web = Web()
    web.client().get("https://filings.xbrl.org/api/entities/X/filings")
    web.client().get("https://filings.xbrl.org/api/entities/Y/filings")
    assert clock.sleeps == [hosts.PACE["filings.xbrl.org"]]


def test_a_request_after_the_gap_does_not_wait(clock):
    http = Web().client()
    http.get("https://filings.xbrl.org/api/entities/X/filings")
    clock.now += 10
    http.get("https://filings.xbrl.org/api/entities/Y/filings")
    assert clock.sleeps == []


def test_a_429_closes_that_host_for_the_rest_of_the_run_and_only_that_host(clock):
    web = Web(filings_status=(429,))
    http = web.client()
    assert http.get("https://filings.xbrl.org/api/entities/X/filings").status_code == 429
    assert http.closed == {"filings.xbrl.org"}

    with pytest.raises(SourceUnavailable, match="429 earlier in this run"):
        http.get("https://filings.xbrl.org/api/entities/Y/filings")
    assert web.count("filings.xbrl.org") == 1  # the refused one never left the process

    assert http.get("https://api.gleif.org/api/v1/lei-records").status_code == 200


def test_a_new_client_starts_open(clock):
    web = Web(filings_status=(429, 200))
    web.client().get("https://filings.xbrl.org/api/entities/X/filings")
    assert web.client().get("https://filings.xbrl.org/api/entities/X/filings").status_code == 200


# ── lookups shared by the readers ────────────────────────────────────


def test_a_lookup_is_asked_once_per_run_including_a_definite_nothing(clock):
    web = Web()
    http = web.client()
    assert esef.isin_to_lei(http, "ES0000000001") == "LEI-ES0000000001"
    assert esef.isin_to_lei(http, "ES0000000001") == "LEI-ES0000000001"
    assert esef.latest_filing(http, "L").filing_id == "F-2024"
    assert esef.latest_filing(http, "L").filing_id == "F-2024"
    assert (web.count("gleif"), web.count("filings.xbrl.org")) == (1, 1)


def test_a_failed_lookup_is_not_remembered(clock):
    web = Web(filings_status=(500, 200))
    http = web.client()
    with pytest.raises(SourceUnavailable):
        esef.latest_filing(http, "L")
    assert esef.latest_filing(http, "L").filing_id == "F-2024"


def test_a_plain_client_still_works_without_a_memo():
    web = Web()
    http = httpx.Client(transport=httpx.MockTransport(web))
    esef.latest_filing(http, "L")
    esef.latest_filing(http, "L")
    assert web.count("filings.xbrl.org") == 2


# ── the segment reader ───────────────────────────────────────────────

HOLDINGS = {
    "ES0000000001": ("AAA.MC", "Alpha"),
    "ES0000000002": ("BBB.MC", "Beta"),
    "ES0000000003": ("CCC.MC", "Gamma"),
    "US0000000001": ("ZZZ", "Zeta Inc"),
}


@pytest.fixture
def world(monkeypatch):
    """ESEF behind a mock that refuses on the first filings request; a SEC with no issuer
    for the one US ISIN (a definite answer, so the US ISIN visibly 'carried on')."""
    web = Web(filings_status=(429,))
    monkeypatch.setattr(esef, "client", web.client)
    monkeypatch.setattr(
        sec, "client", lambda: hosts.Client(transport=httpx.MockTransport(_refuse_everything))
    )
    monkeypatch.setattr(sec, "ticker_to_cik", lambda http: {})
    monkeypatch.setattr(refresh.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(am.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(listing, "refresh", lambda db, holdings, seconds: (0, 0))
    return web


def test_a_429_stops_esef_for_the_run_writes_nothing_and_the_us_isin_still_runs(db, world, caplog):
    result = refresh.refresh(db, HOLDINGS, 30)

    # One GLEIF + one refused filings request, then nothing: not one request per ISIN.
    assert (world.count("gleif"), world.count("filings.xbrl.org")) == (1, 1)
    # No row for any ESEF ISIN: a refusal is not a fact about the issuer.
    assert {c.isin: c.outcome for c in db.query(SegmentCheck).all()} == {
        "US0000000001": "no_issuer"
    }
    assert result == {"checked": 1, "pending": 3}
    # One line for the refused ISIN, one for the rest, not one per ISIN.
    assert [r.message for r in caplog.records if "left for the next run" in r.message] == [
        "[segments] 2 ISINs left for the next run: filings.xbrl.org answered 429"
    ]


def test_a_429_is_never_cached_so_the_next_run_reads_the_issuer(db, world, monkeypatch):
    refresh.refresh(db, HOLDINGS, 30)
    assert db.query(SegmentCheck).filter(SegmentCheck.isin == "ES0000000001").count() == 0
    assert "ES0000000001" in refresh.due_isins(db, HOLDINGS)


# ── the AI reader ────────────────────────────────────────────────────


def test_the_ai_reader_stops_on_a_429_too_and_reads_the_us_isin(db, world):
    result = am.refresh(db, HOLDINGS, 30)

    assert (world.count("gleif"), world.count("filings.xbrl.org")) == (1, 1)
    assert {c.isin: c.outcome for c in db.query(AiMentionCheck).all()} == {
        "US0000000001": "no_issuer"
    }
    assert result == {"checked": 1, "pending": 3}


def test_the_second_reader_inherits_the_closed_host_and_does_not_try_it(db, world):
    """The 11-04 and 11-05 nights: the segment reader had spent the address, the AI reader
    then made 23 requests of its own, each refused. Sharing the run's sources, it makes none."""
    with refresh.Sources() as sources:
        refresh.refresh(db, HOLDINGS, 30, sources)
        before = len(world.calls)
        result = am.refresh(db, HOLDINGS, 30, sources)

    assert len(world.calls) == before
    assert {c.isin for c in db.query(AiMentionCheck).all()} == {"US0000000001"}
    assert result == {"checked": 1, "pending": 3}


def test_without_a_shared_run_the_second_reader_finds_out_for_itself(db, world):
    refresh.refresh(db, HOLDINGS, 30)
    before = len(world.calls)
    am.refresh(db, HOLDINGS, 30)
    assert len(world.calls) > before


def test_both_readers_share_the_lookups_for_an_issuer_that_answers(db, monkeypatch):
    web = Web()
    monkeypatch.setattr(esef, "client", web.client)
    monkeypatch.setattr(
        sec, "client", lambda: hosts.Client(transport=httpx.MockTransport(_refuse_everything))
    )
    monkeypatch.setattr(refresh.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(am.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(listing, "refresh", lambda db, holdings, seconds: (0, 0))
    monkeypatch.setattr(esef, "fetch_report", lambda http, filing: None)  # → no_revenue
    monkeypatch.setattr(am, "read_text", lambda http, url, seconds: am.Document("no mention", []))
    holdings = {"ES0000000001": ("AAA.MC", "Alpha")}

    with refresh.Sources() as sources:
        assert refresh.refresh(db, holdings, 30, sources)["checked"] == 1
        assert am.refresh(db, holdings, 30, sources)["checked"] == 1

    assert db.query(SegmentCheck).one().outcome == "no_revenue"
    assert db.query(AiMentionCheck).one().outcome == "ok"
    # GLEIF and the filings listing: once for the two readers, not once each.
    assert (web.count("gleif"), web.count("filings.xbrl.org")) == (1, 1)


# ── the cron ─────────────────────────────────────────────────────────


def test_the_cron_runs_both_readers_on_one_set_of_connections():
    from unittest.mock import patch

    from backend.services.reference_data_maintenance import run_reference_data_maintenance

    seen = []
    with (
        patch("backend.services.exchange_rates.sync_rates"),
        patch("backend.services.fred_rates.sync_rates"),
        patch("backend.services.macro_context.sync_macro"),
        patch("backend.services.cnmv_catalog.catalog_is_stale", return_value=False),
        patch("backend.services.reference_data_maintenance.SessionLocal"),
        patch("backend.services.portfolio_service.get_open_positions", return_value=[]),
        patch(
            "backend.services.segments.refresh.refresh",
            side_effect=lambda db, h, s, sources: seen.append(("segments", sources)),
        ),
        patch(
            "backend.services.segments.ai_mentions.refresh",
            side_effect=lambda db, h, s, sources: seen.append(("ai", sources)),
        ),
    ):
        run_reference_data_maintenance()

    assert [name for name, _ in seen] == ["segments", "ai"]
    assert seen[0][1] is seen[1][1] and isinstance(seen[0][1], refresh.Sources)
    assert seen[0][1].esef.is_closed  # and they are released when the run ends


def test_a_failing_segment_reader_does_not_stop_the_ai_reader(caplog):
    from unittest.mock import patch

    from backend.services.reference_data_maintenance import run_reference_data_maintenance

    with (
        patch("backend.services.exchange_rates.sync_rates"),
        patch("backend.services.fred_rates.sync_rates"),
        patch("backend.services.macro_context.sync_macro"),
        patch("backend.services.cnmv_catalog.catalog_is_stale", return_value=False),
        patch("backend.services.reference_data_maintenance.SessionLocal"),
        patch("backend.services.portfolio_service.get_open_positions", return_value=[]),
        patch("backend.services.segments.refresh.refresh", side_effect=RuntimeError("boom")),
        patch("backend.services.segments.ai_mentions.refresh") as ai,
    ):
        run_reference_data_maintenance()

    ai.assert_called_once()
    assert "[segments] skipped: RuntimeError" in caplog.text
