from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from pydantic_ai.models import infer_model

from app.config import settings
from app.database import dispose_engine, session_factory
from app.repositories.conversation_store import PostgresConversationStore
from app.services import run_service
from app.services.agent.factory import AgentFactory
from app.services.reaper import SandboxReaper
from app.services.run_manager import RunManager
from app.services.sandbox_registry import SandboxRegistry, create_e2b_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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

    stale = await run_service.fail_stale_runs(session_factory)
    if stale:
        logger.info("已标记 %s 条遗留的 running 记录为 failed", stale)

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
