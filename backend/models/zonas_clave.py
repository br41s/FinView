"""Zonas Clave watchlist, analyses and technical signals."""

from datetime import datetime, timezone

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .auth import User

# ── Zonas Clave ──────────────────────────────────────────────────────


class ZonasClaveWatchlistItem(Base):
    """Tickers the user wants to analyze for key support/resistance zones."""

    __tablename__ = "zonas_clave_watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()
    analyses: Mapped[list["ZonasClaveAnalysis"]] = relationship(
        back_populates="watchlist_item", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)


class ZonasClaveAnalysis(Base):
    """Computed support/resistance zones, indicators and price history for one ticker."""

    __tablename__ = "zonas_clave_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(
        ForeignKey("zonas_clave_watchlist.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    zones: Mapped[str | None] = mapped_column(Text)           # JSON list of zone dicts
    trend_bias_bullish_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    trend_bias_bearish_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    rsi: Mapped[float | None] = mapped_column(Numeric(8, 4))
    macd_signal: Mapped[str | None] = mapped_column(String(20))  # bullish|bearish|neutral
    macd_histogram: Mapped[float | None] = mapped_column(Numeric(10, 6))
    price_history: Mapped[str | None] = mapped_column(Text)   # JSON [{date,close,volume}]
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 6))

    watchlist_item: Mapped["ZonasClaveWatchlistItem"] = relationship(back_populates="analyses")

    __table_args__ = (Index("ix_zc_analysis_item_ts", "watchlist_item_id", "timestamp"),)


class TechnicalSignal(Base):
    """A price approaching a support/resistance zone, scored for break probability.

    Owned by (user, ticker) rather than by a watchlist row: unlike
    ZonasClaveAnalysis, these outlive the watchlist membership that produced them
    (removing a ticker shouldn't erase the record of what it signalled), so
    there's deliberately no FK to zonas_clave_watchlist and no cascade.

    **Every scored candidate is stored, not just the alerting ones.** The
    ALERT_THRESHOLD is an uncalibrated guess — an LLM's "73%" is not a
    probability. Keeping the sub-threshold rows is the only way to ever check
    whether >70 actually breaks more often than <70 and move the cut on evidence.
    Same shape of reasoning as the Phase 2b regime instrumentation.
    """

    __tablename__ = "technical_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Zone context
    zone_level: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(20), default="")  # historical label
    zone_strength: Mapped[float | None] = mapped_column(Numeric(8, 4))
    zone_touches: Mapped[int | None] = mapped_column(Integer)
    price_at_signal: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    distance_pct: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)

    # from_below / from_above — which side price is approaching from. Derived from
    # price vs level, NOT from zone_type, which goes stale on flipped levels.
    approach: Mapped[str] = mapped_column(String(12), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # BULLISH|BEARISH

    # NULL when the LLM was unavailable/unparseable — never coerce to 0, that
    # would read as "certainly won't break" in any later calibration.
    break_probability: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(String(200))
    alerted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped["User"] = relationship()

    __table_args__ = (Index("ix_tech_signal_user_ticker", "user_id", "ticker"),)
