"""Geo-Intel API — signal listing, detail, manual trigger, scheduler control."""

import hmac
import json
import logging
import threading

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    GeoCheckpointOut,
    GeoRuleOut,
    GeoRunResult,
    GeoSchedulerStatus,
    GeoSignalOut,
    GeoSignalTickerOut,
)
from backend.database import DbSession
from backend.models import GeoRuleStat, GeoSignal, GeoSignalStatus
from backend.services.geo.rules import RULES_BY_ID, effective_confidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo-intel"])

_404 = {404: {"description": "Not found"}}

_EAGER = (selectinload(GeoSignal.tickers), selectinload(GeoSignal.checkpoints))


def _ev(value) -> str:
    """Return the .value of an enum member, or the raw string."""
    return value.value if hasattr(value, "value") else value


def _matched_rules(db: Session, signal: GeoSignal) -> list[GeoRuleOut]:
    """Matched rules with their learned (not just base) confidence.

    effective_confidence = base_confidence + auditor-learned confidence_mod, so
    the "why triggered" panel reflects the rule's actual track record.
    """
    if not signal.matched_rule_ids:
        return []
    try:
        rule_ids = json.loads(signal.matched_rule_ids)
    except ValueError:
        return []
    valid_ids = [rid for rid in rule_ids if rid in RULES_BY_ID]
    if not valid_ids:
        return []
    stats = {
        s.rule_id: s
        for s in db.query(GeoRuleStat).filter(GeoRuleStat.rule_id.in_(valid_ids)).all()
    }
    return [
        GeoRuleOut(
            id=rid,
            description=RULES_BY_ID[rid].description,
            thesis=RULES_BY_ID[rid].direction,
            confidence=effective_confidence(RULES_BY_ID[rid], stats.get(rid)),
        )
        for rid in valid_ids
    ]


def _serialize(db: Session, signal: GeoSignal) -> GeoSignalOut:
    checkpoints = sorted(signal.checkpoints, key=lambda c: c.target_at)
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
        tickers=[
            GeoSignalTickerOut(
                symbol=t.symbol,
                direction=_ev(t.direction),
                priceAtSignal=float(t.price_at_signal) if t.price_at_signal is not None else None,
            )
            for t in signal.tickers
        ],
        rules=_matched_rules(db, signal),
        checkpoints=[
            GeoCheckpointOut(
                horizon=_ev(c.horizon),
                targetAt=c.target_at,
                score=float(c.score) if c.score is not None else None,
                outcome=_ev(c.outcome) if c.outcome is not None else None,
                detail=c.detail,
                evaluatedAt=c.evaluated_at,
            )
            for c in checkpoints
        ],
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
    q = db.query(GeoSignal).options(*_EAGER).filter(GeoSignal.user_id == user.id)
    if status != "all":
        q = q.filter(GeoSignal.status == status)
    signals = q.order_by(GeoSignal.created_at.desc()).limit(limit).all()
    return [_serialize(db, s) for s in signals]


@router.get("/signals/{signal_id}", response_model=GeoSignalOut, responses=_404)
def get_signal(signal_id: int, db: DbSession, user: CurrentUser):
    signal = (
        db.query(GeoSignal)
        .options(*_EAGER)
        .filter(GeoSignal.id == signal_id, GeoSignal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _serialize(db, signal)


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
