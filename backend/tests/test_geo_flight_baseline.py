"""The airspace baseline survives scale-to-zero, and no baseline means no surge."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, GeoFlightSample
from backend.services.geo import orchestrator, sentinel
from backend.services.geo.ingest.types import FlightData


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _flight(lat: float, lon: float, military: bool) -> FlightData:
    return FlightData(
        icao24=f"{lat:.3f}{lon:.3f}{military}", callsign="X", origin_country="",
        latitude=lat, longitude=lon, altitude=30000.0, velocity=400.0, heading=0.0,
        vertical_rate=0.0, on_ground=False, squawk=None, is_military=military,
        aircraft_type="military" if military else "commercial",
    )


# Hormuz zone: lat 24–28, lon 54–58, surge threshold 5.
def _hormuz(n_mil: int, n_civ: int = 20) -> list[FlightData]:
    mil = [_flight(26.0 + i * 0.01, 56.0, True) for i in range(n_mil)]
    civ = [_flight(25.0 + i * 0.01, 55.0, False) for i in range(n_civ)]
    return mil + civ


def test_no_baseline_means_no_surge(monkeypatch):
    """Five tankers on station used to be a surge on every cold start."""
    monkeypatch.setattr(sentinel, "_flight_history", {})
    events = sentinel.analyze_flight_anomalies(_hormuz(6))
    assert not [e for e in events if e.type == "military_surge"]


def test_a_real_baseline_detects_a_surge(monkeypatch):
    monkeypatch.setattr(sentinel, "_flight_history", {
        "hormuz-airspace": [(25, 1, 1), (25, 1, 2)],
    })
    events = sentinel.analyze_flight_anomalies(_hormuz(6))
    surge = [e for e in events if e.type == "military_surge"]
    assert surge and surge[0].raw_data["baselineMilitary"] == 1


def test_samples_round_trip_through_the_db(db, monkeypatch):
    monkeypatch.setattr(sentinel, "_flight_history", {})
    sentinel.analyze_flight_anomalies(_hormuz(2))
    assert orchestrator._persist_flight_samples(db) == len(sentinel._AIRSPACE_ZONES)

    # Same cycle seen by a second user: nothing stored twice.
    sentinel.analyze_flight_anomalies(_hormuz(2))
    assert orchestrator._persist_flight_samples(db) == 0

    # A fresh process: the baseline comes back from the DB.
    monkeypatch.setattr(sentinel, "_flight_history", {})
    orchestrator._hydrate_flight_history(db)
    hist = sentinel._flight_history["hormuz-airspace"]
    assert [(h[0], h[1]) for h in hist] == [(22, 2)]


def test_old_samples_are_pruned(db, monkeypatch):
    db.add(GeoFlightSample(
        zone_id="hormuz-airspace", total=1, military=0,
        sampled_at=datetime.now(timezone.utc) - timedelta(days=2),
    ))
    db.commit()
    monkeypatch.setattr(sentinel, "_flight_history", {})
    orchestrator._hydrate_flight_history(db)
    assert "hormuz-airspace" not in sentinel._flight_history
    orchestrator._persist_flight_samples(db)
    assert db.query(GeoFlightSample).filter(
        GeoFlightSample.sampled_at < datetime.now(timezone.utc) - timedelta(days=1)
    ).count() == 0
