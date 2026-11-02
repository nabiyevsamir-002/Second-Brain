"""get_related_notes tool — qeydlə əlaqəli qeydlər (note_links + vektor qonşuları)."""

from __future__ import annotations

from typing import Any

from app.repositories.links import find_related, related_threshold
from app.repositories.notes import get_note
from app.tools.base import Tool, ToolContext

MAX_RELATED = 10


class GetRelatedNotesTool(Tool):
    name = "get_related_notes"
    description = (
        "Konkret qeydlə (#id) əlaqəli digər qeydləri tap ('#12 ilə əlaqəli nə var?', "
        "'bununla bağlı başqa nə yazmışam?'). Mövzu üzrə ümumi axtarış üçün search_notes "
        "istifadə et. Nəticələr [#id] ilə gəlir — cavabında istifadə etdiyin qeydləri sitat gətir."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "note_id": {"type": "integer", "description": "Qeydin id-si (#12 → 12)."},
            "k": {"type": "integer", "description": "Nəticə sayı (default 5, maks 10)."},
        },
        "required": ["note_id"],
    }

    async def run(self, ctx: ToolContext, note_id: Any = 0, k: int = 5, **_: Any) -> str:
        try:
            nid = int(str(note_id).strip().lstrip("#"))
        except ValueError:
            return "note_id rəqəm olmalıdır (məs. 12)."
        note = await get_note(ctx.session, nid)
        if note is None or note.user_id != ctx.user_id:
            return f"#{nid} nömrəli qeyd tapılmadı."

        k = max(1, min(int(k or 5), MAX_RELATED))
        hits = await find_related(
            ctx.session, ctx.user_id, note, k=k, max_distance=related_threshold(ctx.embedder)
        )
        if not hits:
            return f"#{nid} üçün əlaqəli qeyd tapılmadı."

        lines = [f"#{nid} ilə əlaqəli qeydlər:"]
        for other, score in hits:
            when = other.created_at.strftime("%Y-%m-%d")
            body = other.cleaned_text or other.raw_text
            lines.append(
                f"[#{other.id}] ({other.category or 'qeyd'}, {when}, "
                f"oxşarlıq {round(score * 100)}%) {body}"
            )
        return "\n".join(lines)
