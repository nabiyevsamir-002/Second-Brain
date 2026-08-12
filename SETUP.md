# SETUP — Sənin edəcəyin işlər (Phase 0)

Salam Samir 👋 Mən Phase 0-ın **bütün kodunu** qurdum və real test etdim:
- ✅ git repo hazır, bütün struktur yaradıldı
- ✅ Docker bot image **build olundu** (exit 0)
- ✅ Postgres 16 + **pgvector 0.8.6** qalxdı və işlədi
- ✅ Kod DB-yə real qoşuldu (`pgvector reachable: True`)
- ✅ Bütün Telegram importları işləyir

**Qalan tək şey — API açarları, ki bunları yalnız sən əldə edə bilərsən.**
Phase 0-ı işə salmaq üçün faktiki olaraq **cəmi 1 açar** lazımdır: Telegram token.
Qalanları sonrakı fazalar üçündür, indi boş qala bilər.

---

## 1️⃣ Telegram Bot Token al (MÜTLƏQ — Phase 0 üçün)

1. Telegram-da [@BotFather](https://t.me/BotFather) aç.
2. `/newbot` yaz.
3. Bota **ad** ver (məs: `Samir Second Brain`).
4. Bota **username** ver — `bot` ilə bitməlidir (məs: `samir_secondbrain_bot`).
5. BotFather sənə belə bir **token** verəcək:
   `123456789:AAH...uzun-string...`
6. Bu tokeni kopyala — birazdan `.env`-ə yazacaqsan.

> İstəsən BotFather-də `/setdescription`, `/setabouttext` ilə botun təsvirini də verə bilərsən (könüllü).

---

## 2️⃣ Öz Telegram User ID-ni öyrən (MÜTLƏQ — allowlist üçün)

İki yol var, birini seç:

**A) Ən asan:** [@userinfobot](https://t.me/userinfobot) aç → `/start` → sənə ID-ni yazacaq (məs: `587123456`).

**B) Bizim bot vasitəsilə:** aşağıda botu ilk dəfə açanda (`.env`-də `ALLOWED_USER_IDS` boş ikən) bota `/id` yaz — sənə ID-ni göstərəcək. Sonra o ID-ni `.env`-ə əlavə edərsən.

---

## 3️⃣ `.env` faylını yarat və doldur

Terminalda layihə qovluğunda:

```bash
cp .env.example .env
```

Sonra `.env`-i redaktə et. **Phase 0 üçün yalnız bu 2 sətir vacibdir:**

```env
TELEGRAM_BOT_TOKEN=123456789:AAH...sənin-tokenin...
ALLOWED_USER_IDS=587123456          # 2-ci addımdakı öz ID-n
```

> Qalan açarları (ANTHROPIC, OPENAI, AZURE, TAVILY) **indi boş burax** — Phase 1-də dolduracağıq.

---

## 4️⃣ Botu işə sal

```bash
make up      # db + bot qalxır (docker compose up -d --build)
make logs    # logları izlə (Ctrl+C ilə çıx — bot işləməyə davam edir)
```

Loglarda bunları görməlisən:
```
starting_bot        environment=development   allowlist=[587123456]
database_ready      pgvector=True
```

---

## 5️⃣ Test et ✅

1. Telegram-da öz botunu tap (BotFather-in verdiyi username ilə).
2. `/start` yaz → xoş gəldin mesajı.
3. `/help` yaz → əmrlər siyahısı.
4. İstənilən mətn yaz (məs: "salam") → bot `📝 (echo) salam` qaytarmalıdır.
5. `/id` yaz → sənin Telegram ID-ni göstərməli.

**Uğurlu sayılır əgər:** bot cavab verir, echo işləyir, loglarda `pgvector=True` var.

> Başqa birindən (icazəsiz) botun yoxlanması: əgər allowlist doludursa, başqa hesab bota yazanda `⛔️ Bu şəxsi botdur` cavabı almalıdır.

---

## Faydalı komandalar

```bash
make up        # qaldır (build ilə)
make logs      # bot loglarını izlə
make ps        # servislərin vəziyyəti
make restart   # botu yenidən başlat (kod dəyişəndən sonra: make up)
make down      # dayandır
make db-only   # yalnız Postgres
```

---

## Nə vaxt hansı açar lazımdır? (yol xəritəsi)

| Açar | Nə üçün | Hansı fazada |
|------|---------|--------------|
| `TELEGRAM_BOT_TOKEN` | bot | **Phase 0 (indi)** |
| `ALLOWED_USER_IDS` | təhlükəsizlik (yalnız sən) | **Phase 0 (indi)** |
| `ANTHROPIC_API_KEY` | Claude beyin — qeydləri təmizləmə, chat | Phase 1 |
| `OPENAI_API_KEY` | Whisper STT (səs→mətn) + embeddings (RAG) | Phase 1–2 |
| `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | az-AZ STT fallback, sonra TTS səs cavab | Phase 1 / 3 |
| `TAVILY_API_KEY` | web axtarış | Phase 4 |

---

## Problemlər (troubleshooting)

- **`address already in use: 5432`** → Səndə lokal Postgres var. Biz Docker Postgres-i host-da **5433**-ə bağladıq, konflikt olmamalıdır. Yenə olarsa, `docker-compose.yml`-də portu dəyiş.
- **Bot cavab vermir** → `make logs` yoxla. `missing_telegram_bot_token` görsən, `.env`-də token boşdur.
- **`allowlist_empty_open_mode` warning** → `ALLOWED_USER_IDS` boşdur; bot hamıya açıqdır. Öz ID-ni əlavə et və `make up` təkrar et.
- **`database_ready_no_pgvector`** → nadir hal; `docker compose down -v` (volume-u silir!) sonra `make up` — pgvector yenidən qurulur.

---

## Növbəti addım

Sən oyanıb Phase 0-ı test edəndən sonra mənə **"Phase 0 işlədi"** yaz —
mən **Phase 1 (MVP: səs/mətn qeyd → təmizlə → saxla)** üçün qısa plan verəcəyəm,
sən təsdiq edəcəksən, sonra qurmağa başlayacağıq.
