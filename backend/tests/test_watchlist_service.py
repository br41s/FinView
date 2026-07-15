"""Tests for the canonical followed-instruments service (Fase B)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base,
    User,
    WatchlistItem,
    ZonasClaveAnalysis,
    ZonasClaveWatchlistItem,
)
from backend.services import watchlist_service as svc


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(User(id=1, email="t@example.com"))
    session.commit()
    yield session
    session.close()


def _followed(db, ticker):
    return svc.get_followed(db, 1, ticker)


# ── Migration ─────────────────────────────────────────────────────────


def test_migration_merges_both_legacy_lists(db):
    from datetime import datetime

    old_ts = datetime(2025, 3, 1, 12, 0, 0)
    db.add_all(
        [
            WatchlistItem(user_id=1, ticker="AAPL", name="Apple", enabled=True, created_at=old_ts),
            WatchlistItem(user_id=1, ticker="MSFT", name="Microsoft", enabled=False),
            ZonasClaveWatchlistItem(user_id=1, ticker="AAPL", name="Apple Inc"),
            ZonasClaveWatchlistItem(user_id=1, ticker="SAN.MC", name="Santander"),
        ]
    )
    db.commit()

    created = svc.migrate_legacy_watchlists(db)
    assert created == 3

    aapl = _followed(db, "AAPL")
    assert aapl.options_enabled and not aapl.options_paused
    assert aapl.zonas_enabled  # merged, not duplicated
    assert aapl.created_at == old_ts  # original add-date preserved (list ordering)

    msft = _followed(db, "MSFT")
    assert msft.options_enabled and msft.options_paused  # legacy enabled=False
    assert not msft.zonas_enabled

    san = _followed(db, "SAN.MC")
    assert san.zonas_enabled and not san.options_enabled


def test_migration_moves_and_never_resurrects(db):
    db.add(WatchlistItem(user_id=1, ticker="AAPL", enabled=True))
    db.add(ZonasClaveWatchlistItem(user_id=1, ticker="AAPL", name="Apple"))
    db.commit()
    assert svc.migrate_legacy_watchlists(db) == 1

    # Legacy options rows are moved, zonas child rows are kept (analyses FK).
    assert db.query(WatchlistItem).count() == 0
    assert db.query(ZonasClaveWatchlistItem).count() == 1

    # User empties the canonical table; a restart must NOT resurrect anything
    # from the legacy options table…
    db.delete(_followed(db, "AAPL"))
    db.commit()
    svc.migrate_legacy_watchlists(db)
    item = _followed(db, "AAPL")
    # …but the surviving zonas child (still parenting analyses) re-lifts its
    # membership, which is correct: the zonas list still shows that ticker.
    assert item is not None and item.zonas_enabled and not item.options_enabled


def test_migration_noop_when_canonical_populated(db):
    svc.enable_options(db, 1, "TSLA")
    db.commit()
    db.add(WatchlistItem(user_id=1, ticker="AAPL", enabled=True))
    db.commit()
    assert svc.migrate_legacy_watchlists(db) == 0
    assert _followed(db, "AAPL") is None


# ── Options lens ──────────────────────────────────────────────────────


def test_enable_disable_options_prunes_row(db):
    svc.enable_options(db, 1, "aapl", "Apple")
    db.commit()
    item = _followed(db, "AAPL")
    assert item is not None and item.options_enabled

    svc.disable_options(db, item)
    db.commit()
    assert _followed(db, "AAPL") is None


def test_disable_options_keeps_row_when_zonas_on(db):
    svc.enable_options(db, 1, "AAPL")
    svc.enable_zonas(db, 1, "AAPL")
    db.commit()

    svc.disable_options(db, _followed(db, "AAPL"))
    db.commit()
    item = _followed(db, "AAPL")
    assert item is not None
    assert item.zonas_enabled and not item.options_enabled


# ── Zonas lens ────────────────────────────────────────────────────────


def test_enable_zonas_creates_single_child(db):
    _, child1 = svc.enable_zonas(db, 1, "AAPL", "Apple")
    db.commit()
    _, child2 = svc.enable_zonas(db, 1, "AAPL")
    db.commit()
    assert child1.id == child2.id
    assert db.query(ZonasClaveWatchlistItem).count() == 1
    assert _followed(db, "AAPL").zonas_enabled


def test_disable_zonas_cascades_analyses_and_prunes(db):
    _, child = svc.enable_zonas(db, 1, "AAPL")
    db.add(ZonasClaveAnalysis(watchlist_item_id=child.id, zones="[]"))
    db.commit()

    svc.disable_zonas(db, 1, child)
    db.commit()

    assert db.query(ZonasClaveWatchlistItem).count() == 0
    assert db.query(ZonasClaveAnalysis).count() == 0
    assert _followed(db, "AAPL") is None


def test_disable_zonas_keeps_row_when_options_on(db):
    svc.enable_options(db, 1, "AAPL")
    _, child = svc.enable_zonas(db, 1, "AAPL")
    db.commit()

    svc.disable_zonas(db, 1, child)
    db.commit()
    item = _followed(db, "AAPL")
    assert item is not None
    assert item.options_enabled and not item.zonas_enabled
