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
- **LLM:** Claude = beyin, **Claude abunəsi (Pro/Max) ilə — API açarı YOX** (Samir, 2026-10-31):
  Claude Agent SDK + `CLAUDE_CODE_OAUTH_TOKEN`. API rejimi (`LLM_BACKEND=api`) yalnız ehtiyat/çox-istifadəçi.
- **Embedding + STT:** lokal (CPU, açarsız) — OpenAI yalnız açar verilərsə.
- **Storage:** PostgreSQL 16 + pgvector.
- **Hosting:** evdəki **Linux noutbuk 24/7** (Mint 22.3, i7-3630QM, 16 GB, SSD; ssh `jobradar-linux`) — JobRadar ilə
  eyni maşın, ona TOXUNMA. Bir əmr: `scripts/linux/deploy-from-mac.sh` → [LINUX.md](LINUX.md). Mac = Telegram klienti +
  inkişaf. Köhnə DigitalOcean VPS-dən köçürülür (auto-deploy söndürülüb). Windows yolu ([WINDOWS.md](WINDOWS.md)) istifadə olunmur.
- **Git:** ilk gündən (aktivdir).

## Agent arxitekturası (vacib)
- **TƏK** tool-using Claude agent (function calling + intent routing). Multi-agent
  supervisor YOX (bu miqyas üçün over-engineering).
- Agent gələn mesajın niyyətini anlayır və uyğun TOOL çağırır.
- Dizayn "splittable": ağır iş axını gələcəkdə sub-agent-ə ayrıla bilsin
  (provider/tool abstraksiyası buna imkan verir).
- Agent tool-ları: `save_note`, `search_notes` [RAG], `get_related_notes`,
  `create_reminder`, `create_task`, `summarize_category`, `activity_report`,
  `check_email`/`search_email`/`read_email` [IMAP]; internet: abunədə daxili `WebSearch`
  (API rejimində `web_search` [Tavily]).
- Abunə agenti (`app/agent/sdk_agent.py`): alətlər in-process MCP, Claude Code-un Bash/fayl/WebFetch
  alətləri SÖNDÜRÜLÜB (e-poçt/veb məzmunu etibarsızdır — prompt injection).
- Tool OLMAYANLAR (handler səviyyəsində, çünki fayl/audio agentə çatmır): link → `ingest_url`
  (fetch+xülasə), PDF/DOCX → `ingest_document`, şəkil → `ingest_image` (vision), səsli cavab →
  `/voice` setting (Azure TTS).

## Tex Stack
- Python 3.11+ (konteynerdə 3.12), python-telegram-bot v21 (async)
- Claude (abunə, Agent SDK): `claude-haiku-4-5` (agent beyni); `claude-sonnet-5` çətin suallar (escalation)
- STT: lokal faster-whisper `small` (AZ); OpenAI Whisper yalnız `OPENAI_API_KEY` verilərsə. `av<19` pin!
- TTS: Azure Speech `az-AZ` (BabekNeural/BanuNeural) — istəyə bağlı (açar yoxdursa `/voice` söndürülü)
- Embedding: lokal `paraphrase-multilingual-mpnet-base-v2` (768 → 1536-ya sıfırla tamamlanır, DB sütunu
  dəyişməyib). OpenAI `text-embedding-3-small` yalnız açar verilərsə. Model dəyişəndə avtomatik re-embed.
- Web search: abunədə Claude daxili WebSearch; API rejimində Tavily
- E-poçt: IMAP (yalnız oxuma, Gmail App Password)
- PDF/DOCX: pypdf + python-docx
- Scheduler: PTB JobQueue (reminders çatdırılması + səhər brifinqi) — ✅ Phase 4
- DB: SQLAlchemy (async) + Alembic; struktur log (structlog); config: pydantic-settings

## Data model (Alembic 0001→0005; `app_meta(key, value)` — aktiv embedding modeli)
`users(telegram_id PK, name, settings JSONB, created_at)` ·
`notes(id, user_id FK, raw_text, cleaned_text, summary, category, tags TEXT[],
source ENUM[voice,text,forward,pdf,docx,photo], embedding vector(1536), pinned, created_at)` ·
`messages(id, user_id FK, role, content, created_at)` ·
`tasks(id, user_id FK, title, due_at, status, recur, completed_at, source_note_id FK, created_at)` ·
`reminders(id, user_id FK, text, remind_at, sent BOOL, recur, created_at)` ·
`note_links(note_id FK, related_note_id FK, score)` ·
`usage_log(id, user_id FK, kind, tokens, cost, created_at)`

## Əmrlər
`/start` `/help` `/list` `/pinned` `/search` `/related` `/id` `/tasks` `/done` `/remind`
`/stats` `/health` `/export` `/delete` `/edit` `/settings` `/voice` (Azure `az-AZ`, istəyə bağlı) `/mail`
`/list iş`·`/list #tag`·`/search <söz> cat:iş #tag` (filtr) · `/list`-də ☆/🗑 düymələr · `/voice mirror`

## Təhlükəsizlik
- Allowlist — yalnız Samir-in telegram_id (`ALLOWED_USER_IDS`).
- Secret-lər `.env`-də (git izləmir). `.env.example`-a REAL açar YAZMA (git-də izlənir).
- Postgres host portu 127.0.0.1:5433 (lokal Postgres 5432-də olduğu üçün).
- Bütün API çağırışlarında retry + error handling; cost tracking (`usage_log`) + soft aylıq
  büdcə (`MONTHLY_BUDGET_USD`).
- BACKUP: gecə `pg_dump` (`scripts/backup.sh`) — **host cron** (`/etc/cron.d/second-brain`, bot daxilində deyil).
- Telegram-a Markdown ilə gedən istifadəçi/LLM mətni `app/bot/md.py` (`md`/`md_in`) ilə escape olunur.

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
- **Phase 6.2** ✅ (voice mirror, /list pin+sil düymələri, /pinned, təkrarlanan tapşırıq, kateqoriya
  xülasəsi, fəaliyyət hesabatı, cavab dili, ağıllı sual) — migration 0004
- **Phase 7 — Spec boşluqları** ✅ (`get_related_notes` tool + `/related`, soft aylıq büdcə,
  Markdown escape, callback allowlist, `/` menyu avto-sinxron) — migration yoxdur
- **Phase 8 — Abunə + PC + e-poçt** ✅ lokal (Claude abunəsi/Agent SDK, lokal embedding+Whisper, IMAP
  e-poçt + bildiriş, Windows skriptləri, VPS auto-deploy söndürüldü) — migration 0005 (`app_meta`)
- **Phase 8.1 — Linux bir əmrlə** ✅ lokal e2e (`scripts/linux/deploy-from-mac.sh`, `install.sh`, `docker-compose.host.yml`,
  `scripts/doctor.py`, canlı Claude 12/12) — 🟢 real noutbukda CANLI (2026-11-02); e-poçt hələ qoşulmayıb

## Metodologiya
1. Hər fazadan əvvəl qısa plan təsdiqi.
2. Kiçik, işlək, test edilə bilən addımlar.
3. Təmiz fayl strukturu + qısa izahlar.
4. Manual addımları aydın göstər (BotFather, VPS, API açarları).
5. Hər fazanın sonunda "necə test etməli" təlimatı.
