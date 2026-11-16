from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import TypeAdapter, ValidationError
from pydantic_ai.exceptions import UserError
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
from app.runtime.agent.deps import AgentDeps
from app.runtime.runs import hitl
from app.runtime.runs.manager import RunBusy
from app.runtime.runs.stream import AgentRunStream
from app.runtime.sandboxes.errors import SandboxUnavailable
from app.services import conversation_service

logger = logging.getLogger(__name__)
_usage_adapter = TypeAdapter(RunUsage)

router = APIRouter(tags=["对话"])


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
    deferred_results = await hitl.normalize_deferred_results(
        store,
        conversation_id=conversation_id,
        scope=user.id,
        deferred_results=deferred_results,
    )

    await conversation_service.apply_title(
        session, conversation, _first_user_text(body)
    )

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

    try:
        handle = await registry.ensure(conversation.game_id)
        stream = AgentRunStream(
            adapter=adapter,
            store=store,
            registry=registry,
            run_manager=run_manager,
            active=active,
            handle=handle,
            conversation_id=conversation_id,
            user_id=user.id,
            deferred_results=deferred_results,
        )
        response = adapter.streaming_response(stream.aiter())
        # 客户端提前断开时生成器不一定收尾，用响应后台任务兜底释放运行锁。
        response.background = BackgroundTask(stream.finalize)
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

    run_id = await hitl.cancel_waiting(session, conversation, run_manager)
    if run_id is None:
        logger.warning("取消运行失败：没有运行中的回答，conversation_id=%s", conversation_id)
        raise conflict()
    return CancelRunOut(run_id=run_id)
