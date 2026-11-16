from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from app.repositories.conversation_store import PostgresConversationStore
from app.runtime.agent.deps import AgentDeps
from app.runtime.runs import hitl
from app.runtime.runs.manager import ActiveRun, RunManager
from app.runtime.sandboxes.errors import is_workspace_unavailable
from app.runtime.sandboxes.registry import SandboxHandle, SandboxRegistry

logger = logging.getLogger(__name__)


class AgentRunStream:
    """一次 Agent run 的流式生命周期：回调、取消、断开保存与收尾。"""

    def __init__(
        self,
        *,
        adapter: VercelAIAdapter[AgentDeps, str | DeferredToolRequests],
        store: PostgresConversationStore,
        registry: SandboxRegistry,
        run_manager: RunManager,
        active: ActiveRun,
        handle: SandboxHandle,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        deferred_results: DeferredToolResults | None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._run_manager = run_manager
        self._active = active
        self._handle = handle
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._stream = adapter.run_stream(
            conversation_id=str(conversation_id),
            deps=AgentDeps(
                user_id=user_id,
                conversation_id=str(conversation_id),
                approval_mode="auto",
            ),
            workspace=handle.ref,
            deferred_tool_results=deferred_results,
            on_complete=self._on_complete,
            on_cancel=self._on_cancel,
            cancellation_token=active.cancellation,
        )

    def aiter(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        try:
            async for chunk in self._stream:
                yield chunk
        except asyncio.CancelledError as error:
            self._active.cancelled = True
            cancelled = RunCancelled.from_cancellation(error)
            if cancelled is not None:
                self._active.usage = cancelled.usage
                # 断开时当前 task 已被取消，放到独立 task 里保存，避免 await 再次被打断。
                task = asyncio.create_task(self._save_cancelled(cancelled))
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    pass
            raise
        except BaseException as error:  # 记录后交给运行记录
            self._active.error = error
            if is_workspace_unavailable(error):
                await self._registry.mark_dead(self._handle.sandbox_id)
            raise
        finally:
            # 客户端断开或生成器被关闭时，确保底层 agent run 也被取消。
            if (
                self._active.result is None
                and self._active.error is None
                and not self._active.cancelled
            ):
                self._active.cancelled = True
                self._active.cancellation.cancel()

    async def _save_cancelled(self, cancelled: RunCancelled) -> None:
        await hitl.save_cancelled(
            self._store,
            conversation_id=self._conversation_id,
            scope=self._user_id,
            cancelled=cancelled,
        )

    async def _on_complete(self, result: AgentRunResult[Any]) -> None:
        self._active.result = result

    async def _on_cancel(self, cancelled: RunCancelled) -> None:
        self._active.cancelled = True
        self._active.usage = cancelled.usage
        await self._save_cancelled(cancelled)

    async def finalize(self) -> None:
        try:
            await self._registry.touch(self._handle.sandbox_id)
        except Exception:  # 收尾失败不影响运行记录
            logger.exception("更新沙箱 last_used_at 失败")
        await self._run_manager.finish(self._active)
