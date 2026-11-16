from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.factory import AgentFactory
from app.config import settings
from app.db import get_session
from app.models import Conversation, Session, User
from app.runtime.runs import RunManager
from app.runtime.sandboxes import SandboxRegistry
from app.security import hash_token, token_from_cookie
from app.store.conversations import PostgresConversationStore


def get_store(request: Request) -> PostgresConversationStore:
    return request.app.state.store


def get_registry(request: Request) -> SandboxRegistry:
    return request.app.state.sandbox_registry


def get_run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def get_agent_factory(request: Request) -> AgentFactory:
    return request.app.state.agent_factory


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    cookie = request.cookies.get(settings.session_cookie)
    token = token_from_cookie(cookie) if cookie else None
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    row = (
        await session.execute(
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(
                Session.token_hash == hash_token(token),
                Session.expires_at > datetime.now(UTC),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    return row[1]


async def owned_conversation(
    conversation_id: uuid.UUID, user: User, session: AsyncSession
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return row
