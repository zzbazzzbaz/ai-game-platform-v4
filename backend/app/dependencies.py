from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.errors import unauthorized
from app.repositories.conversation_store import PostgresConversationStore
from app.repositories.models import User
from app.security import token_from_cookie
from app.services import auth_service
from app.services.agent.factory import AgentFactory
from app.services.run_manager import RunManager
from app.services.sandbox_registry import SandboxRegistry

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
        raise unauthorized()

    user = await auth_service.user_from_token(session, token)
    if user is None:
        raise unauthorized("登录已过期")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
StoreDep = Annotated[PostgresConversationStore, Depends(get_store)]
RegistryDep = Annotated[SandboxRegistry, Depends(get_registry)]
RunManagerDep = Annotated[RunManager, Depends(get_run_manager)]
AgentFactoryDep = Annotated[AgentFactory, Depends(get_agent_factory)]
