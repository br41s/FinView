"""Tests for the client-IP extraction that per-IP rate limiting keys on.

This is the highest-stakes untested function in the codebase. Login and register
are throttled per IP, and the key comes from ``client_ip``. It deliberately
reads the **rightmost** ``X-Forwarded-For`` entry, because Cloud Run's front end
appends the peer it saw at the TCP layer to the right of anything the client
sent. Reading the leftmost entry instead — the more common convention, and an
easy "cleanup" for someone who hasn't read the comment — would let an attacker
rotate a header value per request and bypass the limiter entirely.

The reasoning was written down; nothing checked it. These tests make the choice
executable, so the bypass cannot be reintroduced silently.
"""

import pytest
from starlette.requests import Request

from backend.services.rate_limit import client_ip


def _request(headers: dict[str, str] | None = None, peer: str | None = "203.0.113.7") -> Request:
    """Build a Starlette request with the given headers and TCP peer."""
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/auth/login",
        "raw_path": b"/api/auth/login",
        "query_string": b"",
        "headers": raw_headers,
        "client": (peer, 54321) if peer else None,
        "server": ("finview", 443),
    }
    return Request(scope)


# ── The spoofing case this function exists to prevent ────────────────


def test_a_spoofed_leading_entry_is_ignored():
    """The attack: prepend your own X-Forwarded-For and get a fresh limiter key.

    Cloud Run appends the real peer, so the client-controlled value sits on the
    left. Taking the rightmost entry makes the header useless as a bypass.
    """
    request = _request({"x-forwarded-for": "1.1.1.1, 198.51.100.23"})

    assert client_ip(request) == "198.51.100.23"


def test_every_spoofed_prefix_maps_to_the_same_key():
    """Rotating the spoofed value must not hand out new buckets."""
    real = "198.51.100.23"
    keys = {
        client_ip(_request({"x-forwarded-for": f"{spoof}, {real}"}))
        for spoof in ("1.1.1.1", "2.2.2.2", "9.9.9.9, 8.8.8.8", "not-an-ip")
    }

    assert keys == {real}, "a client-supplied prefix changed the rate-limit key"


def test_a_long_proxy_chain_still_resolves_to_the_last_hop():
    request = _request({"x-forwarded-for": "10.0.0.1, 10.0.0.2, 10.0.0.3, 198.51.100.23"})

    assert client_ip(request) == "198.51.100.23"


# ── Formatting the header can arrive in ──────────────────────────────


def test_a_single_entry_is_used_as_is():
    assert client_ip(_request({"x-forwarded-for": "198.51.100.23"})) == "198.51.100.23"


@pytest.mark.parametrize(
    "header",
    [
        "1.1.1.1,198.51.100.23",
        "1.1.1.1,   198.51.100.23",
        "1.1.1.1, 198.51.100.23   ",
        "  1.1.1.1 ,198.51.100.23 ",
    ],
)
def test_surrounding_whitespace_never_reaches_the_key(header):
    """A stray space would silently create a second bucket for one IP."""
    assert client_ip(_request({"x-forwarded-for": header})) == "198.51.100.23"


def test_ipv6_survives_intact():
    """Colons in IPv6 must not be mistaken for a separator."""
    request = _request({"x-forwarded-for": "1.1.1.1, 2001:db8::8a2e:370:7334"})

    assert client_ip(request) == "2001:db8::8a2e:370:7334"


# ── No header (local dev, direct uvicorn) ────────────────────────────


def test_falls_back_to_the_tcp_peer_without_the_header():
    assert client_ip(_request(peer="203.0.113.7")) == "203.0.113.7"


def test_an_empty_header_falls_back_rather_than_keying_on_blank():
    """An empty value must not collapse every caller into one shared bucket."""
    request = _request({"x-forwarded-for": ""}, peer="203.0.113.7")

    assert client_ip(request) == "203.0.113.7"


def test_a_missing_peer_still_yields_a_key():
    """Starlette allows no client; the limiter must still get a usable string."""
    key = client_ip(_request(peer=None))

    assert isinstance(key, str) and key
