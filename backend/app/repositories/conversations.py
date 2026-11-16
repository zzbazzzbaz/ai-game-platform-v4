from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import Conversation


async def list_owned(session: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(rows.all())


async def get_owned(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation | None:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def create(
    session: AsyncSession,
    user_id: uuid.UUID,
    game_id: uuid.UUID,
) -> Conversation:
    row = Conversation(id=uuid.uuid7(), user_id=user_id, game_id=game_id, title="新会话", usage={})
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
