"""The options sources are asked about tickers, never about an ISIN nothing resolves."""

import logging

import pytest

from backend.services import options_scraper as scraper
from backend.services import ticker_map

# What prod's watchlist held (Cloud Run, 2026-09-25 to 2026-10-05, 159 ERROR
# tracebacks each): two ES06… ISINs, the prefix Spain gives subscription rights,
# and a bond. A portfolio position nothing knows a ticker for is followed by its
# ISIN, and none of these has a ticker to find.
NO_TICKER = ["ES0622060988", "ES0684262944", "DE000A30WFV1"]


@pytest.fixture(autouse=True)
def cold_caches(monkeypatch):
    for name in ("_ISIN_CACHE", "_OPTIONS_CACHE", "_EXPIRY_CACHE", "_EXPIRATIONS_CACHE"):
        monkeypatch.setattr(scraper, name, {})


@pytest.fixture
def asked(monkeypatch) -> list[tuple[str, str]]:
    """Every (source, symbol) the scraper asked about. Yahoo's search knows nothing."""
    asked: list[tuple[str, str]] = []

    class NoQuotes:
        status_code = 200

        @staticmethod
        def json():
            return {"quotes": []}

    def yahoo(symbol, *a, **k):
        asked.append(("yahoo", symbol))
        # What yfinance 1.2 does with an ISIN-shaped string it cannot place: it
        # looks up anything its `is_isin` accepts and raises on an empty answer.
        # _fetch_yahoo catches it, so the list is what the tests read.
        raise ValueError(f"Invalid ISIN number: {symbol}")

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: NoQuotes())
    monkeypatch.setattr(scraper.yf, "Ticker", yahoo)
    monkeypatch.setattr(scraper, "_fetch_meff", lambda t: asked.append(("meff", t)))
    monkeypatch.setattr(scraper, "_fetch_eurex", lambda t: asked.append(("eurex", t)))
    return asked


@pytest.mark.parametrize("isin", NO_TICKER)
def test_an_isin_with_no_ticker_reaches_no_source(asked, caplog, isin):
    with caplog.at_level(logging.INFO):
        assert scraper.fetch_options(isin) is None
        assert scraper.fetch_expirations(isin) == []
        assert scraper.fetch_options_for_expiry(isin, "2026-12-18") is None
    assert asked == []
    # Said once per call, and not as an error: there is nothing to fix in the
    # code when a bond has no options.
    assert caplog.text.count(f"ISIN {isin} did not resolve to a ticker") == 3
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_an_isin_the_curated_map_knows_is_fetched_as_its_ticker(asked, monkeypatch):
    chain = {"ticker": "TEF.MC", "calls": [{"expiration": "2026-12-18"}], "puts": [],
             "calls_count": 1, "puts_count": 0}
    monkeypatch.setattr(scraper, "_fetch_meff", lambda t: asked.append(("meff", t)) or chain)
    assert ticker_map.CURATED["ES0178430E18"] == "TEF.MC"
    assert scraper.fetch_options("ES0178430E18") is chain
    assert scraper.fetch_expirations("ES0178430E18") == ["2026-12-18"]
    assert scraper.fetch_options_for_expiry("ES0178430E18", "2026-12-18")["calls_count"] == 1
    # Asked once, as the ticker: the other two read the chain cached under its key.
    assert asked == [("meff", "TEF.MC")]


def test_an_isin_yahoo_search_resolves_is_fetched_under_that_symbol(asked, monkeypatch):
    class Found:
        status_code = 200

        @staticmethod
        def json():
            return {"quotes": [{"symbol": "AAPL"}]}

    chain = {"ticker": "AAPL", "calls_count": 1, "puts_count": 1}

    def yahoo_chain(ticker, expiration=None):
        asked.append(("yahoo", ticker))
        return chain

    class Listed:
        options = ("2026-12-18",)

    def yahoo_listing(symbol, *a, **k):
        asked.append(("yahoo expirations", symbol))
        return Listed()

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: Found())
    monkeypatch.setattr(scraper, "_fetch_yahoo", yahoo_chain)
    monkeypatch.setattr(scraper.yf, "Ticker", yahoo_listing)
    assert scraper.fetch_options("US0378331005") is chain
    assert scraper.fetch_expirations("US0378331005") == ["2026-12-18"]
    assert scraper.fetch_options_for_expiry("US0378331005", "2026-12-18") is chain
    assert asked == [("yahoo", "AAPL"), ("yahoo expirations", "AAPL"), ("yahoo", "AAPL")]


def test_a_search_that_fails_is_not_remembered_as_no_ticker(asked, monkeypatch):
    """A resolution that could not be asked costs this call, not the next one."""
    def down(*a, **k):
        raise ConnectionError("yahoo is down")

    monkeypatch.setattr(scraper.requests, "get", down)
    assert scraper.fetch_options("US0378331005") is None
    assert asked == [] and scraper._ISIN_CACHE == {}


def test_a_ticker_is_passed_through_without_a_lookup(monkeypatch):
    def no_search(*a, **k):
        raise AssertionError("a plain ticker must not be searched as an ISIN")

    monkeypatch.setattr(scraper.requests, "get", no_search)
    for ticker in ("AAPL", "TEF.MC", "BRK-B", "IWDA.AS"):
        assert scraper._as_ticker(ticker) == ticker

