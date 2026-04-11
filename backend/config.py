from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{Path(__file__).parent.parent / 'finview.db'}"
    data_dir: Path = Path(__file__).parent.parent / "data"

    # Auth / JWT
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # NextAuth shared secret (must match AUTH_SECRET on frontend)
    auth_secret: str = "change-me-in-production"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""  # Stripe Price ID for Pro plan
    stripe_price_unlimited: str = ""  # Stripe Price ID for Unlimited plan
    frontend_url: str = "http://localhost:3000"

    # Options monitor
    anthropic_api_key: str = ""
    ntfy_topic: str = ""
    notify_email_to: str = ""
    notify_email_from: str = ""
    notify_email_password: str = ""
    options_monitor_interval_minutes: int = 15

    model_config = {"env_prefix": "FINVIEW_"}


settings = Settings()
