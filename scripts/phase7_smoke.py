"""Phase 7 smoke test — əlaqəli qeydlər + soft aylıq büdcə (real Postgres/pgvector).

Yoxlayır (API açarı LAZIM DEYİL — sintetik embedding-lər):
  1) find_related: saxlanmış link (hər iki istiqamət) + vektor qonşuları birləşir;
     hədd (0.68) üstündəkilər və başqa istifadəçinin qeydləri düşmür.
  2) get_related_notes tool çıxışı [#id] formatındadır, başqasının qeydi gizlidir.
  3) get_budget_status: usage_log xərcinə görə ok → warn → over (istifadəçi başına).
  --live: real agent «#id ilə əlaqəli nə var?» → get_related_notes çağırır (açarlar lazımdır).

Hər şey TƏK transaction-da, sonda ROLLBACK — DB təmiz qalır.

Host-dan (lokal DB 5433):
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/second_brain \\
    .venv/bin/python scripts/phase7_smoke.py [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import math
from decimal import Decimal

from app.config import settings
from app.db import SessionLocal
from app.models import NoteSource
from app.repositories.links import add_link, find_related, linked_notes
from app.repositories.notes import create_note
from app.repositories.usage import log_usage
from app.repositories.users import get_or_create_user
from app.services.budget import get_budget_status
from app.tools.base import ToolContext
from app.tools.get_related_notes import GetRelatedNotesTool

TEST_USER = 999_000_007
OTHER_USER = 999_000_008
DIM = 1536


def vec(*pairs: tuple[int, float]) -> list[float]:
    """Seyrək (index, dəyər) → 1536 ölçülü vahid vektor (cosine məsafəni idarə etmək üçün)."""
    v = [0.0] * DIM
    for i, x in pairs:
        v[i] = x
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def line(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


async def main(live: bool) -> None:
    async with SessionLocal() as session:
        try:
            await get_or_create_user(session, TEST_USER, name="Smoke Test")
            await get_or_create_user(session, OTHER_USER, name="Başqası")

            async def note(uid: int, text: str, emb: list[float]):
                return await create_note(
                    session, uid, text, NoteSource.text,
                    cleaned_text=text, summary=text, category="test", embedding=emb,
                )

            a = await note(TEST_USER, "Diş həkimi randevusu", vec((0, 1)))
            b = await note(TEST_USER, "Sığorta kartını götür", vec((0, 0.6), (1, 0.8)))  # 0.4
            c = await note(TEST_USER, "Kitab siyahısı", vec((0, 0.2), (2, 0.98)))  # ~0.8
            d = await note(TEST_USER, "Klinikanın ünvanı", vec((3, 1)))  # uzaq, amma link var
            e = await note(OTHER_USER, "Başqasının diş qeydi", vec((0, 1)))  # eyni vektor
            await add_link(session, a.id, d.id, score=0.9)  # A → D
            await add_link(session, b.id, a.id, score=0.6)  # B → A (əks istiqamət)

            line("TEST 1 — linked_notes + find_related")
            linked = await linked_notes(session, TEST_USER, a.id)
            assert [n.id for n, _ in linked] == [d.id, b.id], linked
            related = await find_related(session, TEST_USER, a, k=5)
            ids = [n.id for n, _ in related]
            assert ids == [d.id, b.id], ids
            print(f"✅ #{a.id} → {[(n.id, round(s, 2)) for n, s in related]} "
                  f"(#{c.id} həddən uzaq, #{e.id} başqa user — düşdü)")
            rel_b = await find_related(session, TEST_USER, b, k=5)
            assert [n.id for n, _ in rel_b] == [a.id], rel_b
            print(f"✅ #{b.id} → [#{a.id}] (link + vektor eyni qeyddir — dublikat yoxdur)")

            line("TEST 2 — get_related_notes tool")
            ctx = ToolContext(
                session=session, user_id=TEST_USER, llm=None, embedder=None,
                source=NoteSource.text,
            )
            out = await GetRelatedNotesTool().run(ctx, note_id=a.id)
            print(out)
            assert f"[#{d.id}]" in out and f"[#{b.id}]" in out and f"[#{c.id}]" not in out
            assert "tapılmadı" in await GetRelatedNotesTool().run(ctx, note_id=e.id)
            print("✅ [#id] formatı + başqasının qeydi gizli")

            line("TEST 3 — soft büdcə (usage_log)")
            settings.monthly_budget_usd = 20.0
            settings.budget_warn_pct = 80
            assert (await get_budget_status(session, TEST_USER)).state == "ok"
            await log_usage(session, TEST_USER, "llm", tokens=1000, cost=Decimal("17"))
            st = await get_budget_status(session, TEST_USER)
            assert (st.state, st.pct) == ("warn", 85), st
            await log_usage(session, TEST_USER, "tts", cost=Decimal("4"))
            st = await get_budget_status(session, TEST_USER)
            assert st.state == "over" and st.degraded, st
            assert (await get_budget_status(session, OTHER_USER)).state == "ok"
            print(f"✅ ok → warn (85%) → over (${st.spent:.2f}) · başqa user təsirlənmir")

            if live:
                line("TEST 4 — LIVE agent: «#id ilə əlaqəli nə var?»")
                from app.providers.factory import init_providers
                from app.providers.registry import providers

                init_providers()
                if not providers.has("agent"):
                    raise SystemExit("❌ Agent yoxdur (ANTHROPIC/OPENAI açarları lazımdır).")
                calls: list[dict] = []
                original = GetRelatedNotesTool.run

                async def spy(self, ctx, **kwargs):
                    calls.append(kwargs)
                    return await original(self, ctx, **kwargs)

                GetRelatedNotesTool.run = spy
                reply = await providers.get("agent").handle(
                    session, TEST_USER, f"#{a.id} ilə əlaqəli nə var?",
                    NoteSource.text, providers.get("embed"), [],
                )
                print(reply)
                assert calls, "agent get_related_notes çağırmadı"
                assert int(str(calls[0]["note_id"]).lstrip("#")) == a.id, calls
                assert f"#{d.id}" in reply or f"#{b.id}" in reply, reply
                print(f"✅ agent get_related_notes(note_id={a.id}) çağırdı, sitatla cavab verdi")
        finally:
            await session.rollback()

    print("\n🎉 Hamısı keçdi (ROLLBACK — DB təmiz qaldı).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="real agent çağırışı (açar lazımdır)")
    asyncio.run(main(parser.parse_args().live))
