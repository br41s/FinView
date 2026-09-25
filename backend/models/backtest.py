"""Backtesting outcomes."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# ── Backtesting ──────────────────────────────────────────────────────


class BacktestOutcome(PyEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    NEUTRAL = "NEUTRAL"  # price moved < 0.5 %


class BacktestSignal(Base):
    """Record of an alert signal with outcome tracking at +1D, +3D, +7D.

    Lifecycle:
        1. Created when an alert fires during a cycle (outcome fields = NULL).
        2. A background evaluator fills price_at_1d/3d/7d and outcome after
           the respective trading days have elapsed.
    """

    __tablename__ = "backtest_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Signal context
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. HIGH_IV, HIGH_PUT_CALL_RATIO, IV_SKEW, UNUSUAL_VOLUME
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # BULLISH or BEARISH — derived from alert type at record time
    price_at_signal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    alert_message: Mapped[str] = mapped_column(Text, default="")

    # Outcome prices (filled by evaluator)
    price_at_1d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    price_at_3d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    price_at_7d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))

    # Accuracy at each horizon (NULL until evaluated)
    outcome_1d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    outcome_3d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    outcome_7d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))

    # Macro-regime context frozen at record time (Phase 2b, instrumentation only).
    # regime: risk_on/neutral/risk_off; regime_alignment: aligned/counter/neutral.
    # NULL on pre-2b rows and whenever FRED macro data is unavailable.
    regime: Mapped[str | None] = mapped_column(String(12))
    regime_alignment: Mapped[str | None] = mapped_column(String(10))
    # ZONE_BREAK only: the scorer's probability, whether it cleared the alert
    # gate, and the gate it was measured against. Every scored candidate is
    # recorded (not just the alerting ones) so the gate can be calibrated:
    # ">70 vs <70" needs outcomes on both sides of the cut.
    break_probability: Mapped[int | None] = mapped_column(Integer)
    alerted: Mapped[bool | None] = mapped_column(Boolean)
    alert_threshold: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_bt_user_ticker", "user_id", "ticker"),
        Index("ix_bt_recorded_at", "recorded_at"),
    )
