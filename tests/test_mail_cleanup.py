"""Poçt təmizliyi: Gmail etiketi ilə arxiv / geri qaytarma, köhnə düymə, sahib yoxlaması."""

import asyncio
from types import SimpleNamespace

import pytest

from app.bot import handlers
from app.config import settings
from app.providers.email_imap import (
    CLEANUP_QUERY,
    PROMO_QUERY,
    ImapMailProvider,
    Mail,
    _quote,
)
from app.providers.registry import providers
from app.services.email_watch import is_mail_owner

ALL_MAIL = '"[Gmail]/Butun mektublar"'  # adı dilə görə dəyişir, \All bayrağı ilə tapılır
TRASH = '"[Gmail]/Zibil"'
LIST_REPLY = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\All \\HasNoChildren) "/" ' + ALL_MAIL.encode(),
    b'(\\HasNoChildren \\Trash) "/" ' + TRASH.encode(),
]


class FakeConn:
    """imaplib.IMAP4 əvəzi — əmrləri yazır. inbox / all_mail / trash: uid → X-GM-MSGID."""

    def __init__(self, inbox=None, all_mail=None, trash=None):
        self.inbox, self.all_mail, self.trash = inbox or {}, all_mail or {}, trash or {}
        self.folder = "INBOX"
        self.calls: list[tuple] = []

    def _mailbox(self, name: str) -> dict:
        return {"INBOX": self.inbox, '"INBOX"': self.inbox, TRASH: self.trash}.get(
            name, self.all_mail
        )

    def select(self, name, readonly=False):
        self.folder = name
        self.calls.append(("SELECT", name, readonly))
        return "OK", [b"1"]

    def list(self):
        return "OK", LIST_REPLY

    def logout(self):
        return "BYE", []

    def uid(self, cmd, *args):
        self.calls.append((cmd, *args))
        box = self._mailbox(self.folder)
        if cmd == "MOVE":
            dest = self._mailbox(args[1])
            for u in (int(x) for x in args[0].split(",")):
                dest[1000 + u] = box.pop(u)  # təyinat qovluğunda yeni UID
            return "OK", []
        if cmd == "SEARCH" and args[0] == "X-GM-RAW":
            return "OK", [" ".join(str(u) for u in sorted(box)).encode()]
        if cmd == "SEARCH":  # [OR ...] X-GM-MSGID <id> ...
            wanted = {int(a) for a in args if a.isdigit()}
            return "OK", [" ".join(str(u) for u, mid in box.items() if mid in wanted).encode()]
        if cmd == "FETCH":
            uids = [int(x) for x in args[0].split(",")]
            return "OK", [f"{n} (X-GM-MSGID {box[u]} UID {u})".encode()
                          for n, u in enumerate(uids, 1)]
        if cmd == "STORE":
            return "OK", []
        raise AssertionError(cmd)


def _box(monkeypatch, conn: FakeConn) -> ImapMailProvider:
    monkeypatch.setattr(ImapMailProvider, "_connect", lambda self: conn)
    return ImapMailProvider("imap.test", 993, "a@test.az", "x")


def _stores(conn: FakeConn) -> list[tuple]:
    return [c for c in conn.calls if c[0] == "STORE"]


def test_archive_removes_inbox_label_in_all_mail_only_for_requested_promos(monkeypatch):
    conn = FakeConn(inbox={10: 111, 11: 222, 12: 333}, all_mail={50: 111, 51: 222, 52: 333})
    assert asyncio.run(_box(monkeypatch, conn).archive([111, 333, 999])) == [111, 333]
    assert ("SEARCH", "X-GM-RAW", _quote(PROMO_QUERY)) in conn.calls  # hələ Inbox-da reklamdır
    assert ("SELECT", ALL_MAIL, False) in conn.calls  # Inbox-un özündə Gmail etiketi götürmür
    assert ("SEARCH", "OR", "X-GM-MSGID", "111", "X-GM-MSGID", "333") in conn.calls
    assert _stores(conn) == [("STORE", "50,52", "-X-GM-LABELS", "(\\Inbox)")]


def test_archive_touches_nothing_when_requested_mail_is_gone(monkeypatch):
    conn = FakeConn(inbox={10: 111}, all_mail={50: 111})
    assert asyncio.run(_box(monkeypatch, conn).archive([999])) == []
    assert _stores(conn) == [] and not any(c[0] == "SELECT" for c in conn.calls)


def test_unarchive_finds_all_mail_by_flag_and_restores_inbox_label(monkeypatch):
    conn = FakeConn(all_mail={50: 111, 51: 333, 52: 777})
    assert asyncio.run(_box(monkeypatch, conn).unarchive([111, 333])) == 2
    assert ("SELECT", ALL_MAIL, False) in conn.calls
    assert _stores(conn) == [("STORE", "50,51", "+X-GM-LABELS", "(\\Inbox)")]


def _moves(conn: FakeConn) -> list[tuple]:
    return [c for c in conn.calls if c[0] == "MOVE"]


def test_trash_moves_only_requested_candidates_to_trash(monkeypatch):
    conn = FakeConn(inbox={10: 111, 11: 222, 12: 333})
    assert asyncio.run(_box(monkeypatch, conn).trash([111, 333, 999])) == [111, 333]
    assert ("SELECT", '"INBOX"', False) in conn.calls
    assert ("SEARCH", "X-GM-RAW", _quote(CLEANUP_QUERY)) in conn.calls  # «Əsas» və ulduzlu yox
    assert _moves(conn) == [("MOVE", "10,12", TRASH)]
    assert conn.inbox == {11: 222} and sorted(conn.trash.values()) == [111, 333]


def test_untrash_moves_mail_back_to_inbox(monkeypatch):
    conn = FakeConn(trash={70: 111, 71: 333, 72: 777})
    assert asyncio.run(_box(monkeypatch, conn).untrash([111, 333])) == 2
    assert ("SELECT", TRASH, False) in conn.calls
    assert _moves(conn) == [("MOVE", "70,71", '"INBOX"')]
    assert conn.trash == {72: 777}


def test_cleanup_candidates_skip_kept_and_come_newest_first(monkeypatch):
    conn = FakeConn(inbox={10: 111, 11: 222, 12: 333, 13: 444})
    box = _box(monkeypatch, conn)

    def fake_fetch(_conn, uids, full=False):
        return [Mail(uid=u, sender="X", subject="S", date=None, unread=True)
                for u in sorted(uids, reverse=True)]

    monkeypatch.setattr(ImapMailProvider, "_fetch", staticmethod(fake_fetch))
    out = asyncio.run(box.cleanup_candidates(exclude={333}, limit=2))
    assert [mid for mid, _ in out] == [444, 222]
    assert ("SEARCH", "X-GM-RAW", _quote(CLEANUP_QUERY)) in conn.calls
    assert not any(c[0] in ("SELECT", "STORE", "MOVE") for c in conn.calls)  # yalnız oxuma


def test_msgid_lookup_uses_chunked_or_searches():
    conn = FakeConn(inbox={u: 1000 + u for u in range(120)})
    uids = ImapMailProvider._uids_by_msgid(conn, [1000 + u for u in range(120)])
    searches = [c for c in conn.calls if c[0] == "SEARCH"]
    assert [s.count("OR") for s in searches] == [49, 49, 19]
    assert sorted(uids) == list(range(120))


def test_cleanup_refuses_a_folder_other_than_inbox(monkeypatch):
    conn = FakeConn(inbox={10: 111})
    box = _box(monkeypatch, conn)
    box.folder = "[Gmail]/All Mail"
    with pytest.raises(RuntimeError):
        asyncio.run(box.archive([111]))
    assert _stores(conn) == []


def test_promotions_lists_read_only_newest_first(monkeypatch):
    conn = FakeConn(inbox={10: 111, 11: 222, 12: 333})
    box = _box(monkeypatch, conn)
    fetched = {}

    def fake_fetch(_conn, uids, full=False):
        fetched["uids"] = uids
        return [Mail(uid=u, sender="Mağaza <m@x.az>", subject="Endirim", date=None, unread=True)
                for u in reversed(uids)]

    monkeypatch.setattr(ImapMailProvider, "_fetch", staticmethod(fake_fetch))
    ids, sample = asyncio.run(box.promotions(limit=2))
    assert ids == [333, 222, 111]
    assert fetched["uids"] == [11, 12] and [m.uid for m in sample] == [12, 11]
    assert not any(c[0] in ("SELECT", "STORE") for c in conn.calls)  # yalnız oxuma


def test_mail_owner_is_the_first_allowed_id(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "1,2")
    assert is_mail_owner(1) and not is_mail_owner(2)
    monkeypatch.setattr(settings, "allowed_user_ids", "")
    assert not is_mail_owner(1)  # açıq rejimdə poçta heç kim yaza bilməz


def test_cleanup_text_shows_sample_and_safety_note():
    sample = [Mail(uid=1, sender="Mağaza <m@x.az>", subject="X" * 80, date=None, unread=True)]
    text = handlers._cleanup_text(44, sample)
    assert "Inbox-da 44 reklam" in text and "Son 1 məktub" in text
    assert "• Mağaza — " + "X" * 69 + "…" in text
    assert "heç nə silinmir" in text


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


class FakeBox:
    def __init__(self) -> None:
        self.archived: list[list[int]] = []

    async def archive(self, ids):
        self.archived.append(ids)
        return ids

    async def unarchive(self, ids):
        return len(ids)


@pytest.fixture
def env(monkeypatch):
    user = SimpleNamespace(
        telegram_id=1, settings={"mail_cleanup": {"key": "K1", "ids": [111, 222], "archived": []}}
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


def _press(data: str, uid: int = 1) -> FakeQuery:
    q = FakeQuery()
    asyncio.run(handlers._on_cleanup_callback(q, SimpleNamespace(bot=None), uid, data.split(":")))
    return q


def test_archive_button_archives_the_batch_once_and_offers_undo(env):
    text, kb = _press("mc:arch:K1").edits[-1]
    assert env.box.archived == [[111, 222]]
    assert "2 məktub arxivləndi" in text
    assert kb.inline_keyboard[0][0].callback_data == "mc:undo:K1"
    assert env.user.settings["mail_cleanup"] == {"key": "K1", "ids": [], "archived": [111, 222]}

    again = _press("mc:arch:K1")  # ikinci basış poçta toxunmur
    assert env.box.archived == [[111, 222]] and "artıq arxivlənib" in again.edits[-1][0]


def test_undo_returns_the_archived_mail_to_inbox(env):
    _press("mc:arch:K1")
    assert "2 məktub Inbox-a qaytarıldı" in _press("mc:undo:K1").edits[-1][0]
    assert env.user.settings["mail_cleanup"]["archived"] == []


def test_stale_or_foreign_button_does_not_touch_mail(env):
    assert "köhnəlib" in _press("mc:arch:OLD").edits[-1][0]
    assert _press("mc:arch:K1", uid=2).edits == []  # poçt sahibi deyil
    assert env.box.archived == []
