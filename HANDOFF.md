# HANDOFF — harada qaldıq (son yeniləmə 2026-11-05)

## 🚩 HARADA QALDIQ — buradan davam et (2026-11-05 ~11:30 Bakı)

**🟢 Bot canlıdır:** `@Personal_AI_Asisstant_bot`, JobRadar-ın Linux noutbukunda (`ssh jobradar-linux`, `~/SecondBrain`), yalnız Claude
abunəsi ilə. İlk real mesaj 23:23-də ~7 saniyəyə emal olundu. Baza təmiz başlayıb (Samir-in seçimi).

**Samir təsdiqlədi:** bot cavab verir (Telegram-da görüb). **Köhnə qeydlər lazım deyil:** droplet silinir, VPS-dən köçürmə ləğv olunub.

**🟢 E-poçt qoşuldu (23:50):** real Gmail, App Password ilə. Real poçtda yoxlandı: giriş, son və oxunmamış siyahısı, tam oxuma, axtarış
(Azərbaycan hərfləri də), oxumaq məktubu oxunmuş etmir (oxunmamış sayı dəyişmədi), bildiriş baza nöqtəsi yazıldı (köhnə məktublara bildiriş getmir).

**🛠️ Xatırlatma düzəlişi (2026-11-03, canlıdır, commit 5a03a68):** gecə 01:15-də «sabah səhər ... xatırlat» yazılmışdı, bot onu bir gün gec
qurmuşdu. İndi 00:00–05:00 arası «sabah» həmin günün səhəri sayılır. Xatırlatma və deadline-lı tapşırıq cavabının sonuna dəqiq vaxtı kod yazır
(`⏰ Xatırlatma #N: 2026-11-04 09:00 (Çərşənbə)`), çünki model tarixi öz sözləri ilə yazanda həftə gününü səhv salırdı. Noutbukda real Claude ilə,
saatı simulyasiya edib yoxlandı (gecə və gündüz), bazaya yazmadan.

**🌙 Phase 9 — gündəlik rutin (2026-11-03, canlıdır, commit 571ca95):**
- **Axşam yekunu** hər gün 22:00-da (`/settings`-də aç/söndür): bu gün bitən tapşırıqlar, açıq qalanlar (gecikənlərin sayı), sabahkı
  xatırlatmalar, Claude-un tapdığı lazımsız məktublar + «🗑 Bax və sil» düyməsi (Phase 9.1), «Bu gün necə keçdi?» sualı. Bu mesaja Reply (yazı və ya səs) →
  «gündəlik» kateqoriyalı qeyd, agentsiz və Claude-suz (`app/services/journal.py`). Mesajı kod yığır; Claude yalnız poçt baxışı üçün bir dəfə çağırılır, alınmasa həmin hissə çıxmır.
- **Poçt təmizliyi** `/mail təmizlə` və ya düymə: Gmail-in öz «Reklamlar» bölməsi (`category:promotions -is:starred`), son 10-u göstərilir,
  «📦 Hamısını arxivlə» → «↩️ Geri qaytar». Arxiv = Inbox etiketini götürmək, heç nə silinmir. **Vacib:** Gmail Inbox etiketini Inbox-un
  özündən götürəndə STORE-a OK qaytarır, amma heç nə dəyişmir (real poçtda görüldü) — ona görə yazma «All Mail» qovluğunda gedir
  (`\All` bayrağı ilə tapılır). «Yeniliklər» (Updates) bölməsinə toxunulmur: bank, qəbz, iş cavabları ola bilər.
- **Yoxlandı:** 129 pytest; real Gmail-də 1 reklam məktubu arxivləndi (Inbox-da reklam 44 → 43) və geri qaytarıldı (→ 44, məktub
  Inbox-da); Gmail `OR` + `X-GM-MSGID` axtarışı yalnız oxuyaraq yoxlandı; test axşam yekunu 23:33-də düymə ilə Samir-ə göndərildi; loqda 0 xəta.

**🗑️ Phase 9.1 — lazımsız məktubları silmək (2026-11-04, canlıdır, commit ca6f6f2):**
- **Giriş:** `/mail sil`, agentə «lazımsız məktubları sil» (`find_unnecessary_emails`, yalnız siyahı hazırlayır) və axşam yekununun «🗑 Bax və sil» düyməsi.
- **Qərar:** namizədləri kod seçir (`-category:primary -is:starred`), Claude ən yeni 25-inə «sil / saxla» və səbəb yazır (`app/services/mail_review.py`).
  «Saxla» deyilənlər `mail_kept`-ə düşür, bir daha baxılmır. Məktub məzmunu etibarsızdır, cavabdan yalnız verilən sıra nömrələri qəbul olunur.
- **Silmə yalnız düymə ilə** (`mt:*`, `_on_trash_callback`): «🗑 Hamısını sil», «✏️ Seç», «✋ Hamısını saxla», sonra «↩️ Geri qaytar» və «🔎 Daha çox yoxla».
  Agentin silən aləti yoxdur. Silmə = Zibil qutusuna IMAP MOVE (Gmail 30 gün saxlayır), expunge yoxdur. Basanda filtr yenidən yoxlanır: arada ulduz qoyulubsa
  və ya məktub «Əsas»a keçibsə toxunulmur.
- **Yoxlandı:** pytest; real Gmail-də Zibil qutusuna köçürmə + geri qaytarma; namizəd seçimi real poçtda yalnız oxuyaraq (Inbox 257, namizəd 129, 25-i ~5 san).
  2026-11-05 canlı Claude: uydurma məktublarda 15/15, təhlükəli səhv 0 (`docker compose exec -T bot python - < scripts/mail_review_smoke.py`, ~40 san);
  agent səhv eşidilmiş səsli cümlədən aləti çağırdı, real poçtda 25-dən 14-ü təklif olundu (test ROLLBACK-la, heç nə silinmədi).

**🎙️ Phase 9.2 — səs tanıma (2026-11-05, canlıdır, commit 9dd3684):**
- **Son vəziyyət:** `WHISPER_MODEL=/models/whisper/az-small-ct2` = `LocalDoc/azerbaijani-whisper-small` (Apache-2.0, `small` ölçüsü, AZ üçün öyrədilib), bir dəfə `scripts/convert_az_whisper.py` ilə çevrilib. `large-v3`-də real 1 saniyəlik səs 45 san çəkdi, Samir «çox gözləyirəm» dedi.
  Ölçü (noutbukda, int8, beam 5): Common Voice 20 klip: **söz səhvi 16,1% · hərf 5,5% · 6,8 san · RAM 0,7 GB** (`large-v3`: 16,8% · 3,9% · 38,6 san · 5,0 GB). FLEURS test 20 klip: **20,7% · 6,5% · 6,1 san**, adi `small` 52,7% · 15,6% · 5,8 san. Model kartındakı FLEURS rəqəmləri: AZ small 20,54%, adi `large-v3` 21,00%, adi `small` 52,17%.
  Həddi: model Common Voice-la öyrədilmiş ola bilər, ona görə o 16,1% yumşaq ola bilər; FLEURS testi kartda ayrıca test kimi göstərilir. Çevrilmiş model yoxdursa bot adi `small`-a keçir (loqda `whisper_model_missing`). Bu CPU-da `int8` ən sürətlidir: `small` üzərində `float32` 8,8 san, `int16` 9,6 san, `int8` 6,9 san; CPU 2,9 GHz, throttle yoxdur. `.env`-dəki OpenAI və Azure açarları 401 qaytarır.
- **Səbəb:** `small` real nitqi pis eşidirdi («laxımsız məşdüplara», «suiks mələyəm»). Əvvəlki «medium daha yaxşı deyil» qənaəti tək təmiz nümunədən idi, səhv çıxdı.
- **Ölçü** (noutbukda, Common Voice az, 20 oxunmuş klip, orta 6 san, int8, beam 5; söz səhvi · hərf səhvi · bir səsə vaxt · RAM pik):
  `small` 58,1% · 15,9% · 6 san · 0,8 GB | `medium` 34,2% · 7,8% · 20 san · 2,7 GB | `large-v3-turbo` 27,1% · 6,0% · 31 san · 2,3 GB | **`large-v3`** 16,8% · 3,9% · 39 san · 5,0 GB.
  Vaxtı encoder aparır: qısa səs də təxminən bu qədər çəkir. `beam_size=1`: 36 san, 3,8 GB, 18,7%, saxlanmadı. 8 thread: 41 san, daha yavaş. Whisper `initial_prompt`: `small`-da kömək etmədi (15,9% → 16,4%), əlavə olunmadı.
- **Digər dəyişikliklər:** Agentə mətnin səsdən gəldiyi deyilir (`VOICE_NOTE`, `with_voice_note`). Telegram timeout-ları 30 san, `_download_voice` 3 cəhd + aydın xəta (2026-11-04 12:14-də səs `get_file` TimedOut ilə itmişdi). Çevrilmə boyu «yazır…».
- **Yoxlandı:** 154 pytest; deploy; canlı agent «suiks mələyəm»-i artıq saxlamır, dəqiqləşdirir (bazaya yazılmadı).
- **Yoxlanmayıb:** Samir yeni modeli «Bəli» ilə təsdiqlədi, amma real səslərin vaxtı loqdan oxunmayıb (`voice_transcribed` → `audio_sec`, `stt_sec`; Mac ev şəbəkəsində deyildi). BuzzASR sınanmayıb: `large-v3` ölçüsündədir, ona görə yavaşdır.

**Açıq iş:** (1) evdən: real səslərin `stt_sec`-ini oxumaq və volume-dan `large-v3`-ü silmək (3 GB); (2) Telegram-da `/mail` və «yeni məktublarım var?» testi (Samir);
(3) droplet-i silmək (DigitalOcean → Destroy, Samir edir).

**Kiçik nasazlıq (düzəldilməyib):** `deploy-from-mac.sh` doctor ❌ versə də sonda «Hazırdır» yazır; doctor başlığındakı «e-poçt: qoşulub» yalnız ayarın
olması deməkdir, real giriş nəticəsi `E-poçt` sətrindədir.

**Gündəlik:** yeniləmə `bash scripts/linux/deploy-from-mac.sh` · yoxlama `ssh jobradar-linux 'cd ~/SecondBrain && docker compose exec bot python scripts/doctor.py'`
· ətraflı [LINUX.md](LINUX.md).
**Qaydalar:** JobRadar production-dur, ona toxunma · Mac-da botu işə salma (token canlı botundur) · Samir-in yapışdıracağı əmrlərdə `||` yox, bir sətir.
**Yoxlandı:** ilk gecə backup-ı 2026-11-03 03:15-də işlədi.
**Yoxlanmayıb:** noutbukun real reboot-u, real yeni məktub bildirişi, Linux-da real xatırlatma çatdırılması
(ilki 2026-11-04 09:00), saat 22:00-da avtomatik gedən ilk axşam yekunu (2026-11-04), Telegram-da «Bax və təmizlə» →
«Hamısını arxivlə» düymələri, Samir-in Reply → gündəlik qeydi.

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

## 🚀 Phase 6.2 — Daha çox feature (2026-08-17, canlı deploy edildi)

Samir seçdi, hamısı lokal smoke test + fresh/existing migration + real image import keçdi.
**Migration 0004** (additive): `notes.pinned`, `tasks.recur`, `tasks.completed_at`.
- **🎙️ Səs→səs mirror** — səsli mesaja avtomatik səslə cavab (`voice_mirror` setting, default AÇIQ;
  `/voice mirror` toggle). Həmişə-səsli `voice_reply`-dan asılı deyil.
- **🗑️/📌 /list düymələri** — hər qeyddə ☆/📌 (pin toggle) + 🗑 (sil); siyahını yerində yeniləyir.
  `/pinned` sabitlənmişləri göstərir; pinned qeydlər əvvəl gəlir. (Filtrli /list mətn-only qalır.)
- **🔁 Təkrarlanan tapşırıq** — `tasks.recur` (daily/weekly/monthly); `/done` edəndə növbəti nüsxə
  yaranır (`next_task_occurrence`, ay-sonu clamp), `completed_at` yazılır. create_task tool + `/tasks` 🔁.
- **🧾 Kateqoriya xülasəsi** — `summarize_category` agent tool ("iş qeydlərimi xülasə et").
- **📊 Fəaliyyət hesabatı** — `activity_report` agent tool ("bu həftə nə etdim?"; completed_at-dan istifadə).
- **🌍 Cavab dili** — agent istifadəçinin dilində cavab verir (default AZ) — system prompt dəyişikliyi.
- **❓ Ağıllı sual** — niyyət/vaxt HƏQİQƏTƏN qeyri-müəyyəndirsə agent bir qısa dəqiqləşdirici sual verir
  (konservativ — hər mesajda yox). ⚠️ Demo zamanı bunu nəzərə al.
- **🔔 Qeyddən xatırlatma** — "bunu sabah xatırlat" kontekstdəki qeyddən xatırlatma qurur (prompt hint).

Yeni agent alətləri: `summarize_category`, `activity_report` (cəmi 6+web_search). Yeni əmr: `/pinned`.

## 🧩 Phase 7 — Spec boşluqları (2026-10-31, commit c244577)

Audit: ilkin spesifikasiyada olub qurulmayan hissələr bağlandı. **Migration yoxdur.**
- **🧩 Əlaqəli qeydlər** — `note_links` yazılırdı, amma heç yerdə oxunmurdu. İndi:
  `links.find_related` (saxlanmış linklər hər iki istiqamətdə + embedding qonşuları ≤0.68 — link/PDF/
  şəkil/`/edit` qeydləri də əhatə olunur), agent tool `get_related_notes` («#12 ilə əlaqəli nə var?»),
  `/related <id>` əmri. Save təsdiqi indi `#id`-ni də deyir (follow-up üçün).
- **💰 Soft aylıq büdcə** (`app/services/budget.py`) — ilkin qərardakı "soft monthly cap".
  `MONTHLY_BUDGET_USD` (per-user, 0=söndürülü) + `BUDGET_WARN_PCT=80`. Hədd keçiləndə bot DAYANMIR:
  Sonnet eskalasiyası + səsli cavab ayın sonunadək söndürülür; warn/over bildirişi ayda bir dəfə
  (`settings.budget_notified`). `/stats`-da büdcə sətri. Yoxlama cavab GÖNDƏRİLDİKDƏN sonra işləyir
  və xəta olsa cavabı bloklamır.
- **🔒 Düzəlişlər** — (1) Markdown escape (`app/bot/md.py`): qeyd/tapşırıq/xatırlatma mətnində tək `_`/`*`
  (e-poçt, fayl adı) `/list`, `/tasks`, `/remind`, `/search`, PDF cavabı və **səhər brifinqini** sındırırdı
  (mesaj ümumiyyətlə getmirdi). (2) `on_callback` allowlist yoxlaması (CallbackQueryHandler-də filtr yox idi).
- **📋 `/` menyu** — `BOT_COMMANDS` + `set_my_commands` startup-da (BotFather-də əl ilə yeniləmə lazım deyil).
- **Testlər:** 42 pytest (16 yeni: büdcə, Markdown, agent wiring, `_run_agent` fake-lərlə) + `scripts/phase7_smoke.py`
  (real Postgres/pgvector, sintetik embedding, ROLLBACK) keçdi. `--live` agent marşrutlaşdırma testi
  **icra olunmadı**: lokal `.env`-dəki `ANTHROPIC_API_KEY` 401 qaytarır (açar dəyişdirilib/ləğv olunub).

**Qeyd:** abunə rejimində (Phase 8) büdcə default söndürülüdür (`MONTHLY_BUDGET_USD=0`) — real ödəniş yoxdur.

## 🐧 Phase 8.1 — Linux noutbukda bir əmrlə quraşdırma (🟢 CANLI 2026-11-02 23:11 Bakı)

**Canlı vəziyyət (quraşdırmadan dərhal sonra oxunub):** `@Personal_AI_Asisstant_bot` noutbukda, konflikt 0, xəta 0, RAM 2.2/5 GB;
real konteynerdə real tokenlə Claude cavab verdi; JobRadar aktiv, sıfır restart. **Baza təmiz başladı (0 qeyd):** Samir
«Təmiz başlasın» seçdi, çünki VPS-ə SSH alınmadı (port 22 açıq, amma `id_ed25519` və `gh_actions` ikisi də açmadı; səbəb
dəqiq bilinmir). **Köhnə qeydlər yalnız droplet-dədir** — silinsə itir, sonradan avtomatik birləşmir. **E-poçt** sonradan qoşuldu
(23:50, yuxarı bax). İlk real mesaj 23:23-də emal olundu (~7 s, xəta yox);
ondan əvvəlki mesajlardan loqda iz yoxdur, səbəbi dəqiq bilinmir (ehtimal: başqa çat və ya 23:14/23:16 yenidən başlamaları).
Quraşdırma real noutbukda ~12 dəqiqə çəkdi.

**Samir-in qərarı:** 4 GB-lıq Windows laptop rədd edildi; bot **JobRadar-ın işlədiyi Linux noutbukda** işləyəcək.
Əmr: `bash scripts/linux/deploy-from-mac.sh --vps root@VPS-IP` → **[LINUX.md](LINUX.md)**.

**Host (2026-11-02 oxunub):** ssh alias `jobradar-linux` (DHCP — IP dəyişə bilər), Linux Mint 22.3 (noble), i7-3630QM
4C/8T, flags **AVX var, AVX2/FMA YOX**, 15 GB RAM (11 GB boş), 88 GB disk boş, Docker yox idi, JobRadar 3 systemd
xidməti aktiv (production, **ona toxunma**; onun canlı restart-ları Samir-indir). Second Brain host portu açmır.

**CPU sübutu (AVX2 yoxdur):** SDK-nın x86_64 wheel-indəki `_bundled/claude` = noutbukda işləyən `claude` 2.1.316
(sha256 + ölçü eyni). x86_64 image emulyasiyada `-cpu IvyBridge`: onnxruntime, ctranslate2, av import + mpnet embedding +
Whisper small transkript işlədi.

**Canlı Claude (abunə, həftəlik limit bərpa olunandan sonra): 12/12.** Sadə cavab, save_note (agent meta, ayrıca CLI yox),
RAG + sitat, get_related_notes, create_reminder, WebSearch, `claude-sonnet-5` eskalasiya, şəkil OCR (streaming input),
e-poçt triajı (high/low düzgün), **prompt injection bloklandı** (məktubdakı "pul göndər" alət çağırmadı). Gecikmə: 5-7 san
sadə, ~20 san WebSearch/Sonnet.

**Tapılıb düzəldilib:** Haiku `**bold**` yazır → `md.plain_text`; «yazır…» 5 san sönürdü → `_keep_typing`; CLI-də
max_tokens yoxdur → `md.split_message` (4096 limit).

**Qurulanlar:** `scripts/linux/deploy-from-mac.sh` (Mac: suallar başda, tar+ssh ilə iş qovluğunu göndərir — commit
lazım deyil, sirlər stdin ilə, VPS keçidi + avtomatik rollback), `scripts/linux/install.sh` (Linux: idempotent; `curl|bash`
də olar), `docker-compose.host.yml` (host portu yox, RAM 5g, cpu_shares 256, oom_score_adj 500, log rotasiya; `.env`-də
COMPOSE_FILE), `scripts/doctor.py` (Telegram/DB/Claude/e-poçt; `--preflight` keçiddən ƏVVƏL). Claude tokeni noutbukda
JobRadar `.env`-indən götürülür. Multiplexing qəsdən yoxdur (yeni sessiya `docker` qrupunu görsün).

**E2E test (saxta noutbuk: systemd + sudo şifrəsi + Docker-siz Ubuntu 24.04, saxta VPS, saxta Telegram; real token/production
toxunulmayıb):** təmiz qurulma; VPS stop → dump → restore → start; saxta Telegram tokeni → avtomatik rollback (VPS geri
qayıtdı); etibarsız Claude tokeni → VPS-ə toxunmadan dayandı; real polling: mesaj → LLM xətası → xam qeyd + xəbərdarlıq,
`/health`, `/search`, `/mail`; sxem 0004→0005; köhnə vektorlar lokal modellə yenidən hesablandı; limitlər tətbiq olundu;
yeniləmə 38 s, sıfır sual, VPS-ə toxunmur; **reboot → girişsiz özü qalxır**; backup; `--email`; loqlarda 0 token. 97 pytest.
**Hələ yoxlanmayıb:** VPS-dən köçürmə real serverdə (giriş alınmadı; köçürmə sonra ləğv olundu). Real Gmail App Password 2026-11-02 23:50-də yoxlandı.

## 🖥️ Phase 8 — Claude abunəsi + Windows PC 24/7 + e-poçt (2026-10-31, commit c244577)

Samir-in tələbi: **API açarı yox, yalnız Claude aylıq abunəsi**; evdəki köhnə Windows PC 24/7 (Mac hibrid);
e-poçt oxumaq. Addım-addım quraşdırma: **[WINDOWS.md](WINDOWS.md)**. Migration: **0005** (`app_meta`, additiv).
- **LLM = abunə** (`app/providers/llm_subscription.py`): Claude Agent SDK (CLI paketin içində, Node yox) +
  `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`, 1 il, scope `user:inference`). `complete()/text_of()` eyni
  interfeys → servislər dəyişmədi. Bərkitmə: `tools=[]`, `dontAsk`, `strict_mcp_config`, `--no-session-persistence`,
  `--disable-slash-commands`, `ANTHROPIC_API_KEY=""` (pullu API-yə səhvən keçmə), token varsa ayrıca
  `CLAUDE_CONFIG_DIR` (host pluginləri/hook-ları yüklənmir). Limit/auth/timeout → `app/providers/errors.py`.
- **Agent** (`app/agent/sdk_agent.py`): alətlərimiz in-process MCP server (`mcp__brain__*`), daxili yalnız
  `WebSearch`; AsyncSession üçün kilid (paralel alət çağırışı); save_note meta-nı agent özü doldurur (əlavə CLI
  çağırışı yox); e-poçt/veb məzmunu ETİBARSIZ (prompt). CLI `init`-də təsdiqləndi: yalnız WebSearch + 7 alət,
  `brain: connected`, `apiKeySource: none`.
- **Limit dolanda** (`_run_agent`): «⏳ … bərpa olunur» + mesaj xam qeyd (alət artıq işləyibsə dublikat yox).
  Qlobal PTB error handler (Telegram `Conflict` üçün aydın log).
- **Lokal embedding** (`embeddings_local.py`, fastembed): `paraphrase-multilingual-mpnet-base-v2` — AZ testi
  top-1 9/10 (MiniLM 6/10). 768 → **1536-ya sıfırla tamamlanır** (cosine dəyişmir, sxem dəyişmədi).
  Əlaqəli hədd 0.55 (provayder atributu). Model dəyişəndə `services/reembed.py`: `app_meta.embedding_model`
  fərqlidirsə vektorlar NULL → `reembed_tick` (60s) partiyalarla doldurur (VPS dump-ı → avtomatik).
- **Lokal STT** (`stt_local.py`, faster-whisper `small`, int8): AZ nümunəsində small ~1.7s, medium 2.5× yavaş
  və daha yaxşı deyil (tək təmiz nümunə idi, real nitqdə səhv çıxdı: Phase 9.2). ⚠️ `av<19` pin (PyAV 19 `metadata_errors`-u silib → faster-whisper 1.2 sınır).
- **E-poçt** (`providers/email_imap.py`): IMAP readonly + `BODY.PEEK` (oxunmuş etmir), UTF-8 axtarış (literal),
  INTERNALDATE fallback. Alətlər `check_email`/`search_email`/`read_email`; `/mail` (`<uid>`, `on|off`);
  `email_tick` (10 dəq) → yeni məktub bildirişi, reklam AI-siz süzülür, triaj TƏK Claude çağırışı; brifinqdə
  oxunmamış sayı. GreenMail IMAP serverinə qarşı uçdan-uca test edildi.
- **Backend seçimi** `auto`: token → abunə; OpenAI açarı yoxdur → lokal. VPS konfiqurasiyası (API açarları)
  dəyişmədən işləyir. **VPS auto-deploy söndürüldü** (`deploy.yml` yalnız `workflow_dispatch`) — PC-yə
  köçəndən sonra push VPS botunu yenidən başladıb Telegram konflikti yaratmasın.
- **Docker/Windows:** `models` volume, `PYTHONPATH=/app`, `claude` əmri image-də, `.gitattributes` (LF —
  Windows klonunda `bad interpreter` olmasın), `scripts/windows/*.ps1` (setup/update/backup/restore/
  install-tasks; PS 5.1 tələləri nəzərə alınıb, pwsh parser ilə yoxlanıb; backup/restore əmrləri real DB-də).
- **Testlər:** 70 pytest + `scripts/phase8_smoke.py` (konteynerdə açarsız hissə keçdi; `--live` PC-də).
- **Canlı Claude yoxlaması mümkün olmadı:** Mac-dəki `claude` hesabı **həftəlik limitə** çatmışdı
  (2026-11-02 18:00 Bakı bərpa) — limit aşkarlanması real cavabla təsdiqləndi.

**⏳ MANUAL (Samir) — ardıcıllıq [WINDOWS.md](WINDOWS.md)-də:** commit + push → PC-də proqramlar (WSL2, Docker,
Git) → `claude setup-token` → Gmail App Password → `.env` → `setup.ps1 -NoSleep` → `phase8_smoke.py --live` →
(köhnə qeydlər üçün) VPS backup → VPS botunu dayandır → `restore.ps1` → `install-tasks.ps1`.

## ☁️ GitHub + Deploy (2026-08-13)
- Repo (2026-10-31 yoxlanıb): **https://github.com/nabiyevsamir-002/Second-Brain** — **PUBLIC** (köhnə ad:
  nebiyevsamir002-star/AI-Assistant, private idi). Açıq repoya sirr/IP yazma.
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
  bot/md.py              # Telegram Markdown escape (md/md_in) — istifadəçi mətni parse-ı pozmasın
  services/budget.py     # soft aylıq büdcə (warn/over, bildiriş, degrade)
  bot/scheduler.py       # PTB JobQueue — reminder (60s) + brifinq (saatlıq tick, per-user settings)
  agent/agent.py         # BrainAgent — tool-use döngəsi + cari vaxt inject + LLM usage log
  timeutils.py           # Baku local ⇄ tz-aware parse/format (parse_local_iso, fmt_local)
  pricing.py             # model qiymətləri + llm/embed/stt cost (TƏXMİNİ) — /stats mənbəyi
  providers/             # llm_claude, embeddings_openai, stt_whisper, factory, registry, base
  tools/                 # base(+ToolContext), save_note, search_notes, get_related_notes, create_reminder,
                         # create_task, summarize_category, activity_report, web_search, registry
  services/              # notes_service (capture_note+cost), ingest_service (url/pdf/docx)
  repositories/          # users(+settings), notes(+delete/export), messages(+count), links, usage(+totals), reminders, tasks
migrations/              # Alembic (0001_initial — bütün cədvəllər onsuz da var)
scripts/backup.sh        # pg_dump → HOST CRON-a bağlanır (aşağı bax)
scripts/phase4_smoke.py  # Phase 4 canlı smoke test (docker compose run ilə)
scripts/phase5_smoke.py  # Phase 5 canlı smoke test (pricing/usage/export/delete/settings)
scripts/phase7_smoke.py  # Phase 7: əlaqəli qeydlər + büdcə (host-dan DATABASE_URL=...127.0.0.1:5433; --live)
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
