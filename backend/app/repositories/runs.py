from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import Run


async def get_owned(
    session: AsyncSession,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Run | None:
    run = await session.get(Run, run_id)
    if run is None or run.user_id != user_id:
        return None
    return run


async def latest(session: AsyncSession, conversation_id: uuid.UUID) -> Run | None:
    return await session.scalar(
        select(Run)
        .where(Run.conversation_id == conversation_id)
        .order_by(Run.started_at.desc())
        .limit(1)
    )


async def latest_waiting(session: AsyncSession, conversation_id: uuid.UUID) -> Run | None:
    return await session.scalar(
        select(Run)
        .where(Run.conversation_id == conversation_id, Run.status == "waiting_approval")
        .order_by(Run.started_at.desc())
        .limit(1)
    )


async def fail_stale(session: AsyncSession, *, started_before: datetime) -> int:
    result = await session.execute(
        update(Run)
        .where(Run.status == "running", Run.started_at < started_before)
        .values(
            status="failed",
            finished_at=datetime.now(started_before.tzinfo),
            error={"type": "ServerRestart", "message": "服务重启，运行被中断"},
        )
    )
    await session.commit()
    return int(result.rowcount or 0)
