"""Səsli mesaj: yükləmənin təkrarı, aydın xəta, çevrilmə boyu «yazır…», Telegram timeout-ları."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest, TimedOut

from app.bot import handlers
from app.bot.telegram_app import build_application
from app.config import settings
from app.models import NoteSource
from app.providers.registry import providers
from app.providers.stt_local import FALLBACK_MODEL, LocalWhisperSTTProvider


class FakeFile:
    async def download_to_drive(self, path) -> None:
        return None


class FakeBot:
    id = 99

    def __init__(self, failures=()) -> None:
        self.failures = list(failures)
        self.calls = 0

    async def get_file(self, file_id):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return FakeFile()


class FakeSTT:
    local = True

    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, path, language=None) -> str:
        self.calls += 1
        await asyncio.sleep(0.01)  # «yazır…» döngəsi işləsin
        return "su içməliyəm"


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.actions: list[str] = []
        self.voice = SimpleNamespace(file_id="F1", duration=3)
        self.audio = None
        self.reply_to_message = None
        self.chat = SimpleNamespace(send_action=self._action)

    async def _action(self, action) -> None:
        self.actions.append(action)

    async def reply_text(self, text, **_kwargs) -> None:
        self.replies.append(text)


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(handlers, "VOICE_RETRY_DELAY_SEC", 0)


@pytest.fixture
def env(monkeypatch):
    """Telegram, DB və agent olmadan note_voice: yaradılan müvəqqəti faylı da izləyir."""
    stt = FakeSTT()
    seen: dict = {"paths": []}
    real_mkstemp = handlers.tempfile.mkstemp

    def mkstemp(**kwargs):
        fd, path = real_mkstemp(**kwargs)
        seen["paths"].append(path)
        return fd, path

    async def rate_ok(update) -> bool:
        return True

    async def run_agent(update, text, source, **kwargs) -> None:
        seen["agent"] = (text, source)

    def no_db():
        raise RuntimeError("DB yoxdur")

    monkeypatch.setattr(handlers.tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(providers, "_providers", {"stt": stt})
    monkeypatch.setattr(handlers, "_rate_ok", rate_ok)
    monkeypatch.setattr(handlers, "_run_agent", run_agent)
    monkeypatch.setattr(handlers, "SessionLocal", no_db)
    return SimpleNamespace(stt=stt, seen=seen, message=FakeMessage())


def _send_voice(env, bot: FakeBot) -> None:
    update = SimpleNamespace(
        message=env.message, effective_user=SimpleNamespace(id=1, full_name="Samir")
    )
    asyncio.run(handlers.note_voice(update, SimpleNamespace(bot=bot)))


def test_download_retries_after_a_timeout():
    bot = FakeBot([TimedOut()])
    asyncio.run(handlers._download_voice(bot, "F1", "/tmp/yoxdur"))
    assert bot.calls == 2


def test_download_gives_up_after_three_attempts():
    bot = FakeBot([TimedOut(), TimedOut(), TimedOut()])
    with pytest.raises(TimedOut):
        asyncio.run(handlers._download_voice(bot, "F1", "/tmp/yoxdur"))
    assert bot.calls == 3


def test_download_does_not_retry_a_rejected_file():
    bot = FakeBot([BadRequest("File is too big")])
    with pytest.raises(BadRequest):
        asyncio.run(handlers._download_voice(bot, "F1", "/tmp/yoxdur"))
    assert bot.calls == 1


def test_failed_download_tells_the_user_and_leaves_no_file(env):
    _send_voice(env, FakeBot([TimedOut(), TimedOut(), TimedOut()]))
    assert env.message.replies == ["🎙 Səsi Telegram-dan yükləmək alınmadı, yenidən göndər."]
    assert env.stt.calls == 0 and "agent" not in env.seen
    assert not os.path.exists(env.seen["paths"][0])


def test_voice_reaches_the_agent_with_typing_shown_and_file_removed(env):
    _send_voice(env, FakeBot())
    assert env.seen["agent"] == ("su içməliyəm", NoteSource.voice)
    assert "typing" in env.message.actions
    assert not os.path.exists(env.seen["paths"][0])


def test_missing_converted_model_falls_back_instead_of_crashing(tmp_path):
    assert LocalWhisperSTTProvider("/models/whisper/yoxdur")._source() == FALLBACK_MODEL
    assert LocalWhisperSTTProvider(str(tmp_path))._source() == str(tmp_path)
    assert LocalWhisperSTTProvider("large-v3")._source() == "large-v3"


def test_telegram_timeouts_are_longer_than_the_defaults(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "1:TEST")
    request = build_application().bot.request
    assert request.read_timeout == 30
