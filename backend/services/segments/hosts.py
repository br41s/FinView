"""The connections to the annual-report hosts, for the readers of one run.

filings.xbrl.org answers 429 to the 11th request inside about 30 seconds from one
address. Measured on 2026-11-06: ten requests succeed at any pace from 0.15 s to 3 s
apart and the eleventh is refused (the limit is on the client, not on the URL: ten
different LEIs trip it too); a gap of 3.5 s passed 22 requests in a row. The refusal
carries no `Retry-After` and no rate-limit header, lasts about 25 s, and the page
says only "Too Many Requests". Before this module, each reader ran at one ISIN every
0.15 s, got ten answers a night and logged the rest as skipped (the segment reader's
backlog went 51, 42, 29, 20, 10 over five nights, the AI reader starting second on an
address the first had just exhausted).

So a `Client` does three things for the run that owns it:

- paces `filings.xbrl.org` (`PACE`), across clients: the limit is on the address, and a
  second client in the same process (the AI reader's, a page load) must not start a
  fresh burst;
- closes a host for the rest of the run the first time it answers 429. The other hosts
  carry on, so SEC ISINs are read while the ESEF ones wait for the next night;
- remembers the ISIN → LEI and LEI → filing lookups (`memo`), so the second reader
  does not pay again for what the first just asked.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

logger = logging.getLogger(__name__)


class SourceUnavailable(Exception):
    """A request failed. Not a fact about the issuer, so it is never cached."""


# Seconds between two requests to a host. filings.xbrl.org's limit is ten requests in a
# window between 27 and 31.5 s, which makes 3.15 s the least that never trips it; 3.5 s
# is the gap the 22-request run used. GLEIF and the SEC are not limited at this pace.
PACE = {"filings.xbrl.org": 3.5}

_lock = threading.Lock()
_next_slot: dict[str, float] = {}
# Module attributes so a test can run on a clock it controls.
_now, _sleep = time.monotonic, time.sleep


def _wait_turn(host: str) -> None:
    """Block until this request's slot at `host`. Slots are handed out under a lock, so
    concurrent requests (two page loads, the cron) queue instead of bursting."""
    interval = PACE.get(host)
    if interval is None:
        return
    with _lock:
        now = _now()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + interval
    if slot > now:
        _sleep(slot - now)


class Client(httpx.Client):
    """An `httpx.Client` for one run: paced, closed per host by a 429, with a memo."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.closed: set[str] = set()  # hosts that answered 429 during this run
        self.memo: dict = {}  # lookups the readers of this run share (`esef`)

    def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        host = request.url.host
        if host in self.closed:
            raise SourceUnavailable(f"{host} answered 429 earlier in this run")
        _wait_turn(host)
        response = super().send(request, **kwargs)
        if response.status_code == 429:
            self.closed.add(host)
            logger.warning("[hosts] %s answered 429: no more requests to it in this run", host)
        return response
