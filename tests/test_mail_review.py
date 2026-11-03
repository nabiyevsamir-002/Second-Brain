"""Lazımsız məktublar: Claude-un qərarı, siyahı, təsdiq düymələri və geri qaytarma."""

import asyncio
import copy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot import handlers
from app.models import NoteSource
from app.providers.email_imap import Mail
from app.providers.registry import providers
from app.services import mail_review
from app.services.budget import BudgetStatus
from app.tools import email_tools
from app.tools.base import ToolContext

PROPOSAL = {
    "key": "K1", "reviewed": 25, "drop": [], "deliver": False,
    "items": [
        {"id": 111, "from": "Mağaza", "subject": "Endirim 50%", "reason": "endirim reklamı"},
        {"id": 222, "from": "Sosial", "subject": "Yeni bildiriş", "reason": "sosial bildiriş"},
        {"id": 333, "from": "Bülleten", "subject": "Həftənin xəbərləri", "reason": "bülleten"},
    ],
}


class FakeLLM:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.text

    @staticmethod
    def text_of(resp):
        return resp


def _mail(subject: str) -> Mail:
    return Mail(uid=1, sender="Mağaza <m@x.az>", subject=subject, date=None, unread=True,
                snippet="Yalnız bu həftə")


def test_review_maps_numbers_to_mail_ids_and_ignores_unknown_ones():
    items = [(111, _mail("Endirim")), (222, _mail("Faktura")), (333, _mail("Bülleten"))]
    llm = FakeLLM('{"items": [{"id": 1, "verdict": "delete", "reason": "endirim reklamı"},'
                  ' {"id": 2, "verdict": "keep"}, {"id": 9, "verdict": "delete"}]}')
    proposals, keep = asyncio.run(mail_review.review(llm, items))
    assert proposals == [
        {"id": 111, "from": "Mağaza", "subject": "Endirim", "reason": "endirim reklamı"}
    ]
    assert keep == [222]  # 3 cavabsız qaldı → növbəti baxışda yenə yoxlanır
    assert "ETİBARSIZDIR" in llm.calls[0]["system"]


def test_review_fails_loudly_when_the_answer_is_unreadable():
    with pytest.raises(RuntimeError):
        asyncio.run(mail_review.review(FakeLLM("bağışla"), [(111, _mail("X"))]))


def test_build_proposal_stores_the_list_and_remembers_what_to_keep(monkeypatch):
    user = SimpleNamespace(settings={"mail_kept": [5]})

    async def get_user(session, uid):
        return user

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}

    class Box:
        async def cleanup_candidates(self, exclude, limit):
            assert exclude == {5} and limit == mail_review.REVIEW_PER_RUN
            return [(111, _mail("Endirim")), (222, _mail("Faktura"))]

    monkeypatch.setattr(mail_review, "get_user", get_user)
    monkeypatch.setattr(mail_review, "update_settings", update_settings)
    llm = FakeLLM('{"items": [{"id": 1, "verdict": "delete", "reason": "reklam"},'
                  ' {"id": 2, "verdict": "keep"}]}')
    p = asyncio.run(mail_review.build_proposal(None, 1, Box(), llm, deliver=True))
    assert p["reviewed"] == 2 and [it["id"] for it in p["items"]] == [111]
    assert p["deliver"] is True
    assert user.settings["mail_trash"] == p and user.settings["mail_kept"] == [5, 222]


def test_tool_prepares_the_list_but_has_no_way_to_delete(monkeypatch):
    seen = {}

    async def fake_build(session, uid, box, llm, deliver=False):
        seen["deliver"] = deliver
        return {"reviewed": 25, "items": [{"id": 1}, {"id": 2}]}

    monkeypatch.setattr(email_tools, "build_proposal", fake_build)
    monkeypatch.setattr(email_tools, "is_mail_owner", lambda uid: True)
    monkeypatch.setattr(providers, "_providers", {"email": object(), "llm": object()})
    ctx = ToolContext(session=None, user_id=1, llm=None, embedder=None, source=None)
    out = asyncio.run(email_tools.FindUnnecessaryEmailsTool().run(ctx))
    assert seen["deliver"] is True
    assert "2 lazımsız məktub" in out and "silə bilməzsən" in out
    names = [t.name for t in email_tools.email_tools()]
    assert "find_unnecessary_emails" in names
    assert not any(word in n for n in names for word in ("delete", "trash"))


class FakeSession:
    async def commit(self) -> None:
        return None


class FakeSessionLocal:
    async def __aenter__(self) -> FakeSession:
        return FakeSession()

    async def __aexit__(self, *_exc) -> bool:
        return False


class FakeQuery:
    def __init__(self) -> None:
        self.edits: list[tuple] = []
        self.markups: list = []

    async def edit_message_text(self, text, **kwargs) -> None:
        self.edits.append((text, kwargs.get("reply_markup")))

    async def edit_message_reply_markup(self, reply_markup=None) -> None:
        self.markups.append(reply_markup)


class FakeBox:
    def __init__(self) -> None:
        self.trashed: list[list[int]] = []
        self.restored: list[list[int]] = []

    async def trash(self, ids):
        self.trashed.append(ids)
        return ids

    async def untrash(self, ids):
        self.restored.append(ids)
        return len(ids)


@pytest.fixture
def env(monkeypatch):
    user = SimpleNamespace(
        telegram_id=1, settings={"mail_trash": copy.deepcopy(PROPOSAL), "mail_kept": [5]}
    )

    async def get_or_create_user(session, uid, name=None):
        return user

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}
        return user.settings

    box = FakeBox()
    monkeypatch.setattr(providers, "_providers", {"email": box})
    monkeypatch.setattr(handlers, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(handlers, "get_or_create_user", get_or_create_user)
    monkeypatch.setattr(handlers, "update_settings", update_settings)
    monkeypatch.setattr(handlers, "is_mail_owner", lambda uid: uid == 1)
    return SimpleNamespace(user=user, box=box)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_message(self, uid, text, **_kwargs) -> None:
        self.sent.append(text)


def _press(data: str, uid: int = 1, bot: FakeBot | None = None) -> FakeQuery:
    q = FakeQuery()
    asyncio.run(handlers._on_trash_callback(q, SimpleNamespace(bot=bot), uid, data.split(":")))
    return q


def test_proposal_text_lists_reasons_and_the_safety_note():
    text = handlers._trash_text(PROPOSAL)
    assert text.startswith("🗑 Lazımsız görünən 3 məktub (Claude 25 məktuba baxdı)")
    assert "1. Mağaza — Endirim 50% (endirim reklamı)" in text
    assert "Zibil qutusuna" in text and "ulduzlu məktublara toxunulmur" in text


def test_delete_all_trashes_the_list_once_and_offers_undo(env):
    text, kb = _press("mt:del:K1").edits[-1]
    assert env.box.trashed == [[111, 222, 333]] and "3 məktub Zibil qutusuna" in text
    assert kb.inline_keyboard[0][0].callback_data == "mt:undo:K1"
    assert env.user.settings["mail_trash"]["items"] == []
    assert env.user.settings["mail_trash_undo"] == {"K1": [111, 222, 333]}

    # İkinci basış poçta toxunmur, nəticə mesajı və «Geri qaytar» düyməsi də yerində qalır.
    assert _press("mt:del:K1").edits == []
    assert env.box.trashed == [[111, 222, 333]]


def test_toggle_marks_a_mail_to_keep(env):
    kb = _press("mt:t:K1:2").markups[-1]
    assert [b.text for b in kb.inline_keyboard[0]] == ["🗑 1", "✋ 2", "🗑 3"]
    assert kb.inline_keyboard[1][0].text == "🗑 Seçilənləri sil (2)"


def test_picked_keeps_are_not_deleted_and_not_proposed_again(env):
    _press("mt:pick:K1")
    _press("mt:t:K1:2")
    text, _ = _press("mt:del:K1").edits[-1]
    assert env.box.trashed == [[111, 333]] and "1 məktub saxlanıldı" in text
    assert env.user.settings["mail_kept"] == [5, 222]


def test_keep_all_deletes_nothing(env):
    text, _ = _press("mt:keep:K1").edits[-1]
    assert env.box.trashed == [] and "Saxlanıldı" in text
    assert env.user.settings["mail_kept"] == [5, 111, 222, 333]


def test_undo_returns_the_mail_and_never_proposes_it_again(env):
    _press("mt:del:K1")
    text, _ = _press("mt:undo:K1").edits[-1]
    assert env.box.restored == [[111, 222, 333]] and "3 məktub Inbox-a qaytarıldı" in text
    assert env.user.settings["mail_trash_undo"] == {}
    assert env.user.settings["mail_kept"][-3:] == [111, 222, 333]


def test_stale_or_foreign_button_does_not_touch_mail(env):
    assert "köhnəlib" in _press("mt:del:OLD").edits[-1][0]
    assert _press("mt:del:K1", uid=2).edits == []  # poçt sahibi deyil
    assert env.box.trashed == []


@pytest.mark.parametrize("handled", [False, True])
def test_stale_show_button_leaves_the_evening_message_intact(env, handled):
    if handled:
        _press("mt:del:K1")
    bot = FakeBot()
    q = _press("mt:show:K1" if handled else "mt:show:OLD", bot=bot)
    assert q.edits == []  # yekunun mətni dəyişsə, ona Reply gündəliyə düşməz
    assert len(bot.sent) == 1 and "köhnəlib" in bot.sent[0]


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[tuple] = []
        self.chat = SimpleNamespace(send_action=self._noop)

    async def _noop(self, *_args) -> None:
        return None

    async def reply_text(self, text, **kwargs) -> None:
        self.replies.append((text, kwargs.get("reply_markup")))


def test_list_found_by_the_agent_is_sent_once_after_its_reply(monkeypatch):
    user = SimpleNamespace(telegram_id=1, settings={})

    class Agent:
        async def handle(self, session, uid, text, source, embedder, history,
                         allow_escalation=True):
            user.settings = {**user.settings,
                             "mail_trash": {**copy.deepcopy(PROPOSAL), "deliver": True}}
            return "Siyahını aşağıda göndərdim."

    async def get_or_create_user(session, uid, name=None):
        return user

    async def nothing(*_args, **_kwargs):
        return []

    async def budget(session, uid):
        return BudgetStatus("ok", Decimal("1"), Decimal("20"))

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}
        return user.settings

    monkeypatch.setattr(providers, "_providers", {"agent": Agent(), "embed": object()})
    for name, fake in {
        "SessionLocal": FakeSessionLocal, "get_or_create_user": get_or_create_user,
        "get_recent_messages": nothing, "add_message": nothing,
        "get_budget_status": budget, "update_settings": update_settings,
    }.items():
        monkeypatch.setattr(handlers, name, fake)

    msg = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1, full_name="Samir"), message=msg)
    asyncio.run(handlers._run_agent(update, "lazımsız məktubları sil", NoteSource.text))
    assert msg.replies[0][0] == "Siyahını aşağıda göndərdim."
    assert msg.replies[1][0].startswith("🗑 Lazımsız görünən 3 məktub")
    assert msg.replies[1][1].inline_keyboard[0][0].callback_data == "mt:del:K1"
    assert user.settings["mail_trash"]["deliver"] is False
