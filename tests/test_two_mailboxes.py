"""İki poçt: hər poçtun öz vəziyyəti var, düymə yalnız öz poçtuna toxunur, xəta o birinə keçmir."""

import asyncio
import copy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agent.sdk_agent import _mailbox_note
from app.bot import handlers, scheduler
from app.config import Settings, settings
from app.models import NoteSource
from app.providers import factory
from app.providers.email_imap import ImapMailProvider, Mail, mailbox_labels
from app.providers.registry import providers
from app.services import mail_review
from app.services.budget import BudgetStatus
from app.services.email_watch import box_for_key, check_new_mail, find_mailbox, state_key
from app.tools import email_tools
from app.tools.base import ToolContext


def _mail(uid: int, subject: str) -> Mail:
    return Mail(uid=uid, sender="Leyla <l@x.az>", subject=subject, date=None, unread=True)


class FakeBox:
    """Bir poçtun əvəzi: nəyə toxunulduğunu yazır, fail=True → qoşulmur."""

    def __init__(self, label: str, slot: int, mails=None, fail: bool = False) -> None:
        self.label, self.slot, self.fail = label, slot, fail
        self.address = f"{label}@x.az"
        self.mails = {m.uid: m for m in mails or []}
        self.trashed: list[list[int]] = []
        self.restored: list[list[int]] = []
        self.archived: list[list[int]] = []

    def _connect(self) -> None:
        if self.fail:
            raise RuntimeError("AUTHENTICATIONFAILED")

    async def recent(self, limit=10, unread_only=False):
        self._connect()
        return list(self.mails.values())[:limit]

    async def search(self, text="", sender="", days=0, limit=10):
        self._connect()
        return list(self.mails.values())[:limit]

    async def get(self, uid):
        self._connect()
        return self.mails.get(uid)

    async def unread_count(self):
        self._connect()
        return len(self.mails)

    async def poll_new(self, last, uv):
        self._connect()
        return 9, 12, [_mail(12, f"Yeni {self.label}")]

    async def promotions(self, limit=10):
        self._connect()
        return [m.uid for m in self.mails.values()], list(self.mails.values())[:limit]

    async def cleanup_candidates(self, exclude, limit=25):
        self._connect()
        return [(m.uid, m) for m in self.mails.values() if m.uid not in exclude]

    async def trash(self, ids):
        self.trashed.append(ids)
        return ids

    async def untrash(self, ids):
        self.restored.append(ids)
        return len(ids)

    async def archive(self, ids):
        self.archived.append(ids)
        return ids

    async def unarchive(self, ids):
        self.restored.append(ids)
        return len(ids)


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

    async def edit_message_text(self, text, **kwargs) -> None:
        self.edits.append((text, kwargs.get("reply_markup")))


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id=None, text=None, **kwargs) -> None:
        self.sent.append((text, kwargs.get("reply_markup")))


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[tuple] = []
        self.chat = SimpleNamespace(send_action=self._typing)

    async def _typing(self, *_args) -> None:
        return None

    async def reply_text(self, text, **kwargs) -> None:
        self.replies.append((text, kwargs.get("reply_markup")))


def _proposal(label: str, mail_id: int, **extra) -> dict:
    return {
        "key": f"{label}-K", "account": label, "reviewed": 5, "drop": [], "deliver": False,
        "items": [{"id": mail_id, "from": "Mağaza", "subject": "Endirim", "reason": "reklam"}],
        **extra,
    }


@pytest.fixture
def two(monkeypatch):
    aaa = FakeBox("aaa", 1, [_mail(4, "Birinci poçt"), _mail(7, "Eyni nömrə A")])
    bbb = FakeBox("bbb", 2, [_mail(5, "İkinci poçt"), _mail(7, "Eyni nömrə B")])
    user = SimpleNamespace(telegram_id=1, settings={
        "mail_trash": _proposal("aaa", 111),
        "mail_trash:2": _proposal("bbb", 222),
        "mail_kept": [1],
        "mail_kept:2": [2],
        "mail_cleanup": {"key": "aaa-C", "ids": [111], "archived": []},
        "mail_cleanup:2": {"key": "bbb-C", "ids": [222], "archived": []},
    })

    async def get_or_create_user(session, uid, name=None):
        return user

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}
        return user.settings

    monkeypatch.setattr(providers, "_providers", {"email": [aaa, bbb], "llm": object()})
    monkeypatch.setattr(handlers, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(handlers, "get_or_create_user", get_or_create_user)
    monkeypatch.setattr(handlers, "update_settings", update_settings)
    monkeypatch.setattr(handlers, "is_mail_owner", lambda uid: uid == 1)
    return SimpleNamespace(aaa=aaa, bbb=bbb, user=user)


def _press_trash(data: str, bot: FakeBot | None = None) -> FakeQuery:
    q = FakeQuery()
    asyncio.run(handlers._on_trash_callback(q, SimpleNamespace(bot=bot), 1, data.split(":")))
    return q


def _press_cleanup(data: str) -> FakeQuery:
    q = FakeQuery()
    asyncio.run(handlers._on_cleanup_callback(q, SimpleNamespace(bot=None), 1, data.split(":")))
    return q


# --- ayarlar və adlar -------------------------------------------------------------------


def _s(**kw) -> Settings:
    return Settings(_env_file=None, email_imap_host="h", email_address="a@x.az",
                    email_password="p", **kw)


def test_second_account_is_optional_and_needs_both_fields():
    assert _s().email_accounts == [("a@x.az", "p")]
    assert _s(email_address_2="b@x.az").email_accounts == [("a@x.az", "p")]
    assert _s(email_address_2="b@x.az", email_password_2="q").email_accounts == [
        ("a@x.az", "p"), ("b@x.az", "q")
    ]


def test_the_same_address_twice_is_one_mailbox():
    assert _s(email_address_2="A@x.az", email_password_2="q").email_accounts == [("a@x.az", "p")]


@pytest.mark.parametrize("addresses, labels", [
    (["first@x.az"], [""]),
    (["First.One@x.az", "second@x.az"], ["fir", "sec"]),
    (["same@x.az", "same@y.az"], ["p1", "p2"]),  # eyni ad
    (["sil@x.az", "other@x.az"], ["p1", "p2"]),  # /mail sil ilə qarışmasın
    (["123456@x.az", "other@x.az"], ["p1", "p2"]),  # /mail <uid> ilə qarışmasın
])
def test_mailbox_labels(addresses, labels):
    assert mailbox_labels(addresses) == labels


def test_factory_builds_one_provider_per_account(monkeypatch):
    monkeypatch.setattr(providers, "_providers", {})
    for key, value in {
        "llm_backend": "auto", "claude_code_oauth_token": "tok", "anthropic_api_key": "",
        "openai_api_key": "", "embed_backend": "auto", "stt_backend": "auto",
        "azure_speech_key": "", "tavily_api_key": "", "email_imap_host": "imap.x.az",
        "email_address": "first@x.az", "email_password": "p",
        "email_address_2": "second@x.az", "email_password_2": "q",
    }.items():
        monkeypatch.setattr(settings, key, value)
    factory.init_providers()
    boxes = providers.get("email")
    assert [(b.address, b.label, b.slot) for b in boxes] == [
        ("first@x.az", "fir", 1), ("second@x.az", "sec", 2)
    ]
    assert "first@x.az" in _mailbox_note() and "second@x.az" in _mailbox_note()


def test_state_of_the_first_mailbox_keeps_its_old_keys(two):
    assert state_key(two.aaa, "mail_trash") == "mail_trash"
    assert state_key(two.bbb, "mail_trash") == "mail_trash:2"


def test_button_key_finds_its_mailbox(two):
    assert box_for_key("bbb-1107220000") is two.bbb
    assert box_for_key("1107220000") is two.aaa  # yeniləmədən əvvəl göndərilmiş düymə
    assert box_for_key("ccc-1107220000") is None  # artıq qoşulu olmayan poçt
    assert find_mailbox("") is two.aaa and find_mailbox("sil") is None


# --- yeni məktub bildirişi ---------------------------------------------------------------


def test_new_mail_uses_its_own_state_and_names_the_mailbox():
    seen = []

    class Box(FakeBox):
        async def poll_new(self, last, uv):
            seen.append((last, uv))
            return 9, 12, [_mail(12, "Görüş")]

    state = {"email_last_uid": 500, "email_uidvalidity": 1,
             "email_last_uid:2": 11, "email_uidvalidity:2": 9}
    text, changes = asyncio.run(check_new_mail(Box("bbb", 2), None, state))
    assert seen == [(11, 9)]
    assert changes == {"email_uidvalidity:2": 9, "email_last_uid:2": 12}
    assert text.startswith("📬 [bbb] 1 yeni məktub:") and "Oxumaq: /mail bbb <uid>" in text


def test_second_mailbox_starts_without_notifying_about_old_mail(monkeypatch):
    class Conn:
        def response(self, key):
            return key, [b"9" if key == "UIDVALIDITY" else b"101"]

        def logout(self):
            return "BYE", []

    monkeypatch.setattr(ImapMailProvider, "_connect", lambda self: Conn())
    box = ImapMailProvider("h", 993, "b@x.az", "p", label="bbb", slot=2)
    state = {"email_last_uid": 500, "email_uidvalidity": 1}  # birinci poçtun vəziyyəti
    text, changes = asyncio.run(check_new_mail(box, None, state))
    assert text is None
    assert changes == {"email_uidvalidity:2": 9, "email_last_uid:2": 100}


@pytest.fixture
def tick(monkeypatch):
    user = SimpleNamespace(settings={})

    async def get_user(session, uid):
        return user

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}

    monkeypatch.setattr(settings, "allowed_user_ids", "1")
    monkeypatch.setattr(scheduler, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(scheduler, "get_user", get_user)
    monkeypatch.setattr(scheduler, "update_settings", update_settings)

    def run(*boxes, bot=None):
        monkeypatch.setattr(providers, "_providers", {"email": list(boxes)})
        bot = bot or FakeBot()
        asyncio.run(scheduler.email_tick(SimpleNamespace(bot=bot)))
        return bot, user.settings

    return run


def test_email_tick_notifies_each_mailbox_separately(tick):
    bot, state = tick(FakeBox("aaa", 1), FakeBox("bbb", 2))
    assert [text.splitlines()[0] for text, _ in bot.sent] == [
        "📬 [aaa] 1 yeni məktub:", "📬 [bbb] 1 yeni məktub:"
    ]
    assert state["email_last_uid"] == 12 and state["email_last_uid:2"] == 12


def test_email_tick_failing_mailbox_does_not_stop_the_other(tick):
    bot, state = tick(FakeBox("aaa", 1, fail=True), FakeBox("bbb", 2))
    assert len(bot.sent) == 1 and "[bbb]" in bot.sent[0][0]
    assert state == {"email_uidvalidity:2": 9, "email_last_uid:2": 12}  # aaa növbəti tick-də


def test_email_tick_keeps_state_when_a_notification_fails(tick):
    class Offline(FakeBot):
        async def send_message(self, chat_id=None, text=None, **kwargs):
            if "[aaa]" in text:
                raise RuntimeError("Telegram düşüb")
            await super().send_message(chat_id, text, **kwargs)

    _, state = tick(FakeBox("aaa", 1), FakeBox("bbb", 2), bot=Offline())
    assert "email_last_uid" not in state and state["email_last_uid:2"] == 12  # aaa təkrar gedəcək


# --- lazımsız məktublar ------------------------------------------------------------------


def test_review_of_one_mailbox_leaves_the_other_alone(monkeypatch):
    user = SimpleNamespace(settings={"mail_kept": [5], "mail_trash": {"key": "OLD"},
                                     "mail_kept:2": [7]})

    async def get_user(session, uid):
        return user

    async def update_settings(session, uid, changes):
        user.settings = {**user.settings, **changes}

    class LLM:
        async def complete(self, **_kw):
            return ('{"items": [{"id": 1, "verdict": "delete", "reason": "reklam"},'
                    ' {"id": 2, "verdict": "keep"}]}')

        @staticmethod
        def text_of(resp):
            return resp

    monkeypatch.setattr(mail_review, "get_user", get_user)
    monkeypatch.setattr(mail_review, "update_settings", update_settings)
    box = FakeBox("bbb", 2, [_mail(7, "Saxlanıb"), _mail(111, "Endirim"), _mail(222, "Faktura")])
    p = asyncio.run(mail_review.build_proposal(None, 1, box, LLM()))
    assert p["key"].startswith("bbb-") and p["account"] == "bbb"
    assert [it["id"] for it in p["items"]] == [111]  # 7 bu poçtun «saxla» siyahısındadır
    assert user.settings["mail_trash:2"] == p and user.settings["mail_kept:2"] == [7, 222]
    assert user.settings["mail_trash"] == {"key": "OLD"} and user.settings["mail_kept"] == [5]


def test_delete_button_touches_only_its_own_mailbox(two):
    text, kb = _press_trash("mt:del:bbb-K").edits[-1]
    assert two.bbb.trashed == [[222]] and two.aaa.trashed == []
    assert text.startswith("🗑 [bbb] 1 məktub Zibil qutusuna")
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == [
        "mt:undo:bbb-K", "mt:more:bbb"
    ]
    state = two.user.settings
    assert state["mail_trash:2"]["items"] == [] and state["mail_trash_undo:2"] == {"bbb-K": [222]}
    assert state["mail_trash"]["items"] and "mail_trash_undo" not in state


def test_undo_goes_back_to_its_own_mailbox(two):
    _press_trash("mt:del:bbb-K")
    text, _ = _press_trash("mt:undo:bbb-K").edits[-1]
    assert two.bbb.restored == [[222]] and two.aaa.restored == []
    assert text.startswith("↩️ [bbb] 1 məktub Inbox-a qaytarıldı")
    assert two.user.settings["mail_kept:2"] == [2, 222] and two.user.settings["mail_kept"] == [1]


def test_keep_button_remembers_in_its_own_mailbox(two):
    _press_trash("mt:keep:bbb-K")
    assert two.bbb.trashed == [] and two.user.settings["mail_kept:2"] == [2, 222]
    assert two.user.settings["mail_kept"] == [1]


def test_button_sent_before_the_upgrade_goes_to_the_first_mailbox(two):
    two.user.settings["mail_trash"] = _proposal("", 111, key="1107220000")
    _press_trash("mt:del:1107220000")
    assert two.aaa.trashed == [[111]] and two.bbb.trashed == []


def test_button_of_a_disconnected_mailbox_touches_nothing(two):
    assert "köhnəlib" in _press_trash("mt:del:ccc-K").edits[-1][0]
    assert "köhnəlib" in _press_cleanup("mc:arch:ccc-C").edits[-1][0]
    assert two.aaa.trashed == two.bbb.trashed == two.aaa.archived == two.bbb.archived == []


def test_show_button_opens_the_list_of_its_own_mailbox(two):
    bot = FakeBot()
    _press_trash("mt:show:bbb-K", bot=bot)
    text, kb = bot.sent[-1]
    assert text.startswith("🗑 [bbb] Lazımsız görünən 1 məktub")
    assert kb.inline_keyboard[0][0].callback_data == "mt:del:bbb-K"


@pytest.fixture
def reviewed(two, monkeypatch):
    calls = []

    async def fake_build(session, uid, box, llm):
        calls.append(box.label)
        if box.fail:
            raise RuntimeError("limit doldu")
        return _proposal(box.label, 111)

    monkeypatch.setattr(handlers, "build_proposal", fake_build)
    two.calls = calls
    return two


def test_mail_delete_reviews_each_mailbox_and_survives_a_failure(reviewed):
    reviewed.aaa.fail = True
    bot = FakeBot()
    asyncio.run(handlers._review_and_send(bot, 1))
    assert reviewed.calls == ["aaa", "bbb"]
    texts = [text for text, _ in bot.sent]
    assert "⚠️ [aaa] Məktublara baxmaq alınmadı: limit doldu" in texts
    assert any(t.startswith("🗑 [bbb] Lazımsız görünən 1 məktub") for t in texts)


def test_more_button_reviews_only_its_own_mailbox(reviewed):
    _press_trash("mt:more:bbb", bot=FakeBot())
    assert reviewed.calls == ["bbb"]


def test_more_button_from_before_the_upgrade_reviews_all(reviewed):
    _press_trash("mt:more", bot=FakeBot())
    assert reviewed.calls == ["aaa", "bbb"]


def test_agent_lists_from_both_mailboxes_are_sent_once(two, monkeypatch):
    user = two.user
    user.settings = {}

    class Agent:
        async def handle(self, session, uid, text, source, embedder, history,
                         allow_escalation=True):
            user.settings = {**user.settings,
                             "mail_trash": _proposal("aaa", 111, deliver=True),
                             "mail_trash:2": _proposal("bbb", 222, deliver=True)}
            return "Siyahıları göndərdim."

    async def nothing(*_args, **_kwargs):
        return []

    async def budget(session, uid):
        return BudgetStatus("ok", Decimal("1"), Decimal("20"))

    providers._providers.update(agent=Agent(), embed=object())
    monkeypatch.setattr(handlers, "get_recent_messages", nothing)
    monkeypatch.setattr(handlers, "add_message", nothing)
    monkeypatch.setattr(handlers, "get_budget_status", budget)

    msg = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1, full_name="Samir"), message=msg)
    asyncio.run(handlers._run_agent(update, "lazımsız məktubları sil", NoteSource.text))
    assert [text.splitlines()[0][:12] for text, _ in msg.replies] == [
        "Siyahıları g", "🗑 [aaa] Lazı", "🗑 [bbb] Lazı"
    ]
    assert msg.replies[2][1].inline_keyboard[0][0].callback_data == "mt:del:bbb-K"
    assert user.settings["mail_trash"]["deliver"] is False
    assert user.settings["mail_trash:2"]["deliver"] is False


# --- reklam təmizliyi --------------------------------------------------------------------


def test_cleanup_sends_a_list_per_mailbox_and_survives_a_failure(two):
    two.aaa.fail = True
    bot = FakeBot()
    asyncio.run(handlers._send_cleanup(bot, 1))
    assert bot.sent[0][0].startswith("📭 [aaa] Reklam məktublarını almaq olmadı")
    text, kb = bot.sent[1]
    assert text.startswith("🧹 [bbb] Inbox-da 2 reklam")
    key = two.user.settings["mail_cleanup:2"]["key"]
    assert key.startswith("bbb-") and kb.inline_keyboard[0][0].callback_data == f"mc:arch:{key}"
    assert two.user.settings["mail_cleanup"]["key"] == "aaa-C"  # birinci poçtun siyahısı yerində


def test_archive_button_touches_only_its_own_mailbox(two):
    text, kb = _press_cleanup("mc:arch:bbb-C").edits[-1]
    assert two.bbb.archived == [[222]] and two.aaa.archived == []
    assert text.startswith("📦 [bbb] 1 məktub arxivləndi")
    assert kb.inline_keyboard[0][0].callback_data == "mc:undo:bbb-C"
    assert two.user.settings["mail_cleanup"]["ids"] == [111]

    text, _ = _press_cleanup("mc:undo:bbb-C").edits[-1]
    assert two.bbb.restored == [[222]] and two.aaa.restored == []
    assert text.startswith("↩️ [bbb] 1 məktub Inbox-a qaytarıldı")


# --- /mail -------------------------------------------------------------------------------


def _mail_cmd(*args) -> tuple[list[str], FakeBot]:
    msg, bot = FakeMessage(), FakeBot()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1, full_name="Samir"), message=msg)
    asyncio.run(handlers.mail_cmd(update, SimpleNamespace(args=list(args), bot=bot)))
    return [text for text, _ in msg.replies], bot


def test_mail_lists_both_mailboxes(two):
    replies, _ = _mail_cmd()
    text = "\n".join(replies)
    assert "📬 [aaa] Son məktublar" in text and "Birinci poçt" in text
    assert "📬 [bbb] Son məktublar" in text and "İkinci poçt" in text
    assert "Oxumaq: /mail aaa <uid> · /mail bbb <uid>" in text


def test_mail_with_a_name_lists_only_that_mailbox(two):
    text = "\n".join(_mail_cmd("BBB")[0])
    assert "İkinci poçt" in text and "Birinci poçt" not in text
    assert "Oxumaq: /mail bbb <uid> ·" in text


def test_mail_list_shows_a_failing_mailbox_next_to_the_working_one(two):
    two.aaa.fail = True
    text = "\n".join(_mail_cmd()[0])
    assert "📭 [aaa] E-poçta qoşulmaq olmadı: AUTHENTICATIONFAILED" in text
    assert "İkinci poçt" in text


def test_mail_uid_found_in_one_mailbox_opens_it(two):
    assert _mail_cmd("5")[0][0].startswith("📧 [bbb] İkinci poçt")


def test_mail_uid_found_in_both_asks_which(two):
    assert _mail_cmd("7")[0] == ["🤔 uid=7 hər iki poçtda var: /mail aaa 7 · /mail bbb 7"]


def test_mail_name_and_uid_reads_only_there(two):
    assert _mail_cmd("bbb", "7")[0][0].startswith("📧 [bbb] Eyni nömrə B")
    assert _mail_cmd("aaa", "5")[0] == ["🤷 uid=5 məktub tapılmadı."]


def test_mail_uid_reports_a_failure_only_when_nothing_was_found(two):
    two.aaa.fail = True
    assert _mail_cmd("5")[0][0].startswith("📧 [bbb]")
    assert _mail_cmd("999")[0] == ["📭 E-poçta qoşulmaq olmadı: AUTHENTICATIONFAILED"]


def test_mail_name_with_delete_reviews_only_that_mailbox(reviewed):
    _mail_cmd("bbb", "sil")
    assert reviewed.calls == ["bbb"]


def test_mail_delete_without_a_name_reviews_both(reviewed):
    _mail_cmd("sil")
    assert reviewed.calls == ["aaa", "bbb"]


# --- agent alətləri ----------------------------------------------------------------------


def _ctx() -> ToolContext:
    return ToolContext(session=None, user_id=1, llm=None, embedder=None, source=None)


def test_check_email_lists_both_and_names_each_mail(two):
    out = asyncio.run(email_tools.CheckEmailTool().run(_ctx()))
    assert out.startswith(email_tools.UNTRUSTED)
    assert "poçt=aaa · uid=4" in out and "poçt=bbb · uid=5" in out


@pytest.mark.parametrize("account", ["bbb", "BBB", "bbb@x.az"])
def test_check_email_can_look_at_one_mailbox(two, account):
    out = asyncio.run(email_tools.CheckEmailTool().run(_ctx(), account=account))
    assert "poçt=bbb" in out and "poçt=aaa" not in out


def test_unknown_mailbox_name_is_explained(two):
    out = asyncio.run(email_tools.CheckEmailTool().run(_ctx(), account="ccc"))
    assert out == "«ccc» adlı poçt yoxdur. Poçtlar: aaa, bbb"


def test_search_shows_a_failing_mailbox_next_to_the_results(two):
    two.aaa.fail = True
    out = asyncio.run(email_tools.SearchEmailTool().run(_ctx(), query="x"))
    assert "poçt=bbb" in out and "⚠️ [aaa] Poçta qoşulmaq olmadı" in out


def test_all_mailboxes_failing_is_not_reported_as_no_mail(two):
    two.aaa.fail = two.bbb.fail = True
    out = asyncio.run(email_tools.CheckEmailTool().run(_ctx()))
    assert "Məktub tapılmadı" not in out and out.count("qoşulmaq olmadı") == 2


def test_read_email_needs_the_mailbox_when_the_uid_is_in_both(two):
    tool = email_tools.ReadEmailTool()
    assert "aaa, bbb" in asyncio.run(tool.run(_ctx(), uid=7))
    assert "Eyni nömrə B" in asyncio.run(tool.run(_ctx(), uid=7, account="bbb"))
    assert "İkinci poçt" in asyncio.run(tool.run(_ctx(), uid=5))


def test_find_unnecessary_reviews_each_mailbox_and_deletes_nothing(two, monkeypatch):
    two.bbb.fail = True

    async def fake_build(session, uid, box, llm, deliver=False):
        assert deliver is True
        if box.fail:
            raise RuntimeError("limit doldu")
        return _proposal(box.label, 111)

    monkeypatch.setattr(email_tools, "build_proposal", fake_build)
    monkeypatch.setattr(email_tools, "is_mail_owner", lambda uid: uid == 1)
    out = asyncio.run(email_tools.FindUnnecessaryEmailsTool().run(_ctx()))
    assert "[aaa] 5 məktuba baxıldı, 1 lazımsız məktub tapıldı." in out
    assert "⚠️ [bbb] Məktublara baxmaq alınmadı: limit doldu" in out
    assert "silə bilməzsən" in out
    assert two.aaa.trashed == two.bbb.trashed == []


def test_agent_is_told_the_mailbox_names_only_with_two(two, monkeypatch):
    assert "aaa = aaa@x.az, bbb = bbb@x.az" in _mailbox_note()
    monkeypatch.setattr(providers, "_providers", {"email": [FakeBox("", 1)]})
    assert _mailbox_note() == ""


# --- səhər brifinqi və axşam yekunu -------------------------------------------------------


def test_briefing_counts_each_mailbox(two):
    assert asyncio.run(scheduler._unread_line()) == "📧 Oxunmamış məktub: aaa 2 · bbb 2 (/mail)"


def test_briefing_shows_a_failing_mailbox(two):
    two.aaa.fail = True
    line = asyncio.run(scheduler._unread_line())
    assert line == "📧 Oxunmamış məktub: aaa ⚠️ qoşulmadı · bbb 2 (/mail)"


def test_briefing_without_unread_mail_has_no_line(two):
    two.aaa.mails, two.bbb.mails = {}, {}
    assert asyncio.run(scheduler._unread_line()) is None


def test_single_mailbox_briefing_looks_as_before(monkeypatch):
    monkeypatch.setattr(providers, "_providers", {"email": [FakeBox("", 1, [_mail(1, "X")])]})
    assert asyncio.run(scheduler._unread_line()) == "📧 Oxunmamış məktub: 1 (/mail)"


def test_evening_reviews_each_mailbox_and_skips_a_failing_one(two, monkeypatch):
    two.aaa.fail = True

    async def fake_build(session, uid, box, llm):
        if box.fail:
            raise RuntimeError("limit doldu")
        return _proposal(box.label, 111)

    monkeypatch.setattr(scheduler, "build_proposal", fake_build)
    monkeypatch.setattr(scheduler, "is_mail_owner", lambda uid: True)
    assert [p["account"] for p in asyncio.run(scheduler._review_mail(None, 1))] == ["bbb"]


def test_evening_buttons_name_their_mailbox():
    button = scheduler._review_button(_proposal("bbb", 111))
    assert button.text == "🗑 Bax və sil · bbb (1)" and button.callback_data == "mt:show:bbb-K"
    assert scheduler._review_button(_proposal("", 111)).text == "🗑 Bax və sil"


def test_old_proposal_without_an_account_still_renders():
    old = copy.deepcopy(_proposal("", 111))
    del old["account"]
    assert handlers._trash_text(old).startswith("🗑 Lazımsız görünən 1 məktub")
