from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./veda.db"
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    frontend_origins: str = "http://localhost:5173"
    dev_auth_enabled: bool = False
    dev_auth_secret: str = ""
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_secret: str = ""
    rate_limit_hash_secret: str = ""
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    rate_limit_user_per_minute: int = Field(default=120, ge=1, le=10_000)
    rate_limit_ip_per_minute: int = Field(default=300, ge=1, le=20_000)
    rate_limit_user_job_creates_per_hour: int = Field(default=6, ge=1, le=500)
    rate_limit_ip_job_creates_per_hour: int = Field(default=24, ge=1, le=2000)
    rate_limit_user_advances_per_minute: int = Field(default=30, ge=1, le=1000)
    rate_limit_ip_advances_per_minute: int = Field(default=120, ge=1, le=5000)
    rate_limit_dev_sessions_per_minute: int = Field(default=10, ge=1, le=500)
    openai_api_key: str = ""
    openai_model_fast: str = ""
    openai_model_reasoning: str = ""
    allow_paid_llm_calls: bool = False
    openai_input_price_per_million: float | None = Field(default=None, ge=0)
    openai_output_price_per_million: float | None = Field(default=None, ge=0)
    llm_provider: str = "disabled"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_reasoning_enabled: bool | None = None
    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"
    sarvam_input_price_per_million_inr: float | None = Field(default=15.0, ge=0)
    sarvam_output_price_per_million_inr: float | None = Field(default=60.0, ge=0)
    # Zero disables Sarvam dispatch unless an operator explicitly configures a cap.
    # Hard pre-tax reservation ceiling. A live validation can set this lower;
    # the currently authorized GLM run uses at most ₹20.
    sarvam_max_job_cost_inr: float = Field(default=0.0, ge=0, le=20)
    openalex_api_key: str = ""
    openalex_allow_billable_calls: bool = False
    crawl4ai_key: str = ""
    crawl4ai_enabled: bool = False
    crawl4ai_max_requests_per_job: int = Field(default=2, ge=0, le=3)
    crawl4ai_max_credits_per_job: float = Field(default=2.0, ge=0, le=3.0)
    crawl4ai_max_total_requests_per_job: int = Field(default=6, ge=0, le=8)
    crawl4ai_max_total_credits_per_job: float = Field(default=5.0, ge=0, le=8.0)
    crawl4ai_max_scrape_requests_per_job: int = Field(default=1, ge=0, le=1)
    crawl4ai_max_scrape_credits_per_job: float = Field(default=1.0, ge=0, le=2.0)
    # The estimate endpoint does not consistently return an x-c4-cost receipt.
    # Reserve one credit for that uncertainty before any scrape is dispatched.
    crawl4ai_estimate_reservation_credits: float = Field(default=1.0, ge=0, le=1.0)
    # Content-rights policy is use-context specific. An empty jurisdiction keeps
    # unlicensed content metadata-only until the operator configures applicable law.
    rights_use_mode: str = "private_research"
    rights_jurisdiction: str = ""
    crossref_mailto: str = ""
    # World Bank D&R API use is restricted to non-commercial purposes absent
    # permission; dispatch requires an explicit operator confirmation.
    world_bank_documents_noncommercial_use_confirmed: bool = False
    # Optional loopback-only GROBID PDF parser; the existing bounded pypdf
    # extractor remains the default when the service is not installed.
    grobid_enabled: bool = False
    grobid_base_url: str = "http://127.0.0.1:8070"
    max_job_cost_usd: float = Field(default=2.0, ge=0, le=20)
    # Defaults support a bounded standard run. Provider-side limits, per-job
    # monetary ceilings and atomic reservations remain separate controls.
    max_daily_model_calls: int = Field(default=50, ge=0, le=1000)
    max_daily_model_calls_per_user: int = Field(default=50, ge=0, le=1000)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def normalize_origins(cls, value: str) -> str:
        return value.strip()

    @field_validator("rights_use_mode")
    @classmethod
    def validate_rights_use_mode(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"private_research", "commercial", "public_sharing"}:
            raise ValueError(
                "RIGHTS_USE_MODE must be private_research, commercial, or public_sharing"
            )
        return normalized

    @field_validator("rights_jurisdiction", mode="before")
    @classmethod
    def validate_rights_jurisdiction(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized and (len(normalized) != 2 or not normalized.isalpha()):
            raise ValueError("RIGHTS_JURISDICTION must be two alphabetic characters or empty")
        return normalized

    def validate_security_configuration(self) -> None:
        is_production = self.app_env.lower() in {"production", "prod"}
        if is_production and self.dev_auth_enabled:
            raise ValueError("Development authentication cannot be enabled in production")
        if self.dev_auth_enabled and len(self.dev_auth_secret) < 32:
            raise ValueError("DEV_AUTH_SECRET must contain at least 32 characters")
        if (
            self.app_env.lower() not in {"development", "dev", "test"}
            and len(self.rate_limit_hash_secret) < 32
        ):
            raise ValueError(
                "RATE_LIMIT_HASH_SECRET must contain at least 32 characters in production"
            )
        if is_production:
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL; SQLite is not durable storage")
            auth_origin = urlsplit(self.supabase_url)
            if auth_origin.scheme != "https" or not auth_origin.netloc:
                raise ValueError("Production requires an HTTPS SUPABASE_URL")
            if not (self.supabase_jwks_url or self.supabase_jwt_secret):
                raise ValueError("Production requires SUPABASE_JWKS_URL or SUPABASE_JWT_SECRET")
            if self.supabase_jwt_secret and len(self.supabase_jwt_secret) < 32:
                raise ValueError("SUPABASE_JWT_SECRET must contain at least 32 characters")
            if self.supabase_jwks_url:
                jwks_url = urlsplit(self.supabase_jwks_url)
                if jwks_url.scheme != "https" or not jwks_url.netloc:
                    raise ValueError("Production requires an HTTPS SUPABASE_JWKS_URL")
            origins = self.cors_origins
            if not origins:
                raise ValueError("Production requires at least one HTTPS FRONTEND_ORIGINS entry")
            for origin in origins:
                parsed_origin = urlsplit(origin)
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.netloc
                    or parsed_origin.path
                    or parsed_origin.query
                    or parsed_origin.fragment
                ):
                    raise ValueError("Production FRONTEND_ORIGINS must contain HTTPS origins only")
        if self.llm_provider not in {"disabled", "openrouter", "openai", "sarvam"}:
            raise ValueError("LLM_PROVIDER must be disabled, openrouter, openai, or sarvam")
        if (
            self.llm_provider == "openrouter"
            and self.openrouter_model != "openrouter/free"
            and not self.openrouter_model.endswith(":free")
        ):
            raise ValueError(
                "OpenRouter Veda workflow only accepts openrouter/free or a :free model"
            )
        if self.llm_provider == "sarvam" and self.sarvam_model not in {
            "sarvam-105b",
            "glm5.3-flash",
        }:
            raise ValueError(
                "LLM_PROVIDER=sarvam must use a model in Veda's reviewed Sarvam registry"
            )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    config = Settings()
    config.validate_security_configuration()
    return config


settings = get_settings()
