"""Markets API — DB-backed watchlist for the /markets candlestick viewer.

Mirrors the options watchlist CRUD pattern but on its own table
(`markets_watchlist`), because the markets list is a casual price-viewing
scope, distinct from the options-monitoring and zonas-clave lists.
Replaces the previous browser-localStorage list so it persists per user.
"""

from fastapi import APIRouter, HTTPException

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    MarketsWatchlistImportIn,
    MarketsWatchlistItemOut,
    WatchlistItemIn,
)
from backend.database import DbSession
from backend.models import MarketsWatchlistItem

router = APIRouter(prefix="/markets", tags=["markets"])

_404 = {404: {"description": "Not found"}}


@router.get("/watchlist", response_model=list[MarketsWatchlistItemOut])
def list_watchlist(db: DbSession, user: CurrentUser):
    return (
        db.query(MarketsWatchlistItem)
        .filter(MarketsWatchlistItem.user_id == user.id)
        .order_by(MarketsWatchlistItem.created_at)
        .all()
    )


@router.post(
    "/watchlist",
    response_model=MarketsWatchlistItemOut,
    status_code=201,
    responses={409: {"description": "Ticker already in watchlist"}},
)
def add_watchlist_item(body: WatchlistItemIn, db: DbSession, user: CurrentUser):
    ticker = body.ticker.upper()
    existing = (
        db.query(MarketsWatchlistItem)
        .filter(
            MarketsWatchlistItem.user_id == user.id,
            MarketsWatchlistItem.ticker == ticker,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ticker already in watchlist")

    item = MarketsWatchlistItem(user_id=user.id, ticker=ticker, name=body.name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/watchlist/import", response_model=list[MarketsWatchlistItemOut])
def import_watchlist(body: MarketsWatchlistImportIn, db: DbSession, user: CurrentUser):
    """Idempotent bulk insert for the one-time localStorage migration.

    Inserts any tickers not already present, then returns the full list.
    Safe to call repeatedly (no-op for tickers that already exist).
    """
    existing = {
        item.ticker
        for item in db.query(MarketsWatchlistItem)
        .filter(MarketsWatchlistItem.user_id == user.id)
        .all()
    }
    for raw in body.tickers:
        ticker = raw.strip().upper()
        if ticker and ticker not in existing:
            db.add(MarketsWatchlistItem(user_id=user.id, ticker=ticker))
            existing.add(ticker)
    db.commit()
    return (
        db.query(MarketsWatchlistItem)
        .filter(MarketsWatchlistItem.user_id == user.id)
        .order_by(MarketsWatchlistItem.created_at)
        .all()
    )


@router.delete("/watchlist/{item_id}", status_code=204, responses=_404)
def remove_watchlist_item(item_id: int, db: DbSession, user: CurrentUser):
    item = (
        db.query(MarketsWatchlistItem)
        .filter(
            MarketsWatchlistItem.id == item_id,
            MarketsWatchlistItem.user_id == user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
