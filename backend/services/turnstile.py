"""Cloudflare Turnstile verification.

Login is gated by a Turnstile challenge to keep credential-stuffing bots out.
Verification is a no-op when ``FINVIEW_TURNSTILE_SECRET`` is unset, so local
dev and placeholder deploys work unchanged.

Fail-closed policy: if the Turnstile widget token is missing/invalid, or the
siteverify call errors out, ``verify_turnstile`` returns ``False`` and the
login is rejected. This favours security over availability — if Cloudflare is
unreachable, logins are blocked rather than waved through. Flip the `except`
branch to ``return True`` if you'd rather fail open during a Cloudflare outage.
"""

from __future__ import annotations

import httpx

from backend.config import settings

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_enabled() -> bool:
    """True when a secret is configured (and verification should run)."""
    return bool(settings.turnstile_secret)


def verify_turnstile(token: str | None, remote_ip: str | None = None) -> bool:
    """Verify a Turnstile token with Cloudflare. Returns True if it passes.

    Skips (returns True) when no secret is configured. Fails closed on a
    missing token or any transport/parse error.
    """
    if not turnstile_enabled():
        return True
    if not token:
        return False

    data = {"secret": settings.turnstile_secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        resp = httpx.post(_VERIFY_URL, data=data, timeout=5.0)
        resp.raise_for_status()
        return bool(resp.json().get("success"))
    except Exception:  # fail closed on any verification error
        return False
