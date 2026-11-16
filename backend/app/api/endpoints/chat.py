from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import RunCancelled, UserError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.usage import RunUsage
from starlette.background import BackgroundTask

from app.agent.deps import AgentDeps
from app.api.dependencies import (
    AgentFactoryDep,
    CurrentUser,
    DbSession,
    RegistryDep,
    RunManagerDep,
    StoreDep,
)
from app.api.services import chat_service, conversation_service
from app.api.services.run_manager import RunBusy
from app.api.services.sandbox_registry import SandboxUnavailable
from app.shared.config import settings
from app.shared.dto.chat import CancelRunOut
from app.shared.errors import bad_request, conflict, not_found, service_unavailable

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
        raise bad_request("请求体不是合法 JSON") from None

    conversation_id_raw = body.get("id") if isinstance(body, dict) else None
    try:
        conversation_id = uuid.UUID(str(conversation_id_raw))
    except (ValueError, TypeError):
        raise bad_request("缺少合法的 conversation id") from None

    try:
        conversation = await conversation_service.get_owned(session, conversation_id, user.id)
    except conversation_service.ConversationNotFoundError as error:
        raise not_found("会话不存在") from error

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
        raise bad_request("消息格式不合法") from error

    try:
        deferred_results = adapter.deferred_tool_results
    except UserError as error:
        raise bad_request(str(error)) from error
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
        raise conflict("该会话正在运行，请等待当前回答结束") from None

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
        active.error = error
        await run_manager.finish(active)
        raise service_unavailable(str(error)) from error
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
        raise not_found("会话不存在") from error

    run_id = await chat_service.cancel_waiting(session, conversation, run_manager)
    if run_id is None:
        raise conflict("当前没有运行中的回答")
    return CancelRunOut(run_id=run_id)
