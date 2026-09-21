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

from backend.models import (
    GeoCycleRun,
    GeoFlightSample,
    GeoRegionSample,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
)

from . import sentinel
from .advisor import IMPORTANCE_THRESHOLD, SignalResult, compute_importance, generate_signal
from .analyst import (
    AnalystResult,
    AnalystTicker,
    analyze_event,
    analyze_unmatched,
    has_fresh_generative,
)
from .auditor import create_checkpoints, evaluate_pending
from .ingest import fetch_all_sources
from .notify import notify_signal
from .rules import RULES_BY_ID, compute_risk, effective_confidence, seed_rule_stats
from .sentinel import GeoEvent

logger = logging.getLogger(__name__)

# Compound-rule ticker buckets (an event counts in a bucket if its basket overlaps).
_ENERGY = {"USO", "UNG", "XLE", "TTF=F"}
_FOOD = {"DBA", "WEAT", "ZC=F", "ZS=F", "KC=F", "CC=F", "SB=F"}
_CONFLICT = {"LMT", "RTX", "ITA"}
_COMPOUND_BUCKETS = {
    "compound-energy-crisis": _ENERGY,
    "compound-food-crisis": _FOOD,
    "compound-geopolitical-escalation": _CONFLICT,
}


# Ingest keys counted into GeoCycleRun.sources (SourceBundle attribute names).
_SOURCE_KEYS = (
    "earthquakes", "events", "fires", "meteo", "flights", "gdelt", "vessels", "ofac",
)
_RUN_RETENTION_DAYS = 7
# Flight baseline: the sentinel keeps the last 12 samples per zone; one cycle per
# 30 min makes that six hours. Samples closer than this are the same cycle seen
# by another user and are not stored twice.
_FLIGHT_SAMPLE_MIN_GAP = timedelta(minutes=10)
_FLIGHT_SAMPLE_RETENTION = timedelta(hours=24)
_REGION_SAMPLE_RETENTION = timedelta(days=7)
# Generative path: at most this many LLM calls per cron request for events no
# rule covers, and only for salient ones (see _salient). Cached per event 6 h.
_MAX_GENERATIVE_PER_REQUEST = 3
_SALIENT_MENTIONS = 15
_SALIENT_MAGNITUDE = 7.0
_REGION_SAMPLE_MIN_GAP = timedelta(minutes=10)


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
    # GDELT signals above the importance gate that the novelty gate held back.
    novelty_suppressed: int = 0


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


def _hydrate_flight_history(db: Session) -> None:
    """Load the per-zone baseline from the DB into the sentinel's rolling window."""
    rows = (
        db.query(GeoFlightSample)
        .filter(GeoFlightSample.sampled_at >= datetime.now(timezone.utc) - _FLIGHT_SAMPLE_RETENTION)
        .order_by(GeoFlightSample.sampled_at.asc())
        .all()
    )
    history: dict[str, list[tuple[int, int, int]]] = {}
    for r in rows:
        ts = r.sampled_at if r.sampled_at.tzinfo else r.sampled_at.replace(tzinfo=timezone.utc)
        history.setdefault(r.zone_id, []).append((r.total, r.military, int(ts.timestamp() * 1000)))
    for hist in history.values():
        del hist[:-sentinel._FLIGHT_MAX_HISTORY]
    sentinel._flight_history.clear()
    sentinel._flight_history.update(history)


def _persist_flight_samples(db: Session) -> int:
    """Store the sample the sentinel just appended for each zone; returns rows written."""
    now = datetime.now(timezone.utc)
    written = 0
    for zone_id, hist in sentinel._flight_history.items():
        if not hist:
            continue
        total, military, ts_ms = hist[-1]
        sampled_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        latest = (
            db.query(GeoFlightSample.sampled_at)
            .filter(GeoFlightSample.zone_id == zone_id)
            .order_by(GeoFlightSample.sampled_at.desc())
            .first()
        )
        if latest is not None:
            prev = latest[0] if latest[0].tzinfo else latest[0].replace(tzinfo=timezone.utc)
            if sampled_at - prev < _FLIGHT_SAMPLE_MIN_GAP:
                continue
        db.add(GeoFlightSample(zone_id=zone_id, sampled_at=sampled_at, total=total, military=military))
        written += 1
    db.query(GeoFlightSample).filter(
        GeoFlightSample.sampled_at < now - _FLIGHT_SAMPLE_RETENTION
    ).delete(synchronize_session=False)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("geo: could not persist flight samples", exc_info=True)
    return written


def _hydrate_region_history(db: Session) -> None:
    rows = (
        db.query(GeoRegionSample.region, GeoRegionSample.sampled_at, GeoRegionSample.stories)
        .filter(GeoRegionSample.sampled_at >= datetime.now(timezone.utc) - _REGION_SAMPLE_RETENTION)
        .order_by(GeoRegionSample.sampled_at.asc())
        .all()
    )
    history: dict[str, list[tuple[int, int]]] = {}
    for region, sampled_at, stories in rows:
        ts = sampled_at if sampled_at.tzinfo else sampled_at.replace(tzinfo=timezone.utc)
        history.setdefault(region, []).append((stories, int(ts.timestamp() * 1000)))
    for hist in history.values():
        del hist[:-sentinel._GDELT_MAX_HISTORY]
    sentinel._gdelt_history.clear()
    sentinel._gdelt_history.update(history)


def _persist_region_samples(db: Session) -> int:
    """Store this cycle's per-region story count; returns rows written."""
    now = datetime.now(timezone.utc)
    written = 0
    for region, hist in sentinel._gdelt_history.items():
        if not hist:
            continue
        stories, ts_ms = hist[-1]
        sampled_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        latest = (
            db.query(GeoRegionSample.sampled_at)
            .filter(GeoRegionSample.region == region)
            .order_by(GeoRegionSample.sampled_at.desc())
            .first()
        )
        if latest is not None:
            prev = latest[0] if latest[0].tzinfo else latest[0].replace(tzinfo=timezone.utc)
            if sampled_at - prev < _REGION_SAMPLE_MIN_GAP:
                continue
        db.add(GeoRegionSample(region=region, sampled_at=sampled_at, stories=stories))
        written += 1
    db.query(GeoRegionSample).filter(
        GeoRegionSample.sampled_at < now - _REGION_SAMPLE_RETENTION
    ).delete(synchronize_session=False)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("geo: could not persist region samples", exc_info=True)
    return written


def _macro_regime() -> str | None:
    """The FRED regime from the cached series; None when unavailable. Never raises."""
    try:
        from backend.services.macro_context import macro_context

        return (macro_context() or {}).get("regime")
    except Exception:
        logger.warning("geo: macro regime unavailable", exc_info=True)
        return None


def _salient(event: GeoEvent) -> bool:
    """Worth one generative call: news in a named region that is a novelty spike
    or widely reported; otherwise red severity or a big quake.

    News is tested first and on its own terms: nearly every conflict bucket
    carries severity "red" (CAMEO 19x is -10), so a severity-first test made the
    news clause unreachable and pointed the calls at region-less wire noise.
    """
    raw = event.raw_data or {}
    if event.source == "gdelt":
        if event.region is None:
            return False
        novelty = raw.get("novelty") or {}
        return novelty.get("novel") is True or (raw.get("numMentions") or 0) >= _SALIENT_MENTIONS
    if event.severity == "red":
        return True
    return event.magnitude is not None and event.magnitude >= _SALIENT_MAGNITUDE


def _generative_pass(analyses: list[AnalystResult], regime: str | None) -> int:
    """Replace the analysis of salient unmatched events with a generated one, in place."""
    generated = 0
    for i, a in enumerate(analyses):
        if a.tickers or not _salient(a.event):
            continue
        # Only a real call is debited: a cached answer is free, and an ACTIVE
        # generated signal is re-derived from its cache every cycle — debiting
        # it would let three live theses starve the path for six hours.
        spends = not has_fresh_generative(a.event.id)
        if spends and generated >= _MAX_GENERATIVE_PER_REQUEST:
            continue
        result = analyze_unmatched(a.event, regime)
        if spends:
            generated += 1
        if result is not None:
            analyses[i] = result
    return generated


def _collect_events(bundle) -> list[GeoEvent]:
    events: list[GeoEvent] = []
    events.extend(sentinel.sentinel_scan(bundle.earthquakes, bundle.events, bundle.fires))
    events.extend(sentinel.analyze_flight_anomalies(bundle.flights))
    events.extend(sentinel.analyze_weather_extremes(bundle.meteo))
    events.extend(sentinel.analyze_gdelt_events(bundle.gdelt))
    events.extend(sentinel.analyze_vessels(bundle.vessels))
    events.extend(sentinel.analyze_ofac_actions(bundle.ofac))
    return events


def _compound_analyses(
    analyses: list[AnalystResult],
    stats: dict[str, GeoRuleStat] | None = None,
    regime: str | None = None,
) -> list[AnalystResult]:
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
        # Learned like every other rule: the panel shows effective_confidence, so
        # scoring the signal on the unlearned base number diverged from it.
        conf = effective_confidence(rule, (stats or {}).get(rid)) * 100
        out.append(
            AnalystResult(
                event=event,
                matched_rules=[rule],
                tickers=[AnalystTicker(t.symbol, t.direction, rule.description) for t in rule.tickers],
                confidence=conf,
                risk_score=compute_risk([rule], event, None, regime),
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


@dataclass
class CycleInputs:
    """Everything a cycle computes that is the same for every user.

    The events are global, the rules are global, the prices are global; only
    dedup, persistence, notification and the auditor's rows are per user. Each
    user's cycle used to redo the lot — with four accounts that was four price
    fetches, four series fetches and four sentinel passes over one bundle.
    """

    bundle: object
    events: list[GeoEvent]
    analyses: list[AnalystResult]
    stats: dict[str, GeoRuleStat]
    prices: dict[str, float]
    yahoo: object  # Budget shared by every Yahoo call in the request
    # FRED macro regime (risk_off | neutral | risk_on | None): read once per
    # request from the cached series, never fetched here. A risk-off regime adds
    # one point of risk to conflict / chokepoint / sanctions events.
    regime: str | None = None
    series_cache: dict[str, dict] = field(default_factory=dict)
    # Symbols any fetch this request has *tried*. "Not in prices" means
    # unresolvable as often as it means "the LLM just added it", and the
    # unresolvable ones (thin futures) must not be re-asked once per user.
    attempted: set[str] = field(default_factory=set)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def prepare_cycle(db: Session) -> CycleInputs:
    """The user-independent half of a cycle: run once per cron request."""
    from backend.services.prices import fetch_ticker_prices
    from backend.services.yahoo_budget import GEO_CYCLE_SECONDS, Budget

    started_at = datetime.now(timezone.utc)
    seed_rule_stats(db)
    stats = _load_stats(db)
    regime = _macro_regime()
    # The stats outlive this session (they are read by every user's cycle) and
    # the flight-sample commit below would expire them: a detached, expired
    # GeoRuleStat raises on first attribute access. Snapshot them now.
    db.expunge_all()

    bundle = asyncio.run(fetch_all_sources())
    _hydrate_flight_history(db)
    _hydrate_region_history(db)
    events = _collect_events(bundle)
    _persist_flight_samples(db)
    _persist_region_samples(db)
    logger.info("geo cycle: %d events from sources", len(events))

    if regime:
        for e in events:
            e.raw_data["macroRegime"] = regime  # persisted with the signal, shown in the panel
    # Phase A: rule-only correlation (cheap) for every event.
    analyses = [analyze_event(e, stats, use_llm=False, regime=regime) for e in events]
    # Phase B: compound rules (orchestrator-level bucket tally).
    analyses.extend(_compound_analyses(analyses, stats, regime))
    # Phase B2: salient events no rule covers get one generative call each.
    generated = _generative_pass(analyses, regime)
    if generated:
        logger.info("geo cycle: %d generative analyses attempted", generated)

    # Phase D: price enrichment for the union of tickers. One allowance for every
    # Yahoo call the request makes — this fetch and the auditor's, for every user.
    # Yahoo cannot be bounded per call (see yahoo_budget); a spent budget leaves
    # checkpoints pending for the next cycle, never scored on nothing.
    yahoo = Budget(GEO_CYCLE_SECONDS, "geo cycle")
    symbols = sorted({t.symbol for a in analyses for t in a.tickers})
    prices = fetch_ticker_prices(symbols, yahoo) if symbols else {}
    return CycleInputs(
        bundle, events, analyses, stats, prices, yahoo,
        regime=regime, attempted=set(symbols), started_at=started_at,
    )


def run_cycle(db: Session, user_id: int, inputs: CycleInputs | None = None) -> CycleResult:
    """Run one pipeline cycle for a user (blocking).

    ``inputs`` is the shared half from ``prepare_cycle``; a single-user caller
    (the manual "Run cycle", the in-process scheduler) may omit it.
    """
    if inputs is None:
        inputs = prepare_cycle(db)
    bundle, events, stats, yahoo = inputs.bundle, inputs.events, inputs.stats, inputs.yahoo

    # Phase C: LLM enrichment only for important, rule-backed signals the user
    # doesn't already track — known active signals only get their scores refreshed
    # by the advisor, so re-running the LLM for them every cycle is pure token burn.
    # Per user because the gate is per user; the call itself is cached per event.
    enriched: list[AnalystResult] = []
    for a in inputs.analyses:
        est_importance = compute_importance(a.confidence, a.risk_score)
        use_llm = (
            est_importance >= IMPORTANCE_THRESHOLD
            and any(r.tickers for r in a.matched_rules)
            and a.event.type != "compound"
            and not _has_active_signal(db, user_id, a.event)
        )
        enriched.append(
            analyze_event(a.event, stats, use_llm=True, regime=inputs.regime) if use_llm else a
        )

    # The LLM may have added tickers the shared fetch did not cover.
    prices = inputs.prices
    extra = sorted(
        {t.symbol for a in enriched for t in a.tickers} - set(prices) - inputs.attempted
    )
    if extra:
        from backend.services.prices import fetch_ticker_prices

        inputs.attempted.update(extra)
        inputs.prices.update(fetch_ticker_prices(extra, yahoo))  # the next user reuses it

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
    checkpoints = evaluate_pending(db, user_id, yahoo, inputs.series_cache)

    new_signals = sum(1 for r in results if r.is_new)
    suppressed = sum(
        1 for r in results
        if not r.should_notify and r.importance >= IMPORTANCE_THRESHOLD
        and r.signal.notified_at is None
        and (r.signal.source == "gdelt" or "\"generated\": true" in (r.signal.raw_json or ""))
    )
    logger.info(
        "geo cycle user=%s done: %d new signals, %d notified, %d undelivered, "
        "%d checkpoints, %d persist failures, %d held by the novelty/confidence gates",
        user_id, new_signals, notified, notify_failed, checkpoints, persist_failures, suppressed,
    )
    return CycleResult(
        events=len(events),
        new_signals=new_signals,
        notified=notified,
        notify_failed=notify_failed,
        checkpoints_evaluated=checkpoints,
        sources={key: len(getattr(bundle, key, []) or []) for key in _SOURCE_KEYS},
        persist_failures=persist_failures,
        novelty_suppressed=suppressed,
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


def run_cycle_for_user(user_id: int, inputs: CycleInputs | None = None) -> CycleResult | None:
    """Scheduler/background entry: manages its own DB session, never raises.

    The run row's started_at is the request's, not this user's: the row is the
    liveness record and its duration should keep covering the ingest."""
    from backend.database import SessionLocal

    started_at = inputs.started_at if inputs else datetime.now(timezone.utc)
    with SessionLocal() as db:
        try:
            result = run_cycle(db, user_id, inputs)
        except Exception as exc:
            logger.exception("geo cycle failed for user %s", user_id)
            _record_run(db, user_id, started_at, None, f"{type(exc).__name__}: {exc}")
            return None
        _record_run(db, user_id, started_at, result, None)
        return result


def run_cycles(user_ids: list[int]) -> list[CycleResult | None]:
    """Cron entry: the shared half once, then one per-user cycle each.

    A failure in the shared half is a failure for every user (each gets a
    recorded run row saying so), which is the truth: no user could have had a
    cycle without it.
    """
    from backend.database import SessionLocal

    if not user_ids:
        return []
    started_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        try:
            inputs = prepare_cycle(db)
        except Exception as exc:
            logger.exception("geo cycle: shared preparation failed")
            for uid in user_ids:
                _record_run(db, uid, started_at, None, f"{type(exc).__name__}: {exc}")
            return [None] * len(user_ids)
    return [run_cycle_for_user(uid, inputs) for uid in user_ids]
