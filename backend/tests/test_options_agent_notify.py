"""run_cycle → notify_alerts wiring: which tickers can end an alert episode.

An episode ends on a cycle that analyzed its ticker without the alert. The
analyzer names an alert by the resolved symbol (``options_data["ticker"]``),
spikes by the watchlist entry, and the two differ for a row stored by ISIN — so
the cycle must report both, and a ticker it got no data for must report neither.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import Base, FollowedInstrument, OptionsAlertNotification
from backend.services import notification_service as ns
from backend.services import options_agent

USER = 1
ISIN = "ES0113900J37"
SYMBOL = "SAN.MC"
SUMMARY = {
    "current_price": 4.0, "call_volume": 10, "put_volume": 30,
    "call_open_interest": 0, "put_open_interest": 0,
    "put_call_ratio_volume": 3.0, "put_call_ratio_oi": 0.0,
    "avg_call_iv": 0.2, "avg_put_iv": 0.2, "iv_skew": 0.0,
    "market_sentiment": "NEUTRAL 😐",
}
PC = {"ticker": SYMBOL, "type": "HIGH_PUT_CALL_RATIO", "severity": "HIGH", "message": "P/C 3.0"}


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(FollowedInstrument(user_id=USER, ticker=ISIN, options_enabled=True, options_paused=False))
        db.commit()
    return factory


def _cycle(session_factory, alerts, data=True):
    chain = {"ticker": SYMBOL, "calls": [], "puts": []} if data else None
    with (
        patch.object(options_agent, "SessionLocal", session_factory),
        patch.object(options_agent, "fetch_options", return_value=chain),
        patch.object(options_agent, "risk_free_rate_for_ticker", return_value=0.03),
        patch.object(options_agent, "enrich_options_with_greeks", side_effect=lambda d, r: d),
        patch.object(options_agent, "analyze_ticker",
                     return_value={"summary": SUMMARY, "alerts": [dict(a) for a in alerts],
                                   "unusual_activity": []}),
        patch.object(options_agent, "macro_context", return_value=None),
        patch.object(options_agent, "evaluate_pending"),
        patch.object(options_agent, "record_signal"),
        patch.object(options_agent.settings, "openrouter_api_key", ""),
        patch.object(ns, "send_ntfy"), patch.object(ns, "send_email"),
        patch.object(ns, "send_telegram") as tg,
    ):
        result = options_agent.run_cycle(USER)
    assert result["status"] in ("ok", "no_watchlist"), result
    return tg.call_count


def _open_episodes(session_factory):
    with session_factory() as db:
        return [r.alert_key for r in db.query(OptionsAlertNotification)]


def test_an_isin_row_clears_its_alert_under_the_resolved_symbol(session_factory):
    assert _cycle(session_factory, [PC]) == 1
    assert _cycle(session_factory, [PC]) == 0  # same episode
    _cycle(session_factory, [])  # SAN.MC analyzed, no alert: cleared
    assert _open_episodes(session_factory) == []
    assert _cycle(session_factory, [PC]) == 1  # back: sent again


def test_a_cycle_with_no_data_leaves_the_episode_open(session_factory):
    _cycle(session_factory, [PC])
    _cycle(session_factory, [], data=False)
    assert _open_episodes(session_factory) == [f"{SYMBOL}|HIGH_PUT_CALL_RATIO"]
    assert _cycle(session_factory, [PC]) == 0
