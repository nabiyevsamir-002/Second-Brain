"""search_notes tool — RAG semantik axtarış (pgvector cosine top-K)."""

from __future__ import annotations

from typing import Any

from app.repositories.notes import search_notes_by_vector
from app.tools.base import Tool, ToolContext


class SearchNotesTool(Tool):
    name = "search_notes"
    description = (
        "İstifadəçinin qeydlərində semantik axtarış. Mövcud qeydlər barədə "
        "suala cavab vermək və ya nəyisə tapmaq üçün çağır. Nəticələr [#id] ilə gəlir — "
        "cavabında istifadə etdiyin qeydləri [#id] kimi sitat gətir."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Axtarış sorğusu."},
            "k": {"type": "integer", "description": "Nəticə sayı (default 5)."},
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str = "", k: int = 5, **_: Any) -> str:
        embedding = await ctx.embedder.embed_one(query)
        hits = await search_notes_by_vector(ctx.session, ctx.user_id, embedding, k=k or 5)
        if not hits:
            return "Heç bir uyğun qeyd tapılmadı."

        lines = []
        for note, dist in hits:
            when = note.created_at.strftime("%Y-%m-%d")
            body = note.cleaned_text or note.raw_text
            lines.append(f"[#{note.id}] ({note.category or 'qeyd'}, {when}) {body}")
        return "\n".join(lines)
