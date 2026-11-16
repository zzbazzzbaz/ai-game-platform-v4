from __future__ import annotations

from fastapi import APIRouter

from app.endpoint import auth, chat, conversations, runs, sandbox

api_router = APIRouter(prefix="/api")

for module in (auth, chat, conversations, runs, sandbox):
    api_router.include_router(module.router)

__all__ = ["api_router"]
