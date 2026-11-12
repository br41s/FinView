"""Living World events from what other parts of FinView already stored.

The town never calls Yahoo. Each event here is read from a table another feature fills:
Zonas Clave's price history and alerts, the split cache, the annual-report reader, the geo
signals and the ledger. When a source does not cover a holding, that holding simply gets no
event of that kind: a gap in stored data is never read as "nothing happened".

Every function returns plain facts (type, ISIN, date or time, figures); the copy and the
priority are the frontend's (`model/realEvents.ts`).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.services.geo.owner import geo_owner_id
from backend.models import (
    Account,
    GeoSignal,
    GeoSignalTicker,
    SegmentReport,
    SplitHistoryCache,
    TechnicalSignal,
    Transaction,
    TransactionType,
    ZonasClaveAnalysis,
    ZonasClaveWatchlistItem,
)

logger = logging.getLogger(__name__)

# A year of closes must really be a year: at least this many sessions, starting this far back.
YEAR_MIN_BARS = 200
YEAR_MIN_SPAN_DAYS = 350
# Unusual volume: the last session against the average of the ones before it.
VOLUME_LOOKBACK = 20
VOLUME_SPIKE_RATIO = 2.5
# Dividend per share against the one a year earlier. Interim and final payments differ, so
# only a payment ~1 year back is comparable; the threshold sits above a year of EUR/USD noise
# (the ledger stores what was collected in euros) and the cap discards obvious data slips.
DIVIDEND_COMPARE_DAYS = (300, 430)
DIVIDEND_CHANGE_PCT = 15.0
DIVIDEND_CHANGE_CAP_PCT = 200.0


def _iso_utc(dt: datetime) -> str:
    """Stored datetimes are naive UTC."""
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _event(id_: str, type_: str, isin: str, name: str, on: date, source: str,
           confidence: str, metrics: dict, at: datetime | None = None) -> dict:
    return {
        "id": id_,
        "event_type": type_,
        "isin": isin,
        "name": name,
        "occurred_on": on,
        "occurred_at": _iso_utc(at) if at else None,
        "source_type": source,
        "confidence": confidence,
        "metrics": metrics,
    }


# ── Zonas Clave price history: 52-week extremes and unusual volume ────────────


def _latest_histories(db: Session, user_id: int, tickers: set[str]) -> dict[str, list[dict]]:
    """Each watched ticker's newest stored price history (Zonas Clave), by ticker."""
    if not tickers:
        return {}
    items = (
        db.query(ZonasClaveWatchlistItem)
        .filter(ZonasClaveWatchlistItem.user_id == user_id, ZonasClaveWatchlistItem.ticker.in_(tickers))
        .all()
    )
    out: dict[str, list[dict]] = {}
    for item in items:
        latest = (
            db.query(ZonasClaveAnalysis.price_history)
            .filter(ZonasClaveAnalysis.watchlist_item_id == item.id)
            .order_by(ZonasClaveAnalysis.timestamp.desc())
            .first()
        )
        if not latest or not latest.price_history:
            continue
        try:
            bars = [
                {"date": date.fromisoformat(b["date"][:10]), "close": float(b["close"]),
                 "volume": int(b.get("volume") or 0)}
                for b in json.loads(latest.price_history)
                if b.get("close") is not None
            ]
        except (ValueError, TypeError, KeyError):
            logger.warning("living world: unreadable price history for %s", item.ticker)
            continue
        out[item.ticker] = sorted(bars, key=lambda b: b["date"])
    return out


def _year_extremes(isin: str, name: str, ticker: str, bars: list[dict], since: date) -> list[dict]:
    if not bars:
        return []
    last = bars[-1]
    if last["date"] < since:
        return []
    start = last["date"] - timedelta(days=365)
    year = [b for b in bars[:-1] if b["date"] >= start]
    if len(year) < YEAR_MIN_BARS or (last["date"] - year[0]["date"]).days < YEAR_MIN_SPAN_DAYS:
        return []
    high = max(b["close"] for b in year)
    low = min(b["close"] for b in year)
    if last["close"] > high:
        kind, previous = "week52_high", high
    elif last["close"] < low:
        kind, previous = "week52_low", low
    else:
        return []
    return [_event(
        f"52w:{isin}:{last['date'].isoformat()}", kind, isin, name, last["date"], "zonas_clave",
        "derived", {"close": last["close"], "previous_extreme": previous, "ticker": ticker},
    )]


def _volume_spike(isin: str, name: str, ticker: str, bars: list[dict], since: date) -> list[dict]:
    if len(bars) <= VOLUME_LOOKBACK or bars[-1]["date"] < since:
        return []
    last = bars[-1]
    before = [b["volume"] for b in bars[-VOLUME_LOOKBACK - 1:-1] if b["volume"] > 0]
    # A thin record (missing volumes) cannot say what is unusual.
    if len(before) < VOLUME_LOOKBACK * 0.8 or last["volume"] <= 0:
        return []
    average = sum(before) / len(before)
    ratio = last["volume"] / average
    if ratio < VOLUME_SPIKE_RATIO:
        return []
    return [_event(
        f"vol:{isin}:{last['date'].isoformat()}", "volume_spike", isin, name, last["date"],
        "zonas_clave", "derived",
        {"volume": last["volume"], "average_volume": round(average), "volume_ratio": round(ratio, 2)},
    )]


# ── Splits, shares received, dividends per share ──────────────────────────────


def _splits(db: Session, yahoo: dict[str, str], names: dict[str, str], since: date, today: date) -> list[dict]:
    by_ticker: dict[str, list[str]] = {}
    for isin, ticker in yahoo.items():
        by_ticker.setdefault(ticker, []).append(isin)
    if not by_ticker:
        return []
    out = []
    for row in db.query(SplitHistoryCache).filter(SplitHistoryCache.ticker.in_(by_ticker)):
        try:
            splits = [(date.fromisoformat(d), Decimal(r)) for d, r in json.loads(row.splits)]
        except (ValueError, TypeError):
            continue
        for day, ratio in splits:
            if not since <= day <= today:
                continue
            out.extend(
                _event(
                    f"split:{isin}:{day.isoformat()}", "stock_split", isin, names[isin], day,
                    "split_history", "reported", {"ratio": float(ratio), "ticker": row.ticker},
                )
                for isin in by_ticker[row.ticker]
            )
    return out


def _ledger(db: Session, user_id: int):
    return (
        db.query(Transaction, Account.broker)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id, Transaction.isin.isnot(None))
    )


def _shares_received(db: Session, user_id: int, open_isins: set[str], since: date) -> list[dict]:
    """Shares that arrived without a purchase, for an ISIN never held before.

    The ledger files a spinoff, a dividend reinvestment and a rights allocation alike (SPINOFF).
    A reinvestment adds to an ISIN already held and rights are sold off within days, so the
    first row of an ISIN that is still held is the one that reads as "a new company arrived".
    It is called what it is, shares received in a corporate action, never "a spinoff".
    """
    out = []
    received = (
        _ledger(db, user_id)
        .filter(Transaction.type == TransactionType.SPINOFF, Transaction.trade_date >= since)
        .all()
    )
    for tx, broker in received:
        if tx.isin not in open_isins:
            continue
        earlier = (
            db.query(Transaction.id)
            .join(Account, Transaction.account_id == Account.id)
            .filter(
                Account.user_id == user_id,
                Transaction.isin == tx.isin,
                (Transaction.trade_date < tx.trade_date)
                | ((Transaction.trade_date == tx.trade_date) & (Transaction.id < tx.id)),
            )
            .first()
        )
        if earlier:
            continue
        out.append(_event(
            f"recv:{tx.id}", "shares_received", tx.isin, tx.name or tx.isin, tx.trade_date, "ledger",
            "verified", {"quantity": float(abs(tx.quantity)), "account": getattr(broker, "value", broker)},
        ))
    return out


def _held_on(rows: list[Transaction], day: date) -> Decimal:
    held = Decimal(0)
    for tx in rows:
        if tx.trade_date > day:
            break
        if tx.type in (TransactionType.BUY, TransactionType.SPINOFF):
            held += abs(tx.quantity)
        elif tx.type == TransactionType.SELL:
            held -= abs(tx.quantity)
    return held


def _dividend_changes(db: Session, user_id: int, since: date) -> list[dict]:
    """A dividend whose amount per share moved against the one collected a year before.

    Per share = net euros collected ÷ shares held that day, both from the ledger (most
    importers do not store a per-share amount). Shares bought between the ex-date and the pay
    date would distort it; the threshold absorbs ordinary noise, not that.
    """
    recent = (
        _ledger(db, user_id)
        .filter(Transaction.type == TransactionType.DIVIDEND, Transaction.trade_date >= since)
        .all()
    )
    out = []
    for tx, _broker in recent:
        history = [
            t for t, _b in _ledger(db, user_id)
            .filter(Transaction.isin == tx.isin)
            .order_by(Transaction.trade_date, Transaction.id)
            .all()
        ]
        lo, hi = DIVIDEND_COMPARE_DAYS
        earlier = [
            t for t in history
            if t.type == TransactionType.DIVIDEND
            and lo <= (tx.trade_date - t.trade_date).days <= hi
        ]
        if not earlier:
            continue
        prev = min(earlier, key=lambda t: abs((tx.trade_date - t.trade_date).days - 365))
        now_held, prev_held = _held_on(history, tx.trade_date), _held_on(history, prev.trade_date)
        if now_held <= 0 or prev_held <= 0 or prev.net_amount_eur <= 0:
            continue
        per_share = tx.net_amount_eur / now_held
        prev_per_share = prev.net_amount_eur / prev_held
        change = float((per_share / prev_per_share - 1) * 100)
        if abs(change) < DIVIDEND_CHANGE_PCT or abs(change) > DIVIDEND_CHANGE_CAP_PCT:
            continue
        out.append(_event(
            f"divchg:{tx.id}", "dividend_raised" if change > 0 else "dividend_cut", tx.isin,
            tx.name or tx.isin, tx.trade_date, "ledger", "derived",
            {
                "per_share_eur": round(float(per_share), 4),
                "previous_per_share_eur": round(float(prev_per_share), 4),
                "previous_date": prev.trade_date.isoformat(),
                "change_pct": round(change, 2),
            },
        ))
    return out


# ── Annual reports, geo signals, Zonas Clave alerts ───────────────────────────


def _annual_reports(db: Session, names: dict[str, str], since: date) -> list[dict]:
    """A new annual report FinView read. The date is when FinView stored it: the filing's own
    publication date is not kept."""
    rows = db.query(SegmentReport).filter(
        SegmentReport.isin.in_(names), SegmentReport.created_at >= datetime.combine(since, datetime.min.time())
    )
    return [
        _event(
            f"report:{r.isin}:{r.fiscal_year}", "annual_report", r.isin, names[r.isin],
            r.created_at.date(), "segment_reports", "verified",
            {"fiscal_year": r.fiscal_year, "source": r.source, "period_end": r.period_end.isoformat() if r.period_end else None},
        )
        for r in rows
    ]


def _geo_alerts(db: Session, yahoo: dict[str, str], names: dict[str, str], since: date) -> list[dict]:
    """Geopolitical signals that were sent out and name one of the user's holdings.

    Read exactly as `/geo` reads them: the shared rows of the system owner
    (`geo/owner.py`), never another account's copies.
    """
    by_ticker: dict[str, list[str]] = {}
    for isin, ticker in yahoo.items():
        by_ticker.setdefault(ticker.upper(), []).append(isin)
    if not by_ticker:
        return []
    rows = (
        db.query(GeoSignal, GeoSignalTicker)
        .join(GeoSignalTicker, GeoSignalTicker.signal_id == GeoSignal.id)
        .filter(
            GeoSignal.user_id == geo_owner_id(db),
            GeoSignal.notified_at.isnot(None),
            GeoSignal.notified_at >= datetime.combine(since, datetime.min.time()),
            GeoSignalTicker.symbol.in_(by_ticker),
        )
    )
    out = []
    for signal, leg in rows:
        out.extend(
            _event(
                f"geo:{signal.id}:{isin}", "geo_alert", isin, names[isin], signal.notified_at.date(),
                "geo_signals", "derived",
                {
                    "headline": signal.headline,
                    "country": signal.country,
                    "importance": signal.importance,
                    "direction": getattr(leg.direction, "value", leg.direction),
                },
                at=signal.notified_at,
            )
            for isin in by_ticker[leg.symbol.upper()]
        )
    return out


def _zone_alerts(db: Session, user_id: int, yahoo: dict[str, str], names: dict[str, str], since: date) -> list[dict]:
    """Zonas Clave alerts the user was sent for a holding (only the alerted ones: every scored
    candidate is stored too, and those were never shown as alerts)."""
    by_ticker: dict[str, list[str]] = {}
    for isin, ticker in yahoo.items():
        by_ticker.setdefault(ticker, []).append(isin)
    if not by_ticker:
        return []
    rows = db.query(TechnicalSignal).filter(
        TechnicalSignal.user_id == user_id,
        TechnicalSignal.alerted.is_(True),
        TechnicalSignal.ticker.in_(by_ticker),
        TechnicalSignal.created_at >= datetime.combine(since, datetime.min.time()),
    )
    out = []
    for s in rows:
        out.extend(
            _event(
                f"zone:{s.id}:{isin}", "technical_signal", isin, names[isin], s.created_at.date(),
                "zonas_clave", "derived",
                {
                    "zone": s.zone_type or None,
                    "zone_level": float(s.zone_level),
                    "price": float(s.price_at_signal),
                    "distance_pct": round(float(s.distance_pct), 2),
                },
                at=s.created_at,
            )
            for isin in by_ticker[s.ticker]
        )
    return out


def market_events(
    db: Session,
    user_id: int,
    open_names: dict[str, str],
    yahoo: dict[str, str],
    since: date,
    today: date,
) -> list[dict]:
    """Every stored-data event of the window for the user's open holdings.

    `open_names`: ISIN → name of what is held now; `yahoo`: ISIN → Yahoo ticker for those
    ISINs, from the stored ticker map (no lookup).
    """
    events: list[dict] = []
    histories = _latest_histories(db, user_id, set(yahoo.values()))
    for isin, ticker in yahoo.items():
        bars = histories.get(ticker)
        if bars:
            events += _year_extremes(isin, open_names[isin], ticker, bars, since)
            events += _volume_spike(isin, open_names[isin], ticker, bars, since)
    events += _splits(db, yahoo, open_names, since, today)
    events += _shares_received(db, user_id, set(open_names), since)
    events += _dividend_changes(db, user_id, since)
    events += _annual_reports(db, open_names, since)
    events += _geo_alerts(db, yahoo, open_names, since)
    events += _zone_alerts(db, user_id, yahoo, open_names, since)
    return events
