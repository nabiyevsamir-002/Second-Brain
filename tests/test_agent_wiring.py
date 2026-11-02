import asyncio
from types import SimpleNamespace

from telegram.ext import CommandHandler

from app.agent.agent import BrainAgent, build_system
from app.bot.telegram_app import BOT_COMMANDS, build_application
from app.config import settings
from app.tools.base import ToolContext
from app.tools.get_related_notes import GetRelatedNotesTool


def _agent(monkeypatch) -> BrainAgent:
    monkeypatch.setattr(settings, "escalation_enabled", True)
    return BrainAgent(SimpleNamespace(model_fast="haiku", model_smart="sonnet"))


def test_related_tool_is_offered_to_the_agent(monkeypatch):
    agent = _agent(monkeypatch)
    names = [s["name"] for s in agent._tool_schemas]
    assert "get_related_notes" in names
    assert "cache_control" in agent._tool_schemas[-1]  # prompt caching breakpoint sonda qalır
    assert "get_related_notes" in build_system()


def test_over_budget_turns_off_escalation(monkeypatch):
    agent = _agent(monkeypatch)
    hard = "Bu iki planı müqayisə et"
    assert agent._pick_model(hard) == "sonnet"
    assert agent._pick_model(hard, allow_escalation=False) == "haiku"
    assert agent._pick_model("salam") == "haiku"


class _Session:
    def __init__(self, note):
        self.note = note

    async def get(self, model, pk):
        return self.note


def test_related_tool_validates_ids_and_ownership():
    tool = GetRelatedNotesTool()
    foreign = SimpleNamespace(id=5, user_id=999)  # başqa istifadəçinin qeydi
    ctx = ToolContext(
        session=_Session(foreign), user_id=1, llm=None, embedder=None, source=None
    )
    assert asyncio.run(tool.run(ctx, note_id="abc")) == "note_id rəqəm olmalıdır (məs. 12)."
    assert asyncio.run(tool.run(ctx, note_id="#5")) == "#5 nömrəli qeyd tapılmadı."


def test_menu_commands_are_all_registered(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST-token")
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    app = build_application()
    registered = {
        cmd
        for group in app.handlers.values()
        for h in group
        if isinstance(h, CommandHandler)
        for cmd in h.commands
    }
    assert {c.command for c in BOT_COMMANDS} <= registered
