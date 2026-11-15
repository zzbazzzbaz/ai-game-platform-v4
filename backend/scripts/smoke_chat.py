"""通过 HTTP 跑一次真实的聊天 SSE：登录演示账号、创建会话、发送一条消息。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings

BASE_URL = "http://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=300) as client:
        login = await client.post(
            "/api/auth/login",
            json={"email": settings.demo_email, "password": settings.demo_password},
        )
        login.raise_for_status()
        conversation = (await client.post("/api/conversations")).json()
        print("conversation:", conversation["id"])

        body = {
            "id": conversation["id"],
            "trigger": "submit-message",
            "messages": [
                {
                    "id": "smoke-1",
                    "role": "user",
                    "parts": [
                        {
                            "type": "text",
                            "text": "在沙箱里创建 smoke.py，打印 hello smoke，然后运行它。",
                        }
                    ],
                }
            ],
        }
        async with client.stream(
            "POST",
            "/api/chat",
            json=body,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    print("\n[DONE]")
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("type") == "text-delta":
                    print(chunk.get("delta", ""), end="", flush=True)
                elif chunk.get("type") == "error":
                    print("\nERROR:", chunk.get("errorText"))


if __name__ == "__main__":
    asyncio.run(main())
