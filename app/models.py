"""SQLAlchemy ORM modelləri — DATA MODEL spesifikasiyasına uyğun.

Cədvəllər: users, notes, messages, tasks, reminders, note_links, usage_log.
embedding sütunu pgvector Vector(1536) — LOCKED (text-embedding-3-small).
Sxem Alembic migration ilə yaradılır (bax: migrations/versions/0001_initial.py).
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1536  # LOCKED — text-embedding-3-small


class Base(DeclarativeBase):
    pass


class NoteSource(str, enum.Enum):
    voice = "voice"
    text = "text"
    forward = "forward"
    pdf = "pdf"
    docx = "docx"


class TaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    cancelled = "cancelled"


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = _created_at()

    notes: Mapped[list["Note"]] = relationship(back_populates="user")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default="{}")
    source: Mapped[NoteSource] = mapped_column(
        SAEnum(NoteSource, name="note_source", create_type=False), nullable=False
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped["User"] = relationship(back_populates="notes")


class Message(Base):
    """Chat kontekst yaddaşı."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status", create_type=False),
        nullable=False,
        server_default=TaskStatus.open.value,
    )
    source_note_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Təkrarlanma: NULL = birdəfəlik, 'daily' = hər gün, 'weekly' = hər həftə.
    recur: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class NoteLink(Base):
    """Əlaqəli qeyd kəşfi (related note discovery)."""

    __tablename__ = "note_links"

    note_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    related_note_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)


class UsageLog(Base):
    """Xərc/istifadə izləmə (cost tracking)."""

    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # llm | stt | tts | embed | search
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    created_at: Mapped[datetime] = _created_at()
