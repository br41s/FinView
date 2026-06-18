"""Shared HTTP + caching helpers for geo ingest clients.

FinView convention: httpx (async) with a shared timeout, structured logging, and
graceful degradation — a source that fails returns its last good payload (stale
cache) or an empty list, never raising into the pipeline cycle.
"""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "FinView-GeoIntel/1.0 (geopolitical-intelligence)"


class TTLCache:
    """Minimal in-memory single-value TTL cache (per source module).

    Mirrors WorldHawk's per-route ``globalThis.__xCache``. Not persisted; resets
    on restart, which is fine — sources are re-fetched on the next cycle.
    """

    def __init__(self) -> None:
        self._value: Any | None = None
        self._ts: float = 0.0

    def get(self, ttl_seconds: float) -> Any | None:
        if self._value is not None and (time.monotonic() - self._ts) < ttl_seconds:
            return self._value
        return None

    @property
    def stale(self) -> Any | None:
        """Last cached value regardless of age (used as a degradation fallback)."""
        return self._value

    def set(self, value: Any) -> None:
        self._value = value
        self._ts = time.monotonic()


async def fetch_json(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
    auth: tuple[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any | None:
    """Fetch and JSON-decode a URL. Returns the parsed body, or None on any failure."""
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.request(
                method, url, params=params, json=json_body, headers=merged, auth=auth
            )
        if resp.status_code != 200:
            logger.warning("geo ingest %s → HTTP %s", url, resp.status_code)
            return None
        return resp.json()
    except Exception:
        logger.warning("geo ingest request failed: %s", url, exc_info=True)
        return None


async def fetch_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """Fetch a URL and return the raw text body, or None on any failure."""
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=merged)
        if resp.status_code != 200:
            logger.warning("geo ingest %s → HTTP %s", url, resp.status_code)
            return None
        return resp.text
    except Exception:
        logger.warning("geo ingest request failed: %s", url, exc_info=True)
        return None
