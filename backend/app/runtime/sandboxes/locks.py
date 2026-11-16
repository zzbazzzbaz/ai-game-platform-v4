from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text

from app.database import engine
from app.runtime.sandboxes.errors import LockBusy

_POLL_SECONDS = 0.25


async def _try_lock(key: str) -> bool:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("select pg_try_advisory_lock(hashtext(:key)::bigint)"),
            {"key": key},
        )
        return bool(result.scalar_one())


@asynccontextmanager
async def advisory_lock(key: str, *, wait_seconds: float | None) -> AsyncGenerator[None]:
    """PostgreSQL 会话级 advisory lock。

    `wait_seconds=None` 表示一直等；`0` 表示只尝试一次。
    连接在整个临界区内保持占用，避免 session 级锁提前释放。
    """
    async with engine.connect() as connection:
        got = bool(
            (
                await connection.execute(
                    text("select pg_try_advisory_lock(hashtext(:key)::bigint)"),
                    {"key": key},
                )
            ).scalar_one()
        )
        deadline = None if wait_seconds is None else time.monotonic() + wait_seconds
        while not got:
            if deadline is not None and time.monotonic() >= deadline:
                raise LockBusy(key)
            await asyncio.sleep(_POLL_SECONDS)
            got = bool(
                (
                    await connection.execute(
                        text("select pg_try_advisory_lock(hashtext(:key)::bigint)"),
                        {"key": key},
                    )
                ).scalar_one()
            )
        try:
            yield
        finally:
            await connection.execute(
                text("select pg_advisory_unlock(hashtext(:key)::bigint)"),
                {"key": key},
            )
            await connection.commit()


async def lock_is_free(key: str) -> bool:
    """只探测，不持有锁。"""
    async with engine.connect() as connection:
        got = bool(
            (
                await connection.execute(
                    text("select pg_try_advisory_lock(hashtext(:key)::bigint)"),
                    {"key": key},
                )
            ).scalar_one()
        )
        if got:
            await connection.execute(
                text("select pg_advisory_unlock(hashtext(:key)::bigint)"),
                {"key": key},
            )
            await connection.commit()
        return got
