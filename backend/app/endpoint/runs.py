from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException, status
from app.endpoint.deps import CurrentUser, DbSession
from app.endpoint.schemas.run import RunOut
from app.models import Run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
) -> RunOut:
    run = await session.get(Run, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行记录不存在")
    return RunOut.from_run(run)
