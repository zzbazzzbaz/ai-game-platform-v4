from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pydantic_ai import Conversation as AgentConversation
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.tools import DeferredToolResults
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import runs
from app.repositories.conversation_store import PostgresConversationStore
from app.repositories.models import Conversation
from app.runtime.runs.manager import RunManager

logger = logging.getLogger(__name__)


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
