from functools import lru_cache

from pydantic import field_validator
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

    # Sessions and one-time tokens
    session_days: int = 14
    verify_token_hours: int = 24
    reset_token_minutes: int = 60

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
