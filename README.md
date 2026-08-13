# Second Brain — Personal AI Assistant (Telegram)

Şəxsi "ikinci beyin": Telegram üzərindən səsli və mətn qeydlər al, sonra
təbii dildə bu qeydlərlə söhbət et (RAG semantik axtarış).

> **Status:** Phase 5 — Polish (qeyd/söhbət + RAG + link/PDF/DOCX ingest +
> xatırlatmalar/tapşırıqlar/brifinq + **cost tracking `/stats`, `/export`,
> `/delete`, `/settings`**). Canlı işləyir.

## Tex Stack
- Python 3.11+ · python-telegram-bot v21 (async)
- Claude API (beyin) · OpenAI Whisper + embeddings · Azure Speech (az-AZ)
- PostgreSQL 16 + pgvector · SQLAlchemy (async) + Alembic
- Docker + docker-compose

## Sürətli başlanğıc
```bash
cp .env.example .env       # sonra .env-i doldur (ən azı TELEGRAM_BOT_TOKEN)
make up                    # db + bot qalxır (docker compose up -d --build)
make logs                  # botun loglarını izlə
```

Botu Telegram-da tap, `/start` yaz — sənə echo cavabı qaytarmalıdır.

## Struktur
```
app/
  main.py            # giriş nöqtəsi
  config.py          # .env -> settings
  logging_conf.py    # struktur log
  db.py              # async engine/session + pgvector yoxlaması
  models.py          # SQLAlchemy modelləri (users, notes, ...) + Vector(1536)
  bot/               # telegram app + handlers (echo)
  providers/         # LLM/STT/TTS/Embedding abstraksiyası
  repositories/      # DB CRUD (users, notes + vektor axtarış)
  tools/             # agent tool abstraksiyası
migrations/          # Alembic (async) — 0001_initial full schema
scripts/backup.sh    # gecə pg_dump backup (retention 14 gün)
docker/
  init-pgvector.sql  # CREATE EXTENSION vector
  entrypoint.sh      # start-da alembic upgrade head, sonra botu işə salır
docker-compose.yml   # Postgres 16 + pgvector + bot
```

`make up` edəndə migration-lar **avtomatik** tətbiq olunur (entrypoint).

## Proaktiv scheduler (Phase 4)
Bot işləyəndə PTB JobQueue avtomatik qoşulur:
- **Xatırlatmalar** — hər 60 san vaxtı çatanlar Telegram-a çatdırılır.
- **Səhər brifinqi** — hər gün 08:00 (`TIMEZONE`, default Asia/Baku): günün
  açıq tapşırıqları + xatırlatmalar + son qeydlər.

Xatırlatma/tapşırıq təbii dillə yaranır (məs: *«sabah 9-da həkimə zəng etməyi
xatırlat»*). Əmrlər: `/tasks`, `/done <id>`, `/remind`.

## İdarəetmə (Phase 5)
- `/stats` — bugün/bu ay üzrə mesaj sayı, token və **təxmini xərc** (LLM/embed/STT).
- `/export` — bütün qeydlər Markdown fayl kimi yüklənir.
- `/delete <id>` — qeydi sil (təsdiqlə); `/delete all` — hamısını.
- `/settings` — səhər brifinqini aç/söndür və saatını dəyiş (`Asia/Baku`).

## Gecə backup (host cron)
`scripts/backup.sh` `docker exec ... pg_dump` işlədir — **host cron**-a bağla
(bot çöksə də backup davam etsin). VPS-də `crontab -e`:
```cron
# hər gecə 03:15 — Second Brain DB backup
15 3 * * * cd /root/AI-Assistant && ./scripts/backup.sh >> ./backups/backup.log 2>&1
```

## Detallı quraşdırma (API açarları, addım-addım)
👉 **[SETUP.md](SETUP.md)** — Azərbaycanca tam bələdçi.
