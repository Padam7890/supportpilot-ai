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
    # Short-lived access JWT; refresh flow extends browser sessions without frequent re-login.
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 30
    invitation_expire_hours: int = 72
    ai_provider_base_url: str | None = None
    ai_provider_api_key: SecretStr | None = Field(default=None, repr=False)
    ai_model: str | None = None
    ai_provider_timeout_seconds: int = Field(default=45, ge=5, le=120)
    ai_provider_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_embedding_base_url: str | None = None
    ai_embedding_api_key: SecretStr | None = Field(default=None, repr=False)
    ai_embedding_timeout_seconds: int = Field(default=60, ge=5, le=180)
    ai_embedding_max_attempts: int = Field(default=3, ge=1, le=6)
    ai_embedding_model: str | None = "text-embedding-3-small"
    ai_embedding_dimensions: int = Field(default=1536, ge=1, le=4096)
    ai_embedding_version: str = "v1"
    ai_embedding_batch_size: int = Field(default=32, ge=1, le=128)
    ai_retrieval_dedupe: bool = True
    ai_retrieval_keyword_limit: int = Field(default=12, ge=1, le=50)
    ai_retrieval_semantic_limit: int = Field(default=12, ge=1, le=50)
    ai_retrieval_result_limit: int = Field(default=6, ge=1, le=10)
    # Cosine similarity lies in [-1, 1]. None keeps the evaluation baseline
    # unthresholded until a corpus-specific threshold has been measured.
    ai_retrieval_similarity_threshold: float | None = Field(default=None, ge=-1, le=1)
    ai_retrieval_token_budget: int = Field(default=4000, ge=256, le=16000)
    ai_retrieval_min_rrf_score: float = Field(default=0.0, ge=0, le=0.2)
    ai_retrieval_rerank_enabled: bool = False
    ai_intent_router_enabled: bool = False
    ai_intent_router_high_confidence: float = Field(default=0.90, ge=0.5, le=1.0)
    ai_intent_router_low_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    ai_intent_router_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_intent_router_max_tokens: int = Field(default=220, ge=64, le=512)
    ai_ingestion_chunk_tokens: int = Field(default=300, ge=64, le=2000)
    ai_ingestion_chunk_overlap_tokens: int = Field(default=48, ge=0, le=512)
    worker_concurrency: int = Field(default=4, ge=1, le=32)
    worker_job_timeout_seconds: int = Field(default=110, ge=10, le=150)
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
    # Development-only: skip workspace login OTP for these normalized emails after password check.
    auth_dev_otp_bypass_emails: list[str] = Field(default_factory=list)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Compose may pass optional settings as empty strings; let backend/.env
        # supply a configured value instead of treating the empty override as set.
        env_ignore_empty=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
