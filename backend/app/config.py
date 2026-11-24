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

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def session_cookie(self) -> str:
        return "__Host-th_session" if self.is_production else "th_session"

    @model_validator(mode="after")
    def check(self):
        self.public_url = self.public_url.rstrip("/")
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
