"""Advisor — score, dedup and persist a GeoSignal from analyst output.

importance = round(confidence × riskScore/10), 0-100. Signals with importance ≥ 60
trigger LLM (upstream) and notifications. Dedup is per-user by (source, external_id):
an existing active signal only re-notifies when confidence shifts ≥ 15.
"""

import json
import logging
from datetime import datetime, timezone
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
_GENERATED_MIN_CONFIDENCE = 75


def _pageable(source: str, importance: int, event=None) -> bool:
    if importance < IMPORTANCE_THRESHOLD or source in _NON_OBSERVED_SOURCES:
        return False
    # News pages on a *spike*, not on the baseline: a GDELT bucket is one tracked
    # signal per (category, region) that is re-tracked after every +7d
    # resolution, so an ongoing war paged weekly. The sentinel stamps each GDELT
    # event with its region's story count against a 7-day rolling median;
    # unknown (no baseline yet) is not novel.
    raw = getattr(event, "raw_data", None) or {}
    # A generated thesis has no rule behind it: it pages only when the model is
    # itself confident, on top of every other gate.
    if raw.get("generated") and (raw.get("llmConfidence") or 0) < _GENERATED_MIN_CONFIDENCE:
        logger.info(
            "geo notify: generated thesis %s held (confidence %s < %s)",
            getattr(event, "id", "?"), raw.get("llmConfidence"), _GENERATED_MIN_CONFIDENCE,
        )
        return False
    if source == "gdelt":
        novelty = (raw.get("novelty") or {})
        return novelty.get("novel") is True
    return True

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


def _raw(raw_json: str | None) -> dict:
    try:
        raw = json.loads(raw_json) if raw_json else {}
    except (ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _raw_json(raw_data: dict | None) -> str | None:
    """Serialise raw_data within the column, dropping the narrative before
    truncating: a sliced blob is invalid JSON and reads back as nothing."""
    if not raw_data:
        return None
    text = json.dumps(raw_data)
    if len(text) > 4000 and "llmNarrative" in raw_data:
        text = json.dumps({k: v for k, v in raw_data.items() if k != "llmNarrative"})
    return text[:4000]


def _reanchor(db: Session, signal: GeoSignal, prices: dict[str, float]) -> None:
    """Re-price the basket and restart the pending checkpoints from now.

    The checkpoints of a news bucket were anchored at its creation, which for a
    signal that pages on a later spike is a quiet day: the auditor would have
    measured, and the rules would have learned from, a window that does not
    contain the event that paged. The thesis starts at the spike.
    """
    from .auditor import create_checkpoints

    now = datetime.now(timezone.utc)
    for t in signal.tickers:
        price = prices.get(t.symbol)
        if price is not None:
            t.price_at_signal = price
            t.resolved = True
    for chk in list(signal.checkpoints):
        if chk.outcome is None:
            db.delete(chk)
    signal.checkpoints = [c for c in signal.checkpoints if c.outcome is not None]
    db.flush()
    signal.created_at = now.replace(tzinfo=None)
    create_checkpoints(db, signal)


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
        # A generated thesis is pinned at first sighting: the basket the auditor
        # prices is day one's, so the numbers, headline and narrative stay day
        # one's too — a 6-hour re-call would describe instruments the panel does
        # not show. Rule-backed signals follow the news.
        pinned = bool(_raw(existing.raw_json).get("generated"))
        if pinned:
            confidence = float(existing.confidence) * 100
            risk = int(existing.risk_score)
            direction = existing.direction
        else:
            risk = analysis.risk_score if analysis.llm_narrative else int(existing.risk_score)
        importance = compute_importance(confidence, risk)
        shift = abs(confidence - round(float(existing.confidence) * 100))
        # notified_at is the retry ledger: a gated signal no channel delivered
        # (outage, rate limit) is re-selected until one does, instead of burning
        # its only attempt on the first cycle.
        should_notify = _pageable(existing.source, importance, event) and (
            shift >= _CONFIDENCE_SHIFT or existing.notified_at is None
        )
        existing.confidence = confidence / 100
        existing.importance = importance
        existing.risk_score = risk
        existing.direction = direction
        # The bucket's representative story moves with the news: a GDELT signal
        # is created on a quiet day and pages on the cycle it spikes, and the
        # push and the panel must carry the spike, not the day-one headline.
        if not pinned:
            existing.headline = event.title[:300]
            existing.lat = event.latitude
            existing.lng = event.longitude
            existing.raw_json = _raw_json(event.raw_data)
        if should_notify and existing.notified_at is None and existing.source == "gdelt":
            _reanchor(db, existing, prices)
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
        raw_json=_raw_json(event.raw_data),
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

    should_notify = _pageable(signal.source, importance, event)
    return SignalResult(signal, importance, is_new=True, should_notify=should_notify)
