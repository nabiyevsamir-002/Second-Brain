"""create_reminder tool — vaxtlı xatırlatma yarat (scheduler çatdırır)."""

from __future__ import annotations

from typing import Any

from app.repositories.reminders import create_reminder
from app.timeutils import fmt_local, parse_local_iso
from app.tools.base import Tool, ToolContext


class CreateReminderTool(Tool):
    name = "create_reminder"
    description = (
        "İstifadəçi müəyyən vaxtda xatırladılmaq istəyəndə çağır (məs: 'sabah 9-da "
        "həkimə zəng etməyi xatırlat', '2 saatdan sonra...'). Vaxtı system prompt-dakı "
        "CARİ VAXT-a əsasən hesabla. remind_at yalnız gələcək vaxt olmalıdır. "
        "İstifadəçi TƏKRARLANMA istəyirsə ('hər gün', 'hər həftə') recur ver."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Xatırlatmanın mətni (nə xatırladılacaq).",
            },
            "remind_at": {
                "type": "string",
                "description": (
                    "Local (Asia/Baku) vaxt, ISO formatı: YYYY-MM-DDTHH:MM "
                    "(məs: 2026-08-14T09:00). Saat qurşağı offset-i YAZMA. "
                    "Təkrarlananda İLK baş verəcək vaxtı ver."
                ),
            },
            "recur": {
                "type": "string",
                "enum": ["daily", "weekly"],
                "description": (
                    "Təkrarlanma: 'daily'=hər gün, 'weekly'=hər həftə. "
                    "Birdəfəlikdirsə YAZMA."
                ),
            },
        },
        "required": ["text", "remind_at"],
    }

    async def run(
        self,
        ctx: ToolContext,
        text: str = "",
        remind_at: str = "",
        recur: str | None = None,
        **_: Any,
    ) -> str:
        text = (text or "").strip()
        if not text:
            return "Xəta: xatırlatma mətni boşdur."
        try:
            when = parse_local_iso(remind_at)
        except (ValueError, TypeError):
            return (
                f"Xəta: 'remind_at' vaxtını oxuya bilmədim ({remind_at!r}). "
                "YYYY-MM-DDTHH:MM formatında ver."
            )

        reminder = await create_reminder(ctx.session, ctx.user_id, text, when, recur=recur)
        repeat = {"daily": " (hər gün 🔁)", "weekly": " (hər həftə 🔁)"}.get(
            reminder.recur, ""
        )
        return (
            f"Xatırlatma #{reminder.id} quruldu: «{text}» — {fmt_local(when)}{repeat}. "
            "Vaxtı çatanda sənə yazacağam."
        )
