from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _signature(token: str) -> str:
    return hmac.new(
        settings.session_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> tuple[str, str]:
    """返回 (Cookie 值, 入库哈希)。Cookie 值由随机令牌和 HMAC 签名组成。"""
    token = secrets.token_urlsafe(32)
    return f"{token}.{_signature(token)}", hash_token(token)


def token_from_cookie(value: str) -> str | None:
    """校验 Cookie 签名，返回原始令牌；签名不匹配时返回 None。"""
    token, separator, signature = value.rpartition(".")
    if not separator or not token:
        return None
    if not hmac.compare_digest(signature, _signature(token)):
        return None
    return token
