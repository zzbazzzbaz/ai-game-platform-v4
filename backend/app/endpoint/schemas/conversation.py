from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models import Conversation


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Conversation) -> "ConversationOut":
        return cls(
            id=str(row.id),
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
