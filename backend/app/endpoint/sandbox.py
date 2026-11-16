from __future__ import annotations

import mimetypes
import posixpath
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic_ai.workspaces import WorkspaceError, WorkspaceUnavailableError

from app.endpoint.deps import CurrentUser, DbSession, RegistryDep, owned_conversation
from app.endpoint.schemas.sandbox import (
    FileEntryOut,
    FileListOut,
    PreviewOut,
    UploadOut,
)
from app.runtime.sandboxes import SandboxUnavailable

router = APIRouter(tags=["sandbox"])

MAX_FILE_BYTES = 2 * 1024 * 1024


def _safe_path(root: str, path: str) -> str:
    root_path = posixpath.normpath(root).rstrip("/")
    candidate = posixpath.normpath(path if path.startswith("/") else posixpath.join(root_path, path))
    if candidate != root_path and not candidate.startswith(f"{root_path}/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径超出工作目录")
    return candidate


@router.get("/conversations/{conversation_id}/sandbox/files", response_model=FileListOut)
async def list_files(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    path: str | None = Query(default=None),
) -> FileListOut:
    await owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        return FileListOut(path=path or "")
    backend = registry.backend(handle)
    try:
        root = await backend.working_dir()
        target = _safe_path(root, path) if path else root
        entries = await backend.list_dir(target)
    except (WorkspaceError, OSError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return FileListOut(
        root=root,
        path=target,
        sandbox=handle.sandbox_id,
        entries=[
            FileEntryOut(name=entry.name, path=entry.path, is_dir=entry.is_dir, size=entry.size)
            for entry in entries
        ],
    )


@router.get("/conversations/{conversation_id}/sandbox/file")
async def read_file(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    path: str = Query(...),
) -> Response:
    await owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    backend = registry.backend(handle)
    try:
        root = await backend.working_dir()
        target = _safe_path(root, path)
        entry = await backend.stat(target)
        if entry.is_dir:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标是目录")
        if entry.size is not None and entry.size > MAX_FILE_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大")
        data = await backend.read_bytes(target)
    except HTTPException:
        raise
    except (WorkspaceError, OSError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大")
    media_type = mimetypes.guess_type(path)[0] or "text/plain; charset=utf-8"
    return Response(content=data, media_type=media_type)


@router.post("/conversations/{conversation_id}/sandbox/preview/{port}")
@router.get("/conversations/{conversation_id}/sandbox/preview/{port}")
async def preview(
    conversation_id: uuid.UUID,
    port: int,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> PreviewOut:
    await owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    try:
        url = await registry.preview_host(handle, port)
    except SandboxUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return PreviewOut(url=url)


@router.post("/conversations/{conversation_id}/files", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    file: UploadFile = File(...),
    path: str | None = Form(default=None),
) -> UploadOut:
    await owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大")
    backend = registry.backend(handle)
    try:
        working_dir = await backend.working_dir()
        name = Path(file.filename or "upload.bin").name
        target = _safe_path(working_dir, path or name)
        await backend.write_bytes(target, data)
    except (WorkspaceError, OSError, WorkspaceUnavailableError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    return UploadOut(path=target, size=len(data))
