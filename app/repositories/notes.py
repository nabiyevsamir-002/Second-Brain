"""Qeyd (note) repository-si — yaratma, siyahı, vektor axtarışı (RAG)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
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


async def list_notes(
    session: AsyncSession,
    user_id: int,
    limit: int = 20,
    *,
    category: str | None = None,
    tag: str | None = None,
) -> list[Note]:
    stmt = select(Note).where(Note.user_id == user_id)
    if category:
        stmt = stmt.where(func.lower(Note.category) == category.lower())
    if tag:
        stmt = stmt.where(Note.tags.any(tag.lower()))  # tag = ANY(notes.tags)
    stmt = stmt.order_by(Note.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_note(session: AsyncSession, note_id: int) -> Note | None:
    return await session.get(Note, note_id)


async def all_notes(session: AsyncSession, user_id: int) -> list[Note]:
    """İstifadəçinin bütün qeydləri, köhnədən yeniyə (export üçün)."""
    result = await session.execute(
        select(Note).where(Note.user_id == user_id).order_by(Note.created_at.asc())
    )
    return list(result.scalars().all())


async def delete_note(session: AsyncSession, user_id: int, note_id: int) -> Note | None:
    """Qeydi sil (yalnız sahibinindirsə). Tapılmasa None qaytarır."""
    note = await session.get(Note, note_id)
    if note is None or note.user_id != user_id:
        return None
    await session.delete(note)
    await session.flush()
    return note


async def delete_all_notes(session: AsyncSession, user_id: int) -> int:
    """İstifadəçinin bütün qeydlərini sil, silinən sayını qaytar."""
    notes = await all_notes(session, user_id)
    for note in notes:
        await session.delete(note)
    await session.flush()
    return len(notes)


async def count_notes_since(session: AsyncSession, user_id: int, since: datetime) -> int:
    """`since`-dən bəri yaradılmış qeydlərin sayı (səhər brifinqi üçün)."""
    result = await session.execute(
        select(func.count())
        .select_from(Note)
        .where(Note.user_id == user_id, Note.created_at >= since)
    )
    return int(result.scalar() or 0)


async def category_counts_since(
    session: AsyncSession, user_id: int, since: datetime, limit: int = 5
) -> list[tuple[str, int]]:
    """`since`-dən bəri kateqoriya üzrə qeyd sayı, çoxdan aza (həftəlik digest)."""
    result = await session.execute(
        select(Note.category, func.count())
        .where(
            Note.user_id == user_id,
            Note.created_at >= since,
            Note.category.is_not(None),
        )
        .group_by(Note.category)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [(row[0], int(row[1])) for row in result.all()]


async def search_notes_by_vector(
    session: AsyncSession,
    user_id: int,
    embedding: list[float],
    k: int = 5,
    *,
    category: str | None = None,
    tag: str | None = None,
) -> list[tuple[Note, float]]:
    """Cosine məsafəyə görə ən yaxın k qeydi qaytarır (RAG top-K).

    category/tag verilibsə nəticələr həmin filtr üzrə məhdudlaşır.
    Returns: (Note, distance) — distance kiçikdirsə, daha oxşardır.
    """
    distance = Note.embedding.cosine_distance(embedding).label("distance")
    stmt = select(Note, distance).where(
        Note.user_id == user_id, Note.embedding.is_not(None)
    )
    if category:
        stmt = stmt.where(func.lower(Note.category) == category.lower())
    if tag:
        stmt = stmt.where(Note.tags.any(tag.lower()))
    stmt = stmt.order_by(distance).limit(k)
    result = await session.execute(stmt)
    return [(row[0], float(row[1])) for row in result.all()]


# --- Hybrid axtarış (vektor + açar söz) ----------------------------------
# Qısa/dəqiq sorğularda (ad, nömrə, konkret söz) yalnız vektor bəzən zəif olur.
# Açar söz ILIKE uyğunluğu vektor oxşarlığı ilə birləşdirilir → dəqiqlik↑.
_KW_MIN_LEN = 3          # bu uzunluqdan qısa tokenlər açar söz sayılmır
_KEYWORD_BONUS = 0.15    # açar söz uyğunluğu olan qeydə əlavə bal
_KEYWORD_ONLY_BASE = 0.45  # yalnız açar söz uyğunluğu (vektorda yox) — baza bal


def _keywords(query: str) -> list[str]:
    return [t for t in (query or "").lower().split() if len(t) >= _KW_MIN_LEN][:6]


async def keyword_search_notes(
    session: AsyncSession,
    user_id: int,
    terms: list[str],
    limit: int = 15,
    *,
    category: str | None = None,
    tag: str | None = None,
) -> list[Note]:
    """cleaned_text/raw_text/summary sahələrində açar söz (ILIKE) uyğunluğu."""
    if not terms:
        return []
    conds = []
    for term in terms:
        like = f"%{term}%"
        conds.extend(
            [Note.cleaned_text.ilike(like), Note.raw_text.ilike(like), Note.summary.ilike(like)]
        )
    stmt = select(Note).where(Note.user_id == user_id, or_(*conds))
    if category:
        stmt = stmt.where(func.lower(Note.category) == category.lower())
    if tag:
        stmt = stmt.where(Note.tags.any(tag.lower()))
    stmt = stmt.order_by(Note.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def hybrid_search_notes(
    session: AsyncSession,
    user_id: int,
    embedding: list[float],
    query: str,
    k: int = 5,
    *,
    category: str | None = None,
    tag: str | None = None,
) -> list[tuple[Note, float]]:
    """Vektor + açar söz nəticələrini birləşdir, birləşik bala görə sırala.

    Qaytarılan distance GÖSTƏRİŞ üçün vektor məsafəsidir (kiçik=oxşar); sıralama
    isə birləşik bala (vektor oxşarlıq + açar söz bonusu) əsaslanır.
    """
    terms = _keywords(query)
    vec = await search_notes_by_vector(
        session, user_id, embedding, k=k * 3, category=category, tag=tag
    )
    kw = (
        await keyword_search_notes(session, user_id, terms, limit=k * 3, category=category, tag=tag)
        if terms
        else []
    )
    kw_ids = {n.id for n in kw}

    # id -> [note, display_distance, score]
    scored: dict[int, list] = {}
    for note, dist in vec:
        scored[note.id] = [note, dist, max(0.0, 1.0 - dist)]
    for note in kw:
        if note.id not in scored:
            scored[note.id] = [note, 1.0 - _KEYWORD_ONLY_BASE, _KEYWORD_ONLY_BASE]
    for nid, entry in scored.items():
        if nid in kw_ids:
            entry[2] += _KEYWORD_BONUS

    ranked = sorted(scored.values(), key=lambda e: e[2], reverse=True)[:k]
    return [(e[0], e[1]) for e in ranked]
