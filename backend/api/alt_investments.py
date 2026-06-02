"""API endpoints for alternative-investments tracking (private banking).

MVP: manual entry of PE/VC/Real-Estate (and other) positions with
committed/called/distributed/NAV aggregates, plus a consolidation summary
that derives the standard PE metrics (TVPI, DPI, RVPI, unfunded).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.models import AltInvestment, AltInvestmentStatus, AltInvestmentType

router = APIRouter(prefix="/alt-investments", tags=["alt-investments"])

_TYPES = {t.value for t in AltInvestmentType}
_STATUSES = {s.value for s in AltInvestmentStatus}


# --------------- schemas ---------------


class AltInvestmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str
    status: str = AltInvestmentStatus.ACTIVE.value
    manager: str = ""
    isin: str | None = None
    vintage_year: int | None = None
    geography: str = ""
    currency: str = "EUR"
    committed_capital: Decimal = Decimal(0)
    called_capital: Decimal = Decimal(0)
    distributed_capital: Decimal = Decimal(0)
    current_nav: Decimal = Decimal(0)
    notes: str = ""


class AltInvestmentUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    status: str | None = None
    manager: str | None = None
    isin: str | None = None
    vintage_year: int | None = None
    geography: str | None = None
    currency: str | None = None
    committed_capital: Decimal | None = None
    called_capital: Decimal | None = None
    distributed_capital: Decimal | None = None
    current_nav: Decimal | None = None
    notes: str | None = None


class AltInvestmentOut(BaseModel):
    id: int
    name: str
    type: str
    status: str
    manager: str
    isin: str | None
    vintage_year: int | None
    geography: str
    currency: str
    committed_capital: Decimal
    called_capital: Decimal
    distributed_capital: Decimal
    current_nav: Decimal
    notes: str
    # Derived metrics
    unfunded: Decimal
    total_value: Decimal
    tvpi: float | None
    dpi: float | None
    rvpi: float | None

    model_config = {"from_attributes": True}


class AltAllocationSlice(BaseModel):
    label: str
    value: Decimal
    pct: float


class AltSummary(BaseModel):
    count: int
    total_committed: Decimal
    total_called: Decimal
    total_distributed: Decimal
    total_nav: Decimal
    total_unfunded: Decimal
    total_value: Decimal
    overall_tvpi: float | None
    overall_dpi: float | None
    overall_rvpi: float | None
    by_type: list[AltAllocationSlice]
    by_geography: list[AltAllocationSlice]
    by_currency: list[AltAllocationSlice]


class CatalogSearchResult(BaseModel):
    name: str
    type: str
    manager: str
    isin: str | None
    source: str
    nav: float | None = None
    fund_size: float | None = None
    data_date: str | None = None


# --------------- helpers ---------------


def _metrics(called: Decimal, distributed: Decimal, nav: Decimal):
    """Return (tvpi, dpi, rvpi) — None when there's no called capital."""
    if called and called > 0:
        return (
            float((distributed + nav) / called),
            float(distributed / called),
            float(nav / called),
        )
    return None, None, None


def _to_out(inv: AltInvestment) -> AltInvestmentOut:
    unfunded = inv.committed_capital - inv.called_capital
    total_value = inv.distributed_capital + inv.current_nav
    tvpi, dpi, rvpi = _metrics(
        inv.called_capital, inv.distributed_capital, inv.current_nav
    )
    return AltInvestmentOut(
        id=inv.id,
        name=inv.name,
        type=inv.type,
        status=inv.status,
        manager=inv.manager,
        isin=inv.isin,
        vintage_year=inv.vintage_year,
        geography=inv.geography,
        currency=inv.currency,
        committed_capital=inv.committed_capital,
        called_capital=inv.called_capital,
        distributed_capital=inv.distributed_capital,
        current_nav=inv.current_nav,
        notes=inv.notes,
        unfunded=unfunded,
        total_value=total_value,
        tvpi=tvpi,
        dpi=dpi,
        rvpi=rvpi,
    )


def _validate_enums(type_: str | None, status_: str | None) -> None:
    if type_ is not None and type_ not in _TYPES:
        raise HTTPException(400, f"Invalid type. Must be one of: {sorted(_TYPES)}")
    if status_ is not None and status_ not in _STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {sorted(_STATUSES)}")


def _allocation(items: list[AltInvestment], key) -> list[AltAllocationSlice]:
    """Allocation by current NAV grouped by `key(inv)`."""
    buckets: dict[str, Decimal] = {}
    for inv in items:
        label = key(inv) or "—"
        buckets[label] = buckets.get(label, Decimal(0)) + inv.current_nav
    total = sum(buckets.values())
    slices = [
        AltAllocationSlice(
            label=label,
            value=value,
            pct=float(value / total * 100) if total else 0.0,
        )
        for label, value in buckets.items()
    ]
    slices.sort(key=lambda s: s.value, reverse=True)
    return slices


# --------------- routes ---------------


@router.get("", response_model=list[AltInvestmentOut], include_in_schema=False)
@router.get("/", response_model=list[AltInvestmentOut])
def list_alt_investments(db: DbSession, user: CurrentUser):
    """List all alternative-investment positions for the current user."""
    items = (
        db.query(AltInvestment)
        .filter(AltInvestment.user_id == user.id)
        .order_by(AltInvestment.created_at.desc())
        .all()
    )
    return [_to_out(i) for i in items]


@router.get("/summary", response_model=AltSummary)
def alt_summary(db: DbSession, user: CurrentUser):
    """Consolidated view across all positions (NAV-weighted allocations)."""
    items = db.query(AltInvestment).filter(AltInvestment.user_id == user.id).all()

    committed = sum((i.committed_capital for i in items), Decimal(0))
    called = sum((i.called_capital for i in items), Decimal(0))
    distributed = sum((i.distributed_capital for i in items), Decimal(0))
    nav = sum((i.current_nav for i in items), Decimal(0))
    tvpi, dpi, rvpi = _metrics(called, distributed, nav)

    return AltSummary(
        count=len(items),
        total_committed=committed,
        total_called=called,
        total_distributed=distributed,
        total_nav=nav,
        total_unfunded=committed - called,
        total_value=distributed + nav,
        overall_tvpi=tvpi,
        overall_dpi=dpi,
        overall_rvpi=rvpi,
        by_type=_allocation(items, lambda i: i.type),
        by_geography=_allocation(items, lambda i: i.geography),
        by_currency=_allocation(items, lambda i: i.currency),
    )


@router.get("/search", response_model=list[CatalogSearchResult])
def search_catalog_endpoint(
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    type: str | None = None,
    min_fund_size: float | None = None,
    max_fund_size: float | None = None,
    sort: str = "name",
    limit: int = 20,
):
    """Search/browse the CNMV catalog of regulated Spanish funds to pre-fill the form.

    Matches by name (substring) or exact ISIN. With a short/empty `q` it still
    browses when a filter (`type`, `min_fund_size`, `max_fund_size`) or non-default
    `sort` (`fund_size_desc` | `nav_desc` | `nav_asc`) is given. Results include the
    fund's latest NAV and fund size (CNMV `FONDMENS`, FI funds only).
    """
    from backend.services.cnmv_catalog import search_catalog

    if type is not None and type not in _TYPES:
        raise HTTPException(400, f"Invalid type. Must be one of: {sorted(_TYPES)}")
    return search_catalog(
        db, q, type_filter=type, min_fund_size=min_fund_size,
        max_fund_size=max_fund_size, sort=sort, limit=min(limit, 50),
    )


@router.post("/", response_model=AltInvestmentOut, status_code=status.HTTP_201_CREATED)
def create_alt_investment(data: AltInvestmentCreate, db: DbSession, user: CurrentUser):
    """Create a new alternative-investment position."""
    _validate_enums(data.type, data.status)
    inv = AltInvestment(
        user_id=user.id,
        name=data.name,
        type=data.type,
        status=data.status,
        manager=data.manager,
        isin=data.isin,
        vintage_year=data.vintage_year,
        geography=data.geography,
        currency=data.currency,
        committed_capital=data.committed_capital,
        called_capital=data.called_capital,
        distributed_capital=data.distributed_capital,
        current_nav=data.current_nav,
        notes=data.notes,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _to_out(inv)


@router.patch("/{inv_id}", response_model=AltInvestmentOut)
def update_alt_investment(
    inv_id: int, data: AltInvestmentUpdate, db: DbSession, user: CurrentUser
):
    """Update an alternative-investment position."""
    inv = (
        db.query(AltInvestment)
        .filter(AltInvestment.id == inv_id, AltInvestment.user_id == user.id)
        .first()
    )
    if not inv:
        raise HTTPException(404, "Alt investment not found")

    _validate_enums(data.type, data.status)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)

    db.commit()
    db.refresh(inv)
    return _to_out(inv)


@router.delete("/{inv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alt_investment(inv_id: int, db: DbSession, user: CurrentUser):
    """Delete an alternative-investment position."""
    inv = (
        db.query(AltInvestment)
        .filter(AltInvestment.id == inv_id, AltInvestment.user_id == user.id)
        .first()
    )
    if not inv:
        raise HTTPException(404, "Alt investment not found")
    db.delete(inv)
    db.commit()
