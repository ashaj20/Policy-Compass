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
