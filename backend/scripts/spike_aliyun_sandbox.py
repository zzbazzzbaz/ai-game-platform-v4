"""直连阿里云 Agent Sandbox：创建、执行命令、获取预览地址、销毁。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.runtime.sandboxes.registry import create_e2b_client


async def main() -> None:
    client = create_e2b_client()
    sandbox = await client.AsyncSandbox.create(
        template=settings.e2b_template or None,
        timeout=settings.sandbox_timeout,
        lifecycle={"on_timeout": "pause"},
    )
    print("sandbox:", sandbox.sandbox_id)
    try:
        result = await sandbox.commands.run("python3 -V && whoami && pwd")
        print("stdout:", result.stdout.strip())
        print("exit:", result.exit_code)
        print("preview:", f"https://{sandbox.get_host(8000)}")
    finally:
        await sandbox.kill()
        print("killed")


if __name__ == "__main__":
    asyncio.run(main())
