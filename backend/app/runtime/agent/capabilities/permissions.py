from __future__ import annotations

from pydantic_ai_harness.permissions import Permissions

from app.runtime.agent.deps import AgentDeps


def permissions() -> Permissions[AgentDeps]:
    """按当前 run 的审批模式决定哪些工具调用需要人工批准。"""
    return Permissions(lambda ctx: ctx.deps.approval_mode)
