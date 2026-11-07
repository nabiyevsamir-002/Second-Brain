"""Axşam yekunu: mətn, saat və gündə bir dəfə qaydası, cavabın gündəlik qeydinə çevrilməsi."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.bot import handlers, scheduler
from app.models import NoteSource
from app.providers.registry import providers
from app.services import journal
from app.services.journal import EVENING_HEADER, is_journal_reply

NOW = datetime(2026, 11, 3, 22, 0, tzinfo=ZoneInfo("Asia/Baku"))
BOT_ID = 99


def _task(task_id, title, due=None):
    return SimpleNamespace(id=task_id, title=title, due_at=due)


@pytest.fixture
def day(monkeypatch):
    data = {
        "done": [_task(3, "Hesabat")],
        "open": [_task(5, "Kitab oxu", NOW - timedelta(days=1)), _task(6, "Məktub yaz")],
        "tomorrow": [SimpleNamespace(remind_at=NOW + timedelta(hours=11), text="Həkimə zəng et")],
        "proposals": [{"key": "K1", "items": [{"id": 111}, {"id": 222}]}],
    }

    async def completed(session, uid, start, end, limit=10):
        assert (start, end) == (NOW.replace(hour=0), NOW.replace(hour=0) + timedelta(days=1))
        return data["done"]

    async def open_tasks(session, uid, limit=50):
        return data["open"]

    async def reminders(session, uid, start, end):
        assert start == NOW.replace(hour=0) + timedelta(days=1)  # sabahın 00:00-ı
        return data["tomorrow"]

    async def review_mail(session, uid):
        return data["proposals"]

    monkeypatch.setattr(scheduler, "now_local", lambda: NOW)
    monkeypatch.setattr(scheduler, "now_utc", lambda: NOW.astimezone(timezone.utc))
    monkeypatch.setattr(scheduler, "list_completed_between", completed)
    monkeypatch.setattr(scheduler, "list_open_tasks", open_tasks)
    monkeypatch.setattr(scheduler, "reminders_between", reminders)
    monkeypatch.setattr(scheduler, "_review_mail", review_mail)
    return data


def test_evening_lists_the_day_tomorrow_and_mail_then_asks_about_the_day(day):
    text, kb = asyncio.run(scheduler._build_evening(None, 1))
    assert text.startswith(EVENING_HEADER)
    assert "#3 Hesabat" in text
    assert "Açıq qalır: 2 tapşırıq (1-i gecikib)" in text
    assert "09:00 — Həkimə zəng et" in text
    assert "Lazımsız görünən 2 məktub tapdım" in text
    assert kb.inline_keyboard[0][0].callback_data == "mt:show:K1"
    assert kb.inline_keyboard[0][0].text == "🗑 Bax və sil"
    assert text.endswith("gündəliyinə yazacağam.")


@pytest.mark.parametrize("proposals", [[], [{"key": "K1", "items": []}]])
def test_evening_without_unnecessary_mail_has_no_button(day, proposals):
    day["proposals"] = proposals
    text, kb = asyncio.run(scheduler._build_evening(None, 1))
    assert kb is None and "Lazımsız" not in text


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.sent.append(kwargs)


@pytest.mark.parametrize("hour, user_settings, sent", [
    (22, {}, True),
    (21, {}, False),
    (22, {"evening_last_sent": "2026-11-03"}, False),
    (22, {"evening_enabled": False}, False),
    (20, {"evening_hour": 20}, True),
])
def test_evening_is_sent_once_at_its_hour(day, monkeypatch, hour, user_settings, sent):
    saved = {}

    async def update_settings(session, uid, changes):
        saved.update(changes)

    monkeypatch.setattr(scheduler, "update_settings", update_settings)
    bot = FakeBot()
    asyncio.run(scheduler._maybe_send_evening(
        SimpleNamespace(bot=bot), None, 1, user_settings, NOW.replace(hour=hour), "2026-11-03"
    ))
    assert bool(bot.sent) is sent
    assert saved == ({"evening_last_sent": "2026-11-03"} if sent else {})


def _reply_to(text: str, author_id: int = BOT_ID) -> SimpleNamespace:
    return SimpleNamespace(reply_to_message=SimpleNamespace(
        from_user=SimpleNamespace(id=author_id), text=text
    ))


def test_only_a_reply_to_the_bots_evening_message_is_a_journal_entry():
    assert is_journal_reply(_reply_to(EVENING_HEADER + "\n📅 2026-11-03"), BOT_ID)
    assert not is_journal_reply(_reply_to("⏰ Xatırlatma: Həkimə zəng et"), BOT_ID)
    assert not is_journal_reply(_reply_to(EVENING_HEADER, author_id=5), BOT_ID)
    assert not is_journal_reply(SimpleNamespace(reply_to_message=None), BOT_ID)


def test_save_journal_keeps_the_text_as_is_without_claude(monkeypatch):
    seen = {}

    async def fake_capture(session, uid, text, source, *, llm=None, embedder=None, meta=None):
        seen.update(llm=llm, meta=meta, source=source)
        return SimpleNamespace(id=7)

    monkeypatch.setattr(journal, "capture_note", fake_capture)
    note = asyncio.run(journal.save_journal(None, 1, "Yaxşı keçdi", NoteSource.voice, None))
    assert note.id == 7 and seen["llm"] is None and seen["source"] is NoteSource.voice
    assert seen["meta"] == {
        "cleaned_text": "Yaxşı keçdi", "category": "gündəlik", "tags": ["gündəlik"]
    }


class FakeSessionLocal:
    async def __aenter__(self):
        return SimpleNamespace(commit=self._commit)

    async def __aexit__(self, *_exc) -> bool:
        return False

    @staticmethod
    async def _commit() -> None:
        return None


def test_reply_to_evening_goes_to_the_journal_not_the_agent(monkeypatch):
    saved, replies = [], []

    async def fake_save(session, uid, text, source, embedder):
        saved.append((uid, text, source))
        return SimpleNamespace(id=7)

    async def rate_ok(update):
        return True

    async def get_or_create_user(session, uid, name=None):
        return SimpleNamespace(telegram_id=uid)

    async def no_agent(*_args, **_kwargs):
        raise AssertionError("gündəlik cavabı agentə getməməlidir")

    async def reply_text(text, **_kwargs):
        replies.append(text)

    monkeypatch.setattr(providers, "_providers", {})
    monkeypatch.setattr(handlers, "save_journal", fake_save)
    monkeypatch.setattr(handlers, "_rate_ok", rate_ok)
    monkeypatch.setattr(handlers, "get_or_create_user", get_or_create_user)
    monkeypatch.setattr(handlers, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(handlers, "_run_agent", no_agent)

    msg = _reply_to(EVENING_HEADER)
    msg.text, msg.entities, msg.reply_text = "Bu gün yaxşı keçdi", [], reply_text
    update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=1, full_name="Samir"))
    asyncio.run(handlers.note_text(update, SimpleNamespace(bot=SimpleNamespace(id=BOT_ID))))
    assert saved == [(1, "Bu gün yaxşı keçdi", NoteSource.text)]
    assert replies == ["📝 Gündəliyə yazdım — qeyd #7."]
