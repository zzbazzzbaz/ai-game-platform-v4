from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """应用配置。所有值只来自环境变量文件，代码中不提供默认值。"""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str
    deepseek_api_key: str

    database_url: str

    session_secret: str
    session_cookie: str
    session_ttl_seconds: int

    demo_email: str
    demo_password: str

    e2b_api_key: str
    e2b_api_url: str
    e2b_domain: str
    e2b_template: str

    logfire_token: str

    sandbox_timeout: int
    sandbox_idle_seconds: int

    @property
    def e2b_template_name(self) -> str | None:
        """空字符串表示使用阿里云默认模板。"""
        return self.e2b_template or None


settings = Settings()
