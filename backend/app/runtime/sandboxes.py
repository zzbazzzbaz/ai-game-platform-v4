from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import e2b
from pydantic_ai.workspaces import WorkspaceRef
from pydantic_ai_harness.e2b_sandbox import E2BSandboxBackend
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models import SandboxSession


class SandboxUnavailable(RuntimeError):
    """沙箱创建或连接失败。"""


@dataclass(frozen=True)
class SandboxHandle:
    id: uuid.UUID
    sandbox_id: str
    template: str

    @property
    def ref(self) -> WorkspaceRef:
        return WorkspaceRef(provider="e2b", id=self.sandbox_id)


def create_e2b_client() -> e2b.E2B:
    options: dict[str, object] = {}
    if settings.e2b_api_key:
        options["api_key"] = settings.e2b_api_key
    if settings.e2b_api_url:
        options["api_url"] = settings.e2b_api_url
    if settings.e2b_domain:
        options["domain"] = settings.e2b_domain
    return e2b.E2B(**options)  # type: ignore[arg-type]


class SandboxRegistry:
    """把 conversation 与阿里云沙箱实例的映射落到 `sandbox_sessions`。"""

    def __init__(self, client: e2b.E2B, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._client = client
        self._sessions = session_factory

    async def ensure(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> SandboxHandle:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SandboxSession).where(
                    SandboxSession.conversation_id == conversation_id,
                    SandboxSession.status == "active",
                )
            )
        if row is not None:
            await self.touch(row.sandbox_id)
            return SandboxHandle(id=row.id, sandbox_id=row.sandbox_id, template=row.template)

        template = settings.e2b_template or None
        try:
            sandbox = await self._client.AsyncSandbox.create(
                template=template,
                timeout=settings.sandbox_timeout,
                lifecycle={"on_timeout": "pause"},
            )
        except Exception as error:  # noqa: BLE001 - 统一转成 503
            raise SandboxUnavailable(f"创建沙箱失败：{error}") from error

        expires_at = datetime.now(UTC) + timedelta(seconds=settings.sandbox_timeout)
        async with self._sessions() as session:
            record = SandboxSession(
                user_id=user_id,
                conversation_id=conversation_id,
                provider="e2b",
                sandbox_id=sandbox.sandbox_id,
                template=template or "",
                status="active",
                last_used_at=datetime.now(UTC),
                expires_at=expires_at,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                # 并发创建时另一个请求已登记，弃用刚创建的实例并复用既有记录。
                await session.rollback()
                await self._kill_quietly(sandbox.sandbox_id)
                existing = await session.scalar(
                    select(SandboxSession).where(
                        SandboxSession.conversation_id == conversation_id,
                        SandboxSession.status == "active",
                    )
                )
                if existing is None:
                    raise SandboxUnavailable("沙箱登记冲突。") from None
                return SandboxHandle(
                    id=existing.id, sandbox_id=existing.sandbox_id, template=existing.template
                )
            await session.refresh(record)
        return SandboxHandle(id=record.id, sandbox_id=record.sandbox_id, template=record.template)

    async def touch(self, sandbox_id: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(SandboxSession)
                .where(SandboxSession.sandbox_id == sandbox_id, SandboxSession.status == "active")
                .values(last_used_at=datetime.now(UTC))
            )
            await session.commit()

    async def mark_dead(self, sandbox_id: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(SandboxSession).where(SandboxSession.sandbox_id == sandbox_id).values(status="dead")
            )
            await session.commit()

    async def active_handle(self, conversation_id: uuid.UUID) -> SandboxHandle | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SandboxSession).where(
                    SandboxSession.conversation_id == conversation_id,
                    SandboxSession.status == "active",
                )
            )
        if row is None:
            return None
        return SandboxHandle(id=row.id, sandbox_id=row.sandbox_id, template=row.template)

    def backend(self, handle: SandboxHandle) -> E2BSandboxBackend:
        return E2BSandboxBackend(
            client=self._client,
            ref=handle.ref,
            template=handle.template or None,
        )

    async def kill(self, handle: SandboxHandle) -> None:
        await self._kill_quietly(handle.sandbox_id)

    async def kill_checked(self, sandbox_id: str) -> None:
        """回收时使用：让调用方知道失败，保留记录下次重试。"""
        await self._client.AsyncSandbox.kill(sandbox_id)

    async def preview_host(self, handle: SandboxHandle, port: int) -> str:
        try:
            sandbox = await self._client.AsyncSandbox.connect(handle.sandbox_id)
            host = sandbox.get_host(port)
        except Exception as error:  # noqa: BLE001
            raise SandboxUnavailable(f"获取预览地址失败：{error}") from error
        return host if host.startswith("http") else f"https://{host}"

    async def _kill_quietly(self, sandbox_id: str) -> None:
        try:
            await self._client.AsyncSandbox.kill(sandbox_id)
        except Exception:  # noqa: BLE001
            pass
