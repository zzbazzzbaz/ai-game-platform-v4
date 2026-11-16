from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.api.services import run_service
from app.shared.dto.run import RunOut
from app.shared.errors import not_found

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
        raise not_found("运行记录不存在") from error
    return RunOut.model_validate(run)
