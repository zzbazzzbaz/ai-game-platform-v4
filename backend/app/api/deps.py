from __future__ import annotations

from fastapi import Request

from app.agent.factory import AgentFactory
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
