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

## 🚀 Phase 6 — Optimizasiya + yeni feature-lər (2026-08-14, canlı deploy edildi)

**Optimizasiya (keyfiyyət balansı qorunub):**
- **Prompt caching** — system 2 blokdur: statik (keşlənir, `cache_control`) + dinamik cari vaxt;
  son tool sxemasına `cache_control` → tools+statik system keşlənir (cache read ~0.1×).
  `pricing.llm_cost`/`log_llm_usage` cache write(1.25×)/read(0.1×) tokenlərini sayır (/stats dəqiq).
- **Selective escalation** — `is_complex_query()`: sadə mesaj Haiku, analitik/uzun/çox-suallı → `CLAUDE_MODEL_SMART`
  (default `claude-sonnet-5`). `ESCALATION_ENABLED` env-toggle. Sadə hallar ucuz qalır, çətinlərdə keyfiyyət↑.
  (Thinking kodda aktiv deyildi — azaldılası bir şey yoxdur; escalation keyfiyyət leveridir.)
- **Rate-limit** — `app/bot/ratelimit.py` sliding-window (60s+60dəq) per-user; bahalı handler-lərdə
  (text/voice/document/photo). `RATE_LIMIT_PER_MIN=20`, `RATE_LIMIT_PER_HOUR=240` (səxavətli, 0=limitsiz).

**Yeni feature-lər:**
- **Təkrarlanan xatırlatma + snooze** — `reminders.recur` (migration **0002**; daily/weekly). Scheduler
  çatdırdıqdan sonra növbəti vaxta sürüşdürür. Hər xatırlatmada inline düymələr: 😴10dəq/😴1saat (yeni birdəfəlik
  yaradır) + ✅Bağla (təkrarlananı dayandırır). `/remind`-də 🔁.
- **/list & /search filtri** — `/list iş`, `/list #tag`, `/search <söz> cat:iş #tag` (repo-da category/tag filtri).
- **/edit <id> <mətn>** — qeydi yenidən təmizlə+re-embed (`recapture_note`).
- **Hybrid axtarış** — `hybrid_search_notes` (vektor + açar söz ILIKE, birləşik bal). `/search` + agent `search_notes` tool.
- **Həftəlik digest** — opt-in (`digest_enabled`, default söndürülü), B.e. `briefing_hour`-da; /settings-də toggle.
  Son 7 gün: qeyd sayı, əsas kateqoriyalar, açıq tapşırıq, gələn xatırlatma.
- **Şəkil qeydlər (OCR)** — Telegram foto → Claude **vision** (tək çağırış: OCR+summary+category+tags JSON) →
  qeyd (yeni `source=photo`, migration **0003** enum ADD VALUE, autocommit_block). Yeni native asılılıq YOX.
- **DEPLOYMENT.md** — şirkət təhvili üçün addım-addım (compose+.env, açarlar, allowlist, backup/verify cron, troubleshooting).

**Migrationlar:** `0002_reminder_recur`, `0003_note_source_photo`. Deploy-da entrypoint `alembic upgrade head`
avtomatik tətbiq edir. **Test:** fresh-DB zənciri (0001→0002→0003) + mövcud-DB (0001→head) təmiz keçdi; hər feature
lokal smoke test keçdi; real image tam import olundu.

**⏳ MANUAL (server, Samir):** həftəlik backup-verify cron (aşağı bax). Digest istəyirsənsə `/settings`-də aç.

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

## Qalıqlar / növbəti
- **🌙 Backup-verify skripti** ✅ — `scripts/verify_backup.sh` (yuxarı bax).
- **⏱️ Rate-limit** ✅ — Phase 6-da tamamlandı (`app/bot/ratelimit.py`).
- **🏢 Şirkətə təhvil** ✅ — `DEPLOYMENT.md` yazıldı (addım-addım guide).
- **📊 Həftəlik digest / 🖼 şəkil OCR / 🔁 təkrarlanan xatırlatma / /edit / hybrid axtarış** ✅ — Phase 6.
- **⏳ MANUAL (server, Samir):**
  - Həftəlik backup-verify cron:
    `30 3 * * 0 cd /root/AI-Assistant && ./scripts/verify_backup.sh >> ./backups/verify.log 2>&1`
  - (İstəyə bağlı) həftəlik digest üçün botda `/settings` → «Həftəlik icmalı aç».
- **📡 Monitoring / uptime alert** ✅ — dead man's switch: `heartbeat` job hər 5 dəq DB yoxlayıb
  `HEALTHCHECK_URL`-a ping (DB xətası→`/fail`); boşdursa söndürülü. `/health` əmri (DB/providerlər/uptime).
  `scripts/watchdog.sh` (imzasız alternativ: konteyner düşsə Telegram DM). Detallar: [DEPLOYMENT.md](DEPLOYMENT.md) §7.1.
  **⏳ MANUAL (server, Samir):** healthchecks.io-da pulsuz check yarat → ping URL-i `.env`-ə (`HEALTHCHECK_URL=`) →
  `docker compose up -d bot` (loglarda `heartbeat=on`). VPS düşməsini də tutur. (Ya da host cron: `watchdog.sh`.)

## İş üsulu
Hər fazada: qısa plan → kod (kiçik test edilə bilən addımlar) → açarlarla canlı test
(`docker compose run`) → təmizlə → deploy (`up -d --build bot`) → commit → yaddaşı yenilə.
Yaddaş: `~/.claude/projects/-Users-samirnbiyev-Projects-AI-Assistant/memory/personal-ai-assistant-project.md`.
