from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.background import BackgroundTask
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic_ai import AgentRunResult, Conversation as AgentConversation
from pydantic_ai.workspaces import WorkspaceUnavailableError
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from app.agent.deps import AgentDeps
from app.agent.factory import AgentFactory
from app.api.deps import get_agent_factory, get_registry, get_run_manager, get_store
from app.auth.deps import current_user
from app.config import settings
from app.db import get_session
from app.models import Conversation, User
from app.runtime.runs import RunBusy, RunManager
from app.runtime.sandboxes import SandboxRegistry, SandboxUnavailable
from app.store.conversations import PostgresConversationStore

logger = logging.getLogger(__name__)

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

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    try:
        active = await run_manager.start(
            user_id=user.id, conversation_id=conversation_id, model=settings.model
        )
    except RunBusy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该会话正在运行，请等待当前回答结束"
        ) from None

    try:
        handle = await registry.ensure(user.id, conversation_id)
    except SandboxUnavailable as error:
        active.error = error
        await run_manager.finish(active)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error

    agent = agent_factory.build()
    deps = AgentDeps(
        user_id=user.id,
        conversation_id=str(conversation_id),
        sandbox_ref=handle.ref,
        approval_mode="auto",
    )

    try:
        adapter = await VercelAIAdapter.from_request(
            request,
            agent=agent,
            sdk_version=6,
            conversation_store=store,
            conversation_scope=str(user.id),
        )
    except ValidationError as error:
        active.error = error
        await run_manager.finish(active)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="消息格式不合法"
        ) from error

    title_text = _first_user_text(body)
    if title_text and conversation.title == "新会话":
        conversation.title = title_text[:40]
        await session.commit()

    async def on_complete(result: AgentRunResult[Any]) -> None:
        active.result = result
        await registry.touch(handle.sandbox_id)
        await run_manager.finish(active)

    async def on_cancel(cancelled: RunCancelled) -> None:
        active.cancelled = True
        active.usage = cancelled.usage
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
        await registry.touch(handle.sandbox_id)
        await run_manager.finish(active)

    stream = adapter.run_stream(
        conversation_id=str(conversation_id),
        deps=deps,
        on_complete=on_complete,
        on_cancel=on_cancel,
        cancellation_token=active.cancellation,
    )

    async def finalize() -> None:
        try:
            await registry.touch(handle.sandbox_id)
        except Exception:  # noqa: BLE001 - 收尾失败不影响运行记录
            logger.exception("更新沙箱 last_used_at 失败")
        await run_manager.finish(active)

    async def wrapped_stream():
        try:
            async for chunk in stream:
                yield chunk
        except asyncio.CancelledError:
            active.cancelled = True
            raise
        except BaseException as error:  # noqa: BLE001 - 记录后交给运行记录
            active.error = error
            if _workspace_unavailable(error):
                await registry.mark_dead(handle.sandbox_id)
            raise
        finally:
            await finalize()

    response = adapter.streaming_response(wrapped_stream())
    # 客户端提前断开时生成器的 finally 可能来不及执行，用响应后台任务兜底收尾。
    response.background = BackgroundTask(finalize)
    return response


@router.post("/conversations/{conversation_id}/cancel")
async def cancel_run(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    run_manager: Annotated[RunManager, Depends(get_run_manager)],
) -> dict[str, str]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    run_id = await run_manager.cancel(conversation_id)
    if run_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有运行中的回答")
    return {"run_id": str(run_id)}
