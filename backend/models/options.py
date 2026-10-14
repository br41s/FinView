"""Options monitor: followed instruments, snapshots, alerts, agent log."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .auth import User

# ── Options Monitor Models ───────────────────────────────────────────


class AlertSeverity(PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FollowedInstrument(Base):
    """Canonical followed-instrument row — one per (user, ticker), with opt-in
    per-section "lenses". Replaces the separate options/zonas watchlist
    memberships (legacy tables migrated on first boot, see watchlist_service).

    Lens semantics:
    - options_enabled: shows in the options watchlist / agent scope.
    - options_paused:  stays in the options list but the agent skips it
      (maps the legacy WatchlistItem.enabled=False state).
    - zonas_enabled:   has a synced ZonasClaveWatchlistItem child row, which
      still parents ZonasClaveAnalysis via its own FK (kept internal on
      purpose — no FK surgery in prod).
    A row with no lens enabled is pruned.
    """

    __tablename__ = "followed_instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    options_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    options_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    zonas_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)


# NOTE: the legacy `watchlist_items` table (options membership pre-Fase B) has no
# model anymore — watchlist_service.migrate_legacy_watchlists() reads any remaining
# rows via raw SQL and drops the table (B3).


class OptionsSnapshot(Base):
    """Point-in-time options chain metrics for a ticker."""

    __tablename__ = "options_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    call_volume: Mapped[int] = mapped_column(Integer, default=0)
    put_volume: Mapped[int] = mapped_column(Integer, default=0)
    call_open_interest: Mapped[int] = mapped_column(Integer, default=0)
    put_open_interest: Mapped[int] = mapped_column(Integer, default=0)
    put_call_ratio_volume: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    put_call_ratio_oi: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    avg_call_iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    avg_put_iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    historical_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    iv_skew: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    market_sentiment: Mapped[str | None] = mapped_column(String(20))

    # Full chain data stored as JSON text for detail views
    chain_data: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_opt_snap_user_ticker", "user_id", "ticker"),
    )


class OptionsAlert(Base):
    """Generated alerts from options monitoring cycles."""

    __tablename__ = "options_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.MEDIUM.value)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Macro-regime alignment tag (Phase 2b, informational): aligned/counter/neutral.
    # NULL on pre-2b rows and whenever FRED macro data is unavailable.
    regime_alignment: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (
        Index("ix_opt_alert_user", "user_id", "timestamp"),
    )


class OptionsAlertNotification(Base):
    """When an alert identity was last pushed, so a still-true alert is not re-sent.

    In the DB, not in memory: prod scales to zero between cron ticks, so every
    cycle starts on a fresh instance and an in-process dict is always empty.
    """

    __tablename__ = "options_alert_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    alert_key: Mapped[str] = mapped_column(String(120), nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "alert_key", name="uq_opt_alert_notif_user_key"),
    )


class UnusualActivity(Base):
    """Smart money / unusual volume detection."""

    __tablename__ = "unusual_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # CALL / PUT
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expiration: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False)
    vol_oi_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))


class OptionsAgentLog(Base):
    """Log of each agent cycle execution."""

    __tablename__ = "options_agent_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tickers_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    alerts_generated: Mapped[int] = mapped_column(Integer, default=0)
    unusual_activities: Mapped[int] = mapped_column(Integer, default=0)
    market_sentiment: Mapped[str | None] = mapped_column(String(20))
    claude_analysis: Mapped[str | None] = mapped_column(Text)
    execution_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class OptionsHiddenPortfolioTicker(Base):
    """Tickers the user has hidden from the Options Monitor portfolio tab."""

    __tablename__ = "options_hidden_portfolio_tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)
