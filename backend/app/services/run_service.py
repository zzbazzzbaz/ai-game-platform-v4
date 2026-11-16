from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import runs
from app.repositories.models import Run


class RunNotFoundError(Exception):
    """运行记录不存在或不属于当前用户。"""


async def get_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Run:
    run = await runs.get_owned(session, run_id, user_id)
    if run is None:
        raise RunNotFoundError
    return run
