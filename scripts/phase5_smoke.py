"""Phase 5 canlı smoke test — konteynerdə işləyir (docker compose run).

Yoxlayır:
  0) pricing: llm/embed/stt xərc hesablaması dəqiqdir.
  1) agent qeyd saxlayır → usage loglanır (llm + embed, cost > 0); usage_totals əks etdirir.
  2) /export: all_notes qeydləri qaytarır, markdown qurulur.
  3) /delete: delete_note qeydi silir.
  4) /settings: update_settings brifinq aç/söndür + saat dəyişir.
  5) count_messages işləyir.

Hər şey TƏK transaction-da, sonda ROLLBACK — DB təmiz qalır.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.config import settings
from app.db import SessionLocal
from app.models import NoteSource
from app.pricing import embed_cost, llm_cost, stt_cost
from app.providers.factory import init_providers
from app.providers.registry import providers
from app.repositories.messages import add_message, count_messages
from app.repositories.notes import all_notes, delete_note
from app.repositories.usage import usage_totals
from app.repositories.users import get_or_create_user, update_settings
from app.services.notes_service import capture_note
from app.timeutils import now_local

TEST_USER_ID = settings.allowed_ids[0] if settings.allowed_ids else 999_000_002


def line(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


async def main() -> None:
    init_providers()
    if not providers.has("agent"):
        print("❌ Agent yoxdur (açarlar lazımdır). Test dayandırıldı.")
        return
    agent = providers.get("agent")
    embed = providers.get("embed")
    llm = providers.get("llm")

    # 0) Pricing ---------------------------------------------------------
    line("TEST 0 — pricing")
    assert llm_cost("claude-sonnet-5", 1_000_000, 1_000_000) == Decimal("18.00")
    assert llm_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == Decimal("6.00")
    assert embed_cost(1_000_000) == Decimal("0.02")
    assert stt_cost(60) == Decimal("0.006")
    print("✅ sonnet-5 1M/1M=$18, haiku 1M/1M=$6, embed 1M=$0.02, stt 60s=$0.006")

    month_start = now_local().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with SessionLocal() as session:
        user = await get_or_create_user(session, TEST_USER_ID, name="Samir Test")

        # 1) Agent LLM usage + birbaşa qeyd embed usage ------------------
        line("TEST 1 — usage tracking (agent llm + capture_note embed)")
        reply = await agent.handle(
            session, user.telegram_id, "Sabah səhər 8-də qaçış xatırlat",
            NoteSource.text, embed, None,
        )
        print(f"agent: {reply[:80]}")
        # Determinik qeyd (embed usage üçün) — birbaşa capture_note.
        await capture_note(
            session, TEST_USER_ID, "Layihə API açarı .env faylındadır (kofe qeydi).",
            NoteSource.text, llm=llm, embedder=embed,
        )
        totals = await usage_totals(session, TEST_USER_ID, month_start)
        print("usage_totals:", {k: (t, str(c)) for k, (t, c) in totals.items()})
        assert "llm" in totals and totals["llm"][1] > 0, "❌ LLM cost loglanmadı!"
        assert "embed" in totals, "❌ Embed usage loglanmadı!"
        print(f"✅ llm=${totals['llm'][1]:.6f}, embed token={totals['embed'][0]}")

        # 2) Export ------------------------------------------------------
        line("TEST 2 — export (all_notes → markdown)")
        notes = await all_notes(session, TEST_USER_ID)
        assert notes, "❌ Qeyd tapılmadı!"
        md = f"# export\n\n## #{notes[0].id}\n{notes[0].cleaned_text or notes[0].raw_text}"
        print(md[:120])
        assert "api" in md.lower() or "açar" in md.lower()
        print(f"✅ {len(notes)} qeyd export markdown-a çevrildi.")

        # 3) Delete ------------------------------------------------------
        line("TEST 3 — delete_note")
        nid = notes[0].id
        deleted = await delete_note(session, TEST_USER_ID, nid)
        assert deleted is not None, "❌ Silinmədi!"
        remaining = await all_notes(session, TEST_USER_ID)
        assert all(n.id != nid for n in remaining), "❌ Qeyd hələ də var!"
        print(f"✅ Qeyd #{nid} silindi. Qalan: {len(remaining)}")

        # 4) Settings ----------------------------------------------------
        line("TEST 4 — settings (brifinq aç/söndür + saat)")
        s = await update_settings(session, TEST_USER_ID, {"briefing_enabled": False})
        assert s["briefing_enabled"] is False
        s = await update_settings(session, TEST_USER_ID, {"briefing_hour": 7})
        assert s["briefing_hour"] == 7 and s["briefing_enabled"] is False
        print(f"✅ settings: {s}")

        # 5) count_messages ---------------------------------------------
        line("TEST 5 — count_messages")
        await add_message(session, TEST_USER_ID, "user", "salam")
        await add_message(session, TEST_USER_ID, "assistant", "salam!")
        n_user = await count_messages(session, TEST_USER_ID, "user", month_start)
        assert n_user >= 1
        print(f"✅ user mesaj sayı (bu ay): {n_user}")

        await session.rollback()

    line("NƏTİCƏ")
    print("✅ Bütün Phase 5 smoke testləri keçdi. (DB rollback edildi.)")


if __name__ == "__main__":
    asyncio.run(main())
