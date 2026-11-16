from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import Run


class RunOut(BaseModel):
    id: str
    status: str
    model: str
    started_at: datetime
    finished_at: datetime | None
    usage: dict[str, Any]
    error: dict[str, Any] | None

    @classmethod
    def from_run(cls, run: Run) -> "RunOut":
        return cls(
            id=str(run.id),
            status=run.status,
            model=run.model,
            started_at=run.started_at,
            finished_at=run.finished_at,
            usage=run.usage,
            error=run.error,
        )
