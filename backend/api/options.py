"""Options monitor API — watchlist, snapshots, alerts, agent control."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    AgentCycleResult,
    AgentStatusOut,
    OptionsAlertOut,
    OptionsSnapshotOut,
    UnusualActivityOut,
    WatchlistItemIn,
    WatchlistItemOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.models import (
    OptionsAgentLog,
    OptionsAlert,
    OptionsHiddenPortfolioTicker,
    OptionsSnapshot,
    UnusualActivity,
    WatchlistItem,
)
from backend.services.options_agent import run_cycle
from backend.services.options_scraper import fetch_options

# ── Availability cache ───────────────────────────────────────────────
# ticker → (has_options, timestamp); 24-hour TTL
_availability_cache: dict[str, tuple[bool, float]] = {}
_AVAIL_TTL = 86_400  # seconds

router = APIRouter(prefix="/options", tags=["options"])

_404 = {404: {"description": "Not found"}}
_now = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── Watchlist CRUD ───────────────────────────────────────────────────


@router.get("/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(db: DbSession, user: CurrentUser):
    return (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.created_at)
        .all()
    )


@router.post(
    "/watchlist",
    response_model=WatchlistItemOut,
    status_code=201,
    responses={409: {"description": "Ticker already in watchlist"}},
)
def add_watchlist_item(body: WatchlistItemIn, db: DbSession, user: CurrentUser):
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id, WatchlistItem.ticker == body.ticker.upper())
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ticker already in watchlist")

    item = WatchlistItem(user_id=user.id, ticker=body.ticker.upper(), name=body.name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/watchlist/{item_id}", responses=_404)
def toggle_watchlist_item(item_id: int, db: DbSession, user: CurrentUser):
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.enabled = not item.enabled
    db.commit()
    return {"id": item.id, "enabled": item.enabled}


@router.delete("/watchlist/{item_id}", status_code=204, responses=_404)
def remove_watchlist_item(item_id: int, db: DbSession, user: CurrentUser):
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    ticker = item.ticker
    db.delete(item)
    db.query(OptionsAlert).filter(
        OptionsAlert.user_id == user.id, OptionsAlert.ticker == ticker
    ).delete(synchronize_session=False)
    db.query(UnusualActivity).filter(
        UnusualActivity.user_id == user.id, UnusualActivity.ticker == ticker
    ).delete(synchronize_session=False)
    db.query(OptionsSnapshot).filter(
        OptionsSnapshot.user_id == user.id, OptionsSnapshot.ticker == ticker
    ).delete(synchronize_session=False)
    db.commit()


# ── Snapshots ────────────────────────────────────────────────────────


@router.get("/snapshots", response_model=list[OptionsSnapshotOut])
def list_snapshots(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
    days: int = 7,
    limit: int = 100,
):
    q = (
        db.query(OptionsSnapshot)
        .filter(
            OptionsSnapshot.user_id == user.id,
            OptionsSnapshot.timestamp >= _now() - timedelta(days=days),
        )
    )
    if ticker:
        q = q.filter(OptionsSnapshot.ticker == ticker.upper())
    return q.order_by(OptionsSnapshot.timestamp.desc()).limit(limit).all()


@router.get("/chain/{ticker}", responses=_404)
def get_ticker_chain(ticker: str, user: CurrentUser):
    """Fetch live options chain for a ticker without requiring a stored snapshot."""
    data = fetch_options(ticker.upper())
    if not data:
        raise HTTPException(status_code=404, detail="No options data found for this ticker")
    return {
        "ticker": data["ticker"],
        "timestamp": data["timestamp"],
        "calls": data["calls"],
        "puts": data["puts"],
    }


@router.get("/snapshots/{snapshot_id}/chain", responses=_404)
def get_snapshot_chain(snapshot_id: int, db: DbSession, user: CurrentUser):
    snap = (
        db.query(OptionsSnapshot)
        .filter(OptionsSnapshot.id == snapshot_id, OptionsSnapshot.user_id == user.id)
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    chain = json.loads(snap.chain_data) if snap.chain_data else {"calls": [], "puts": []}
    return {"ticker": snap.ticker, "timestamp": snap.timestamp, **chain}


# ── Alerts ───────────────────────────────────────────────────────────


@router.get("/alerts", response_model=list[OptionsAlertOut])
def list_alerts(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
    unread: bool = False,
    days: int = 7,
    limit: int = 100,
):
    q = (
        db.query(OptionsAlert)
        .filter(
            OptionsAlert.user_id == user.id,
            OptionsAlert.timestamp >= _now() - timedelta(days=days),
        )
    )
    if ticker:
        q = q.filter(OptionsAlert.ticker == ticker.upper())
    if unread:
        q = q.filter(OptionsAlert.acknowledged.is_(False))
    return q.order_by(OptionsAlert.timestamp.desc()).limit(limit).all()


@router.patch("/alerts/{alert_id}/ack", responses=_404)
def acknowledge_alert(alert_id: int, db: DbSession, user: CurrentUser):
    alert = (
        db.query(OptionsAlert)
        .filter(OptionsAlert.id == alert_id, OptionsAlert.user_id == user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    db.commit()
    return {"id": alert.id, "acknowledged": True}


@router.post("/alerts/ack-all")
def acknowledge_all_alerts(db: DbSession, user: CurrentUser):
    count = (
        db.query(OptionsAlert)
        .filter(OptionsAlert.user_id == user.id, OptionsAlert.acknowledged.is_(False))
        .update({"acknowledged": True})
    )
    db.commit()
    return {"acknowledged": count}


# ── Unusual Activity ─────────────────────────────────────────────────


@router.get("/unusual", response_model=list[UnusualActivityOut])
def list_unusual_activity(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
    days: int = 7,
    limit: int = 50,
):
    q = (
        db.query(UnusualActivity)
        .filter(
            UnusualActivity.user_id == user.id,
            UnusualActivity.timestamp >= _now() - timedelta(days=days),
        )
    )
    if ticker:
        q = q.filter(UnusualActivity.ticker == ticker.upper())
    return q.order_by(UnusualActivity.timestamp.desc()).limit(limit).all()


# ── Hidden portfolio tickers ─────────────────────────────────────────


class _HideTicker(BaseModel):
    ticker: str


@router.get("/portfolio/hidden")
def list_hidden_portfolio(db: DbSession, user: CurrentUser):
    rows = (
        db.query(OptionsHiddenPortfolioTicker)
        .filter(OptionsHiddenPortfolioTicker.user_id == user.id)
        .all()
    )
    return [r.ticker for r in rows]


@router.post("/portfolio/hidden", status_code=201)
def hide_portfolio_ticker(body: _HideTicker, db: DbSession, user: CurrentUser):
    ticker = body.ticker.upper()
    existing = (
        db.query(OptionsHiddenPortfolioTicker)
        .filter(
            OptionsHiddenPortfolioTicker.user_id == user.id,
            OptionsHiddenPortfolioTicker.ticker == ticker,
        )
        .first()
    )
    if not existing:
        db.add(OptionsHiddenPortfolioTicker(user_id=user.id, ticker=ticker))
        db.commit()
    return {"ticker": ticker}


@router.delete("/portfolio/hidden/{ticker}", status_code=204)
def unhide_portfolio_ticker(ticker: str, db: DbSession, user: CurrentUser):
    db.query(OptionsHiddenPortfolioTicker).filter(
        OptionsHiddenPortfolioTicker.user_id == user.id,
        OptionsHiddenPortfolioTicker.ticker == ticker.upper(),
    ).delete(synchronize_session=False)
    db.commit()


# ── Options availability check ────────────────────────────────────────


class _TickerListIn(BaseModel):
    tickers: list[str]


def _check_single_availability(ticker: str) -> tuple[str, bool]:
    """Light availability check: does the ticker have any options expirations?"""
    try:
        import yfinance as yf
        from backend.services.options_scraper import _EUREX_RDF_CACHE, _EUREX_SUFFIXES

        # Fast path: if Eurex RDF is already loaded, check it first for European tickers
        if any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
            if _EUREX_RDF_CACHE.get("sym_to_code"):
                sym = ticker.split(".")[0].upper()
                return ticker, sym in _EUREX_RDF_CACHE["sym_to_code"]
            # RDF not loaded yet — assume European tickers have options
            return ticker, True

        t = yf.Ticker(ticker)
        return ticker, bool(t.options)
    except Exception:
        return ticker, False


@router.post("/check-availability")
def check_options_availability(body: _TickerListIn, user: CurrentUser):
    """Return which tickers have options available (cached 24 h)."""
    now = time.time()
    uncached = []
    results: dict[str, bool] = {}

    for raw in body.tickers:
        ticker = raw.upper()
        cached = _availability_cache.get(ticker)
        if cached and now - cached[1] < _AVAIL_TTL:
            results[ticker] = cached[0]
        else:
            uncached.append(ticker)

    if uncached:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_check_single_availability, t): t for t in uncached}
            for future in as_completed(futures, timeout=20):
                try:
                    ticker, has_opt = future.result()
                    _availability_cache[ticker] = (has_opt, now)
                    results[ticker] = has_opt
                except Exception:
                    ticker = futures[future]
                    results[ticker] = True  # default to visible on error

    has_options = [t for t, v in results.items() if v]
    no_options = [t for t, v in results.items() if not v]
    return {"has_options": has_options, "no_options": no_options}


# ── Agent Control ────────────────────────────────────────────────────

_scheduler_running = False


@router.post("/agent/run", response_model=AgentCycleResult)
def trigger_cycle(user: CurrentUser):
    """Manually trigger one monitoring cycle."""
    result = run_cycle(user.id)
    return AgentCycleResult(**result)


@router.get("/agent/status", response_model=AgentStatusOut)
def agent_status(db: DbSession, user: CurrentUser):
    last_log = (
        db.query(OptionsAgentLog)
        .filter(OptionsAgentLog.user_id == user.id)
        .order_by(OptionsAgentLog.timestamp.desc())
        .first()
    )
    total = (
        db.query(func.count(OptionsAgentLog.id))
        .filter(OptionsAgentLog.user_id == user.id)
        .scalar()
    )
    return AgentStatusOut(
        running=_scheduler_running,
        interval_minutes=settings.options_monitor_interval_minutes,
        last_cycle=last_log.timestamp if last_log else None,
        total_cycles=total or 0,
    )


@router.post("/agent/start")
def start_scheduler(user: CurrentUser):
    """Start the APScheduler background job for this user."""
    global _scheduler_running
    from backend.services.options_scheduler import start_user_schedule

    start_user_schedule(user.id)
    _scheduler_running = True
    return {"status": "started", "interval_minutes": settings.options_monitor_interval_minutes}


@router.post("/agent/stop")
def stop_scheduler(user: CurrentUser):
    """Stop the APScheduler background job."""
    global _scheduler_running
    from backend.services.options_scheduler import stop_user_schedule

    stop_user_schedule(user.id)
    _scheduler_running = False
    return {"status": "stopped"}
