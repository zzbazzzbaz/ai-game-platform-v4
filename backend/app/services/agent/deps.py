from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

ApprovalMode = Literal["full", "auto", "read-only"]


@dataclass
class AgentDeps:
    """一次 run 的依赖。"""

    user_id: uuid.UUID
    conversation_id: str
    approval_mode: ApprovalMode = "auto"
