# HANDOFF — harada qaldıq (2026-08-13)

Layihə spesifikasiyası: **[CLAUDE.md](CLAUDE.md)**. Bu fayl **hazırkı canlı vəziyyəti**
və **növbəti addımı** saxlayır.

## ✅ Tamamlanmış fazalar (hamısı canlı test olunub və deploy edilib)

| Faza | Nə edilib | Commit |
|------|-----------|--------|
| **Phase 0** | Docker + Postgres16/pgvector, config (pydantic-settings), structlog, provider/tool skeleti, echo bot | `fb41f64` |
| **Phase 1 (DB)** | Bütün cədvəllər (SQLAlchemy), Alembic `0001_initial`, HNSW cosine index, repositories, `scripts/backup.sh` | `61dbab3` |
| **Phase 1 (capture)** | Providers (Claude/Whisper/OpenAI-embed), capture workflow (təmizlə→embed→saxla), `/list` | `cdcbd5b` |
| **Phase 2 (RAG)** | Tək tool-using Claude agent (intent routing), `save_note`+`search_notes` tools, RAG chat + `[#id]` citations, `/search`, chat yaddaşı (messages), əlaqəli qeyd kəşfi (note_links) | `d88f0b2` |
| **Phase 3 (capture+)** | Link→fetch+xülasə+saxla, forward→save, PDF/DOCX indeks (chunk→batch embed) | `7202fd3` |

**Canlı vəziyyət:** bot `docker compose` ilə işləyir; loglar:
`providers_initialized agent=True embed=True llm=True stt=True`,
`database_ready pgvector=True`, `Application started`.
Samir Telegram-da mətn+səs+link+sənəd göndərib test edib — hər şey işləyir,
Whisper AZ dəqiqliyi **yaxşıdır** (Azure STT fallback lazım deyil).

## 🔑 Açarlar (`.env`, git izləmir)
- ✅ `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS=6389536587`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- ⛔ `AZURE_SPEECH_KEY` (boş) — səsli cavab üçün
- ⛔ `TAVILY_API_KEY` (boş) — web search üçün

## 🏗️ Kod strukturu (əsas)
```
app/
  main.py                # entrypoint (init_providers -> build_application -> run_polling)
  config.py, db.py, models.py, logging_conf.py
  bot/telegram_app.py    # handler qeydiyyatı + allowlist
  bot/handlers.py        # /start /help /id /list /search, mətn/səs/link/sənəd routing
  agent/agent.py         # BrainAgent — Claude tool-use döngəsi (intent routing)
  providers/             # llm_claude, embeddings_openai, stt_whisper, factory, registry, base
  tools/                 # base(+ToolContext), save_note, search_notes, registry
  services/              # notes_service (capture_note), ingest_service (url/pdf/docx)
  repositories/          # users, notes, messages, links, usage
migrations/              # Alembic (0001_initial)
scripts/backup.sh        # pg_dump (hələ scheduler-ə bağlı deyil)
docker/entrypoint.sh     # start-da alembic upgrade head, sonra botu işə salır
```

## ▶️ İşə salma / test
```bash
docker compose up -d          # db + bot (schema avtomatik migrate olunur)
docker compose logs -f bot    # loglar
./scripts/backup.sh           # əl ilə backup
# Kod dəyişəndən sonra:
docker compose up -d --build bot
# Açarsız test/skript (migration ötür):
docker compose run --rm -e RUN_MIGRATIONS=0 bot python -c "..."
```
> Test datası əlavə edəndən sonra təmizlə:
> `docker exec second_brain_db psql -U postgres -d second_brain -c "TRUNCATE users, notes, messages, tasks, reminders, note_links, usage_log RESTART IDENTITY CASCADE;"`

## ⚠️ Vacib texniki qeydlər
- Postgres host portu **5433** (lokal Postgres 5432-də).
- Agent = **manual** Claude tool-use loop (AsyncAnthropic), sonnet-5, max_tokens=2048,
  adaptive thinking default; `resp.content` (thinking blokları daxil) hər turda geri ötürülür.
- Əlaqəli qeyd həddi: cosine distance ≤ **0.68** (text-embedding-3-small: əlaqəli ~0.63, əlaqəsiz ~0.74).
- Agent cavabları Telegram-a **plain text** göndərilir (`[#id]` Markdown-ı pozmasın).
- `.env.example`-a REAL açar yazma (git izləyir); real açarlar yalnız `.env`-də.
- Model ID-ləri: `claude-sonnet-5`, `claude-haiku-4-5` (Samir seçib — dəyişmə).

## ⏭️ NÖVBƏTİ ADDIM — Phase 4 (Proactive), başlanmayıb
Plan (mövcud açarlarla qurula/test edilə bilər; Tavily istisna):
1. **Yeni agent tool-ları:** `create_task`, `create_reminder` (agentə əlavə et → registry).
2. **Scheduler:** APScheduler (və ya PTB JobQueue) — reminders `remind_at`-də çatdırılır (sent=True).
3. **`/tasks`** əmri (açıq tapşırıqlar), tapşırıq statusu.
4. **Səhər brifinqi:** hər səhər (məs 08:00) → günün tasks + reminders + son qeydlər.
5. **Gecə backup:** `scripts/backup.sh`-ı scheduler-ə bağla.
6. **Web search (Tavily):** `web_search` tool + provider — `TAVILY_API_KEY` gələndə.

**Deferred (açar lazımdır):** Phase 3 səsli cavab (Azure `az-AZ` TTS, `AZURE_SPEECH_KEY`);
Phase 4 web search (Tavily, `TAVILY_API_KEY`).

## İş üsulu
Hər fazada: qısa plan → kod (kiçik test edilə bilən addımlar) → açarlarla canlı test
(`docker compose run`) → təmizlə → deploy (`up -d --build bot`) → commit → yaddaşı yenilə.
Yaddaş: `~/.claude/projects/-Users-samirnbiyev-Projects-AI-Assistant/memory/personal-ai-assistant-project.md`.
