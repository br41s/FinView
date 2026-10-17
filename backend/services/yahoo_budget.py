"""Wall-clock budget for the loops that call Yahoo Finance.

yfinance bounds every individual HTTP request — curl_cffi maps a scalar timeout
onto ``CURLOPT_TIMEOUT`` and ``YfConfig.network.retries`` is 0 — so no single
call runs forever. What it does not bound is the loop around it, and the bound
it applies is not the one you ask for: ``YfData._make_request`` fetches the
cookie/crumb with a hardcoded 30s default before every request, so
``yf.download(..., timeout=3)`` still takes 30s against an endpoint that accepts
the connection and never answers (measured), and ``yf.Ticker(...).info`` exposes
no timeout argument at all. Passing a timeout at the call site is a placebo.

That leaves the caller's loop as the only place to stand. One stalled lookup
costs ~30s and the supervisor does one per unresolved ISIN, so a portfolio with
~90 of them is a 45-minute import — which is what a hung pytest run looked like,
holding two ESTABLISHED sockets to query2.finance.yahoo.com.

A budget cannot interrupt a request already in flight, so an operation may
overshoot by one call. It stops the multiplication, which is the part that turns
a slow Yahoo into a stalled user import or a cron cycle that never finishes.
"""

import logging
import threading
import time

import yfinance as yf

logger = logging.getLogger(__name__)

# yf.download() has internal shared state that is not thread-safe: two concurrent
# calls for different tickers can hand one ticker's frame to the other and the
# wrong price is then persisted. The lock used to live in zonas_clave_analyzer
# only, while /charts/price-history (a sync route, so one thread per request)
# and the portfolio price refresh downloaded unguarded. Serializing costs
# nothing measurable — yfinance's HTTP round-trip dominates — and one lock in
# one place is the only way to make the guarantee hold for every caller.
_DOWNLOAD_LOCK = threading.Lock()


def download(*args, **kwargs):
    """``yf.download`` behind the process-wide lock. Every caller goes through here."""
    with _DOWNLOAD_LOCK:
        return yf.download(*args, **kwargs)

# One broker import. Two stalled lookups and the rest degrade to "unresolved",
# which is the outcome a failed lookup already produces. A healthy lookup takes
# ~1.5s, so this is dozens of ISINs before the budget ever bites.
IMPORT_SECONDS = 60.0

# One portfolio valuation. Tightest of the three because a user is waiting on the
# response. It is affordable because the price cache is per ISIN per day: in steady
# state nothing is fetched at all, and the cost lands on the first view of the day.
# Cloud Run allows the request 1800s (cloudbuild.yaml --timeout=1800), so without a
# budget a stalled Yahoo hangs the page for half an hour and is then killed mid-work.
PORTFOLIO_SECONDS = 30.0

# ISINs nothing resolves, looked up during a portfolio valuation. Its own allowance,
# spent before the price download, so a slow lookup cannot eat the 30s that prices
# every position that already has a ticker. ~1.5s a healthy lookup: about ten a day;
# whatever it does not reach is looked up on the next day's first valuation.
TICKER_LOOKUP_SECONDS = 15.0

# One geo cron cycle. Longer because no user is waiting on it, but still bounded:
# the Cloud Run revision runs --max-instances=1 with --cpu-throttling and the
# work has to finish inside the HTTP request.
GEO_CYCLE_SECONDS = 120.0


class Budget:
    """Wall-clock allowance shared by every Yahoo call in one operation."""

    def __init__(self, seconds: float, label: str) -> None:
        self._seconds = seconds
        self._label = label
        self._deadline = time.monotonic() + seconds
        self._reported = False

    def spent(self) -> bool:
        """True once the allowance is gone; logs the first time it says so."""
        if time.monotonic() < self._deadline:
            return False
        if not self._reported:
            self._reported = True
            logger.warning(
                "Yahoo budget of %.0fs spent on %s — skipping the remaining lookups",
                self._seconds,
                self._label,
            )
        return True
