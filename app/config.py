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

    # --- AI backend seçimi (Phase 8 — Claude abunəsi, API açarsız) ---
    # llm_backend: auto | subscription | api
    #   subscription → Claude Code (Agent SDK) + CLAUDE_CODE_OAUTH_TOKEN (Pro/Max abunəsi)
    #   api          → Anthropic API (ANTHROPIC_API_KEY, token başına ödəniş)
    #   auto         → token varsa subscription, yoxsa API açarı varsa api
    llm_backend: str = "auto"
    claude_code_oauth_token: str = ""  # `claude setup-token` çıxışı (1 il etibarlı)
    agent_max_turns: int = 8  # abunə agentinin bir mesajda maksimum addımı
    llm_timeout_sec: int = 180  # Claude Code CLI ilişib qalmasın
    # embed_backend / stt_backend: auto | local | openai — auto: OpenAI açarı varsa openai.
    embed_backend: str = "auto"
    local_embed_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    # Əlaqəli qeyd həddi (cosine məsafə). 0 = embedding provayderinin öz dəyəri.
    related_max_distance: float = 0.0
    stt_backend: str = "auto"
    whisper_model: str = "small"  # faster-whisper: ad və ya çevrilmiş qovluq (.env.example-a bax)
    whisper_compute_type: str = "int8"
    model_cache_dir: str = ""  # lokal model faylları; Docker-də /models (volume), boş = default keş

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

    # --- Soft aylıq büdcə (USD, istifadəçi başına; usage_log əsasında) ---
    # Limitin budget_warn_pct %-ində xəbərdarlıq; keçəndə bot DAYANMIR — yalnız Sonnet
    # eskalasiyası + səsli cavab ayın sonunadək söndürülür. 0 = söndürülü.
    monthly_budget_usd: float = 0.0
    budget_warn_pct: int = 80

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

    # --- E-poçt (Phase 8) — IMAP, YALNIZ oxuma (məktublar "oxunmuş" olmur) ---
    # Gmail: imap.gmail.com + 2 addımlı doğrulama + App Password (adi parol işləmir).
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_imap_ssl: bool = True
    email_address: str = ""
    email_password: str = ""
    # İkinci poçt (istəyə bağlı): eyni host, öz ünvanı və App Password-u.
    email_address_2: str = ""
    email_password_2: str = ""
    email_folder: str = "INBOX"
    email_check_interval_min: int = 10  # yeni məktub bildirişi yoxlaması; 0 = söndürülü
    email_ai_triage: bool = True  # yeni məktubları Claude ilə vacib/adi ayır (abunə istifadəsi)

    @property
    def resolved_llm_backend(self) -> str:
        """subscription | api | none — `auto` açarlara görə həll olunur."""
        b = self.llm_backend.strip().lower()
        if b in ("subscription", "api"):
            return b
        if self.claude_code_oauth_token:
            return "subscription"
        return "api" if self.anthropic_api_key else "none"

    def resolved_backend(self, value: str) -> str:
        """embed/stt üçün: local | openai — `auto`: OpenAI açarı varsa openai."""
        b = value.strip().lower()
        if b in ("local", "openai"):
            return b
        return "openai" if self.openai_api_key else "local"

    @property
    def email_accounts(self) -> list[tuple[str, str]]:
        """Doldurulmuş poçtlar (ünvan, parol); eyni ünvan iki dəfə yazılıbsa bir dəfə sayılır."""
        accounts: dict[str, tuple[str, str]] = {}
        for address, password in (
            (self.email_address, self.email_password),
            (self.email_address_2, self.email_password_2),
        ):
            address = address.strip()
            if address and password:
                accounts.setdefault(address.lower(), (address, password))
        return list(accounts.values())

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_imap_host and self.email_accounts)

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
