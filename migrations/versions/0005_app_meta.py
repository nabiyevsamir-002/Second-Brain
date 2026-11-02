"""add app_meta (key-value) — aktiv embedding modelini izləmək üçün

Revision ID: 0005_app_meta
Revises: 0004_pin_task_recur
Create Date: 2026-10-31

Additiv yeni cədvəl — mövcud data üçün təhlükəsiz.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005_app_meta"
down_revision: Union[str, None] = "0004_pin_task_recur"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_meta")
