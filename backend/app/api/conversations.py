from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from app.api.deps import get_registry, get_run_manager, get_store, owned_conversation
from app.auth.deps import current_user
from app.db import get_session
from app.models import Conversation, Run, User
from app.runtime.runs import RunManager
from app.runtime.sandboxes import SandboxRegistry
from app.store.conversations import PostgresConversationStore

router = APIRouter(prefix="/api", tags=["conversations"])


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class RunOut(BaseModel):
    id: str
    status: str
    model: str
    started_at: datetime
    finished_at: datetime | None
    usage: dict[str, Any]
    error: dict[str, Any] | None

    @classmethod
    def from_run(cls, run: Run) -> "RunOut":
        return cls(
            id=str(run.id),
            status=run.status,
            model=run.model,
            started_at=run.started_at,
            finished_at=run.finished_at,
            usage=run.usage,
            error=run.error,
        )


def _conversation_out(row: Conversation) -> ConversationOut:
    return ConversationOut(
        id=str(row.id), title=row.title, created_at=row.created_at, updated_at=row.updated_at
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ConversationOut]:
    rows = (
        await session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
    ).all()
    return [_conversation_out(row) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationOut:
    row = Conversation(id=uuid.uuid7(), user_id=user.id, title="新会话", usage={})
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _conversation_out(row)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[PostgresConversationStore, Depends(get_store)],
) -> dict[str, Any]:
    row = await owned_conversation(conversation_id, user, session)
    conversation = await store.load(str(conversation_id), scope=str(user.id))
    messages = (
        VercelAIAdapter.dump_messages(conversation.messages, sdk_version=6)
        if conversation is not None
        else []
    )
    last_run = await session.scalar(
        select(Run)
        .where(Run.conversation_id == conversation_id)
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    return {
        "id": str(row.id),
        "title": row.title,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "messages": messages,
        "usage": conversation.usage if conversation is not None else {},
        "deferred_tool_requests": (
            conversation.deferred_tool_requests if conversation is not None else None
        ),
        "last_run": RunOut.from_run(last_run) if last_run is not None else None,
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[PostgresConversationStore, Depends(get_store)],
    registry: Annotated[SandboxRegistry, Depends(get_registry)],
    run_manager: Annotated[RunManager, Depends(get_run_manager)],
) -> None:
    await owned_conversation(conversation_id, user, session)
    if run_manager.active(conversation_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话正在运行，无法删除")
    handle = await registry.active_handle(conversation_id)
    if handle is not None:
        try:
            await registry.kill_checked(handle.sandbox_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="沙箱销毁失败，请稍后重试"
            ) from error
    await store.delete(str(conversation_id), scope=str(user.id))
