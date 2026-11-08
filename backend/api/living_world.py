"""Living World ("Mundo vivo"): the portfolio as the town draws it. Read-only."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.services.living_world import build_world

router = APIRouter(prefix="/living-world", tags=["living-world"])


class WorldAssetOut(BaseModel):
    isin: str
    ticker: str | None
    name: str
    country: str | None
    brokers: list[str]
    asset_type: str
    sector: str | None
    classified: bool
    archetype_override: str | None
    market_value_eur: float | None
    weight_pct: float | None
    total_cost_eur: float | None
    unrealized_pl_eur: float | None
    day_change_pct: float | None


class WorldSummaryOut(BaseModel):
    positions: int
    valued: int
    cost_known: int
    valuation_complete: bool
    total_market_value: float | None
    classified: int
    prices_as_of: date | None


class WorldOut(BaseModel):
    summary: WorldSummaryOut
    assets: list[WorldAssetOut]


@router.get("/world", response_model=WorldOut)
def world(db: DbSession, user: CurrentUser):
    """One building per held ISIN with its valuation, cost and classification.

    Unknown values are null, never zero. No external call: prices come from the portfolio
    service's cache and the sector from what the exposure refresh already stored.
    """
    return build_world(db, user.id)
