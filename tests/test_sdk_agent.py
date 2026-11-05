"""Abunə agenti — prompt, alət sarğısı, icazə siyahısı (CLI işə salınmır)."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import timeutils
from app.agent.agent import VOICE_NOTE
from app.agent.sdk_agent import MCP_SERVER, SDKBrainAgent, _wrap, format_prompt
from app.config import settings
from app.models import NoteSource
from app.providers.errors import SubscriptionLimitError
from app.providers.llm_subscription import RunResult
from app.tools.base import Tool, ToolContext
from app.tools.save_note import META_PROPERTIES, SaveNoteTool


class EchoTool(Tool):
    name = "echo"
    description = "test"
    input_schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": []}

    def __init__(self, fail=False):
        self.fail = fail
        self.active = 0
        self.max_active = 0

    async def run(self, ctx, x="", **_):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if self.fail:
            raise RuntimeError("bum")
        return f"echo:{x}:{ctx.user_id}"


class FakeLLM:
    model_fast, model_smart = "haiku", "sonnet"

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def options(self, **kw):
        return kw

    async def run(self, prompt, options):
        self.calls.append((prompt, options))
        if self.error:
            raise self.error
        return RunResult(text="Cavab", usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                         cost_usd=0.0)


def test_format_prompt_wraps_history_as_context():
    assert format_prompt(None, "salam") == "salam"
    p = format_prompt([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}], "yeni")
    assert p.splitlines() == ["[Son söhbət — yalnız kontekst üçün]", "İstifadəçi: a",
                              "Assistent: b", "[/Son söhbət]", "", "yeni"]


def test_wrapped_tool_runs_serially_and_reports_errors():
    ok, bad = EchoTool(), EchoTool(fail=True)
    ctx = ToolContext(session=None, user_id=7, llm=None, embedder=None, source=None)
    lock, calls = asyncio.Lock(), []

    async def go():
        a, b = _wrap(ok, ctx, lock, calls), _wrap(bad, ctx, lock, calls)
        return await asyncio.gather(a.handler({"x": "1"}), a.handler({"x": "2"}), b.handler({}))

    r1, r2, r3 = asyncio.run(go())
    assert r1 == {"content": [{"type": "text", "text": "echo:1:7"}]} and ok.max_active == 1
    assert r3["is_error"] and "bum" in r3["content"][0]["text"]
    assert calls == ["echo", "echo", "echo"]


def test_handle_allows_only_our_tools_and_websearch(monkeypatch):
    monkeypatch.setattr(settings, "escalation_enabled", True)
    llm = FakeLLM()
    agent = SDKBrainAgent(llm, [EchoTool()])
    reply = asyncio.run(agent.handle(None, 1, "Bu iki planı müqayisə et", NoteSource.text, None))
    assert reply == "Cavab"
    opts = llm.calls[0][1]
    assert opts["tools"] == ["WebSearch"]
    assert opts["allowed_tools"] == [f"mcp__{MCP_SERVER}__echo", "WebSearch"]
    assert opts["model"] == "sonnet"  # mürəkkəb sual → smart
    assert "WebSearch" in opts["system"] and "ETİBARSIZ" in opts["system"]


def test_voice_message_is_marked_for_the_agent_but_not_for_model_choice(monkeypatch):
    monkeypatch.setattr(settings, "escalation_enabled", True)
    llm = FakeLLM()
    agent = SDKBrainAgent(llm, [EchoTool()])
    asyncio.run(agent.handle(None, 1, "salam", NoteSource.voice, None))
    asyncio.run(agent.handle(None, 1, "salam", NoteSource.text, None))
    voice_prompt, voice_opts = llm.calls[0]
    assert voice_prompt == f"{VOICE_NOTE}\nsalam"
    assert voice_opts["model"] == "haiku"  # uzun qeyd sadə mesajı Sonnet-ə qaldırmır
    assert llm.calls[1][0] == "salam"


def test_handle_marks_whether_tools_ran_on_failure():
    agent = SDKBrainAgent(FakeLLM(error=SubscriptionLimitError(123)), [EchoTool()])
    with pytest.raises(SubscriptionLimitError) as info:
        asyncio.run(agent.handle(None, 1, "salam", NoteSource.text, None))
    assert info.value.tools_ran == []


def test_save_note_schema_asks_agent_for_metadata():
    plain, rich = SaveNoteTool(), SaveNoteTool(agent_fills_meta=True)
    assert plain.input_schema["required"] == ["content"]
    assert set(META_PROPERTIES) <= set(rich.input_schema["properties"])
    assert "cleaned_text" in rich.input_schema["required"]
    assert SaveNoteTool.input_schema["required"] == ["content"]  # sinif sxeması pozulmayıb


def test_system_prompt_carries_night_rule_and_date_confirmation(monkeypatch):
    night = datetime(2026, 11, 3, 1, 15, tzinfo=settings.tz)
    monkeypatch.setattr(timeutils, "now_local", lambda: night)
    prompt = SDKBrainAgent(FakeLLM(), [EchoTool()]).system_prompt()
    assert "BU GÜN, 2026-11-03" in prompt  # 01:15-də "sabah" = bu səhər
    assert "ÖZÜN YAZMA" in prompt  # dəqiq vaxtı kod əlavə edir
