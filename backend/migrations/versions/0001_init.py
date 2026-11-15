"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE users (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email         citext NOT NULL UNIQUE,
            password_hash text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE sessions (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash text NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX sessions_user_id_idx ON sessions (user_id)")
    op.execute("CREATE INDEX sessions_expires_at_idx ON sessions (expires_at)")

    op.execute(
        """
        CREATE TABLE conversations (
            id                     uuid PRIMARY KEY,
            user_id                uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title                  text NOT NULL DEFAULT '新会话',
            head_id                uuid,
            usage                  jsonb NOT NULL DEFAULT '{}'::jsonb,
            deferred_tool_requests jsonb,
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX conversations_user_updated_idx ON conversations (user_id, updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE conversation_entries (
            id              uuid PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            parent_id       uuid REFERENCES conversation_entries(id) ON DELETE CASCADE,
            message         jsonb NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX conversation_entries_conversation_created_idx "
        "ON conversation_entries (conversation_id, created_at)"
    )
    op.execute("CREATE INDEX conversation_entries_parent_idx ON conversation_entries (parent_id)")

    op.execute(
        """
        CREATE TABLE sandbox_sessions (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            provider        text NOT NULL DEFAULT 'e2b',
            sandbox_id      text NOT NULL,
            template        text NOT NULL,
            status          text NOT NULL DEFAULT 'active',
            created_at      timestamptz NOT NULL DEFAULT now(),
            last_used_at    timestamptz NOT NULL DEFAULT now(),
            expires_at      timestamptz,
            CONSTRAINT sandbox_sessions_status_check
                CHECK (status IN ('active', 'paused', 'dead'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX sandbox_sessions_active_conversation_idx "
        "ON sandbox_sessions (conversation_id) WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX sandbox_sessions_user_last_used_idx "
        "ON sandbox_sessions (user_id, last_used_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE runs (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status          text NOT NULL,
            model           text NOT NULL,
            started_at      timestamptz NOT NULL DEFAULT now(),
            finished_at     timestamptz,
            usage           jsonb NOT NULL DEFAULT '{}'::jsonb,
            error           jsonb,
            parent_run_id   uuid REFERENCES runs(id) ON DELETE SET NULL,
            CONSTRAINT runs_status_check
                CHECK (status IN ('running', 'waiting_approval', 'completed', 'cancelled', 'failed'))
        )
        """
    )
    op.execute(
        "CREATE INDEX runs_conversation_started_idx ON runs (conversation_id, started_at DESC)"
    )
    op.execute("CREATE INDEX runs_user_status_idx ON runs (user_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS runs")
    op.execute("DROP TABLE IF EXISTS sandbox_sessions")
    op.execute("DROP TABLE IF EXISTS conversation_entries")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
