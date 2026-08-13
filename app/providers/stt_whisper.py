"""Whisper STT provider (OpenAI) — səs → mətn.

Azərbaycan dili üçün language="az". Telegram voice .oga (ogg/opus) formatındadır;
Whisper bu formatı qəbul edir (fayl adının uzantısı ilə tanıyır).
Azure az-AZ fallback Phase 1-in sonrakı addımında əlavə oluna bilər.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.providers.base import STTProvider

MODEL = "whisper-1"


class WhisperSTTProvider(STTProvider):
    def __init__(self, api_key: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio_path: str, language: str | None = None) -> str:
        with open(audio_path, "rb") as audio_file:
            resp = await self.client.audio.transcriptions.create(
                model=MODEL,
                file=audio_file,
                language=language,
            )
        return resp.text.strip()
