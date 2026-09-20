"""Orchestrator — the per-user geo pipeline cycle.

ingest → sentinel + specialist analysts → (compound rules) → analyst → advisor →
persist signals + checkpoints → notify → evaluate pending outcomes.

Async at the ingest boundary (httpx); the DB/scoring work is synchronous (SQLAlchemy).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import GeoCycleRun, GeoRuleStat, GeoSignal, GeoSignalStatus

from . import sentinel
from .advisor import IMPORTANCE_THRESHOLD, SignalResult, compute_importance, generate_signal
from .analyst import AnalystResult, AnalystTicker, analyze_event
from .auditor import create_checkpoints, evaluate_pending
from .ingest import fetch_all_sources
from .notify import notify_signal
from .rules import RULES_BY_ID, compute_risk, seed_rule_stats
from .sentinel import GeoEvent

logger = logging.getLogger(__name__)

# Compound-rule ticker buckets (an event counts in a bucket if its basket overlaps).
_ENERGY = {"USO", "UNG", "XLE", "XOM", "CVX"}
_FOOD = {"DBA", "WEAT", "SOYB", "ZC=F", "KC=F"}
_CONFLICT = {"LMT", "RTX", "NOC", "ITA"}
_COMPOUND_BUCKETS = {
    "compound-energy-crisis": _ENERGY,
    "compound-food-crisis": _FOOD,
    "compound-geopolitical-escalation": _CONFLICT,
}


# Ingest keys counted into GeoCycleRun.sources (SourceBundle attribute names).
_SOURCE_KEYS = (
    "earthquakes", "events", "fires", "meteo", "flights", "gdelt", "acled", "vessels",
)
_RUN_RETENTION_DAYS = 7


@dataclass
class CycleResult:
    events: int
    new_signals: int
    notified: int
    checkpoints_evaluated: int
    # Item count per ingest source, for the health record. Every source at zero
    # is an ingest outage; the pipeline cannot tell that from a calm day, but a
    # human reading the run row can.
    sources: dict[str, int] = field(default_factory=dict)
    # Signals dropped by the persist phase. A cycle can finish with work lost.
    persist_failures: int = 0
    # Signals the notify gate selected that no channel delivered.
    notify_failed: int = 0


def _load_stats(db: Session) -> dict[str, GeoRuleStat]:
    return {s.rule_id: s for s in db.query(GeoRuleStat).all()}


def _has_active_signal(db: Session, user_id: int, event: GeoEvent) -> bool:
    return (
        db.query(GeoSignal.id)
        .filter(
            GeoSignal.user_id == user_id,
            GeoSignal.source == event.source,
            GeoSignal.external_id == event.id,
            GeoSignal.status == GeoSignalStatus.ACTIVE.value,
        )
        .first()
        is not None
    )


def _collect_events(bundle) -> list[GeoEvent]:
    events: list[GeoEvent] = []
    events.extend(sentinel.sentinel_scan(bundle.earthquakes, bundle.events, bundle.fires))
    events.extend(sentinel.analyze_flight_anomalies(bundle.flights))
    events.extend(sentinel.analyze_weather_extremes(bundle.meteo))
    events.extend(sentinel.analyze_gdelt_events(bundle.gdelt))
    events.extend(sentinel.analyze_acled_events(bundle.acled))
    events.extend(sentinel.analyze_vessels(bundle.vessels))
    return events


def _compound_analyses(analyses: list[AnalystResult]) -> list[AnalystResult]:
    """Tally matched-event baskets into compound buckets; emit compound analyses for count ≥ 2."""
    counts = {rid: 0 for rid in _COMPOUND_BUCKETS}
    seen_events: set[str] = set()
    for a in analyses:
        # "Simultaneous events" counts events, not analyses: a feed that emits
        # several rows for one id (GDELT, one per article) must not tally twice.
        if not a.matched_rules or a.event.id in seen_events:
            continue
        seen_events.add(a.event.id)
        symbols = {t.symbol for t in a.tickers}
        for rid, bucket in _COMPOUND_BUCKETS.items():
            if symbols & bucket:
                counts[rid] += 1

    day = datetime.now(timezone.utc).date().isoformat()
    out: list[AnalystResult] = []
    for rid, count in counts.items():
        if count < 2:
            continue
        rule = RULES_BY_ID[rid]
        event = GeoEvent(
            id=f"{rid}-{day}",
            type="compound",
            title=f"{rule.description} ({count} simultaneous events)",
            latitude=0.0,
            longitude=0.0,
            source="compound",
            timestamp=int(time.time() * 1000),
            raw_data={"eventCount": count},
        )
        conf = rule.base_confidence * 100
        out.append(
            AnalystResult(
                event=event,
                matched_rules=[rule],
                tickers=[AnalystTicker(t.symbol, t.direction, rule.description) for t in rule.tickers],
                confidence=conf,
                risk_score=compute_risk([rule], event, None),
                direction=rule.direction,
            )
        )
    return out


def _dispatch_notifications(
    db: Session, user_id: int, results: list[SignalResult]
) -> tuple[int, int]:
    """Push the gated signals and record what was actually delivered.

    Returns (notified, notify_failed). ``notified`` is a delivery count, not an
    attempt count: it used to be incremented next to the call regardless of
    outcome, so prod reported notifications on cycles where every channel was
    unconfigured and silently returned False. ``notified_at`` on the signal is
    the per-signal half of the same record.

    Bound the loop, not the call: a channel that fails once is skipped for the
    rest of the cycle. Worst case per signal with every channel stalling is
    ~60 s, this runs synchronously inside the cron request, and a real outage
    is exactly when many signals are gated. The skipped signals keep
    ``notified_at`` NULL and the advisor re-selects them next cycle.
    """
    gated = [res for res in results if res.should_notify]
    # Everything the payload reads, loaded before the first send: the Phase E
    # commit expired the ORM objects, and a lazy load between two channel
    # stalls is a DB round trip held open across the whole fan-out.
    for res in gated:
        _ = (res.signal.headline, res.signal.direction, res.signal.risk_score,
             res.signal.location, list(res.signal.tickers))
    notified = 0
    notify_failed = 0
    down: set[str] = set()
    for res in gated:
        channels = notify_signal(res.signal, res.importance, skip=down)
        down.update(ch for ch, ok in channels.items() if not ok)
        if any(channels.values()):
            res.signal.notified_at = datetime.now(timezone.utc)
            notified += 1
        else:
            notify_failed += 1
    if notified:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "geo cycle user=%s: could not stamp notified_at", user_id, exc_info=True
            )
    return notified, notify_failed


def run_cycle(db: Session, user_id: int) -> CycleResult:
    """Run one full pipeline cycle for a user (blocking; runs ingest in an event loop)."""
    seed_rule_stats(db)
    stats = _load_stats(db)

    bundle = asyncio.run(fetch_all_sources())
    events = _collect_events(bundle)
    logger.info("geo cycle user=%s: %d events from sources", user_id, len(events))

    # Phase A: rule-only correlation (cheap) for every event.
    analyses = [analyze_event(e, stats, use_llm=False) for e in events]

    # Phase B: compound rules (orchestrator-level bucket tally).
    analyses.extend(_compound_analyses(analyses))

    # Phase C: LLM enrichment only for important, rule-backed signals the user
    # doesn't already track — known active signals only get their scores refreshed
    # by the advisor, so re-running the LLM for them every cycle is pure token burn.
    enriched: list[AnalystResult] = []
    for a in analyses:
        est_importance = compute_importance(a.confidence, a.risk_score)
        use_llm = (
            est_importance >= IMPORTANCE_THRESHOLD
            and any(r.tickers for r in a.matched_rules)
            and a.event.type != "compound"
            and not _has_active_signal(db, user_id, a.event)
        )
        enriched.append(analyze_event(a.event, stats, use_llm=True) if use_llm else a)

    # Phase D: price enrichment (one batched fetch for the union of tickers).
    symbols = sorted({t.symbol for a in enriched for t in a.tickers})
    from backend.services.prices import fetch_ticker_prices
    from backend.services.yahoo_budget import GEO_CYCLE_SECONDS, Budget

    # One allowance for every Yahoo call this cycle makes — this fetch and the
    # auditor's in Phase F. Yahoo cannot be bounded per call (see yahoo_budget), and
    # a per-call budget would let one cycle spend it twice over.
    yahoo = Budget(GEO_CYCLE_SECONDS, f"geo cycle (user {user_id})")
    prices = fetch_ticker_prices(symbols, yahoo) if symbols else {}

    # Phase E: persist signals + checkpoints, collect notifications.
    #
    # Each signal writes inside its own SAVEPOINT. A single bad row used to take
    # the whole cycle down from inside generate_signal's flush — and with it
    # Phase F, so nothing was ever resolved again either. One event is allowed to
    # fail; the cycle is not.
    results: list[SignalResult] = []
    persist_failures = 0
    for a in enriched:
        if not a.tickers:
            continue  # nothing actionable
        try:
            with db.begin_nested():
                res = generate_signal(db, user_id=user_id, analysis=a, prices=prices)
                if res.is_new:
                    db.flush()
                    create_checkpoints(db, res.signal)
        except SQLAlchemyError:
            persist_failures += 1
            logger.exception(
                "geo cycle user=%s: dropped signal for event %s", user_id, a.event.id
            )
            continue
        results.append(res)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        persist_failures += len(results)
        results = []
        logger.exception("geo cycle user=%s: commit failed, no signals persisted", user_id)

    notified, notify_failed = _dispatch_notifications(db, user_id, results)

    # Phase F: evaluate any due outcome checkpoints. Runs even when the persist
    # phase lost everything — the auditor is what resolves the signals already on
    # the board, and it must never be blocked by a write that failed upstream.
    checkpoints = evaluate_pending(db, user_id, yahoo)

    new_signals = sum(1 for r in results if r.is_new)
    logger.info(
        "geo cycle user=%s done: %d new signals, %d notified, %d undelivered, "
        "%d checkpoints, %d persist failures",
        user_id, new_signals, notified, notify_failed, checkpoints, persist_failures,
    )
    return CycleResult(
        events=len(events),
        new_signals=new_signals,
        notified=notified,
        notify_failed=notify_failed,
        checkpoints_evaluated=checkpoints,
        sources={key: len(getattr(bundle, key, []) or []) for key in _SOURCE_KEYS},
        persist_failures=persist_failures,
    )


def _record_run(
    db: Session,
    user_id: int,
    started_at: datetime,
    result: CycleResult | None,
    error: str | None,
) -> None:
    """Persist the cycle's outcome. Best-effort: never raises into the cycle.

    This is the only durable trace a cycle leaves when it produces nothing, and
    without it "the pipeline is dead" and "nothing happened today" are the same
    observation from every surface the owner actually looks at.
    """
    try:
        db.rollback()  # the cycle may have left the session dirty
        db.add(
            GeoCycleRun(
                user_id=user_id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                ok=error is None,
                events=result.events if result else 0,
                new_signals=result.new_signals if result else 0,
                notified=result.notified if result else 0,
                notify_failed=result.notify_failed if result else 0,
                checkpoints_evaluated=result.checkpoints_evaluated if result else 0,
                persist_failures=result.persist_failures if result else 0,
                sources=json.dumps(result.sources) if result and result.sources else None,
                error=error[:500] if error else None,
            )
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RUN_RETENTION_DAYS)
        db.query(GeoCycleRun).filter(
            GeoCycleRun.user_id == user_id, GeoCycleRun.started_at < cutoff
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("geo cycle: could not record run for user %s", user_id, exc_info=True)


def run_cycle_for_user(user_id: int) -> CycleResult | None:
    """Scheduler/background entry: manages its own DB session, never raises."""
    from backend.database import SessionLocal

    started_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        try:
            result = run_cycle(db, user_id)
        except Exception as exc:
            logger.exception("geo cycle failed for user %s", user_id)
            _record_run(db, user_id, started_at, None, f"{type(exc).__name__}: {exc}")
            return None
        _record_run(db, user_id, started_at, result, None)
        return result
