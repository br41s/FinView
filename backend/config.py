import logging
import os
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

INSECURE_DEFAULT_SECRET = "change-me-in-production"  # nosec: sentinel, not a real secret
PRODUCTION_LIKE_ENVS = {"staging", "production", "prod"}
# RFC 7518 §3.2: an HMAC key should be at least the hash output size (32 bytes
# for HS256). PyJWT warns below this.
MIN_SECRET_BYTES = 32

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Deployment environment: "local", "dev", "test", "staging", "production".
    # Production-like environments enforce secret validation at startup.
    env: str = "local"

    # Cloud Run request-based billing throttles CPU after the response. When
    # enabled, API work must finish inside the request instead of relying on
    # daemon threads or in-process schedulers that can be frozen at any time.
    request_scoped_runtime: bool = False

    database_url: str = f"sqlite:///{Path(__file__).parent.parent / 'finview.db'}"
    data_dir: Path = Path(__file__).parent.parent / "data"

    # Auth / JWT
    secret_key: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 90  # 90 days

    # NextAuth shared secret (must match AUTH_SECRET on frontend)
    auth_secret: str = INSECURE_DEFAULT_SECRET

    # Shared secret for external cron callers (Cloud Scheduler → POST /geo/cron).
    # Empty disables the endpoint entirely.
    cron_secret: str = ""

    # Cloudflare Turnstile (bot protection on login). When empty, verification
    # is skipped so local dev / unconfigured deploys keep working. Set
    # FINVIEW_TURNSTILE_SECRET in prod; the frontend uses NEXT_PUBLIC_TURNSTILE_SITE_KEY.
    turnstile_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""  # Stripe Price ID for Pro plan
    stripe_price_unlimited: str = ""  # Stripe Price ID for Unlimited plan
    frontend_url: str = "http://localhost:3000"

    # LLM — single OpenRouter model for all FinView use cases (options + geo-intel).
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    ntfy_topic: str = ""
    notify_email_to: str = ""
    notify_email_from: str = ""
    notify_email_password: str = ""
    options_monitor_interval_minutes: int = 15

    # Telegram notifications (optional)
    telegram_bot_token: str = ""  # from @BotFather
    telegram_chat_id: str = ""    # personal chat or group ID
    telegram_thread_id: str = ""  # forum-topic (message_thread_id) in the group; empty = General

    # Geo-Intel (WorldHawk) ingest source keys — all optional; a missing key
    # degrades that single source to empty rather than failing the cycle.
    firms_map_key: str = ""        # NASA FIRMS (wildfires)
    windy_api_key: str = ""        # Windy point-forecast (meteo)
    # OpenSky Network (flights). The portal issues OAuth2 client credentials;
    # the username/password pair below is the legacy basic-auth path, kept as a
    # fallback for accounts that still have it. Anonymous works but is heavily
    # rate-limited, which is indistinguishable from "no flights today".
    opensky_client_id: str = ""
    opensky_client_secret: str = ""
    opensky_username: str = ""     # legacy basic auth
    opensky_password: str = ""
    acled_email: str = ""          # ACLED (armed conflict) — OAuth password grant with
    acled_password: str = ""       # the myACLED login; there is no API key any more
    aisstream_key: str = ""        # aisstream.io global AIS (maritime WS, deferred)
    geo_monitor_interval_minutes: int = 15

    # FRED (St. Louis Fed) — risk-free rate source for Black-Scholes Greeks.
    # Optional: when empty, Greeks fall back to per-currency constants (no-op,
    # like Turnstile/aisstream). Free key: https://fred.stlouisfed.org/docs/api/api_key.html
    fred_api_key: str = ""

    # Rate limiting (per-IP, see backend/services/rate_limit.py for IP extraction)
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"

    model_config = {"env_prefix": "FINVIEW_"}

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Block startup if a production-like env runs with insecure/missing secrets."""
        if os.getenv("K_SERVICE") and self.env.lower() not in PRODUCTION_LIKE_ENVS:
            raise RuntimeError(
                "Cloud Run requires FINVIEW_ENV=production; refusing a fail-open "
                "runtime configuration."
            )
        if self.env.lower() not in PRODUCTION_LIKE_ENVS:
            return self

        offenders = []
        for field in ("secret_key", "auth_secret"):
            value = getattr(self, field)
            if not value or value == INSECURE_DEFAULT_SECRET:
                offenders.append(f"FINVIEW_{field.upper()}")

        if offenders:
            raise RuntimeError(
                f"FINVIEW_ENV={self.env!r} requires secure secrets but the following are "
                f"missing or still set to the insecure default: {', '.join(offenders)}. "
                "Set them via environment variables before starting the app."
            )

        # Length was never checked, only presence — so FINVIEW_SECRET_KEY=abc
        # passed and signed every 90-day JWT with a 3-byte HMAC key. RFC 7518
        # §3.2 wants at least as many key bytes as the hash output (32 for
        # HS256); PyJWT warns below that.
        #
        # Deliberately a warning rather than a RuntimeError: this validator runs
        # at import, so raising would refuse to boot a running production whose
        # secret happens to be short. Promote it to `raise` once the deployed
        # secrets are known to clear the bar.
        for field in ("secret_key", "auth_secret"):
            value = getattr(self, field)
            if len(value.encode()) < MIN_SECRET_BYTES:
                _logger.warning(
                    "FINVIEW_%s is %d bytes; HS256 wants at least %d (RFC 7518 §3.2). "
                    "Generate one with: python -c "
                    "'import secrets; print(secrets.token_urlsafe(32))'",
                    field.upper(),
                    len(value.encode()),
                    MIN_SECRET_BYTES,
                )

        if not self.request_scoped_runtime:
            raise RuntimeError(
                "Production requires FINVIEW_REQUEST_SCOPED_RUNTIME=true so work "
                "cannot escape request-based billing."
            )
        if self.database_url.startswith("sqlite"):
            raise RuntimeError(
                "Production requires FINVIEW_DATABASE_URL to reference the persistent "
                "PostgreSQL database, not SQLite."
            )
        return self


settings = Settings()
