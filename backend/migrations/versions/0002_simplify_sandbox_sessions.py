"""simplify sandbox_sessions

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 一个 conversation 只保留最新的一条 active 记录。
    op.execute("DELETE FROM sandbox_sessions WHERE status <> 'active'")
    op.execute(
        """
        DELETE FROM sandbox_sessions a
        USING sandbox_sessions b
        WHERE a.conversation_id = b.conversation_id
          AND (a.last_used_at, a.id) < (b.last_used_at, b.id)
        """
    )

    op.execute("DROP INDEX IF EXISTS sandbox_sessions_active_conversation_idx")
    op.execute("DROP INDEX IF EXISTS sandbox_sessions_user_last_used_idx")
    op.drop_constraint(
        "sandbox_sessions_status_check",
        "sandbox_sessions",
        type_="check",
    )

    for column in (
        "user_id",
        "provider",
        "template",
        "status",
        "created_at",
        "expires_at",
    ):
        op.drop_column("sandbox_sessions", column)

    op.create_index(
        "sandbox_sessions_conversation_idx",
        "sandbox_sessions",
        ["conversation_id"],
        unique=True,
    )
    op.create_index(
        "sandbox_sessions_last_used_idx",
        "sandbox_sessions",
        ["last_used_at"],
    )


def downgrade() -> None:
    op.drop_index("sandbox_sessions_last_used_idx", table_name="sandbox_sessions")
    op.drop_index("sandbox_sessions_conversation_idx", table_name="sandbox_sessions")

    op.add_column("sandbox_sessions", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column(
        "sandbox_sessions",
        sa.Column("provider", sa.Text(), nullable=False, server_default="e2b"),
    )
    op.add_column(
        "sandbox_sessions",
        sa.Column("template", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "sandbox_sessions",
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )
    op.add_column(
        "sandbox_sessions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "sandbox_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "UPDATE sandbox_sessions s SET user_id = c.user_id "
        "FROM conversations c WHERE c.id = s.conversation_id"
    )
    op.alter_column("sandbox_sessions", "user_id", nullable=False)
    op.create_foreign_key(
        "sandbox_sessions_user_id_fkey",
        "sandbox_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "sandbox_sessions_status_check",
        "sandbox_sessions",
        "status IN ('active', 'paused', 'dead')",
    )
    op.execute(
        "CREATE UNIQUE INDEX sandbox_sessions_active_conversation_idx "
        "ON sandbox_sessions (conversation_id) WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX sandbox_sessions_user_last_used_idx "
        "ON sandbox_sessions (user_id, last_used_at DESC)"
    )
