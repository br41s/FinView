"""Geo prices resolve intraday, with a per-symbol fallback to the daily close.

Both ends of every geo measurement come from `fetch_ticker_prices`: the price
stamped on a signal at creation, and the price the auditor scores it against. On
daily closes the +1h and +6h checkpoints compared a close against itself — 0.00%
— and scored every basket 0. The portfolio path keeps its daily closes, because
its cache is one row per ISIN per day paired with that day's ECB rate.
"""

import pandas as pd
import pytest

from backend.services import prices as svc


@pytest.fixture
def calls(monkeypatch):
    """Record every yfinance fetch with the interval it asked for."""
    seen: list[dict] = []
    responses: dict[str, dict[str, float]] = {}

    def fake_fetch(tickers, *, period="5d", interval="1d", budget=None):
        seen.append({"tickers": list(tickers), "period": period, "interval": interval})
        return dict(responses.get(interval, {}))

    monkeypatch.setattr(svc, "_fetch_yahoo_prices", fake_fetch)
    return seen, responses


def test_intraday_is_preferred(calls):
    seen, responses = calls
    responses["5m"] = {"XLE": 91.25, "USO": 74.10}

    assert svc.fetch_ticker_prices(["XLE", "USO"]) == {"XLE": 91.25, "USO": 74.10}
    assert [c["interval"] for c in seen] == ["5m"], "no daily call when intraday covers it"


def test_only_the_symbols_without_intraday_bars_fall_back(calls):
    """A thin listing keeps a price instead of dropping out of the basket."""
    seen, responses = calls
    responses["5m"] = {"XLE": 91.25}
    responses["1d"] = {"ZC=F": 430.0}

    prices = svc.fetch_ticker_prices(["XLE", "ZC=F"])

    assert prices == {"XLE": 91.25, "ZC=F": 430.0}
    assert seen[1]["interval"] == "1d"
    assert seen[1]["tickers"] == ["ZC=F"], "the fallback asks only for what is missing"


def test_a_dead_intraday_feed_still_yields_daily_prices(calls):
    seen, responses = calls
    responses["1d"] = {"XLE": 90.0, "USO": 74.0}

    assert svc.fetch_ticker_prices(["XLE", "USO"]) == {"XLE": 90.0, "USO": 74.0}
    assert [c["interval"] for c in seen] == ["5m", "1d"]


def test_unresolvable_symbols_are_absent_not_zero(calls):
    """Absent means "no price"; a zero would read as a -100% move in the auditor."""
    _, responses = calls
    responses["5m"] = {"XLE": 91.25}

    assert svc.fetch_ticker_prices(["XLE", "NOPE"]) == {"XLE": 91.25}


def test_symbols_are_deduplicated(calls):
    seen, responses = calls
    responses["5m"] = {"XLE": 91.25}

    svc.fetch_ticker_prices(["XLE", "XLE", "XLE"])

    assert seen[0]["tickers"] == ["XLE"]


def test_no_symbols_makes_no_calls(calls):
    seen, _ = calls
    assert svc.fetch_ticker_prices([]) == {}
    assert seen == []


# ── _last_closes: the column shapes yfinance actually returns ────────


def test_last_close_from_a_multiindex_frame():
    frame = pd.DataFrame(
        {
            ("Close", "XLE"): [90.0, 91.5],
            ("Close", "USO"): [74.0, float("nan")],
        }
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)

    # The last USO bar is NaN (no trade in that 5-minute slot) — take the one before.
    assert svc._last_closes(frame, ["XLE", "USO"]) == {"XLE": 91.5, "USO": 74.0}


def test_last_close_from_a_single_ticker_series():
    frame = pd.DataFrame({"Close": [90.0, 91.5]})
    assert svc._last_closes(frame, ["XLE"]) == {"XLE": 91.5}


def test_an_all_nan_column_yields_no_price():
    frame = pd.DataFrame({"Close": [float("nan"), float("nan")]})
    assert svc._last_closes(frame, ["XLE"]) == {}


def test_an_empty_frame_is_not_a_price():
    assert svc._last_closes(pd.DataFrame(), ["XLE"]) == {}
    assert svc._last_closes(None, ["XLE"]) == {}


def test_a_frame_without_a_close_column_is_survivable():
    """yfinance shapes shift between versions; a missing column must not raise."""
    assert svc._last_closes(pd.DataFrame({"Open": [1.0]}), ["XLE"]) == {}
