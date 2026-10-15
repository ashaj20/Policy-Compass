from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PC_", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://pc:pc@localhost:5432/policy_compass"
    # Origins allowed to call the API from a browser (the React dev server in development).
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
