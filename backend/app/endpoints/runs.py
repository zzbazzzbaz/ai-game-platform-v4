from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.dto.run import RunOut
from app.errors import not_found
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["运行"])


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
) -> RunOut:
    try:
        run = await run_service.get_run(session, run_id, user.id)
    except run_service.RunNotFoundError as error:
        raise not_found() from error
    return RunOut.model_validate(run)
