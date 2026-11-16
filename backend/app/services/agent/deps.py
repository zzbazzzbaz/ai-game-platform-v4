from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic_ai.workspaces import WorkspaceRef

ApprovalMode = Literal["full", "auto", "read-only"]


@dataclass
class AgentDeps:
    """一次 run 的依赖。"""

    user_id: uuid.UUID
    conversation_id: str
    sandbox_ref: WorkspaceRef
    approval_mode: ApprovalMode = "auto"
