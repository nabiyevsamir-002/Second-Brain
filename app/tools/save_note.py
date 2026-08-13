"""save_note tool — qeydi saxla + əlaqəli qeyd kəşfi."""

from __future__ import annotations

from typing import Any

from app.repositories.links import add_link
from app.repositories.notes import search_notes_by_vector
from app.services.notes_service import capture_note
from app.tools.base import Tool, ToolContext

# Cosine məsafə bu həddən kiçikdirsə "əlaqəli" sayılır (kiçik = daha oxşar).
# Empirik: text-embedding-3-small-də əlaqəli qeydlər ~0.60-0.68, əlaqəsizlər ~0.72+.
RELATED_MAX_DISTANCE = 0.68


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

    async def run(self, ctx: ToolContext, content: str = "", **_: Any) -> str:
        note = await capture_note(
            ctx.session,
            ctx.user_id,
            content,
            ctx.source,
            llm=ctx.llm,
            embedder=ctx.embedder,
        )
        ctx.saved_note = note

        related: list[Any] = []
        if note.embedding is not None:
            hits = await search_notes_by_vector(ctx.session, ctx.user_id, note.embedding, k=4)
            for other, dist in hits:
                if other.id != note.id and dist <= RELATED_MAX_DISTANCE:
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
