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


def _story(i, *, lat=50.4, lon=30.5, date="20260921120000"):
    return GdeltEvent(
        id=f"gdelt-{i}", title="t", event_code="190", event_root_code="19", quad_class=4,
        goldstein_scale=-10.0, num_mentions=20, num_sources=1, num_articles=20, avg_tone=-8.0,
        latitude=lat, longitude=lon + i * 0.01, location="Kyiv", actor1="A", actor2="B",
        date_added=date, source_url=f"https://ex.test/{i}",
    )


def _ukraine(n):
    return next(e for e in sentinel.analyze_gdelt_events([_story(i) for i in range(n)])
                if e.type == "armed_conflict" and e.region == "ukraine_black_sea")


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


def test_coordinate_cells_are_never_sampled():
    """A story outside every box keys on "lat_lon"; it never recurs, never
    reaches a baseline, and was half the rows written per cycle."""
    sentinel.analyze_gdelt_events([_story(1, lat=-19.0, lon=29.0)])  # Zimbabwe: no box
    assert all(not k.lstrip("-").split("_")[0].isdigit() for k in sentinel._gdelt_history)


def test_every_gdelt_rule_region_is_sampled_every_cycle():
    """The zero-fill set must cover every region a GDELT rule can fire on, or a
    rule on a region outside it gets a positives-only baseline and can never be
    novel — and it would look fine in review."""
    import re

    from backend.services.geo.rules import FAST_RULES

    gdelt_types = {f[0] for f in sentinel._GDELT_FILTERS.values()}
    regions = {
        m.group(1)
        for r in FAST_RULES
        if r.category in gdelt_types
        for m in [re.search(r"region=(\w+)", r.condition)]
        if m
    }
    assert regions <= sentinel._ESCALATION_REGIONS, regions - sentinel._ESCALATION_REGIONS


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


# ── The ingest reads two hours; every count is over the newest one ────


def test_the_bridge_reaches_the_matcher_but_is_not_counted():
    """Newest batch 12:00, so the hour is 11:15–12:00 (four batches). A row from
    11:00 was a missed cycle's news: it must still become an event, but counting
    it would change the unit the 7-day baseline was measured in."""
    rows = [
        _story(1), _story(2, date="20260921111500"),  # in the hour, edge included
        _story(3, date="20260921110000"), _story(4, date="20260921103000"),  # bridge
        _story(5, lat=26.0, lon=56.0, date="20260921110000"),  # Hormuz, bridge only
    ]
    events = {e.region: e for e in sentinel.analyze_gdelt_events(rows)
              if e.type == "armed_conflict"}
    assert events["ukraine_black_sea"].raw_data["storiesThisHour"] == 2
    assert sentinel._gdelt_history["ukraine_black_sea"][-1][0] == 2
    hormuz = events["strait_of_hormuz"]  # tracked, not counted
    assert hormuz.raw_data["storiesThisHour"] == 0
    assert hormuz.raw_data["novelty"]["stories"] == 0


def test_a_region_at_its_baseline_is_not_novel_when_the_bridge_doubles_the_read():
    """THE hazard of widening the window: counted per read, an ongoing war at
    its hourly baseline reads 2× its median and pages as novel for days."""
    _history("ukraine_black_sea", [20] * 24)
    rows = [_story(i) for i in range(20)] + [
        _story(100 + i, date="20260921110000") for i in range(20)
    ]
    ukraine = next(e for e in sentinel.analyze_gdelt_events(rows)
                   if e.type == "armed_conflict" and e.region == "ukraine_black_sea")
    assert ukraine.raw_data["novelty"] == {"stories": 20, "baseline": 20, "novel": False}


def test_the_cluster_bar_counts_the_newest_hour_only():
    """Ten stories was calibrated on one hour; two hours would halve the bar."""
    def mixed(start, date):
        return [
            GdeltEvent(id=f"g-{start + i}", title="t", event_code=code, event_root_code=root,
                       quad_class=4, goldstein_scale=gs, num_mentions=20, num_sources=1,
                       num_articles=20, avg_tone=-8.0, latitude=50.4,
                       longitude=30.5 + (start + i) * 0.01, location="Kyiv", actor1="A",
                       actor2="B", date_added=date, source_url=f"https://ex.test/c{start + i}")
            for i, (code, root, gs) in enumerate([("190", "19", -10.0), ("154", "15", -7.2)] * 3)
        ]
    rows = mixed(0, "20260921120000") + mixed(10, "20260921110000")  # 6 + 6 bridged
    assert [e for e in sentinel.analyze_gdelt_events(rows)
            if e.type == "geopolitical_escalation"] == []


def test_a_row_without_a_usable_stamp_still_counts():
    """It cannot be placed in or out of the hour; dropping it would silently
    thin the feed if GDELT ever changed the column."""
    rows = [_story(1), _story(2, date=""), _story(3, date="garbage")]
    ukraine = next(e for e in sentinel.analyze_gdelt_events(rows)
                   if e.type == "armed_conflict" and e.region == "ukraine_black_sea")
    assert ukraine.raw_data["storiesThisHour"] == 3


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


def test_a_deferred_page_carries_the_spike_and_reanchors(db):
    """A bucket created on a quiet day pages on the spike: the push must carry
    the spike's headline, and the checkpoints must start there, not at creation."""
    from backend.models import GeoCheckpoint

    quiet = AnalystResult(
        event=_gdelt_event(False), matched_rules=[],
        tickers=[AnalystTicker("WEAT", "bullish", "x")], confidence=84.0, risk_score=8,
        direction="bullish",
    )
    first = generate_signal(db, user_id=1, analysis=quiet, prices={"WEAT": 100.0})
    db.flush()
    from backend.services.geo.auditor import create_checkpoints

    first.signal.created_at = datetime.now(timezone.utc) - timedelta(days=2)  # the quiet day
    create_checkpoints(db, first.signal)
    db.commit()
    old_targets = {getattr(c.horizon, "value", c.horizon): c.target_at for c in first.signal.checkpoints}

    spike_event = _gdelt_event(True)
    spike_event.title = "Armed Conflict: RUSSIA → KYIV: fight with artillery"
    spike = AnalystResult(
        event=spike_event, matched_rules=[], tickers=[AnalystTicker("WEAT", "bullish", "x")],
        confidence=84.0, risk_score=8, direction="bullish",
    )
    res = generate_signal(db, user_id=1, analysis=spike, prices={"WEAT": 130.0})
    db.commit()
    assert res.should_notify is True and res.is_new is False
    assert res.signal.headline.startswith("Armed Conflict: RUSSIA")
    assert float(res.signal.tickers[0].price_at_signal) == 130.0
    fresh = {getattr(c.horizon, "value", c.horizon): c.target_at for c in
             db.query(GeoCheckpoint).filter_by(signal_id=res.signal.id).all()}
    assert set(fresh) == set(old_targets)
    # The daily horizons restart from the spike; the intraday ones are in
    # trading time and may land on the same session bar (weekend → Monday).
    assert all(fresh[h] > old_targets[h] for h in ("1d", "3d", "7d"))
    assert all(fresh[h] >= old_targets[h] for h in ("1h", "6h"))
