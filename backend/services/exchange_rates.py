"""ECB exchange-rate service — incremental caching strategy.

All rates live in the DB (`exchange_rates` table). Downloads happen only:
  - First boot ever → full ECB history (~20MB, once)
  - Subsequent boots / daily → 90-day feed (~300KB) to add new dates
  - Never during a request — only in the background pre-cache

`get_rate()` is DB-only: one SELECT per (date, currency). No HTTP.

Rate convention (matches the ECB feed): rate = units of `currency` per 1 EUR.
So to convert a foreign amount to EUR: amount_eur = amount / rate.

Ported from OptionsAI (fiscal/exchange_rates.py), adapted to SQLAlchemy.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import SessionLocal, engine
from backend.models import ExchangeRate

_ECB_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
_ECB_FULL_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
_ECB_NS = {
    "gesmes": "http://www.gesmes.org/xml/2002-08-01",
    "ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref",
}


# ── ECB feed helpers ──────────────────────────────────────────────────────────


def _fetch_ecb_xml(url: str) -> ET.Element:
    import requests

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _parse_ecb_rates(root: ET.Element) -> list[tuple[str, str, float]]:
    """Parse ECB XML → flat list of (date_str, currency, rate)."""
    rows: list[tuple[str, str, float]] = []
    cube = root.find(".//ecb:Cube", _ECB_NS)
    if cube is None:
        return rows
    for time_cube in cube.findall("ecb:Cube[@time]", _ECB_NS):
        date_str = time_cube.attrib["time"]
        for rate_cube in time_cube.findall("ecb:Cube", _ECB_NS):
            rows.append(
                (date_str, rate_cube.attrib["currency"], float(rate_cube.attrib["rate"]))
            )
    return rows


# ── DB helpers ────────────────────────────────────────────────────────────────


def _upsert_rates(rows: list[tuple[str, str, float]], source: str = "ECB") -> int:
    """Bulk insert/upsert rates. rows = [(date_str, currency, rate), ...]."""
    if not rows:
        return 0
    payload = [
        {
            "rate_date": date.fromisoformat(d),
            "currency": ccy,
            "rate": Decimal(str(rate)),
            "source": source,
        }
        for d, ccy, rate in rows
    ]
    dialect = engine.dialect.name
    BATCH = 500
    n = 0
    with SessionLocal() as db:
        for i in range(0, len(payload), BATCH):
            chunk = payload[i : i + BATCH]
            if dialect == "postgresql":
                stmt = pg_insert(ExchangeRate).values(chunk)
                stmt = stmt.on_conflict_do_nothing(index_elements=["rate_date", "currency"])
            elif dialect == "sqlite":
                stmt = sqlite_insert(ExchangeRate).values(chunk)
                stmt = stmt.on_conflict_do_nothing(index_elements=["rate_date", "currency"])
            else:  # pragma: no cover - other dialects unused in this project
                stmt = ExchangeRate.__table__.insert().values(chunk)
            db.execute(stmt)
            n += len(chunk)
        db.commit()
    return n


def _cached_date_range(currency: str = "USD") -> tuple[str | None, str | None]:
    with SessionLocal() as db:
        row = db.execute(
            select(func.min(ExchangeRate.rate_date), func.max(ExchangeRate.rate_date)).where(
                ExchangeRate.currency == currency
            )
        ).one()
    mn, mx = row
    if mn is None:
        return None, None
    return mn.isoformat(), mx.isoformat()


# ── Public API ────────────────────────────────────────────────────────────────


def sync_rates() -> int:
    """Incremental sync — call from a background thread, NOT from a request.

    1. No data in DB → download full history (once ever)
    2. Data exists, stale → download 90-day feed (only new dates upserted)
    3. Data already fresh (≤1 day old) → skip entirely
    """
    min_cached, max_cached = _cached_date_range("USD")

    if not min_cached:
        print("[ecb-sync] No cached rates — downloading full ECB history...")
        rows = _parse_ecb_rates(_fetch_ecb_xml(_ECB_FULL_URL))
        n = _upsert_rates(rows)
        print(f"[ecb-sync] Loaded {n} rates (full history)")
        return n

    today = datetime.now(timezone.utc).date()
    max_date = date.fromisoformat(max_cached)
    gap_days = (today - max_date).days
    if gap_days <= 1:
        print(f"[ecb-sync] Rates already fresh (last: {max_cached})")
        return 0

    print(f"[ecb-sync] Updating rates (last: {max_cached}, gap: {gap_days}d)...")
    rows = _parse_ecb_rates(_fetch_ecb_xml(_ECB_90D_URL))
    new_rows = [(d, c, r) for d, c, r in rows if d > max_cached]
    if new_rows:
        n = _upsert_rates(new_rows)
        print(f"[ecb-sync] Added {n} new rate entries")
        return n
    print("[ecb-sync] 90-day feed had no new dates")
    return 0


def get_rate(currency: str, on: date | str | None) -> Decimal | None:
    """EUR reference rate for `currency` on a date. DB-only, no HTTP.

    Returns units of `currency` per 1 EUR. Falls back to the nearest
    available date (±7 days) for weekends/holidays. Returns None if the
    currency/date isn't cached at all.
    """
    if currency == "EUR":
        return Decimal(1)
    if on is None:
        return None
    target = on if isinstance(on, date) else date.fromisoformat(on)

    with SessionLocal() as db:
        exact = db.execute(
            select(ExchangeRate.rate).where(
                ExchangeRate.currency == currency, ExchangeRate.rate_date == target
            )
        ).scalar_one_or_none()
        if exact is not None:
            return exact

        # Nearest available within ±7 days (weekends/holidays have no fixing)
        for delta in range(1, 8):
            for direction in (-1, 1):
                nearby = target + timedelta(days=delta * direction)
                rate = db.execute(
                    select(ExchangeRate.rate).where(
                        ExchangeRate.currency == currency, ExchangeRate.rate_date == nearby
                    )
                ).scalar_one_or_none()
                if rate is not None:
                    return rate
    return None


def to_eur(amount: Decimal | float, currency: str, on: date | str | None) -> Decimal | None:
    """Convert an amount in a foreign currency to EUR using the cached rate."""
    amt = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    if currency == "EUR":
        return amt
    rate = get_rate(currency, on)
    if rate is None or rate == 0:
        return None
    return amt / rate
