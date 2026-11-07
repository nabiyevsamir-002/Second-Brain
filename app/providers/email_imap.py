"""IMAP e-poçt oxuyucu (Gmail, Outlook, Yandex, Mail.ru ...) + Gmail-də düymə ilə arxiv.

• Oxuyanda qovluq readonly seçilir və BODY.PEEK işlədilir → məktublar "oxunmuş" olmur.
• Yazma yalnız poçt təmizliyində (yalnız Gmail, yalnız istifadəçi düyməni basanda):
  arxiv = Inbox etiketini götürmək; silmə = Zibil qutusuna köçürmək (Gmail 30 gün saxlayır).
  Hər ikisi geri qaytarılır; birdəfəlik silmə (expunge) yoxdur.
• Gmail: 2 addımlı doğrulama + App Password (adi Google parolu IMAP-da işləmir).
• imaplib sinxrondur → asyncio.to_thread; hər əməliyyat qısa ömürlü bağlantı açır.
• Hər poçtun öz provayderi var: label — mesajlardakı qısa adı («abc»), slot — sırası (1, 2).
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup

from app.logging_conf import get_logger

log = get_logger("email")

SNIPPET_BYTES = 65536  # siyahı üçün məktubun ilk 64KB-ı (başlıqlar + mətnin əvvəli)
MAX_BODY_BYTES = 2_000_000
MAX_NEW = 10  # bir yoxlamada bildirilən maksimum yeni məktub
_UID_RE = re.compile(rb"UID (\d+)")
_FLAGS_RE = re.compile(rb"FLAGS \(([^)]*)\)")
_SIZE_RE = re.compile(rb"RFC822\.SIZE (\d+)")
_MSGID_RE = re.compile(rb"X-GM-MSGID (\d+)")
_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$')
# Poçt təmizliyi: siyahını Gmail-in öz «Reklamlar» bölməsi verir (Claude yox), ulduzlulara toxunma.
PROMO_QUERY = "category:promotions -is:starred"
# Silmə namizədləri: «Əsas» (şəxsi) bölmə və ulduzlu məktublar heç vaxt təklif olunmur.
CLEANUP_QUERY = "-category:primary -is:starred"
MAX_CLEANUP = 500  # bir dəfədə arxivlənən maksimum məktub
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass
class Mail:
    uid: int
    sender: str
    subject: str
    date: datetime | None
    unread: bool
    snippet: str = ""
    body: str = ""
    bulk: bool = False  # reklam/bülleten (List-Unsubscribe / Precedence: bulk)


def mailbox_labels(addresses: list[str]) -> list[str]:
    """Poçtların qısa adları: abcdef…@ → abc. Tək poçtda ad lazım deyil (boş).

    Adlar üst-üstə düşsə və ya /mail əmrləri ilə qarışsa: p1, p2.
    """
    if len(addresses) < 2:
        return [""] * len(addresses)
    labels = [re.sub(r"[^a-z0-9]", "", a.split("@")[0].lower())[:3] for a in addresses]
    clash = len(set(labels)) < len(labels) or any(
        not x or x.isdigit() or x in ("on", "off", "sil") for x in labels
    )
    return [f"p{i}" for i in range(1, len(labels) + 1)] if clash else labels


def imap_date(d: date) -> str:
    """IMAP SINCE formatı (01-Oct-2026) — lokaldan asılı olmayan ay adları."""
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _body_text(msg: EmailMessage) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        try:
            content = part.get_content()
        except (LookupError, ValueError):  # naməlum charset
            content = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if part.get_content_subtype() == "html":
            content = BeautifulSoup(content, "html.parser").get_text("\n")
    except Exception:  # noqa: BLE001 — qismən (kəsilmiş) MIME və ya pozuq məktub
        return ""
    content = re.sub(r"[ \t\r\f\v]+", " ", content)
    return re.sub(r"\n\s*\n+", "\n\n", content).strip()


def parse_mail(
    uid: int, raw: bytes, flags: bytes = b"", *, full: bool = False,
    fallback_date: datetime | None = None,
) -> Mail:
    msg = email.message_from_bytes(raw, policy=default_policy)
    name, addr = parseaddr(str(msg.get("From", "")))
    sender = f"{name} <{addr}>" if name and addr else (addr or name or "?")
    try:
        when = parsedate_to_datetime(str(msg["Date"])) if msg["Date"] else None
    except (TypeError, ValueError, IndexError):
        when = None
    when = when or fallback_date  # Date başlığı yoxdursa serverin INTERNALDATE-i
    body = _body_text(msg)
    precedence = str(msg.get("Precedence", "")).strip().lower()
    return Mail(
        uid=uid,
        sender=sender,
        subject=(str(msg.get("Subject", "")).strip() or "(mövzusuz)"),
        date=when,
        unread=b"\\Seen" not in flags,
        snippet=body[:400],
        body=body if full else "",
        bulk=bool(msg.get("List-Unsubscribe")) or precedence in ("bulk", "list", "junk"),
    )


def _fetch_items(data: list) -> list[tuple[int, bytes, bytes]]:
    """FETCH cavabından (uid, meta-sətir, literal) — UID literal-dan SONRA da gələ bilər."""
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, tuple):
            continue
        meta, literal = item[0], item[1]
        m = _UID_RE.search(meta)
        if m is None and i + 1 < len(data) and isinstance(data[i + 1], bytes):
            meta = meta + data[i + 1]
            m = _UID_RE.search(meta)
        if m:
            out.append((int(m.group(1)), meta, literal))
    return out


class ImapMailProvider:
    def __init__(
        self, host: str, port: int, address: str, password: str,
        folder: str = "INBOX", ssl: bool = True, label: str = "", slot: int = 1,
    ) -> None:
        self.host, self.port = host, port
        self.address, self._password = address, password
        self.folder, self.ssl = folder, ssl
        self.label, self.slot = label, slot

    # --- sinxron (thread-də) ---------------------------------------------
    def _connect(self) -> imaplib.IMAP4:
        cls = imaplib.IMAP4_SSL if self.ssl else imaplib.IMAP4
        conn = cls(self.host, self.port, timeout=30)
        conn.login(self.address, self._password)
        typ, _ = conn.select(_quote(self.folder), readonly=True)
        if typ != "OK":
            conn.logout()
            raise RuntimeError(f"qovluq açılmadı: {self.folder}")
        return conn

    @staticmethod
    def _close(conn: imaplib.IMAP4) -> None:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _untagged_int(conn: imaplib.IMAP4, key: str) -> int | None:
        _, data = conn.response(key)
        try:
            return int(data[0]) if data and data[0] else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _uids(conn: imaplib.IMAP4, *criteria: str, literal: str | None = None) -> list[int]:
        if literal is not None:
            conn.literal = literal.encode("utf-8")  # UTF-8 axtarış mətni (ə, ş, ğ ...)
            typ, data = conn.uid("SEARCH", "CHARSET", "UTF-8", *criteria)
        else:
            typ, data = conn.uid("SEARCH", *criteria)
        if typ != "OK":
            raise RuntimeError("IMAP axtarışı uğursuz oldu")
        return sorted(int(x) for x in (data[0] or b"").split())

    @staticmethod
    def _fetch(conn: imaplib.IMAP4, uids: list[int], *, full: bool = False) -> list[Mail]:
        if not uids:
            return []
        uid_set = ",".join(str(u) for u in uids)
        _, meta = conn.uid("FETCH", uid_set, "(UID FLAGS RFC822.SIZE INTERNALDATE)")
        flags: dict[int, bytes] = {}
        sizes: dict[int, int] = {}
        dates: dict[int, datetime] = {}
        for line in meta:
            line = line[0] if isinstance(line, tuple) else line
            m = _UID_RE.search(line or b"")
            if m:
                uid = int(m.group(1))
                f = _FLAGS_RE.search(line)
                s = _SIZE_RE.search(line)
                flags[uid] = f.group(1) if f else b""
                sizes[uid] = int(s.group(1)) if s else 0
                internal = imaplib.Internaldate2tuple(line)
                if internal:
                    dates[uid] = datetime.fromtimestamp(time.mktime(internal), tz=timezone.utc)
        big = full and any(v > MAX_BODY_BYTES for v in sizes.values())
        if full and not big:
            section = "BODY.PEEK[]"
        else:
            section = f"BODY.PEEK[]<0.{MAX_BODY_BYTES if full else SNIPPET_BYTES}>"
        _, data = conn.uid("FETCH", uid_set, f"(UID {section})")
        mails = []
        for uid, _meta, raw in _fetch_items(data):
            try:
                mails.append(parse_mail(uid, raw, flags.get(uid, b""), full=full,
                                        fallback_date=dates.get(uid)))
            except Exception as exc:  # noqa: BLE001 — bir pozuq məktub siyahını sındırmasın
                log.warning("mail_parse_failed", uid=uid, error=str(exc))
        return sorted(mails, key=lambda x: x.uid, reverse=True)

    @staticmethod
    def _msgids(conn: imaplib.IMAP4, uids: list[int]) -> dict[int, int]:
        """UID → Gmail X-GM-MSGID (qovluqdan asılı olmayan sabit id)."""
        if not uids:
            return {}
        _, data = conn.uid("FETCH", ",".join(str(u) for u in uids), "(X-GM-MSGID)")
        out: dict[int, int] = {}
        for line in data or []:
            line = line[0] if isinstance(line, tuple) else line
            u, g = _UID_RE.search(line or b""), _MSGID_RE.search(line or b"")
            if u and g:
                out[int(u.group(1))] = int(g.group(1))
        return out

    @staticmethod
    def _special_folder(conn: imaplib.IMAP4, flag: bytes) -> str:
        """Gmail xüsusi qovluğu (\\All, \\Trash): adı dilə görə dəyişir, bayraqla tapılır."""
        _, data = conn.list()
        for line in data or []:
            m = _LIST_RE.match(line) if isinstance(line, bytes) else None
            if m and flag in m.group("flags").split():
                return m.group("name").decode()
        raise RuntimeError(f"Gmail qovluğu tapılmadı: {flag.decode()}")

    @staticmethod
    def _move(conn: imaplib.IMAP4, uids: list[int], folder: str) -> None:
        typ, _ = conn.uid("MOVE", ",".join(str(u) for u in uids), folder)
        if typ != "OK":
            raise RuntimeError("məktublar köçürülmədi")

    @classmethod
    def _uids_by_msgid(cls, conn: imaplib.IMAP4, msgids: list[int]) -> list[int]:
        """Seçilmiş qovluqda X-GM-MSGID-lərin UID-ləri (50-lik OR axtarışları ilə)."""
        uids: list[int] = []
        for i in range(0, len(msgids), 50):
            chunk = msgids[i : i + 50]
            criteria = ["OR"] * (len(chunk) - 1)
            for mid in chunk:
                criteria += ["X-GM-MSGID", str(mid)]
            uids += cls._uids(conn, *criteria)
        return uids

    def _set_inbox_label(self, conn: imaplib.IMAP4, msgids: list[int], *, add: bool) -> int:
        """Inbox etiketini «All Mail»-da götür/qoy → dəyişən məktubların sayı.

        Inbox-un özündə Gmail bu STORE-a OK qaytarır, amma etiket yerində qalır (real
        poçtda yoxlanıb) — ona görə yazma həmişə «All Mail» qovluğunda gedir.
        """
        typ, _ = conn.select(self._special_folder(conn, b"\\All"), readonly=False)
        if typ != "OK":
            raise RuntimeError("Gmail «All Mail» qovluğu açılmadı")
        uids = self._uids_by_msgid(conn, msgids)
        if uids:
            typ, _ = conn.uid(
                "STORE", ",".join(str(u) for u in uids),
                "+X-GM-LABELS" if add else "-X-GM-LABELS", "(\\Inbox)",
            )
            if typ != "OK":
                raise RuntimeError("Gmail etiketi dəyişmədi")
        return len(uids)

    def _search_inbox(self, conn: imaplib.IMAP4, query: str) -> list[int]:
        if self.folder.upper() != "INBOX":  # arxiv/silmə Inbox-dan çıxarmaq deməkdir
            raise RuntimeError("Poçt təmizliyi yalnız INBOX qovluğu ilə işləyir")
        return self._uids(conn, "X-GM-RAW", _quote(query))

    def _run(self, fn):
        conn = self._connect()
        try:
            return fn(conn)
        finally:
            self._close(conn)

    # --- async API -------------------------------------------------------
    async def recent(self, limit: int = 10, unread_only: bool = False) -> list[Mail]:
        def work(conn):
            uids = self._uids(conn, "UNSEEN" if unread_only else "ALL")
            return self._fetch(conn, uids[-limit:])

        return await asyncio.to_thread(self._run, work)

    async def get(self, uid: int) -> Mail | None:
        def work(conn):
            found = self._fetch(conn, [uid], full=True)
            return found[0] if found else None

        return await asyncio.to_thread(self._run, work)

    async def search(
        self, text: str = "", sender: str = "", days: int = 0, limit: int = 10
    ) -> list[Mail]:
        criteria: list[str] = []
        literal = None
        if sender:
            if sender.isascii():
                criteria += ["FROM", _quote(sender)]
            elif not text:
                criteria.append("FROM")
                literal = sender
        if days and days > 0:
            criteria += ["SINCE", imap_date(date.today() - timedelta(days=int(days)))]
        if text:
            criteria.append("TEXT")  # literal sonda gəlməlidir
            literal = text
        if not criteria:
            criteria = ["ALL"]

        def work(conn):
            uids = self._uids(conn, *criteria, literal=literal)
            return self._fetch(conn, uids[-limit:])

        return await asyncio.to_thread(self._run, work)

    async def unread_count(self) -> int:
        return await asyncio.to_thread(self._run, lambda conn: len(self._uids(conn, "UNSEEN")))

    # --- poçt təmizliyi (Gmail) ------------------------------------------
    async def promotions(self, limit: int = 10) -> tuple[list[int], list[Mail]]:
        """(namizədlərin X-GM-MSGID-ləri — ən çox MAX_CLEANUP, ən yeni `limit` məktub)."""

        def work(conn):
            uids = self._search_inbox(conn, PROMO_QUERY)[-MAX_CLEANUP:]
            ids = self._msgids(conn, uids)
            return [ids[u] for u in reversed(uids) if u in ids], self._fetch(conn, uids[-limit:])

        return await asyncio.to_thread(self._run, work)

    async def archive(self, msgids: list[int]) -> list[int]:
        """Seçilmiş reklam məktublarını arxivlə (Inbox etiketini götür) → arxivlənənlərin id-si.

        Yalnız hələ Inbox-da olan ulduzsuz reklam məktublarına toxunur: arada ulduz qoyulubsa
        və ya məktub başqa bölməyə keçibsə, yerində qalır.
        """
        wanted = set(msgids)

        def work(conn):
            uids = self._search_inbox(conn, PROMO_QUERY)
            ids = self._msgids(conn, uids)
            hit = [ids[u] for u in uids if ids.get(u) in wanted]
            if hit:
                self._set_inbox_label(conn, hit, add=False)
            return hit

        return await asyncio.to_thread(self._run, work)

    async def unarchive(self, msgids: list[int]) -> int:
        """Arxivlənmiş məktubları Inbox-a qaytar (etiketi geri qoy) → qaytarılanların sayı."""
        return await asyncio.to_thread(
            self._run, lambda conn: self._set_inbox_label(conn, msgids, add=True)
        )

    async def cleanup_candidates(
        self, exclude: set[int], limit: int = 25
    ) -> list[tuple[int, Mail]]:
        """Silmə namizədləri (CLEANUP_QUERY): ən yeni `limit` məktub, `exclude` id-ləri xaric."""

        def work(conn):
            uids = self._search_inbox(conn, CLEANUP_QUERY)
            ids = self._msgids(conn, uids)
            fresh = [u for u in reversed(uids) if u in ids and ids[u] not in exclude][:limit]
            return [(ids[m.uid], m) for m in self._fetch(conn, fresh)]

        return await asyncio.to_thread(self._run, work)

    async def trash(self, msgids: list[int]) -> list[int]:
        """Məktubları Zibil qutusuna köçür (Gmail 30 gün saxlayır) → köçənlərin id-si.

        Yalnız hələ Inbox-da olan, ulduzsuz və «Əsas»dan kənar məktublara toxunur: arada
        ulduz qoyulubsa və ya məktub «Əsas»a keçibsə, yerində qalır.
        """
        wanted = set(msgids)

        def work(conn):
            typ, _ = conn.select(_quote(self.folder), readonly=False)
            if typ != "OK":
                raise RuntimeError(f"qovluq yazma üçün açılmadı: {self.folder}")
            uids = self._search_inbox(conn, CLEANUP_QUERY)
            ids = self._msgids(conn, uids)
            hit = [u for u in uids if ids.get(u) in wanted]
            if hit:
                self._move(conn, hit, self._special_folder(conn, b"\\Trash"))
            return [ids[u] for u in hit]

        return await asyncio.to_thread(self._run, work)

    async def untrash(self, msgids: list[int]) -> int:
        """Zibil qutusundakı məktubları Inbox-a qaytar → qaytarılanların sayı."""

        def work(conn):
            typ, _ = conn.select(self._special_folder(conn, b"\\Trash"), readonly=False)
            if typ != "OK":
                raise RuntimeError("Gmail Zibil qutusu açılmadı")
            uids = self._uids_by_msgid(conn, msgids)
            if uids:
                self._move(conn, uids, _quote(self.folder))
            return len(uids)

        return await asyncio.to_thread(self._run, work)

    async def poll_new(
        self, last_uid: int | None, uidvalidity: int | None
    ) -> tuple[int | None, int, list[Mail]]:
        """(uidvalidity, son UID, last_uid-dən sonrakı yeni məktublar ≤ MAX_NEW).

        İlk dəfə (və ya UIDVALIDITY dəyişibsə) yalnız baza nöqtəsi qaytarılır — köhnə
        məktublar barədə bildiriş getmir.
        """

        def work(conn):
            uv = self._untagged_int(conn, "UIDVALIDITY")
            uidnext = self._untagged_int(conn, "UIDNEXT")
            if last_uid is None or uv != uidvalidity:
                if uidnext:
                    return uv, uidnext - 1, []
                uids = self._uids(conn, "ALL")
                return uv, (uids[-1] if uids else 0), []
            uids = [u for u in self._uids(conn, f"UID {last_uid + 1}:*") if u > last_uid]
            if not uids:
                return uv, last_uid, []
            return uv, uids[-1], self._fetch(conn, uids[-MAX_NEW:])

        return await asyncio.to_thread(self._run, work)
