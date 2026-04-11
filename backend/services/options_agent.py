"""Options monitor agent — background worker that runs periodic analysis cycles.

Ported from OptionsAI/options_monitor_agent/agent.py.
Runs as an APScheduler job inside the FastAPI process.
"""

import json
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models import (
    OptionsAlert,
    OptionsAgentLog,
    OptionsSnapshot,
    UnusualActivity,
    WatchlistItem,
)
from backend.services.greeks_calculator import enrich_options_with_greeks
from backend.services.notification_service import notify_alerts
from backend.services.options_analyzer import analyze_ticker
from backend.services.options_scraper import fetch_options

logger = logging.getLogger(__name__)

# In-memory state per user (user_id -> cycle count)
_cycle_counts: dict[int, int] = {}


def run_cycle(user_id: int) -> dict:
    """Execute one full monitoring cycle for a user.

    Flow: Observe → Calculate Greeks → Analyze → Store → Notify
    Returns summary dict.
    """
    start = time.time()
    db: Session = SessionLocal()
    try:
        # 1. Get user's watchlist
        items = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.user_id == user_id, WatchlistItem.enabled.is_(True))
            .all()
        )
        tickers = [item.ticker for item in items]
        if not tickers:
            return {"status": "no_watchlist", "tickers": []}

        cycle_num = _cycle_counts.get(user_id, 0) + 1
        _cycle_counts[user_id] = cycle_num

        all_alerts: list[dict] = []
        all_unusual: list[dict] = []
        snapshots_saved = 0

        for ticker in tickers:
            # PHASE 1: Observe — fetch options data
            options_data = fetch_options(ticker)
            if not options_data:
                logger.warning("No data for %s", ticker)
                continue

            # PHASE 2: Calculate Greeks
            options_data = enrich_options_with_greeks(options_data)

            # PHASE 3: Analyze
            analysis = analyze_ticker(options_data)
            summary = analysis["summary"]
            alerts = analysis["alerts"]
            unusual = analysis["unusual_activity"]

            all_alerts.extend(alerts)
            all_unusual.extend(unusual)

            # PHASE 4: Store snapshot
            snapshot = OptionsSnapshot(
                user_id=user_id,
                ticker=ticker,
                current_price=summary["current_price"],
                call_volume=summary["call_volume"],
                put_volume=summary["put_volume"],
                call_open_interest=summary["call_open_interest"],
                put_open_interest=summary["put_open_interest"],
                put_call_ratio_volume=summary["put_call_ratio_volume"],
                put_call_ratio_oi=summary["put_call_ratio_oi"],
                avg_call_iv=summary["avg_call_iv"],
                avg_put_iv=summary["avg_put_iv"],
                historical_volatility=summary.get("historical_volatility"),
                iv_skew=summary["iv_skew"],
                market_sentiment=summary["market_sentiment"],
                chain_data=json.dumps({
                    "calls": options_data.get("calls", [])[:20],  # top 20 per type
                    "puts": options_data.get("puts", [])[:20],
                }),
            )
            db.add(snapshot)
            snapshots_saved += 1

            # Store alerts
            for alert in alerts:
                db.add(OptionsAlert(
                    user_id=user_id,
                    ticker=alert["ticker"],
                    alert_type=alert["type"],
                    message=alert["message"],
                    severity=alert["severity"],
                ))

            # Store unusual activity
            for ua in unusual:
                db.add(UnusualActivity(
                    user_id=user_id,
                    ticker=ua["ticker"],
                    option_type=ua["option_type"],
                    strike=ua["strike"],
                    expiration=ua["expiration"],
                    volume=ua["volume"],
                    open_interest=ua["open_interest"],
                    vol_oi_ratio=ua["vol_oi_ratio"],
                    implied_volatility=ua.get("implied_volatility"),
                    last_price=ua.get("last_price"),
                ))

        elapsed = time.time() - start

        # Claude analysis (optional — only if API key configured)
        claude_analysis = None
        if settings.anthropic_api_key and all_alerts:
            claude_analysis = _run_claude_analysis(tickers, all_alerts, all_unusual)

        # Log cycle
        log_entry = OptionsAgentLog(
            user_id=user_id,
            cycle_number=cycle_num,
            tickers_analyzed=len(tickers),
            alerts_generated=len(all_alerts),
            unusual_activities=len(all_unusual),
            market_sentiment=all_alerts[0]["severity"] if all_alerts else "NEUTRAL",
            claude_analysis=claude_analysis[:5000] if claude_analysis else None,
            execution_time_seconds=round(elapsed, 2),
        )
        db.add(log_entry)
        db.commit()

        # PHASE 5: Notify
        if all_alerts:
            try:
                notify_alerts(all_alerts)
            except Exception:
                logger.exception("Notification failed")

        return {
            "status": "ok",
            "cycle": cycle_num,
            "tickers_analyzed": len(tickers),
            "snapshots_saved": snapshots_saved,
            "alerts": len(all_alerts),
            "unusual": len(all_unusual),
            "execution_time": round(elapsed, 2),
            "claude_analysis": claude_analysis,
        }
    except Exception:
        db.rollback()
        logger.exception("Cycle failed for user %d", user_id)
        return {"status": "error"}
    finally:
        db.close()


def _run_claude_analysis(tickers: list[str], alerts: list[dict], unusual: list[dict]) -> str | None:
    """Optional Claude AI analysis of the current cycle results."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        context = f"""=== OPTIONS ANALYSIS CYCLE ===
Tickers: {', '.join(tickers)}
Timestamp: {datetime.now().isoformat()}

=== ALERTS ({len(alerts)}) ===
{json.dumps(alerts, indent=2)}

=== UNUSUAL ACTIVITY ({len(unusual)}) ===
{json.dumps(unusual, indent=2)}

Analyze this data. Focus on Greeks, IV vs HV, Smart Money, and actionable insights."""

        response = client.messages.create(
            model="claude-haiku-3-5-20241022",
            max_tokens=2048,
            temperature=0.3,
            system=(
                "Eres un experto en análisis de opciones financieras. "
                "Analiza los datos y da un resumen conciso con: "
                "1) Resumen ejecutivo 2) Top picks 3) Greeks insights "
                "4) Alertas 5) Smart money 6) Interpretación. "
                "Usa emojis. NUNCA des consejos de inversión directos."
            ),
            messages=[{"role": "user", "content": context}],
        )
        return response.content[0].text
    except Exception:
        logger.exception("Claude analysis failed")
        return None
