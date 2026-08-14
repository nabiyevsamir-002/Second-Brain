# Personal AI Assistant — "Second Brain" (Telegram)

> Bu fayl hər sessiyada avtomatik yüklənir. Hazırkı canlı vəziyyət və növbəti
> addım üçün **[HANDOFF.md](HANDOFF.md)**-a bax.

**Dil:** Samir ilə **Azərbaycanca** danış (texniki terminlər İngiliscə qala bilər).
İşçi qovluq: `/Users/samirnbiyev/Projects/AI-Assistant`.

## Məqsəd
Telegram üzərindən səsli/mətn qeydlər al, sonra təbii dildə həmin qeydlərlə
söhbət et (RAG semantik axtarış) — şəxsi "ikinci beyin".

## Təsdiqlənmiş qərarlar
- **Platforma:** Telegram bot (channel-agnostic — sonra WhatsApp əlavə oluna bilər).
- **LLM:** yalnız API (lokal model YOX). Claude = beyin.
- **Storage:** PostgreSQL 16 + pgvector.
- **Hosting:** DigitalOcean VPS (4 vCPU / 8GB), Docker + docker-compose.
- **Git:** ilk gündən (aktivdir).

## Agent arxitekturası (vacib)
- **TƏK** tool-using Claude agent (function calling + intent routing). Multi-agent
  supervisor YOX (bu miqyas üçün over-engineering).
- Agent gələn mesajın niyyətini anlayır və uyğun TOOL çağırır.
- Dizayn "splittable": ağır iş axını gələcəkdə sub-agent-ə ayrıla bilsin
  (provider/tool abstraksiyası buna imkan verir).
- Tool-lar: `save_note`, `search_notes` [RAG], `get_related_notes`,
  `create_reminder`, `create_task`, `web_search` [Tavily], `fetch_url`,
  `ingest_document` [PDF/DOCX], `speak_reply` [Azure TTS].

## Tex Stack
- Python 3.11+ (konteynerdə 3.12), python-telegram-bot v21 (async)
- Claude API: `claude-haiku-4-5` (agent beyni — xərc balansı, canlı təsdiqlənib); `claude-sonnet-5` yüksək-keyfiyyət seçimi (env ilə)
- STT: OpenAI Whisper (`whisper-1`, language=`az`); Azure `az-AZ` STT (fallback — hələ yox)
- TTS: Azure Speech `az-AZ` (BabekNeural/BanuNeural) — ✅ (OGG/Opus, `/voice`)
- Embedding: OpenAI `text-embedding-3-small` (1536 ölçü) — **LOCKED, dəyişmə**
- Web search: Tavily — ✅ (`web_search` agent tool)
- PDF/DOCX: pypdf + python-docx
- Scheduler: PTB JobQueue (reminders çatdırılması + səhər brifinqi) — ✅ Phase 4
- DB: SQLAlchemy (async) + Alembic; struktur log (structlog); config: pydantic-settings

## Data model (Alembic 0001_initial ilə yaradılıb)
`users(telegram_id PK, name, settings JSONB, created_at)` ·
`notes(id, user_id FK, raw_text, cleaned_text, summary, category, tags TEXT[],
source ENUM[voice,text,forward,pdf,docx], embedding vector(1536), created_at)` ·
`messages(id, user_id FK, role, content, created_at)` ·
`tasks(id, user_id FK, title, due_at, status, source_note_id FK, created_at)` ·
`reminders(id, user_id FK, text, remind_at, sent BOOL, created_at)` ·
`note_links(note_id FK, related_note_id FK, score)` ·
`usage_log(id, user_id FK, kind, tokens, cost, created_at)`

## Əmrlər
`/start` `/help` `/list` `/search` `/id` `/tasks` `/done` `/remind`
`/stats` `/export` `/delete` `/edit` `/settings` `/voice` (hazır — Azure `az-AZ` səsli cavab)
`/list iş`·`/list #tag`·`/search <söz> cat:iş #tag` (filtr) · `/settings`-də həftəlik digest toggle

## Təhlükəsizlik
- Allowlist — yalnız Samir-in telegram_id (`ALLOWED_USER_IDS`).
- Secret-lər `.env`-də (git izləmir). `.env.example`-a REAL açar YAZMA (git-də izlənir).
- Postgres host portu 127.0.0.1:5433 (lokal Postgres 5432-də olduğu üçün).
- Bütün API çağırışlarında retry + error handling; cost tracking (`usage_log`).
- BACKUP: gecə `pg_dump` (`scripts/backup.sh`) — hələ scheduler-ə bağlanmayıb.

## Roadmap
- **Phase 0 — Foundation** ✅ (Docker/Postgres/pgvector, config, skelet, echo bot)
- **Phase 1 — MVP** ✅ (səs/mətn → təmizlə → saxla; `/list`; Whisper AZ)
- **Phase 2 — RAG Brain** ✅ (embedding, `/search`, chat + citations, auto-kateqoriya, əlaqəli qeyd)
- **Phase 3 — Capture+** ✅ (forward→save, PDF/DOCX indeks, Azure `az-AZ` TTS səsli cavab `/voice`)
- **Phase 4 — Proactive** ✅ (reminders+tasks, `/tasks` `/done` `/remind`, səhər brifinqi, PTB JobQueue; backup **host-cron**; Tavily `web_search` ✅)
- **Phase 5 — Polish** ✅ (cost tracking + `/stats`, `/export`, `/delete`, `/settings`)
- **Phase 6 — Optimize + Extend** ✅ (prompt caching, Haiku↔Sonnet escalation, rate-limit; təkrarlanan
  xatırlatma+snooze, /list·/search filtr, /edit, hybrid axtarış, həftəlik digest, şəkil OCR (vision),
  backup-verify, DEPLOYMENT.md) — migrationlar 0002/0003

## Metodologiya
1. Hər fazadan əvvəl qısa plan təsdiqi.
2. Kiçik, işlək, test edilə bilən addımlar.
3. Təmiz fayl strukturu + qısa izahlar.
4. Manual addımları aydın göstər (BotFather, VPS, API açarları).
5. Hər fazanın sonunda "necə test etməli" təlimatı.
