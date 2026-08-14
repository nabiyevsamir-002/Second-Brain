"""Tətbiq konfiqurasiyası — .env faylından typed settings (pydantic-settings)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Mühit / log ---
    environment: str = "development"
    log_level: str = "INFO"

    # --- Saat qurşağı (Phase 4 — reminders/tasks/brifinq) ---
    # Azərbaycan DST işlətmir (sabit UTC+4), amma ZoneInfo gələcək üçün təhlükəsizdir.
    timezone: str = "Asia/Baku"

    # --- Telegram (Phase 0) ---
    telegram_bot_token: str = ""
    # Vergüllə ayrılmış ID-lər, məs: "12345678,87654321".
    # list[int] əvəzinə str saxlayırıq ki, pydantic-settings JSON parse etməyə çalışmasın.
    allowed_user_ids: str = ""

    # --- Verilənlər bazası ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/second_brain"

    # --- LLM (Phase 1) ---
    anthropic_api_key: str = ""
    # Agent beyni — HƏR mesajda işləyir (əsas xərc). Xərc balansı üçün default Haiku 4.5
    # (~3× ucuz, AZ güclü). Daha yüksək keyfiyyət lazım olsa .env-də claude-sonnet-5 et.
    claude_model_main: str = "claude-haiku-4-5"
    claude_model_fast: str = "claude-haiku-4-5"
    # Selective escalation (Phase 6): sadə mesaj → Haiku, ÇƏTİN/analitik sual → bu model.
    # Yalnız mürəkkəb suallarda işə düşür (keyfiyyət↑), sadə hallar ucuz Haiku qalır.
    claude_model_smart: str = "claude-sonnet-5"
    escalation_enabled: bool = True

    # --- Rate-limit (Phase 6) — runaway API xərcinə qarşı sadə throttle ---
    # Tək istifadəçi üçün səxavətli limitlər (normal istifadə heç vaxt dəyməz).
    rate_limit_per_min: int = 20
    rate_limit_per_hour: int = 240

    # --- OpenAI: Whisper STT + embeddings (Phase 1-2) ---
    openai_api_key: str = ""

    # --- Azure Speech: az-AZ STT fallback + TTS (Phase 1/3) ---
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    # Səsli cavab üçün default az-AZ neural səs (BabekNeural=kişi, BanuNeural=qadın).
    azure_tts_voice: str = "az-AZ-BabekNeural"

    # --- Tavily web axtarış (Phase 4) ---
    tavily_api_key: str = ""

    # --- Monitoring / uptime (Phase 6.1) ---
    # Dead man's switch: bot müntəzəm bu URL-a "sağam" ping atır (məs. healthchecks.io).
    # Ping kəsilsə (bot/DB/VPS düşüb) xarici monitor SƏNƏ alert göndərir. Boş = söndürülü.
    healthcheck_url: str = ""
    heartbeat_interval_min: int = 5

    @property
    def tz(self) -> ZoneInfo:
        """Konfiqurasiya olunmuş saat qurşağı (reminders/tasks/brifinq üçün)."""
        return ZoneInfo(self.timezone)

    @property
    def allowed_ids(self) -> list[int]:
        """ALLOWED_USER_IDS string-ini int siyahısına çevir."""
        ids: list[int] = []
        for part in self.allowed_user_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                # Yanlış dəyəri sükutla ötür (log startup-da olacaq).
                continue
        return ids


settings = Settings()
