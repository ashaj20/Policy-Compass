from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PC_", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://pc:pc@localhost:5432/policy_compass"
    # Origins allowed to call the API from a browser (the React dev server in development).
    cors_origins: list[str] = ["http://localhost:5173"]
    # Built React app to serve from the same origin as the API (set in the Docker image).
    frontend_dist: str | None = None
    # Base URL of the web app, used to build links in emails.
    public_base_url: str = "http://localhost:5173"

    # Where uploaded files (logos, later policy documents) are stored on disk.
    storage_dir: str = "storage"
    logo_max_bytes: int = 2 * 1024 * 1024
    policy_max_bytes: int = 20 * 1024 * 1024
    # Re-queue uploads left mid-processing when the server starts (off in tests).
    resume_processing_on_startup: bool = True
    # Run the retention clean-up at start-up and then daily (off in tests).
    retention_schedule_enabled: bool = True

    # Claude, for writing grounded answers (US-014). Decided 18 Oct 2026: Claude Haiku 5.5 to keep
    # credit use low, and at most 100 Claude answers per organisation per day. The key is read from
    # ANTHROPIC_API_KEY (backend/.env); without it, answers fall back to escalation.
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "PC_ANTHROPIC_API_KEY")
    )
    llm_model: str = "claude-haiku-5-5"
    llm_daily_answer_cap: int = 100
    llm_max_output_tokens: int = 1500
    llm_timeout_seconds: float = 30.0
    # Evidence gate: Claude is only asked when a passage is at least this relevant (cosine
    # similarity with the local embedding model; ~0.75+ for good matches, ~0.5 for unrelated).
    retrieval_min_score: float = 0.6
    answer_max_passages: int = 4
    # A weaker match than retrieval_min_score: too weak to answer from, but related enough to
    # pick whose contact details to show when we can't answer (US-017).
    # Measured with bge-small: related ("boiler servicing" vs repairs) ~0.58, unrelated
    # ("rent date", "annual leave") 0.51-0.55.
    escalation_min_score: float = 0.56

    # Sessions and one-time tokens
    session_days: int = 14
    verify_token_hours: int = 24
    reset_token_minutes: int = 60
    invitation_days: int = 7

    # Email. With no SMTP host, emails are written to the server log (development).
    email_from: str = "Policy Compass <no-reply@example.org>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        # Hosting providers such as Render hand out plain postgres:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
