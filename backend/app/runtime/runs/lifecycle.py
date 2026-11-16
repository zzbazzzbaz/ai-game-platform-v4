from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories import runs

STALE_RUN_AFTER = timedelta(minutes=10)


async def fail_stale_runs(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """进程重启后，上次遗留的 running 记录不可能再有执行者。"""
    async with session_factory() as session:
        return await runs.fail_stale(
            session,
            started_before=datetime.now(UTC) - STALE_RUN_AFTER,
        )
