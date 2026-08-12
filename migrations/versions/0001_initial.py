"""initial schema — users, notes, messages, tasks, reminders, note_links, usage_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    # pgvector (init-pgvector.sql onsuz da yaradır — idempotent təhlükəsizlik).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    note_source = postgresql.ENUM(
        "voice", "text", "forward", "pdf", "docx", name="note_source"
    )
    task_status = postgresql.ENUM("open", "done", "cancelled", name="task_status")
    note_source.create(op.get_bind(), checkfirst=True)
    task_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("source", postgresql.ENUM(name="note_source", create_type=False), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_category", "notes", ["category"])
    # RAG üçün cosine HNSW indeksi (pgvector 0.5+).
    op.execute(
        "CREATE INDEX ix_notes_embedding_hnsw ON notes "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="task_status", create_type=False), server_default="open", nullable=False),
        sa.Column("source_note_id", sa.BigInteger(), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_remind_at", "reminders", ["remind_at"])

    op.create_table(
        "note_links",
        sa.Column("note_id", sa.BigInteger(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("related_note_id", sa.BigInteger(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("score", sa.Float(), nullable=False),
    )

    op.create_table(
        "usage_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_usage_log_user_id", "usage_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("usage_log")
    op.drop_table("note_links")
    op.drop_table("reminders")
    op.drop_table("tasks")
    op.drop_table("messages")
    op.drop_index("ix_notes_embedding_hnsw", table_name="notes")
    op.drop_table("notes")
    op.drop_table("users")
    postgresql.ENUM(name="task_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="note_source").drop(op.get_bind(), checkfirst=True)
