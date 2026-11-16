from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI

from app.config import settings
from app.database import dispose_engine, session_factory
from app.repositories.conversation_store import PostgresConversationStore
from app.runtime.agent.factory import AgentFactory
from app.runtime.agent.model import build_model
from app.runtime.runs.lifecycle import fail_stale_runs
from app.runtime.runs.manager import RunManager
from app.runtime.sandboxes.registry import SandboxRegistry, create_e2b_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            environment=settings.logfire_environment,
        )
    else:
        logfire.configure(
            send_to_logfire=False,
            environment=settings.logfire_environment,
        )
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

    stale = await fail_stale_runs(session_factory)
    if stale:
        logger.info("已标记 %s 条遗留的 running 记录为 failed", stale)

    try:
        yield
    finally:
        await dispose_engine()
