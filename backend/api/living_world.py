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
    # "open", or "closed": sold out of; drawn in ruins, with what the ledger says about it.
    status: str
    closed_on: date | None
    invested_eur: float | None
    sold_eur: float | None
    dividends_eur: float | None


class WorldSummaryOut(BaseModel):
    positions: int
    valued: int
    cost_known: int
    valuation_complete: bool
    total_market_value: float | None
    classified: int
    closed: int
    prices_as_of: date | None


class WorldEventOut(BaseModel):
    """A fact the town shows as activity: a stored daily move or a ledger entry."""

    id: str
    event_type: str
    isin: str
    name: str
    occurred_on: date
    # ISO-8601 UTC when the source knows the moment (a geo alert, a Zonas Clave alert); null
    # for what only has a date.
    occurred_at: str | None = None
    source_type: str
    confidence: str
    metrics: dict[str, float | str | None]


class WorldOut(BaseModel):
    summary: WorldSummaryOut
    assets: list[WorldAssetOut]
    events: list[WorldEventOut]


@router.get("/world", response_model=WorldOut)
def world(db: DbSession, user: CurrentUser):
    """One building per held ISIN with its valuation, cost and classification, and the
    last week's real events: daily moves of at least 2 %, buys, sells, dividends, and what
    other features stored (Zonas Clave history and alerts, splits, annual reports, geo).

    Unknown values are null, never zero. No external call: prices come from the portfolio
    service's cache and the sector from what the exposure refresh already stored.
    """
    return build_world(db, user.id)
