#!/usr/bin/env bash
# Second Brain: MacBook-dan BİR əmr — Linux noutbukda hər şeyi qurur, yeniləyir, işə salır.
#
#   bash scripts/linux/deploy-from-mac.sh [HƏDƏF] [--vps root@IP [--vps-key AÇAR]] [--email] [--yes]
#
#   HƏDƏF      ssh alias və ya user@ip (default: jobradar-linux)
#   --vps      köhnə serverdən ilk keçid: botu orada dayandırır, qeydləri köçürür
#   --vps-key  VPS üçün SSH açarı (default açar oranı açmırsa, məs. ~/.ssh/gh_actions)
#   --email    Gmail məlumatlarını yenidən soruş
#   --yes    təsdiq soruşma
#
# Bütün sualları başda verir, sonra işini özü görür (Linux şifrəsi bir dəfə soruşula bilər).
# Təkrar işlətmək təhlükəsizdir: ikinci dəfə sadəcə kodu yeniləyir, heç nə soruşmur.
# Keçid yarımçıq qalsa VPS-dəki bot avtomatik geri qaytarılır.
set -euo pipefail

say()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
good() { printf '\033[1;32m✅ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠️  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m❌ %s\033[0m\n' "$*" >&2; exit 1; }

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

TARGET="jobradar-linux"
VPS=""
VPS_KEY=""
VPS_DIR="${SECOND_BRAIN_VPS_DIR:-/root/AI-Assistant}"
FORCE_EMAIL=0
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --vps) VPS="${2:?--vps üçün ünvan lazımdır (root@IP)}"; shift 2 ;;
    --vps-key) VPS_KEY="${2:?--vps-key üçün açar faylı lazımdır}"; shift 2 ;;
    --email) FORCE_EMAIL=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    -*) die "Naməlum seçim: $1" ;;
    *) TARGET="$1"; shift ;;
  esac
done

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=15 -o StrictHostKeyChecking=accept-new)
# Multiplexing qəsdən yoxdur: yeni SSH sessiyası docker qrupunu dərhal görməlidir.
remote()   { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }
remote_t() { ssh -t "${SSH_OPTS[@]}" "$TARGET" "$@"; }
vps() {
  local opts=("${SSH_OPTS[@]}" -o BatchMode=yes)
  if [ -n "$VPS_KEY" ]; then opts+=(-i "$VPS_KEY" -o IdentitiesOnly=yes); fi
  ssh "${opts[@]}" "$VPS" "$@"
}

VPS_STOPPED=0
STARTED=0
on_exit() {
  local code=$?
  trap - EXIT
  if [ "$VPS_STOPPED" = 1 ] && [ "$STARTED" = 0 ]; then
    warn "Keçid yarımçıq qaldı. Linux-dakı botu dayandırıb VPS-dəkini geri qaytarıram."
    remote 'cd "$HOME/SecondBrain" && bash scripts/linux/install.sh --stop-bot' >/dev/null 2>&1 || true
    if vps "cd $VPS_DIR && docker compose start bot" >/dev/null 2>&1; then
      warn "VPS botu yenidən işləyir, heç nə itməyib. Səbəbi düzəldib əmri təkrar işlət."
    else
      warn "VPS botu özü başlamadı. Əl ilə: ssh ${VPS_KEY:+-i $VPS_KEY }$VPS \"cd $VPS_DIR && docker compose start bot\""
    fi
  fi
  exit "$code"
}
trap on_exit EXIT

env_value() {  # FAYL AÇAR → dəyər (export/dırnaq/şərhsiz); heç vaxt çap etmə
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

confirm() {  # SUAL — b/h → davam, qalanı dayan
  [ "$YES" = 0 ] || return 0
  local answer=""
  read -r -p "   $1 [b/x]: " answer </dev/tty || answer=""
  case "$answer" in b|B|bəli|h|H|y|Y) return 0 ;; *) return 1 ;; esac
}

# --- 1. Qoşulma ------------------------------------------------------------------
say "Linux-a qoşuluram: $TARGET"
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$TARGET" true 2>/dev/null; then
  case "$TARGET" in
    *@*)
      info "SSH açarı yoxdur — Linux şifrəni bir dəfə yaz (açar köçürülür, sonra soruşulmur):"
      [ -f "$HOME/.ssh/id_ed25519.pub" ] || ssh-keygen -q -t ed25519 -N '' -f "$HOME/.ssh/id_ed25519"
      ssh-copy-id "${SSH_OPTS[@]}" "$TARGET" >/dev/null
      ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$TARGET" true || die "SSH açarı ilə qoşulmaq alınmadı."
      ;;
    *)
      die "Qoşulmaq olmadı. Noutbuk açıqdır? IP dəyişmiş ola bilər (DHCP): Linux-da \`hostname -I\` yaz, sonra: bash scripts/linux/deploy-from-mac.sh samir@YENİ-IP"
      ;;
  esac
fi
remote_state() { remote "grep -qs '^$1=' \"\$HOME/SecondBrain/.install-state\"" 2>/dev/null; }

FIRST=1
if remote_state installed; then FIRST=0; fi
if [ "$FIRST" = 0 ]; then info "Artıq qurulub — kodu yeniləyirəm"; fi

# --- 2. Bütün suallar başda --------------------------------------------------------
TG_TOKEN=""
TG_IDS=""
if [ "$FIRST" = 1 ]; then
  TG_TOKEN="$(env_value "$REPO/.env" TELEGRAM_BOT_TOKEN)"
  TG_IDS="$(env_value "$REPO/.env" ALLOWED_USER_IDS)"
  if [ -n "$TG_TOKEN" ]; then info "Telegram tokeni: bu Mac-ın .env-indən"; fi
fi

EMAIL_ADDR=""
EMAIL_PASS=""
ASK_EMAIL=0
if [ "$FORCE_EMAIL" = 1 ]; then ASK_EMAIL=1; fi
if [ "$FIRST" = 1 ] && [ "$YES" = 0 ]; then
  if ! remote "grep -Eqs '^EMAIL_PASSWORD=.+' \"\$HOME/SecondBrain/.env\"" 2>/dev/null; then ASK_EMAIL=1; fi
fi
if [ "$ASK_EMAIL" = 1 ]; then
  say "E-poçt (istəyə bağlı — boş burax, sonra əlavə edərsən)"
  info "App Password: myaccount.google.com/apppasswords (əvvəl 2 addımlı doğrulama açıq olmalıdır)"
  read -r -p "   Gmail ünvanı: " EMAIL_ADDR </dev/tty || EMAIL_ADDR=""
  if [ -n "$EMAIL_ADDR" ]; then
    read -r -s -p "   App Password (16 simvol, ekranda görünmür): " EMAIL_PASS </dev/tty || EMAIL_PASS=""
    printf '\n'
    EMAIL_PASS="$(printf '%s' "$EMAIL_PASS" | tr -d ' ')"
    if [ -z "$EMAIL_PASS" ]; then EMAIL_ADDR=""; fi
  fi
fi

MIGRATE=0
if [ -n "$VPS" ] && ! remote_state vps_migrated; then
  say "Köhnə server: $VPS"
  if vps true 2>/dev/null; then
    info "Bot orada dayandırılacaq, qeydlər bura köçürüləcək, bir nüsxə də bu Mac-ın backups/ qovluğuna."
    info "Keçid ~1-2 dəqiqə çəkir. Alınmasa VPS botu avtomatik geri qayıdır."
    if confirm "Razısan?"; then MIGRATE=1; else die "Dayandırıldı, heç nə dəyişmədi."; fi
  else
    warn "VPS-ə qoşulmaq olmadı ($VPS): qeydlər köçürülmür. Açar fərqlidirsə x yaz və --vps-key ~/.ssh/AÇAR əlavə et."
    warn "Bot orada hələ işləyirsə, eyni token ilə konflikt olacaq."
    confirm "Köçürmədən davam edim?" || die "Dayandırıldı, heç nə dəyişmədi."
    VPS=""
  fi
elif [ -z "$VPS" ] && [ "$FIRST" = 1 ]; then
  warn "--vps verilməyib: köhnə qeydlər köçürülmür. Bot başqa yerdə işləyirsə, token konflikti olacaq."
  confirm "Davam edim?" || die "Dayandırıldı, heç nə dəyişmədi."
fi

# --- 3. Kod --------------------------------------------------------------------------
say "Kod göndərilir"
git ls-files -co --exclude-standard -z \
  | while IFS= read -r -d '' f; do if [ -e "$f" ]; then printf '%s\0' "$f"; fi; done \
  | COPYFILE_DISABLE=1 tar --null -T - --no-xattrs --no-mac-metadata -czf - \
  | remote 'set -e; d="$HOME/SecondBrain"; mkdir -p "$d"; cd "$d"; rm -rf app migrations scripts tests docker; tar xzf -'
good "Kod noutbukdadır (~/SecondBrain)"

# Sirlər yalnız stdin ilə gedir: komanda sətrində (ps) görünmür.
if [ -n "$TG_TOKEN$TG_IDS$EMAIL_ADDR" ]; then
  {
    if [ -n "$TG_TOKEN" ]; then printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TG_TOKEN"; fi
    if [ -n "$TG_IDS" ]; then printf 'ALLOWED_USER_IDS=%s\n' "$TG_IDS"; fi
    if [ -n "$EMAIL_ADDR" ]; then
      printf 'EMAIL_ADDRESS=%s\nEMAIL_PASSWORD=%s\n' "$EMAIL_ADDR" "$EMAIL_PASS"
    fi
  } | remote 'umask 077; cat > "$HOME/SecondBrain/.env.seed"'
fi

# --- 4. Quraşdırma (bot hələ başlamır) ------------------------------------------------
remote_t 'cd "$HOME/SecondBrain" && bash scripts/linux/install.sh --no-start'

# --- 5. Keçid: köhnə bot dayanır, qeydlər köçür ------------------------------------------
if [ "$MIGRATE" = 1 ]; then
  say "Keçid: VPS-dəki bot dayandırılır"
  vps "cd $VPS_DIR && docker compose stop bot" >/dev/null 2>&1 || die "VPS botu dayanmadı."
  VPS_STOPPED=1
  mkdir -p backups
  DUMP="backups/vps_final_$(date +%Y%m%d_%H%M%S).sql.gz"
  vps "bash -c 'set -o pipefail; docker exec second_brain_db pg_dump -U postgres -d second_brain | gzip'" > "$DUMP" \
    || die "VPS-dən qeydləri götürmək alınmadı."
  gzip -t "$DUMP" || die "Dump pozuqdur: $DUMP"
  good "Nüsxə bu Mac-da: $DUMP"
  remote 'mkdir -p "$HOME/SecondBrain/backups"; cat > "$HOME/SecondBrain/backups/from_vps.sql.gz"' < "$DUMP"
  remote 'cd "$HOME/SecondBrain" && bash scripts/linux/install.sh --restore backups/from_vps.sql.gz'
fi

# --- 6. İşə sal + yoxla --------------------------------------------------------------------
remote 'cd "$HOME/SecondBrain" && bash scripts/linux/install.sh --start'
STARTED=1
if [ "$MIGRATE" = 1 ]; then
  remote 'printf "vps_migrated=%s\n" "$(date "+%F %T")" >> "$HOME/SecondBrain/.install-state"'
fi

# --- 7. Yanındakı xidmətlər toxunulmaz qaldımı ----------------------------------------------
JR="$(remote 'if systemctl list-unit-files jobradar-bot.service >/dev/null 2>&1; then systemctl is-active jobradar-bot jobradar-panel jobradar-tunnel 2>/dev/null | tr "\n" " "; fi' || true)"
if [ -n "$JR" ]; then
  case "$JR" in
    *inactive*|*failed*) warn "JobRadar xidmətləri: $JR— yoxla: ssh $TARGET systemctl status jobradar-bot" ;;
    *) good "JobRadar işləməyə davam edir (bot, panel, tunel aktivdir)" ;;
  esac
fi

say "Hazırdır"
info "Telegram-da botuna yaz: /health"
info "Yeniləmək: eyni əmr · E-poçt əlavə etmək: --email ilə"
info "Loqlar:  ssh $TARGET 'cd ~/SecondBrain && docker compose logs -f bot'"
info "Yoxlama: ssh $TARGET 'cd ~/SecondBrain && docker compose exec bot python scripts/doctor.py'"
if [ "$MIGRATE" = 1 ]; then
  info "VPS-dəki bot dayanıb (data orada qalır). Bir neçə gün sonra droplet-i silə bilərsən."
fi
