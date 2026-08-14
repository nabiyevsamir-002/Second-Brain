"""add 'photo' value to note_source enum

Revision ID: 0003_note_source_photo
Revises: 0002_reminder_recur
Create Date: 2026-08-14

Qeyd: PG-də ENUM-a dəyər əlavəsi (ADD VALUE) transaksiya bloku xaricində
işlədilməlidir → autocommit_block. Enum dəyərini geri silmək PG-də dəstəklənmir,
ona görə downgrade no-op-dur (təhlükəsiz).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_note_source_photo"
down_revision: Union[str, None] = "0002_reminder_recur"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE note_source ADD VALUE IF NOT EXISTS 'photo'")


def downgrade() -> None:
    # PG ENUM dəyərini geri silmək dəstəklənmir — no-op.
    pass
