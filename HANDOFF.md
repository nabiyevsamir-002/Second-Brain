# HANDOFF — harada qaldıq (son yeniləmə 2026-08-14)

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
| **Phase 4 (proactive)** | `create_reminder`+`create_task` agent tool-ları, PTB JobQueue scheduler (reminder çatdırılması hər 60s + səhər brifinqi 08:00), `/tasks` `/done` `/remind`, Asia/Baku tz | `07d7e91` |
| **Phase 5 (polish)** | cost tracking (agent+haiku+embed+stt loglanır, `app/pricing.py`), `/stats`, `/export` (Markdown fayl), `/delete <id>`+`/delete all` (inline təsdiq), `/settings` (brifinq aç/söndür + saat, JSONB) | `2a9d5c3` |
| **Phase 3 (voice reply)** | 🔊 Azure `az-AZ` TTS səsli cavab: `AzureTTSProvider` (OGG/Opus, sync SDK→`asyncio.to_thread`), `/voice` əmri (aç/söndür + Babek/Banu seçimi + `test`), per-user setting (`voice_reply`/`voice_name` JSONB), `_run_agent`-ə inteqrasiya (mətn + səsli qeyd), `_clean_for_speech` (sitat/markdown/emoji təmizlə), TTS cost tracking (`tts_cost`, kind=`tts`) | `07d362a` |
| **Web search (Tavily)** | 🌐 `web_search` agent tool + `TavilySearchProvider` (AsyncTavilyClient), factory-də şərti qeydiyyat (`TAVILY_API_KEY`), system prompt-da İNTERNET AXTARIŞ niyyəti (şəxsi=search_notes, internet=web_search), mənbə URL-li cavab, cost tracking (`search_cost`, kind=`search`) | `ea6b802` |

## ☁️ GitHub + Deploy (2026-08-13)
- Repo: **https://github.com/nebiyevsamir002-star/AI-Assistant** — **PRIVATE**.
- Branch **`main`** (tracking qurulub → sadəcə `git push`). HTTPS auth osxkeychain token.
- `.env` push OLUNMUR (gitignore) — açarlar yalnız lokal + server `.env`-dədir.
- **🚀 PRODUCTION: DigitalOcean VPS** — Frankfurt (`fra1`), 4vCPU/8GB, Ubuntu 24.04,
  IP `167.71.48.123`, repo `/root/AI-Assistant`, `docker compose` ilə işləyir.
- **CI/CD: GitHub Actions → SSH** ([.github/workflows/deploy.yml](.github/workflows/deploy.yml)):
  `main`-ə push → `appleboy/ssh-action` server-ə SSH → `git pull --ff-only` +
  `docker compose up -d --build bot` + `docker image prune`. **Canlı test: run #2 Success ✅.**
  App açarları GitHub-a GETMİR (yalnız server `.env`); GitHub secrets = `SSH_HOST`/`SSH_USER`/`SSH_KEY`.
  **Optimallaşma** (commit `b482f16`): Dockerfile-də asılılıqlar `app/`-dan ƏVVƏL quraşdırılır →
  kod-only deploy ~15s (pip layer keşdə); workflow `paths-ignore: ['**.md', ...]` → docs-only push deploy etmir.
  İki açar: server→GitHub **deploy key** (`~/.ssh/id_ed25519`, repo Deploy keys, read-only, `git pull` üçün);
  Actions→server **`gh_actions`** (private → `SSH_KEY` secret, public → server authorized_keys).
- **Gecə backup cron** server-də quruldu: `15 3 * * * cd /root/AI-Assistant && ./scripts/backup.sh ...`.

**⚠️ TƏK INSTANS QAYDASI:** Bir Telegram token = yalnız bir polling instansı. Server canlı olduğu üçün
**Mac-dəki bot DAYANDIRILIB** (`docker compose stop bot`). İkisini eyni token ilə eyni anda işlətmə →
`Conflict: terminated by other getUpdates` xətası. Lokal işləmək üçün Mac-də ayrı test token istifadə et.

## 💰 Model dəyişikliyi (xərc balansı, 2026-08-13)
- **`CLAUDE_MODEL_MAIN=claude-haiku-4-5`** edildi (əvvəl `claude-sonnet-5`) — `.env` dəyişikliyi, kod yox.
- Səbəb: agent beyni HƏR mesajda işləyir (əsas xərc); Haiku ~**3× ucuz** (`$1/$5` vs Sonnet `$3/$15`),
  Azərbaycanca güclü qalır (açıq modellərdən yaxşı). Qeyd təmizləmə onsuz da Haiku-da idi.
- **✅ Samir Haiku keyfiyyətini canlı təsdiqlədi — SAXLANILDI.** Default hər yerdə Haiku edildi
  (`config.py`, `.env.example`, hər iki `.env`). Çətin RAG suallarında gələcəkdə lazım olsa → seçici
  Sonnet eskalasiyası (sadə=Haiku, çətin=Sonnet), ya da `.env`-də bir dəyişikliklə Sonnet-ə qaytar.

**Canlı vəziyyət (server):** `providers_initialized agent=True embed=True llm=True search=True stt=True tts=True`,
`database_ready pgvector=True`, `scheduler_ready`, `Application started`. Bütün AI feature-lər (RAG, reminders,
tasks, brifinq, TTS səsli cavab, Tavily web search) canlı. Whisper AZ dəqiqliyi yaxşı (Azure STT fallback lazım deyil).

## 🔑 Açarlar (`.env`, git izləmir)
- ✅ `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS=6389536587`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- ✅ `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION=germanywestcentral` — əlavə olundu, TTS canlı işləyir (`AZURE_TTS_VOICE` default `az-AZ-BabekNeural`).
- ✅ `TAVILY_API_KEY` — əlavə olundu, web search canlı işləyir.

## 🏗️ Kod strukturu (əsas)
```
app/
  main.py                # entrypoint (init_providers -> build_application -> run_polling)
  config.py, db.py, models.py, logging_conf.py
  bot/telegram_app.py    # handler qeydiyyatı + allowlist
  bot/handlers.py        # əmrlər + inline callback (on_callback: /delete təsdiqi, /settings)
  bot/scheduler.py       # PTB JobQueue — reminder (60s) + brifinq (saatlıq tick, per-user settings)
  agent/agent.py         # BrainAgent — tool-use döngəsi + cari vaxt inject + LLM usage log
  timeutils.py           # Baku local ⇄ tz-aware parse/format (parse_local_iso, fmt_local)
  pricing.py             # model qiymətləri + llm/embed/stt cost (TƏXMİNİ) — /stats mənbəyi
  providers/             # llm_claude, embeddings_openai, stt_whisper, factory, registry, base
  tools/                 # base(+ToolContext), save_note, search_notes, create_reminder, create_task, registry
  services/              # notes_service (capture_note+cost), ingest_service (url/pdf/docx)
  repositories/          # users(+settings), notes(+delete/export), messages(+count), links, usage(+totals), reminders, tasks
migrations/              # Alembic (0001_initial — bütün cədvəllər onsuz da var)
scripts/backup.sh        # pg_dump → HOST CRON-a bağlanır (aşağı bax)
scripts/phase4_smoke.py  # Phase 4 canlı smoke test (docker compose run ilə)
scripts/phase5_smoke.py  # Phase 5 canlı smoke test (pricing/usage/export/delete/settings)
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

## ✅ Phase 4 tamamlandı (reminders + tasks + brifinq). Qalıqlar:
- **Gecə backup → HOST CRON** (bot daxilində deyil, tövsiyə olunan seçim). VPS-də:
  ```cron
  15 3 * * * cd /root/AI-Assistant && ./scripts/backup.sh >> ./backups/backup.log 2>&1
  ```
  (Samir hələ VPS-də bu sətri əlavə etməlidir — manual addım.)
- **Web search (Tavily):** `web_search` tool + provider — `TAVILY_API_KEY` gələndə (deferred).

## ✅ Phase 3 səsli cavab tamamlandı (Azure TTS). Canlı vəziyyət:
- `AzureTTSProvider` — `Ogg48Khz16BitMonoOpus` (Telegram voice note native format),
  SDK sinxrondur → `asyncio.to_thread`, `audio_config=None` (baytla qayıdır).
- Dockerfile-a native libs əlavə olundu: `libasound2`, `libssl3`, `ca-certificates`
  (GStreamer LAZIM DEYİL — o yalnız sıxılmış STT girişi üçündür).
- Trigger dizaynı: `speak_reply` agent tool DEYİL — **per-user setting + `/voice`**
  (tool yalnız string qaytarır, audio handler-ə çatmır; setting proqnozlaşdırıla bilən + xərc-nəzarətli).
  Voice açıqdırsa `_run_agent` mətn + səsli qeyd göndərir (echo/prefiks səsə getmir).
- `/voice` (toggle), `/voice babek|banu` (səs seç+aç), `/voice test` (nümunə), `/voice off`.
- Smoke test: `scripts/tts_smoke.py` KEÇDİ (hər iki səs, OGG magic təsdiq).

## ✅ HAMISI HAZIR: bütün AI feature-lər + private repo + VPS production + CI/CD + Haiku beyni.
Layihə tam funksionaldır və canlıdır (yuxarıdakı "GitHub + Deploy" və "Model dəyişikliyi" bölmələrinə bax).

## Qalıqlar / növbəti (hamısı AŞAĞI prioritet — Samir seçimi, əvvəl qısa plan təsdiqi):
- **🌙 Backup-verify skripti** ✅ — `scripts/verify_backup.sh`: ən son backup-ı AYRI müvəqqəti
  Postgres konteynerində bərpa edir (canlı DB-yə toxunmur), pgvector + 7 cədvəl + `notes` oxunuşu +
  `embedding vector(1536)` yoxlanır, exit 0/1. Lokal 3 ssenari test keçdi (boş DB, data=1, korlanmış fayl).
  **⏳ MANUAL (server):** həftəlik verify cron əlavə et:
  `30 3 * * 0 cd /root/AI-Assistant && ./scripts/verify_backup.sh >> ./backups/verify.log 2>&1`
- **⏱️ Rate-limit** (tək istifadəçi üçün aşağı dəyər — runaway API xərcinə qarşı sadə throttle).
- **🏢 Şirkətə təhvil** — layihə şirkət üçündür, onlar öz serverlərində host edəcək: eyni `docker compose`
  + `.env`. Multi-user miqyasda "hibrid/lokal-model beyni" variantı danışıldı (indi Haiku API optimaldır).
- **(İstəyə bağlı monitoring)** — server sağlamlığı / uptime alert (hələ yoxdur).

## İş üsulu
Hər fazada: qısa plan → kod (kiçik test edilə bilən addımlar) → açarlarla canlı test
(`docker compose run`) → təmizlə → deploy (`up -d --build bot`) → commit → yaddaşı yenilə.
Yaddaş: `~/.claude/projects/-Users-samirnbiyev-Projects-AI-Assistant/memory/personal-ai-assistant-project.md`.
