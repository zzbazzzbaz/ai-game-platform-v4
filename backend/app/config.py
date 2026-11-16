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
    fcsandbox_team_id: str
    aliyun_region: str

    logfire_token: str
    logfire_environment: str

    sandbox_timeout: int
    sandbox_heartbeat_seconds: int
    sandbox_archive_after_seconds: int
    sandbox_archive_scan_seconds: int
    sandbox_workspace_dir: str
    sandbox_game_port: int
    sandbox_novnc_port: int

    oss_endpoint: str
    oss_bucket: str
    oss_access_key_id: str
    oss_access_key_secret: str
    oss_security_token: str
    oss_prefix: str
    oss_proxy: str


settings = Settings()
