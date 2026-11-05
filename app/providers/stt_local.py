"""Lokal STT — faster-whisper (CTranslate2, CPU int8), API açarı YOX.

Telegram səsi (OGG/Opus) birbaşa oxunur (PyAV daxili FFmpeg). Model WHISPER_MODEL: ad və ya
çevrilmiş qovluq. Noutbukda (i7-3630QM) real AZ nitqi ilə ölçülüb, söz səhvi · ~6 san səsə vaxt ·
RAM pik: AZ small (scripts/convert_az_whisper.py) 16% · 7 san · 0.7 GB | large-v3 17% · 39 san ·
5 GB | large-v3-turbo 27% · 31 san · 2.3 GB | medium 34% · 20 san · 2.7 GB | small 58% · 6 san ·
0.8 GB. Transkripti sonra Claude kontekstdən düzəldir (VOICE_NOTE).
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

from app.logging_conf import get_logger
from app.providers.base import STTProvider

log = get_logger("stt_local")

FALLBACK_MODEL = "small"


class LocalWhisperSTTProvider(STTProvider):
    local = True

    def __init__(self, model_size: str, cache_dir: str | None = None,
                 compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.cache_dir = cache_dir
        self.compute_type = compute_type
        self._model: Any = None
        self._lock = threading.Lock()

    def _source(self) -> str:
        """Çevrilmiş model qovluğu yoxdursa (təzə quraşdırma) adi modelə keç, bot sınmasın."""
        if os.path.isabs(self.model_size) and not os.path.isdir(self.model_size):
            log.warning("whisper_model_missing", path=self.model_size, fallback=FALLBACK_MODEL,
                        hint="scripts/convert_az_whisper.py")
            return FALLBACK_MODEL
        return self.model_size

    def warmup(self) -> None:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._source(), device="cpu", compute_type=self.compute_type,
                    download_root=self.cache_dir,
                )

    def _transcribe_sync(self, audio_path: str, language: str | None) -> str:
        self.warmup()
        segments, _info = self._model.transcribe(
            audio_path, language=language, beam_size=5, vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments).strip()

    async def transcribe(self, audio_path: str, language: str | None = None) -> str:
        return await asyncio.to_thread(self._transcribe_sync, audio_path, language)
