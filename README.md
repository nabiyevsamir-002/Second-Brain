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
  db.py              # async DB + pgvector yoxlaması
  bot/               # telegram app + handlers (echo)
  providers/         # LLM/STT/TTS/Embedding abstraksiyası
  tools/             # agent tool abstraksiyası
docker/
  init-pgvector.sql  # CREATE EXTENSION vector
docker-compose.yml   # Postgres 16 + pgvector + bot
```

## Detallı quraşdırma (API açarları, addım-addım)
👉 **[SETUP.md](SETUP.md)** — Azərbaycanca tam bələdçi.
