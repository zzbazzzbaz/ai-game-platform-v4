from __future__ import annotations

from pydantic_ai_harness.planning import Planning

from app.agent.deps import AgentDeps


def planning() -> Planning[AgentDeps]:
    """计划工具，使用默认内存存储，不跨 run 持久化。"""
    return Planning()
