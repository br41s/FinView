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
    AskIn,
    AskOut,
    BacktestSignalOut,
    BacktestStatsOut,
    OptionsAlertOut,
    OptionsSnapshotOut,
    UnusualActivityOut,
    WatchlistItemIn,
    WatchlistItemOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.models import (
    BacktestSignal,
    OptionsAgentLog,
    OptionsAlert,
    OptionsHiddenPortfolioTicker,
    OptionsSnapshot,
    UnusualActivity,
    WatchlistItem,
)
from backend.services.notification_service import send_telegram
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
        from backend.services.options_scraper import (
            _EUREX_RDF_CACHE, _EUREX_SUFFIXES, _ISIN_RE,
        )

        # ISINs — we can't cheaply determine options availability across all markets
        # (Spanish ISINs → MEFF, German → Eurex, UK → LSE/Eurex, etc.).
        # Always include them; users can manually hide positions with no data.
        if _ISIN_RE.match(ticker):
            return ticker, True

        # European exchange suffix (e.g. BAS.DE, AIR.PA) — check Eurex RDF
        if any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
            rdf_sym = _EUREX_RDF_CACHE.get("sym_to_code", {})
            if rdf_sym:
                sym = ticker.split(".")[0].upper()
                return ticker, sym in rdf_sym
            return ticker, True

        t = yf.Ticker(ticker)
        return ticker, bool(t.options)
    except Exception:
        return ticker, False


def _invalidate_european_availability_cache() -> None:
    """Remove stale False entries for ISINs and European tickers after the Eurex RDF loads."""
    from backend.services.options_scraper import _EUREX_RDF_CACHE, _EUREX_SUFFIXES, _ISIN_RE
    rdf_sym = _EUREX_RDF_CACHE.get("sym_to_code", {})
    to_delete = [
        t for t, (v, _) in list(_availability_cache.items())
        if not v and (
            _ISIN_RE.match(t)  # all ISINs now always return True
            or (
                any(t.endswith(s.upper()) for s in _EUREX_SUFFIXES)
                and t.split(".")[0] in rdf_sym
            )
        )
    ]
    for t in to_delete:
        _availability_cache.pop(t, None)
    if to_delete:
        import logging
        logging.getLogger(__name__).info(
            "Invalidated %d stale availability entries after Eurex RDF load", len(to_delete)
        )


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


# ── Backtest ─────────────────────────────────────────────────────────


@router.get("/backtest", response_model=list[BacktestSignalOut])
def list_backtest_signals(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
    days: int = 30,
    limit: int = 200,
):
    """Return recorded backtest signals with their outcome data."""
    q = (
        db.query(BacktestSignal)
        .filter(
            BacktestSignal.user_id == user.id,
            BacktestSignal.recorded_at >= _now() - timedelta(days=days),
        )
    )
    if ticker:
        q = q.filter(BacktestSignal.ticker == ticker.upper())
    return q.order_by(BacktestSignal.recorded_at.desc()).limit(limit).all()


@router.get("/backtest/stats", response_model=BacktestStatsOut)
def backtest_stats(
    db: DbSession,
    user: CurrentUser,
    ticker: str | None = None,
):
    """Return accuracy statistics for all completed backtest signals."""
    from backend.services.backtest_service import get_stats

    return get_stats(db, user.id, ticker=ticker)


@router.post("/backtest/evaluate", status_code=200)
def trigger_backtest_evaluation(db: DbSession, user: CurrentUser):
    """Manually trigger outcome evaluation for pending signals."""
    from backend.services.backtest_service import evaluate_pending

    updated = evaluate_pending(db, user.id)
    return {"evaluated": updated}


@router.post("/test-telegram", status_code=200)
def test_telegram(user: CurrentUser):
    """Send a test message to the configured Telegram bot.

    Returns whether the message was delivered. Requires
    FINVIEW_TELEGRAM_BOT_TOKEN and FINVIEW_TELEGRAM_CHAT_ID to be set.
    """
    configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram not configured — set FINVIEW_TELEGRAM_BOT_TOKEN and FINVIEW_TELEGRAM_CHAT_ID.",
        )

    from datetime import datetime, timezone

    text = (
        "✅ *FinView — test de conexión Telegram*\n"
        f"Usuario: `{user.email}`\n"
        f"Hora: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`\n\n"
        "La integración funciona correctamente. "
        "Recibirás aquí las alertas HIGH y los premium spikes."
    )
    ok = send_telegram(text)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telegram delivery failed — check bot token and chat ID.",
        )
    return {"sent": True, "chat_id": settings.telegram_chat_id}


# ── Agent chat ───────────────────────────────────────────────────────


@router.post("/ask", response_model=AskOut)
def ask_agent(body: AskIn, db: DbSession, user: CurrentUser):  # noqa: C901
    """Stateless Q&A with the options agent.

    Provides the model with: last agent cycle log + latest snapshots (top 8 by
    timestamp) + unacknowledged HIGH alerts. History is passed in by the client
    so the endpoint itself stays stateless.
    """
    try:
        import anthropic as _anthropic
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthropic SDK not installed.",
        )

    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FINVIEW_ANTHROPIC_API_KEY not configured.",
        )

    if not body.question.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty question.")

    # ── Build context ──────────────────────────────────────────────
    ctx_parts: list[str] = []

    # Last agent cycle log
    last_log = (
        db.query(OptionsAgentLog)
        .filter(OptionsAgentLog.user_id == user.id)
        .order_by(OptionsAgentLog.timestamp.desc())
        .first()
    )
    if last_log:
        log_data = last_log.result_json or {}
        ctx_parts.append(
            f"=== Último ciclo del agente ({last_log.timestamp.strftime('%Y-%m-%d %H:%M UTC')}) ===\n"
            + json.dumps(log_data, ensure_ascii=False, indent=2)[:3000]
        )

    # Latest snapshots (8 most recent, one per ticker)
    snapshots = (
        db.query(OptionsSnapshot)
        .filter(OptionsSnapshot.user_id == user.id)
        .order_by(OptionsSnapshot.timestamp.desc())
        .limit(40)
        .all()
    )
    seen_tickers: set[str] = set()
    snap_lines: list[str] = []
    for s in snapshots:
        if s.ticker in seen_tickers or len(seen_tickers) >= 8:
            continue
        seen_tickers.add(s.ticker)
        snap_lines.append(
            f"{s.ticker}: precio={s.current_price} "
            f"P/C={s.put_call_ratio_volume} "
            f"IV_call={s.avg_call_iv} IV_put={s.avg_put_iv} "
            f"HV={s.historical_volatility} "
            f"skew={s.iv_skew} sentiment={s.market_sentiment}"
        )
    if snap_lines:
        ctx_parts.append("=== Snapshots recientes ===\n" + "\n".join(snap_lines))

    # Unacknowledged HIGH alerts
    high_alerts = (
        db.query(OptionsAlert)
        .filter(
            OptionsAlert.user_id == user.id,
            OptionsAlert.severity == "HIGH",
            OptionsAlert.acknowledged.is_(False),
        )
        .order_by(OptionsAlert.timestamp.desc())
        .limit(10)
        .all()
    )
    if high_alerts:
        alert_lines = [f"[{a.ticker}] {a.alert_type}: {a.message}" for a in high_alerts]
        ctx_parts.append("=== Alertas HIGH sin confirmar ===\n" + "\n".join(alert_lines))

    system_prompt = (
        "Eres el agente de análisis de opciones de FinView. "
        "Respondes preguntas sobre la cartera de opciones del usuario basándote en los datos "
        "de mercado proporcionados. Eres conciso, preciso y usas terminología financiera correcta. "
        "Si no tienes datos suficientes para responder, dilo claramente. "
        "Responde siempre en el mismo idioma que la pregunta del usuario.\n\n"
        + "\n\n".join(ctx_parts)
    )

    # ── Build messages ─────────────────────────────────────────────
    messages = [
        {"role": m.role, "content": m.content}
        for m in body.history
        if m.role in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": body.question.strip()})

    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    answer = response.content[0].text if response.content else "Sin respuesta."
    return AskOut(answer=answer)
