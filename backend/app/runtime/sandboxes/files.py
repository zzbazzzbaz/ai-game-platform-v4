from __future__ import annotations

import mimetypes
import posixpath
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.workspaces import WorkspaceError, WorkspaceUnavailableError

from app.config import settings
from app.dto.sandbox import FileEntryOut, FileListOut, UploadOut
from app.runtime.sandboxes.errors import (
    SandboxFileTooLargeError,
    SandboxMissingError,
    SandboxPathError,
    SandboxReadError,
    SandboxTargetIsDirectoryError,
    SandboxWriteError,
)
from app.runtime.sandboxes.registry import SandboxRegistry

MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FileReadResult:
    content: bytes
    media_type: str


def safe_path(root: str, path: str) -> str:
    root_path = posixpath.normpath(root).rstrip("/")
    candidate = posixpath.normpath(path if path.startswith("/") else posixpath.join(root_path, path))
    if candidate != root_path and not candidate.startswith(f"{root_path}/"):
        raise SandboxPathError
    return candidate


async def list_files(
    registry: SandboxRegistry,
    game_id: uuid.UUID,
    *,
    path: str | None,
) -> FileListOut | None:
    handle = await registry.active_handle(game_id)
    if handle is None:
        return None

    backend = registry.backend(handle)
    try:
        root = await backend.working_dir()
        target = safe_path(root, path) if path else root
        entries = await backend.list_dir(target)
    except (WorkspaceError, OSError) as error:
        raise SandboxReadError(str(error)) from error

    return FileListOut(
        root=root,
        path=target,
        sandbox=handle.sandbox_id,
        entries=[
            FileEntryOut(name=entry.name, path=entry.path, is_dir=entry.is_dir, size=entry.size)
            for entry in entries
        ],
    )


async def read_file(
    registry: SandboxRegistry,
    game_id: uuid.UUID,
    *,
    path: str,
) -> FileReadResult:
    handle = await registry.active_handle(game_id)
    if handle is None:
        raise SandboxMissingError

    backend = registry.backend(handle)
    try:
        root = await backend.working_dir()
        target = safe_path(root, path)
        entry = await backend.stat(target)
        if entry.is_dir:
            raise SandboxTargetIsDirectoryError
        if entry.size is not None and entry.size > MAX_FILE_BYTES:
            raise SandboxFileTooLargeError
        data = await backend.read_bytes(target)
    except (SandboxTargetIsDirectoryError, SandboxFileTooLargeError):
        raise
    except (WorkspaceError, OSError) as error:
        raise SandboxReadError(str(error)) from error

    if len(data) > MAX_FILE_BYTES:
        raise SandboxFileTooLargeError
    media_type = mimetypes.guess_type(path)[0] or "text/plain; charset=utf-8"
    return FileReadResult(content=data, media_type=media_type)


async def upload_file(
    registry: SandboxRegistry,
    game_id: uuid.UUID,
    *,
    filename: str | None,
    data: bytes,
    path: str | None,
) -> UploadOut:
    if len(data) > MAX_FILE_BYTES:
        raise SandboxFileTooLargeError

    handle = await registry.active_handle(game_id)
    if handle is None:
        raise SandboxMissingError

    backend = registry.backend(handle)
    try:
        working_dir = await backend.working_dir()
        name = Path(filename or "upload.bin").name
        target = safe_path(working_dir, path or name)
        await backend.write_bytes(target, data)
    except (WorkspaceError, OSError, WorkspaceUnavailableError) as error:
        raise SandboxWriteError(str(error)) from error
    return UploadOut(path=target, size=len(data))


async def preview_url(
    registry: SandboxRegistry,
    game_id: uuid.UUID,
    *,
    port: int,
) -> str:
    handle, urls = await registry.open_game(game_id)
    if port == settings.sandbox_game_port:
        return urls.game_url
    if port == settings.sandbox_novnc_port:
        return urls.novnc_url
    return await registry.preview_host(handle, port)
