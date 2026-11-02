"""Əlaqəli qeyd (note_links) repository-si."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Note, NoteLink
from app.repositories.notes import search_notes_by_vector

# Cosine məsafə bu həddən kiçikdirsə "əlaqəli" sayılır (kiçik = daha oxşar).
# Empirik: text-embedding-3-small-də əlaqəli qeydlər ~0.60-0.68, əlaqəsizlər ~0.72+.
# Lokal model başqa paylanma verir — provayder öz həddini `related_max_distance` ilə verir.
RELATED_MAX_DISTANCE = 0.68


def related_threshold(embedder: Any = None) -> float:
    """Aktiv embedding modelinə uyğun "əlaqəli" həddi (config > provayder > default)."""
    if settings.related_max_distance > 0:
        return settings.related_max_distance
    return float(getattr(embedder, "related_max_distance", RELATED_MAX_DISTANCE))


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


async def linked_notes(
    session: AsyncSession, user_id: int, note_id: int
) -> list[tuple[Note, float]]:
    """note_links-də saxlanmış əlaqələr — hər iki istiqamətdə, score azalan sırada."""
    result = await session.execute(
        select(NoteLink).where(
            or_(NoteLink.note_id == note_id, NoteLink.related_note_id == note_id)
        )
    )
    scores: dict[int, float] = {}
    for link in result.scalars().all():
        other = link.related_note_id if link.note_id == note_id else link.note_id
        scores[other] = max(scores.get(other, 0.0), link.score)
    if not scores:
        return []
    notes = await session.execute(
        select(Note).where(Note.id.in_(scores), Note.user_id == user_id)
    )
    pairs = [(n, scores[n.id]) for n in notes.scalars().all()]
    return sorted(pairs, key=lambda p: p[1], reverse=True)


async def find_related(
    session: AsyncSession,
    user_id: int,
    note: Note,
    k: int = 5,
    max_distance: float = RELATED_MAX_DISTANCE,
) -> list[tuple[Note, float]]:
    """Qeydlə əlaqəli qeydlər: saxlanmış linklər + embedding-dən canlı qonşular.

    Link yalnız agent `save_note` ilə yaranır — link/PDF/şəkil/`/edit` ilə gələn və ya
    sonradan əlavə olunan qeydlərdə yoxdur. Ona görə eyni həddə (max_distance) vektor
    qonşuları da birləşdirilir. Returns: (Note, score) — score = 1 - cosine məsafə.
    """
    merged = {n.id: (n, s) for n, s in await linked_notes(session, user_id, note.id)}
    if note.embedding is not None:
        hits = await search_notes_by_vector(session, user_id, note.embedding, k=k + 1)
        for other, dist in hits:
            if other.id == note.id or dist > max_distance:
                continue
            score = 1.0 - dist
            if other.id not in merged or merged[other.id][1] < score:
                merged[other.id] = (other, score)
    ranked = sorted(merged.values(), key=lambda p: p[1], reverse=True)
    return ranked[:k]
