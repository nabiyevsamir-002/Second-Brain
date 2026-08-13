"""Phase 4 canlı smoke test — konteynerdə işləyir (docker compose run).

Yoxlayır:
  1) Agent niyyət routing: reminder mesajı → create_reminder tool → Reminder sətri.
  2) Agent niyyət routing: task mesajı → create_task tool → Task sətri.
  3) Nisbi vaxt parse (system prompt-dakı cari Baku vaxtından hesablanır).
  4) deliver_due_reminders seçim sorğusu vaxtı çatmış xatırlatmanı tapır.
  5) Səhər brifinqi mətni qurulur.

Hər şey TƏK transaction-da olur və sonda ROLLBACK edilir — DB təmiz qalır
(real API çağırışları istisna: Claude/OpenAI token xərci var).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from app.bot.scheduler import _build_briefing
from app.config import settings
from app.db import SessionLocal
from app.models import NoteSource
from app.providers.factory import init_providers
from app.providers.registry import providers
from app.repositories.reminders import create_reminder, due_reminders
from app.repositories.tasks import list_open_tasks
from app.repositories.users import get_or_create_user
from app.timeutils import fmt_local, now_local, now_utc

TEST_USER_ID = settings.allowed_ids[0] if settings.allowed_ids else 999_000_001


def line(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


async def main() -> None:
    init_providers()
    if not providers.has("agent"):
        print("❌ Agent yoxdur (ANTHROPIC/OPENAI açarları lazımdır). Test dayandırıldı.")
        return

    agent = providers.get("agent")
    embed = providers.get("embed")

    line("CARİ VAXT")
    print(f"now_local  = {fmt_local(now_local())}")
    print(f"test user  = {TEST_USER_ID}")

    async with SessionLocal() as session:
        user = await get_or_create_user(session, TEST_USER_ID, name="Samir Test")

        # 1) Reminder routing + nisbi vaxt parse ----------------------------
        line("TEST 1 — Reminder (agent)")
        msg1 = "2 saatdan sonra su içməyi xatırlat"
        print(f"user: {msg1}")
        reply1 = await agent.handle(
            session, user.telegram_id, msg1, NoteSource.text, embed, None
        )
        print(f"agent: {reply1}")
        pend = await due_reminders(session, now_utc() + timedelta(days=3650))
        my_rem = [r for r in pend if r.user_id == TEST_USER_ID]
        assert my_rem, "❌ Reminder yaradılmadı!"
        r = my_rem[-1]
        delta_min = (r.remind_at - now_utc()).total_seconds() / 60
        print(f"✅ Reminder #{r.id}: «{r.text}» @ {fmt_local(r.remind_at)} "
              f"(~{delta_min:.0f} dəq sonra)")
        assert 100 < delta_min < 140, f"❌ Vaxt ~2 saat gözlənilirdi, alındı {delta_min:.0f} dəq"

        # 2) Task routing ---------------------------------------------------
        line("TEST 2 — Task (agent)")
        msg2 = "Sabah axşama qədər aylıq hesabatı bitirmək tapşırığı əlavə et"
        print(f"user: {msg2}")
        reply2 = await agent.handle(
            session, user.telegram_id, msg2, NoteSource.text, embed, None
        )
        print(f"agent: {reply2}")
        tasks = await list_open_tasks(session, TEST_USER_ID)
        assert tasks, "❌ Task yaradılmadı!"
        t = tasks[0]
        print(f"✅ Task #{t.id}: «{t.title}» · due={fmt_local(t.due_at) if t.due_at else '—'}")

        # 3) Çatdırılma seçimi (indi vaxtı çatmış reminder) -----------------
        line("TEST 3 — deliver_due_reminders seçimi")
        past = await create_reminder(
            session, TEST_USER_ID, "Keçmiş test xatırlatması", now_utc() - timedelta(minutes=1)
        )
        due_now = await due_reminders(session, now_utc())
        picked = [x.id for x in due_now]
        print(f"vaxtı çatmış (sent=false) tapıldı: {picked}")
        assert past.id in picked, "❌ Vaxtı çatmış reminder seçilmədi!"
        print(f"✅ #{past.id} çatdırılma növbəsinə düşdü (gələcəkdəki #{r.id} DÜŞMƏDİ).")
        assert r.id not in picked, "❌ Gələcək reminder səhvən seçildi!"

        # 4) Səhər brifinqi mətni -------------------------------------------
        line("TEST 4 — Səhər brifinqi mətni")
        briefing = await _build_briefing(session, TEST_USER_ID)
        print(briefing)

        # Heç nə commit etmə — DB təmiz qalsın.
        await session.rollback()

    line("NƏTİCƏ")
    print("✅ Bütün Phase 4 smoke testləri keçdi. (DB rollback edildi — təmiz.)")


if __name__ == "__main__":
    asyncio.run(main())
