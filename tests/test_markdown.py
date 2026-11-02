from decimal import Decimal
from types import SimpleNamespace

from app.bot.handlers import _budget_line, _note_line
from app.bot.md import md, md_in, plain_text, split_message
from app.models import NoteSource
from app.services.budget import BudgetStatus


def test_md_escapes_entity_chars_outside_entities():
    assert md("ali_veli@mail.az *vacib* `kod` [link]") == (
        r"ali\_veli@mail.az \*vacib\* \`kod\` \[link]"
    )
    assert md("adi mətn") == "adi mətn"
    assert md(None) == ""


def test_md_in_strips_chars_inside_entities():
    assert md_in("iş_plan*") == "işplan"
    assert md_in(None) == ""


def test_note_line_is_markdown_safe():
    note = SimpleNamespace(
        id=7,
        source=NoteSource.text,
        summary="ali_veli@mail.az-a yaz",
        cleaned_text=None,
        raw_text="",
        pinned=True,
        category="iş_plan",
    )
    assert _note_line(note) == r"📌 #7 📝 ali\_veli@mail.az-a yaz · _işplan_"


def test_budget_line():
    off = _budget_line(BudgetStatus("off", Decimal("3"), Decimal("0")))
    assert "limit yoxdur" in off
    over = _budget_line(BudgetStatus("over", Decimal("21"), Decimal("20")))
    assert over == (
        "💰 *Aylıq büdcə:* ~$21.00 / $20.00 (105%) — "
        "🔻 soft rejim (Sonnet + səsli cavab söndürülü)"
    )


def test_plain_text_removes_claude_markdown_but_keeps_citations_and_tags():
    assert plain_text("**Leyla** görüşü [#1]\n## Başlıq\n* bənd\n#12 qeydi #iş") == (
        "Leyla görüşü [#1]\nBaşlıq\n• bənd\n#12 qeydi #iş"
    )
    assert plain_text("https://x.az/a__b__c") == "https://x.az/a__b__c"
    assert plain_text(None) == ""


def test_split_message_respects_the_telegram_limit():
    assert split_message("qısa") == ["qısa"]
    assert split_message("") == [""]
    long = ("sətir " * 40 + "\n") * 40
    parts = split_message(long, limit=1000)
    assert len(parts) > 1 and all(len(p) <= 1000 for p in parts)
    assert "".join(parts).replace("\n", "") == long.replace("\n", "")
    assert all(len(p) <= 50 for p in split_message("x" * 120, limit=50))
