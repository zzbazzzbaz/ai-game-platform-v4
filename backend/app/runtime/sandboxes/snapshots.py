from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import oss2

from app.config import settings


@dataclass(frozen=True)
class SnapshotInfo:
    key: str
    size: int
    etag: str


class SnapshotStore:
    """阿里云 OSS 上的工作区 tar.gz 快照。"""

    def __init__(self) -> None:
        if settings.oss_security_token:
            auth = oss2.StsAuth(
                settings.oss_access_key_id,
                settings.oss_access_key_secret,
                settings.oss_security_token,
            )
        else:
            auth = oss2.Auth(
                settings.oss_access_key_id, settings.oss_access_key_secret
            )
        self._bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
        if settings.oss_proxy:
            self._bucket.session.session.proxies = {
                "http": settings.oss_proxy,
                "https": settings.oss_proxy,
            }

    def new_key(self, game_id: uuid.UUID) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{settings.oss_prefix.strip('/')}/games/{game_id}/workspace/{stamp}.tar.gz"

    def prefix(self, game_id: uuid.UUID) -> str:
        return f"{settings.oss_prefix.strip('/')}/games/{game_id}/"

    async def presign_put(self, key: str, *, expires: int = 3600) -> str:
        return await asyncio.to_thread(
            self._bucket.sign_url, "PUT", key, expires, slash_safe=True
        )

    async def presign_get(self, key: str, *, expires: int = 3600) -> str:
        return await asyncio.to_thread(
            self._bucket.sign_url, "GET", key, expires, slash_safe=True
        )

    async def head(self, key: str) -> SnapshotInfo | None:
        def _head() -> SnapshotInfo | None:
            try:
                result = self._bucket.head_object(key)
            except oss2.exceptions.NoSuchKey:
                return None
            except oss2.exceptions.NotFound:
                return None
            return SnapshotInfo(
                key=key,
                size=int(result.content_length or 0),
                etag=str(result.etag or ""),
            )

        return await asyncio.to_thread(_head)

    async def delete_prefix(self, game_id: uuid.UUID) -> int:
        prefix = self.prefix(game_id)

        def _delete() -> int:
            keys = [obj.key for obj in oss2.ObjectIterator(self._bucket, prefix=prefix)]
            for start in range(0, len(keys), 1000):
                self._bucket.batch_delete_objects(keys[start : start + 1000])
            return len(keys)

        return await asyncio.to_thread(_delete)

    async def list_keys(self, game_id: uuid.UUID) -> list[str]:
        prefix = self.prefix(game_id)
        return await asyncio.to_thread(
            lambda: [obj.key for obj in oss2.ObjectIterator(self._bucket, prefix=prefix)]
        )

    async def put_text(self, key: str, text: str) -> None:
        await asyncio.to_thread(self._bucket.put_object, key, text.encode())

    async def put_file(self, key: str, path: str) -> None:
        await asyncio.to_thread(self._bucket.put_object_from_file, key, path)

    async def get_bytes(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            try:
                return self._bucket.get_object(key).read()
            except oss2.exceptions.NoSuchKey:
                return None
            except oss2.exceptions.NotFound:
                return None

        return await asyncio.to_thread(_get)

    async def describe(self) -> dict[str, Any]:
        return {
            "endpoint": settings.oss_endpoint,
            "bucket": settings.oss_bucket,
            "prefix": settings.oss_prefix,
        }
