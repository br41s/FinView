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

    model_config = {"env_prefix": "FINVIEW_"}


settings = Settings()
