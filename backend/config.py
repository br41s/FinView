from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

INSECURE_DEFAULT_SECRET = "change-me-in-production"  # nosec: sentinel, not a real secret
PRODUCTION_LIKE_ENVS = {"staging", "production", "prod"}


class Settings(BaseSettings):
    # Deployment environment: "local", "dev", "test", "staging", "production".
    # Production-like environments enforce secret validation at startup.
    env: str = "local"

    database_url: str = f"sqlite:///{Path(__file__).parent.parent / 'finview.db'}"
    data_dir: Path = Path(__file__).parent.parent / "data"

    # Auth / JWT
    secret_key: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 90  # 90 days

    # NextAuth shared secret (must match AUTH_SECRET on frontend)
    auth_secret: str = INSECURE_DEFAULT_SECRET

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

    # Geo-Intel (WorldHawk) ingest source keys — all optional; a missing key
    # degrades that single source to empty rather than failing the cycle.
    firms_map_key: str = ""        # NASA FIRMS (wildfires)
    windy_api_key: str = ""        # Windy point-forecast (meteo)
    opensky_username: str = ""     # OpenSky Network (flights) — optional auth
    opensky_password: str = ""
    acled_email: str = ""          # ACLED (armed conflict) — needs email + key
    acled_key: str = ""
    aisstream_key: str = ""        # aisstream.io global AIS (maritime WS, deferred)
    geo_monitor_interval_minutes: int = 15

    # Rate limiting (per-IP, see backend/services/rate_limit.py for IP extraction)
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"

    model_config = {"env_prefix": "FINVIEW_"}

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Block startup if a production-like env runs with insecure/missing secrets."""
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
        return self


settings = Settings()
