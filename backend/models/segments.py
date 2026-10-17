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
    # The reader version that wrote it (`refresh.READERS`); NULL before 2026-10-17.
    reader: Mapped[str | None] = mapped_column(String(20))
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

    `measure` is what `total_revenue` and the line values are: "revenue", or, for
    issuers that tag no revenue line, "bank_gross_income" (margen bruto),
    "insurance_revenue" or "rental_income" (`esef.TOTAL_CONCEPTS`). NULL on rows
    written before 2026-10-17, all of which are revenue.

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
    measure: Mapped[str | None] = mapped_column(String(30))
    lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    axis_status: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (UniqueConstraint("isin", "fiscal_year"),)


class ListingProfile(Base):
    """What Yahoo Finance says a held listing is: its quote type and sector.

    The last resort of the exposure split (`segments/listing.py`): a stock no annual
    report breaks down is counted in its ISIN's country and this sector, labelled as
    an estimate. `quote_type` NULL means Yahoo gave nothing usable at `checked_at`;
    it is asked again a day later. `sector` is Yahoo's own name, mapped to FinView's
    sectors when read. Not user-scoped: a listing is the same for everybody.
    """

    __tablename__ = "listing_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    quote_type: Mapped[str | None] = mapped_column(String(20))
    sector: Mapped[str | None] = mapped_column(String(60))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AiMentionCheck(Base):
    """When an ISIN's annual report was last read for what it says about AI.

    Same caching contract as `SegmentCheck`: a definite answer is kept for
    `segments.RECHECK_DAYS`, a failed request or model call writes nothing, and
    the same `filing_id` on a recheck means there is nothing new to read.

    Not user-scoped.
    """

    __tablename__ = "ai_mention_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    filing_id: Mapped[str | None] = mapped_column(String(120))
    reader: Mapped[str | None] = mapped_column(String(20))  # as in SegmentCheck
    checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AiMentionReport(Base):
    """What one annual report says about artificial intelligence, in its own words.

    `scope` is the part of the filing that was read: "risk_factors" (10-K Item 1A)
    or "annual_report" (the whole ESEF report, which has no standard risk section).
    `mentions` and `words` are counted in code over that part. `quotes` is a JSON
    list of `{"text", "theme"}`; every `text` was found verbatim in the filing.
    `quotes_status` is "ok", "none" (no mention to quote) or "unverified" (the
    model's quotes did not match the filing, so none was kept). `summary` is the
    model's one-sentence description, kept only with verified quotes.

    Not user-scoped.
    """

    __tablename__ = "ai_mention_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # "sec" | "esef"
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    mentions: Mapped[int] = mapped_column(Integer, nullable=False)
    words: Mapped[int] = mapped_column(Integer, nullable=False)
    quotes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    quotes_status: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (UniqueConstraint("isin", "fiscal_year"),)
