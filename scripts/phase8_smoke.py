"""Phase 8 smoke test — Claude abunəsi + lokal modellər + e-poçt (konteynerdə).

İşə salma (PC və ya Mac, Docker):
  docker compose run --rm bot python scripts/phase8_smoke.py            # açarsız hissə
  docker compose run --rm bot python scripts/phase8_smoke.py --live     # + Claude + e-poçt
  ... --audio /yol/səs.ogg   # lokal Whisper-i real səslə yoxla

Yoxlayır:
  1) Lokal embedding (AZ): hybrid axtarış düzgün qeydi tapır; əlaqəli qeyd həddi.
  2) Lokal Whisper yüklənir (və --audio verilsə transkript edir).
  3) Embedding modeli dəyişikliyi: köhnə (OpenAI) vektorlar sıfırlanır → backfill doldurur.
  --live: 4) Claude abunəsi sadə cavab; 5) agent qeyd saxlayır və sualı sitatla cavablandırır;
          5b) şəkil OCR (vision); 6) e-poçt qoşulubsa son 3 məktub.
Hər şey TƏK transaction-da, sonda ROLLBACK — DB təmiz qalır.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import AppMeta, Note, NoteSource
from app.providers.factory import init_providers
from app.providers.registry import providers
from app.repositories.links import find_related, related_threshold
from app.repositories.notes import create_note, hybrid_search_notes
from app.repositories.users import get_or_create_user
from app.services.reembed import LEGACY_MODEL_ID, META_KEY, backfill_embeddings, ensure_embedding_model

TEST_USER = settings.allowed_ids[0] if settings.allowed_ids else 999_000_009

NOTES = {
    "dentist": "Sabah saat 10-da diş həkiminə getməliyəm, sığorta kartını unutma",
    "health": "Həkim dedi ki, hər gün 30 dəqiqə piyada gəzməliyəm və şəkəri azaltmalıyam",
    "report": "Layihə hesabatını cümə gününə qədər müdirə təqdim etmək lazımdır",
    "bills": "Bu ay elektrik və qaz pulunu ödəməyi unutma, 85 manat",
}


def line(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


async def main(live: bool, audio: str | None) -> None:
    init_providers()
    from app.bot.handlers import backend_label

    print("AI:", backend_label())
    embed = providers.get("embed")

    async with SessionLocal() as session:
        try:
            await get_or_create_user(session, TEST_USER, name="Smoke Test")

            line("TEST 1 — lokal embedding + axtarış (AZ)")
            t = time.time()
            vecs = await embed.embed(list(NOTES.values()))
            notes = {}
            for (key, text), vec in zip(NOTES.items(), vecs):
                notes[key] = await create_note(session, TEST_USER, text, NoteSource.text,
                                               cleaned_text=text, embedding=vec)
            print(f"embed {len(vecs)} qeyd: {time.time() - t:.1f}s ({embed.model_id})")
            for query, want in (("stomatoloq randevum", "dentist"), ("kommunal xərclər", "bills"),
                                ("işdə hansı sənədi təhvil verməliyəm", "report")):
                hits = await hybrid_search_notes(session, TEST_USER, await embed.embed_one(query),
                                                 query, k=3)
                top = hits[0][0].id if hits else None
                ok = "✅" if top == notes[want].id else "❌"
                print(f"{ok} '{query}' → #{top} (gözlənilən #{notes[want].id})")
                assert top == notes[want].id
            rel = await find_related(session, TEST_USER, notes["dentist"],
                                     max_distance=related_threshold(embed))
            print(f"əlaqəli (hədd {related_threshold(embed)}): "
                  f"{[(n.id, round(s, 2)) for n, s in rel]}")

            line("TEST 2 — lokal Whisper")
            stt = providers.get("stt")
            t = time.time()
            if hasattr(stt, "warmup"):
                stt.warmup()
            print(f"model hazır: {time.time() - t:.1f}s")
            if audio:
                t = time.time()
                transcript = await stt.transcribe(audio, "az")
                print(f"transkript ({time.time() - t:.1f}s): {transcript}")

            if live:
                line("TEST 4 — Claude abunəsi (sadə cavab)")
                llm = providers.get("llm")
                t = time.time()
                resp = await llm.complete(system="Qısa cavab ver.", messages=[
                    {"role": "user", "content": "Bir sözlə: Azərbaycanın paytaxtı?"}])
                print(f"✅ {llm.text_of(resp)!r} ({time.time() - t:.1f}s)")

                line("TEST 5 — agent: qeyd saxla + sitatla cavab")
                agent = providers.get("agent")
                t = time.time()
                r1 = await agent.handle(session, TEST_USER,
                                        "Qeyd et: Leyla ilə layihə görüşü cümə saat 15:00-dadır",
                                        NoteSource.text, embed, [])
                print(f"1) {r1} ({time.time() - t:.1f}s)")
                t = time.time()
                r2 = await agent.handle(session, TEST_USER, "Leyla ilə görüş nə vaxtdır?",
                                        NoteSource.text, embed, [])
                print(f"2) {r2} ({time.time() - t:.1f}s)")
                assert "15" in r2, "agent saxlanmış qeydi tapmadı"

                line("TEST 5b — şəkil OCR (vision, streaming input)")
                import io

                from PIL import Image, ImageDraw

                from app.services.ingest_service import ingest_image

                img = Image.new("RGB", (420, 120), "white")
                ImageDraw.Draw(img).text((20, 45), "SALAM SAMIR 2026", fill="black")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                t = time.time()
                note = await ingest_image(session, providers.get("llm"), embed, TEST_USER,
                                          buf.getvalue(), media_type="image/png")
                print(f"✅ #{note.id}: {note.raw_text[:80]!r} ({time.time() - t:.1f}s)")
                assert "2026" in note.raw_text

                if providers.has("email"):
                    line("TEST 6 — e-poçt (hər poçtdan son 3 məktub)")
                    for box in providers.get("email"):
                        for m in await box.recent(limit=3):
                            dot = "●" if m.unread else " "
                            print(f"  {dot} {box.label} {m.uid} · {m.sender} — {m.subject}")

            line("TEST 3 — embedding modeli dəyişikliyi → təkrar embed")
            total = await session.scalar(select(func.count()).select_from(Note))
            if total > len(NOTES) + 200:  # canlı baza: bütün qeydlərə uzun kilid qoymayaq
                print(f"⏭ ötürüldü: bazada {total} qeyd var (canlı data)")
                return
            meta = await session.get(AppMeta, META_KEY)
            if meta is None:
                session.add(AppMeta(key=META_KEY, value=LEGACY_MODEL_ID))
            else:
                meta.value = LEGACY_MODEL_ID
            await session.flush()
            invalidated = await ensure_embedding_model(session, embed.model_id)
            filled = 0
            while n := await backfill_embeddings(session, embed):
                filled += n
            left = (await session.execute(
                select(Note.id).where(Note.user_id == TEST_USER, Note.embedding.is_(None))
            )).first()
            print(f"✅ sıfırlandı={invalidated}, yenidən embed={filled}, boş qalan={left is not None}")
            assert invalidated >= len(NOTES) and left is None
        finally:
            await session.rollback()

    print("\n🎉 Hamısı keçdi (ROLLBACK — DB təmiz qaldı).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Claude abunəsi + e-poçt yoxlaması")
    parser.add_argument("--audio", help="lokal Whisper üçün səs faylı (ogg/mp3/wav)")
    args = parser.parse_args()
    asyncio.run(main(args.live, args.audio))
