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
    ai_input_cost_per_million: float | None = Field(default=None, ge=0)
    ai_output_cost_per_million: float | None = Field(default=None, ge=0)
    shopify_client_id: str | None = None
    shopify_client_secret: SecretStr | None = Field(default=None, repr=False)
    shopify_store_domain: str | None = None
    shopify_redirect_uri: str | None = None
    shopify_encryption_key: SecretStr | None = Field(default=None, repr=False)
    shopify_api_version: str = "2026-10"
    shopify_timeout_seconds: int = Field(default=20, ge=5, le=60)
    email_smtp_host: str | None = None
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_smtp_username: str | None = None
    email_smtp_password: SecretStr | None = Field(default=None, repr=False)
    email_from_address: str | None = None
    email_use_ssl: bool = False
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
