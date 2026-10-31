from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SupportPilot AI"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        ...,
        repr=False,
    )
    redis_url: str = Field(
        ...,
        repr=False,
    )
    jwt_secret: str = Field(
        ...,
        repr=False,
    )
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    invitation_expire_hours: int = 72
    ai_provider_base_url: str | None = None
    ai_provider_api_key: SecretStr | None = Field(default=None, repr=False)
    ai_model: str | None = None
    ai_provider_timeout_seconds: int = Field(default=45, ge=5, le=120)
    ai_provider_max_attempts: int = Field(default=2, ge=1, le=3)
    cors_origins: list[str] = [
        "http://localhost:3000",
    ]
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
