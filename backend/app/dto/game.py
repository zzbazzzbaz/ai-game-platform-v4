from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GameCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class SandboxStatusOut(BaseModel):
    lifecycle_state: str
    sandbox_id: str | None = None
    platform_state: str | None = None
    end_at: str | None = None
    snapshot_key: str | None = None
    snapshot_at: str | None = None
    snapshot_bytes: int | None = None
    snapshot_sha256: str | None = None
    last_used_at: str | None = None
    archive_retry_at: str | None = None
    archive_attempts: int = 0
    last_error: str | None = None


class ArchiveOut(BaseModel):
    status: str
    snapshot_key: str | None = None
    snapshot_bytes: int | None = None
    snapshot_sha256: str | None = None
    oss_etag: str | None = None


class TouchOut(BaseModel):
    game_id: uuid.UUID
    sandbox_id: str


class GameOpenOut(BaseModel):
    game_id: uuid.UUID
    sandbox_id: str
    game_url: str
    novnc_url: str
