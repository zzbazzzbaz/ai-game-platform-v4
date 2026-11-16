from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter
from pydantic_ai.conversation_store import (
    ConversationConflict,
    ConversationEntry,
    ConversationRecord,
    ConversationStore,
)
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.usage import RunUsage
from sqlalchemy import delete, literal_column, null, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.repositories.models import Conversation as ConversationRow
from app.api.repositories.models import ConversationEntryRow

_usage_adapter = TypeAdapter(RunUsage)
_deferred_adapter = TypeAdapter(DeferredToolRequests)


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _scope_user_id(scope: str | None) -> uuid.UUID:
    if not scope:
        raise UserError("新会话必须提供 conversation_scope（当前用户 ID）。")
    return uuid.UUID(scope)


def _dump_usage(usage: RunUsage) -> dict[str, Any]:
    return _usage_adapter.dump_python(usage, mode="json")


def _load_usage(raw: dict[str, Any] | None) -> RunUsage:
    return _usage_adapter.validate_python(raw or {})


def _dump_message(message: Any) -> dict[str, Any]:
    return ModelMessagesTypeAdapter.dump_python([message], mode="json")[0]


def _load_message(raw: dict[str, Any]) -> Any:
    return ModelMessagesTypeAdapter.validate_python([raw])[0]


def _dump_deferred(value: DeferredToolRequests | None) -> dict[str, Any] | None:
    return None if value is None else _deferred_adapter.dump_python(value, mode="json")


def _load_deferred(raw: dict[str, Any] | None) -> DeferredToolRequests | None:
    return None if raw is None else _deferred_adapter.validate_python(raw)


def _record(row: ConversationRow, revision: str) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=str(row.id),
        head_id=str(row.head_id) if row.head_id is not None else None,
        usage=_load_usage(row.usage),
        deferred_tool_requests=_load_deferred(row.deferred_tool_requests),
        scope=str(row.user_id),
        revision=revision,
        updated_at=row.updated_at,
    )


class PostgresConversationStore(ConversationStore):
    """ConversationStore 的 PostgreSQL 实现。

    只使用五个存储原语。`scope` 映射为 `conversations.user_id`，`revision` 使用系统列 `xmin::text`。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def read_record(self, conversation_id: str) -> ConversationRecord | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ConversationRow)
                    .add_columns(literal_column("xmin::text").label("xmin_text"))
                    .where(ConversationRow.id == _uuid(conversation_id))
                )
            ).first()
        if row is None:
            return None
        conversation, revision = row
        return _record(conversation, revision)

    async def read_records(
        self, *, scope: str | None = None, limit: int | None = None
    ) -> Sequence[ConversationRecord]:
        statement = (
            select(ConversationRow)
            .add_columns(literal_column("xmin::text").label("xmin_text"))
            .order_by(ConversationRow.updated_at.desc())
        )
        if scope is not None:
            statement = statement.where(ConversationRow.user_id == _scope_user_id(scope))
        if limit is not None:
            statement = statement.limit(limit)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [_record(row[0], row[1]) for row in rows]

    async def read_entry(self, entry_id: str) -> ConversationEntry:
        async with self._sessions() as session:
            row = await session.get(ConversationEntryRow, _uuid(entry_id))
        if row is None:
            raise KeyError(entry_id)
        return ConversationEntry(
            id=str(row.id),
            parent_id=str(row.parent_id) if row.parent_id is not None else None,
            message=_load_message(row.message),
        )

    async def read_history(
        self, head_id: str | None, *, limit: int | None = None
    ) -> list[ConversationEntry]:
        if head_id is None:
            return []
        # 一条递归 CTE 取出整条链，避免逐条 entry 查询。
        order = "ASC" if limit is not None else "DESC"
        statement = text(
            f"""
            WITH RECURSIVE chain(id, parent_id, message, depth) AS (
                SELECT id, parent_id, message, 0
                FROM conversation_entries
                WHERE id = :head_id
                UNION ALL
                SELECT e.id, e.parent_id, e.message, chain.depth + 1
                FROM conversation_entries e
                JOIN chain ON e.id = chain.parent_id
            )
            SELECT id, parent_id, message FROM chain ORDER BY depth {order}
            {"LIMIT :limit" if limit is not None else ""}
            """
        )
        params: dict[str, Any] = {"head_id": _uuid(head_id)}
        if limit is not None:
            params["limit"] = limit
        async with self._sessions() as session:
            rows = (await session.execute(statement, params)).all()
        if not rows:
            raise KeyError(head_id)
        entries = [
            ConversationEntry(
                id=str(row.id),
                parent_id=str(row.parent_id) if row.parent_id is not None else None,
                message=_load_message(row.message),
            )
            for row in rows
        ]
        if limit is not None:
            entries.reverse()
        return entries

    async def write_record(
        self,
        record: ConversationRecord,
        *,
        new_entries: Sequence[ConversationEntry] = (),
        expected_revision: str | None,
    ) -> None:
        conversation_id = _uuid(record.conversation_id)
        head_id = _uuid(record.head_id) if record.head_id is not None else None
        new_ids = {entry.id for entry in new_entries}
        now = datetime.now(UTC)
        values = {
            "head_id": head_id,
            "usage": _dump_usage(record.usage),
            "deferred_tool_requests": (
                _dump_deferred(record.deferred_tool_requests)
                if record.deferred_tool_requests is not None
                else null()
            ),
            "updated_at": now,
        }
        try:
            async with self._sessions() as session, session.begin():
                if expected_revision is None:
                    user_id = _scope_user_id(record.scope)
                    session.add(
                        ConversationRow(
                            id=conversation_id,
                            user_id=user_id,
                            title="新会话",
                            head_id=None,
                            usage={},
                        )
                    )
                    await session.flush()
                elif head_id is not None and record.head_id not in new_ids:
                    exists = await session.scalar(
                        select(ConversationEntryRow.id).where(ConversationEntryRow.id == head_id)
                    )
                    if exists is None:
                        raise ConversationConflict(record.conversation_id)

                for entry in new_entries:
                    session.add(
                        ConversationEntryRow(
                            id=_uuid(entry.id),
                            conversation_id=conversation_id,
                            parent_id=_uuid(entry.parent_id) if entry.parent_id is not None else None,
                            message=_dump_message(entry.message),
                        )
                    )
                await session.flush()

                if expected_revision is None:
                    await session.execute(
                        update(ConversationRow)
                        .where(ConversationRow.id == conversation_id)
                        .values(**values)
                    )
                else:
                    result = await session.execute(
                        update(ConversationRow)
                        .where(
                            ConversationRow.id == conversation_id,
                            literal_column("xmin::text") == expected_revision,
                        )
                        .values(**values)
                    )
                    if result.rowcount == 0:
                        raise ConversationConflict(record.conversation_id)

                revision = await session.scalar(
                    select(literal_column("xmin::text")).where(ConversationRow.id == conversation_id)
                )
                record.revision = revision
        except IntegrityError as error:
            raise ConversationConflict(record.conversation_id) from error

    async def delete_record(self, conversation_id: str, *, expected_revision: str) -> None:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                delete(ConversationRow).where(
                    ConversationRow.id == _uuid(conversation_id),
                    literal_column("xmin::text") == expected_revision,
                )
            )
            if result.rowcount == 0:
                raise ConversationConflict(conversation_id)
