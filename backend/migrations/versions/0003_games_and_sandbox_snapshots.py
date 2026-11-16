"""add games and per-game sandbox snapshots

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE games (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX games_user_updated_idx ON games (user_id, updated_at DESC)")

    # 老会话各自生成一个游戏；直接用会话 ID 作为 game ID，保证一一对应。
    op.execute(
        """
        INSERT INTO games (id, user_id, name, created_at, updated_at)
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        """
    )

    op.execute("ALTER TABLE conversations ADD COLUMN game_id uuid")
    op.execute("UPDATE conversations SET game_id = id")
    op.execute("ALTER TABLE conversations ALTER COLUMN game_id SET NOT NULL")
    op.execute(
        """
        ALTER TABLE conversations
        ADD CONSTRAINT conversations_game_id_fkey
        FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        """
    )
    op.execute("CREATE INDEX conversations_game_idx ON conversations (game_id)")

    # 老沙箱使用旧模板，直接丢弃映射，下一次按 game 用新模板重建。
    op.execute("DROP TABLE sandbox_sessions")

    op.execute(
        """
        CREATE TABLE sandbox_sessions (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            game_id           uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
            sandbox_id        text,
            lifecycle_state   text NOT NULL DEFAULT 'active',
            snapshot_key      text,
            snapshot_at       timestamptz,
            snapshot_bytes    bigint,
            snapshot_sha256   text,
            last_used_at      timestamptz NOT NULL DEFAULT now(),
            archive_retry_at  timestamptz,
            archive_attempts  integer NOT NULL DEFAULT 0,
            last_error        text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sandbox_sessions_state_check
                CHECK (lifecycle_state IN ('active', 'archiving', 'archived', 'restoring'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX sandbox_sessions_game_idx ON sandbox_sessions (game_id)"
    )
    op.execute(
        "CREATE INDEX sandbox_sessions_last_used_idx ON sandbox_sessions (last_used_at)"
    )
    op.execute(
        "CREATE INDEX sandbox_sessions_retry_idx ON sandbox_sessions (archive_retry_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE sandbox_sessions")
    op.execute(
        """
        CREATE TABLE sandbox_sessions (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sandbox_id      text NOT NULL,
            last_used_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX sandbox_sessions_conversation_idx "
        "ON sandbox_sessions (conversation_id)"
    )
    op.execute(
        "CREATE INDEX sandbox_sessions_last_used_idx ON sandbox_sessions (last_used_at)"
    )
    op.execute("DROP INDEX IF EXISTS conversations_game_idx")
    op.execute("ALTER TABLE conversations DROP CONSTRAINT conversations_game_id_fkey")
    op.execute("ALTER TABLE conversations DROP COLUMN game_id")
    op.execute("DROP TABLE games")
