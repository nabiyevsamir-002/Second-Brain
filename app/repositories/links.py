"""Əlaqəli qeyd (note_links) repository-si."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NoteLink


async def add_link(
    session: AsyncSession, note_id: int, related_note_id: int, score: float
) -> None:
    if note_id == related_note_id:
        return
    existing = await session.get(NoteLink, (note_id, related_note_id))
    if existing is not None:
        return
    session.add(NoteLink(note_id=note_id, related_note_id=related_note_id, score=score))
    await session.flush()
