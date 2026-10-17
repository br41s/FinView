"""Revenue by business segment and by geography, read from issuers' annual reports."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SegmentCheck(Base):
    """When an ISIN's issuer was last looked up, and what the lookup found.

    One row per ISIN. A definite answer ("no LEI", "no segment note", "does not add
    up") is cached for `segments.RECHECK_DAYS` so the refresh does not repeat the
    same lookups every run. A failed request is not written at all: caching an
    outage would hide a real report for a week (the split-history lesson).

    `filing_id` is the latest filing seen (SEC accession number or filings.xbrl.org
    id). A recheck that finds the same id does no work; a new id means a new annual
    report, which is how the data follows each year's report.

    Not user-scoped: an issuer's annual report is the same for everybody.
    """

    __tablename__ = "segment_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    filing_id: Mapped[str | None] = mapped_column(String(120))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SegmentReport(Base):
    """What one annual report says about where an issuer's revenue comes from.

    One row per ISIN and fiscal year, so each new report adds a year instead of
    overwriting the last. `lines` is a JSON list of
    `{"axis": "business"|"geography", "label", "value", "category"}`: `label` and
    `value` are as the report states them (value in `currency`, already scaled),
    `category` is FinView's sector or region for that line. Only axes whose lines
    add up to `total_revenue` are stored; `axis_status` records why the others
    are missing.

    Not user-scoped.
    """

    __tablename__ = "segment_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # "sec" | "esef"
    filing_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_revenue: Mapped[Decimal] = mapped_column(Numeric(22, 2), nullable=False)
    lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    axis_status: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (UniqueConstraint("isin", "fiscal_year"),)
