"""Zonas Clave API — watchlist CRUD, analysis retrieval, manual trigger, scheduler control."""

import json
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    ZcZoneOut,
    ZonasClaveAnalysisOut,
    ZonasClaveSchedulerStatus,
    ZonasClaveWatchlistItemIn,
    ZonasClaveWatchlistItemOut,
)
from backend.database import DbSession
from backend.models import ZonasClaveAnalysis, ZonasClaveWatchlistItem

router = APIRouter(prefix="/zonas-clave", tags=["zonas-clave"])

_404 = {404: {"description": "Not found"}}


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_analysis(row: ZonasClaveAnalysis) -> ZonasClaveAnalysisOut:
    zones = [ZcZoneOut(**z) for z in json.loads(row.zones or "[]")]
    history = json.loads(row.price_history or "[]")
    return ZonasClaveAnalysisOut(
        id=row.id,
        watchlist_item_id=row.watchlist_item_id,
        timestamp=row.timestamp,
        zones=zones,
        trend_bias_bullish_pct=float(row.trend_bias_bullish_pct) if row.trend_bias_bullish_pct is not None else None,
        trend_bias_bearish_pct=float(row.trend_bias_bearish_pct) if row.trend_bias_bearish_pct is not None else None,
        rsi=float(row.rsi) if row.rsi is not None else None,
        macd_signal=row.macd_signal,
        macd_histogram=float(row.macd_histogram) if row.macd_histogram is not None else None,
        current_price=float(row.current_price) if row.current_price is not None else None,
        price_history=history,
    )


def _latest_analysis(db, item_id: int) -> ZonasClaveAnalysis | None:
    return (
        db.query(ZonasClaveAnalysis)
        .filter(ZonasClaveAnalysis.watchlist_item_id == item_id)
        .order_by(ZonasClaveAnalysis.timestamp.desc())
        .first()
    )


# ── Watchlist CRUD ───────────────────────────────────────────────────


@router.get("/watchlist", response_model=list[ZonasClaveWatchlistItemOut])
def list_watchlist(db: DbSession, user: CurrentUser):
    return (
        db.query(ZonasClaveWatchlistItem)
        .filter(ZonasClaveWatchlistItem.user_id == user.id)
        .order_by(ZonasClaveWatchlistItem.added_at)
        .all()
    )


@router.post(
    "/watchlist",
    response_model=ZonasClaveWatchlistItemOut,
    status_code=201,
    responses={409: {"description": "Ticker already in watchlist"}},
)
def add_ticker(body: ZonasClaveWatchlistItemIn, db: DbSession, user: CurrentUser):
    existing = (
        db.query(ZonasClaveWatchlistItem)
        .filter(
            ZonasClaveWatchlistItem.user_id == user.id,
            ZonasClaveWatchlistItem.ticker == body.ticker.upper(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ticker already in Zonas Clave watchlist")

    item = ZonasClaveWatchlistItem(
        user_id=user.id,
        ticker=body.ticker.upper(),
        name=body.name,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Kick off initial analysis in background so the user sees data quickly
    from backend.services.zonas_clave_analyzer import run_analysis_for_user

    threading.Thread(
        target=run_analysis_for_user, args=[user.id], daemon=True
    ).start()

    return item


@router.delete("/watchlist/{item_id}", status_code=204, responses=_404)
def remove_ticker(item_id: int, db: DbSession, user: CurrentUser):
    item = (
        db.query(ZonasClaveWatchlistItem)
        .filter(
            ZonasClaveWatchlistItem.id == item_id,
            ZonasClaveWatchlistItem.user_id == user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()


# ── Analysis retrieval ───────────────────────────────────────────────


@router.get("/analysis/{ticker}", response_model=ZonasClaveAnalysisOut, responses=_404)
def get_analysis(ticker: str, db: DbSession, user: CurrentUser):
    item = (
        db.query(ZonasClaveWatchlistItem)
        .filter(
            ZonasClaveWatchlistItem.user_id == user.id,
            ZonasClaveWatchlistItem.ticker == ticker.upper(),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ticker not in Zonas Clave watchlist")

    row = _latest_analysis(db, item.id)
    if not row:
        raise HTTPException(status_code=404, detail="No analysis computed yet")

    return _parse_analysis(row)


@router.get("/analysis", response_model=list[ZonasClaveAnalysisOut])
def list_analyses(db: DbSession, user: CurrentUser):
    items = (
        db.query(ZonasClaveWatchlistItem)
        .filter(ZonasClaveWatchlistItem.user_id == user.id)
        .all()
    )
    results = []
    for item in items:
        row = _latest_analysis(db, item.id)
        if row:
            results.append(_parse_analysis(row))
    return results


# ── Manual trigger ───────────────────────────────────────────────────


@router.post("/analyze/{ticker}", responses=_404)
def trigger_analysis(ticker: str, db: DbSession, user: CurrentUser):
    """Trigger analysis for a single ticker synchronously."""
    item = (
        db.query(ZonasClaveWatchlistItem)
        .filter(
            ZonasClaveWatchlistItem.user_id == user.id,
            ZonasClaveWatchlistItem.ticker == ticker.upper(),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ticker not in Zonas Clave watchlist")

    from backend.services.zonas_clave_analyzer import analyze_ticker

    result = analyze_ticker(item.ticker)
    if not result:
        raise HTTPException(status_code=502, detail="Analysis failed — check ticker validity")

    row = ZonasClaveAnalysis(
        watchlist_item_id=item.id,
        timestamp=datetime.now(timezone.utc),
        zones=json.dumps(result["zones"]),
        trend_bias_bullish_pct=result["trend_bias_bullish_pct"],
        trend_bias_bearish_pct=result["trend_bias_bearish_pct"],
        rsi=result["rsi"],
        macd_signal=result["macd_signal"],
        macd_histogram=result["macd_histogram"],
        price_history=json.dumps(result["price_history"]),
        current_price=result["current_price"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _parse_analysis(row)


@router.post("/analyze-all")
def trigger_all(user: CurrentUser):
    """Trigger full recalculation for all user's tickers in background."""
    from backend.services.zonas_clave_analyzer import run_analysis_for_user

    threading.Thread(
        target=run_analysis_for_user, args=[user.id], daemon=True
    ).start()
    return {"status": "started"}


# ── Scheduler control ────────────────────────────────────────────────


@router.post("/scheduler/start")
def start_scheduler(user: CurrentUser):
    from backend.services.zonas_clave_scheduler import start_user_schedule

    start_user_schedule(user.id)
    return {"status": "started", "interval_hours": 24}


@router.post("/scheduler/stop")
def stop_scheduler(user: CurrentUser):
    from backend.services.zonas_clave_scheduler import stop_user_schedule

    stop_user_schedule(user.id)
    return {"status": "stopped"}


@router.get("/scheduler/status", response_model=ZonasClaveSchedulerStatus)
def scheduler_status(db: DbSession, user: CurrentUser):
    from backend.services.zonas_clave_scheduler import is_running

    total = (
        db.query(ZonasClaveWatchlistItem)
        .filter(ZonasClaveWatchlistItem.user_id == user.id)
        .count()
    )
    latest_analysis = (
        db.query(ZonasClaveAnalysis)
        .join(ZonasClaveWatchlistItem)
        .filter(ZonasClaveWatchlistItem.user_id == user.id)
        .order_by(ZonasClaveAnalysis.timestamp.desc())
        .first()
    )
    return ZonasClaveSchedulerStatus(
        running=is_running(user.id),
        last_run=latest_analysis.timestamp if latest_analysis else None,
        total_items=total,
    )
