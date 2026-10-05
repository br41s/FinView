"""Geo-Intel (WorldHawk port): signals, checkpoints, rule stats, samples, cycle runs."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .backtest import BacktestOutcome

# ── Geo-Intel (WorldHawk integration) ────────────────────────────────


class GeoDisplayCategory(PyEnum):
    """Coarse category surfaced to the frontend GeoSignal contract.

    The pipeline matches on a finer ``event_type`` (e.g. ``armed_conflict``);
    this collapses ~28 matcher categories into the 7 buckets the map UI uses.
    Values are lowercase to match the frontend type literal directly.
    """

    EARTHQUAKE = "earthquake"
    CYCLONE = "cyclone"
    FIRE = "fire"
    VOLCANO = "volcano"
    CONFLICT = "conflict"
    MARITIME = "maritime"
    WEATHER = "weather"


class GeoDirection(PyEnum):
    """Market thesis direction for a geo signal (frontend contract = lowercase)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class GeoSignalStatus(PyEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class GeoHorizon(PyEnum):
    """Checkpoint horizons for geo outcome tracking (union of all backtests)."""

    H1 = "1h"
    H6 = "6h"
    D1 = "1d"
    D3 = "3d"
    D7 = "7d"


def _geo_enum(enum_cls: type[PyEnum]) -> Enum:
    """Enum column that persists by VALUE, not member name.

    The geo enums use lowercase values (e.g. EARTHQUAKE="earthquake") to match the
    frontend GeoSignal contract, so name != value. SQLAlchemy defaults to storing
    the name; values_callable flips it to the value.
    """
    return Enum(enum_cls, values_callable=lambda obj: [e.value for e in obj])


class GeoSignal(Base):
    """A geopolitical / natural-event signal produced by the geo pipeline.

    ``user_id`` is the system owner (`services/geo/owner.py`): the pipeline runs
    once and every account reads the owner's rows — the column is a NOT NULL FK
    kept for lack of Alembic, not a tenancy boundary. ``event_type`` is the fine
    matcher category; ``display_category`` is the coarse UI bucket.
    """

    __tablename__ = "geo_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Classification
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # matcher category
    display_category: Mapped[str] = mapped_column(_geo_enum(GeoDisplayCategory), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # ingest feed key
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)  # source id (dedup)

    # Event content
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="")
    # services/geo/countries.py slug, as the source reported it; NULL when the
    # source names no country. A template rule is rendered for this country.
    country: Mapped[str | None] = mapped_column(String(40))
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)

    # Scoring (frontend GeoSignal contract)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # 0-1
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 0-10
    direction: Mapped[str] = mapped_column(_geo_enum(GeoDirection), nullable=False)
    status: Mapped[str] = mapped_column(
        _geo_enum(GeoSignalStatus), default=GeoSignalStatus.ACTIVE.value
    )
    # When at least one notification channel actually delivered this signal.
    # NULL means never delivered — which, before this column existed, was
    # indistinguishable from delivered: notify_signal discarded every sender's
    # return value and GeoCycleRun.notified counted attempts.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Live rating: the basket scored against the latest price on every audit run,
    # so an open thesis shows how it is doing between checkpoints. Overwritten
    # each run; the checkpoints stay the immutable record.
    live_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    live_outcome: Mapped[str | None] = mapped_column(String(20))
    live_rated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Provenance
    matched_rule_ids: Mapped[str | None] = mapped_column(Text)  # JSON list of rule_id
    raw_json: Mapped[str | None] = mapped_column(Text)  # normalized source event

    tickers: Mapped[list["GeoSignalTicker"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )
    checkpoints: Mapped[list["GeoCheckpoint"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_geo_sig_user_created", "user_id", "created_at"),
        # Dedup is per *active* signal, not per event id for all time. The whole
        # table was once unique on (user_id, source, external_id), which
        # contradicted the pipeline: the advisor only dedups against ACTIVE rows
        # because the auditor resolves a signal at +7d, and most feeds keep
        # emitting the same id long after that (an EONET event stays open for
        # months, `wx-*`/`ais-*`/`fire-cluster-*` ids are region-keyed and never
        # rotate). So the first recurrence of a resolved event raised
        # IntegrityError inside generate_signal's flush, which killed the cycle
        # before the auditor ran -- no new signals and no resolutions, ever
        # again, while /geo/cron kept answering 200.
        #
        # A partial unique index says what was actually meant: at most one ACTIVE
        # signal per (user, event), while resolved sightings stay as history and
        # a live event may be tracked again later. Existing installations drop the
        # old constraint and gain this index at startup (see
        # database._DROP_UNIQUE_CONSTRAINTS / _ADDITIVE_UNIQUE_INDEXES).
        Index(
            "uq_geo_sig_active_dedup",
            "user_id",
            "source",
            "external_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )


class GeoSignalTicker(Base):
    """A ticker affected by a geo signal, with its per-ticker thesis direction."""

    __tablename__ = "geo_signal_tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("geo_signals.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(_geo_enum(GeoDirection), nullable=False)
    # Price at signal time (per-ticker), used for basket outcome scoring.
    price_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    # False when prices.py cannot resolve the symbol (futures / foreign listings).
    resolved: Mapped[bool] = mapped_column(Boolean, default=True)
    # The leg read on its own (services/geo/ladder.py: confirms | contradicts |
    # flat). `live_*` is overwritten by every audit while the signal is active;
    # `final_state` is written once, at the +7d resolution. NULL = never read,
    # which is not the same as read and flat.
    live_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    live_state: Mapped[str | None] = mapped_column(String(12))
    final_state: Mapped[str | None] = mapped_column(String(12))

    signal: Mapped["GeoSignal"] = relationship(back_populates="tickers")


class GeoCheckpoint(Base):
    """Outcome-tracking checkpoint for a geo signal at one horizon.

    Parallel to BacktestSignal's per-horizon columns but row-per-horizon so it
    can carry the full union (+1h/+6h/+1d/+3d/+7d), which the options backtest
    columns cannot. Reuses BacktestOutcome for the verdict.
    """

    __tablename__ = "geo_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("geo_signals.id"), nullable=False, index=True
    )
    horizon: Mapped[str] = mapped_column(_geo_enum(GeoHorizon), nullable=False)
    target_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Basket score 0-100 (% of non-neutral tickers that moved as predicted),
    # the BacktestOutcome verdict, and a human-readable per-ticker breakdown.
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    outcome: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    detail: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)

    signal: Mapped["GeoSignal"] = relationship(back_populates="checkpoints")

    __table_args__ = (
        UniqueConstraint("signal_id", "horizon", name="uq_geo_checkpoint_horizon"),
        Index("ix_geo_chk_user_target", "user_id", "target_at"),
    )


class GeoRuleStat(Base):
    """Static rule definition + learned tuning for the 63 geo-economic rules.

    Global (no user_id): the rules are universal IP and tuning aggregates across
    all outcomes. Seeded idempotently from the rule table in P4. ``base_confidence``
    is static; ``confidence_mod`` is the auditor-learned adjustment applied at
    scoring time (effective = base_confidence + confidence_mod).
    """

    __tablename__ = "geo_rule_stats"

    rule_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    base_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    correct_signals: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence_mod: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class GeoRegionSample(Base):
    """GDELT stories per region per cycle — the novelty baseline for the notify gate.

    A conflict bucket like Ukraine is one tracked signal that the auditor
    resolves after seven days and then tracks again, so an ongoing war paged
    weekly on re-tracking. A GDELT signal now pages only when its region's
    story count is *novel* against this rolling window — a spike, not the
    baseline. One row per escalation region per cycle (zeros included, so a
    quiet region's baseline is honestly zero); 7-day retention.
    """

    __tablename__ = "geo_region_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    stories: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GeoFlightSample(Base):
    """One per-zone flight count per cycle — the airspace rules' rolling baseline.

    The sentinel's drop/surge detection compares this cycle against the last
    twelve samples. That history used to live in process memory, which with
    ``--min-instances=0`` and a 30-minute cron dies between every cycle, so the
    baseline was always the hard-coded default and five tankers over Hormuz read
    as a "military surge" on every cold start. Objective and user-independent:
    one row per zone per cycle, not per user.
    """

    __tablename__ = "geo_flight_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    military: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GeoGenerativeAnswer(Base):
    """The generative LLM's last answer for one event: a thesis, or "not actionable".

    The six-hour cache these rows back used to live in process memory, the same
    mistake as the two baselines above. With ``--min-instances=0`` and an hourly
    cron nearly every cycle starts on a new instance (26 instances over 29
    cycles, 2026-10-04), so the cache was empty: the first three salient events
    were asked again every hour — the per-request cap, 73 cycles running — and
    the events behind them never got a call. One row per event id, not per
    user, pruned at the cache's own TTL.
    """

    __tablename__ = "geo_generative_answers"

    event_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # The validated proposal as JSON; "{}" is the model's "not actionable".
    proposal_json: Mapped[str] = mapped_column(Text, nullable=False)


class GeoCycleRun(Base):
    """One execution of the geo pipeline for one user — the section's heartbeat.

    Ideas can stop producing without anything saying so: the orchestrator logs a
    failed cycle and returns None, ``/geo/cron`` answers 200 either way, and the
    UI only ever knew the date of the newest signal — which is also what a
    genuinely quiet week looks like. That ambiguity is what let a dead pipeline
    sit unnoticed for six weeks. A row per cycle answers "when did this last run,
    what did it ingest, and did it fail" from the API, with no log access.

    Rows are pruned to the last ``_RUN_RETENTION_DAYS`` days on write: this is a
    liveness record, not an audit trail.
    """

    __tablename__ = "geo_cycle_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    events: Mapped[int] = mapped_column(Integer, default=0)
    new_signals: Mapped[int] = mapped_column(Integer, default=0)
    # Signals that reached at least one channel. This used to be incremented
    # unconditionally next to the notify call, so it counted attempts: prod read
    # "notified" on cycles where nothing was ever configured to deliver.
    notified: Mapped[int] = mapped_column(Integer, default=0)
    # Signals the gate selected for notification where no channel delivered.
    # Non-zero is a delivery outage, which a green `ok` and a zero `notified`
    # (nothing to notify) cannot be told apart otherwise.
    notify_failed: Mapped[int] = mapped_column(Integer, default=0)
    checkpoints_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    # Signals the persist phase had to skip. Non-zero means the cycle finished
    # but lost work, which a green `ok` would otherwise hide.
    persist_failures: Mapped[int] = mapped_column(Integer, default=0)

    # Per-source item counts as JSON, e.g. {"earthquakes": 12, "events": 40, ...}.
    # All-zero is the signature of an ingest outage (dead egress, expired keys)
    # as opposed to a genuinely calm day, which never has every source empty.
    sources: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_geo_run_user_started", "user_id", "started_at"),)
