"""API endpoints for portfolio positions and holdings."""

import threading

from fastapi import APIRouter, HTTPException

from backend.api.auth import CurrentUser
from backend.database import DbSession, SessionLocal
from backend.services.portfolio_service import (
    get_open_positions,
    get_portfolio_summary,
    get_position_detail,
)
from backend.services.prices import fetch_and_cache_prices

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Track in-flight warm requests per user to avoid duplicate work
_warming: set[int] = set()
_warming_lock = threading.Lock()


def _warm_prices_background(user_id: int) -> None:
    """Fetch and cache prices for all open positions in a background thread."""
    try:
        db = SessionLocal()
        try:
            positions = get_open_positions(db, user_id, skip_prices=True)
            isins = list({p.isin for p in positions})
            if isins:
                fetch_and_cache_prices(db, isins)
        finally:
            db.close()
    finally:
        with _warming_lock:
            _warming.discard(user_id)


@router.post("/warm-prices")
def warm_prices(user: CurrentUser):
    """Trigger background price fetch for all open positions.

    Returns immediately. Prices land in the DB cache so subsequent
    calls to /positions or /summary are instant.
    """
    with _warming_lock:
        if user.id in _warming:
            return {"status": "already_warming"}
        _warming.add(user.id)

    thread = threading.Thread(
        target=_warm_prices_background, args=(user.id,), daemon=True,
    )
    thread.start()
    return {"status": "warming"}


@router.get("/positions")
def list_positions(db: DbSession, user: CurrentUser, skip_prices: bool = False):
    """Get all open positions with live prices and P&L."""
    positions = get_open_positions(db, user.id, skip_prices=skip_prices)
    return [
        {
            "isin": p.isin,
            "ticker": p.ticker,
            "name": p.name,
            "country": p.country,
            "broker": p.broker,
            "quantity": float(round(p.quantity, 6)),
            "avg_cost_eur": float(round(p.avg_cost_eur, 4)) if p.avg_cost_eur is not None else None,
            "total_cost_eur": float(round(p.total_cost_eur, 2)) if p.total_cost_eur is not None else None,
            "current_price_eur": float(round(p.current_price_eur, 4)) if p.current_price_eur is not None else None,
            "market_value_eur": float(round(p.market_value_eur, 2)) if p.market_value_eur is not None else None,
            "unrealized_pl_eur": float(round(p.unrealized_pl_eur, 2)) if p.unrealized_pl_eur is not None else None,
            "unrealized_pl_pct": float(round(p.unrealized_pl_pct, 2)) if p.unrealized_pl_pct is not None else None,
            "weight_pct": float(round(p.weight_pct, 2)) if p.weight_pct is not None else None,
        }
        for p in positions
    ]


@router.get("/summary")
def portfolio_summary(db: DbSession, user: CurrentUser, skip_prices: bool = False):
    """Aggregated portfolio statistics."""
    return get_portfolio_summary(db, user.id, skip_prices=skip_prices)


@router.get("/positions/{isin}")
def position_detail(isin: str, db: DbSession, user: CurrentUser):
    """Detailed view of a single position (lots, history, per-account breakdown)."""
    detail = get_position_detail(db, isin, user.id)
    if not detail:
        raise HTTPException(404, "No open position for this ISIN")
    return detail
