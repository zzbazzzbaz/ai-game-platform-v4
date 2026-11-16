from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.dto.run import RunOut


class ConversationCreate(BaseModel):
    game_id: uuid.UUID | None = None
    name: str = Field(default="新游戏", min_length=1, max_length=120)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    game_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    deferred_tool_requests: dict[str, Any] | None = None
    last_run: RunOut | None = None
