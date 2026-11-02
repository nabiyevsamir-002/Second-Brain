"""Canlı sağlamlıq yoxlaması — quraşdırmanın sonunda və istənilən vaxt:

  docker compose exec bot python scripts/doctor.py
  ... doctor.py --preflight   # yalnız Claude + e-poçt (quraşdırıcı keçiddən əvvəl işlədir)

Telegram, DB, Claude abunəsi, e-poçt. DB-yə heç nə yazmır, modelləri yükləmir.
Çıxış kodu: 0 = işləyir (limit dolu olması da xəbərdarlıqdır, xəta deyil), 1 = düzəldilməli problem.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from telegram import Bot

from app.bot.handlers import backend_label
from app.config import settings
from app.db import SessionLocal
from app.providers.errors import LLMUnavailableError, SubscriptionLimitError
from app.providers.factory import init_providers
from app.providers.registry import providers
from app.timeutils import fmt_local

failed = 0


def good(msg: str) -> None:
    print(f"✅ {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"⚠️  {msg}", flush=True)


def bad(msg: str) -> None:
    global failed
    failed += 1
    print(f"❌ {msg}", flush=True)


async def check_db() -> None:
    try:
        async with SessionLocal() as session:
            notes = (await session.execute(text("SELECT count(*) FROM notes"))).scalar() or 0
            empty = (await session.execute(
                text("SELECT count(*) FROM notes WHERE embedding IS NULL")
            )).scalar() or 0
            rev = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        extra = f", {empty} qeyd hələ indekslənir" if empty else ""
        good(f"Baza: {notes} qeyd{extra} (sxem {rev})")
    except Exception as exc:  # noqa: BLE001
        bad(f"Baza: {exc}")


async def check_telegram() -> None:
    try:
        async with Bot(settings.telegram_bot_token) as bot:
            me = await bot.get_me()
        good(f"Telegram: @{me.username}")
    except Exception as exc:  # noqa: BLE001
        bad(f"Telegram: {exc} — TELEGRAM_BOT_TOKEN-i yoxla")


async def check_claude() -> None:
    if not providers.has("llm"):
        bad("Claude: qurulmayıb — CLAUDE_CODE_OAUTH_TOKEN yoxdur")
        return
    llm = providers.get("llm")
    try:
        resp = await llm.complete(
            system="Qısa cavab ver.",
            messages=[{"role": "user", "content": "Yalnız bu sözü yaz: hazır"}],
            model=llm.model_fast,
        )
        good(f"Claude abunəsi cavab verdi: {llm.text_of(resp)[:40]!r}")
    except SubscriptionLimitError as exc:
        when = ""
        if exc.resets_at:
            reset = datetime.fromtimestamp(exc.resets_at, tz=timezone.utc)
            when = f" — bərpa: {fmt_local(reset, with_weekday=False)}"
        warn(f"Claude abunə limiti doludur{when}. Bot işləyir, limit bərpa olunanda AI qayıdır.")
    except LLMUnavailableError as exc:
        bad(f"Claude: {exc}")


async def check_email() -> None:
    if not providers.has("email"):
        warn("E-poçt qoşulmayıb (istəyə bağlı: EMAIL_ADDRESS + EMAIL_PASSWORD)")
        return
    try:
        unread = await providers.get("email").unread_count()
        good(f"E-poçt ({settings.email_address}): {unread} oxunmamış")
    except Exception as exc:  # noqa: BLE001
        bad(f"E-poçt: {exc} — App Password-u yoxla")


async def main() -> int:
    init_providers()
    print("AI:", backend_label(), flush=True)
    if "--preflight" in sys.argv:  # yalnız Claude tokeni keçidi dayandırır; e-poçt sonra da düzələr
        await check_claude()
        code = 1 if failed else 0
        await check_email()
        return code
    await check_db()
    await check_telegram()
    await check_claude()
    await check_email()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
