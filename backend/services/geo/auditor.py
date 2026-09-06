"""Auditor — outcome tracking for geo signals across 5 horizons.

Reuses the backtest concept (BacktestOutcome verdict) but writes to geo_checkpoints
(basket scoring, row-per-horizon) rather than the options-shaped BacktestSignal,
which is per-ticker/daily and would be corrupted by geo's basket/intraday model.
The final (+7d) checkpoint resolves the signal and feeds learned confidence_mod
back into geo_rule_stats.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models import (
    BacktestOutcome,
    GeoCheckpoint,
    GeoHorizon,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
)
from backend.services.prices import fetch_ticker_prices

logger = logging.getLogger(__name__)

# Horizon → wait delay (calendar). Intraday horizons are evaluated by the next
# scheduler tick after they mature, against an intraday price (prices.py resolves
# 5-minute bars first) — on daily closes +1h compared a close against itself.
_HORIZON_DELAYS: dict[str, timedelta] = {
    GeoHorizon.H1.value: timedelta(hours=1),
    GeoHorizon.H6.value: timedelta(hours=6),
    GeoHorizon.D1.value: timedelta(days=1),
    GeoHorizon.D3.value: timedelta(days=3),
    GeoHorizon.D7.value: timedelta(days=7),
}
_FINAL_HORIZON = GeoHorizon.D7.value
# Below this move a ticker is unreadable rather than wrong: it is excluded from
# the basket instead of counting against it.
_MIN_MOVE_PCT = 0.1  # % move for a ticker to count at all
_CONFIDENCE_MOD_CLAMP = 0.3


def create_checkpoints(db: Session, signal: GeoSignal) -> None:
    """Create the 5 pending checkpoints for a freshly created signal. Caller commits."""
    base = signal.created_at or datetime.now(timezone.utc)
    for horizon, delay in _HORIZON_DELAYS.items():
        db.add(
            GeoCheckpoint(
                user_id=signal.user_id,
                signal_id=signal.id,
                horizon=horizon,
                target_at=base + delay,
            )
        )


def _score_basket(signal: GeoSignal, prices: dict[str, float]) -> tuple[float | None, str, int]:
    """Return (score 0-100 or None, detail string, measurable-ticker count)."""
    correct = total = 0
    parts: list[str] = []
    for t in signal.tickers:
        cur = prices.get(t.symbol)
        at = float(t.price_at_signal) if t.price_at_signal is not None else 0.0
        if cur is None or at <= 0:
            continue
        change = (cur - at) / at * 100
        parts.append(f"{t.symbol}: {'+' if change >= 0 else ''}{change:.2f}%")
        # t.direction reads back as a GeoDirection member (Enum values_callable, no
        # str mixin), so a raw `== "bullish"` is always False on a DB-read ticker —
        # the same enum boundary as the horizon check above. Normalize before compare.
        direction = getattr(t.direction, "value", t.direction)
        if direction == "neutral":
            continue
        # A move too small to read is *undetermined*, not wrong, so it stays out of
        # the denominator entirely. It used to count as a miss, which made the
        # intraday checkpoints unwinnable: prices.py returns the last **daily
        # close**, so at +1h and +6h `cur` is the very same close the signal was
        # priced at, change is exactly 0.00%, and every basket scored 0 → INCORRECT.
        # Two of the five checkpoints were red by construction, the accuracy read
        # 0%, and the +7d resolution fed that back into the rules as failure.
        if abs(change) <= _MIN_MOVE_PCT:
            continue
        total += 1
        if (direction == "bullish" and change > 0) or (direction == "bearish" and change < 0):
            correct += 1
    if total == 0:
        return None, ", ".join(parts), 0
    return round(correct / total * 100, 2), ", ".join(parts), total


def _update_rule_stats(db: Session, signal: GeoSignal, is_correct: bool) -> None:
    try:
        rule_ids = json.loads(signal.matched_rule_ids) if signal.matched_rule_ids else []
    except ValueError:
        rule_ids = []
    delta = 0.02 if is_correct else -0.03
    for rid in rule_ids:
        stat = db.get(GeoRuleStat, rid)
        if stat is None:
            continue
        stat.total_signals = (stat.total_signals or 0) + 1
        stat.correct_signals = (stat.correct_signals or 0) + (1 if is_correct else 0)
        stat.accuracy = stat.correct_signals / stat.total_signals if stat.total_signals else None
        mod = float(stat.confidence_mod or 0) + delta
        stat.confidence_mod = max(-_CONFIDENCE_MOD_CLAMP, min(_CONFIDENCE_MOD_CLAMP, mod))
        stat.updated_at = datetime.now(timezone.utc)


def evaluate_pending(db: Session, user_id: int) -> int:
    """Evaluate all due, unscored checkpoints for a user. Returns count evaluated."""
    now = datetime.now(timezone.utc)
    pending: list[GeoCheckpoint] = (
        db.query(GeoCheckpoint)
        .filter(
            GeoCheckpoint.user_id == user_id,
            GeoCheckpoint.target_at <= now,
            GeoCheckpoint.outcome.is_(None),
        )
        .all()
    )
    if not pending:
        return 0

    signal_ids = {c.signal_id for c in pending}
    signals = {
        s.id: s
        for s in db.query(GeoSignal).filter(GeoSignal.id.in_(signal_ids)).all()
    }

    symbols: set[str] = set()
    for s in signals.values():
        for t in s.tickers:
            symbols.add(t.symbol)
    prices = fetch_ticker_prices(list(symbols)) if symbols else {}

    evaluated = 0
    for chk in pending:
        signal = signals.get(chk.signal_id)
        if signal is None:
            continue
        score, detail, total = _score_basket(signal, prices)
        if score is None:
            chk.outcome = BacktestOutcome.NEUTRAL.value
            chk.score = None
        else:
            chk.score = score
            chk.outcome = (
                BacktestOutcome.CORRECT.value
                if score >= 50
                else BacktestOutcome.INCORRECT.value
            )
        chk.detail = detail[:1000] if detail else None
        chk.evaluated_at = now
        evaluated += 1

        # chk.horizon reads back as a GeoHorizon member (Enum values_callable), not a
        # str — GeoHorizon has no str mixin, so a raw `== "7d"` is always False and the
        # +7d resolution branch never ran. Normalize like api/geo.py's _ev() helper.
        if getattr(chk.horizon, "value", chk.horizon) == _FINAL_HORIZON:
            signal.status = GeoSignalStatus.RESOLVED.value
            # Only a measurable outcome teaches the rules anything. An unscored
            # basket (nothing moved, or no price resolved) used to arrive here as
            # `is_correct=False` and cost every matched rule 0.03 of confidence —
            # so silence was punished exactly like being wrong, and a dozen of them
            # pinned a rule at the -0.30 floor.
            if score is not None:
                _update_rule_stats(db, signal, is_correct=score >= 50)

    if evaluated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit geo checkpoint evaluations")
            return 0
    return evaluated
