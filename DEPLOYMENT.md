# DEPLOYMENT — Second Brain botunu öz serverinizdə qaldırmaq

Bu sənəd layihəni **sıfırdan** öz serverinizə (VPS / şirkət serveri) yerləşdirmək
üçün addım-addım təlimatdır. Kod dəyişikliyi TƏLƏB OLUNMUR — eyni `docker compose`
+ `.env` kifayətdir.

Spesifikasiya: [CLAUDE.md](CLAUDE.md) · Cari canlı status: [HANDOFF.md](HANDOFF.md).

---

## 1. Arxitektura (qısa)

```
Telegram  ──►  bot (python-telegram-bot, async)  ──►  Claude agent (tool-use)
                    │                                      │
                    │                                      ├─ save_note / search_notes (RAG)
                    ▼                                      ├─ create_reminder / create_task
              PostgreSQL 16 + pgvector                     └─ web_search (Tavily)
              (notes + embeddings 1536)
```
- **Tək konteyner** bot + **tək** Postgres konteyner (`docker compose`).
- Bütün API-lər xarici (Claude, OpenAI, Azure, Tavily) — lokal model YOX.
- Schema konteyner start-da avtomatik migrate olunur (Alembic).

---

## 2. Tələblər

| | Minimum | Tövsiyə |
|---|---|---|
| Server | 2 vCPU / 2GB RAM | 4 vCPU / 8GB (istehsalat) |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |
| Disk | 20 GB | 40 GB+ |
| Soft | Docker + Docker Compose plugin | — |

Docker quraşdırma (Ubuntu):
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # yenidən login lazım ola bilər
```

---

## 3. Lazım olan API açarları

| Açar | Haradan | Nə üçün | Məcburi? |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram [@BotFather](https://t.me/BotFather) → `/newbot` | Bot | ✅ Bəli |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Agent beyni (Claude) | ✅ Bəli |
| `OPENAI_API_KEY` | platform.openai.com | Whisper STT + embeddings | ✅ Bəli (RAG üçün) |
| `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | Azure Portal → Speech | səsli cavab (TTS) | ⬜ İstəyə bağlı |
| `TAVILY_API_KEY` | tavily.com | internet axtarışı | ⬜ İstəyə bağlı |

> Açar verilməyən funksiya sadəcə **deaktiv** olur — bot yenə qalxır (məs. Azure yoxdursa
> səsli cavab işləmir, qalan hər şey işləyir).

---

## 4. Quraşdırma (addım-addım)

```bash
# 1) Kodu gətir
git clone <repo-url> AI-Assistant
cd AI-Assistant

# 2) .env yarat
cp .env.example .env
nano .env            # açarları doldur (aşağı bax)

# 3) Qaldır (schema avtomatik migrate olunur)
docker compose up -d --build

# 4) Logları izlə
docker compose logs -f bot
```

`.env`-də ən azı bunları doldur:
```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC...
ALLOWED_USER_IDS=            # boş = "open mode"; bota /id yaz → ID-ni al → bura yaz
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Uğur əlaməti** (loglarda):
```
providers_initialized agent=True embed=True llm=True ...
database_ready pgvector=True
scheduler_ready
Application started
```

### Allowlist (təhlükəsizlik)
1. İlk açılışda `ALLOWED_USER_IDS` boş → bota istənilən kəs yaza bilər ("open mode").
2. Bota `/id` yaz → sənə Telegram ID-ni göstərir.
3. Həmin ID-ni `.env`-də `ALLOWED_USER_IDS=<id>` et (bir neçəsi vergüllə).
4. `docker compose up -d bot` → yalnız icazəli istifadəçilər giriş edir.

---

## 5. İstismar (operations)

### Loglar / restart
```bash
docker compose logs -f bot
docker compose restart bot
docker compose up -d --build bot      # kod yeniləndikdən sonra
```

### Gecə backup (cron)
`scripts/backup.sh` → `pg_dump` (gzip, 14 gün saxlama). Host cron-a əlavə et:
```cron
15 3 * * * cd /root/AI-Assistant && ./scripts/backup.sh >> ./backups/backup.log 2>&1
```

### Backup-verify (backup bərpa olunurmu?)
`scripts/verify_backup.sh` ən son backup-ı AYRI müvəqqəti konteynerdə bərpa edib
strukturu yoxlayır (canlı DB-yə toxunmadan). Həftəlik cron:
```cron
30 3 * * 0 cd /root/AI-Assistant && ./scripts/verify_backup.sh >> ./backups/verify.log 2>&1
```

### Bərpa (restore)
```bash
gunzip -c backups/second_brain_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i second_brain_db psql -U postgres -d second_brain
```

---

## 6. Yeniləmə / CI-CD (istəyə bağlı)

- **Sadə:** serverdə `git pull && docker compose up -d --build bot`.
- **Avtomatik:** [.github/workflows/deploy.yml](.github/workflows/deploy.yml) — `main`-ə
  push → SSH ilə serverə `git pull` + rebuild. GitHub secrets: `SSH_HOST`, `SSH_USER`,
  `SSH_KEY`. **App açarları GitHub-a getmir — yalnız server `.env`-də.**

> ⚠️ **TƏK INSTANS QAYDASI:** bir Telegram token = yalnız bir işləyən bot. Eyni token ilə
> iki yerdə (məs. lokal + server) eyni anda işlətmə → `Conflict: terminated by other
> getUpdates`. Test üçün ayrı bot token istifadə et.

---

## 7. Xərc modeli (cost)

- Agent HƏR mesajda işləyir → əsas xərc **Claude**-dur. Default **Haiku 4.5** (ucuz).
- **Prompt caching** açıqdır: sabit system+tools prefiksi keşlənir (cache read ~0.1×).
- **Escalation**: yalnız çətin/analitik suallar `CLAUDE_MODEL_SMART` (Sonnet) işlədir;
  sadə mesajlar Haiku qalır. `ESCALATION_ENABLED=false` → həmişə Haiku (ən ucuz).
- **Rate-limit**: `RATE_LIMIT_PER_MIN/HOUR` runaway xərci məhdudlaşdırır.
- İstifadəçi `/stats` ilə token/xərci görür (təxmini; qiymətlər `app/pricing.py`).

---

## 8. Çox-istifadəçi (multi-user) qeydi

Data onsuz da `user_id` üzrə izolyasiyalıdır (hər qeyd/tapşırıq/xatırlatma istifadəçiyə
bağlı). Çox istifadəçi üçün:
- `ALLOWED_USER_IDS`-ə bütün icazəli ID-ləri əlavə et.
- Rate-limit per-user işləyir (hər kəs ayrı limitə malikdir).
- Miqyas böyüyəndə: Postgres-ə resurs, embedding/agent çağırışlarına monitoring.

---

## 9. Troubleshooting

| Simptom | Səbəb / həll |
|---|---|
| `Conflict: terminated by other getUpdates` | Eyni token iki yerdə işləyir → birini dayandır |
| `providers_initialized agent=False` | `ANTHROPIC_API_KEY` və/və ya `OPENAI_API_KEY` yoxdur |
| Bot cavab vermir, log-da `unauthorized` | `ALLOWED_USER_IDS` səni daxil etmir → `/id` yoxla |
| `pgvector=False` | Postgres image `pgvector/pgvector:pg16` olmalıdır (compose-də var) |
| Migration xətası start-da | `docker compose logs bot` → Alembic xətasına bax; DB volume-u yoxla |
| Səsli cavab yoxdur | `AZURE_SPEECH_KEY/REGION` yoxdur (istəyə bağlı funksiya) |

---

## 10. Təhlükəsizlik checklist

- [ ] `.env` git-ə DÜŞMÜR (`.gitignore`-dadır) — real açarları yalnız server `.env`-də saxla.
- [ ] `.env.example`-a REAL açar YAZMA (git izləyir).
- [ ] `ALLOWED_USER_IDS` doldurulub (open mode-da qalma).
- [ ] Postgres host portu yalnız `127.0.0.1`-ə bağlı (compose-də belədir) — public açma.
- [ ] Gecə backup + həftəlik verify cron qurulub.
- [ ] Server SSH açarla (parolsuz) girişə keçirilib.
