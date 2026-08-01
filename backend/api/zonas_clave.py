"""Zonas Clave API — watchlist CRUD, analysis retrieval, manual trigger, scheduler control."""

import hmac
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    TechnicalSignalOut,
    ZcZoneOut,
    ZonasClaveAnalysisOut,
    ZonasClaveSchedulerStatus,
    ZonasClaveWatchlistItemIn,
    ZonasClaveWatchlistItemOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.models import TechnicalSignal, ZonasClaveAnalysis, ZonasClaveWatchlistItem
from backend.services import watchlist_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zonas-clave", tags=["zonas-clave"])

_404 = {404: {"description": "Not found"}}


class ZcTickerSearchResult(BaseModel):
    ticker: str
    name: str
    exchange: str


def _analyze_single(item_id: int, ticker: str) -> None:
    """Analyze one ticker and persist the result in an independent session."""
    import json as _json
    from backend.database import SessionLocal
    from backend.models import ZonasClaveAnalysis
    from backend.services.zonas_clave_analyzer import analyze_ticker

    result = analyze_ticker(ticker)
    if result is None:
        return
    row = ZonasClaveAnalysis(
        watchlist_item_id=item_id,
        timestamp=datetime.now(timezone.utc),
        zones=_json.dumps(result["zones"]),
        trend_bias_bullish_pct=result["trend_bias_bullish_pct"],
        trend_bias_bearish_pct=result["trend_bias_bearish_pct"],
        rsi=result["rsi"],
        macd_signal=result["macd_signal"],
        macd_histogram=result["macd_histogram"],
        price_history=_json.dumps(result["price_history"]),
        current_price=result["current_price"],
    )
    with SessionLocal() as db:
        db.add(row)
        db.commit()


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

    _, item = watchlist_service.enable_zonas(db, user.id, body.ticker, body.name)
    try:
        db.commit()
    except IntegrityError:
        # Lost a concurrent insert race on the canonical (user, ticker) row —
        # e.g. the options auto-sync following the same new ticker. Treat as
        # already-followed, same as the pre-check.
        db.rollback()
        raise HTTPException(status_code=409, detail="Ticker already in Zonas Clave watchlist")
    db.refresh(item)

    if settings.request_scoped_runtime:
        try:
            _analyze_single(item.id, item.ticker)
        except Exception as exc:  # noqa: BLE001 - resource was already committed
            logger.warning(
                "single ticker analysis failed after create: %s",
                exc.__class__.__name__,
            )
    else:
        threading.Thread(
            target=_analyze_single, args=[item.id, item.ticker], daemon=True
        ).start()

    return item


@router.get("/search", response_model=list[ZcTickerSearchResult])
def search_tickers(q: str, user: CurrentUser):
    """Live global ticker search (Yahoo Finance) for the add-ticker search box."""
    from backend.services.zonas_clave_analyzer import search_tickers as _search

    return _search(q)


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
    watchlist_service.disable_zonas(db, user.id, item)
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
    item_ids_sq = (
        db.query(ZonasClaveWatchlistItem.id)
        .filter(ZonasClaveWatchlistItem.user_id == user.id)
        .subquery()
    )
    latest_ids_sq = (
        db.query(func.max(ZonasClaveAnalysis.id))
        .filter(ZonasClaveAnalysis.watchlist_item_id.in_(item_ids_sq))
        .group_by(ZonasClaveAnalysis.watchlist_item_id)
        .subquery()
    )
    rows = (
        db.query(ZonasClaveAnalysis)
        .filter(ZonasClaveAnalysis.id.in_(latest_ids_sq))
        .all()
    )
    return [_parse_analysis(row) for row in rows]


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
    """Recalculate inline on request-scoped runtimes, in a local thread otherwise."""
    from backend.services.zonas_clave_analyzer import run_analysis_for_user

    if settings.request_scoped_runtime:
        result = run_analysis_for_user(user.id)
        return {"status": "completed", **result}

    threading.Thread(
        target=run_analysis_for_user, args=[user.id], daemon=True
    ).start()
    return {"status": "started"}


@router.post("/cron", include_in_schema=False)
def cron_run(request: Request, db: DbSession):
    """External-cron entry (Cloud Scheduler / any cron): one analysis per user.

    Third instance of the same rule as /api/geo/cron and /api/options/agent/cron:
    the in-process APScheduler dies whenever Cloud Run scales to zero, so prod
    periodicity comes from an external scheduler. Auth is the shared secret
    (X-Cron-Key == FINVIEW_CRON_SECRET); empty secret disables the endpoint. Runs
    synchronously so the instance stays alive for the work.

    This only started mattering once the technical analysis began emitting
    signals — before that a missed cycle cost nothing, since nobody was waiting
    on the output.
    """
    secret = settings.cron_secret
    provided = request.headers.get("x-cron-key", "")
    if not secret or not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    from backend.models import User
    from backend.services.reference_data_maintenance import (
        run_reference_data_maintenance,
    )
    from backend.services.zonas_clave_analyzer import run_analysis_for_user

    # This job runs once each market day, so reference refreshes stay out of the
    # 10/15-minute cycles and cannot form a costly retry loop.
    run_reference_data_maintenance()

    user_ids = [uid for (uid,) in db.query(User.id).all()]
    analyzed = signals = alerts = 0
    for uid in user_ids:
        try:
            result = run_analysis_for_user(uid)
        except Exception:
            # run_analysis_for_user handles per-ticker failures itself; this
            # guards the cycle so one user's blow-up doesn't skip the rest.
            logger.exception("zonas cron cycle failed for user %d", uid)
            continue
        analyzed += result.get("analyzed", 0)
        signals += result.get("signals", 0)
        alerts += result.get("alerts", 0)

    return {
        "status": "done",
        "users": len(user_ids),
        "analyzed": analyzed,
        "signals": signals,
        "alerts": alerts,
    }


# ── Technical signals ────────────────────────────────────────────────


@router.get("/signals", response_model=list[TechnicalSignalOut])
def list_technical_signals(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
    alerted_only: bool = False,
    days: int = 7,
    limit: int = 100,
):
    """Technical signals for the user, newest first.

    Defaults to everything scored in the window, not just alerting rows:
    `alerted_only=true` is what the Monitor asks for, while the unfiltered view
    is what makes the threshold auditable (see TechnicalSignal's docstring).
    """
    q = db.query(TechnicalSignal).filter(
        TechnicalSignal.user_id == user.id,
        TechnicalSignal.created_at >= datetime.now(timezone.utc) - timedelta(days=days),
    )
    if ticker:
        q = q.filter(TechnicalSignal.ticker == ticker.upper())
    if alerted_only:
        q = q.filter(TechnicalSignal.alerted.is_(True))
    return q.order_by(TechnicalSignal.created_at.desc()).limit(limit).all()


# ── Scheduler control ────────────────────────────────────────────────


@router.post("/scheduler/start")
def start_scheduler(user: CurrentUser):
    from backend.services.zonas_clave_scheduler import start_user_schedule

    if settings.request_scoped_runtime:
        raise HTTPException(
            status_code=409,
            detail="In-process schedulers are disabled on request-scoped runtimes",
        )
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
        external_scheduler=settings.request_scoped_runtime,
        last_run=latest_analysis.timestamp if latest_analysis else None,
        total_items=total,
    )
