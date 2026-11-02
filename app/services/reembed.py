"""Embedding modeli dəyişəndə (məs. VPS-dən köçürülmüş OpenAI vektorları → lokal model)
qeydləri yenidən embed et.

Fərqli modellərin vektorları müqayisə oluna bilməz. app_meta.embedding_model aktiv modeli
saxlayır; startup-da fərqlidirsə bütün embedding-lər NULL edilir və `backfill_embeddings`
(scheduler, partiyalarla) onları yenidən hesablayır. Bu müddətdə açar söz axtarışı işləyir.
Embedding-i olmayan qeydlər (məs. provayder əlçatmaz olanda saxlanmış) də doldurulur.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppMeta, Note, NoteSource

META_KEY = "embedding_model"
LEGACY_MODEL_ID = "openai:text-embedding-3-small"  # app_meta-dan əvvəlki bütün data


def note_embed_text(note: Note) -> str:
    body = note.cleaned_text or note.raw_text or ""
    if note.source == NoteSource.forward and note.summary:
        body = f"{note.summary}\n{body}"
    return body[:3000]


async def ensure_embedding_model(session: AsyncSession, model_id: str) -> int:
    """Aktiv modeli qeyd et; dəyişibsə köhnə vektorları sil. Silinən sayı qaytarır."""
    row = await session.get(AppMeta, META_KEY)
    current = row.value if row else None
    if current is None:
        has_vectors = await session.scalar(
            select(func.count()).select_from(Note).where(Note.embedding.is_not(None))
        )
        current = LEGACY_MODEL_ID if has_vectors else model_id
    invalidated = 0
    if current != model_id:
        result = await session.execute(
            update(Note).where(Note.embedding.is_not(None)).values(embedding=None)
        )
        invalidated = int(result.rowcount or 0)
    if row is None:
        session.add(AppMeta(key=META_KEY, value=model_id))
    else:
        row.value = model_id
    await session.flush()
    return invalidated


async def backfill_embeddings(session: AsyncSession, embedder: Any, batch: int = 32) -> int:
    """Embedding-i olmayan qeydlərdən bir partiyanı embed et. Doldurulan sayı."""
    result = await session.execute(
        select(Note).where(Note.embedding.is_(None)).order_by(Note.id).limit(batch)
    )
    notes = list(result.scalars().all())
    if not notes:
        return 0
    vectors = await embedder.embed([note_embed_text(n) for n in notes])
    for note, vec in zip(notes, vectors):
        note.embedding = vec
    await session.flush()
    return len(notes)
