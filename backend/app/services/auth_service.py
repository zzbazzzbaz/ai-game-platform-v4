from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories import users
from app.repositories.models import User
from app.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)


class InvalidCredentialsError(Exception):
    """邮箱不存在或密码不匹配。"""


class EmailTakenError(Exception):
    """邮箱已注册。"""


class WeakPasswordError(Exception):
    """密码长度不足。"""


@dataclass(frozen=True)
class IssuedSession:
    token: str
    max_age: int


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def login(session: AsyncSession, *, email: str, password: str) -> User:
    user = await users.get_by_email(session, _normalize_email(email))
    if user is None or not verify_password(user.password_hash, password):
        raise InvalidCredentialsError
    return user


async def register(session: AsyncSession, *, email: str, password: str) -> User:
    normalized = _normalize_email(email)
    if await users.get_by_email(session, normalized) is not None:
        raise EmailTakenError
    if len(password) < 6:
        raise WeakPasswordError
    return await users.create(
        session,
        email=normalized,
        password_hash=hash_password(password),
    )


async def ensure_demo_user(session: AsyncSession) -> User:
    email = _normalize_email(settings.demo_email)
    user = await users.get_by_email(session, email)
    if user is not None:
        return user
    return await users.create(
        session,
        email=email,
        password_hash=hash_password(settings.demo_password),
    )


async def issue_session(session: AsyncSession, user: User) -> IssuedSession:
    token, token_hash = new_session_token()
    await users.create_session(
        session,
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
    )
    return IssuedSession(token=token, max_age=settings.session_ttl_seconds)


async def revoke_session(session: AsyncSession, token: str) -> None:
    await users.delete_session(session, token_hash=hash_token(token))


async def user_from_token(session: AsyncSession, token: str) -> User | None:
    return await users.get_by_token_hash(
        session,
        hash_token(token),
        now=datetime.now(UTC),
    )
