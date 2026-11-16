from __future__ import annotations

import logging

from app.runtime.sandboxes.errors import LockBusy
from app.runtime.sandboxes.locks import advisory_lock
from app.runtime.sandboxes.registry import SandboxRegistry

logger = logging.getLogger(__name__)


async def run_archive_scan(registry: SandboxRegistry) -> dict[str, int]:
    """APScheduler 每轮扫描；全局锁保证多进程只有一个扫描器。"""
    try:
        async with advisory_lock("sandbox:archive-scan", wait_seconds=0):
            result = await registry.archive_due()
    except LockBusy:
        return {"scanned": 0, "archived": 0, "skipped": 1, "failed": 0}
    if result["archived"] or result["failed"]:
        logger.info("沙箱归档扫描完成：%s", result)
    return result
