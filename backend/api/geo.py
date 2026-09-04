"""Geo-Intel API — signal listing, detail, manual trigger, scheduler control."""

import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import CronKey, CurrentUser
from backend.api.schemas import (
    GeoCheckpointOut,
    GeoCycleRunOut,
    GeoRuleOut,
    GeoRunResult,
    GeoSchedulerStatus,
    GeoSignalOut,
    GeoSignalTickerOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.models import GeoCycleRun, GeoRuleStat, GeoSignal, GeoSignalStatus
from backend.services.geo.rules import RULES_BY_ID, effective_confidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo-intel"])

_404 = {404: {"description": "Not found"}}

_EAGER = (selectinload(GeoSignal.tickers), selectinload(GeoSignal.checkpoints))


def _ev(value) -> str:
    """Return the .value of an enum member, or the raw string."""
    return value.value if hasattr(value, "value") else value


def _as_utc(value: datetime | None) -> datetime | None:
    """Stamp UTC on a timestamp read back from the DB.

    Every DateTime column here is naive and written from
    `datetime.now(timezone.utc)`, so an unstamped value serializes as
    "2026-09-04T10:00:00" and `new Date(...)` in the browser reads it as *local*
    time. Every age the page renders was therefore off by the viewer's offset:
    from Madrid a signal two hours old showed as four, and the checkpoint clock
    drifted the same way. Any timestamp leaving this module goes through here.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _matched_rules(signal: GeoSignal, stats: dict[str, GeoRuleStat]) -> list[GeoRuleOut]:
    """Matched rules with their learned (not just base) confidence.

    effective_confidence = base_confidence + auditor-learned confidence_mod, so
    the "why triggered" panel reflects the rule's actual track record. `stats`
    is batch-loaded once by the caller (see `_load_rule_stats`) to avoid a
    GeoRuleStat query per signal.
    """
    if not signal.matched_rule_ids:
        return []
    try:
        rule_ids = json.loads(signal.matched_rule_ids)
    except ValueError:
        return []
    valid_ids = [rid for rid in rule_ids if rid in RULES_BY_ID]
    return [
        GeoRuleOut(
            id=rid,
            description=RULES_BY_ID[rid].description,
            thesis=RULES_BY_ID[rid].direction,
            confidence=effective_confidence(RULES_BY_ID[rid], stats.get(rid)),
            category=RULES_BY_ID[rid].category,
            trigger=RULES_BY_ID[rid].condition,
        )
        for rid in valid_ids
    ]


def _source_url(raw_json: str | None) -> str | None:
    """Best-effort link to the underlying source event.

    Ingest normalizers stash the event's own page in ``raw_data`` under ``url``
    (USGS, EONET) or ``source_url`` (GDELT). Absent for feeds that don't publish
    a per-event page (fires, meteo, flights, AIS) — return None then. Only http(s)
    links pass, so a malformed value never becomes a broken anchor.
    """
    if not raw_json:
        return None
    try:
        raw = json.loads(raw_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    url = raw.get("url") or raw.get("source_url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    return None


def _load_rule_stats(db: Session, signals: list[GeoSignal]) -> dict[str, GeoRuleStat]:
    """Batch-load GeoRuleStat rows for every rule referenced across `signals`."""
    rule_ids: set[str] = set()
    for s in signals:
        if not s.matched_rule_ids:
            continue
        try:
            rule_ids.update(json.loads(s.matched_rule_ids))
        except ValueError:
            continue
    if not rule_ids:
        return {}
    return {
        row.rule_id: row
        for row in db.query(GeoRuleStat).filter(GeoRuleStat.rule_id.in_(rule_ids)).all()
    }


def _serialize(signal: GeoSignal, stats: dict[str, GeoRuleStat]) -> GeoSignalOut:
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
        rules=_matched_rules(signal, stats),
        checkpoints=[
            GeoCheckpointOut(
                horizon=_ev(c.horizon),
                targetAt=_as_utc(c.target_at),
                score=float(c.score) if c.score is not None else None,
                outcome=_ev(c.outcome) if c.outcome is not None else None,
                detail=c.detail,
                evaluatedAt=_as_utc(c.evaluated_at),
            )
            for c in checkpoints
        ],
        timestamp=_as_utc(signal.created_at),
        status=_ev(signal.status),
        source=signal.source or "",
        sourceUrl=_source_url(signal.raw_json),
    )


def _serialize_run(run: GeoCycleRun | None) -> GeoCycleRunOut | None:
    """Expose one cycle's outcome, including its per-source ingest counts.

    A run whose sources are all zero is an ingest outage rather than a quiet
    world — no calm day leaves USGS, EONET and GDELT simultaneously empty — so
    the counts travel with the run instead of staying in the logs.
    """
    if run is None:
        return None
    sources: dict[str, int] = {}
    if run.sources:
        try:
            parsed = json.loads(run.sources)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            sources = {k: int(v) for k, v in parsed.items() if isinstance(v, int)}
    return GeoCycleRunOut(
        started_at=_as_utc(run.started_at),
        finished_at=_as_utc(run.finished_at),
        ok=bool(run.ok),
        events=run.events or 0,
        new_signals=run.new_signals or 0,
        notified=run.notified or 0,
        checkpoints_evaluated=run.checkpoints_evaluated or 0,
        persist_failures=run.persist_failures or 0,
        sources=sources,
        error=run.error,
    )


def _balance_ids_by_category(rows: list[tuple[int, object]], limit: int) -> list[int]:
    """Fair, category-balanced pick of at most ``limit`` signal ids.

    ``rows`` are (id, display_category) tuples pre-ordered by descending priority
    (importance, then recency). We round-robin across categories, so one
    high-churn category can't consume the whole window and starve sparse ones.
    Fires create a signal per grid cell per day and compound rules up to 3/day,
    so a pure recency (or even pure importance) window fills with fire/compound
    and genuinely-live volcano/conflict/weather never render on the map or feed.

    Within a category the input order is preserved, so each category still
    contributes its most significant signals first.
    """
    from collections import OrderedDict, deque

    buckets: "OrderedDict[object, deque[int]]" = OrderedDict()
    for sig_id, category in rows:
        buckets.setdefault(category, deque()).append(sig_id)

    chosen: list[int] = []
    while len(chosen) < limit and any(buckets.values()):
        for queue in buckets.values():
            if queue:
                chosen.append(queue.popleft())
                if len(chosen) >= limit:
                    break
    return chosen


@router.get("/signals", response_model=list[GeoSignalOut])
def list_signals(
    db: DbSession,
    user: CurrentUser,
    status: str = Query("active", pattern="^(active|resolved|all)$"),
    limit: int = Query(100, le=500),
):
    """List a user's geo signals, balanced across categories, filtered by status.

    The window is chosen so no single high-volume category (fires, compound)
    buries lower-volume but live ones (volcano, conflict, weather). We first rank
    every matching signal by importance then recency in a lightweight (id,
    category) scan — no eager loads — then round-robin across categories up to
    ``limit`` (see `_balance_ids_by_category`), and only then hydrate the chosen
    rows with tickers/checkpoints.
    """
    ranked = db.query(GeoSignal.id, GeoSignal.display_category).filter(
        GeoSignal.user_id == user.id
    )
    if status != "all":
        ranked = ranked.filter(GeoSignal.status == status)
    rows = ranked.order_by(
        GeoSignal.importance.desc(), GeoSignal.created_at.desc()
    ).all()

    chosen_ids = _balance_ids_by_category([(r[0], r[1]) for r in rows], limit)
    if not chosen_ids:
        return []

    signals = (
        db.query(GeoSignal)
        .options(*_EAGER)
        .filter(GeoSignal.id.in_(chosen_ids))
        .order_by(GeoSignal.importance.desc(), GeoSignal.created_at.desc())
        .all()
    )
    stats = _load_rule_stats(db, signals)
    return [_serialize(s, stats) for s in signals]


@router.get("/signals/{signal_id}", response_model=GeoSignalOut, responses=_404)
def get_signal(signal_id: int, db: DbSession, user: CurrentUser):
    signal = (
        db.query(GeoSignal)
        .options(*_EAGER)
        .filter(GeoSignal.id == signal_id, GeoSignal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Señal no encontrada")
    return _serialize(signal, _load_rule_stats(db, [signal]))


@router.post("/run", response_model=GeoRunResult)
def trigger_run(user: CurrentUser):
    """Run inline on request-scoped runtimes; use a local thread otherwise."""
    from backend.services.geo.orchestrator import run_cycle_for_user

    if settings.request_scoped_runtime:
        result = run_cycle_for_user(user.id)
        if result is None:
            raise HTTPException(status_code=500, detail="El ciclo de Geo-Intel ha fallado")
        return GeoRunResult(
            status="completed",
            events=result.events,
            new_signals=result.new_signals,
            notified=result.notified,
        )

    threading.Thread(
        target=run_cycle_for_user, args=(user.id,), daemon=True
    ).start()
    return GeoRunResult(status="started")


@router.post("/cron", include_in_schema=False, dependencies=[CronKey])
def cron_run(db: DbSession):
    """External-cron entry (Cloud Scheduler / any cron): one cycle per user.

    Runs synchronously so the instance stays alive for the cycle. Auth is the
    shared cron secret — see `require_cron_key`.

    A cycle that fails is swallowed by `run_cycle_for_user`, which is right for
    one user out of many but wrong for the caller: this endpoint used to answer
    200 "done" while every cycle blew up, so Cloud Scheduler recorded success and
    the pipeline could stay dead indefinitely without a single failed run. If
    there are users and not one cycle completed, the job hears about it.
    """
    from backend.models import User
    from backend.services.geo.orchestrator import run_cycle_for_user

    user_ids = [uid for (uid,) in db.query(User.id).all()]
    ok = sum(1 for uid in user_ids if run_cycle_for_user(uid) is not None)
    if user_ids and not ok:
        raise HTTPException(
            status_code=500,
            detail=f"Every geo cycle failed ({len(user_ids)} users); see logs",
        )
    return {
        "status": "done",
        "users": len(user_ids),
        "cycles_ok": ok,
        "cycles_failed": len(user_ids) - ok,
    }


@router.post("/scheduler/start")
def start_scheduler(user: CurrentUser):
    from backend.services.geo.scheduler import start_user_schedule

    if settings.request_scoped_runtime:
        raise HTTPException(
            status_code=409,
            detail="In-process schedulers are disabled on request-scoped runtimes",
        )
    start_user_schedule(user.id)
    return {"status": "started", "interval_minutes": settings.geo_monitor_interval_minutes}


@router.post("/scheduler/stop")
def stop_scheduler(user: CurrentUser):
    from backend.services.geo.scheduler import stop_user_schedule

    stop_user_schedule(user.id)
    return {"status": "stopped"}


@router.get("/scheduler/status", response_model=GeoSchedulerStatus)
def scheduler_status(db: DbSession, user: CurrentUser):
    """Signal counts plus the pipeline's own heartbeat.

    ``last_signal_at`` alone cannot say whether the pipeline is alive: a cycle
    that runs and matches nothing leaves exactly the same trace as one that never
    ran. ``last_run`` is the cycle itself — when it ran, whether it finished, what
    each source returned — so a stopped pipeline is visible in the UI on the next
    poll instead of six weeks later.
    """
    from backend.services.geo.scheduler import is_running

    base = db.query(GeoSignal).filter(GeoSignal.user_id == user.id)
    total = base.count()
    active = base.filter(GeoSignal.status == GeoSignalStatus.ACTIVE.value).count()
    latest = base.order_by(GeoSignal.created_at.desc()).first()
    run = (
        db.query(GeoCycleRun)
        .filter(GeoCycleRun.user_id == user.id)
        .order_by(GeoCycleRun.started_at.desc())
        .first()
    )
    return GeoSchedulerStatus(
        running=is_running(user.id),
        external_scheduler=settings.request_scoped_runtime,
        interval_minutes=settings.geo_monitor_interval_minutes,
        total_signals=total,
        active_signals=active,
        last_signal_at=_as_utc(latest.created_at) if latest else None,
        last_run=_serialize_run(run),
    )
