"""activity_report tool — 'bu həftə/dövrdə nə etdim?' üçün fəaliyyət icmalı."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.repositories.notes import category_counts_since, count_notes_since
from app.repositories.reminders import reminders_between
from app.repositories.tasks import count_tasks_completed_since, list_open_tasks
from app.timeutils import now_utc
from app.tools.base import Tool, ToolContext


class ActivityReportTool(Tool):
    name = "activity_report"
    description = (
        "İstifadəçi müəyyən dövrdə NƏ ETDİYİNİ soruşanda çağır (məs: 'bu həftə nə etdim?', "
        "'son 3 gündə nə oldu?'). days = dövr (gün, default 7). Nəticəni oxuyub qısa, "
        "təbii icmal yaz."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Neçə günlük dövr (default 7)."}
        },
    }

    async def run(self, ctx: ToolContext, days: int = 7, **_: Any) -> str:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        days = max(1, min(days, 90))
        now = now_utc()
        since = now - timedelta(days=days)

        n_notes = await count_notes_since(ctx.session, ctx.user_id, since)
        cats = await category_counts_since(ctx.session, ctx.user_id, since)
        done = await count_tasks_completed_since(ctx.session, ctx.user_id, since)
        open_tasks = await list_open_tasks(ctx.session, ctx.user_id, limit=100)
        upcoming = await reminders_between(ctx.session, ctx.user_id, now, now + timedelta(days=days))

        parts = [f"Son {days} günün fəaliyyəti:"]
        parts.append(f"- Əlavə olunan qeyd: {n_notes}")
        if cats:
            parts.append("- Əsas mövzular: " + ", ".join(f"{c} ({n})" for c, n in cats))
        parts.append(f"- Tamamlanan tapşırıq: {done}")
        parts.append(f"- Açıq tapşırıq (hazırda): {len(open_tasks)}")
        parts.append(f"- Növbəti {days} gündə xatırlatma: {len(upcoming)}")
        return "\n".join(parts)
