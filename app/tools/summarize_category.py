"""summarize_category tool — bir kateqoriyanın qeydlərini yığıb agentə xülasə üçün verir."""

from __future__ import annotations

from typing import Any

from app.repositories.notes import list_notes
from app.tools.base import Tool, ToolContext

MAX_NOTES = 40


class SummarizeCategoryTool(Tool):
    name = "summarize_category"
    description = (
        "İstifadəçi bir kateqoriyanın/mövzunun qeydlərinin XÜLASƏSİNİ istəyəndə çağır "
        "(məs: 'iş qeydlərimi xülasə et', 'ideyalarımı ümumiləşdir'). category = kateqoriya adı "
        "(iş, şəxsi, ideya, sağlamlıq, maliyyə və s.). Nəticəni oxuyub qısa, aydın xülasə yaz."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Xülasə ediləcək kateqoriya."}
        },
        "required": ["category"],
    }

    async def run(self, ctx: ToolContext, category: str = "", **_: Any) -> str:
        category = (category or "").strip()
        if not category:
            return "Xəta: kateqoriya boşdur."
        notes = await list_notes(ctx.session, ctx.user_id, limit=MAX_NOTES, category=category)
        if not notes:
            return f"'{category}' kateqoriyasında qeyd tapılmadı."
        lines = [f"'{category}' kateqoriyasında {len(notes)} qeyd — bunları qısa xülasə et:"]
        for n in notes:
            when = n.created_at.strftime("%Y-%m-%d")
            body = (n.cleaned_text or n.raw_text or "").strip()
            lines.append(f"[#{n.id}] ({when}) {body}")
        return "\n".join(lines)
