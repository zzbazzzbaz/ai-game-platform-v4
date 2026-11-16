from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import e2b
from pydantic_ai.workspaces import WorkspaceRef
from pydantic_ai_harness.e2b_sandbox import E2BSandboxBackend
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.repositories.models import SandboxSession
from app.runtime.sandboxes.errors import SandboxUnavailable


@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str

    @property
    def ref(self) -> WorkspaceRef:
        return WorkspaceRef(provider="e2b", id=self.sandbox_id)


def create_e2b_client() -> e2b.E2B:
    return e2b.E2B(
        api_key=settings.e2b_api_key or None,
        api_url=settings.e2b_api_url or None,
        domain=settings.e2b_domain or None,
    )


class SandboxRegistry:
    """把 conversation 与阿里云沙箱实例的映射落到 `sandbox_sessions`。"""

    def __init__(self, client: e2b.E2B, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._client = client
        self._sessions = session_factory

    async def ensure(self, conversation_id: uuid.UUID) -> SandboxHandle:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SandboxSession).where(SandboxSession.conversation_id == conversation_id)
            )
        if row is not None:
            await self.touch(row.sandbox_id)
            return SandboxHandle(row.sandbox_id)

        template = settings.e2b_template or None
        try:
            sandbox = await self._client.AsyncSandbox.create(
                template=template,
                timeout=settings.sandbox_timeout,
                lifecycle={"on_timeout": "pause", "auto_resume": True},
            )
        except Exception as error:  # 统一转成 503
            raise SandboxUnavailable(f"创建沙箱失败：{error}") from error

        async with self._sessions() as session:
            session.add(
                SandboxSession(
                    conversation_id=conversation_id,
                    sandbox_id=sandbox.sandbox_id,
                    last_used_at=datetime.now(UTC),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # 并发创建时另一个请求已登记，弃用刚创建的实例并复用既有记录。
                await session.rollback()
                await self._kill_quietly(sandbox.sandbox_id)
                existing = await session.scalar(
                    select(SandboxSession).where(
                        SandboxSession.conversation_id == conversation_id
                    )
                )
                if existing is None:
                    raise SandboxUnavailable("沙箱登记冲突。") from None
                return SandboxHandle(existing.sandbox_id)
        return SandboxHandle(sandbox.sandbox_id)

    async def touch(self, sandbox_id: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(SandboxSession)
                .where(SandboxSession.sandbox_id == sandbox_id)
                .values(last_used_at=datetime.now(UTC))
            )
            await session.commit()

    async def mark_dead(self, sandbox_id: str) -> None:
        """删除映射，下一次 run 重新创建沙箱。"""
        async with self._sessions() as session:
            await session.execute(
                delete(SandboxSession).where(SandboxSession.sandbox_id == sandbox_id)
            )
            await session.commit()

    async def active_handle(self, conversation_id: uuid.UUID) -> SandboxHandle | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SandboxSession).where(SandboxSession.conversation_id == conversation_id)
            )
        if row is None:
            return None
        return SandboxHandle(row.sandbox_id)

    def backend(self, handle: SandboxHandle) -> E2BSandboxBackend:
        return E2BSandboxBackend(client=self._client, ref=handle.ref)

    async def kill_checked(self, sandbox_id: str) -> None:
        """回收时使用：让调用方知道失败，保留记录下次重试。"""
        await self._client.AsyncSandbox.kill(sandbox_id)

    async def preview_host(self, handle: SandboxHandle, port: int) -> str:
        try:
            sandbox = await self._client.AsyncSandbox.connect(
                handle.sandbox_id,
                timeout=settings.sandbox_timeout,
            )
            host = sandbox.get_host(port)
        except Exception as error:  # 统一转成 503
            raise SandboxUnavailable(f"获取预览地址失败：{error}") from error
        return host if host.startswith("http") else f"https://{host}"

    async def _kill_quietly(self, sandbox_id: str) -> None:
        try:
            await self._client.AsyncSandbox.kill(sandbox_id)
        except Exception:  # noqa: BLE001, S110 - 回收失败保持静默
            pass
