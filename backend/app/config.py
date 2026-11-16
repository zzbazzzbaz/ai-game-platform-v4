from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str
    deepseek_api_key: str
    deepseek_base_url: str

    database_url: str

    session_secret: str
    session_cookie: str
    session_ttl_seconds: int

    e2b_api_key: str
    e2b_api_url: str
    e2b_domain: str
    e2b_template: str

    logfire_token: str
    logfire_environment: str

    sandbox_timeout: int
    sandbox_idle_seconds: int


settings = Settings()
