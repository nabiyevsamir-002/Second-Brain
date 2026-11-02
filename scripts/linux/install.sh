#!/usr/bin/env bash
# Second Brain: Linux-da hər şeyi qurur və işə salır. Təkrar işlətmək təhlükəsizdir.
#
#   bash scripts/linux/install.sh               # hamısı: qur + işə sal + yoxla
#   bash scripts/linux/install.sh --no-start    # qur, botu başlatma (keçiddən əvvəl)
#   bash scripts/linux/install.sh --start       # yalnız işə sal + yoxla
#   bash scripts/linux/install.sh --restore F   # F (.sql.gz) dump-ını BOŞ bazaya bərpa et
#
# Adətən MacBook-dan scripts/linux/deploy-from-mac.sh işlədir. Birbaşa Linux-da da olar:
#   curl -fsSL https://raw.githubusercontent.com/nabiyevsamir-002/Second-Brain/main/scripts/linux/install.sh | bash
#
# Yanındakı xidmətlərə toxunmur (məs. JobRadar): host portu açmır, onların fayllarını dəyişmir,
# konteyner yaddaş/CPU limiti ilə işləyir (docker-compose.host.yml).
set -euo pipefail

REPO_URL="${SECOND_BRAIN_REPO_URL:-https://github.com/nabiyevsamir-002/Second-Brain.git}"
INSTALL_DIR="${SECOND_BRAIN_DIR:-$HOME/SecondBrain}"
DB_CONTAINER="second_brain_db"
MIN_DISK_MB=8000          # image ~2.2 GB + modellər ~1.6 GB + baza + ehtiyat
MIN_RAM_MB=3500           # ölçülmüş pik ~2.4 GB

say()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
good() { printf '\033[1;32m✅ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠️  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m❌ %s\033[0m\n' "$*" >&2; exit 1; }

# Loqda token görünsə (məs. PTB InvalidToken) ekrana çıxmasın.
redact() { sed -E 's/[0-9]{6,}:[A-Za-z0-9_-]{20,}/<telegram-token>/g; s/sk-ant-[A-Za-z0-9_-]+/<claude-token>/g'; }

# --- sudo: yalnız lazım olanda soruşulur --------------------------------------
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
SUDO_READY=0
need_sudo() {
  [ -n "$SUDO" ] || return 0
  [ "$SUDO_READY" = 0 ] || return 0
  command -v sudo >/dev/null || die "sudo tapılmadı."
  if ! sudo -n true 2>/dev/null; then
    info "Admin icazəsi lazımdır (Linux şifrən bir dəfə soruşulur, ekranda görünmür):"
    sudo -v || die "Bu istifadəçinin sudo icazəsi yoxdur."
  fi
  ( while kill -0 "$$" 2>/dev/null; do sudo -n true; sleep 50; done ) >/dev/null 2>&1 &
  SUDO_READY=1
}

APT=(env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300)

apt_update() {  # sınıq üçüncü tərəf repo (məs. köhnə PPA) quraşdırmanı dayandırmasın
  $SUDO "${APT[@]}" update -qq || warn "apt update xəbərdarlıq verdi, davam edirəm."
}

pkg_install() {
  need_sudo
  if command -v apt-get >/dev/null; then
    apt_update
    $SUDO "${APT[@]}" install -y -qq "$@"
  elif command -v dnf >/dev/null; then
    $SUDO dnf install -y -q "$@"
  elif command -v pacman >/dev/null; then
    $SUDO pacman -Sy --noconfirm --needed "$@"
  elif command -v zypper >/dev/null; then
    $SUDO zypper --non-interactive install "$@"
  else
    die "Paket meneceri tapılmadı (apt, dnf, pacman, zypper)."
  fi
}

# --- `curl | bash`: kod hələ yoxdursa gətir və özünü oradan işlət -----------------
script_path="${BASH_SOURCE[0]:-}"
REPO=""
if [ -n "$script_path" ] && [ -f "$script_path" ]; then
  REPO="$(cd "$(dirname "$script_path")/../.." && pwd)"
fi
if [ -z "$REPO" ] || [ ! -f "$REPO/docker-compose.yml" ]; then
  say "Kod: $INSTALL_DIR"
  command -v git >/dev/null || pkg_install git curl ca-certificates
  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull -q --ff-only
  else
    git clone -q "$REPO_URL" "$INSTALL_DIR"
  fi
  if (exec </dev/tty) 2>/dev/null; then
    exec bash "$INSTALL_DIR/scripts/linux/install.sh" "$@" </dev/tty
  fi
  exec bash "$INSTALL_DIR/scripts/linux/install.sh" "$@"
fi
cd "$REPO"

ENV_FILE="$REPO/.env"
STATE_FILE="$REPO/.install-state"

# --- .env köməkçiləri: dəyərləri heç vaxt çap etmir -------------------------------
env_value() {  # FAYL AÇAR → dəyər (export/dırnaq/şərhsiz)
  [ -f "$1" ] || return 0
  KEY="$2" awk '
    BEGIN { k = ENVIRON["KEY"]; q = sprintf("%c", 39) }
    {
      line = $0
      sub(/^[ \t]*(export[ \t]+)?/, "", line)
      if (index(line, k "=") != 1) next
      v = substr(line, length(k) + 2)
      c = substr(v, 1, 1)
      if (c == "\"" || c == q) {
        v = substr(v, 2); i = index(v, c); if (i) v = substr(v, 1, i - 1)
      } else {
        sub(/[ \t]+#.*$/, "", v); sub(/[ \t]+$/, "", v)
      }
      val = v
    }
    END { printf "%s", val }
  ' "$1"
}

set_env() {  # AÇAR DƏYƏR — sətri əvəz edir, yoxdursa sona əlavə edir (awk həmişə \n yazır)
  local key="$1" value="$2" tmp
  case "$value" in
    *[!A-Za-z0-9_:.@/+,=-]*) value="'$value'" ;;  # compose/dotenv $ və # işarəsini yozmasın
  esac
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  KEY="$key" VALUE="$value" awk '
    BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VALUE"]; done = 0 }
    index($0, k "=") == 1 { if (!done) { print k "=" v; done = 1 } next }
    { print }
    END { if (!done) print k "=" v }
  ' "$ENV_FILE" > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

state_get() { [ -f "$STATE_FILE" ] && grep -q "^$1=" "$STATE_FILE"; }
state_set() { touch "$STATE_FILE"; state_get "$1" || printf '%s=%s\n' "$1" "$(date '+%F %T')" >> "$STATE_FILE"; }

ask() {  # SUAL → dəyişən REPLY (terminal yoxdursa boş)
  REPLY=""
  [ -t 0 ] || return 0
  read -r -p "   $1" REPLY || REPLY=""
}

ask_secret() {
  REPLY=""
  [ -t 0 ] || return 0
  read -r -s -p "   $1" REPLY || REPLY=""
  printf '\n'
}

# --- Docker --------------------------------------------------------------------
DOCKER="docker"
dc() { $DOCKER compose "$@"; }

pick_docker_cmd() {
  if docker info >/dev/null 2>&1; then
    DOCKER="docker"
  else  # qrup üzvlüyü bu sessiyada hələ qüvvədə deyil
    need_sudo
    DOCKER="$SUDO docker"
  fi
}

ensure_docker() {
  if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
    info "Docker artıq var: $(docker --version | cut -d, -f1)"
  else
    say "Docker quraşdırılır"
    need_sudo
    local apt_ok=0
    if command -v apt-get >/dev/null; then
      # Mint/Ubuntu/Debian öz paketləri: üçüncü tərəf repo əlavə etmir.
      apt_update
      if $SUDO "${APT[@]}" install -y -qq docker.io docker-compose-v2 docker-buildx; then
        apt_ok=1
      fi
    fi
    if [ "$apt_ok" = 0 ]; then
      command -v curl >/dev/null || pkg_install curl ca-certificates
      curl -fsSL https://get.docker.com | $SUDO sh
    fi
  fi
  if command -v systemctl >/dev/null; then
    if [ "$(systemctl is-enabled docker 2>/dev/null || true)" != "enabled" ] \
        || ! systemctl is-active -q docker; then
      need_sudo
      $SUDO systemctl enable --now docker >/dev/null 2>&1 || warn "docker xidməti aktiv olmadı."
    fi
  fi
  if [ -n "$SUDO" ]; then
    case ",$(getent group docker | cut -d: -f4)," in
      *",$(id -un),"*) ;;
      *) need_sudo; $SUDO usermod -aG docker "$(id -un)" ;;
    esac
  fi
  pick_docker_cmd
  $DOCKER compose version >/dev/null 2>&1 || die "docker compose işləmir."
}

# --- Yoxlamalar -----------------------------------------------------------------
preflight() {
  say "Sistem yoxlanır"
  [ "$(uname -s)" = "Linux" ] || die "Bu skript Linux üçündür."
  case "$(uname -m)" in
    x86_64|amd64|aarch64|arm64) ;;
    *) die "Bu prosessor dəstəklənmir: $(uname -m)" ;;
  esac
  local ram avail disk cpu
  ram="$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)"
  avail="$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
  disk="$(df -Pm "$REPO" | awk 'NR==2 {print $4}')"
  cpu="$(awk -F: '/^model name/ {sub(/^ +/, "", $2); print $2; exit}' /proc/cpuinfo)"
  info "${cpu:-$(uname -m)} · RAM ${ram} MB (boş ${avail} MB) · disk boş ${disk} MB"
  [ "$ram" -ge "$MIN_RAM_MB" ] || die "RAM azdır: ${ram} MB (minimum ${MIN_RAM_MB} MB, bot ~2.4 GB işlədir)."
  [ "$disk" -ge "$MIN_DISK_MB" ] || die "Disk azdır: ${disk} MB boş (minimum ${MIN_DISK_MB} MB)."
  [ "$avail" -ge 3000 ] || warn "Boş RAM azdır (${avail} MB): bot digər proqramları sıxışdıra bilər."
  case "$(uname -m)" in
    x86_64|amd64) grep -qw avx /proc/cpuinfo || warn "Bu prosessorda AVX yoxdur: AI modelləri işləməyə bilər." ;;
  esac
}

# --- .env -----------------------------------------------------------------------
configure_env() {
  say "Konfiqurasiya (.env)"
  if [ ! -f "$ENV_FILE" ]; then
    cp "$REPO/.env.example" "$ENV_FILE"
    info ".env yaradıldı"
  fi
  chmod 600 "$ENV_FILE"

  # MacBook-dan gələn dəyərlər (deploy-from-mac.sh) — stdin ilə gəlib, sonra silinir.
  local seed="$REPO/.env.seed" line
  if [ -f "$seed" ]; then
    while IFS= read -r line; do
      case "$line" in *=*) set_env "${line%%=*}" "${line#*=}" ;; esac
    done < "$seed"
    rm -f "$seed"
  fi

  # Yalnız abunə + lokal modellər; bu hostda pullu API açarı işlədilmir.
  case "$(env_value "$ENV_FILE" COMPOSE_FILE)" in
    *docker-compose.host.yml*) ;;
    *) set_env COMPOSE_FILE "docker-compose.yml:docker-compose.host.yml" ;;
  esac
  set_env LLM_BACKEND subscription
  set_env EMBED_BACKEND local
  set_env STT_BACKEND local
  set_env ENVIRONMENT production

  if [ -z "$(env_value "$ENV_FILE" TELEGRAM_BOT_TOKEN)" ]; then
    ask_secret "Telegram bot tokeni (@BotFather): "
    [ -n "$REPLY" ] || die "TELEGRAM_BOT_TOKEN lazımdır (.env faylına yaz və yenidən işlət)."
    set_env TELEGRAM_BOT_TOKEN "$REPLY"
  fi
  if [ -z "$(env_value "$ENV_FILE" ALLOWED_USER_IDS)" ]; then
    ask "Telegram ID-n (bota yalnız bu ID yaza bilər): "
    [ -n "$REPLY" ] || die "ALLOWED_USER_IDS lazımdır — boş qalsa bota hər kəs yaza bilər."
    set_env ALLOWED_USER_IDS "$REPLY"
  fi

  # Claude abunə tokeni: eyni noutbukdakı JobRadar artıq işlədirsə, ikinci dəfə almağa ehtiyac yoxdur.
  if [ -z "$(env_value "$ENV_FILE" CLAUDE_CODE_OAUTH_TOKEN)" ]; then
    local token
    token="$(env_value "$HOME/JobRadar-AZ/.env" CLAUDE_CODE_OAUTH_TOKEN)"
    if [ -n "$token" ]; then
      set_env CLAUDE_CODE_OAUTH_TOKEN "$token"
      info "Claude tokeni: JobRadar-ın .env-indən götürüldü (eyni abunə)"
    else
      info "Claude tokeni yoxdur. MacBook terminalında bunu işlət: claude setup-token"
      ask_secret "Çıxan tokeni (sk-ant-oat01-...) bura yapışdır: "
      [ -n "$REPLY" ] || die "CLAUDE_CODE_OAUTH_TOKEN lazımdır."
      set_env CLAUDE_CODE_OAUTH_TOKEN "$REPLY"
    fi
  fi
  info "Hazırdır: abunə rejimi, lokal axtarış və səs tanıma"
}

# --- 24/7: yuxu yoxdur (qapaq bağlı da işləyir) -----------------------------------
no_sleep() {
  command -v systemctl >/dev/null || return 0
  if [ "$(systemctl is-enabled sleep.target 2>/dev/null || true)" = "masked" ]; then
    info "Yuxu rejimi artıq söndürülüb"
    return 0
  fi
  say "Yuxu rejimi söndürülür (qapaq bağlı da işləyir)"
  need_sudo
  $SUDO mkdir -p /etc/systemd/logind.conf.d
  $SUDO tee /etc/systemd/logind.conf.d/second-brain.conf >/dev/null <<'LOGIND'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
HandleSuspendKey=ignore
HandleHibernateKey=ignore
IdleAction=ignore
LOGIND
  # HUP, restart yox: logind-i restart etmək masaüstü sessiyasını bağlaya bilər.
  $SUDO systemctl kill -s HUP systemd-logind >/dev/null 2>&1 || true
  $SUDO systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target \
    suspend-then-hibernate.target >/dev/null 2>&1 || warn "Yuxu rejimi söndürülmədi."
}

# --- Gecə backup (03:15, 14 gün saxlanır) ------------------------------------------
backup_cron() {
  mkdir -p "$REPO/backups"
  local cron_file="/etc/cron.d/second-brain" user line
  user="$(id -un)"
  line="15 3 * * * $user cd $REPO && bash scripts/backup.sh >> backups/backup.log 2>&1"
  if [ -f "$cron_file" ] && grep -qxF "$line" "$cron_file"; then
    info "Gecə backup artıq qurulub"
    return 0
  fi
  if ! command -v cron >/dev/null && ! command -v crond >/dev/null; then
    warn "cron tapılmadı: gecə backup qurulmadı (əl ilə: bash scripts/backup.sh)."
    return 0
  fi
  need_sudo
  printf '# Second Brain gecə backup — scripts/linux/install.sh\n%s\n' "$line" \
    | $SUDO tee "$cron_file" >/dev/null
  $SUDO chmod 644 "$cron_file"
  info "Gecə backup quruldu: hər gün 03:15, 14 gün saxlanır ($REPO/backups)"
}

# --- Build + bu prosessorda işləyirmi ----------------------------------------------
build_image() {
  say "Image build olunur (ilk dəfə 5-15 dəqiqə)"
  dc build bot
  say "Bu prosessorda işləyirmi"
  dc run --rm --no-deps -T --entrypoint claude bot --version \
    || die "Claude CLI bu prosessorda işləmədi (kod $?)."
  dc run --rm --no-deps -T --entrypoint python bot \
      -c "import onnxruntime, ctranslate2, av; print('AI kitabxanaları: OK')" 2>/dev/null \
    || die "AI kitabxanaları bu prosessorda yüklənmədi (onnxruntime/ctranslate2)."
}

check_accounts() {
  # Köhnə bot dayandırılmazdan ƏVVƏL: token etibarsızdırsa heç nəyə toxunmadan dayanırıq.
  [ -z "$(env_value "$ENV_FILE" SKIP_CLAUDE_CHECK)" ] || return 0
  say "Claude abunəsi və e-poçt yoxlanır"
  dc run --rm --no-deps -T --entrypoint python bot scripts/doctor.py --preflight \
    || die "Claude tokeni işləmir: Mac-da \`claude setup-token\`, tokeni $ENV_FILE faylında CLAUDE_CODE_OAUTH_TOKEN= sətrinə yaz, əmri təkrar işlət."
}

# --- Bərpa: yalnız BOŞ bazaya ------------------------------------------------------
db_up() {
  dc up -d db
  local i
  for i in $(seq 1 60); do
    if $DOCKER exec "$DB_CONTAINER" pg_isready -U postgres -d second_brain >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  die "Baza vaxtında qalxmadı."
}

db_scalar() { $DOCKER exec "$DB_CONTAINER" psql -U postgres -d second_brain -tAc "$1"; }

restore_dump() {
  local file="$1"
  [ -f "$file" ] || die "Fayl tapılmadı: $file"
  gzip -t "$file" || die "Dump pozuqdur: $file"
  say "Köhnə qeydlər bərpa olunur"
  db_up
  local tables notes
  tables="$(db_scalar "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
  if [ "$tables" != "0" ]; then
    notes="$(db_scalar "SELECT count(*) FROM notes" 2>/dev/null || echo 0)"
    if [ "$notes" != "0" ] && state_get installed; then
      die "Bazada artıq $notes qeyd var və bot burada işləyib — üstünə yazmıram."
    fi
    # Bot burada heç canlı olmayıb: əvvəlki uğursuz cəhdin qalığıdır, təmizlə.
    db_scalar "DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
  fi
  gunzip -c "$file" | $DOCKER exec -i "$DB_CONTAINER" \
    psql -q -v ON_ERROR_STOP=1 --single-transaction -U postgres -d second_brain >/dev/null \
    || die "Bərpa uğursuz oldu (baza dəyişmədi)."
  good "Bərpa olundu: $(db_scalar "SELECT count(*) FROM notes") qeyd"
}

# --- İşə sal + yoxla ---------------------------------------------------------------
bot_logs() { dc logs --no-color --tail=400 bot 2>&1 | redact; }

stop_and_die() {  # bot restart dövrəsində qalmasın (eyni token ilə başqa instansı da narahat edir)
  dc stop bot >/dev/null 2>&1 || true
  die "$1"
}

wait_started() {
  local i logs
  for i in $(seq 1 60); do
    logs="$(bot_logs)"
    case "$logs" in
      *"Application started"*) return 0 ;;
      *InvalidToken*)
        printf '%s\n' "$logs" | tail -5 >&2
        stop_and_die "Telegram tokeni qəbul olunmadı: .env-də TELEGRAM_BOT_TOKEN-i yoxla."
        ;;
    esac
    sleep 5
  done
  printf '%s\n' "$logs" | tail -20 >&2
  stop_and_die "Bot 5 dəqiqəyə başlamadı (yuxarıdakı loqa bax)."
}

wait_models() {
  # Bot artıq cavab verir; modellər arxa planda endirilir (ilk dəfə ~1.6 GB).
  local i logs n
  for i in $(seq 1 90); do
    logs="$(bot_logs)"
    n="$(printf '%s\n' "$logs" | grep -c 'model_ready' || true)"
    if [ "$n" -ge 2 ]; then
      good "AI modelləri hazırdır"
      return 0
    fi
    case "$logs" in
      *model_warmup_failed*) warn "Model yüklənmədi: docker compose logs bot | grep model_warmup"; return 0 ;;
    esac
    [ $((i % 6)) -ne 1 ] || info "Modellər endirilir/yüklənir (ilk dəfə ~1.6 GB)..."
    sleep 10
  done
  warn "Modellər hələ yüklənir, bot arxa planda davam edəcək."
}

check_conflict() {
  # Köhnə instansın son sorğusu bir neçə saniyə qala bilər: yalnız DAVAM EDƏN konflikt xətadır.
  local logs
  logs="$(bot_logs)"
  case "$logs" in *telegram_conflict*) ;; *) return 0 ;; esac
  info "Telegram konflikti görünür, 40 saniyə gözləyirəm..."
  sleep 40
  logs="$(dc logs --no-color --since 25s bot 2>&1 | redact)"
  case "$logs" in
    *telegram_conflict*) stop_and_die "Eyni Telegram tokeni başqa yerdə də işləyir (VPS? Mac?): əvvəl oranı dayandır." ;;
  esac
}

start_bot() {
  say "Bot işə salınır"
  dc up -d
  wait_started
  good "Bot işləyir"
  wait_models
  check_conflict
  say "Son yoxlama"
  dc exec -T bot python scripts/doctor.py || warn "Yuxarıdakı ❌ sətrini düzəlt, sonra bu skripti yenidən işlət."
  state_set installed
  $DOCKER image prune -f >/dev/null 2>&1 || true  # köhnə build-lər 120 GB diski doldurmasın
}

# --- Əsas axın ---------------------------------------------------------------------
MODE="${1:-all}"
case "$MODE" in
  all|--no-start)
    preflight
    ensure_docker
    configure_env
    no_sleep
    backup_cron
    build_image
    check_accounts
    if [ "$MODE" = "all" ]; then start_bot; fi
    ;;
  --start)
    pick_docker_cmd
    start_bot
    ;;
  --restore)
    pick_docker_cmd
    restore_dump "${2:?İstifadə: install.sh --restore FAYL.sql.gz}"
    ;;
  --stop-bot)  # deploy-from-mac.sh: keçid alınmasa konflikt olmasın
    pick_docker_cmd
    dc stop bot >/dev/null 2>&1 || true
    ;;
  *)
    die "Naməlum seçim: $MODE (--no-start | --start | --restore F)"
    ;;
esac
