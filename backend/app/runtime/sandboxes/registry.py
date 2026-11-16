from __future__ import annotations

import asyncio
import logging
import shlex
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import e2b
from e2b import SandboxQuery, SandboxState
from pydantic_ai.workspaces import WorkspaceRef
from pydantic_ai_harness.e2b_sandbox import E2BSandboxBackend
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.repositories import games as game_repo
from app.repositories.models import Game, SandboxSession
from app.runtime.sandboxes.errors import LockBusy, SandboxUnavailable
from app.runtime.sandboxes.locks import advisory_lock
from app.runtime.sandboxes.snapshots import SnapshotStore

logger = logging.getLogger(__name__)

APP_METADATA = "ai-game-platform-v4"
TAR_PATH = "/tmp/workspace.tar.gz"

# 不进入快照的内容：依赖、构建产物、运行日志、素材、密钥和 agent 临时状态。
ARCHIVE_EXCLUDES = (
    "node_modules",
    ".runtime",
    "dist",
    "input",
    ".git",
    ".env",
    ".cache",
    "__pycache__",
    ".pydantic-ai-harness",
)

GAME_SERVER_ENSURE_COMMAND = """
cd /home/user/workspace
mkdir -p .runtime
if ! pgrep -f "[d]ev.mjs" >/dev/null; then
  nohup npm run dev > .runtime/server.log 2>&1 &
  sleep 4
fi
tail -n 20 .runtime/server.log 2>/dev/null || true
"""


@dataclass(frozen=True)
class SandboxHandle:
    game_id: uuid.UUID
    sandbox_id: str

    @property
    def ref(self) -> WorkspaceRef:
        return WorkspaceRef(provider="e2b", id=self.sandbox_id)


@dataclass(frozen=True)
class GameUrls:
    game_url: str
    novnc_url: str


def create_e2b_client() -> e2b.E2B:
    return e2b.E2B(
        api_key=settings.e2b_api_key or None,
        api_url=settings.e2b_api_url or None,
        domain=settings.e2b_domain or None,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _is_paused(info: Any) -> bool:
    return info.state == SandboxState.PAUSED


class SandboxRegistry:
    """按 game 管理阿里云沙箱：创建、续签、归档到 OSS、从 OSS 恢复。"""

    def __init__(
        self,
        client: e2b.E2B,
        snapshots: SnapshotStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._client = client
        self._snapshots = snapshots
        self._sessions = session_factory

    # ---------- 对外入口 ----------

    async def ensure(self, game_id: uuid.UUID) -> SandboxHandle:
        async with advisory_lock(f"sandbox:{game_id}", wait_seconds=60):
            async with self._sessions() as session:
                row = await game_repo.ensure_sandbox_row(session, game_id)
            if row.lifecycle_state in {"archiving", "restoring"}:
                return await self._recover_locked(game_id, row)
            if row.lifecycle_state == "archived" or not row.sandbox_id:
                return await self._restore_locked(game_id, row)
            try:
                sandbox = await self._connect(row.sandbox_id)
            except e2b.SandboxNotFoundException:
                logger.warning("沙箱 %s 已不存在，准备从快照恢复", row.sandbox_id)
                return await self._restore_locked(game_id, row)
            except Exception as error:
                raise SandboxUnavailable(f"连接沙箱失败：{error}") from error
            await self._mark_used(game_id)
            return SandboxHandle(game_id, sandbox.sandbox_id)

    async def touch(self, game_id: uuid.UUID) -> SandboxHandle:
        handle = await self.ensure(game_id)
        await self._mark_used(game_id)
        return handle

    async def open_game(self, game_id: uuid.UUID) -> tuple[SandboxHandle, GameUrls]:
        handle = await self.ensure(game_id)
        sandbox = await self._connect(handle.sandbox_id)
        await self._prepare_workspace(sandbox)
        await self._start_display_services(sandbox)
        await self._start_game_server(sandbox)
        await self._wait_game_ready(sandbox)
        urls = await self._preview_urls(sandbox)
        return handle, urls

    async def status(self, game_id: uuid.UUID) -> dict[str, Any]:
        async with self._sessions() as session:
            row = await game_repo.get_sandbox(session, game_id)
        if row is None:
            return {"lifecycle_state": "missing", "sandbox_id": None, "platform_state": None}
        platform_state = None
        end_at = None
        if row.sandbox_id:
            try:
                info = await self._client.AsyncSandbox.get_info(row.sandbox_id)
                platform_state = info.state.value
                end_at = info.end_at.isoformat() if info.end_at else None
            except e2b.SandboxNotFoundException:
                platform_state = "missing"
            except Exception as error:  # noqa: BLE001 - 查询失败不改变本地状态
                logger.warning("查询沙箱 %s 状态失败：%s", row.sandbox_id, error)
        return {
            "lifecycle_state": row.lifecycle_state,
            "sandbox_id": row.sandbox_id,
            "platform_state": platform_state,
            "end_at": end_at,
            "snapshot_key": row.snapshot_key,
            "snapshot_at": row.snapshot_at.isoformat() if row.snapshot_at else None,
            "snapshot_bytes": row.snapshot_bytes,
            "snapshot_sha256": row.snapshot_sha256,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "archive_retry_at": (
                row.archive_retry_at.isoformat() if row.archive_retry_at else None
            ),
            "archive_attempts": row.archive_attempts,
            "last_error": row.last_error,
        }

    async def archive(self, game_id: uuid.UUID, *, force: bool = False) -> dict[str, Any]:
        try:
            async with advisory_lock(f"sandbox:{game_id}", wait_seconds=0):
                return await self._archive_locked(game_id, force=force)
        except LockBusy as error:
            raise LockBusy("工作区正在被其他操作占用") from error

    async def archive_due(self) -> dict[str, int]:
        """扫描暂停沙盒，归档暂停超过阈值的实例。"""
        scanned = 0
        archived = 0
        skipped = 0
        failed = 0
        try:
            paginator = self._client.AsyncSandbox.list(
                query=SandboxQuery(
                    metadata={"app": APP_METADATA},
                    state=[SandboxState.PAUSED],
                )
            )
            while paginator.has_next:
                for info in await paginator.next_items():
                    scanned += 1
                    game_id = self._game_id_from_metadata(info.metadata)
                    if game_id is None:
                        skipped += 1
                        continue
                    if not self._paused_long_enough(info):
                        skipped += 1
                        continue
                    try:
                        result = await self.archive(game_id, force=False)
                    except LockBusy:
                        skipped += 1
                        continue
                    except Exception:
                        failed += 1
                        logger.exception("归档沙盒失败 game=%s", game_id)
                        continue
                    if result.get("status") == "archived":
                        archived += 1
                    else:
                        skipped += 1
        except Exception:
            logger.exception("扫描暂停沙盒失败，回退到数据库扫描")
            scanned, archived, skipped, failed = await self._archive_from_db(
                scanned, archived, skipped, failed
            )
        scanned, archived, skipped, failed = await self._archive_retries(
            scanned, archived, skipped, failed
        )
        return {
            "scanned": scanned,
            "archived": archived,
            "skipped": skipped,
            "failed": failed,
        }

    async def delete_game(self, game_id: uuid.UUID) -> None:
        async with advisory_lock(f"sandbox:{game_id}", wait_seconds=30):
            async with self._sessions() as session:
                row = await game_repo.get_sandbox(session, game_id)
            if row is not None and row.sandbox_id:
                await self._safe_kill(row.sandbox_id)
            await self._snapshots.delete_prefix(game_id)
            async with self._sessions() as session:
                await session.execute(
                    delete(Game).where(Game.id == game_id)
                )
                await session.commit()

    # ---------- 恢复与创建 ----------

    async def _recover_locked(
        self, game_id: uuid.UUID, row: SandboxSession
    ) -> SandboxHandle:
        """处理进程崩溃后遗留的 archiving / restoring 状态。"""
        if row.sandbox_id:
            try:
                sandbox = await self._connect(row.sandbox_id)
            except e2b.SandboxNotFoundException:
                pass
            except Exception as error:
                raise SandboxUnavailable(f"恢复遗留状态失败：{error}") from error
            else:
                await self._set_state(game_id, "active", last_error=None)
                await self._mark_used(game_id)
                return SandboxHandle(game_id, sandbox.sandbox_id)
        if row.snapshot_key:
            return await self._restore_locked(game_id, row)
        await self._set_state(game_id, "active", sandbox_id=None, last_error=None)
        return await self._restore_locked(game_id, row)

    async def _restore_locked(
        self, game_id: uuid.UUID, row: SandboxSession
    ) -> SandboxHandle:
        await self._set_state(game_id, "restoring")
        sandbox = None
        try:
            sandbox = await self._create_sandbox(game_id)
            if row.snapshot_key:
                await self._download_snapshot(sandbox, row.snapshot_key, row.snapshot_sha256)
            else:
                await self._prepare_workspace(sandbox)
            await self._start_display_services(sandbox)
            await self._set_state(
                game_id,
                "active",
                sandbox_id=sandbox.sandbox_id,
                last_used_at=_now(),
                archive_retry_at=None,
                last_error=None,
            )
            logger.info("沙箱已就绪 game=%s sandbox=%s", game_id, sandbox.sandbox_id)
            return SandboxHandle(game_id, sandbox.sandbox_id)
        except Exception as error:
            if sandbox is not None:
                await self._safe_kill(sandbox.sandbox_id)
            state = "archived" if row.snapshot_key else "active"
            await self._set_state(
                game_id,
                state,
                sandbox_id=None,
                last_error=str(error)[:2000],
            )
            raise SandboxUnavailable(f"恢复沙箱失败：{error}") from error

    async def _create_sandbox(self, game_id: uuid.UUID) -> e2b.AsyncSandbox:
        try:
            return await self._client.AsyncSandbox.create(
                template=settings.e2b_template or None,
                timeout=settings.sandbox_timeout,
                metadata={"app": APP_METADATA, "game_id": str(game_id)},
                lifecycle={"on_timeout": "pause", "auto_resume": True},
            )
        except Exception as error:
            raise SandboxUnavailable(f"创建沙箱失败：{error}") from error

    async def _connect(self, sandbox_id: str) -> e2b.AsyncSandbox:
        return await self._client.AsyncSandbox.connect(
            sandbox_id, timeout=settings.sandbox_timeout
        )

    # ---------- 归档 ----------

    async def _archive_locked(self, game_id: uuid.UUID, *, force: bool) -> dict[str, Any]:
        async with self._sessions() as session:
            row = await game_repo.get_sandbox(session, game_id)
        if row is None:
            return {"status": "missing"}
        if not row.sandbox_id:
            if row.snapshot_key:
                await self._set_state(game_id, "archived")
                return {"status": "archived", "snapshot_key": row.snapshot_key}
            return {"status": "empty"}

        sandbox_id = row.sandbox_id
        try:
            info = await self._client.AsyncSandbox.get_info(sandbox_id)
        except e2b.SandboxNotFoundException:
            await self._set_state(game_id, "archived" if row.snapshot_key else "active", sandbox_id=None)
            return {"status": "missing"}
        if not _is_paused(info):
            if not force:
                return {"status": "running"}
            await self._pause(sandbox_id)
            info = await self._client.AsyncSandbox.get_info(sandbox_id)
            if not _is_paused(info):
                return {"status": "running"}
        retry_due = row.archive_retry_at is not None and row.archive_retry_at <= _now()
        if not force and not retry_due and not self._paused_long_enough(info):
            return {"status": "not_due"}

        await self._set_state(game_id, "archiving", last_error=None)
        sandbox = None
        try:
            sandbox = await self._connect(sandbox_id)
            await self._stop_game_server(sandbox)
            size, sha256 = await self._tar_workspace(sandbox)
            key = self._snapshots.new_key(game_id)
            url = await self._snapshots.presign_put(key)
            await self._upload_snapshot(sandbox, url)
            snapshot = await self._snapshots.head(key)
            if snapshot is None or snapshot.size <= 0:
                raise SandboxUnavailable("OSS 快照上传后校验失败")
            await self._set_state(
                game_id,
                "archiving",
                snapshot_key=key,
                snapshot_at=_now(),
                snapshot_bytes=size,
                snapshot_sha256=sha256,
                last_error=None,
            )
            await self._safe_kill(sandbox_id)
            await self._set_state(
                game_id,
                "archived",
                sandbox_id=None,
                archive_retry_at=None,
                archive_attempts=0,
                last_error=None,
            )
            logger.info(
                "沙箱已归档 game=%s sandbox=%s key=%s bytes=%s",
                game_id,
                sandbox_id,
                key,
                size,
            )
            return {
                "status": "archived",
                "snapshot_key": key,
                "snapshot_bytes": size,
                "snapshot_sha256": sha256,
                "oss_etag": snapshot.etag,
            }
        except Exception as error:
            logger.exception("归档沙盒失败 game=%s sandbox=%s", game_id, sandbox_id)
            if sandbox is not None:
                await self._safe_pause(sandbox)
            async with self._sessions() as session:
                current = await game_repo.get_sandbox(session, game_id)
                attempts = (current.archive_attempts if current else 0) + 1
            await self._set_state(
                game_id,
                "active",
                archive_retry_at=_now() + timedelta(seconds=300),
                archive_attempts=attempts,
                last_error=str(error)[:2000],
            )
            raise SandboxUnavailable(f"归档沙箱失败：{error}") from error

    async def _archive_from_db(
        self,
        scanned: int,
        archived: int,
        skipped: int,
        failed: int,
    ) -> tuple[int, int, int, int]:
        async with self._sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SandboxSession).where(SandboxSession.sandbox_id.is_not(None))
                    )
                ).all()
            )
        for row in rows:
            scanned += 1
            try:
                result = await self.archive(row.game_id, force=False)
            except LockBusy:
                skipped += 1
                continue
            except Exception:
                failed += 1
                logger.exception("数据库回退归档失败 game=%s", row.game_id)
                continue
            if result.get("status") == "archived":
                archived += 1
            else:
                skipped += 1
        return scanned, archived, skipped, failed

    async def _archive_retries(
        self,
        scanned: int,
        archived: int,
        skipped: int,
        failed: int,
    ) -> tuple[int, int, int, int]:
        """归档失败后按 archive_retry_at 重试，不等下一次暂停满 2 小时。"""
        async with self._sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SandboxSession).where(
                            SandboxSession.sandbox_id.is_not(None),
                            SandboxSession.archive_retry_at.is_not(None),
                            SandboxSession.archive_retry_at <= _now(),
                        )
                    )
                ).all()
            )
        for row in rows:
            scanned += 1
            try:
                result = await self.archive(row.game_id, force=False)
            except LockBusy:
                skipped += 1
                continue
            except Exception:
                failed += 1
                logger.exception("归档重试失败 game=%s", row.game_id)
                continue
            if result.get("status") == "archived":
                archived += 1
            else:
                skipped += 1
        return scanned, archived, skipped, failed

    def _paused_long_enough(self, info: Any) -> bool:
        if not info.end_at:
            return False
        return (_now() - info.end_at).total_seconds() >= settings.sandbox_archive_after_seconds

    def _game_id_from_metadata(self, metadata: dict[str, str] | None) -> uuid.UUID | None:
        if not metadata:
            return None
        raw = metadata.get("game_id")
        if not raw:
            return None
        try:
            return uuid.UUID(raw)
        except ValueError:
            return None

    async def _tar_workspace(self, sandbox: e2b.AsyncSandbox) -> tuple[int, str]:
        excludes = " ".join(f"--exclude={shlex.quote('./' + item)}" for item in ARCHIVE_EXCLUDES)
        command = (
            f"tar -czf {shlex.quote(TAR_PATH)} -C {shlex.quote(settings.sandbox_workspace_dir)} "
            f"{excludes} . && "
            f"stat -c '%s' {shlex.quote(TAR_PATH)} && "
            f"sha256sum {shlex.quote(TAR_PATH)} | cut -d' ' -f1"
        )
        output = await self._run(sandbox, command, timeout=600)
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) < 2:
            raise SandboxUnavailable(f"打包输出异常：{output[-500:]}")
        size = int(lines[-2])
        sha256 = lines[-1]
        return size, sha256

    async def _upload_snapshot(self, sandbox: e2b.AsyncSandbox, url: str) -> None:
        command = (
            f"curl -fsS --retry 3 -X PUT -T {shlex.quote(TAR_PATH)} {shlex.quote(url)}"
        )
        await self._run(sandbox, command, timeout=900)

    async def _download_snapshot(
        self, sandbox: e2b.AsyncSandbox, key: str, sha256: str | None
    ) -> None:
        url = await self._snapshots.presign_get(key)
        verify = ""
        if sha256:
            verify = (
                f"actual=$(sha256sum {shlex.quote(TAR_PATH)} | cut -d' ' -f1); "
                f"[ \"$actual\" = {shlex.quote(sha256)} ] || {{ echo 'sha256 mismatch'; exit 1; }}; "
            )
        command = (
            f"curl -fsSL --retry 3 {shlex.quote(url)} -o {shlex.quote(TAR_PATH)} && "
            f"{verify}"
            f"rm -rf {shlex.quote(settings.sandbox_workspace_dir)} && "
            f"mkdir -p {shlex.quote(settings.sandbox_workspace_dir)} && "
            f"tar -xzf {shlex.quote(TAR_PATH)} -C {shlex.quote(settings.sandbox_workspace_dir)} && "
            f"/opt/sandbox/prepare-workspace.sh && "
            f"rm -f {shlex.quote(TAR_PATH)}"
        )
        await self._run(sandbox, command, timeout=900)

    async def _prepare_workspace(self, sandbox: e2b.AsyncSandbox) -> None:
        await self._run(
            sandbox,
            f"mkdir -p {shlex.quote(settings.sandbox_workspace_dir)} && "
            "/opt/sandbox/prepare-workspace.sh",
            timeout=120,
        )

    async def _start_display_services(self, sandbox: e2b.AsyncSandbox) -> None:
        await self._run(sandbox, "/opt/sandbox/start-services.sh", timeout=60)

    async def _stop_game_server(self, sandbox: e2b.AsyncSandbox) -> None:
        await self._run(
            sandbox,
            'pkill -f "[d]ev.mjs" >/dev/null 2>&1 || true; '
            'pkill -f "server/index\\.js" >/dev/null 2>&1 || true; '
            "sleep 1; true",
            timeout=30,
        )

    async def _start_game_server(self, sandbox: e2b.AsyncSandbox) -> None:
        await self._run(sandbox, GAME_SERVER_ENSURE_COMMAND, timeout=180)

    async def _wait_game_ready(self, sandbox: e2b.AsyncSandbox) -> None:
        for _ in range(60):
            result = await sandbox.commands.run(
                "curl -sf -m 2 http://127.0.0.1:3000/api/health >/dev/null",
                timeout=10,
            )
            if result.exit_code == 0:
                return
            await asyncio.sleep(1)
        raise SandboxUnavailable("游戏服务未在 60 秒内就绪")

    async def _preview_urls(self, sandbox: e2b.AsyncSandbox) -> GameUrls:
        game_host = sandbox.get_host(settings.sandbox_game_port)
        novnc_host = sandbox.get_host(settings.sandbox_novnc_port)
        token = getattr(sandbox, "_envd_access_token", None)
        game_url = game_host if game_host.startswith("http") else f"https://{game_host}"
        novnc_url = (
            novnc_host if novnc_host.startswith("http") else f"https://{novnc_host}"
        )
        novnc_url = f"{novnc_url}/vnc.html?autoconnect=1&resize=scale&path=websockify"
        if token:
            novnc_url += f"&access_token={token}"
        return GameUrls(game_url=game_url, novnc_url=novnc_url)

    # ---------- 基础操作 ----------

    async def _run(
        self, sandbox: e2b.AsyncSandbox, command: str, *, timeout: float
    ) -> str:
        try:
            result = await sandbox.commands.run(command, timeout=timeout)
        except Exception as error:
            raise SandboxUnavailable(f"沙箱命令执行失败：{error}") from error
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if result.exit_code != 0:
            raise SandboxUnavailable(f"沙箱命令退出码 {result.exit_code}：{output[-1000:]}")
        return output

    async def _pause(self, sandbox_id: str) -> None:
        try:
            sandbox = await self._connect(sandbox_id)
            await sandbox.pause()
            for _ in range(30):
                info = await self._client.AsyncSandbox.get_info(sandbox_id)
                if _is_paused(info):
                    return
                await asyncio.sleep(0.5)
        except Exception as error:  # noqa: BLE001 - 暂停失败不阻塞主流程
            logger.warning("暂停沙箱 %s 失败：%s", sandbox_id, error)

    async def _safe_pause(self, sandbox: e2b.AsyncSandbox) -> None:
        try:
            await sandbox.pause()
        except Exception as error:  # noqa: BLE001 - 暂停失败不阻塞主流程
            logger.warning("暂停沙箱 %s 失败：%s", sandbox.sandbox_id, error)

    async def _safe_kill(self, sandbox_id: str) -> None:
        try:
            await self._client.AsyncSandbox.kill(sandbox_id)
        except e2b.SandboxNotFoundException:
            return
        except Exception as error:  # noqa: BLE001 - STOPPED 视为已删除
            if "STOPPED" in str(error):
                return
            logger.warning("删除沙箱 %s 失败：%s", sandbox_id, error)

    async def active_handle(self, game_id: uuid.UUID) -> SandboxHandle | None:
        async with self._sessions() as session:
            row = await game_repo.get_sandbox(session, game_id)
        if row is None or not row.sandbox_id:
            return None
        return SandboxHandle(game_id, row.sandbox_id)

    def backend(self, handle: SandboxHandle) -> E2BSandboxBackend:
        return E2BSandboxBackend(
            client=self._client,
            ref=handle.ref,
            working_dir=settings.sandbox_workspace_dir,
        )

    async def preview_host(self, handle: SandboxHandle, port: int) -> str:
        try:
            sandbox = await self._connect(handle.sandbox_id)
            host = sandbox.get_host(port)
        except Exception as error:
            raise SandboxUnavailable(f"获取预览地址失败：{error}") from error
        url = host if host.startswith("http") else f"https://{host}"
        if port == settings.sandbox_novnc_port:
            token = getattr(sandbox, "_envd_access_token", None)
            url = f"{url}/vnc.html?autoconnect=1&resize=scale&path=websockify"
            if token:
                url += f"&access_token={token}"
        return url

    async def kill_checked(self, sandbox_id: str) -> None:
        await self._client.AsyncSandbox.kill(sandbox_id)

    async def mark_dead(self, sandbox_id: str) -> None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SandboxSession).where(SandboxSession.sandbox_id == sandbox_id)
            )
            if row is None:
                return
            row.sandbox_id = None
            row.lifecycle_state = "archived" if row.snapshot_key else "active"
            await session.commit()

    async def _mark_used(self, game_id: uuid.UUID) -> None:
        async with self._sessions() as session:
            await game_repo.update_sandbox(session, game_id, last_used_at=_now())

    async def _set_state(self, game_id: uuid.UUID, state: str, **values: Any) -> None:
        async with self._sessions() as session:
            await game_repo.update_sandbox(
                session, game_id, lifecycle_state=state, **values
            )
