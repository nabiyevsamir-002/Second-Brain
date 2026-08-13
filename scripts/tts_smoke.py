"""Azure TTS canlı smoke test (Phase 3 — səsli cavab).

İşə salma (açar `.env`-də olduqdan sonra, migration lazım deyil):
    docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 bot python scripts/tts_smoke.py

Yoxlayır:
  1) TTS provider açarla qeydiyyatdan keçir.
  2) az-AZ mətn sintez olunur → OGG/Opus baytları qayıdır (magic "OggS").
  3) Hər iki səs (Babek/Banu) işləyir.
Çıxışı /app/backups/... altında OGG kimi saxlayır ki, əl ilə də dinləyə biləsən.
"""

from __future__ import annotations

import asyncio
import os

from app.config import settings
from app.providers.factory import init_providers
from app.providers.registry import providers

OUT_DIR = "/app/backups"
SENTENCE = "Salam Samir. Bu, Azərbaycan dilində Azure səsli cavab testidir."


async def main() -> int:
    init_providers()
    if not providers.has("tts"):
        print("❌ TTS provider qeydiyyatda yoxdur — AZURE_SPEECH_KEY/REGION .env-də boşdur?")
        return 1

    print(f"✅ TTS provider hazırdır (region={settings.azure_speech_region!r}).")
    tts = providers.get("tts")
    os.makedirs(OUT_DIR, exist_ok=True)

    ok = True
    for label, voice in (("babek", "az-AZ-BabekNeural"), ("banu", "az-AZ-BanuNeural")):
        try:
            audio = await tts.synthesize(SENTENCE, voice=voice)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {voice}: sintez xətası: {exc}")
            ok = False
            continue

        is_ogg = audio[:4] == b"OggS"
        path = os.path.join(OUT_DIR, f"tts_test_{label}.ogg")
        with open(path, "wb") as f:
            f.write(audio)
        flag = "✅" if (audio and is_ogg) else "❌"
        print(f"{flag} {voice}: {len(audio)} bayt · OGG={is_ogg} · saxlanıldı: {path}")
        ok = ok and bool(audio) and is_ogg

    print("\n🎯 Nəticə:", "KEÇDİ" if ok else "PROBLEM VAR")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
