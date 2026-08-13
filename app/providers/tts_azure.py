"""Azure Speech TTS provider — mətn → səs (az-AZ neural səslər).

Telegram voice note (səsli qeyd) OGG/Opus konteyner tələb edir; Azure-un
`Ogg48Khz16BitMonoOpus` çıxış formatı məhz bunu verir, ona görə əlavə
transcode lazım deyil.

Azure Speech SDK **sinxrondur**, ona görə sinxron sintez `asyncio.to_thread`
ilə thread-ə köçürülür (event loop bloklanmasın). `audio_config=None` verilir ki,
səs host dinamikinə oxunmasın, `result.audio_data` kimi baytlarla qayıtsın.

Səslər (az-AZ): BabekNeural (kişi), BanuNeural (qadın).
"""

from __future__ import annotations

import asyncio

import azure.cognitiveservices.speech as speechsdk

from app.logging_conf import get_logger
from app.providers.base import TTSProvider

log = get_logger("providers")

DEFAULT_VOICE = "az-AZ-BabekNeural"


class AzureTTSProvider(TTSProvider):
    def __init__(self, key: str, region: str, default_voice: str = DEFAULT_VOICE) -> None:
        self.key = key
        self.region = region
        self.default_voice = default_voice or DEFAULT_VOICE

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Mətni OGG/Opus baytlarına çevir (Telegram voice note üçün)."""
        return await asyncio.to_thread(self._synthesize_sync, text, voice or self.default_voice)

    def _synthesize_sync(self, text: str, voice: str) -> bytes:
        speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Ogg48Khz16BitMonoOpus
        )
        # audio_config=None → dinamikə oxumur, baytları geri qaytarır.
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return bytes(result.audio_data)

        if result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            raise RuntimeError(
                f"TTS ləğv edildi: {details.reason} — {details.error_details}"
            )
        raise RuntimeError(f"TTS uğursuz oldu: {result.reason}")
