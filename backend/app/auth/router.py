from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.auth.security import (
    hash_password,
    hash_token,
    new_session_token,
    token_from_cookie,
    verify_password,
)
from app.config import settings
from app.db import get_session
from app.models import Session, User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(id=str(user.id), email=user.email)


@router.post("/auth/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    token, token_hash = new_session_token()
    session.add(
        Session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await session.commit()

    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return UserOut.from_user(user)


@router.post("/auth/register", response_model=UserOut)
async def register(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    existing = await session.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")
    if len(body.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少 6 位")

    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token, token_hash = new_session_token()
    session.add(
        Session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await session.commit()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return UserOut.from_user(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    cookie = request.cookies.get(settings.session_cookie)
    token = token_from_cookie(cookie) if cookie else None
    if token is not None:
        await session.execute(delete(Session).where(Session.token_hash == hash_token(token)))
        await session.commit()
    response.delete_cookie(settings.session_cookie, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    return UserOut.from_user(user)


@router.post("/auth/demo", response_model=UserOut)
async def demo_login(response: Response, session: AsyncSession = Depends(get_session)) -> UserOut:
    """演示账号一键登录。"""
    user = await session.scalar(select(User).where(User.email == settings.demo_email))
    if user is None:
        user = User(email=settings.demo_email, password_hash=hash_password(settings.demo_password))
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token, token_hash = new_session_token()
    session.add(
        Session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await session.commit()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return UserOut.from_user(user)
