from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import Session, User


async def get(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def create(session: AsyncSession, *, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_by_token_hash(
    session: AsyncSession,
    token_hash: str,
    *,
    now: datetime,
) -> User | None:
    statement = (
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(
            Session.token_hash == token_hash,
            Session.expires_at > now,
        )
    )
    return await session.scalar(statement)


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
) -> None:
    session.add(
        Session(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await session.commit()


async def delete_session(session: AsyncSession, *, token_hash: str) -> None:
    await session.execute(delete(Session).where(Session.token_hash == token_hash))
    await session.commit()
