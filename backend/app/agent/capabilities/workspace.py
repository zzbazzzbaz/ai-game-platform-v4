from __future__ import annotations

from dataclasses import dataclass

import e2b
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import RunContext
from pydantic_ai.workspaces import WorkspaceBackend, WorkspaceRef
from pydantic_ai_harness.e2b_sandbox import E2BSandboxBackend

from app.agent.deps import AgentDeps


@dataclass(kw_only=True)
class ConversationWorkspace(AbstractCapability[AgentDeps]):
    """把 `AgentDeps.sandbox_ref` 解析为本次 run 的 E2B 工作区。

    沙箱的创建、登记与回收由 `SandboxRegistry` 负责，这里只附加已有实例。
    """

    client: e2b.E2B | None = None
    """`e2b.E2B` 客户端；启动时由应用注入。"""

    template: str | None = None
    sandbox_timeout: int = 3600

    def get_workspace(
        self, ctx: RunContext[AgentDeps], *, ref: WorkspaceRef | None
    ) -> WorkspaceBackend | None:
        sandbox_ref = ctx.deps.sandbox_ref
        if sandbox_ref.provider != "e2b":
            return None
        if ref is not None and ref != sandbox_ref:
            return None
        return E2BSandboxBackend(
            client=self.client,
            ref=sandbox_ref,
            template=self.template,
            sandbox_timeout=self.sandbox_timeout,
        )
