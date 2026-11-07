"""E-poçt: MIME parse, IMAP FETCH cavabı, bildiriş formatı (server lazım deyil)."""

import asyncio
from datetime import date
from email.message import EmailMessage
from types import SimpleNamespace

from app.providers.email_imap import Mail, _fetch_items, imap_date, parse_mail
from app.services.email_watch import check_new_mail, format_new_mail, short_sender, triage


def _raw(subject="Salam", sender="Əli Məmmədov <ali@firma.az>", text=None, html=None, **headers):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "samir@test.az", subject
    m["Date"] = "Fri, 30 Oct 2026 09:15:00 +0400"
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    if text:
        m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html") if text else m.set_content(html, subtype="html")
    return m.as_bytes()


def test_parse_plain_utf8_mail():
    m = parse_mail(5, _raw(subject="Hesabat sabaha qədər", text="Rüblük hesabatı göndər."),
                   b"\\Seen")
    assert (m.uid, m.sender, m.subject, m.unread) == (5, "Əli Məmmədov <ali@firma.az>",
                                                     "Hesabat sabaha qədər", False)
    assert m.snippet == "Rüblük hesabatı göndər." and m.body == ""
    assert m.date.isoformat() == "2026-10-30T09:15:00+04:00"


def test_parse_html_only_bulk_mail():
    raw = _raw(html="<p>Yalnız <b>bu həftə</b> endirim</p>", List_Unsubscribe="<mailto:u@x.az>")
    m = parse_mail(1, raw, full=True)
    assert m.bulk and m.unread
    assert "bu həftə" in m.body and "<b>" not in m.body


def test_broken_mail_does_not_crash():
    m = parse_mail(2, b"From: x\r\nSubject: \r\n\r\n\xff\xfe garbage")
    assert m.subject == "(mövzusuz)" and m.sender == "x"


def test_fetch_items_handles_uid_after_literal():
    data = [
        (b"1 (UID 41 BODY[]<0> {3}", b"abc"), b")",
        (b"2 (BODY[]<0> {3}", b"def"), b" UID 42)",
        b"garbage",
    ]
    assert [(u, lit) for u, _, lit in _fetch_items(data)] == [(41, b"abc"), (42, b"def")]


def test_imap_date_is_locale_independent():
    assert imap_date(date(2026, 10, 1)) == "01-Oct-2026"


def _mail(uid, subject, bulk=False, sender="Leyla <l@x.az>"):
    return Mail(uid=uid, sender=sender, subject=subject, date=None, unread=True, bulk=bulk)


def test_format_new_mail_hides_noise():
    mails = [_mail(1, "Görüş"), _mail(2, "Endirim", bulk=True), _mail(3, "Müqavilə")]
    text = format_new_mail(mails, {3: ("high", "Bu gün imzalanmalıdır.")})
    assert text.splitlines() == [
        "📬 3 yeni məktub:", "🟡 Leyla — Görüş", "🔴 Leyla — Müqavilə",
        "   ↳ Bu gün imzalanmalıdır.", "⚪ +1 reklam/bildiriş", "Oxumaq: /mail <uid> · /mail",
    ]
    assert format_new_mail([_mail(2, "Endirim", bulk=True)], {}) is None
    assert short_sender('"Əli" <a@b.az>') == "Əli"


class FakeLLM:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def complete(self, **kw):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])

    @staticmethod
    def text_of(r):
        return r.content[0].text


def test_triage_tolerates_bad_items():
    llm = FakeLLM('{"items": [{"uid": 3, "importance": "HIGH", "summary": "x"}, {"uid": "?"}, '
                  '{"uid": 4, "importance": "weird"}]}')
    assert asyncio.run(triage(llm, [_mail(3, "a"), _mail(4, "b")])) == {
        3: ("high", "x"), 4: ("normal", "")}


def test_check_new_mail_skips_ai_for_newsletters():
    class Box:
        label, slot = "", 1

        async def poll_new(self, last, uv):
            return 9, 12, [_mail(12, "Endirim", bulk=True)]

    llm = FakeLLM("{}")
    text, changes = asyncio.run(check_new_mail(Box(), llm, {"email_last_uid": 11}))
    assert text is None and changes == {"email_uidvalidity": 9, "email_last_uid": 12}
    assert llm.calls == 0  # yalnız reklam → Claude çağırılmır (abunə limiti qorunur)
