# Second Brain Linux noutbukda

Bot 24/7 Linux noutbukda işləyir (JobRadar ilə eyni maşın, bir-birinə toxunmurlar), sən ondan
Telegram-la istifadə edirsən — telefon, MacBook, fərq etmir. AI = Claude abunən; API açarı yoxdur.

## Bir əmr

**MacBook terminalında** (qurur da, yeniləyir də):

```bash
cd ~/Projects/AI-Assistant && bash scripts/linux/deploy-from-mac.sh --vps root@VPS-IP
```

`VPS-IP` yerinə köhnə serverin ünvanını yaz. Köçürüləcək heç nə yoxdursa `--vps ...` hissəsini sil.
Adi SSH açarın VPS-i açmırsa `--vps-key ~/.ssh/AÇAR` əlavə et.

Əmr bütün sualları **başda** verir, sonra işini özü görür (ilk dəfə 15-30 dəqiqə):

| Soruşur | Nə üçün |
|---|---|
| Gmail ünvanı + App Password (boş buraxmaq olar) | E-poçt oxumaq. Parol: myaccount.google.com/apppasswords |
| «Razısan?» | Köhnə serverdəki botu dayandırıb qeydləri köçürmək |
| Linux şifrən (bir dəfə) | Docker quraşdırmaq üçün `sudo` |

Qalanını özü tapır: Telegram tokeni və ID-n bu Mac-ın `.env`-indən, Claude tokeni noutbukdakı
JobRadar-ın `.env`-indən (eyni abunə). Tapmasa soruşur.

Sonra nə edir: kodu göndərir → Docker qurur → image build edir → bu prosessorda işlədiyini yoxlayır →
VPS botunu dayandırır → qeydləri köçürür (bir nüsxə Mac-ın `backups/` qovluğuna) → botu işə salır →
Telegram, baza, Claude və e-poçtu yoxlayır → JobRadar-ın toxunulmaz qaldığını təsdiqləyir.

**Alınmasa:** VPS botu avtomatik geri qayıdır, heç nə itmir. Səbəbi düzəldib eyni əmri təkrar işlət.

**Noutbukun IP-si dəyişibsə** (DHCP): Linux-da `hostname -I` yaz, sonra əmrin sonuna əlavə et: `samir@YENİ-IP`.

## Gündəlik (Mac-da)

| Nə lazımdır | Əmr |
|---|---|
| Kodu yenilə | `bash scripts/linux/deploy-from-mac.sh` |
| E-poçtu sonradan əlavə et | `bash scripts/linux/deploy-from-mac.sh --email` |
| Hər şey qaydasındadır? | `ssh jobradar-linux 'cd ~/SecondBrain && docker compose exec bot python scripts/doctor.py'` |
| Bot nə edir | `ssh jobradar-linux 'cd ~/SecondBrain && docker compose logs -f bot'` |
| Yenidən başlat | `ssh jobradar-linux 'cd ~/SecondBrain && docker compose restart bot'` |
| Əl ilə backup | `ssh jobradar-linux 'cd ~/SecondBrain && bash scripts/backup.sh'` |
| Backup-ları Mac-a götür | `scp 'jobradar-linux:~/SecondBrain/backups/second_brain_*.sql.gz' ~/Downloads/` |

Telegram-da: `/health` (qısa vəziyyət), `/mail`, `/stats`.

## Noutbukda nə dəyişir

- **Paketlər:** `docker.io`, `docker-compose-v2`, `docker-buildx` (Ubuntu/Mint-in öz repo-sundan); Docker
  açılışda özü başlayır; `samir` istifadəçisi `docker` qrupuna düşür.
- **`~/SecondBrain`:** kod, `.env` (yalnız sən oxuya bilərsən), `backups/`.
- **`/etc/cron.d/second-brain`:** gecə 03:15 backup, 14 gün saxlanır.
- **Yuxu rejimi:** JobRadar artıq söndürüb, ona görə toxunulmur (söndürülməyibsə söndürür).

**JobRadar-a toxunmur:** onun fayllarını, xidmətlərini, portlarını dəyişmir (yalnız `.env`-indən Claude tokenini
oxuyur). Second Brain heç bir port açmır. Konteynerin limiti var: RAM 5 GB; CPU-da JobRadar üstündür; yaddaş
böhranında əvvəlcə bu konteyner ölür, JobRadar yox ([docker-compose.host.yml](docker-compose.host.yml)).

Ölçülmüş istifadə: ~2.4 GB RAM, ~4 GB disk (image + modellər). Noutbukda 11 GB RAM və 88 GB disk boşdur.

## Limitlər — vacib

Bir Claude abunəsini **üç şey** paylaşır: sənin Claude Code işin, JobRadar-ın Claude axtarışları və bu bot.
Həftəlik limit dolanda bot dayanmır: «⏳ Claude abunə limiti doldu — … bərpa olunur» yazır və mesajını xam qeyd
kimi saxlayır. `/list`, `/search`, `/tasks`, `/remind`, `/mail`, xatırlatmalar, brifinq AI-siz işləyir.

Qənaət (`~/SecondBrain/.env`, sonra `docker compose up -d bot`): `ESCALATION_ENABLED=false` (həmişə Haiku),
`EMAIL_AI_TRIAGE=false`, `EMAIL_CHECK_INTERVAL_MIN=30`.

Şəxsi abunədir: botu başqalarına xidmət kimi açmaq üçün API açarı lazımdır (`LLM_BACKEND=api`).

## Problemlər

| Simptom | Səbəb / həll |
|---|---|
| «Qoşulmaq olmadı» | Noutbuk sönüb və ya IP dəyişib: yuxarıdakı `samir@YENİ-IP` |
| `telegram_conflict` | Eyni token başqa yerdə işləyir (VPS? Mac-dakı bot?) — onu dayandır |
| «Claude girişi uğursuz» | Token vaxtı keçib: Mac-da `claude setup-token`, tokeni `~/SecondBrain/.env`-də `CLAUDE_CODE_OAUTH_TOKEN=` sətrinə yaz, sonra `docker compose up -d bot` |
| E-poçt: `AUTHENTICATIONFAILED` | App Password səhvdir: `--email` ilə yenidən yaz |
| Loqda `whisper_model_missing`, səs pis başa düşülür | Azərbaycan modeli çevrilməyib: `scripts/convert_az_whisper.py`-nin əvvəlindəki əmri noutbukda işlət (bir dəfə, ~5 dəq), sonra `docker compose up -d bot` |

## Silmək

```bash
ssh jobradar-linux 'cd ~/SecondBrain && docker compose down'
```

Data qalır. Datanı da silmək `docker compose down -v` ilədir — **geri qaytarılmır**, əvvəlcə backup götür.

Başqa Linux maşında (Mac-sız): `curl -fsSL https://raw.githubusercontent.com/nabiyevsamir-002/Second-Brain/main/scripts/linux/install.sh | bash` — hər şeyi soruşur və qurur (kod GitHub-da olmalıdır).
