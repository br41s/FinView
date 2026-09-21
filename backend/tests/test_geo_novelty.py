"""The novelty gate: news pages on a spike over its region's own baseline."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, GeoRegionSample
from backend.services.geo import orchestrator, sentinel
from backend.services.geo.advisor import _pageable, generate_signal
from backend.services.geo.analyst import AnalystResult, AnalystTicker
from backend.services.geo.ingest.types import GdeltEvent
from backend.services.geo.sentinel import GeoEvent


@pytest.fixture(autouse=True)
def fresh_history(monkeypatch):
    monkeypatch.setattr(sentinel, "_gdelt_history", {})


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _story(i, *, lat=50.4, lon=30.5):
    return GdeltEvent(
        id=f"gdelt-{i}", title="t", event_code="190", event_root_code="19", quad_class=4,
        goldstein_scale=-10.0, num_mentions=20, num_sources=1, num_articles=20, avg_tone=-8.0,
        latitude=lat, longitude=lon + i * 0.01, location="Kyiv", actor1="A", actor2="B",
        date_added="20260921120000", source_url=f"https://ex.test/{i}",
    )


def _ukraine(n):
    return [e for e in sentinel.analyze_gdelt_events([_story(i) for i in range(n)])
            if e.type == "armed_conflict" and e.region == "ukraine_black_sea"][0]


def _history(region, counts):
    sentinel._gdelt_history[region] = [(c, i) for i, c in enumerate(counts)]


def test_no_baseline_is_not_novel():
    assert _ukraine(5).raw_data["novelty"] == {"stories": 5, "baseline": None, "novel": None}


def test_a_spike_over_a_quiet_region_is_novel():
    _history("ukraine_black_sea", [0] * 12)
    assert _ukraine(3).raw_data["novelty"]["novel"] is True
    sentinel._gdelt_history["ukraine_black_sea"] = sentinel._gdelt_history["ukraine_black_sea"][:12]
    assert _ukraine(2).raw_data["novelty"]["novel"] is False  # below the story floor


def test_an_ongoing_war_at_its_baseline_is_not_novel():
    """Ukraine at 20 stories an hour, every hour, is the baseline — not news."""
    _history("ukraine_black_sea", [20] * 24)
    assert _ukraine(25).raw_data["novelty"] == {"stories": 25, "baseline": 20, "novel": False}
    _history("ukraine_black_sea", [20] * 24)
    assert _ukraine(45).raw_data["novelty"]["novel"] is True  # a real escalation doubles it


def test_every_escalation_region_gets_a_sample_including_zero():
    _ukraine(2)
    assert "strait_of_hormuz" in sentinel._gdelt_history
    assert sentinel._gdelt_history["strait_of_hormuz"][-1][0] == 0
    assert sentinel._gdelt_history["ukraine_black_sea"][-1][0] == 2


def test_the_cluster_carries_the_region_novelty():
    _history("ukraine_black_sea", [0] * 12)
    rows = [_story(i) for i in range(6)] + [
        GdeltEvent(id=f"g-{i}", title="t", event_code="154", event_root_code="15", quad_class=3,
                   goldstein_scale=-7.2, num_mentions=20, num_sources=1, num_articles=20,
                   avg_tone=-8.0, latitude=50.4, longitude=30.6 + i * 0.01, location="Kyiv",
                   actor1="A", actor2="B", date_added="20260921120000", source_url=f"https://ex.test/m{i}")
        for i in range(6)
    ]
    cluster = [e for e in sentinel.analyze_gdelt_events(rows) if e.type == "geopolitical_escalation"]
    assert cluster and cluster[0].raw_data["novelty"]["novel"] is True


def _gdelt_event(novel):
    return GeoEvent(
        id="gdelt-armed_conflict-ukraine_black_sea", type="armed_conflict", title="t",
        latitude=50.4, longitude=30.5, source="gdelt", timestamp=int(time.time() * 1000),
        raw_data={"novelty": {"stories": 5, "baseline": 20, "novel": novel}},
    )


def test_the_gate_pages_gdelt_only_on_novelty():
    assert _pageable("gdelt", 80, _gdelt_event(True)) is True
    assert _pageable("gdelt", 80, _gdelt_event(False)) is False
    assert _pageable("gdelt", 80, _gdelt_event(None)) is False
    assert _pageable("usgs", 80, None) is True  # physical events are new ids by nature


def test_a_retracked_war_at_baseline_does_not_page(db):
    analysis = AnalystResult(
        event=_gdelt_event(False), matched_rules=[],
        tickers=[AnalystTicker("WEAT", "bullish", "x")], confidence=84.0, risk_score=8,
        direction="bullish",
    )
    res = generate_signal(db, user_id=1, analysis=analysis, prices={})
    assert res.importance >= 60 and res.should_notify is False


def test_region_samples_round_trip(db, monkeypatch):
    _ukraine(4)
    assert orchestrator._persist_region_samples(db) == len(sentinel._gdelt_history)
    assert orchestrator._persist_region_samples(db) == 0  # same cycle, another user
    monkeypatch.setattr(sentinel, "_gdelt_history", {})
    orchestrator._hydrate_region_history(db)
    assert sentinel._gdelt_history["ukraine_black_sea"][-1][0] == 4
    db.add(GeoRegionSample(region="iran", stories=9,
                           sampled_at=datetime.now(timezone.utc) - timedelta(days=8)))
    db.commit()
    orchestrator._hydrate_region_history(db)
    assert all(s != 9 for s, _ in sentinel._gdelt_history.get("iran", []))
