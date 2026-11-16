from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import Game, SandboxSession


async def create(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str = "新游戏",
) -> Game:
    game = Game(id=uuid.uuid7(), user_id=user_id, name=name)
    session.add(game)
    await session.commit()
    await session.refresh(game)
    return game


async def list_owned(session: AsyncSession, user_id: uuid.UUID) -> list[Game]:
    rows = await session.scalars(
        select(Game).where(Game.user_id == user_id).order_by(Game.updated_at.desc())
    )
    return list(rows.all())


async def get_owned(
    session: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Game | None:
    row = await session.get(Game, game_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def delete_owned(
    session: AsyncSession,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        delete(Game)
        .where(Game.id == game_id, Game.user_id == user_id)
        .returning(Game.id)
    )
    await session.commit()
    return bool(result.scalars().all())


async def get_sandbox(session: AsyncSession, game_id: uuid.UUID) -> SandboxSession | None:
    return await session.scalar(
        select(SandboxSession).where(SandboxSession.game_id == game_id)
    )


async def ensure_sandbox_row(session: AsyncSession, game_id: uuid.UUID) -> SandboxSession:
    row = await get_sandbox(session, game_id)
    if row is not None:
        return row
    row = SandboxSession(game_id=game_id)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_sandbox(session, game_id)
        if existing is None:
            raise
        return existing
    await session.refresh(row)
    return row


async def update_sandbox(
    session: AsyncSession,
    game_id: uuid.UUID,
    **values: Any,
) -> SandboxSession | None:
    row = await get_sandbox(session, game_id)
    if row is None:
        return None
    for key, value in values.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row
