"""Geo-Intel API — signal listing, detail, manual trigger, scheduler control."""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import CronKey, CurrentUser
from backend.api.schemas import (
    GeoAccuracyOut,
    GeoCheckpointOut,
    GeoMacroOut,
    GeoCycleRunOut,
    GeoHorizonAccuracy,
    GeoRuleAccuracy,
    GeoRuleOut,
    GeoRuleStatsReset,
    GeoRunResult,
    GeoSchedulerStatus,
    GeoSignalOut,
    GeoSignalTickerOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.models import (
    GeoCheckpoint,
    GeoCycleRun,
    GeoHorizon,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
)
from backend.services.geo.owner import geo_owner_id
from backend.services.geo.rules import RULES_BY_ID, effective_confidence, rule_scope, INSTRUMENT_TRADABILITY

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
            thesis=RULES_BY_ID[rid].thesis,
            scope=rule_scope(RULES_BY_ID[rid]),
            confidence=effective_confidence(RULES_BY_ID[rid], stats.get(rid)),
            category=RULES_BY_ID[rid].category,
            trigger=RULES_BY_ID[rid].condition,
        )
        for rid in valid_ids
    ]


def _raw(raw_json: str | None) -> dict:
    if not raw_json:
        return {}
    try:
        raw = json.loads(raw_json)
    except (ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


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
                tradability=INSTRUMENT_TRADABILITY.get(t.symbol, ("cash_eu", ""))[0],
                alternate=INSTRUMENT_TRADABILITY.get(t.symbol, ("cash_eu", ""))[1] or None,
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
        notifiedAt=_as_utc(signal.notified_at),
        status=_ev(signal.status),
        source=signal.source or "",
        sourceUrl=_source_url(signal.raw_json),
        generated=bool(_raw(signal.raw_json).get("generated")),
        narrative=(_raw(signal.raw_json).get("llmNarrative") or None),
        thesis=(_raw(signal.raw_json).get("llmThesis") or None),
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
        notify_failed=run.notify_failed or 0,
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
    """List the shared geo signals, balanced across categories, filtered by status.

    Every account reads the same rows — the system owner's (`geo/owner.py`);
    ``user`` is the auth gate, not a filter.

    The window is chosen so no single high-volume category (fires, compound)
    buries lower-volume but live ones (volcano, conflict, weather). We first rank
    every matching signal by importance then recency in a lightweight (id,
    category) scan — no eager loads — then round-robin across categories up to
    ``limit`` (see `_balance_ids_by_category`), and only then hydrate the chosen
    rows with tickers/checkpoints.
    """
    ranked = db.query(GeoSignal.id, GeoSignal.display_category).filter(
        GeoSignal.user_id == geo_owner_id(db)
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
        .filter(GeoSignal.id == signal_id, GeoSignal.user_id == geo_owner_id(db))
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Señal no encontrada")
    return _serialize(signal, _load_rule_stats(db, [signal]))


_ACCURACY_WINDOW_DAYS = 30

# The outcome names as BacktestOutcome stores them, mapped to the response field
# each one feeds. Anything else the column might hold is ignored rather than
# guessed at.
_OUTCOME_FIELD = {
    "CORRECT": "correct",
    "INCORRECT": "incorrect",
    "NEUTRAL": "neutral",
}


def _naive_utc(value: datetime) -> datetime:
    """Drop to naive UTC for comparison against the DB's naive columns."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/accuracy", response_model=GeoAccuracyOut)
def accuracy(
    db: DbSession,
    user: CurrentUser,
    since: datetime | None = Query(None, description="ISO date; default 30 days ago"),
):
    """Hit rate per checkpoint horizon plus the per-rule learning table.

    Nothing aggregated this before: the only reading of the loop's accuracy was
    five 3.5 px dots per signal, so a scorer that was comparing a daily close
    against itself could fail 4374 checkpoints at exactly 0 without anyone
    seeing a number. The window defaults to 30 days because the pre-2026-09-06
    history was scored by that broken comparison and is not evidence about the
    rules.

    ``accuracy`` is correct / (correct + incorrect) — NEUTRAL is excluded on
    purpose, because "no measurable move" is not a failed thesis. ``pending``
    is ``outcome IS NULL`` and is counted regardless of the window: a checkpoint
    that has never resolved has no date to filter on, and an evaluated-but-null
    row is pending too, not a neutral one.

    Checkpoints belong to the system owner like the signals; the rule table is
    global — see ``reset_rule_stats``.
    """
    since_dt = since or datetime.now(timezone.utc) - timedelta(days=_ACCURACY_WINDOW_DAYS)
    cutoff = _naive_utc(since_dt)

    buckets = {h.value: GeoHorizonAccuracy() for h in GeoHorizon}

    # One grouped scan, not a query per horizon: (horizon, outcome) -> count.
    rows = (
        db.query(
            GeoCheckpoint.horizon,
            GeoCheckpoint.outcome,
            func.count(GeoCheckpoint.id),
        )
        .filter(
            GeoCheckpoint.user_id == geo_owner_id(db),
            or_(GeoCheckpoint.outcome.is_(None), GeoCheckpoint.evaluated_at >= cutoff),
        )
        .group_by(GeoCheckpoint.horizon, GeoCheckpoint.outcome)
        .all()
    )
    for horizon, outcome, count in rows:
        bucket = buckets.get(_ev(horizon))
        if bucket is None:
            continue
        if outcome is None:
            bucket.pending += int(count)
            continue
        field = _OUTCOME_FIELD.get(_ev(outcome))
        if field:
            setattr(bucket, field, getattr(bucket, field) + int(count))

    for bucket in buckets.values():
        measured = bucket.correct + bucket.incorrect
        bucket.accuracy = bucket.correct / measured if measured else None

    stats = db.query(GeoRuleStat).order_by(GeoRuleStat.total_signals.desc()).all()
    return GeoAccuracyOut(
        since=_as_utc(since_dt),
        horizons=buckets,
        rules=[
            GeoRuleAccuracy(
                ruleId=row.rule_id,
                category=row.category,
                baseConfidence=float(row.base_confidence),
                confidenceMod=float(row.confidence_mod or 0),
                totalSignals=row.total_signals or 0,
                correctSignals=row.correct_signals or 0,
                accuracy=float(row.accuracy) if row.accuracy is not None else None,
            )
            for row in stats
        ],
    )


@router.post("/rule-stats/reset", response_model=GeoRuleStatsReset)
def reset_rule_stats(db: DbSession, user: CurrentUser):
    """Zero every learned adjustment in `geo_rule_stats`.

    **The table is global, not per user** — there is one row per rule for the
    whole installation, so this resets the learning for everybody. That is
    acceptable today because this is a personal tool with one owner; it is not
    acceptable the moment a second tenant matters, and there is no UI for it for
    the same reason.

    It exists because the loop had no escape hatch: `seed_rule_stats` never
    overwrites, so two rules pinned at the -0.30 `confidence_mod` floor by
    checkpoints the old scorer failed by construction would stay pinned forever.
    `base_confidence` is static rule data and is deliberately left alone.
    """
    n = (
        db.query(GeoRuleStat)
        .update(
            {
                GeoRuleStat.confidence_mod: 0,
                GeoRuleStat.total_signals: 0,
                GeoRuleStat.correct_signals: 0,
                GeoRuleStat.accuracy: None,
                GeoRuleStat.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    logger.warning("geo_rule_stats reset by user %s — %d rows zeroed", user.id, n)
    return GeoRuleStatsReset(reset=n)


@router.post("/run", response_model=GeoRunResult)
def trigger_run(db: DbSession, user: CurrentUser):
    """Run the shared cycle inline on request-scoped runtimes; a local thread otherwise."""
    from backend.services.geo.orchestrator import run_cycle_for_user

    owner = geo_owner_id(db)
    if settings.request_scoped_runtime:
        result = run_cycle_for_user(owner)
        if result is None:
            raise HTTPException(status_code=500, detail="El ciclo de Geo-Intel ha fallado")
        return GeoRunResult(
            status="completed",
            events=result.events,
            new_signals=result.new_signals,
            notified=result.notified,
        )

    threading.Thread(
        target=run_cycle_for_user, args=(owner,), daemon=True
    ).start()
    return GeoRunResult(status="started")


@router.post("/cron", include_in_schema=False, dependencies=[CronKey])
def cron_run(db: DbSession):
    """External-cron entry (Cloud Scheduler / any cron): the one shared cycle.

    Runs synchronously so the instance stays alive for the cycle. Auth is the
    shared cron secret — see `require_cron_key`.

    The cycle runs for the system owner, whatever the number of accounts (see
    `geo/owner.py`). `run_cycle_for_user` swallows its exception and returns
    None, which is right for the log and wrong for the caller: this endpoint
    used to answer 200 "done" while the cycle blew up, so Cloud Scheduler
    recorded success and the pipeline could stay dead indefinitely without a
    single failed run. A failed cycle is a failed job.
    """
    from backend.services.geo.orchestrator import run_cycles

    (result,) = run_cycles([geo_owner_id(db)])
    if result is None:
        raise HTTPException(status_code=500, detail="The geo cycle failed; see logs")
    return {"status": "done", "cycles_ok": 1, "cycles_failed": 0}


@router.post("/scheduler/start")
def start_scheduler(db: DbSession, user: CurrentUser):
    from backend.services.geo.scheduler import start_user_schedule

    if settings.request_scoped_runtime:
        raise HTTPException(
            status_code=409,
            detail="In-process schedulers are disabled on request-scoped runtimes",
        )
    start_user_schedule(geo_owner_id(db))
    return {"status": "started", "interval_minutes": settings.geo_monitor_interval_minutes}


@router.post("/scheduler/stop")
def stop_scheduler(db: DbSession, user: CurrentUser):
    from backend.services.geo.scheduler import stop_user_schedule

    stop_user_schedule(geo_owner_id(db))
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

    owner = geo_owner_id(db)
    base = db.query(GeoSignal).filter(GeoSignal.user_id == owner)
    total = base.count()
    active = base.filter(GeoSignal.status == GeoSignalStatus.ACTIVE.value).count()
    latest = base.order_by(GeoSignal.created_at.desc()).first()
    run = (
        db.query(GeoCycleRun)
        .filter(GeoCycleRun.user_id == owner)
        .order_by(GeoCycleRun.started_at.desc())
        .first()
    )
    return GeoSchedulerStatus(
        running=is_running(owner),
        external_scheduler=settings.request_scoped_runtime,
        interval_minutes=settings.geo_monitor_interval_minutes,
        total_signals=total,
        active_signals=active,
        last_signal_at=_as_utc(latest.created_at) if latest else None,
        last_run=_serialize_run(run),
        macro=_macro_snapshot(),
    )


def _macro_snapshot() -> dict | None:
    try:
        from backend.services.macro_context import macro_context

        snapshot = macro_context()
        return GeoMacroOut(**snapshot) if snapshot else None
    except Exception:
        logger.warning("geo status: macro snapshot unavailable", exc_info=True)
        return None
