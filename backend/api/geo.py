"""Geo-Intel API — signal listing, detail, manual trigger, scheduler control."""

import hmac
import logging
import threading

from fastapi import APIRouter, HTTPException, Query, Request

from backend.api.auth import CurrentUser
from backend.api.schemas import GeoRunResult, GeoSchedulerStatus, GeoSignalOut
from backend.database import DbSession
from backend.models import GeoSignal, GeoSignalStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo-intel"])

_404 = {404: {"description": "Not found"}}


def _ev(value) -> str:
    """Return the .value of an enum member, or the raw string."""
    return value.value if hasattr(value, "value") else value


def _serialize(signal: GeoSignal) -> GeoSignalOut:
    return GeoSignalOut(
        id=str(signal.id),
        headline=signal.headline,
        category=_ev(signal.display_category),
        eventType=signal.event_type,
        lat=float(signal.lat),
        lng=float(signal.lng),
        location=signal.location or "",
        importance=signal.importance,
        confidence=float(signal.confidence),
        riskScore=float(signal.risk_score),
        direction=_ev(signal.direction),
        tickers=[t.symbol for t in signal.tickers],
        timestamp=signal.created_at,
        status=_ev(signal.status),
    )


@router.get("/signals", response_model=list[GeoSignalOut])
def list_signals(
    db: DbSession,
    user: CurrentUser,
    status: str = Query("active", pattern="^(active|resolved|all)$"),
    limit: int = Query(100, le=500),
):
    """List a user's geo signals (newest first), filtered by status."""
    q = db.query(GeoSignal).filter(GeoSignal.user_id == user.id)
    if status != "all":
        q = q.filter(GeoSignal.status == status)
    signals = q.order_by(GeoSignal.created_at.desc()).limit(limit).all()
    return [_serialize(s) for s in signals]


@router.get("/signals/{signal_id}", response_model=GeoSignalOut, responses=_404)
def get_signal(signal_id: int, db: DbSession, user: CurrentUser):
    signal = (
        db.query(GeoSignal)
        .filter(GeoSignal.id == signal_id, GeoSignal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _serialize(signal)


@router.post("/run", response_model=GeoRunResult)
def trigger_run(user: CurrentUser):
    """Fire one pipeline cycle in the background (a cycle takes ~1 min)."""
    from backend.services.geo.orchestrator import run_cycle_for_user

    threading.Thread(
        target=run_cycle_for_user, args=(user.id,), daemon=True
    ).start()
    return GeoRunResult(status="started")


@router.post("/cron", include_in_schema=False)
def cron_run(request: Request, db: DbSession):
    """External-cron entry (Cloud Scheduler / any cron): one cycle per user.

    The in-process APScheduler dies whenever Cloud Run scales to zero, so prod
    periodicity comes from an external scheduler hitting this endpoint. Auth is
    a shared secret (X-Cron-Key == FINVIEW_CRON_SECRET); empty secret disables
    the endpoint. Runs synchronously so the instance stays alive for the cycle.
    """
    from backend.config import settings

    secret = settings.cron_secret
    provided = request.headers.get("x-cron-key", "")
    if not secret or not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    from backend.models import User
    from backend.services.geo.orchestrator import run_cycle_for_user

    user_ids = [uid for (uid,) in db.query(User.id).all()]
    ok = sum(1 for uid in user_ids if run_cycle_for_user(uid) is not None)
    return {"status": "done", "users": len(user_ids), "cycles_ok": ok}


@router.post("/scheduler/start")
def start_scheduler(user: CurrentUser):
    from backend.config import settings
    from backend.services.geo.scheduler import start_user_schedule

    start_user_schedule(user.id)
    return {"status": "started", "interval_minutes": settings.geo_monitor_interval_minutes}


@router.post("/scheduler/stop")
def stop_scheduler(user: CurrentUser):
    from backend.services.geo.scheduler import stop_user_schedule

    stop_user_schedule(user.id)
    return {"status": "stopped"}


@router.get("/scheduler/status", response_model=GeoSchedulerStatus)
def scheduler_status(db: DbSession, user: CurrentUser):
    from backend.config import settings
    from backend.services.geo.scheduler import is_running

    base = db.query(GeoSignal).filter(GeoSignal.user_id == user.id)
    total = base.count()
    active = base.filter(GeoSignal.status == GeoSignalStatus.ACTIVE.value).count()
    latest = base.order_by(GeoSignal.created_at.desc()).first()
    return GeoSchedulerStatus(
        running=is_running(user.id),
        interval_minutes=settings.geo_monitor_interval_minutes,
        total_signals=total,
        active_signals=active,
        last_signal_at=latest.created_at if latest else None,
    )
