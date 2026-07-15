"""Canonical followed-instruments service (Fase B — watchlist unificada).

One FollowedInstrument row per (user, ticker) with opt-in per-section lenses:
options (agent scope, with a pause sub-state) and zonas (S/R analysis). The
zonas lens keeps ZonasClaveWatchlistItem as a synced internal child because
ZonasClaveAnalysis hangs off it via a cascade FK — membership truth lives
here, the child row is an implementation detail.

`migrate_legacy_watchlists()` copies the two legacy tables into the canonical
one exactly once (only when followed_instruments is empty), so redeploys and
restarts never resurrect rows the user later removed.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.models import (
    FollowedInstrument,
    ZonasClaveWatchlistItem,
)

logger = logging.getLogger(__name__)


def get_followed(db: Session, user_id: int, ticker: str) -> FollowedInstrument | None:
    return (
        db.query(FollowedInstrument)
        .filter(FollowedInstrument.user_id == user_id, FollowedInstrument.ticker == ticker.upper())
        .first()
    )


def ensure_followed(db: Session, user_id: int, ticker: str, name: str = "") -> FollowedInstrument:
    """Upsert the canonical row (no lens change, no commit)."""
    item = get_followed(db, user_id, ticker)
    if item is None:
        item = FollowedInstrument(user_id=user_id, ticker=ticker.upper(), name=name)
        db.add(item)
        db.flush()
    elif name and not item.name:
        item.name = name
    return item


def _prune_if_lensless(db: Session, item: FollowedInstrument) -> None:
    if not item.options_enabled and not item.zonas_enabled:
        db.delete(item)


# ── Options lens ──────────────────────────────────────────────────────


def enable_options(db: Session, user_id: int, ticker: str, name: str = "") -> FollowedInstrument:
    item = ensure_followed(db, user_id, ticker, name)
    item.options_enabled = True
    return item


def disable_options(db: Session, item: FollowedInstrument) -> None:
    """Turn the options lens off; the caller cleans options-side data
    (alerts/snapshots) and commits. Prunes the row when no lens remains."""
    item.options_enabled = False
    item.options_paused = False
    _prune_if_lensless(db, item)


# ── Zonas lens ────────────────────────────────────────────────────────


def enable_zonas(
    db: Session, user_id: int, ticker: str, name: str = ""
) -> tuple[FollowedInstrument, ZonasClaveWatchlistItem]:
    """Turn the zonas lens on and sync the internal child row (created if
    missing). The caller fires the background analysis and commits."""
    item = ensure_followed(db, user_id, ticker, name)
    item.zonas_enabled = True
    child = (
        db.query(ZonasClaveWatchlistItem)
        .filter(
            ZonasClaveWatchlistItem.user_id == user_id,
            ZonasClaveWatchlistItem.ticker == ticker.upper(),
        )
        .first()
    )
    if child is None:
        child = ZonasClaveWatchlistItem(user_id=user_id, ticker=ticker.upper(), name=name)
        db.add(child)
        db.flush()
    return item, child


def disable_zonas(db: Session, user_id: int, child: ZonasClaveWatchlistItem) -> None:
    """Turn the zonas lens off. Deleting the child row cascades the stored
    ZonasClaveAnalysis rows exactly like the legacy delete did."""
    item = get_followed(db, user_id, child.ticker)
    db.delete(child)
    if item is not None:
        item.zonas_enabled = False
        _prune_if_lensless(db, item)


# ── One-off legacy migration ──────────────────────────────────────────


def _parse_dt(value) -> datetime | None:
    """Raw-SQL datetime values arrive as datetime on Postgres but as ISO
    strings on SQLite — normalize both."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def migrate_legacy_watchlists(db: Session) -> int:
    """Move legacy watchlist memberships into followed_instruments, then drop
    the legacy `watchlist_items` table (B3 — it has no ORM model anymore, so
    it is read via raw SQL and never recreated by create_all).

    Behavior by state:
    - legacy table absent → nothing to do (fresh DBs post-B3).
    - canonical empty → migrate legacy options rows + lift zonas memberships,
      then drop the legacy table.
    - canonical populated + legacy empty → just drop the legacy table
      (prod path: the Fase-B move already emptied it).
    - canonical populated + legacy has rows → stranded writes from an old
      revision: warn and keep the table for manual reconciliation. Never
      silently destroy data.

    Zonas child rows are kept (ZonasClaveAnalysis still hangs off them) —
    only their membership is lifted. Returns the number of rows created.
    """
    bind = db.get_bind()
    legacy_exists = inspect(bind).has_table("watchlist_items")
    canonical_empty = db.query(FollowedInstrument.id).first() is None

    legacy_rows: list = []
    if legacy_exists:
        legacy_rows = db.execute(
            text("SELECT user_id, ticker, name, enabled, created_at FROM watchlist_items")
        ).all()

    if not canonical_empty:
        if legacy_rows:
            # Rolling-deploy stranding: an old revision wrote legacy rows after
            # this table was populated. Surface it — those rows are invisible.
            logger.warning(
                "watchlist migration skipped but legacy watchlist_items has %d rows — "
                "stranded writes from an old revision, reconcile manually (table kept)",
                len(legacy_rows),
            )
        elif legacy_exists:
            db.execute(text("DROP TABLE watchlist_items"))
            db.commit()
            logger.info("watchlist migration: dropped empty legacy watchlist_items table")
        return 0

    merged: dict[tuple[int, str], FollowedInstrument] = {}

    for row in legacy_rows:
        key = (row.user_id, row.ticker.upper())
        item = merged.get(key) or FollowedInstrument(
            user_id=row.user_id,
            ticker=row.ticker.upper(),
            name=row.name or "",
            created_at=_parse_dt(row.created_at),
        )
        item.options_enabled = True
        # NULL enabled (raw insert without the column) maps to the legacy
        # Python-side default (active), not to paused.
        item.options_paused = row.enabled is not None and not bool(row.enabled)
        merged[key] = item

    for legacy in db.query(ZonasClaveWatchlistItem).all():
        key = (legacy.user_id, legacy.ticker.upper())
        item = merged.get(key) or FollowedInstrument(
            user_id=legacy.user_id,
            ticker=legacy.ticker.upper(),
            name=legacy.name or "",
            created_at=legacy.added_at,
        )
        if not item.name and legacy.name:
            item.name = legacy.name
        item.zonas_enabled = True
        merged[key] = item

    db.add_all(merged.values())
    db.commit()
    if legacy_exists:
        # Data is committed; the legacy table is now fully superseded.
        db.execute(text("DROP TABLE watchlist_items"))
        db.commit()
        logger.info("watchlist migration: dropped legacy watchlist_items table")
    if merged:
        logger.info("watchlist migration: created %d followed_instruments rows", len(merged))
    return len(merged)
