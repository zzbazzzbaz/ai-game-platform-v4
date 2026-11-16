from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_size=10, max_overflow=10, pool_pre_ping=True)

# 运行锁连接会贯穿整个 SSE 生命周期，单独成池，避免占满业务连接。
lock_engine: AsyncEngine = create_async_engine(settings.database_url, poolclass=NullPool)
session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    await lock_engine.dispose()
    await engine.dispose()
