from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_ai.models import infer_model
from sqlalchemy import select, update

from app.agent.factory import AgentFactory
from app.endpoint import api_router
from app.config import settings
from app.db import dispose_engine, session_factory
from app.models import Run, User
from app.runtime.reaper import SandboxReaper
from app.runtime.runs import RunManager
from app.runtime.sandboxes import SandboxRegistry, create_e2b_client
from app.security import hash_password
from app.store.conversations import PostgresConversationStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_demo_user() -> None:
    async with session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == settings.demo_email))
        if existing is None:
            session.add(
                User(email=settings.demo_email, password_hash=hash_password(settings.demo_password))
            )
            await session.commit()
            logger.info("已创建演示账号 %s", settings.demo_email)


async def fail_stale_runs() -> None:
    """进程重启后，上次遗留的 running 记录不可能再有执行者。"""
    async with session_factory() as session:
        result = await session.execute(
            update(Run)
            .where(Run.status == "running", Run.started_at < datetime.now(UTC) - timedelta(minutes=10))
            .values(
                status="failed",
                finished_at=datetime.now(UTC),
                error={"type": "ServerRestart", "message": "服务重启，运行被中断"},
            )
        )
        await session.commit()
        if result.rowcount:
            logger.info("已标记 %s 条遗留的 running 记录为 failed", result.rowcount)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.deepseek_api_key:
        os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key

    if settings.logfire_token:
        logfire.configure(token=settings.logfire_token)
    else:
        logfire.configure(send_to_logfire=False)
    logfire.instrument_pydantic_ai()

    e2b_client = create_e2b_client()
    store = PostgresConversationStore(session_factory)
    registry = SandboxRegistry(e2b_client, session_factory)
    run_manager = RunManager(session_factory)
    agent_factory = AgentFactory(
        infer_model(settings.model),
        e2b_client=e2b_client,
        template=settings.e2b_template or None,
        sandbox_timeout=settings.sandbox_timeout,
    )

    app.state.store = store
    app.state.sandbox_registry = registry
    app.state.run_manager = run_manager
    app.state.agent_factory = agent_factory

    await fail_stale_runs()
    await seed_demo_user()

    reaper = SandboxReaper(registry, session_factory)
    reaper_task = asyncio.create_task(reaper.run_forever())
    try:
        yield
    finally:
        reaper_task.cancel()
        try:
            await reaper_task
        except asyncio.CancelledError:
            pass
        await dispose_engine()


app = FastAPI(title="Pydantic AI Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
