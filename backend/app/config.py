from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")

    # Production is the default so that a missing setting can never enable the fake login.
    env: Literal["production", "dev", "test"] = "production"
    public_url: str = "https://twilight-hearth.net"
    database_url: str | None = None
    secret_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    media_dir: Path = Path("media")
    session_days: int = 30
    invite_days: int = 14
    max_upload_bytes: int = 15 * 1024 * 1024
    # Recipe import. Without a key, only sources that need no model can be imported.
    anthropic_api_key: str = ""
    import_model: str = "claude-haiku-5-5"
    import_retry_model: str = "claude-sonnet-5-5"
    # Dollars per million input and output tokens.
    import_prices: dict[str, tuple[float, float]] = {
        "claude-haiku-5-5": (0.10, 0.50),
        "claude-sonnet-5-5": (2.0, 10.0),
    }
    import_daily_limit: int = 100
    import_daily_model_limit: int = 20
    import_monthly_dollars: float = 10

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def session_cookie(self) -> str:
        return "__Host-th_session" if self.is_production else "th_session"

    @model_validator(mode="after")
    def check(self):
        self.public_url = self.public_url.rstrip("/")
        if not {self.import_model, self.import_retry_model} <= self.import_prices.keys():
            raise ValueError("TH_IMPORT_PRICES must include both import models")
        if len(self.secret_key) < 32:
            raise ValueError("TH_SECRET_KEY must be at least 32 characters")
        if self.is_production:
            if not self.public_url.startswith("https://"):
                raise ValueError("TH_PUBLIC_URL must be https in production")
            for name in ("database_url", "google_client_id", "google_client_secret"):
                if not getattr(self, name):
                    raise ValueError(f"TH_{name.upper()} is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
