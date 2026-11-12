"""Price, ticker, split and rate caches."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class PriceCache(Base):
    """Cache for Yahoo Finance daily prices."""

    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    yahoo_ticker: Mapped[str | None] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    original_currency: Mapped[str | None] = mapped_column(String(3))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    # The close of the session before the one `original_price` comes from, in the same
    # currency (pence already divided). NULL = unknown: rows written before it existed,
    # or a ticker with a single bar in the window.
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fetched_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("isin", "fetched_date"),
    )


class TickerMap(Base):
    """ISIN → Yahoo Finance ticker, learned at runtime.

    `prices._ISIN_TICKER_MAP` is a hand-curated list of ISINs that Yahoo cannot
    resolve on its own. Everything outside it used to be a dead end: the data
    supervisor would look a ticker up via yfinance, write the answer into a
    DataIssue description, and throw it away. Nothing read it back, so prices
    stayed "—" forever, the same lookup ran again on every import, and split
    detection — which iterates the curated map — never saw the security at all.

    Rows here are what the app has learned. The curated map still wins on
    conflict: it encodes corporate actions (AENA pre/post split ISINs sharing
    one ticker) that a symbol lookup cannot know. `source` records where a row
    came from, and a 'manual' row is a correction a user made through the
    issue resolver.

    Not user-scoped: an ISIN maps to one security for everybody.
    """

    __tablename__ = "ticker_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    yahoo_ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="yfinance")
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SplitHistoryCache(Base):
    """Yahoo split history per ticker, so the supervisor stops re-asking.

    `_check_split_candidates` called yfinance once per distinct ticker in the
    portfolio, uncached, on the import path — a 50-position portfolio meant 50
    sequential network calls inside one HTTP request, on a Cloud Run revision
    with CPU throttling and a single instance.

    A company's split history changes a few times per decade, so it is cached
    for `split_history.TTL`. `splits` is a JSON list of [iso_date, ratio]; an
    empty list is a real answer (most tickers have never split) and is cached
    like any other. A failed fetch is not cached at all — otherwise one Yahoo
    outage would pin "no splits" for a month.

    Not user-scoped: a ticker's split history is the same for everybody.
    """

    __tablename__ = "split_history_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    splits: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


# ── Exchange Rates (ECB) ─────────────────────────────────────────────


class ExchangeRate(Base):
    """ECB daily reference rates. rate = units of `currency` per 1 EUR.

    Populated incrementally from the ECB eurofxref feed by
    services.exchange_rates. Used as an official-rate fallback for IRPF
    conversions when a broker file omits the rate or for manual entries.
    """

    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="ECB")

    __table_args__ = (
        UniqueConstraint("rate_date", "currency"),
        Index("ix_fx_ccy_date", "currency", "rate_date"),
    )


class FredRate(Base):
    """FRED (St. Louis Fed) risk-free rate series cache.

    rate = annualized risk-free rate as a decimal (0.053 = 5.3%). One row per
    (series_id, rate_date). Populated incrementally from the FRED API by
    services.fred_rates and used as the risk-free input for Black-Scholes
    Greeks, resolved per option currency. Empty/stale → Greeks fall back to
    per-currency constants (no-op when FINVIEW_FRED_API_KEY is unset).
    """

    __tablename__ = "fred_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    __table_args__ = (
        UniqueConstraint("series_id", "rate_date"),
        Index("ix_fred_series_date", "series_id", "rate_date"),
    )
