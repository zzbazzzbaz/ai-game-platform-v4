from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.runtime.sandboxes.registry import SandboxRegistry

logger = logging.getLogger(__name__)


async def _heartbeat_loop(
    registry: SandboxRegistry, game_id: uuid.UUID, interval: int
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await registry.touch(game_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("沙箱心跳失败 game=%s", game_id)


@asynccontextmanager
async def keep_sandbox_alive(
    registry: SandboxRegistry, game_id: uuid.UUID, interval: int
) -> AsyncGenerator[None]:
    """在 agent run 期间定期 connect(timeout=600)，避免长思考/长命令中途暂停。"""
    task = asyncio.create_task(_heartbeat_loop(registry, game_id, interval))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
