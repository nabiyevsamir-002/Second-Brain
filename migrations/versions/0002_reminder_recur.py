"""add reminders.recur (recurring reminders)

Revision ID: 0002_reminder_recur
Revises: 0001_initial
Create Date: 2026-08-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002_reminder_recur"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = birdəfəlik, 'daily' = hər gün, 'weekly' = hər həftə.
    op.add_column("reminders", sa.Column("recur", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "recur")
