# Second Brain — Personal AI Assistant (Telegram)

Şəxsi "ikinci beyin": Telegram üzərindən səsli və mətn qeydlər al, sonra
təbii dildə bu qeydlərlə söhbət et (RAG semantik axtarış).

> **Status:** Phase 0 — Foundation (git repo, Docker + Postgres/pgvector,
> config, provider/tool skeleti, işlək **echo bot**).

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
Backup: `./scripts/backup.sh` (cron/scheduler ilə gecə çağırılacaq).

## Detallı quraşdırma (API açarları, addım-addım)
👉 **[SETUP.md](SETUP.md)** — Azərbaycanca tam bələdçi.
