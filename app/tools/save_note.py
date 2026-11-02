"""save_note tool — qeydi saxla + əlaqəli qeyd kəşfi."""

from __future__ import annotations

from typing import Any

from app.repositories.links import add_link, related_threshold
from app.repositories.notes import search_notes_by_vector
from app.services.notes_service import capture_note
from app.tools.base import Tool, ToolContext

# Abunə agenti (SDKBrainAgent) təmizləmə/kateqoriyanı özü doldurur — əlavə LLM çağırışı yox.
META_PROPERTIES: dict[str, Any] = {
    "cleaned_text": {
        "type": "string",
        "description": "Qeydin səliqəli mətni (orijinal dildə): transkript/durğu səhvlərini "
        "düzəlt, mənanı DƏYİŞMƏ, yeni məlumat ƏLAVƏ ETMƏ.",
    },
    "summary": {"type": "string", "description": "1 qısa cümləlik xülasə (qeydin dilində)."},
    "category": {
        "type": "string",
        "description": "Bir sözlük kateqoriya (məs: iş, şəxsi, ideya, tapşırıq, sağlamlıq, maliyyə).",
    },
    "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "1-5 qısa açar söz (kiçik hərflərlə).",
    },
}


class SaveNoteTool(Tool):
    name = "save_note"
    description = (
        "İstifadəçinin qeydini (fikir, tapşırıq, məlumat, xatırlatma) yadda saxla. "
        "Mesaj nəyisə qeyd etmək məqsədi daşıyırsa bunu çağır."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Saxlanılacaq qeydin mətni."}
        },
        "required": ["content"],
    }

    def __init__(self, agent_fills_meta: bool = False) -> None:
        self.agent_fills_meta = agent_fills_meta
        if agent_fills_meta:
            self.input_schema = {
                "type": "object",
                "properties": {**self.input_schema["properties"], **META_PROPERTIES},
                "required": ["content", "cleaned_text", "summary", "category", "tags"],
            }

    async def run(self, ctx: ToolContext, content: str = "", **kwargs: Any) -> str:
        meta = None
        if self.agent_fills_meta:
            meta = {k: kwargs.get(k) for k in META_PROPERTIES}
        note = await capture_note(
            ctx.session,
            ctx.user_id,
            content,
            ctx.source,
            llm=ctx.llm,
            embedder=ctx.embedder,
            meta=meta,
        )
        ctx.saved_note = note

        related: list[Any] = []
        if note.embedding is not None:
            max_dist = related_threshold(ctx.embedder)
            hits = await search_notes_by_vector(ctx.session, ctx.user_id, note.embedding, k=4)
            for other, dist in hits:
                if other.id != note.id and dist <= max_dist:
                    await add_link(ctx.session, note.id, other.id, score=1.0 - dist)
                    related.append(other)
        ctx.related = related

        out = [
            f"Qeyd #{note.id} saxlanıldı. kateqoriya={note.category or '-'}, "
            f"taglar={note.tags or []}"
        ]
        if related:
            out.append(
                "Əlaqəli qeydlər: "
                + "; ".join(f"#{r.id} {(r.summary or r.raw_text)[:40]}" for r in related)
            )
        return "\n".join(out)
