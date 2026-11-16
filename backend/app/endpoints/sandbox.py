from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.dependencies import CurrentUser, DbSession, RegistryDep
from app.dto.sandbox import FileListOut, PreviewOut, UploadOut
from app.errors import (
    bad_gateway,
    bad_request_detail,
    not_found,
    payload_too_large,
    service_unavailable,
)
from app.services import conversation_service, sandbox_service
from app.services.sandbox_registry import SandboxUnavailable

router = APIRouter(tags=["沙箱"])


async def _ensure_owned(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    try:
        await conversation_service.get_owned(session, conversation_id, user.id)
    except conversation_service.ConversationNotFoundError as error:
        raise not_found() from error


@router.get("/conversations/{conversation_id}/sandbox/files", response_model=FileListOut)
async def list_files(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    path: str | None = Query(default=None),
) -> FileListOut:
    await _ensure_owned(conversation_id, user, session)
    try:
        result = await sandbox_service.list_files(registry, conversation_id, path=path)
    except sandbox_service.SandboxPathError as error:
        raise bad_request_detail("路径超出工作目录") from error
    except sandbox_service.SandboxReadError as error:
        raise not_found() from error
    return result if result is not None else FileListOut(path=path or "")


@router.get("/conversations/{conversation_id}/sandbox/file")
async def read_file(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    path: str = Query(...),
) -> Response:
    await _ensure_owned(conversation_id, user, session)
    try:
        result = await sandbox_service.read_file(registry, conversation_id, path=path)
    except sandbox_service.SandboxMissingError as error:
        raise not_found() from error
    except sandbox_service.SandboxPathError as error:
        raise bad_request_detail("路径超出工作目录") from error
    except sandbox_service.SandboxTargetIsDirectoryError as error:
        raise bad_request_detail("目标是目录") from error
    except sandbox_service.SandboxFileTooLargeError as error:
        raise payload_too_large() from error
    except sandbox_service.SandboxReadError as error:
        raise not_found() from error
    return Response(content=result.content, media_type=result.media_type)


@router.post("/conversations/{conversation_id}/sandbox/preview/{port}")
@router.get("/conversations/{conversation_id}/sandbox/preview/{port}")
async def preview(
    conversation_id: uuid.UUID,
    port: int,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
) -> PreviewOut:
    await _ensure_owned(conversation_id, user, session)
    try:
        url = await sandbox_service.preview_url(registry, conversation_id, port=port)
    except sandbox_service.SandboxMissingError as error:
        raise not_found() from error
    except SandboxUnavailable as error:
        raise service_unavailable() from error
    return PreviewOut(url=url)


@router.post(
    "/conversations/{conversation_id}/files",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    registry: RegistryDep,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI 依赖必须写在参数默认值
    path: str | None = Form(default=None),
) -> UploadOut:
    await _ensure_owned(conversation_id, user, session)
    data = await file.read(sandbox_service.MAX_FILE_BYTES + 1)
    try:
        return await sandbox_service.upload_file(
            registry,
            conversation_id,
            filename=file.filename,
            data=data,
            path=path,
        )
    except sandbox_service.SandboxMissingError as error:
        raise not_found() from error
    except sandbox_service.SandboxFileTooLargeError as error:
        raise payload_too_large() from error
    except sandbox_service.SandboxPathError as error:
        raise bad_request_detail("路径超出工作目录") from error
    except sandbox_service.SandboxWriteError as error:
        raise bad_gateway() from error
