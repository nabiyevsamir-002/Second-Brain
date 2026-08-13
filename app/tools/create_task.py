"""create_task tool — açıq tapşırıq (todo) yarat."""

from __future__ import annotations

from typing import Any

from app.repositories.tasks import create_task
from app.timeutils import fmt_local, parse_local_iso
from app.tools.base import Tool, ToolContext


class CreateTaskTool(Tool):
    name = "create_task"
    description = (
        "İstifadəçi görüləcək iş / tapşırıq (todo) əlavə etmək istəyəndə çağır "
        "(məs: 'API sənədini oxumaq tapşırığı əlavə et', 'sabaha qədər hesabatı bitir'). "
        "Vaxt (deadline) qeyd olunubsa due_at ver, yoxdursa boş burax."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Tapşırığın qısa başlığı."},
            "due_at": {
                "type": "string",
                "description": (
                    "İstəyə bağlı deadline — local (Asia/Baku) ISO: YYYY-MM-DDTHH:MM. "
                    "Vaxt yoxdursa bu sahəni ötür."
                ),
            },
        },
        "required": ["title"],
    }

    async def run(
        self, ctx: ToolContext, title: str = "", due_at: str = "", **_: Any
    ) -> str:
        title = (title or "").strip()
        if not title:
            return "Xəta: tapşırıq başlığı boşdur."

        due = None
        due_str = (due_at or "").strip()
        if due_str:
            try:
                due = parse_local_iso(due_str)
            except (ValueError, TypeError):
                return (
                    f"Xəta: 'due_at' vaxtını oxuya bilmədim ({due_at!r}). "
                    "YYYY-MM-DDTHH:MM formatında ver və ya boş burax."
                )

        # Yeni saxlanmış qeyd varsa, tapşırığı ona bağla (mənbə izlənməsi).
        source_note_id = getattr(getattr(ctx, "saved_note", None), "id", None)
        task = await create_task(
            ctx.session, ctx.user_id, title, due_at=due, source_note_id=source_note_id
        )

        out = f"Tapşırıq #{task.id} əlavə olundu: «{title}»"
        if due is not None:
            out += f" — deadline {fmt_local(due)}"
        return out + "."
