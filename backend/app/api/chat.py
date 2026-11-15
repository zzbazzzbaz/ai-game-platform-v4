from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import AgentRunResult, Conversation as AgentConversation
from pydantic_ai.exceptions import RunCancelled, UserError
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.usage import RunUsage
from pydantic_ai.workspaces import WorkspaceUnavailableError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.agent.deps import AgentDeps
from app.agent.factory import AgentFactory
from app.api.deps import get_agent_factory, get_registry, get_run_manager, get_store, owned_conversation
from app.auth.deps import current_user
from app.config import settings
from app.db import get_session
from app.models import Conversation, Run, User
from app.runtime.runs import RunBusy, RunManager
from app.runtime.sandboxes import SandboxRegistry, SandboxUnavailable
from app.store.conversations import PostgresConversationStore

logger = logging.getLogger(__name__)
_usage_adapter = TypeAdapter(RunUsage)

router = APIRouter(prefix="/api", tags=["chat"])


def _workspace_unavailable(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, WorkspaceUnavailableError):
            return True
        current = current.__cause__
    return False


def _first_user_text(body: dict[str, Any]) -> str | None:
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


@router.post("/chat")
async def chat(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[PostgresConversationStore, Depends(get_store)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
    run_manager: Annotated[RunManager, Depends(get_run_manager)],
    agent_factory: Annotated[AgentFactory, Depends(get_agent_factory)],
):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请求体不是合法 JSON") from None

    conversation_id_raw = body.get("id") if isinstance(body, dict) else None
    try:
        conversation_id = uuid.UUID(str(conversation_id_raw))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="缺少合法的 conversation id"
        ) from None

    conversation = await owned_conversation(conversation_id, user, session)

    agent = agent_factory.build()
    try:
        adapter = await VercelAIAdapter.from_request(
            request,
            agent=agent,
            sdk_version=6,
            conversation_store=store,
            conversation_scope=str(user.id),
        )
    except (ValidationError, UserError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="消息格式不合法"
        ) from error

    try:
        deferred_results = adapter.deferred_tool_results
    except UserError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    if deferred_results is not None:
        pending = await store.load(str(conversation_id), scope=str(user.id))
        metadata = (pending.deferred_tool_requests.metadata if pending and pending.deferred_tool_requests else {})
        deferred_results = DeferredToolResults(
            approvals=deferred_results.approvals,
            metadata={**metadata, **deferred_results.metadata},
            answered_by={tool_call_id: str(user.id) for tool_call_id in deferred_results.approvals},
        )

    title_text = _first_user_text(body)
    if title_text and conversation.title == "新会话":
        conversation.title = title_text[:40]
        conversation.updated_at = datetime.now(UTC)
        await session.commit()

    usage_baseline = _usage_adapter.validate_python(conversation.usage or {})
    try:
        active = await run_manager.start(
            conversation_id=conversation_id,
            user_id=user.id,
            model=settings.model,
            resuming=deferred_results is not None,
            usage_baseline=usage_baseline,
        )
    except RunBusy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该会话正在运行，请等待当前回答结束"
        ) from None

    async def save_cancelled(cancelled: RunCancelled) -> None:
        try:
            loaded = await store.load(str(conversation_id), scope=str(user.id))
            cancelled_conversation = AgentConversation(
                messages=list(cancelled.all_messages()),
                usage=cancelled.usage,
                conversation_id=str(conversation_id),
                revision=loaded.revision if loaded is not None else None,
            )
            await store.save(cancelled_conversation, scope=str(user.id))
        except Exception:  # noqa: BLE001 - 取消时保存失败不应吞掉取消本身
            logger.exception("保存取消时的会话失败")

    async def finalize() -> None:
        try:
            await registry.touch(handle.sandbox_id)
        except Exception:  # noqa: BLE001 - 收尾失败不影响运行记录
            logger.exception("更新沙箱 last_used_at 失败")
        await run_manager.finish(active)

    try:
        handle = await registry.ensure(user.id, conversation_id)

        async def on_complete(result: AgentRunResult[Any]) -> None:
            active.result = result

        async def on_cancel(cancelled: RunCancelled) -> None:
            active.cancelled = True
            active.usage = cancelled.usage
            await save_cancelled(cancelled)

        stream = adapter.run_stream(
            conversation_id=str(conversation_id),
            deps=AgentDeps(
                user_id=user.id,
                conversation_id=str(conversation_id),
                sandbox_ref=handle.ref,
                approval_mode="auto",
            ),
            deferred_tool_results=deferred_results,
            on_complete=on_complete,
            on_cancel=on_cancel,
            cancellation_token=active.cancellation,
        )

        async def wrapped_stream():
            try:
                async for chunk in stream:
                    yield chunk
            except asyncio.CancelledError as error:
                active.cancelled = True
                cancelled = RunCancelled.from_cancellation(error)
                if cancelled is not None:
                    active.usage = cancelled.usage
                    # 断开时当前 task 已被取消，放到独立 task 里保存，避免 await 再次被打断。
                    task = asyncio.create_task(save_cancelled(cancelled))
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        pass
                raise
            except BaseException as error:  # noqa: BLE001 - 记录后交给运行记录
                active.error = error
                if _workspace_unavailable(error):
                    await registry.mark_dead(handle.sandbox_id)
                raise
            finally:
                # 客户端断开或生成器被关闭时，确保底层 agent run 也被取消。
                if active.result is None and active.error is None and not active.cancelled:
                    active.cancelled = True
                    active.cancellation.cancel()

        response = adapter.streaming_response(wrapped_stream())
        # 客户端提前断开时生成器不一定收尾，用响应后台任务兜底释放运行锁。
        response.background = BackgroundTask(finalize)
        return response
    except SandboxUnavailable as error:
        active.error = error
        await run_manager.finish(active)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    except BaseException:
        await run_manager.finish(active)
        raise


@router.post("/conversations/{conversation_id}/cancel")
async def cancel_run(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    run_manager: Annotated[RunManager, Depends(get_run_manager)],
) -> dict[str, str]:
    conversation = await owned_conversation(conversation_id, user, session)

    run_id = await run_manager.cancel(conversation_id)
    if run_id is not None:
        return {"run_id": str(run_id)}

    waiting = await session.scalar(
        select(Run)
        .where(Run.conversation_id == conversation_id, Run.status == "waiting_approval")
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    if waiting is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有运行中的回答")
    waiting.status = "cancelled"
    waiting.finished_at = datetime.now(UTC)
    conversation.deferred_tool_requests = None
    await session.commit()
    return {"run_id": str(waiting.id)}
