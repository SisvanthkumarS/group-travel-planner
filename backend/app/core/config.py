from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )

    app_name: str = "Group Travel Planner"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://travel@localhost:5432/travel"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, gt=0)
    jwt_cookie_name: str = "access_token"
    jwt_cookie_secure: bool = False
    jwt_refresh_cookie_name: str = "refresh_token"
    jwt_refresh_token_expire_days: int = Field(default=7, gt=0)
    jwt_session_max_days: int = Field(default=30, gt=0)
    jwt_refresh_window_seconds: int = Field(default=60, ge=0)
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    redis_key_prefix: str = "travel:auth:refresh:"
    redis_timeout_seconds: float = Field(default=2, gt=0)
    poll_scheduler_enabled: bool = True
    poll_scheduler_interval_seconds: float = Field(default=5, gt=0)
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def validate_cookie_names(self):
        if not self.jwt_cookie_name or not self.jwt_refresh_cookie_name:
            raise ValueError("Authentication cookie names cannot be empty.")
        if self.jwt_cookie_name == self.jwt_refresh_cookie_name:
            raise ValueError("Access and refresh cookies must have different names.")
        if not self.redis_key_prefix:
            raise ValueError("Redis key prefix cannot be empty.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
