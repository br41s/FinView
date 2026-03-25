from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{Path(__file__).parent.parent / 'finview.db'}"
    data_dir: Path = Path(__file__).parent.parent / "data"

    model_config = {"env_prefix": "FINVIEW_"}


settings = Settings()
