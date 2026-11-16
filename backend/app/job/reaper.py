from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import dispose_engine, lock_engine, session_factory
from app.repositories.models import Run, SandboxSession
from app.services.sandbox_registry import SandboxRegistry, create_e2b_client

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 300

# 与 RunManager 的单 key advisory lock 使用不同的锁空间。
REAPER_LOCK_CLASS_ID = 0x52455052  # "REPR"
REAPER_LOCK_OBJECT_ID = 1


async def sweep(
    registry: SandboxRegistry,
    sessions: async_sessionmaker[AsyncSession],
) -> int:
    """回收长时间空闲且没有运行中 run 的沙箱。"""
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.sandbox_idle_seconds)
    running = select(Run.conversation_id).where(Run.status == "running")
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(SandboxSession).where(
                    SandboxSession.last_used_at < cutoff,
                    SandboxSession.conversation_id.not_in(running),
                )
            )
        ).all()

    reclaimed = 0
    for row in rows:
        try:
            await registry.kill_checked(row.sandbox_id)
        except Exception:  # 单个沙箱失败不影响其余记录
            logger.warning("回收沙箱 %s 失败", row.sandbox_id, exc_info=True)
            continue

        async with sessions() as session:
            await session.execute(
                delete(SandboxSession).where(SandboxSession.id == row.id)
            )
            await session.commit()
        reclaimed += 1
    return reclaimed


async def run_reaper() -> int:
    """获取 PostgreSQL advisory lock 后执行一次回收。"""
    async with lock_engine.connect() as connection:
        locked = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:class_id, :object_id)"),
            {"class_id": REAPER_LOCK_CLASS_ID, "object_id": REAPER_LOCK_OBJECT_ID},
        )
        if not locked:
            logger.info("另一个沙箱回收任务正在运行，跳过本次执行")
            return 0

        try:
            registry = SandboxRegistry(create_e2b_client(), session_factory)
            reclaimed = await sweep(registry, session_factory)
            if reclaimed:
                logger.info("已回收 %s 个空闲沙箱", reclaimed)
            return reclaimed
        except Exception:  # 单次回收失败不退出定时任务
            logger.exception("沙箱回收失败")
            return 0
        finally:
            await connection.scalar(
                text("SELECT pg_advisory_unlock(:class_id, :object_id)"),
                {"class_id": REAPER_LOCK_CLASS_ID, "object_id": REAPER_LOCK_OBJECT_ID},
            )


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_reaper,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="sandbox-reaper",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
        replace_existing=True,
        next_run_time=datetime.now(UTC),
    )
    scheduler.start()
    logger.info("沙箱回收任务已启动，间隔 %s 秒", SCAN_INTERVAL_SECONDS)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
