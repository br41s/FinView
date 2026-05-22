"""Rate limiting setup with Cloud-Run-aware client IP extraction.

## IP extraction behind Cloud Run

Cloud Run terminates TLS at Google's Front End (GFE) and forwards to the
container over HTTP. The container's TCP peer is always a Google internal
proxy, so ``request.client.host`` is useless for per-user throttling.

The real client IP is in the ``X-Forwarded-For`` header. Per Google's
behavior, the GFE *appends* the actual TCP-level peer to the right of any
client-supplied value. So ``X-Forwarded-For: spoofed, real_client`` is the
worst case, and the **rightmost** entry is the trustworthy IP that GFE saw.

We use the rightmost entry deliberately:
- Leftmost would be trivially spoofable by adding an X-Forwarded-For header,
  letting an attacker bypass per-IP rate limits.
- Rightmost is what Cloud Run / GFE observed at the TCP layer.

If the header is missing (local dev, direct uvicorn), we fall back to
``request.client.host``.

Limitation: this is in-memory state. Cloud Run scales horizontally, so
limits are per-instance. For the current single-instance deployment this
is acceptable; if traffic grows, swap to a Redis-backed limiter.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Extract the trusted client IP for rate-limiting purposes.

    Uses the rightmost ``X-Forwarded-For`` entry (the value Cloud Run's GFE
    appended from the TCP layer), falling back to the direct peer for local
    development.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        # Rightmost = the IP GFE saw on the wire; cannot be spoofed by the client.
        return xff.rsplit(",", 1)[-1].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
