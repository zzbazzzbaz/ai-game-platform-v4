from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.factory import AgentFactory
from app.models import Conversation, User
from app.runtime.runs import RunManager
from app.runtime.sandboxes import SandboxRegistry
from app.store.conversations import PostgresConversationStore


def get_store(request: Request) -> PostgresConversationStore:
    return request.app.state.store


def get_registry(request: Request) -> SandboxRegistry:
    return request.app.state.sandbox_registry


def get_run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def get_agent_factory(request: Request) -> AgentFactory:
    return request.app.state.agent_factory


async def owned_conversation(
    conversation_id: uuid.UUID, user: User, session: AsyncSession
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return row
