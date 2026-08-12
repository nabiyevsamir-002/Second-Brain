"""Qeyd (note) repository-si — yaratma, siyahı, vektor axtarışı (RAG)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, NoteSource


async def create_note(
    session: AsyncSession,
    user_id: int,
    raw_text: str,
    source: NoteSource,
    *,
    cleaned_text: str | None = None,
    summary: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    embedding: list[float] | None = None,
) -> Note:
    note = Note(
        user_id=user_id,
        raw_text=raw_text,
        source=source,
        cleaned_text=cleaned_text,
        summary=summary,
        category=category,
        tags=tags or [],
        embedding=embedding,
    )
    session.add(note)
    await session.flush()
    return note


async def list_notes(session: AsyncSession, user_id: int, limit: int = 20) -> list[Note]:
    result = await session.execute(
        select(Note)
        .where(Note.user_id == user_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_note(session: AsyncSession, note_id: int) -> Note | None:
    return await session.get(Note, note_id)


async def search_notes_by_vector(
    session: AsyncSession, user_id: int, embedding: list[float], k: int = 5
) -> list[tuple[Note, float]]:
    """Cosine məsafəyə görə ən yaxın k qeydi qaytarır (RAG top-K).

    Returns: (Note, distance) — distance kiçikdirsə, daha oxşardır.
    """
    distance = Note.embedding.cosine_distance(embedding).label("distance")
    result = await session.execute(
        select(Note, distance)
        .where(Note.user_id == user_id, Note.embedding.is_not(None))
        .order_by(distance)
        .limit(k)
    )
    return [(row[0], float(row[1])) for row in result.all()]
