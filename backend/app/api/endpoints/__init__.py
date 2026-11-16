from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import auth, chat, conversations, runs, sandbox

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(runs.router)
api_router.include_router(sandbox.router)

__all__ = ["api_router"]
