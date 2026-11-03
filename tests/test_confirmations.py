"""Dəqiq vaxt təsdiqi alətin özündən gəlir — LLM həftə gününü səhv yaza bilir."""

import asyncio
from types import SimpleNamespace

import app.tools.create_reminder as reminder_mod
import app.tools.create_task as task_mod
from app.tools.base import ToolContext, with_confirmations


def _ctx() -> ToolContext:
    return ToolContext(session=None, user_id=1, llm=None, embedder=None, source=None)


def test_create_reminder_adds_exact_time_line(monkeypatch):
    async def fake_create(session, user_id, text, when, recur=None):
        return SimpleNamespace(id=5, recur=recur)

    monkeypatch.setattr(reminder_mod, "create_reminder", fake_create)
    tool, ctx = reminder_mod.CreateReminderTool(), _ctx()
    out = asyncio.run(tool.run(ctx, text="Həkimə zəng et", remind_at="2026-11-04T09:00"))
    assert ctx.confirmations == ["⏰ Xatırlatma #5: 2026-11-04 09:00 (Çərşənbə)"]
    assert "təkrar yazma" in out


def test_create_task_adds_deadline_line_only_with_due(monkeypatch):
    async def fake_create(session, user_id, title, **kw):
        return SimpleNamespace(id=3, recur=kw.get("recur"))

    monkeypatch.setattr(task_mod, "create_task", fake_create)
    tool, with_due, no_due = task_mod.CreateTaskTool(), _ctx(), _ctx()
    asyncio.run(tool.run(with_due, title="Hesabat", due_at="2026-11-06T18:00"))
    asyncio.run(tool.run(no_due, title="Kitab oxu"))
    assert with_due.confirmations == ["📌 Tapşırıq #3: deadline 2026-11-06 18:00 (Cümə)"]
    assert no_due.confirmations == []


def test_with_confirmations_appends_lines_after_reply():
    ctx = _ctx()
    assert with_confirmations("Tamam.", ctx) == "Tamam."
    ctx.confirmations += ["⏰ A", "📌 B"]
    reply = with_confirmations("Tamam, xatırladacağam.\n", ctx)
    assert reply == "Tamam, xatırladacağam.\n\n⏰ A\n📌 B"
