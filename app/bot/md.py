"""Telegram Markdown (v1) köməkçiləri — istifadəçi/LLM mətni mesajı pozmasın.

Qeyd/tapşırıq mətnində tək `_` və ya `*` (məs. e-poçt, fayl adı) olsa, Telegram
"can't parse entities" verir və mesaj ümumiyyətlə getmir (/list, /tasks, brifinq...).
"""

from __future__ import annotations

import re

from telegram.helpers import escape_markdown

_SPECIAL_RE = re.compile(r"[_*`\[]")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+", re.M)  # "#12" və "#tag" toxunulmaz: boşluq tələb olunur
_STAR_BULLET_RE = re.compile(r"^([ \t]*)\*[ \t]+", re.M)


def md(text: str | None) -> str:
    """Entity XARİCİNDƏKİ mətn üçün escape (`\\_`, `\\*` ...)."""
    return escape_markdown(text or "", version=1)


def md_in(text: str | None) -> str:
    """*bold* / _italic_ DAXİLİNƏ qoyulan mətn — orada escape işləmir, simvolları sil."""
    return _SPECIAL_RE.sub("", text or "")


def plain_text(text: str | None) -> str:
    """Agent cavabı düz mətn kimi gedir: Claude-un Markdown-ı ulduz/`#` kimi görünməsin."""
    t = _BOLD_RE.sub(r"\1", text or "")
    t = _HEADING_RE.sub("", t)
    return _STAR_BULLET_RE.sub(r"\1• ", t)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Telegram 4096 simvoldan uzun mesajı qəbul etmir: sətir sonlarından böl."""
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest or not parts:
        parts.append(rest)
    return parts
