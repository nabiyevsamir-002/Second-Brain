# Second Brain — Personal AI Assistant (Telegram)

[![Tests](https://github.com/nabiyevsamir-002/Second-Brain/actions/workflows/tests.yml/badge.svg)](https://github.com/nabiyevsamir-002/Second-Brain/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview (English)

A personal "second brain" on Telegram, built Azerbaijani-first. You send it voice or text notes, links, PDFs and DOCX files. It stores them in PostgreSQL with vector embeddings, and you can then ask questions about your own notes in natural language (RAG semantic search). The bot is live and in daily use.

- **Capture:** voice messages are transcribed, and documents and links are extracted, so everything becomes searchable text.
- **Ask:** a Claude-powered agent searches your notes and answers from them.
- **Act:** you can create reminders and tasks in plain language (for example, "remind me to call the doctor tomorrow at 9"). It also sends a daily morning briefing with open tasks, reminders and recent notes.
- **Manage:** `/stats` shows message, token and estimated cost usage. `/export` downloads all notes as Markdown. `/delete` removes notes, and `/settings` controls the briefing.
- **Operations:** runs with Docker Compose. Migrations apply automatically on start, PostgreSQL is backed up every night, and GitHub Actions deploys to a VPS on every push.

**Stack:** Python 3.11 · python-telegram-bot (async) · Claude API · OpenAI Whisper and embeddings · Azure Speech (az-AZ) · PostgreSQL 16 + pgvector · SQLAlchemy (async) + Alembic · Docker

**Quick start:** `cp .env.example .env` (set at least `TELEGRAM_BOT_TOKEN`), then `make up`.

**Tests:** `pip install -e ".[dev]" && pytest`. They cover pure logic only, so no database, Telegram or API keys are needed.

*The rest of this README is in Azerbaijani.*

---

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
