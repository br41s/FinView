"""FRED risk-free rate service — risk-free input for Black-Scholes Greeks.

Mirrors services.exchange_rates (ECB): all rates live in the DB (`fred_rates`
table), downloads happen only in a background pre-cache (never during a
request), and `get_rate()` is DB-only.

Two series are tracked, one per option-pricing currency:
  - USD → DGS3MO  (3-Month Treasury Constant Maturity Rate)
  - EUR → ECBESTRVOLWGTTRMDMNRT  (Euro Short-Term Rate, €STR)
FRED reports both as percent (e.g. 5.30); we store the annualized decimal
(0.0530). The risk-free rate moves slowly, so the latest value on or before
the lookup date (within a short window) is used.

Fallback policy (A): when FRED is unconfigured, empty, or stale for a
currency, callers fall back to a per-currency constant. A missing
FINVIEW_FRED_API_KEY makes sync a no-op — Greeks keep working off the
constants, exactly like Turnstile/aisstream degrade.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.config import settings
from backend.database import SessionLocal, engine
from backend.models import FredRate

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# Currency → FRED series id (annualized short-term risk-free rate).
_SERIES: dict[str, str] = {
    "USD": "DGS3MO",
    "EUR": "ECBESTRVOLWGTTRMDMNRT",
}

# Fallback (A): per-currency constant used when FRED has no usable value.
# USD keeps the historical greeks_calculator default so behaviour is unchanged
# when FRED is absent; EUR is a rough resting value only hit without FRED.
_FALLBACK: dict[str, float] = {
    "USD": 0.053,
    "EUR": 0.025,
}

# Euro-area ticker suffixes (MEFF + Eurex euro venues). Everything else —
# plain US tickers, ISINs, and non-euro European venues (.L/.SW/.OL/.ST/.CO…)
# — resolves to USD for now (adding GBP/CHF series is a Phase-2 follow-up).
_EUR_SUFFIXES = {"MC", "DE", "PA", "AS", "MI", "BR", "VI", "HE", "LS"}

# Look-back window when resolving a rate for a date (weekends/holidays/stale).
_LOOKBACK_DAYS = 14


# ── Currency resolution ─────────────────────────────────────────────────────


def currency_for_ticker(ticker: str | None) -> str:
    """Infer the option-pricing currency from a ticker symbol."""
    if not ticker or "." not in ticker:
        return "USD"
    suffix = ticker.rsplit(".", 1)[-1].upper()
    return "EUR" if suffix in _EUR_SUFFIXES else "USD"


# ── FRED feed helpers ───────────────────────────────────────────────────────


def _fetch_observations(
    series_id: str, start: str | None, scale: float = 0.01
) -> list[tuple[str, float]]:
    """Fetch (date_str, value) observations for a series from FRED.

    `scale` multiplies the raw FRED value: rates come as percent so the
    default 0.01 stores a decimal (5.30 → 0.0530); macro index levels
    (VIX, stress) pass scale=1.0 to store the raw reading.

    Returns [] when no API key is configured or no usable rows come back.
    """
    if not settings.fred_api_key:
        return []
    import requests

    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    if start:
        params["observation_start"] = start
    resp = requests.get(_FRED_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows: list[tuple[str, float]] = []
    for obs in resp.json().get("observations", []):
        value = obs.get("value", ".")
        if value in (".", "", None):  # FRED uses "." for missing observations
            continue
        try:
            rows.append((obs["date"], float(value) * scale))
        except (ValueError, KeyError):
            continue
    return rows


def _upsert(series_id: str, rows: list[tuple[str, float]]) -> int:
    """Bulk insert/upsert observations for one series."""
    if not rows:
        return 0
    payload = [
        {"series_id": series_id, "rate_date": date.fromisoformat(d), "rate": Decimal(str(r))}
        for d, r in rows
    ]
    dialect = engine.dialect.name
    BATCH = 500
    n = 0
    with SessionLocal() as db:
        for i in range(0, len(payload), BATCH):
            chunk = payload[i : i + BATCH]
            if dialect in ("postgresql", "sqlite"):
                ins = pg_insert if dialect == "postgresql" else sqlite_insert
                stmt = ins(FredRate).values(chunk)
                stmt = stmt.on_conflict_do_nothing(index_elements=["series_id", "rate_date"])
            else:  # pragma: no cover - other dialects unused in this project
                stmt = FredRate.__table__.insert().values(chunk)
            db.execute(stmt)
            n += len(chunk)
        db.commit()
    return n


def _max_cached(series_id: str) -> date | None:
    with SessionLocal() as db:
        return db.execute(
            select(FredRate.rate_date)
            .where(FredRate.series_id == series_id)
            .order_by(FredRate.rate_date.desc())
            .limit(1)
        ).scalar_one_or_none()


# ── Public API ──────────────────────────────────────────────────────────────


def sync_rates() -> int:
    """Incremental sync for all tracked series. Background thread only.

    No-op (returns 0) when no FRED API key is configured.
    """
    if not settings.fred_api_key:
        print("[fred-sync] no FRED_API_KEY — skipping (Greeks use constants)")
        return 0

    total = 0
    for series_id in _SERIES.values():
        max_cached = _max_cached(series_id)
        # Re-fetch from the day after the last cached date (overlap-safe via upsert);
        # full history on first boot.
        start = (max_cached + timedelta(days=1)).isoformat() if max_cached else None
        if max_cached and (datetime.now(timezone.utc).date() - max_cached).days <= 1:
            continue  # already fresh
        rows = _fetch_observations(series_id, start)
        total += _upsert(series_id, rows)
    if total:
        print(f"[fred-sync] added {total} rate observations")
    return total


def latest_value(series_id: str, on: date | str | None = None) -> Decimal | None:
    """Latest stored value for a FRED series on/before `on`. DB-only, no HTTP.

    Returns the most recent observation within the look-back window, or None
    when the series isn't cached for that period. Shared by the risk-free
    rate lookup and the macro-context reader.
    """
    target = date.today() if on is None else (on if isinstance(on, date) else date.fromisoformat(on))
    floor = target - timedelta(days=_LOOKBACK_DAYS)
    with SessionLocal() as db:
        return db.execute(
            select(FredRate.rate)
            .where(
                FredRate.series_id == series_id,
                FredRate.rate_date <= target,
                FredRate.rate_date >= floor,
            )
            .order_by(FredRate.rate_date.desc())
            .limit(1)
        ).scalar_one_or_none()


def get_rate(currency: str, on: date | str | None = None) -> Decimal | None:
    """Latest risk-free rate for `currency` on/before `on`. DB-only, no HTTP.

    Returns the annualized decimal, or None when the currency has no tracked
    series or no observation within the look-back window.
    """
    series_id = _SERIES.get(currency.upper())
    if not series_id:
        return None
    return latest_value(series_id, on)


def risk_free_rate(currency: str, on: date | str | None = None) -> float:
    """Risk-free rate for a currency, with fallback (A) to a constant."""
    ccy = currency.upper()
    rate = get_rate(ccy, on)
    if rate is not None:
        return float(rate)
    return _FALLBACK.get(ccy, _FALLBACK["USD"])


def risk_free_rate_for_ticker(ticker: str | None, on: date | str | None = None) -> float:
    """Resolve the risk-free rate for an option ticker via its currency."""
    return risk_free_rate(currency_for_ticker(ticker), on)
