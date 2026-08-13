"""Qeyd tutma iş axını (Phase 1 core).

capture_note: mətn/səs qeyd → Claude təmizləyir+kateqoriyalayır → embedding →
DB-yə saxla → istifadə logu. Provayderlər (llm/embedder) yoxdursa, qeyd xam
(raw) saxlanılır — sistem açar olmadan da işləyir.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_conf import get_logger
from app.models import Note, NoteSource
from app.providers.llm_claude import ClaudeLLMProvider
from app.repositories.notes import create_note
from app.repositories.usage import log_usage

log = get_logger("notes")

CLEAN_SYSTEM = (
    "Sən qeyd emalı köməkçisisən. Sənə istifadəçinin qeydi (mətn və ya səsdən "
    "çıxarılmış transkript) verilir. Vəzifən:\n"
    "1) cleaned_text: qeydi orijinal dildə (adətən Azərbaycanca) səliqəyə sal — "
    "transkript/durğu səhvlərini düzəlt, mənanı DƏYİŞMƏ, yeni məlumat ƏLAVƏ ETMƏ.\n"
    "2) summary: 1 qısa cümləlik xülasə (qeydin dilində).\n"
    "3) category: bir sözlük kateqoriya (məs: iş, şəxsi, ideya, tapşırıq, sağlamlıq, maliyyə).\n"
    "4) tags: 1-5 qısa açar söz (kiçik hərflərlə).\n\n"
    'YALNIZ bu JSON obyektini qaytar, başqa heç nə yazma:\n'
    '{"cleaned_text": "...", "summary": "...", "category": "...", "tags": ["...", "..."]}'
)


def _parse_json(text: str) -> dict[str, Any]:
    """Modelin cavabından JSON çıxar (kod bloku və artıq mətnə qarşı davamlı)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


async def _clean_and_categorize(
    session: AsyncSession, llm: ClaudeLLMProvider, user_id: int, raw_text: str
) -> dict[str, Any]:
    resp = await llm.complete(
        system=CLEAN_SYSTEM,
        messages=[{"role": "user", "content": raw_text}],
        model=settings.claude_model_fast,
        max_tokens=1024,
    )
    meta = _parse_json(llm.text_of(resp))
    try:
        tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
        await log_usage(session, user_id, "llm", tokens=tokens)
    except Exception:  # noqa: BLE001 — usage logu kritik deyil
        pass
    return meta


async def capture_note(
    session: AsyncSession,
    user_id: int,
    raw_text: str,
    source: NoteSource,
    *,
    llm: ClaudeLLMProvider | None = None,
    embedder: Any | None = None,
) -> Note:
    cleaned_text: str | None = None
    summary: str | None = None
    category: str | None = None
    tags: list[str] = []
    embedding: list[float] | None = None

    if llm is not None:
        meta = await _clean_and_categorize(session, llm, user_id, raw_text)
        cleaned_text = (meta.get("cleaned_text") or "").strip() or None
        summary = (meta.get("summary") or "").strip() or None
        category = (meta.get("category") or "").strip() or None
        raw_tags = meta.get("tags") or []
        if isinstance(raw_tags, list):
            tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()][:5]

    if embedder is not None:
        text_to_embed = cleaned_text or raw_text
        embedding = await embedder.embed_one(text_to_embed)
        try:
            await log_usage(
                session, user_id, "embed", tokens=getattr(embedder, "last_total_tokens", 0)
            )
        except Exception:  # noqa: BLE001
            pass

    note = await create_note(
        session,
        user_id,
        raw_text,
        source,
        cleaned_text=cleaned_text,
        summary=summary,
        category=category,
        tags=tags,
        embedding=embedding,
    )
    log.info(
        "note_saved",
        note_id=note.id,
        user_id=user_id,
        source=source.value,
        category=category,
        embedded=embedding is not None,
    )
    return note
