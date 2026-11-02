# Windows PC-də 24/7 quraşdırma — Claude abunəsi ilə (API açarsız)

> **İstifadə olunmur:** bot Linux noutbukda işləyir → [LINUX.md](LINUX.md). Bu sənəd yalnız 8 GB+ RAM-lı Windows PC lazım olsa.

Bot evdəki Windows PC-də Docker-də işləyir, sən onu Telegram-dan (telefon, MacBook, PC) istifadə
edirsən. **AI = Claude abunən (Pro/Max)** — API açarı yoxdur. Axtarış (embedding) və səs tanıma
(Whisper) PC-nin öz CPU-sunda işləyir. E-poçt (Gmail) yalnız **oxunur**.

| Nə | Necə | Pul |
|---|---|---|
| Beyin (agent, qeyd təmizləmə, şəkil OCR, e-poçt triajı) | Claude Code CLI + abunə tokeni | abunəyə daxildir |
| İnternet axtarışı | Claude-un daxili WebSearch | abunəyə daxildir |
| Axtarış embedding | lokal `paraphrase-multilingual-mpnet-base-v2` | pulsuz |
| Səs → mətn | lokal faster-whisper (`small`) | pulsuz |
| Səsli cavab (`/voice`) | Azure — istəyə bağlı, açar yoxdursa söndürülü | — |

---

## 1. Tələblər
- Windows 10 (22H2) və ya 11, **64-bit**; virtualizasiya aktiv
  (Task Manager → Performance → CPU → *Virtualization: Enabled*; deyilsə BIOS-da VT-x/AMD-V aç).
- RAM: 8 GB tövsiyə (minimum 6 GB). Disk: ~15 GB boş yer.
- Claude **Pro və ya Max** abunəsi.

## 2. Bir dəfəlik proqramlar (PC)
1. **WSL2** — PowerShell-i *Administrator* kimi aç: `wsl --install` → PC-ni yenidən başlat.
2. **Docker Desktop** — https://www.docker.com/products/docker-desktop/ → quraşdır →
   Settings → General: ✅ *Use the WSL 2 based engine*, ✅ *Start Docker Desktop when you sign in*.
3. **Git for Windows** — https://git-scm.com/download/win (default seçimlər).

## 3. Kodu PC-yə gətir
PowerShell (adi):
```powershell
git clone https://github.com/nabiyevsamir-002/Second-Brain.git C:\SecondBrain
cd C:\SecondBrain
```
> Yeni kod (abunə rejimi) əvvəlcə Mac-dən GitHub-a **push** olunmalıdır — push etmədən PC köhnə kodu alar.

## 4. Açarlar → `.env`
İlk dəfə `scripts\windows\setup.ps1` (bölmə 5) `.env` faylını yaradıb Notepad-da açır. Doldur:

| Sahə | Haradan |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Mövcud botun tokeni (Mac `.env`-dən) və ya @BotFather → yeni bot |
| `ALLOWED_USER_IDS` | Sənin Telegram ID-n (botda `/id`) |
| `CLAUDE_CODE_OAUTH_TOKEN` | Aşağıda 4.1 |
| `EMAIL_ADDRESS` / `EMAIL_PASSWORD` | Gmail ünvanın + App Password (4.2) |

### 4.1 Claude abunə tokeni (1 il etibarlı)
- **Variant A — MacBook-da (tövsiyə):** Terminal → `claude setup-token` → brauzer açılır → Claude
  hesabına daxil ol → terminalda `sk-ant-oat01-…` ilə başlayan token çıxır → kopyala.
- **Variant B — PC-də:** `docker compose run --rm -it -e RUN_MIGRATIONS=0 bot claude setup-token`
  → göstərilən linki brauzerdə aç → daxil ol → çıxan kodu kopyala → terminala yapışdır → token çıxır.

Token yalnız `user:inference` icazəsi verir (hesabını idarə edə bilməz). **Heç kimə göndərmə.**

### 4.2 Gmail App Password
1. https://myaccount.google.com/security → **2-Step Verification**-ı aç.
2. https://myaccount.google.com/apppasswords → ad: `Second Brain` → **Create** → 16 simvollu parol.
3. `EMAIL_PASSWORD=` sahəsinə yaz (boşluqsuz). Adi Google parolu IMAP-da **işləmir**.

> Gmail deyilsə: `EMAIL_IMAP_HOST` dəyiş (Yandex `imap.yandex.com`, Mail.ru `imap.mail.ru`).
> Outlook/Hotmail IMAP-ı artıq parolla qəbul etmir — Gmail tövsiyə olunur.

## 5. İşə sal
```powershell
cd C:\SecondBrain
powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1 -NoSleep
```
- İlk dəfə `.env` yaradır → doldur, saxla → **eyni əmri yenidən işə sal**.
- İlk build 5–10 dəq; ilk start AI modellərini endirir (~1.5 GB, bir dəfə).
- `-NoSleep` — PC elektrikdə olanda yuxuya getməsin (24/7 üçün).

**Yoxla:**
```powershell
docker compose logs -f bot
```
`providers_initialized ... llm=subscription embed=local stt=local email=True agent=True` və
`Application started` görünməlidir. Telegram-da `/health`:
`AI: Claude abunəsi (Claude Code) · embed: local:… · STT: lokal Whisper (small) · e-poçt: qoşulub`.

**Tam yoxlama** (Claude + e-poçt, DB-yə heç nə yazmır):
```powershell
docker compose run --rm bot python scripts/phase8_smoke.py --live
```

## 6. 24/7 etibarlılıq
- Docker Desktop *Start when you sign in* ✅ + Windows avtomatik giriş (`netplwiz` → "Users must
  enter a user name…" işarəsini götür). Konteynerlər `restart: unless-stopped` ilə özləri qalxır.
- Elektrik kəsilsə PC özü açılsın: BIOS → *Restore on AC Power Loss* → **Power On**.
- Windows Update gecə restart etməsin: Settings → Windows Update → *Active hours*.
- **Gecə backup** (03:15, 14 gün saxlanır):
  `powershell -ExecutionPolicy Bypass -File scripts\windows\install-tasks.ps1`
- Monitoring (istəyə bağlı): healthchecks.io ping URL-i → `.env`-də `HEALTHCHECK_URL=`.
- Yeniləmə (Mac-dən push etdikdən sonra): `powershell -ExecutionPolicy Bypass -File scripts\windows\update.ps1`

## 7. VPS-dən köçmə (köhnə qeydlərin)
⚠️ **Eyni Telegram tokeni ilə iki bot eyni anda işləyə bilməz** (`Conflict: terminated by other getUpdates`).
1. VPS-də backup al və PC-yə/Mac-ə köçür:
   ```powershell
   ssh root@<VPS-IP> "cd /root/AI-Assistant && ./scripts/backup.sh"
   scp root@<VPS-IP>:/root/AI-Assistant/backups/second_brain_<SON>.sql.gz C:\SecondBrain\backups\
   ```
2. VPS botunu dayandır: `ssh root@<VPS-IP> "cd /root/AI-Assistant && docker compose stop bot"`
3. PC-də bərpa (bot hələ işə salınmayıbsa; işə salınıbsa sona `-Force` əlavə et):
   `powershell -ExecutionPolicy Bypass -File scripts\windows\restore.ps1 -Dump C:\SecondBrain\backups\second_brain_<SON>.sql.gz`
   Bot köhnə (OpenAI) vektorları görür və bütün qeydləri lokal modellə **avtomatik** yenidən embed edir.
4. Hər şey PC-də işləyəndən sonra DigitalOcean droplet-i söndür/sil (aylıq ödəniş dayansın).
   GitHub-dakı VPS auto-deploy artıq **söndürülüb** (yalnız əl ilə işə düşür).

## 8. Hibrid — MacBook
- **İstifadə:** Telegram Mac/telefonda — eyni bot, eyni data (data PC-dədir).
- **İnkişaf:** Mac-də kod → commit + push → PC-də `update.ps1`.
- Mac-də botu eyni tokenlə **işə salma**. Test üçün @BotFather-dən ayrıca test botu + ayrıca `.env`.
  Mac-də Docker-siz test: `LLM_BACKEND=subscription`, token boş → Mac-dəki `claude` girişi işlənir.

## 9. Abunə limitləri — VACİB
- Bot və sənin öz Claude / Claude Code istifadən **eyni limiti paylaşır** (5 saatlıq + həftəlik).
- Limit dolanda bot dayanmır: «⏳ Claude abunə limiti doldu — … bərpa olunur» yazır və mesajı xam
  qeyd kimi saxlayır. `/list`, `/search`, `/tasks`, `/remind`, `/mail`, xatırlatmalar və brifinq
  AI-siz işləməyə davam edir.
- Qənaət: `ESCALATION_ENABLED=false` (həmişə Haiku), `EMAIL_AI_TRIAGE=false`,
  `EMAIL_CHECK_INTERVAL_MIN=30`.
- Bu sənin **şəxsi** abunəndir. Botu başqalarına (şirkət, çox istifadəçi) xidmət kimi açmaq üçün
  Anthropic şərtlərinə görə API açarı lazımdır: `LLM_BACKEND=api` + `ANTHROPIC_API_KEY`.

## 10. Problemlər
| Simptom | Səbəb / həll |
|---|---|
| `Conflict: terminated by other getUpdates` | Başqa yerdə (VPS/Mac) eyni token ilə bot işləyir — dayandır |
| «Claude girişi uğursuz — CLAUDE_CODE_OAUTH_TOKEN-i yoxla» | Token səhv/vaxtı keçib → 4.1 yenidən, `.env` → `docker compose up -d bot` |
| `/bin/sh^M: bad interpreter` | CRLF sətir sonu — `setup.ps1` avtomatik düzəldir |
| E-poçt: `AUTHENTICATIONFAILED` | App Password səhvdir və ya 2-Step Verification söndürülüb |
| Səs tanıma yavaşdır | `.env`: `WHISPER_MODEL=base`; daha dəqiq üçün `medium` (güclü PC) |
| Model endirilmir (ilk start) | İnternet/disk yeri; `docker compose logs bot` → `model_warmup_failed` |
