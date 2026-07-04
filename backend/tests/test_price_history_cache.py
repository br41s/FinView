"""Tests for the /charts/price-history in-memory TTL cache."""

import pandas as pd
import pytest
import yfinance as yf

from backend.api import charts


@pytest.fixture(autouse=True)
def clear_cache():
    charts._PRICE_HISTORY_CACHE.clear()
    yield
    charts._PRICE_HISTORY_CACHE.clear()


def _fake_df():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
    return pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [10.6, 10.9],
            "Low": [9.8, 10.2],
            "Close": [10.4, 10.7],
            "Volume": [1000, 1200],
        },
        index=idx,
    )


def test_second_call_hits_cache(monkeypatch):
    calls = []

    def fake_download(*args, **kwargs):
        calls.append(args)
        return _fake_df()

    monkeypatch.setattr(yf, "download", fake_download)

    first = charts.price_history("AAPL", user=None, period="1y")
    second = charts.price_history("aapl ", user=None, period="1y")  # normalizes to same key

    assert len(calls) == 1
    assert first == second
    assert first[0]["close"] == 10.4


def test_periods_are_cached_separately(monkeypatch):
    calls = []
    monkeypatch.setattr(yf, "download", lambda *a, **k: (calls.append(a), _fake_df())[1])

    charts.price_history("AAPL", user=None, period="1y")
    charts.price_history("AAPL", user=None, period="5y")

    assert len(calls) == 2


def test_empty_result_is_not_cached(monkeypatch):
    calls = []

    def fake_download(*args, **kwargs):
        calls.append(args)
        return pd.DataFrame()

    monkeypatch.setattr(yf, "download", fake_download)

    assert charts.price_history("NOPE", user=None, period="1y") == []
    assert charts.price_history("NOPE", user=None, period="1y") == []

    # Both calls reached yfinance — a transient failure must not be pinned for the TTL.
    assert len(calls) == 2
    assert charts._PRICE_HISTORY_CACHE == {}
