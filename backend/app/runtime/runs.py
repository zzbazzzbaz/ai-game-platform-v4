from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import AgentRunResult, CancellationToken
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.usage import RunUsage
from pydantic import TypeAdapter
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.db import engine
from app.models import Run

logger = logging.getLogger(__name__)

_usage_adapter = TypeAdapter(RunUsage)


class RunBusy(RuntimeError):
    """同一 conversation 已有 run 在执行。"""


@dataclass
class ActiveRun:
    id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    parent_run_id: uuid.UUID | None
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    result: AgentRunResult[Any] | None = None
    usage: RunUsage | None = None
    cancelled: bool = False
    finished: bool = False
    error: BaseException | None = None
    _lock_connection: AsyncConnection | None = None
    _lock_key: int = 0


def advisory_key(conversation_id: uuid.UUID) -> int:
    return int.from_bytes(conversation_id.bytes[:8], "big", signed=True)


class RunManager:
    """同一 conversation 的运行锁、`runs` 记录与取消令牌。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory
        self._active: dict[uuid.UUID, ActiveRun] = {}

    async def start(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID, model: str
    ) -> ActiveRun:
        if conversation_id in self._active:
            raise RunBusy(str(conversation_id))

        key = advisory_key(conversation_id)
        connection = await engine.connect()
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        if not locked:
            await connection.close()
            raise RunBusy(str(conversation_id))

        try:
            async with self._sessions() as session:
                parent_run_id = await session.scalar(
                    select(Run.id)
                    .where(
                        Run.conversation_id == conversation_id,
                        Run.status == "waiting_approval",
                    )
                    .order_by(Run.started_at.desc())
                    .limit(1)
                )
                run = Run(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    status="running",
                    model=model,
                    parent_run_id=parent_run_id,
                )
                session.add(run)
                await session.commit()
                await session.refresh(run)
        except BaseException:
            await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            await connection.close()
            raise

        active = ActiveRun(
            id=run.id,
            conversation_id=conversation_id,
            user_id=user_id,
            parent_run_id=parent_run_id,
        )
        active._lock_connection = connection
        active._lock_key = key
        self._active[conversation_id] = active
        return active

    def active(self, conversation_id: uuid.UUID) -> ActiveRun | None:
        return self._active.get(conversation_id)

    async def cancel(self, conversation_id: uuid.UUID) -> uuid.UUID | None:
        active = self._active.get(conversation_id)
        if active is None:
            return None
        active.cancellation.cancel()
        return active.id

    async def finish(self, active: ActiveRun) -> None:
        if active.finished:
            return
        active.finished = True
        self._active.pop(active.conversation_id, None)
        usage: RunUsage = (
            active.result.usage
            if active.result is not None
            else active.usage
            if active.usage is not None
            else RunUsage()
        )
        if active.cancelled:
            status = "cancelled"
        elif active.result is not None and isinstance(active.result.output, DeferredToolRequests):
            status = "waiting_approval"
        elif active.result is not None:
            status = "completed"
        else:
            status = "failed"

        error: dict[str, Any] | None = None
        if active.error is not None:
            error = {"type": type(active.error).__name__, "message": str(active.error)}

        try:
            async with self._sessions() as session:
                await session.execute(
                    update(Run)
                    .where(Run.id == active.id)
                    .values(
                        status=status,
                        finished_at=datetime.now(UTC),
                        usage=_usage_adapter.dump_python(usage, mode="json"),
                        error=error,
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001 - 收尾失败仍必须释放运行锁
            logger.exception("更新 run %s 状态失败", active.id)
        finally:
            if active._lock_connection is not None:
                try:
                    await active._lock_connection.scalar(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": active._lock_key}
                    )
                finally:
                    await active._lock_connection.close()

    async def latest_for_conversation(self, conversation_id: uuid.UUID) -> Run | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(Run)
                .where(Run.conversation_id == conversation_id)
                .order_by(Run.started_at.desc())
                .limit(1)
            )

    async def count_running(self) -> int:
        async with self._sessions() as session:
            return await session.scalar(
                select(func.count()).select_from(Run).where(Run.status == "running")
            ) or 0
