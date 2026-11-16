from __future__ import annotations

import e2b
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai_harness.coder import Coder
from pydantic_ai_harness.e2b_sandbox import E2BSandbox

from app.runtime.agent.capabilities.permissions import permissions
from app.runtime.agent.capabilities.planning import planning
from app.runtime.agent.deps import AgentDeps
from app.runtime.agent.instructions import INSTRUCTIONS


class AgentFactory:
    """为每次 run 组装 Agent。模型实例由应用启动时创建并复用。"""

    def __init__(
        self,
        model: Model,
        *,
        e2b_client: e2b.E2B | None = None,
        template: str | None = None,
        sandbox_timeout: int = 600,
    ) -> None:
        self._model = model
        self._e2b_client = e2b_client
        self._template = template
        self._sandbox_timeout = sandbox_timeout

    def build(self) -> Agent[AgentDeps, str | DeferredToolRequests]:
        return Agent(
            self._model,
            deps_type=AgentDeps,
            output_type=[str, DeferredToolRequests],
            instructions=INSTRUCTIONS,
            capabilities=[
                E2BSandbox(
                    client=self._e2b_client,
                    template=self._template,
                    sandbox_timeout=self._sandbox_timeout,
                ),
                Coder(),
                permissions(),
                planning(),
            ],
        )
