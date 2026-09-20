"""Advisor — score, dedup and persist a GeoSignal from analyst output.

importance = round(confidence × riskScore/10), 0-100. Signals with importance ≥ 60
trigger LLM (upstream) and notifications. Dedup is per-user by (source, external_id):
an existing active signal only re-notifies when confidence shifts ≥ 15.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models import (
    GeoDisplayCategory,
    GeoSignal,
    GeoSignalStatus,
    GeoSignalTicker,
)

from .analyst import AnalystResult
from .rules import dumps_rule_ids

logger = logging.getLogger(__name__)

IMPORTANCE_THRESHOLD = 60
_CONFIDENCE_SHIFT = 15  # min confidence delta to re-notify a known event
# Sources that describe the world as configured, not as observed. The static
# ALERT_ZONES polygons emit the same "red" event every cycle forever; they may
# sit on the board but a hardcoded polygon is not something to page a phone
# about. The first two notifications the pipeline ever sent (2026-09-20) were
# Gaza and Syria — from these polygons, unchanged since June.
_NON_OBSERVED_SOURCES = frozenset({"alerts"})


def _pageable(source: str, importance: int) -> bool:
    return importance >= IMPORTANCE_THRESHOLD and source not in _NON_OBSERVED_SOURCES

# Fine matcher type → coarse frontend display category.
_DISPLAY_CATEGORY: dict[str, GeoDisplayCategory] = {
    "earthquake": GeoDisplayCategory.EARTHQUAKE,
    "cyclone": GeoDisplayCategory.CYCLONE,
    "deep_cyclone": GeoDisplayCategory.CYCLONE,
    "fire": GeoDisplayCategory.FIRE,
    "volcano": GeoDisplayCategory.VOLCANO,
    "maritime_disruption": GeoDisplayCategory.MARITIME,
    "maritime_rerouting": GeoDisplayCategory.MARITIME,
    "maritime_congestion": GeoDisplayCategory.MARITIME,
    "flood": GeoDisplayCategory.WEATHER,
    "drought": GeoDisplayCategory.WEATHER,
    "storm": GeoDisplayCategory.WEATHER,
    "severe_storm": GeoDisplayCategory.WEATHER,
    "extreme_heat": GeoDisplayCategory.WEATHER,
    "extreme_cold": GeoDisplayCategory.WEATHER,
    "heavy_precipitation": GeoDisplayCategory.WEATHER,
    "iceberg": GeoDisplayCategory.WEATHER,
}
# Everything geopolitical (conflict/armed_conflict/military_*/sanctions/protest/…) → CONFLICT.


def _display_category(event_type: str) -> GeoDisplayCategory:
    return _DISPLAY_CATEGORY.get(event_type, GeoDisplayCategory.CONFLICT)


def compute_importance(confidence: float, risk_score: int) -> int:
    return round(confidence * (risk_score / 10))


def _basket_direction(tickers) -> str:
    bull = sum(1 for t in tickers if t.direction == "bullish")
    bear = sum(1 for t in tickers if t.direction == "bearish")
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


@dataclass
class SignalResult:
    signal: GeoSignal
    importance: int
    is_new: bool
    should_notify: bool


def generate_signal(
    db: Session,
    *,
    user_id: int,
    analysis: AnalystResult,
    prices: dict[str, float],
) -> SignalResult:
    """Create or update the per-user signal for this event. Caller commits."""
    event = analysis.event
    confidence = round(analysis.confidence)
    importance = compute_importance(confidence, analysis.risk_score)
    direction = _basket_direction(analysis.tickers)

    existing = (
        db.query(GeoSignal)
        .filter(
            GeoSignal.user_id == user_id,
            GeoSignal.source == event.source,
            GeoSignal.external_id == event.id,
            GeoSignal.status == GeoSignalStatus.ACTIVE.value,
        )
        .order_by(GeoSignal.created_at.desc())
        .first()
    )

    if existing is not None:
        # The LLM runs on first sighting only; every later cycle re-analyses with
        # the rules alone. Its risk therefore sticks until an LLM re-assesses —
        # a rule-only refresh must not overwrite it, or the override flips back
        # one cycle later and pages what the model had just judged not worth a
        # page (2026-09-20: five conflict signals paged on cycle two this way).
        risk = analysis.risk_score if analysis.llm_narrative else int(existing.risk_score)
        importance = compute_importance(confidence, risk)
        shift = abs(confidence - round(float(existing.confidence) * 100))
        # notified_at is the retry ledger: a gated signal no channel delivered
        # (outage, rate limit) is re-selected until one does, instead of burning
        # its only attempt on the first cycle.
        should_notify = _pageable(existing.source, importance) and (
            shift >= _CONFIDENCE_SHIFT or existing.notified_at is None
        )
        existing.confidence = confidence / 100
        existing.importance = importance
        existing.risk_score = risk
        existing.direction = direction
        return SignalResult(existing, importance, is_new=False, should_notify=should_notify)

    signal = GeoSignal(
        user_id=user_id,
        event_type=event.type,
        display_category=_display_category(event.type).value,
        source=event.source,
        external_id=event.id,
        headline=event.title[:300],
        location=(event.region or "").replace("_", " ")[:200],
        lat=event.latitude,
        lng=event.longitude,
        importance=importance,
        confidence=confidence / 100,
        risk_score=analysis.risk_score,
        direction=direction,
        status=GeoSignalStatus.ACTIVE.value,
        matched_rule_ids=dumps_rule_ids(analysis.matched_rules),
        raw_json=json.dumps(event.raw_data)[:4000] if event.raw_data else None,
    )
    db.add(signal)
    db.flush()  # assign signal.id for ticker FKs

    for t in analysis.tickers:
        price = prices.get(t.symbol)
        signal.tickers.append(
            GeoSignalTicker(
                symbol=t.symbol,
                direction=t.direction,
                price_at_signal=price,
                resolved=price is not None,
            )
        )

    should_notify = _pageable(signal.source, importance)
    return SignalResult(signal, importance, is_new=True, should_notify=should_notify)
