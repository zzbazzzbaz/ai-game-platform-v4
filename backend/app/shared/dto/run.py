from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    model: str
    started_at: datetime
    finished_at: datetime | None
    usage: dict[str, Any]
    error: dict[str, Any] | None
