from __future__ import annotations

import e2b
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai_harness.coder import Coder

from app.agent.capabilities.permissions import permissions
from app.agent.capabilities.planning import planning
from app.agent.capabilities.workspace import ConversationWorkspace
from app.agent.deps import AgentDeps
from app.agent.instructions import INSTRUCTIONS


class AgentFactory:
    """为每次 run 组装 Agent。模型实例由应用启动时创建并复用。"""

    def __init__(self, model: Model, *, e2b_client: e2b.E2B | None = None, template: str | None = None) -> None:
        self._model = model
        self._e2b_client = e2b_client
        self._template = template

    def build(self) -> Agent[AgentDeps, str | DeferredToolRequests]:
        return Agent(
            self._model,
            deps_type=AgentDeps,
            output_type=[str, DeferredToolRequests],
            instructions=INSTRUCTIONS,
            capabilities=[
                ConversationWorkspace(client=self._e2b_client, template=self._template),
                Coder(),
                permissions(),
                planning(),
            ],
        )
