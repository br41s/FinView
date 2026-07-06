"""Orchestrator — the per-user geo pipeline cycle.

ingest → sentinel + specialist analysts → (compound rules) → analyst → advisor →
persist signals + checkpoints → notify → evaluate pending outcomes.

Async at the ingest boundary (httpx); the DB/scoring work is synchronous (SQLAlchemy).
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import GeoRuleStat, GeoSignal, GeoSignalStatus

from . import sentinel
from .advisor import IMPORTANCE_THRESHOLD, SignalResult, compute_importance, generate_signal
from .analyst import AnalystResult, AnalystTicker, analyze_event
from .auditor import create_checkpoints, evaluate_pending
from .ingest import fetch_all_sources
from .notify import notify_signal
from .rules import RULES_BY_ID, seed_rule_stats
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


@dataclass
class CycleResult:
    events: int
    new_signals: int
    notified: int
    checkpoints_evaluated: int


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
    for a in analyses:
        if not a.matched_rules:
            continue
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
                risk_score=min(round(conf / 15), 10),
                direction=rule.direction,
            )
        )
    return out


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

    prices = fetch_ticker_prices(symbols) if symbols else {}

    # Phase E: persist signals + checkpoints, collect notifications.
    results: list[SignalResult] = []
    for a in enriched:
        if not a.tickers:
            continue  # nothing actionable
        res = generate_signal(db, user_id=user_id, analysis=a, prices=prices)
        if res.is_new:
            db.flush()
            create_checkpoints(db, res.signal)
        results.append(res)

    db.commit()

    notified = 0
    for res in results:
        if res.should_notify:
            notify_signal(res.signal, res.importance)
            notified += 1

    # Phase F: evaluate any due outcome checkpoints.
    checkpoints = evaluate_pending(db, user_id)

    new_signals = sum(1 for r in results if r.is_new)
    logger.info(
        "geo cycle user=%s done: %d new signals, %d notified, %d checkpoints",
        user_id, new_signals, notified, checkpoints,
    )
    return CycleResult(
        events=len(events),
        new_signals=new_signals,
        notified=notified,
        checkpoints_evaluated=checkpoints,
    )


def run_cycle_for_user(user_id: int) -> CycleResult | None:
    """Scheduler/background entry: manages its own DB session, never raises."""
    from backend.database import SessionLocal

    with SessionLocal() as db:
        try:
            return run_cycle(db, user_id)
        except Exception:
            logger.exception("geo cycle failed for user %s", user_id)
            return None
