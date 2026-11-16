from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import Conversation as AgentConversation
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.workspaces import WorkspaceUnavailableError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import runs
from app.repositories.conversation_store import PostgresConversationStore
from app.repositories.models import Conversation
from app.services.run_manager import RunManager

logger = logging.getLogger(__name__)


def first_user_text(body: dict[str, Any]) -> str | None:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        for part in message.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                return str(part["text"]).strip()
    return None


def workspace_unavailable(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, WorkspaceUnavailableError):
            return True
        current = current.__cause__
    return False


async def apply_title(
    session: AsyncSession,
    conversation: Conversation,
    text: str | None,
) -> None:
    if not text or conversation.title != "新会话":
        return
    conversation.title = text[:40]
    conversation.updated_at = datetime.now(UTC)
    await session.commit()


async def normalize_deferred_results(
    store: PostgresConversationStore,
    *,
    conversation_id: uuid.UUID,
    scope: uuid.UUID,
    deferred_results: DeferredToolResults | None,
) -> DeferredToolResults | None:
    if deferred_results is None:
        return None
    pending = await store.load(str(conversation_id), scope=str(scope))
    metadata = (
        pending.deferred_tool_requests.metadata
        if pending is not None and pending.deferred_tool_requests is not None
        else {}
    )
    return DeferredToolResults(
        approvals=deferred_results.approvals,
        metadata={**metadata, **deferred_results.metadata},
        answered_by={tool_call_id: str(scope) for tool_call_id in deferred_results.approvals},
    )


async def save_cancelled(
    store: PostgresConversationStore,
    *,
    conversation_id: uuid.UUID,
    scope: uuid.UUID,
    cancelled: RunCancelled,
) -> None:
    try:
        loaded = await store.load(str(conversation_id), scope=str(scope))
        conversation = AgentConversation(
            messages=list(cancelled.all_messages()),
            usage=cancelled.usage,
            conversation_id=str(conversation_id),
            revision=loaded.revision if loaded is not None else None,
        )
        await store.save(conversation, scope=str(scope))
    except Exception:  # 取消时保存失败不应吞掉取消本身
        logger.exception("保存取消时的会话失败")


async def cancel_waiting(
    session: AsyncSession,
    conversation: Conversation,
    run_manager: RunManager,
) -> uuid.UUID | None:
    run_id = await run_manager.cancel(conversation.id)
    if run_id is not None:
        return run_id

    waiting = await runs.latest_waiting(session, conversation.id)
    if waiting is None:
        return None
    waiting.status = "cancelled"
    waiting.finished_at = datetime.now(UTC)
    conversation.deferred_tool_requests = None
    await session.commit()
    return waiting.id
