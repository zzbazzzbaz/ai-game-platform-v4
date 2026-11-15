from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """应用配置。根目录 .env 先加载，backend/.env 覆盖。"""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str = "deepseek:deepseek-flash"
    deepseek_api_key: str = ""

    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/agent"

    session_secret: str = "dev-session-secret"
    session_cookie: str = "agent_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 30

    demo_email: str = "demo@example.com"
    demo_password: str = "demo1234"

    e2b_api_key: str = ""
    e2b_api_url: str = ""
    e2b_domain: str = ""
    e2b_template: str = ""

    logfire_token: str = ""

    sandbox_timeout: int = 3600
    sandbox_idle_seconds: int = 60 * 30

    @property
    def e2b_template_name(self) -> str | None:
        """空字符串表示使用阿里云默认模板。"""
        return self.e2b_template or None


settings = Settings()
