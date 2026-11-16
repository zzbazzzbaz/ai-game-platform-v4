from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai_harness.planning import InMemoryPlanStore, Planning

from app.runtime.agent.deps import AgentDeps

_stores: dict[str, InMemoryPlanStore] = {}


def _store_for(ctx: RunContext[AgentDeps]) -> InMemoryPlanStore:
    return _stores.setdefault(ctx.deps.conversation_id, InMemoryPlanStore())


def planning() -> Planning[AgentDeps]:
    """计划工具：按 conversation 使用进程内存储，不落库，进程重启后清空。"""
    return Planning(store_resolver=_store_for)
