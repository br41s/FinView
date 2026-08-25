"""Stock split history, cached so the import path stops calling Yahoo in a loop.

`data_supervisor._check_split_candidates` asked yfinance for a ticker's split
history once per distinct ticker in the portfolio, with no cache of any kind.
A 50-position portfolio meant 50 sequential network calls inside a single
import request — on a Cloud Run revision with `--cpu-throttling` and
`--max-instances=1`, where production work has to finish inside the request.

Split history is close to static: a company splits a few times per decade. It
is cached in the DB rather than in memory because `--min=0` means a cold start
throws away anything in-process, which is most of them.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from backend.models import SplitHistoryCache

logger = logging.getLogger(__name__)

TTL = timedelta(days=30)

Splits = list[tuple[date, Decimal]]


def _fetch(ticker: str) -> Splits | None:
    """Ask Yahoo. Returns None on failure — deliberately distinct from empty.

    The difference carries weight: most tickers have genuinely never split, and
    that empty list is a real answer worth caching. A network failure is not,
    or one Yahoo outage would pin "never split" on a real security for a month.
    """
    try:
        import yfinance as yf

        raw = yf.Ticker(ticker).splits
    except Exception as e:
        logger.debug("Failed to get splits for %s: %s", ticker, e)
        return None

    if raw is None:
        return None

    out: Splits = []
    try:
        for dt, ratio in raw.items():
            out.append((dt.date() if hasattr(dt, "date") else dt, Decimal(str(ratio))))
    except Exception as e:
        logger.debug("Unparseable split history for %s: %s", ticker, e)
        return None
    return out


def _decode(payload: str) -> Splits | None:
    try:
        return [(date.fromisoformat(d), Decimal(r)) for d, r in json.loads(payload)]
    except (ValueError, TypeError, InvalidOperation):
        return None


def _encode(splits: Splits) -> str:
    return json.dumps([[d.isoformat(), str(r)] for d, r in splits])


def _fresh(row: SplitHistoryCache | None, now: datetime) -> Splits | None:
    """Decoded splits when the row is present, readable and still inside TTL."""
    if row is None or row.fetched_at is None:
        return None
    fetched = row.fetched_at
    # Stored naive — the column carries no timezone — but always written in UTC.
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    if now - fetched >= TTL:
        return None
    return _decode(row.splits)


def _resolve(db: Session, row: SplitHistoryCache | None, ticker: str, now: datetime) -> Splits:
    cached = _fresh(row, now)
    if cached is not None:
        return cached

    fetched = _fetch(ticker)
    if fetched is None:
        # Serve a stale entry rather than claim the security has never split
        # just because Yahoo was unreachable. Nothing is written, so the next
        # run retries instead of inheriting the failure.
        return (_decode(row.splits) or []) if row is not None else []

    payload = _encode(fetched)
    if row is None:
        db.add(SplitHistoryCache(ticker=ticker, splits=payload, fetched_at=now))
    else:
        row.splits = payload
        row.fetched_at = now
    return fetched


def prefetch(db: Session, tickers: list[str]) -> dict[str, Splits]:
    """Split history for many tickers, reading every cached row in one query.

    Does not commit — the caller owns the transaction, matching the rest of the
    supervisor, so a cached row lands with the import that fetched it.
    """
    wanted = list(dict.fromkeys(t for t in tickers if t))
    if not wanted:
        return {}

    now = datetime.now(timezone.utc)
    rows = {
        r.ticker: r
        for r in db.query(SplitHistoryCache).filter(SplitHistoryCache.ticker.in_(wanted)).all()
    }
    return {ticker: _resolve(db, rows.get(ticker), ticker, now) for ticker in wanted}
