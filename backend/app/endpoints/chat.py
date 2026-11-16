from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import RunCancelled, UserError
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.usage import RunUsage
from starlette.background import BackgroundTask

from app.config import settings
from app.dependencies import (
    AgentFactoryDep,
    CurrentUser,
    DbSession,
    RegistryDep,
    RunManagerDep,
    StoreDep,
)
from app.dto.chat import CancelRunOut
from app.errors import bad_request, conflict, not_found, service_unavailable
from app.services import chat_service, conversation_service
from app.services.agent.deps import AgentDeps
from app.services.run_manager import RunBusy
from app.services.sandbox_registry import SandboxUnavailable

logger = logging.getLogger(__name__)
_usage_adapter = TypeAdapter(RunUsage)

router = APIRouter(tags=["对话"])


@router.post("/chat")
async def chat(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    store: StoreDep,
    registry: RegistryDep,
    run_manager: RunManagerDep,
    agent_factory: AgentFactoryDep,
):
    try:
        body = await request.json()
    except ValueError:
        logger.warning("聊天请求体不是合法 JSON")
        raise bad_request() from None

    conversation_id_raw = body.get("id") if isinstance(body, dict) else None
    try:
        conversation_id = uuid.UUID(str(conversation_id_raw))
    except (ValueError, TypeError):
        logger.warning("聊天请求缺少合法的 conversation id：%r", conversation_id_raw)
        raise bad_request() from None

    try:
        conversation = await conversation_service.get_owned(session, conversation_id, user.id)
    except conversation_service.ConversationNotFoundError as error:
        logger.warning(
            "聊天会话不存在：conversation_id=%s user_id=%s", conversation_id, user.id
        )
        raise not_found() from error

    agent = agent_factory.build()
    try:
        adapter = await VercelAIAdapter[AgentDeps, str | DeferredToolRequests].from_request(
            request,
            agent=agent,
            sdk_version=6,
            conversation_store=store,
            conversation_scope=str(user.id),
        )
    except (ValidationError, UserError) as error:
        logger.warning("消息格式不合法：conversation_id=%s error=%s", conversation_id, error)
        raise bad_request() from error

    try:
        deferred_results = adapter.deferred_tool_results
    except UserError as error:
        logger.warning(
            "解析 deferred tool results 失败：conversation_id=%s error=%s",
            conversation_id,
            error,
        )
        raise bad_request() from error
    deferred_results = await chat_service.normalize_deferred_results(
        store,
        conversation_id=conversation_id,
        scope=user.id,
        deferred_results=deferred_results,
    )

    await chat_service.apply_title(session, conversation, chat_service.first_user_text(body))

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
        logger.warning(
            "会话已有运行中的回答：conversation_id=%s user_id=%s", conversation_id, user.id
        )
        raise conflict() from None

    async def save_cancelled(cancelled: RunCancelled) -> None:
        await chat_service.save_cancelled(
            store,
            conversation_id=conversation_id,
            scope=user.id,
            cancelled=cancelled,
        )

    async def finalize() -> None:
        try:
            await registry.touch(handle.sandbox_id)
        except Exception:  # 收尾失败不影响运行记录
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
            except BaseException as error:  # 记录后交给运行记录
                active.error = error
                if chat_service.workspace_unavailable(error):
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
        logger.warning("沙箱不可用：conversation_id=%s error=%s", conversation_id, error)
        active.error = error
        await run_manager.finish(active)
        raise service_unavailable() from error
    except BaseException:
        await run_manager.finish(active)
        raise


@router.post(
    "/conversations/{conversation_id}/cancel",
    response_model=CancelRunOut,
)
async def cancel_run(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    run_manager: RunManagerDep,
) -> CancelRunOut:
    try:
        conversation = await conversation_service.get_owned(session, conversation_id, user.id)
    except conversation_service.ConversationNotFoundError as error:
        logger.warning(
            "取消运行时会话不存在：conversation_id=%s user_id=%s", conversation_id, user.id
        )
        raise not_found() from error

    run_id = await chat_service.cancel_waiting(session, conversation, run_manager)
    if run_id is None:
        logger.warning("取消运行失败：没有运行中的回答，conversation_id=%s", conversation_id)
        raise conflict()
    return CancelRunOut(run_id=run_id)
