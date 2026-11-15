"""在本地临时目录跑一次真实模型的 Coder。"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.models import infer_model
from pydantic_ai_harness.coder import Coder

from app.config import settings


async def main() -> None:
    if settings.deepseek_api_key:
        os.environ.setdefault("DEEPSEEK_API_KEY", settings.deepseek_api_key)

    with tempfile.TemporaryDirectory(prefix="agent-local-") as directory:
        agent = Agent(
            infer_model(settings.model),
            capabilities=[LocalWorkspace(directory), Coder()],
            instructions="用简体中文回答，完成任务后总结。",
        )
        result = await agent.run("创建 hello.py，内容是打印 hello local，然后运行它并告诉我输出。")
        print(result.output)
        print("--- workspace ---")
        for path in sorted(Path(directory).iterdir()):
            print(path.name)


if __name__ == "__main__":
    asyncio.run(main())
