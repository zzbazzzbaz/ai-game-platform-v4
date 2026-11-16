from __future__ import annotations

from fastapi import APIRouter

from app.endpoints import auth, chat, conversations, games, maintenance, runs, sandbox

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(games.router)
api_router.include_router(maintenance.router)
api_router.include_router(conversations.router)
api_router.include_router(runs.router)
api_router.include_router(sandbox.router)

__all__ = ["api_router"]
