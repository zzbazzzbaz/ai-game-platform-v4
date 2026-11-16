from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.dependencies import CurrentUser, DbSession, RegistryDep
from app.dto.game import (
    ArchiveOut,
    GameCreate,
    GameOpenOut,
    GameOut,
    SandboxStatusOut,
    TouchOut,
)
from app.errors import conflict, not_found, service_unavailable
from app.repositories import games
from app.runtime.sandboxes.errors import LockBusy, SandboxUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["游戏"])


@router.post("", response_model=GameOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreate,
    user: CurrentUser,
    session: DbSession,
) -> GameOut:
    game = await games.create(session, user_id=user.id, name=payload.name)
    await games.ensure_sandbox_row(session, game.id)
    return GameOut.model_validate(game)


@router.get("", response_model=list[GameOut])
async def list_games(user: CurrentUser, session: DbSession) -> list[GameOut]:
    rows = await games.list_owned(session, user.id)
    return [GameOut.model_validate(row) for row in rows]


@router.get("/{game_id}", response_model=SandboxStatusOut)
async def get_game(
    game_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> SandboxStatusOut:
    if await games.get_owned(session, game_id, user.id) is None:
        raise not_found()
    return SandboxStatusOut(**await registry.status(game_id))


@router.post("/{game_id}/open", response_model=GameOpenOut)
async def open_game(
    game_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> GameOpenOut:
    if await games.get_owned(session, game_id, user.id) is None:
        raise not_found()
    try:
        handle, urls = await registry.open_game(game_id)
    except SandboxUnavailable:
        raise service_unavailable() from None
    except LockBusy:
        raise conflict() from None
    return GameOpenOut(
        game_id=game_id,
        sandbox_id=handle.sandbox_id,
        game_url=urls.game_url,
        novnc_url=urls.novnc_url,
    )


@router.post("/{game_id}/touch", response_model=TouchOut)
async def touch_game(
    game_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> TouchOut:
    if await games.get_owned(session, game_id, user.id) is None:
        raise not_found()
    try:
        handle = await registry.touch(game_id)
    except SandboxUnavailable:
        raise service_unavailable() from None
    except LockBusy:
        raise conflict() from None
    return TouchOut(game_id=game_id, sandbox_id=handle.sandbox_id)


@router.post("/{game_id}/archive", response_model=ArchiveOut)
async def archive_game(
    game_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    force: bool = False,
) -> ArchiveOut:
    if await games.get_owned(session, game_id, user.id) is None:
        raise not_found()
    try:
        result = await registry.archive(game_id, force=force)
    except SandboxUnavailable:
        raise service_unavailable() from None
    except LockBusy:
        raise conflict() from None
    return ArchiveOut(**result)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> None:
    if await games.get_owned(session, game_id, user.id) is None:
        raise not_found()
    try:
        await registry.delete_game(game_id)
    except LockBusy:
        raise conflict() from None
