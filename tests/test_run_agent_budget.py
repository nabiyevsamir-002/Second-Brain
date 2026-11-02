"""_run_agent əsas axını + soft büdcə: eskalasiya, səsli cavab, bir dəfəlik bildiriş."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot import handlers
from app.models import NoteSource
from app.providers.errors import SubscriptionLimitError
from app.providers.registry import providers
from app.services.budget import BudgetStatus


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.chat = SimpleNamespace(send_action=self._noop)

    async def _noop(self, *_args) -> None:
        return None

    async def reply_text(self, text, **_kwargs) -> None:
        self.replies.append(text)


class FakeAgent:
    def __init__(self) -> None:
        self.allow_escalation: bool | None = None

    async def handle(self, session, user_id, text, source, embedder, history,
                     allow_escalation=True):
        self.allow_escalation = allow_escalation
        return "Cavab"


class FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeSessionLocal:
    async def __aenter__(self) -> FakeSession:
        return FakeSession()

    async def __aexit__(self, *_exc) -> bool:
        return False


@pytest.fixture
def env(monkeypatch):
    agent = FakeAgent()
    user = SimpleNamespace(telegram_id=1, settings={})
    status = {"now": BudgetStatus("ok", Decimal("1"), Decimal("20"))}
    spoken: list[str] = []

    async def get_or_create_user(session, uid, name=None):
        return user

    async def get_recent_messages(session, uid, limit=6):
        return []

    async def add_message(session, uid, role, content):
        return None

    async def get_budget_status(session, uid):
        return status["now"]

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}
        return user.settings

    async def speak(update, text, voice_name=None):
        spoken.append(text)

    monkeypatch.setattr(providers, "_providers", {"agent": agent, "embed": object()})
    monkeypatch.setattr(handlers, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(handlers, "get_or_create_user", get_or_create_user)
    monkeypatch.setattr(handlers, "get_recent_messages", get_recent_messages)
    monkeypatch.setattr(handlers, "add_message", add_message)
    monkeypatch.setattr(handlers, "get_budget_status", get_budget_status)
    monkeypatch.setattr(handlers, "update_settings", update_settings)
    monkeypatch.setattr(handlers, "_speak_reply", speak)
    return SimpleNamespace(agent=agent, user=user, status=status, spoken=spoken)


def _send(text: str, source: NoteSource, voice: bool = False) -> FakeMessage:
    msg = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1, full_name="Samir"), message=msg
    )
    asyncio.run(handlers._run_agent(update, text, source, input_is_voice=voice))
    return msg


def test_normal_budget_keeps_escalation_and_voice_mirror(env):
    msg = _send("salam", NoteSource.voice, voice=True)
    assert env.agent.allow_escalation is True
    assert msg.replies == ["Cavab"]
    assert env.spoken == ["Cavab"]


def test_over_budget_degrades_and_notifies_once(env):
    env.status["now"] = BudgetStatus("over", Decimal("21"), Decimal("20"))

    msg = _send("salam", NoteSource.voice, voice=True)
    assert env.agent.allow_escalation is False
    assert env.spoken == []  # soft rejim: səsli cavab yoxdur
    assert msg.replies[0] == "Cavab"
    assert "limiti keçildi" in msg.replies[1]
    assert env.user.settings["budget_notified"].endswith(":over")

    again = _send("yenə", NoteSource.text)
    assert again.replies == ["Cavab"]  # bildiriş bu ay təkrar getmir


def test_budget_check_failure_after_reply_keeps_the_answer(env, monkeypatch):
    calls = {"n": 0}

    async def flaky(session, uid):
        calls["n"] += 1
        if calls["n"] > 1:  # cavabdan sonrakı yoxlama
            raise RuntimeError("db düşdü")
        return BudgetStatus("ok", Decimal("1"), Decimal("20"))

    monkeypatch.setattr(handlers, "get_budget_status", flaky)
    msg = _send("salam", NoteSource.voice, voice=True)
    assert msg.replies == ["Cavab"]
    assert env.spoken == ["Cavab"]


@pytest.fixture
def saved_raw(monkeypatch):
    saved: list[str] = []

    async def capture(session, uid, raw, source, embedder=None, **_kw):
        saved.append(raw)
        return SimpleNamespace(id=77)

    monkeypatch.setattr(handlers, "capture_note", capture)
    return saved


def test_subscription_limit_keeps_the_message(env, monkeypatch, saved_raw):
    async def limited(*_a, **_kw):
        raise SubscriptionLimitError(1793628000)

    monkeypatch.setattr(env.agent, "handle", limited)
    msg = _send("sabah həkimə zəng et", NoteSource.text)
    assert saved_raw == ["sabah həkimə zəng et"]
    assert msg.replies == [
        "⏳ Claude abunə limiti doldu — 2026-11-02 18:00-də bərpa olunur.\n"
        "📝 Mesajın itməsin deyə xam qeyd #77 kimi saxladım."
    ]


def test_limit_after_a_tool_ran_does_not_duplicate(env, monkeypatch, saved_raw):
    async def limited(*_a, **_kw):
        err = SubscriptionLimitError(None)
        err.tools_ran = ["save_note"]
        raise err

    monkeypatch.setattr(env.agent, "handle", limited)
    msg = _send("qeyd et: test", NoteSource.text)
    assert saved_raw == [] and msg.replies == ["⏳ Claude abunə limiti doldu."]
