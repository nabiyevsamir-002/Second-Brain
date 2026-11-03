"""Gündəlik: axşam yekunu mesajına verilən cavab «gündəlik» qeydi kimi saxlanır.

Claude çağırılmır — mətn (və ya səsin transkripti) olduğu kimi saxlanır, embedding lokaldır.
Agent bu qeydləri adi axtarışla tapır («bu həftə necə keçdi?»).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, NoteSource
from app.services.notes_service import capture_note

EVENING_HEADER = "🌙 Günün yekunu"
JOURNAL_CATEGORY = "gündəlik"


def is_journal_reply(msg: Any, bot_id: int) -> bool:
    """Mesaj botun axşam yekunu mesajına verilmiş cavabdırmı (Telegram «Reply»)."""
    parent = getattr(msg, "reply_to_message", None)
    author = getattr(parent, "from_user", None)
    if author is None or author.id != bot_id:
        return False
    return (parent.text or "").startswith(EVENING_HEADER)


async def save_journal(
    session: AsyncSession, user_id: int, text: str, source: NoteSource, embedder: Any | None
) -> Note:
    meta = {"cleaned_text": text, "category": JOURNAL_CATEGORY, "tags": [JOURNAL_CATEGORY]}
    return await capture_note(session, user_id, text, source, embedder=embedder, meta=meta)
