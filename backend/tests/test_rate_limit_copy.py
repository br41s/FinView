"""A spent rate limit answers like every other user-reachable error: 429 with a
Spanish ``detail``.

slowapi's default handler returned ``{"error": "Rate limit exceeded: 3 per 1
minute"}``. The frontend reads ``detail`` and otherwise shows the raw body, so a
user who double-clicked "Crear cuenta" saw that JSON, in English, in the form.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.services.rate_limit import limiter, rate_limited


def _client() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limited)

    @app.get("/once")
    @limiter.limit("1/minute")
    def once(request: Request):
        return {"ok": True}

    limiter.reset()
    return TestClient(app)


def test_a_spent_limit_is_a_spanish_detail():
    client = _client()
    assert client.get("/once").status_code == 200

    r = client.get("/once")

    assert r.status_code == 429
    assert r.json() == {"detail": "Demasiadas solicitudes. Inténtalo de nuevo en unos minutos."}
