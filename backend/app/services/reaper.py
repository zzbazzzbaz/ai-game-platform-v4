from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.repositories.models import Run, SandboxSession
from app.services.sandbox_registry import SandboxRegistry

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 300


class SandboxReaper:
    """回收长时间空闲的沙箱。"""

    def __init__(self, registry: SandboxRegistry, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._registry = registry
        self._sessions = session_factory

    async def run_forever(self) -> None:
        while True:
            try:
                await self.sweep()
            except Exception:  # 单次扫描失败不退出循环
                logger.exception("沙箱回收失败")
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    async def sweep(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.sandbox_idle_seconds)
        async with self._sessions() as session:
            running = select(Run.conversation_id).where(Run.status == "running")
            rows = (
                await session.scalars(
                    select(SandboxSession).where(
                        SandboxSession.status == "active",
                        SandboxSession.last_used_at < cutoff,
                        SandboxSession.conversation_id.not_in(running),
                    )
                )
            ).all()
        for row in rows:
            try:
                await self._registry.kill_checked(row.sandbox_id)
            except Exception:  # 单个沙箱失败不影响其余记录
                logger.warning("回收沙箱 %s 失败", row.sandbox_id, exc_info=True)
                continue
            async with self._sessions() as session:
                await session.execute(
                    update(SandboxSession)
                    .where(SandboxSession.id == row.id)
                    .values(status="dead")
                )
                await session.commit()
        return len(rows)
