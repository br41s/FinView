"""Options monitor API — watchlist, snapshots, alerts, agent control."""

import json
import logging
import threading
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.api.auth import CronKey, CurrentUser
from backend.api.schemas import (
    AgentCycleResult,
    AgentStatusOut,
    AskIn,
    AskOut,
    BacktestSignalOut,
    BacktestStatsOut,
    LastAnalysisOut,
    OptionsAlertOut,
    OptionsSnapshotOut,
    UnusualActivityOut,
    WatchlistItemIn,
    WatchlistItemOut,
)
from backend.config import settings
from backend.database import DbSession
from backend.services import options_scheduler
from backend.services.llm_envelope import chat
from backend.models import (
    BacktestSignal,
    FollowedInstrument,
    OptionsAgentLog,
    OptionsAlert,
    OptionsHiddenPortfolioTicker,
    OptionsSnapshot,
    UnusualActivity,
    User,
)
from backend.services import watchlist_service
from backend.services.notification_service import send_telegram
from backend.services.options_agent import run_cycle
from backend.services.options_scraper import fetch_expirations, fetch_options, fetch_options_for_expiry

# ── Availability cache ───────────────────────────────────────────────
# ticker → (has_options, timestamp); 24-hour TTL
_availability_cache: dict[str, tuple[bool, float]] = {}
_AVAIL_TTL = 86_400  # seconds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/options", tags=["options"])

_404 = {404: {"description": "Not found"}}
_now = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── Watchlist CRUD ───────────────────────────────────────────────────


def _to_watchlist_out(item: FollowedInstrument) -> WatchlistItemOut:
    # Legacy response shape: `enabled` means "the agent scans it".
    return WatchlistItemOut(
        id=item.id,
        ticker=item.ticker,
        name=item.name,
        enabled=not item.options_paused,
        created_at=item.created_at,
    )


def _get_options_item(db, user_id: int, item_id: int) -> FollowedInstrument | None:
    return (
        db.query(FollowedInstrument)
        .filter(
            FollowedInstrument.id == item_id,
            FollowedInstrument.user_id == user_id,
            FollowedInstrument.options_enabled.is_(True),
        )
        .first()
    )


@router.get("/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(db: DbSession, user: CurrentUser):
    items = (
        db.query(FollowedInstrument)
        .filter(
            FollowedInstrument.user_id == user.id,
            FollowedInstrument.options_enabled.is_(True),
        )
        .order_by(FollowedInstrument.created_at, FollowedInstrument.id)
        .all()
    )
    return [_to_watchlist_out(i) for i in items]


@router.post(
    "/watchlist",
    response_model=WatchlistItemOut,
    status_code=201,
    responses={409: {"description": "Ticker already in watchlist"}},
)
def add_watchlist_item(body: WatchlistItemIn, db: DbSession, user: CurrentUser):
    existing = watchlist_service.get_followed(db, user.id, body.ticker)
    if existing is not None and existing.options_enabled:
        raise HTTPException(status_code=409, detail="El ticker ya está en la watchlist")

    item = watchlist_service.enable_options(db, user.id, body.ticker, body.name)
    try:
        db.commit()
    except IntegrityError:
        # Lost a concurrent insert race on (user, ticker) — e.g. the portfolio
        # auto-sync and a manual add firing together. Same outcome as the
        # pre-check: it's already followed.
        db.rollback()
        raise HTTPException(status_code=409, detail="El ticker ya está en la watchlist")
    db.refresh(item)
    return _to_watchlist_out(item)


@router.patch("/watchlist/{item_id}", responses=_404)
def toggle_watchlist_item(item_id: int, db: DbSession, user: CurrentUser):
    item = _get_options_item(db, user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")
    item.options_paused = not item.options_paused
    db.commit()
    return {"id": item.id, "enabled": not item.options_paused}


@router.delete("/watchlist/{item_id}", status_code=204, responses=_404)
def remove_watchlist_item(item_id: int, db: DbSession, user: CurrentUser):
    item = _get_options_item(db, user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")
    ticker = item.ticker
    watchlist_service.disable_options(db, item)
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


@router.get("/expirations/{ticker}", responses=_404)
def get_ticker_expirations(ticker: str, user: CurrentUser):
    """Return available expiration dates for a ticker (no chain data fetched for Yahoo)."""
    expirations = fetch_expirations(ticker.upper())
    if not expirations:
        raise HTTPException(status_code=404, detail="No hay vencimientos para este ticker")
    return {"ticker": ticker.upper(), "expirations": expirations}


@router.get("/chain/{ticker}", responses=_404)
def get_ticker_chain(ticker: str, user: CurrentUser, expiration: str | None = None):
    """Fetch live options chain for a ticker.

    If *expiration* (YYYY-MM-DD) is given, only that single date is fetched.
    Otherwise returns the first MAX_EXPIRATIONS dates (used by the agent cycle).
    """
    if expiration:
        data = fetch_options_for_expiry(ticker.upper(), expiration)
    else:
        data = fetch_options(ticker.upper())
    if not data:
        raise HTTPException(status_code=404, detail="No hay datos de opciones para este ticker")
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
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")
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
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
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
            _EUREX_RDF_CACHE, _EUREX_SUFFIXES, _ISIN_RE, _MEFF_SLUGS,
        )

        # ISINs — we can't cheaply determine options availability across all markets
        # (Spanish ISINs → MEFF, German → Eurex, UK → LSE/Eurex, etc.).
        # Always include them; users can manually hide positions with no data.
        if _ISIN_RE.match(ticker):
            return ticker, True

        # Spanish .MC tickers (e.g. TEF.MC) — options live on MEFF, not Yahoo.
        # Yahoo returns no options for them, so check the MEFF slug catalog.
        if ticker.endswith(".MC"):
            return ticker, ticker[:-3] in _MEFF_SLUGS

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

_cycles_in_progress: set[int] = set()
_cycle_lock = threading.Lock()


@router.post("/agent/run", response_model=AgentCycleResult)
def trigger_cycle(user: CurrentUser):
    """Manually trigger one monitoring cycle.

    Cloud Run finishes the cycle inside the request so request-based billing
    cannot freeze it after a response. Local runtimes retain the background
    thread and return ``started`` immediately.
    """
    # FastAPI runs sync def endpoints in a thread pool, so two concurrent
    # requests for the same user could both pass the membership check before
    # either adds to the set (TOCTOU race) without this lock.
    with _cycle_lock:
        if user.id in _cycles_in_progress:
            return AgentCycleResult(status="already_running")
        _cycles_in_progress.add(user.id)

    if settings.request_scoped_runtime:
        try:
            result = run_cycle(user.id)
        finally:
            with _cycle_lock:
                _cycles_in_progress.discard(user.id)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="El ciclo de opciones ha fallado")
        return AgentCycleResult.model_validate(result)

    def _run_in_background(user_id: int) -> None:
        try:
            run_cycle(user_id)
        except Exception:
            # run_cycle already catches and logs its own errors internally;
            # this is only a safety net so the in-progress flag can never get
            # stuck if that ever stops being true.
            pass
        finally:
            with _cycle_lock:
                _cycles_in_progress.discard(user_id)

    threading.Thread(target=_run_in_background, args=(user.id,), daemon=True).start()
    return AgentCycleResult(status="started")


@router.post("/agent/cron", include_in_schema=False, dependencies=[CronKey])
def cron_run(db: DbSession):
    """External-cron entry (Cloud Scheduler / any cron): one cycle per user.

    Runs synchronously so the instance stays alive for the cycle. Auth is the
    shared cron secret — see `require_cron_key`.

    Mirrors /api/geo/cron, but honours the same _cycles_in_progress guard as the
    manual /agent/run: a cron tick landing on top of a manual run would other-
    wise double-fetch every chain and write duplicate snapshots.
    """
    user_ids = [uid for (uid,) in db.query(User.id).filter(User.is_active.is_(True)).all()]
    ok = skipped = 0
    for uid in user_ids:
        with _cycle_lock:
            if uid in _cycles_in_progress:
                skipped += 1
                continue
            _cycles_in_progress.add(uid)
        try:
            # run_cycle swallows its own errors and returns {"status": "error"};
            # it never raises and never returns None.
            if run_cycle(uid).get("status") == "ok":
                ok += 1
        finally:
            with _cycle_lock:
                _cycles_in_progress.discard(uid)

    return {"status": "done", "users": len(user_ids), "cycles_ok": ok, "skipped": skipped}


@router.post("/agent/analyze-ticker", responses=_404)
def analyze_ticker_on_demand(body: WatchlistItemIn, user: CurrentUser):
    """On-demand single-ticker AI options analysis for the instrument drawer.

    Runs regardless of alerts (user explicitly requested it). AI failure still
    returns the rule-based summary/alerts; only missing options data is a 404.
    """
    from backend.services.options_agent import analyze_single_ticker

    result = analyze_single_ticker(body.ticker)
    if result.get("status") == "no_data":
        raise HTTPException(status_code=404, detail="No hay datos de opciones para este ticker")
    return result


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
        running=options_scheduler.is_running(user.id),
        external_scheduler=settings.request_scoped_runtime,
        interval_minutes=settings.options_monitor_interval_minutes,
        last_cycle=last_log.timestamp if last_log else None,
        total_cycles=total or 0,
    )


@router.get("/agent/last-analysis", response_model=LastAnalysisOut)
def agent_last_analysis(db: DbSession, user: CurrentUser):
    """Return metadata from the most recent cycle + claude_analysis from the most recent cycle that has one."""
    base_q = db.query(OptionsAgentLog).filter(OptionsAgentLog.user_id == user.id)

    from backend.services.macro_context import macro_context

    last_log = base_q.order_by(OptionsAgentLog.timestamp.desc()).first()
    if not last_log:
        return LastAnalysisOut(macro=macro_context())

    analysis_log = (
        base_q
        .filter(OptionsAgentLog.claude_analysis.isnot(None))
        .order_by(OptionsAgentLog.timestamp.desc())
        .first()
    )
    return LastAnalysisOut(
        timestamp=last_log.timestamp,
        cycle=last_log.cycle_number,
        tickers_analyzed=last_log.tickers_analyzed,
        alerts=last_log.alerts_generated,
        unusual=last_log.unusual_activities,
        market_sentiment=last_log.market_sentiment,
        claude_analysis=analysis_log.claude_analysis if analysis_log else None,
        ai_configured=bool(settings.openrouter_api_key),
        macro=macro_context(),
    )


@router.post("/agent/start")
def start_scheduler(user: CurrentUser):
    """Start the APScheduler background job for this user."""
    if settings.request_scoped_runtime:
        raise HTTPException(
            status_code=409,
            detail="In-process schedulers are disabled on request-scoped runtimes",
        )
    options_scheduler.start_user_schedule(user.id)
    return {"status": "started", "interval_minutes": settings.options_monitor_interval_minutes}


@router.post("/agent/stop")
def stop_scheduler(user: CurrentUser):
    """Stop the APScheduler background job."""
    options_scheduler.stop_user_schedule(user.id)
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


@router.get("/backtest/calibration")
def backtest_calibration(db: DbSession, user: CurrentUser, days: int = 30):
    """Read-only calibration digest over a recent window (default 30 days).

    Surfaces aligned-vs-counter accuracy by signal type, dedup health (rows per
    ticker-day), and evaluator freshness — so data-quality regressions are
    visible in-app instead of needing a hand-written Neon query.
    """
    from backend.services.backtest_service import get_calibration

    days = max(1, min(days, 365))
    return get_calibration(db, user.id, days=days)


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
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FINVIEW_OPENROUTER_API_KEY not configured.",
        )

    if not body.question.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La pregunta está vacía.")

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

    answer, error = chat(
        [{"role": "system", "content": system_prompt}] + messages,
        context="options ask",
        max_tokens=1024,
    )
    if answer is None:
        logger.warning("options ask failed — %s", error)
        raise HTTPException(status_code=502, detail="El asistente no ha podido responder. Inténtalo de nuevo.")
    return AskOut(answer=answer)
