"""Auditor — outcome tracking for geo signals across 5 horizons.

Reuses the backtest concept (BacktestOutcome verdict) but writes to geo_checkpoints
(basket scoring, row-per-horizon) rather than the options-shaped BacktestSignal,
which is per-ticker/daily and would be corrupted by geo's basket/intraday model.
The final (+7d) checkpoint resolves the signal and feeds learned confidence_mod
back into geo_rule_stats.
"""

import json
from dataclasses import dataclass
import logging
import math
from bisect import bisect_right
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
from backend.services.prices import fetch_price_series
from backend.services.yahoo_budget import Budget

from .rules import fetch_order, resolve_rule
from .trading_time import add_trading_time

logger = logging.getLogger(__name__)

Series = list[tuple[datetime, float]]

# Horizon → delay. The two intraday horizons are *trading* time on the US
# session (see trading_time.py); the daily ones are calendar days.
_HORIZON_DELAYS: dict[str, timedelta] = {
    GeoHorizon.H1.value: timedelta(hours=1),
    GeoHorizon.H6.value: timedelta(hours=6),
    GeoHorizon.D1.value: timedelta(days=1),
    GeoHorizon.D3.value: timedelta(days=3),
    GeoHorizon.D7.value: timedelta(days=7),
}
_FINAL_HORIZON = GeoHorizon.D7.value
_TRADING_TIME_HORIZONS = frozenset({GeoHorizon.H1.value, GeoHorizon.H6.value})
# Below this move a ticker is unreadable rather than wrong: it is excluded from
# the basket instead of counting against it. This is the floor; the working
# threshold is scaled to each ticker's own noise (see _threshold_pct).
_MIN_MOVE_PCT = 0.1
# Measured (2026-09-20 audit) on the ten most common basket symbols: median
# |move| is 0.24% at +1h and ~1.0% at +1d, so a flat 0.1% dead zone excluded
# nothing in-hours and every in-hours checkpoint was a coin flip on noise.
# A ticker has to move more than 0.75 of its own horizon sigma to be readable.
_SIGMA_K = 0.75
# 5-minute bars spanned by each horizon's sigma lag: the intraday ones directly,
# the daily ones as one session (78 bars) scaled by the square root of the
# trading days spanned. Everything comes from the one intraday series, so the
# daily series is only fetched for symbols that have no 5-minute bars at all.
_SESSION_BARS = 78
_HORIZON_BARS = {GeoHorizon.H1.value: 12, GeoHorizon.H6.value: 72}
_HORIZON_DAYS = {GeoHorizon.D1.value: 1, GeoHorizon.D3.value: 2, GeoHorizon.D7.value: 5}
_MIN_SIGMA_SAMPLES = 10
# A checkpoint with no price at its target is left pending and retried next
# cycle — a Yahoo stall used to burn it as NEUTRAL forever. Three days, not
# seven: a final horizon kept pending keeps its signal ACTIVE, and ACTIVE is
# what the per-user dedup blocks re-tracking on.
_GIVE_UP_AFTER = timedelta(days=3)
# Ten days of 5-minute bars reach past the +7d target with margin; five did
# not (five trading days is seven calendar days to the hour).
_INTRADAY = {"period": "10d", "interval": "5m"}
_DAILY = {"period": "1mo", "interval": "1d"}
_CONFIDENCE_MOD_CLAMP = 0.3
# confidence_mod is a function of the rule's measured accuracy, not a step
# counter. The old ±0.02/−0.03 steps only drifted upward for a rule right more
# than 60% of the time and never converged on anything; a rule at 24% accuracy
# (prod, 2026-09-20) kept most of its base confidence. Now a rule at 100% earns
# +0.30 and one at 0% loses 0.30, scaled by how much of the evidence is in:
# the first outcomes count for a tenth each, so one lucky hit is not a promotion.
_ACCURACY_GAIN = 0.6
_FULL_WEIGHT_SAMPLES = 10


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _as_of(series: Series | None, target: datetime) -> float | None:
    """Last close at or before ``target`` — the bar the checkpoint is about."""
    if not series:
        return None
    stamps = [ts for ts, _ in series]
    idx = bisect_right(stamps, target)
    return series[idx - 1][1] if idx else None


def _sigma_pct(series: Series | None, lag: int) -> float | None:
    """Std of percentage changes over ``lag`` bars, from the series' own history."""
    if not series or len(series) <= lag + _MIN_SIGMA_SAMPLES:
        return None
    closes = [c for _, c in series]
    moves = [
        (closes[i] - closes[i - lag]) / closes[i - lag] * 100
        for i in range(lag, len(closes))
        if closes[i - lag] > 0
    ]
    if len(moves) < _MIN_SIGMA_SAMPLES:
        return None
    mean = sum(moves) / len(moves)
    return math.sqrt(sum((m - mean) ** 2 for m in moves) / (len(moves) - 1))


def _threshold_pct(intraday: Series | None, daily: Series | None, horizon: str) -> float | None:
    """Readable-move threshold in %, or None when the series cannot calibrate one.

    None is not the floor: a ticker priced without a calibrated threshold used
    to fall back to 0.1% silently — 45× too loose at +7d — and the resulting
    coin flip wrote confidence_mod into geo_rule_stats. Uncalibrated is
    unmeasurable.
    """
    if horizon in _HORIZON_BARS:
        sigma = _sigma_pct(intraday, _HORIZON_BARS[horizon])
    else:
        days = _HORIZON_DAYS[horizon]
        session = _sigma_pct(intraday, _SESSION_BARS)
        if session is None:
            session = _sigma_pct(daily, 1)
        sigma = session * math.sqrt(days) if session is not None else None
    if sigma is None:
        return None
    return max(_MIN_MOVE_PCT, _SIGMA_K * sigma)


def create_checkpoints(db: Session, signal: GeoSignal) -> None:
    """Create the pending checkpoints a signal is missing. Caller commits.

    Skips horizons the signal already has: `_reanchor` deletes only the unscored
    checkpoints before calling this, and recreating a horizon that was already
    scored violated the (signal_id, horizon) unique constraint — the whole page
    rolled back as a persist failure, every cycle, until +7d.
    """
    base = signal.created_at or datetime.now(timezone.utc)
    existing = {getattr(c.horizon, "value", c.horizon) for c in signal.checkpoints}
    for horizon, delay in _HORIZON_DELAYS.items():
        if horizon in existing:
            continue
        target = (
            add_trading_time(base, delay) if horizon in _TRADING_TIME_HORIZONS else base + delay
        )
        # One naive-UTC column: add_trading_time answers aware, the calendar
        # branch answers whatever created_at was.
        target = target.astimezone(timezone.utc).replace(tzinfo=None) if target.tzinfo else target
        db.add(
            GeoCheckpoint(
                user_id=signal.user_id,
                signal_id=signal.id,
                horizon=horizon,
                target_at=target,
            )
        )


@dataclass(frozen=True)
class LegReading:
    """One leg of a basket at one moment: how far it moved against its own noise."""

    symbol: str
    direction: str  # the signal's direction for the leg
    change_pct: float
    threshold_pct: float

    @property
    def readable(self) -> bool:
        # A move too small to read is *undetermined*, not wrong, so it stays out of
        # the denominator entirely. It used to count as a miss, which made the
        # intraday checkpoints unwinnable: prices.py returns the last **daily
        # close**, so at +1h and +6h `cur` is the very same close the signal was
        # priced at, change is exactly 0.00%, and every basket scored 0 → INCORRECT.
        # Two of the five checkpoints were red by construction, the accuracy read
        # 0%, and the +7d resolution fed that back into the rules as failure.
        return abs(self.change_pct) > self.threshold_pct


def _leg_readings(
    signal: GeoSignal,
    prices: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> list[LegReading]:
    """A reading for every leg that has both a price now and a price at the signal."""
    out: list[LegReading] = []
    for t in signal.tickers:
        cur = prices.get(t.symbol)
        at = float(t.price_at_signal) if t.price_at_signal is not None else 0.0
        if cur is None or at <= 0:
            continue
        out.append(LegReading(
            symbol=t.symbol,
            # t.direction reads back as a GeoDirection member (Enum values_callable,
            # no str mixin), so a raw `== "bullish"` is always False on a DB-read
            # ticker — the same enum boundary as the horizon check above.
            direction=getattr(t.direction, "value", t.direction),
            change_pct=(cur - at) / at * 100,
            threshold_pct=(thresholds or {}).get(t.symbol, _MIN_MOVE_PCT),
        ))
    return out


def _score(
    readings: list[LegReading], directions: dict[str, str] | None = None
) -> tuple[float | None, int]:
    """(% of readable legs that moved as predicted, how many were readable).

    ``directions`` scores a *rule's* view of the basket: only the symbols it
    names, each against the direction the rule gives it — which is not always
    the one the signal stored, since a symbol two rules name keeps the first
    writer's.
    """
    correct = total = 0
    for r in readings:
        direction = r.direction if directions is None else directions.get(r.symbol)
        if direction not in ("bullish", "bearish") or not r.readable:
            continue
        total += 1
        if (direction == "bullish") == (r.change_pct > 0):
            correct += 1
    return (round(correct / total * 100, 2) if total else None), total


def _detail(readings: list[LegReading]) -> str:
    return ", ".join(
        f"{r.symbol}: {'+' if r.change_pct >= 0 else ''}{r.change_pct:.2f}% (σ {r.threshold_pct:.2f}%)"
        for r in readings
    )


def _score_basket(
    signal: GeoSignal,
    prices: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> tuple[float | None, str, int]:
    """Return (score 0-100 or None, detail string, measurable-ticker count).

    ``thresholds`` is the per-ticker readable-move threshold in %; absent, the
    flat floor applies.
    """
    readings = _leg_readings(signal, prices, thresholds)
    score, total = _score(readings)
    return score, _detail(readings), total


def learned_confidence_mod(correct: int, total: int) -> float:
    """The confidence adjustment a rule has earned from ``correct`` of ``total`` outcomes.

    (accuracy − 0.5) × gain, shrunk toward 0 while the sample is small, clamped to
    ±_CONFIDENCE_MOD_CLAMP. 0 outcomes → 0. Pure, so the rule stats can be
    recomputed from their counters at any time.
    """
    if total <= 0:
        return 0.0
    weight = min(1.0, total / _FULL_WEIGHT_SAMPLES)
    mod = (correct / total - 0.5) * _ACCURACY_GAIN * weight
    return max(-_CONFIDENCE_MOD_CLAMP, min(_CONFIDENCE_MOD_CLAMP, mod))


def _apply_learned_mod(stat: GeoRuleStat) -> bool:
    """Set the stat's accuracy and confidence_mod from its counters. True if changed."""
    total = stat.total_signals or 0
    correct = stat.correct_signals or 0
    accuracy = correct / total if total else None
    mod = learned_confidence_mod(correct, total)
    before = (
        float(stat.accuracy) if stat.accuracy is not None else None,
        float(stat.confidence_mod) if stat.confidence_mod is not None else None,
    )
    stat.accuracy = accuracy
    stat.confidence_mod = mod
    return before != (accuracy, mod)


def recompute_confidence_mods(db: Session) -> int:
    """Re-derive every rule's confidence_mod from its accuracy. Returns rows changed.

    Idempotent. Runs at the start of every audit so a change to the formula, or
    a row that still carries the old step-counter value, takes effect without
    waiting for that rule's next +7d outcome.
    """
    changed = 0
    for stat in db.query(GeoRuleStat).all():
        if _apply_learned_mod(stat):
            stat.updated_at = datetime.now(timezone.utc)
            changed += 1
    return changed


def _update_rule_stats(
    db: Session, signal: GeoSignal, readings: list[LegReading], basket_outcome: str
) -> None:
    """Teach each matched rule from **its own legs**, not from the basket.

    One outcome for the whole basket used to be applied to every matched rule,
    so a rule's learned confidence followed whatever else was in the signal: a
    template would learn from a hand-written rule's copper leg, and the 2026-09-20
    audit found the mods dominated by GLD and USO drift rather than the thesis.
    A rule is now scored on the symbols it names, each against its own direction;
    when none of them was readable the rule learns nothing from this signal.

    A signal that carries none of a rule's current legs — a basket written
    before the rule was last edited — is scored as a whole, as it always was.
    """
    try:
        rule_ids = json.loads(signal.matched_rule_ids) if signal.matched_rule_ids else []
    except ValueError:
        rule_ids = []
    carried = {t.symbol for t in signal.tickers}
    for rid in rule_ids:
        stat = db.get(GeoRuleStat, rid)
        if stat is None:
            continue
        rule = resolve_rule(rid, signal.country)
        own = {t.symbol: t.direction for t in rule.tickers} if rule else {}
        outcome = _outcome(_score(readings, own)[0]) if own.keys() & carried else basket_outcome
        if outcome == BacktestOutcome.NEUTRAL.value:
            continue  # silence is not being wrong
        is_correct = outcome == BacktestOutcome.CORRECT.value
        stat.total_signals = (stat.total_signals or 0) + 1
        stat.correct_signals = (stat.correct_signals or 0) + (1 if is_correct else 0)
        _apply_learned_mod(stat)
        stat.updated_at = datetime.now(timezone.utc)


def _outcome(score: float | None) -> str:
    """Ties are not wins: a 1-for-2 basket is undetermined, not 50% correct."""
    if score is None or score == 50:
        return BacktestOutcome.NEUTRAL.value
    return BacktestOutcome.CORRECT.value if score > 50 else BacktestOutcome.INCORRECT.value


def _series_for(
    symbols: list[str], budget: Budget | None, cache: dict[str, Series] | None, **spec
) -> dict[str, Series]:
    """Fetch the series for ``symbols``, reusing ``cache`` (one per cron request)
    for whatever was already fetched for another user this cycle."""
    if cache is None:
        return fetch_price_series(symbols, budget=budget, **spec) if symbols else {}
    missing = [s for s in symbols if s not in cache]
    if missing:
        cache.update(fetch_price_series(missing, budget=budget, **spec))
        for s in missing:
            cache.setdefault(s, [])  # remember a miss too: don't re-ask per user
    return {s: cache[s] for s in symbols if cache.get(s)}


def evaluate_pending(
    db: Session,
    user_id: int,
    budget: Budget | None = None,
    series_cache: dict[str, dict[str, Series]] | None = None,
) -> int:
    """Evaluate all due, unscored checkpoints for a user. Returns count evaluated.

    ``series_cache`` is shared across the users of one cron request: the price
    series are the same for everyone, so they are fetched once per request, not
    once per user.

    Each checkpoint is scored against the bar at its own target time, from the
    series fetched once per cycle: intraday when the target is inside the
    5-minute window, the daily close otherwise. A checkpoint none of whose
    tickers has a price is left pending for the next cycle, up to
    ``_GIVE_UP_AFTER``; it used to be stamped NEUTRAL on the spot, so one Yahoo
    stall burned every window that was due that cycle.
    """
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
    symbols = fetch_order(t.symbol for s in signals.values() for t in s.tickers)
    cache = series_cache if series_cache is not None else {}
    intraday = _series_for(symbols, budget, cache.setdefault("5m", {}), **_INTRADAY)
    # The daily series backs only what the intraday one cannot: symbols with no
    # 5-minute bars at all, and targets older than the intraday window. Fetching
    # it for everything doubled the Yahoo footprint for data never read, and it
    # shared the budget the intraday pass had just spent.
    earliest = min((_utc(c.target_at) for c in pending), default=now)
    # "Too few bars to calibrate" is as good as none: TTF=F has ~36 five-minute
    # bars in ten days, so its daily horizons had no sigma and the leg never
    # reached the +7d checkpoint that trains the rules.
    need_daily = sorted(
        sym for sym in symbols
        if sym not in intraday
        or intraday[sym][0][0] > earliest
        or len(intraday[sym]) <= _SESSION_BARS + _MIN_SIGMA_SAMPLES
    )
    daily = _series_for(need_daily, budget, cache.setdefault("1d", {}), **_DAILY)

    evaluated = 0
    uncalibrated: set[str] = set()
    for chk in pending:
        signal = signals.get(chk.signal_id)
        if signal is None:
            continue
        horizon = getattr(chk.horizon, "value", chk.horizon)
        target = _utc(chk.target_at)
        prices: dict[str, float] = {}
        thresholds: dict[str, float] = {}
        for t in signal.tickers:
            bars = intraday.get(t.symbol)
            use_intraday = bool(bars) and bars[0][0] <= target
            price = _as_of(bars if use_intraday else daily.get(t.symbol), target)
            threshold = _threshold_pct(bars, daily.get(t.symbol), horizon)
            # A price without a calibrated threshold is unmeasurable, not "0.1%".
            if price is not None and threshold is None and t.symbol not in uncalibrated:
                uncalibrated.add(t.symbol)
                logger.info("geo auditor: %s has no %s sigma — leg unmeasurable", t.symbol, horizon)
            if price is not None and threshold is not None:
                prices[t.symbol] = price
                thresholds[t.symbol] = threshold

        readings: list[LegReading] = []
        if not prices:
            if now - target < _GIVE_UP_AFTER:
                continue  # retry next cycle: the bars may just not have arrived
            score, detail = None, "sin datos de precio para ningún ticker"
        else:
            readings = _leg_readings(signal, prices, thresholds)
            score, detail = _score(readings)[0], _detail(readings)

        chk.score = score
        chk.outcome = _outcome(score)
        chk.detail = detail[:1000] if detail else None
        chk.evaluated_at = now
        evaluated += 1

        if horizon == _FINAL_HORIZON:
            signal.status = GeoSignalStatus.RESOLVED.value
            # Only a measurable outcome teaches a rule anything, and each rule is
            # measured on its own legs: a tied basket can still hold one rule that
            # was right and one that was wrong. An unscored basket used to arrive
            # here as `is_correct=False` and cost every matched rule 0.03 —
            # silence punished exactly like being wrong.
            _update_rule_stats(db, signal, readings, chk.outcome)

    if evaluated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit geo checkpoint evaluations")
            return 0
    return evaluated


def _elapsed_horizon(created_at: datetime, now: datetime) -> str:
    """The checkpoint horizon a signal's age has reached (calendar time), floor 1h.

    Only used to pick the sigma window for the live rating: a two-day-old thesis
    is read against its 1d noise, not its 1h noise.
    """
    elapsed = now - _utc(created_at)
    reached = _HORIZON_DELAYS[GeoHorizon.H1.value]
    chosen = GeoHorizon.H1.value
    for horizon, delay in _HORIZON_DELAYS.items():
        if delay <= elapsed and delay >= reached:
            reached, chosen = delay, horizon
    return chosen


def rate_active(
    db: Session,
    user_id: int,
    budget: Budget | None = None,
    series_cache: dict[str, dict[str, Series]] | None = None,
) -> int:
    """Re-rate every ACTIVE signal against the latest price. Returns signals rated.

    The checkpoints score fixed moments and are never rewritten; this is the
    running read between them, so the feed keeps moving on the audit cadence
    (every four hours) instead of only when a horizon falls due. Same scorer,
    same readability threshold (the sigma of the horizon the signal's age has
    reached), stored on the signal and overwritten each run.
    """
    now = datetime.now(timezone.utc)
    active = (
        db.query(GeoSignal)
        .filter(GeoSignal.user_id == user_id, GeoSignal.status == GeoSignalStatus.ACTIVE.value)
        .all()
    )
    if not active:
        return 0
    symbols = fetch_order(t.symbol for s in active for t in s.tickers)
    cache = series_cache if series_cache is not None else {}
    intraday = _series_for(symbols, budget, cache.setdefault("5m", {}), **_INTRADAY)
    need_daily = sorted(
        sym for sym in symbols
        if sym not in intraday or len(intraday[sym]) <= _SESSION_BARS + _MIN_SIGMA_SAMPLES
    )
    daily = _series_for(need_daily, budget, cache.setdefault("1d", {}), **_DAILY)

    rated = 0
    for signal in active:
        horizon = _elapsed_horizon(signal.created_at or now, now)
        prices: dict[str, float] = {}
        thresholds: dict[str, float] = {}
        for t in signal.tickers:
            bars = intraday.get(t.symbol)
            price = _as_of(bars if bars else daily.get(t.symbol), now)
            threshold = _threshold_pct(bars, daily.get(t.symbol), horizon)
            if price is not None and threshold is not None:
                prices[t.symbol] = price
                thresholds[t.symbol] = threshold
        if not prices:
            continue  # no price this run: keep the last rating rather than blank it
        score, _detail, _n = _score_basket(signal, prices, thresholds)
        signal.live_score = score
        signal.live_outcome = _outcome(score)
        signal.live_rated_at = now
        rated += 1

    if rated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit geo live ratings")
            return 0
    return rated


@dataclass
class AuditResult:
    checkpoints_evaluated: int
    signals_rated: int
    rules_recomputed: int


def run_audit(
    db: Session,
    user_id: int,
    budget: Budget | None = None,
    series_cache: dict[str, dict[str, Series]] | None = None,
) -> AuditResult:
    """One learning pass for one user: recompute → score due checkpoints → re-rate.

    The recompute goes first so a rule's confidence_mod already reflects its
    accuracy before this run's outcomes add to it, and so a formula change
    lands on the next audit rather than the rule's next resolution.
    """
    recomputed = recompute_confidence_mods(db)
    if recomputed:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit geo confidence_mod recompute")
            recomputed = 0
    evaluated = evaluate_pending(db, user_id, budget, series_cache)
    rated = rate_active(db, user_id, budget, series_cache)
    logger.info(
        "geo audit user=%s done: %d checkpoints scored, %d active signals re-rated, "
        "%d rule mods recomputed",
        user_id, evaluated, rated, recomputed,
    )
    return AuditResult(evaluated, rated, recomputed)
