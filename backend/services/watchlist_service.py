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

from sqlalchemy.orm import Session

from backend.models import (
    FollowedInstrument,
    WatchlistItem,
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


def migrate_legacy_watchlists(db: Session) -> int:
    """Move legacy options/zonas watchlist memberships into followed_instruments.

    Move, not copy: legacy WatchlistItem rows are deleted in the same
    transaction, so a later restart finds nothing to migrate and can never
    resurrect rows the user removed from the canonical table. Zonas child
    rows are kept (ZonasClaveAnalysis still hangs off them) — only their
    membership is lifted into the canonical row. Guarded on the canonical
    table being empty. Returns the number of rows created.
    """
    if db.query(FollowedInstrument.id).first() is not None:
        if db.query(WatchlistItem.id).first() is not None:
            # Rolling-deploy stranding: an old revision wrote legacy rows after
            # this table was populated. Surface it — those rows are invisible.
            logger.warning(
                "watchlist migration skipped but legacy watchlist_items is non-empty — "
                "stranded rows from an old revision, reconcile manually before B3 drop"
            )
        return 0

    merged: dict[tuple[int, str], FollowedInstrument] = {}

    legacy_options = db.query(WatchlistItem).all()
    for legacy in legacy_options:
        key = (legacy.user_id, legacy.ticker.upper())
        item = merged.get(key) or FollowedInstrument(
            user_id=legacy.user_id,
            ticker=legacy.ticker.upper(),
            name=legacy.name or "",
            created_at=legacy.created_at,
        )
        item.options_enabled = True
        item.options_paused = not legacy.enabled
        merged[key] = item
        db.delete(legacy)

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
    if merged:
        logger.info("watchlist migration: created %d followed_instruments rows", len(merged))
    return len(merged)
