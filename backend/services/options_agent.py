"""Options monitor agent — background worker that runs periodic analysis cycles.

Flow per cycle: Observe → Calculate Greeks → Analyze → Store → Notify → (optional) Claude AI.
Runs as an APScheduler job inside the FastAPI process.
"""

import json
import logging
import time
from datetime import datetime

import httpx
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
from backend.services.backtest_service import evaluate_pending, record_signal
from backend.services.fred_rates import risk_free_rate_for_ticker
from backend.services.greeks_calculator import enrich_options_with_greeks
from backend.services.macro_context import macro_prompt_block
from backend.services.notification_service import notify_alerts, notify_spike_telegram
from backend.services.options_analyzer import analyze_ticker
from backend.services.options_scraper import fetch_options
from backend.services.premium_spike import detect_spikes

logger = logging.getLogger(__name__)

# In-memory cycle counter per user (resets on restart — DB log is authoritative)
_cycle_counts: dict[int, int] = {}

# Sentiment priority for aggregation across tickers
_SENTIMENT_RANK = {"BEARISH 🐻": 2, "BULLISH 🐂": 1, "NEUTRAL 😐": 0}


def _aggregate_sentiment(sentiments: list[str]) -> str:
    """Return the most extreme sentiment from a list."""
    if not sentiments:
        return "NEUTRAL 😐"
    return max(sentiments, key=lambda s: _SENTIMENT_RANK.get(s, 0))


def run_cycle(user_id: int) -> dict:
    """Execute one full monitoring cycle for a user.

    Returns a summary dict with cycle results.
    """
    start = time.time()
    db: Session = SessionLocal()
    try:
        # 1. Get user's enabled watchlist
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
        all_sentiments: list[str] = []
        snapshots_saved = 0

        for ticker in tickers:
            # Phase 1: Observe
            options_data = fetch_options(ticker)
            if not options_data:
                logger.warning("No data for %s", ticker)
                continue

            # Phase 2: Greeks (risk-free rate resolved per ticker currency,
            # FRED-backed with a per-currency constant fallback)
            r = risk_free_rate_for_ticker(ticker)
            options_data = enrich_options_with_greeks(options_data, r=r)

            # Phase 3: Analyze
            analysis = analyze_ticker(options_data)
            summary = analysis["summary"]
            alerts = analysis["alerts"]
            unusual = analysis["unusual_activity"]

            all_alerts.extend(alerts)
            all_unusual.extend(unusual)
            all_sentiments.append(summary["market_sentiment"])

            # Premium spike detection (in-memory EMA baseline, no DB needed)
            spike_alerts = detect_spikes(user_id, ticker, options_data)
            if spike_alerts:
                all_alerts.extend(spike_alerts)
                logger.info("%d premium spike(s) detected for %s", len(spike_alerts), ticker)

            # Phase 4: Store snapshot
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
                    "calls": options_data.get("calls", [])[:20],
                    "puts": options_data.get("puts", [])[:20],
                }),
            )
            db.add(snapshot)
            snapshots_saved += 1

            # Record backtest signals for HIGH/MEDIUM alerts
            for alert in alerts:
                db.add(OptionsAlert(
                    user_id=user_id,
                    ticker=alert["ticker"],
                    alert_type=alert["type"],
                    message=alert["message"],
                    severity=alert["severity"],
                ))
                if alert.get("severity") in ("HIGH", "MEDIUM"):
                    record_signal(
                        db,
                        user_id=user_id,
                        ticker=alert["ticker"],
                        alert_type=alert["type"],
                        message=alert["message"],
                        current_price=float(summary["current_price"]),
                    )

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

        # Evaluate pending backtest signals from previous cycles
        try:
            evaluate_pending(db, user_id)
        except Exception:
            logger.exception("Backtest evaluation failed — non-fatal")

        # Phase 5: Optional AI analysis via OpenRouter
        claude_analysis = None
        ai_error: str | None = None
        if not settings.openrouter_api_key:
            logger.warning("FINVIEW_OPENROUTER_API_KEY not set — skipping AI analysis")
            ai_error = "API key not configured (set FINVIEW_OPENROUTER_API_KEY)"
        elif not all_alerts:
            logger.info("No alerts this cycle — skipping AI analysis")
        else:
            claude_analysis, ai_error = _run_claude_analysis(tickers, all_alerts, all_unusual)

        elapsed = time.time() - start
        overall_sentiment = _aggregate_sentiment(all_sentiments)

        log_entry = OptionsAgentLog(
            user_id=user_id,
            cycle_number=cycle_num,
            tickers_analyzed=len(tickers),
            alerts_generated=len(all_alerts),
            unusual_activities=len(all_unusual),
            market_sentiment=overall_sentiment,
            claude_analysis=claude_analysis[:5000] if claude_analysis else None,
            execution_time_seconds=round(elapsed, 2),
        )
        db.add(log_entry)
        db.commit()

        # Phase 6: Notify
        spike_alerts = [a for a in all_alerts if a.get("type") == "PREMIUM_SPIKE"]
        if all_alerts:
            try:
                notify_alerts(all_alerts)
            except Exception:
                logger.exception("Notification failed")
        if spike_alerts:
            try:
                notify_spike_telegram(spike_alerts)
            except Exception:
                logger.exception("Telegram spike notification failed")

        return {
            "status": "ok",
            "cycle": cycle_num,
            "tickers_analyzed": len(tickers),
            "snapshots_saved": snapshots_saved,
            "alerts": len(all_alerts),
            "unusual": len(all_unusual),
            "market_sentiment": overall_sentiment,
            "execution_time": round(elapsed, 2),
            "claude_analysis": claude_analysis,
            "ai_error": ai_error,
        }
    except Exception:
        db.rollback()
        logger.exception("Cycle failed for user %d", user_id)
        return {"status": "error"}
    finally:
        db.close()


_CLAUDE_SYSTEM = """\
Eres VolatilityEdge, un analista cuantitativo senior especializado en opciones financieras. \
Combinas análisis de Greeks, detección de flujo institucional (Smart Money) y lectura de IV/HV \
para identificar oportunidades accionables en el mercado de derivados.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español.
- Usa el formato de secciones exactamente como se indica (## 1. ... ## 7. ...).
- Máximo 750 palabras en total.
- Sé concreto: usa los datos proporcionados, no inventes cifras.
- La sección ## 6. Contexto MEFF solo aparece si hay tickers terminados en .MC.
- NUNCA des recomendaciones de compra/venta directas. Usa lenguaje analítico: \
  "sugiere", "apunta a", "podría indicar", "merece seguimiento".
- Termina SIEMPRE con ## 7. Gestión de Riesgo.
"""

_CLAUDE_USER_TEMPLATE = """\
=== CICLO DE ANÁLISIS DE OPCIONES ===
Fecha/Hora: {timestamp}
Watchlist: {tickers}
Total alertas: {n_alerts} | Severidad HIGH: {n_high} | Actividad inusual: {n_unusual}

=== ALERTAS (ordenadas por severidad) ===
{alerts_json}

=== ACTIVIDAD INUSUAL ===
{unusual_json}

=== CONTEXTO MACRO (FRED) ===
{macro_block}

---
Genera el informe estructurado con EXACTAMENTE estas 7 secciones:

## 1. Resumen Ejecutivo
[Sentimiento global del ciclo: alcista / bajista / neutral / mixto. \
Una frase por cada mercado con actividad relevante. Considera el régimen macro \
como telón de fondo (no cambies las señales, solo contextualízalas).]

## 2. Smart Money
[Flujos institucionales detectados. Volumen/OI fuera de lo normal. \
¿Compra de protección o apuesta direccional? Mínimo 2 observaciones concretas.]

## 3. Señales Greeks
[IV implícita vs HV histórica: ¿cara o barata? Skew put/call notable. \
Delta y Gamma de posiciones con mayor actividad. Theta decay relevant si hay posiciones cortas.]

## 4. Top Picks
[Máximo 3 tickers. Para cada uno: nombre, tesis en 1-2 frases, nivel de riesgo (ALTO/MEDIO/BAJO).]

## 5. Alertas Clave
[Lista las alertas HIGH primero, luego MEDIUM. Para cada una: ticker — tipo — razonamiento breve.]

## 6. Contexto MEFF
[Solo si hay tickers .MC. Diferenciales bid/ask, liquidez, ciclos de vencimiento MEFF vs CBOE.]

## 7. Gestión de Riesgo
[Stop-loss conceptual por tipo de estrategia. Tamaño de posición sugerido según volatilidad. \
Horizonte temporal óptimo según los vencimientos detectados.]
"""


def _run_claude_analysis(
    tickers: list[str], alerts: list[dict], unusual: list[dict]
) -> tuple[str | None, str | None]:
    """Run AI analysis via OpenRouter. Returns (text, error_message)."""
    response = None
    try:
        n_high = sum(1 for a in alerts if a.get("severity") == "HIGH")
        has_meff = any(t.endswith(".MC") for t in tickers)

        sorted_alerts = sorted(alerts, key=lambda a: (0 if a.get("severity") == "HIGH" else 1))
        alerts_payload = sorted_alerts[:20]
        unusual_payload = unusual[:10]

        user_content = _CLAUDE_USER_TEMPLATE.format(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            tickers=", ".join(tickers),
            n_alerts=len(alerts),
            n_high=n_high,
            n_unusual=len(unusual),
            alerts_json=json.dumps(alerts_payload, indent=2, ensure_ascii=False),
            unusual_json=json.dumps(unusual_payload, indent=2, ensure_ascii=False),
            macro_block=macro_prompt_block(),
        )

        if not has_meff:
            user_content = user_content.replace(
                "\n## 6. Contexto MEFF\n"
                "[Solo si hay tickers .MC. Diferenciales bid/ask, liquidez, ciclos de vencimiento MEFF vs CBOE.]\n",
                "\n## 6. Contexto MEFF\n[No hay tickers MEFF en este ciclo — sección omitida.]\n",
            )

        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "max_tokens": 1500,
                "messages": [
                    {"role": "system", "content": _CLAUDE_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return text, None
    except Exception as exc:
        body = response.text[:500] if response is not None else "no response"
        error_msg = f"{type(exc).__name__}: {exc} | response: {body}"
        logger.error("OpenRouter analysis failed — %s", error_msg)
        return None, error_msg
