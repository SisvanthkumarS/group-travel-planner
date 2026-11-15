from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, model_validator
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
    email_enabled: bool = False
    email_test_enabled: bool = False
    email_timeout_seconds: float = Field(default=10, gt=0, le=60)
    notification_email_worker_enabled: bool = True
    notification_email_interval_seconds: float = Field(default=5, gt=0)
    notification_email_batch_size: int = Field(default=20, ge=1, le=100)
    notification_email_max_attempts: int = Field(default=5, ge=1, le=20)
    notification_email_retry_seconds: float = Field(default=60, gt=0, le=3600)
    notification_email_lease_seconds: float = Field(default=600, ge=120)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_encryption: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    email_from_address: EmailStr | None = None
    email_from_name: str = Field(default="Group Travel Planner", pattern=r"^[^\r\n]*$")

    @model_validator(mode="after")
    def validate_email_settings(self):
        if not self.email_enabled:
            return self
        if self.email_from_address is None:
            raise ValueError("EMAIL_ENABLED requires EMAIL_FROM_ADDRESS.")
        if not self.smtp_host.strip():
            raise ValueError("SMTP email requires SMTP_HOST.")
        if bool(self.smtp_username) != bool(self.smtp_password.get_secret_value()):
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or neither.")
        if self.smtp_encryption == "none":
            if self.app_env not in {"development", "test"} or self.smtp_username:
                raise ValueError("Unencrypted SMTP is only for local testing without credentials.")
        return self

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
