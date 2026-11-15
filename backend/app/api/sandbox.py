from __future__ import annotations

import mimetypes
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic_ai.workspaces import WorkspaceError, WorkspaceUnavailableError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_registry
from app.auth.deps import current_user
from app.db import get_session
from app.models import Conversation, User
from app.runtime.sandboxes import SandboxRegistry, SandboxUnavailable

router = APIRouter(prefix="/api", tags=["sandbox"])

MAX_FILE_BYTES = 2 * 1024 * 1024


async def _owned_conversation(
    conversation_id: uuid.UUID, user: User, session: AsyncSession
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return row


@router.get("/conversations/{conversation_id}/sandbox/files")
async def list_files(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
    path: str | None = Query(default=None),
) -> dict[str, object]:
    await _owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        return {"path": path or "", "entries": [], "sandbox": None}
    backend = registry.backend(handle)
    try:
        root = path or await backend.working_dir()
        entries = await backend.list_dir(root)
    except (WorkspaceError, OSError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return {
        "path": root,
        "sandbox": handle.sandbox_id,
        "entries": [
            {"name": entry.name, "path": entry.path, "is_dir": entry.is_dir, "size": entry.size}
            for entry in entries
        ],
    }


@router.get("/conversations/{conversation_id}/sandbox/file")
async def read_file(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
    path: str = Query(...),
) -> Response:
    await _owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    backend = registry.backend(handle)
    try:
        data = await backend.read_bytes(path)
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
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
) -> dict[str, str]:
    await _owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    try:
        url = await registry.preview_host(handle, port)
    except SandboxUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return {"url": url}


@router.post("/conversations/{conversation_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
    file: UploadFile = File(...),
    path: str | None = Form(default=None),
) -> dict[str, object]:
    await _owned_conversation(conversation_id, user, session)
    handle = await registry.active_handle(conversation_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该会话还没有沙箱")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大")
    backend = registry.backend(handle)
    try:
        working_dir = await backend.working_dir()
        target = path or f"{working_dir.rstrip('/')}/{file.filename}"
        await backend.write_bytes(target, data)
    except (WorkspaceError, OSError, WorkspaceUnavailableError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    return {"path": target, "size": len(data)}
