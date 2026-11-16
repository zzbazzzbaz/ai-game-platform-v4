from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import logfire
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.config import settings
from app.database import dispose_engine, session_factory
from app.job.reaper import SCAN_INTERVAL_SECONDS, run_reaper
from app.repositories.conversation_store import PostgresConversationStore
from app.services import run_service
from app.services.agent.factory import AgentFactory
from app.services.agent.model import build_model
from app.services.run_manager import RunManager
from app.services.sandbox_registry import SandboxRegistry, create_e2b_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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
        build_model(),
        e2b_client=e2b_client,
        template=settings.e2b_template or None,
        sandbox_timeout=settings.sandbox_timeout,
    )

    app.state.store = store
    app.state.sandbox_registry = registry
    app.state.run_manager = run_manager
    app.state.agent_factory = agent_factory

    stale = await run_service.fail_stale_runs(session_factory)
    if stale:
        logger.info("已标记 %s 条遗留的 running 记录为 failed", stale)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_reaper,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="sandbox-reaper",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
        replace_existing=True,
        next_run_time=datetime.now(UTC),
    )
    scheduler.start()
    logger.info("沙箱回收任务已启动，间隔 %s 秒", SCAN_INTERVAL_SECONDS)

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()
