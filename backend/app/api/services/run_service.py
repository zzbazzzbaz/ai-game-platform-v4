from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.repositories import runs
from app.api.repositories.models import Run

STALE_RUN_AFTER = timedelta(minutes=10)


class RunNotFoundError(Exception):
    """运行记录不存在或不属于当前用户。"""


async def get_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Run:
    run = await runs.get_owned(session, run_id, user_id)
    if run is None:
        raise RunNotFoundError
    return run


async def fail_stale_runs(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """进程重启后，上次遗留的 running 记录不可能再有执行者。"""
    async with session_factory() as session:
        return await runs.fail_stale(
            session,
            started_before=datetime.now(UTC) - STALE_RUN_AFTER,
        )
