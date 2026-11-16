from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.errors import unauthorized
from app.repositories.conversation_store import PostgresConversationStore
from app.repositories.models import User
from app.runtime.agent.factory import AgentFactory
from app.runtime.runs.manager import RunManager
from app.runtime.sandboxes.registry import SandboxRegistry
from app.security import token_from_cookie
from app.services import auth_service

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_store(request: Request) -> PostgresConversationStore:
    return request.app.state.store


def get_registry(request: Request) -> SandboxRegistry:
    return request.app.state.sandbox_registry


def get_run_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def get_agent_factory(request: Request) -> AgentFactory:
    return request.app.state.agent_factory


async def current_user(request: Request, session: DbSession) -> User:
    cookie = request.cookies.get(settings.session_cookie)
    token = token_from_cookie(cookie) if cookie else None
    if token is None:
        logger.warning("请求未携带有效的会话 Cookie")
        raise unauthorized()

    user = await auth_service.user_from_token(session, token)
    if user is None:
        logger.warning("会话令牌无效或已过期")
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
StoreDep = Annotated[PostgresConversationStore, Depends(get_store)]
RegistryDep = Annotated[SandboxRegistry, Depends(get_registry)]
RunManagerDep = Annotated[RunManager, Depends(get_run_manager)]
AgentFactoryDep = Annotated[AgentFactory, Depends(get_agent_factory)]
