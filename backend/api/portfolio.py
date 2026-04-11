"""API endpoints for portfolio positions and holdings."""

from fastapi import APIRouter, HTTPException

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.services.portfolio_service import (
    get_open_positions,
    get_portfolio_summary,
    get_position_detail,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


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
            "avg_cost_eur": float(round(p.avg_cost_eur, 4)),
            "total_cost_eur": float(round(p.total_cost_eur, 2)),
            "current_price_eur": float(round(p.current_price_eur, 4)) if p.current_price_eur else None,
            "market_value_eur": float(round(p.market_value_eur, 2)) if p.market_value_eur else None,
            "unrealized_pl_eur": float(round(p.unrealized_pl_eur, 2)) if p.unrealized_pl_eur else None,
            "unrealized_pl_pct": float(round(p.unrealized_pl_pct, 2)) if p.unrealized_pl_pct else None,
            "weight_pct": float(round(p.weight_pct, 2)) if p.weight_pct else None,
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
