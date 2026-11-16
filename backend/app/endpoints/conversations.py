from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.dependencies import (
    CurrentUser,
    DbSession,
    RunManagerDep,
    StoreDep,
)
from app.dto.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
)
from app.errors import conflict, not_found
from app.services import conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["会话"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser,
    session: DbSession,
) -> list[ConversationOut]:
    rows = await conversation_service.list_conversations(session, user.id)
    return [ConversationOut.model_validate(row) for row in rows]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user: CurrentUser,
    session: DbSession,
    payload: ConversationCreate | None = None,
) -> ConversationOut:
    payload = payload or ConversationCreate()
    try:
        row = await conversation_service.create_conversation(
            session,
            user.id,
            game_id=payload.game_id,
            name=payload.name,
        )
    except conversation_service.GameNotFoundError as error:
        logger.warning("创建会话失败：游戏不存在，game_id=%s", payload.game_id)
        raise not_found() from error
    return ConversationOut.model_validate(row)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    store: StoreDep,
) -> ConversationDetailOut:
    try:
        return await conversation_service.get_detail(
            session,
            conversation_id=conversation_id,
            user_id=user.id,
            store=store,
        )
    except conversation_service.ConversationNotFoundError as error:
        logger.warning(
            "读取会话失败：会话不存在，conversation_id=%s user_id=%s", conversation_id, user.id
        )
        raise not_found() from error


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    store: StoreDep,
    run_manager: RunManagerDep,
) -> None:
    try:
        await conversation_service.delete_conversation(
            session,
            conversation_id=conversation_id,
            user_id=user.id,
            store=store,
            run_manager=run_manager,
        )
    except conversation_service.ConversationNotFoundError as error:
        logger.warning(
            "删除会话失败：会话不存在，conversation_id=%s user_id=%s", conversation_id, user.id
        )
        raise not_found() from error
    except conversation_service.ConversationBusyError as error:
        logger.warning(
            "删除会话失败：会话正在运行，conversation_id=%s user_id=%s",
            conversation_id,
            user.id,
        )
        raise conflict() from error
