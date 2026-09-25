"""Technical signal emission: proximity gate → LLM scorer → persist → alert.

Every scored candidate is also recorded as a ZONE_BREAK BacktestSignal with its
probability, so the alert gate can be calibrated against outcomes on both sides
of the cut (`backtest_service.zone_calibration`). The gate itself is
`backtest_service.alert_threshold_for`: the default 70 until the evidence says
otherwise.

Wires the two halves together and decides what becomes user-facing:

    zones (already computed by zonas_clave_analyzer)
      → zone_proximity.detect_proximity_candidates   (deterministic, free)
      → zone_scorer.score_break_probability          (LLM, candidates only)
      → TechnicalSignal rows                          (ALL scored candidates)
      → alerted=True + BacktestSignal                 (only > ALERT_THRESHOLD)

Store-everything / alert-on-some is deliberate: see zone_scorer's docstring on
why the threshold is a guess until there's outcome data behind it.
"""

import logging

from sqlalchemy.orm import Session

from backend.models import TechnicalSignal
from backend.services.zone_proximity import detect_proximity_candidates
from backend.services.backtest_service import alert_threshold_for
from backend.services.zone_scorer import score_break_probability

logger = logging.getLogger(__name__)

# Signal type recorded in BacktestSignal, so technical triggers can be told apart
# from the options-microstructure ones in the accuracy breakdown.
SIGNAL_TYPE = "ZONE_BREAK"


def _already_open(db: Session, user_id: int, ticker: str, level: float) -> bool:
    """True if this user already has a signal for this ticker+level today.

    The scorer's cache stops repeat *LLM calls*, but a cache miss (restart, TTL
    expiry) would still write a duplicate row. Proximity lasts days, so without
    this a week near one level becomes a week of daily duplicate rows.
    """
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(hours=20)
    return (
        db.query(TechnicalSignal.id)
        .filter(
            TechnicalSignal.user_id == user_id,
            TechnicalSignal.ticker == ticker,
            TechnicalSignal.created_at >= since,
            # Same rounding as the scorer cache key: a cent of drift inside one
            # zone is the same signal.
            TechnicalSignal.zone_level == round(level, 2),
        )
        .first()
        is not None
    )


def emit_for_analysis(
    db: Session,
    *,
    user_id: int,
    analysis: dict,
    regime: str | None = None,
    alert_threshold: int | None = None,
) -> list[TechnicalSignal]:
    """Emit technical signals for one analyzed ticker. Caller commits.

    `analysis` is a zonas_clave_analyzer.analyze_ticker() result. Returns the
    persisted rows (possibly empty — no proximity is the common case).

    Never raises: a signalling failure must not take down the analysis cycle that
    produced the zones, which is the actual product.
    """
    try:
        ticker = analysis["ticker"]
        current_price = float(analysis["current_price"])
        candidates = detect_proximity_candidates(analysis.get("zones") or [], current_price)
        if not candidates:
            return []

        indicators = {
            "current_price": current_price,
            "rsi": analysis.get("rsi"),
            "macd_signal": analysis.get("macd_signal"),
            "macd_histogram": analysis.get("macd_histogram"),
            "trend_bias_bullish_pct": analysis.get("trend_bias_bullish_pct"),
        }

        emitted: list[TechnicalSignal] = []
        # The cycle passes the gate it computed once; a direct caller gets it here.
        threshold = alert_threshold if alert_threshold is not None else alert_threshold_for(db, user_id)
        for candidate in candidates:
            level = round(candidate["level"], 2)
            if _already_open(db, user_id, ticker, level):
                continue

            score = score_break_probability(ticker, candidate, indicators)
            probability = score["break_probability"] if score else None
            # None (no API key / LLM failure) must not alert: absence of a score
            # is not a low score, and it isn't a high one either.
            alerted = probability is not None and probability > threshold

            row = TechnicalSignal(
                user_id=user_id,
                ticker=ticker,
                zone_level=level,
                zone_type=candidate["zone_type"],
                zone_strength=candidate.get("strength"),
                zone_touches=candidate.get("touches"),
                price_at_signal=current_price,
                distance_pct=candidate["distance_pct"],
                approach=candidate["approach"],
                direction=candidate["direction"],
                break_probability=probability,
                rationale=score["rationale"] if score else None,
                alerted=alerted,
            )
            db.add(row)
            emitted.append(row)

            # Every scored candidate gets an outcome row, alerting or not: the gate
            # can only be calibrated with outcomes on both sides of it. An unscored
            # candidate has nothing to calibrate against and gets none.
            if probability is not None:
                _record_backtest(
                    db,
                    user_id=user_id,
                    ticker=ticker,
                    candidate=candidate,
                    probability=probability,
                    current_price=current_price,
                    regime=regime,
                    alerted=alerted,
                    threshold=threshold,
                )

        return emitted
    except Exception:
        logger.exception("technical signal emission failed for %s", analysis.get("ticker"))
        return []


def _record_backtest(
    db: Session,
    *,
    user_id: int,
    ticker: str,
    candidate: dict,
    probability: int,
    current_price: float,
    regime: str | None,
    alerted: bool,
    threshold: int,
) -> None:
    """Record a scored candidate for outcome tracking, alerting or not.

    Bypasses backtest_service.record_signal() on purpose: that derives direction
    by keyword-matching the alert type/message, which has no case for ZONE_BREAK
    and would fall through to a default. Here the direction is already known
    exactly (which side of the level price sits on), so it's passed straight in.
    """
    from backend.models import BacktestSignal
    from backend.services.backtest_service import alignment_for

    try:
        direction = candidate["direction"]
        message = (
            f"Precio a {candidate['distance_pct'] * 100:.2f}% de la zona "
            f"{candidate['level']:.2f} ({candidate['approach']}), "
            f"probabilidad de ruptura {probability}%"
        )
        db.add(
            BacktestSignal(
                user_id=user_id,
                ticker=ticker,
                signal_type=SIGNAL_TYPE,
                direction=direction,
                price_at_signal=current_price,
                alert_message=message[:500],
                regime=regime,
                regime_alignment=alignment_for(direction, regime),
                break_probability=probability,
                alerted=alerted,
                alert_threshold=threshold,
            )
        )
    except Exception:
        logger.exception("backtest recording failed for technical signal on %s", ticker)
