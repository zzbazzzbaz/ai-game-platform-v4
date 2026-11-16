from __future__ import annotations

import uuid
from typing import Any

from pydantic import TypeAdapter
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.conversation import ConversationDetailOut
from app.dto.run import RunOut
from app.repositories import conversations, runs
from app.repositories.conversation_store import PostgresConversationStore
from app.repositories.models import Conversation
from app.services.run_manager import RunManager
from app.services.sandbox_registry import SandboxRegistry

_usage_adapter = TypeAdapter(RunUsage)
_deferred_adapter = TypeAdapter(DeferredToolRequests)


class ConversationNotFoundError(Exception):
    """会话不存在或不属于当前用户。"""


class ConversationBusyError(Exception):
    """会话仍有运行中的回答。"""


class SandboxCleanupError(Exception):
    """删除会话时沙箱销毁失败。"""


async def list_conversations(session: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    return await conversations.list_owned(session, user_id)


async def create_conversation(session: AsyncSession, user_id: uuid.UUID) -> Conversation:
    return await conversations.create(session, user_id)


async def get_owned(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    row = await conversations.get_owned(session, conversation_id, user_id)
    if row is None:
        raise ConversationNotFoundError
    return row


async def get_detail(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    store: PostgresConversationStore,
) -> ConversationDetailOut:
    row = await get_owned(session, conversation_id, user_id)
    conversation = await store.load(str(conversation_id), scope=str(user_id))
    messages: list[dict[str, Any]] = (
        [
            message.model_dump(mode="json")
            for message in VercelAIAdapter.dump_messages(conversation.messages, sdk_version=6)
        ]
        if conversation is not None
        else []
    )
    usage: dict[str, Any] = (
        _usage_adapter.dump_python(conversation.usage, mode="json")
        if conversation is not None and conversation.usage is not None
        else {}
    )
    deferred: dict[str, Any] | None = (
        _deferred_adapter.dump_python(conversation.deferred_tool_requests, mode="json")
        if conversation is not None and conversation.deferred_tool_requests is not None
        else None
    )
    last_run = await runs.latest(session, conversation_id)
    return ConversationDetailOut(
        id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=messages,
        usage=usage,
        deferred_tool_requests=deferred,
        last_run=RunOut.model_validate(last_run) if last_run is not None else None,
    )


async def delete_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    store: PostgresConversationStore,
    registry: SandboxRegistry,
    run_manager: RunManager,
) -> None:
    await get_owned(session, conversation_id, user_id)
    if run_manager.active(conversation_id) is not None:
        raise ConversationBusyError

    handle = await registry.active_handle(conversation_id)
    if handle is not None:
        try:
            await registry.kill_checked(handle.sandbox_id)
        except Exception as error:  # 保留记录，交给下一次重试或回收
            raise SandboxCleanupError from error

    await store.delete(str(conversation_id), scope=str(user_id))
