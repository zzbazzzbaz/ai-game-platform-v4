from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import RegistryDep
from app.runtime.sandboxes.scan import run_archive_scan

router = APIRouter(prefix="/maintenance", tags=["维护"])


@router.post("/archive-scan")
async def archive_scan(registry: RegistryDep) -> dict[str, int]:
    return await run_archive_scan(registry)
