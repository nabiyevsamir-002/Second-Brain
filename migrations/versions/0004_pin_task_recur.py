"""add notes.pinned, tasks.recur, tasks.completed_at

Revision ID: 0004_pin_task_recur
Revises: 0003_note_source_photo
Create Date: 2026-08-17

Additive nullable/default sütunlar — mövcud data üçün təhlükəsiz.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_pin_task_recur"
down_revision: Union[str, None] = "0003_note_source_photo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("tasks", sa.Column("recur", sa.String(length=20), nullable=True))
    op.add_column(
        "tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "recur")
    op.drop_column("notes", "pinned")
