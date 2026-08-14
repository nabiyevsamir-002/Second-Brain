#!/usr/bin/env bash
# Backup-verify — ən son pg_dump backup-ının həqiqətən BƏRPA olunduğunu yoxlayır.
# İzolyasiya: müvəqqəti AYRI Postgres konteynerində bərpa edir — canlı DB-yə TOXUNMUR
# (host port açmır, öz volume-u yoxdur, sonda silinir).
#
# İstifadə:
#   ./scripts/verify_backup.sh                 # ən son backup-ı yoxla
#   ./scripts/verify_backup.sh path/to/x.sql.gz  # konkret faylı yoxla
#
# Exit code: 0 = UĞURLU (bərpa + struktur tam), 1 = UĞURSUZ.
# Cron nümunəsi (həftəlik, backup-dan sonra):
#   30 3 * * 0 cd /root/AI-Assistant && ./scripts/verify_backup.sh >> ./backups/verify.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
IMAGE="${VERIFY_IMAGE:-pgvector/pgvector:pg16}"
TMP_CONTAINER="second_brain_verify_$$"
DB_USER="postgres"
DB_NAME="second_brain"
DB_PASS="postgres"

# --- 1) Yoxlanacaq backup faylını seç -------------------------------------
if [[ $# -ge 1 ]]; then
  BACKUP_FILE="$1"
else
  BACKUP_FILE="$(ls -1t "$BACKUP_DIR"/second_brain_*.sql.gz 2>/dev/null | head -n1 || true)"
fi

if [[ -z "${BACKUP_FILE:-}" || ! -f "$BACKUP_FILE" ]]; then
  echo "❌ Backup tapılmadı ($BACKUP_DIR/second_brain_*.sql.gz)."
  echo "   Əvvəlcə ./scripts/backup.sh işlət, ya da faylı arqument kimi ver."
  exit 1
fi
echo "🔎 Yoxlanılan backup: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# --- 2) Hər halda müvəqqəti konteyneri təmizlə ----------------------------
cleanup() { docker rm -f "$TMP_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# --- 3) Müvəqqəti Postgres qaldır (host port YOX — yalnız docker exec) -----
echo "🐳 Müvəqqəti Postgres qaldırılır ($TMP_CONTAINER)…"
docker run -d --name "$TMP_CONTAINER" \
  -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_PASSWORD="$DB_PASS" \
  -e POSTGRES_DB="$DB_NAME" \
  "$IMAGE" >/dev/null

# --- 4) Postgres hazır olana qədər gözlə ----------------------------------
echo -n "⏳ Postgres hazırlanır"
ready=0
for _ in $(seq 1 30); do
  if docker exec "$TMP_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    ready=1; break
  fi
  echo -n "."; sleep 1
done
echo
if [[ "$ready" != "1" ]]; then
  echo "❌ Müvəqqəti Postgres 30s ərzində hazır olmadı."
  exit 1
fi

# --- 5) Backup-ı bərpa et (ilk xətada dayan) ------------------------------
echo "♻️  Backup bərpa olunur…"
RESTORE_LOG="$(mktemp)"
if ! gunzip -c "$BACKUP_FILE" \
    | docker exec -i "$TMP_CONTAINER" \
        psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
    >"$RESTORE_LOG" 2>&1; then
  echo "❌ Bərpa XƏTA verdi. Son sətirlər:"
  tail -n 20 "$RESTORE_LOG"
  rm -f "$RESTORE_LOG"
  exit 1
fi
rm -f "$RESTORE_LOG"

# --- 6) Struktur + oxunabilirlik yoxlamaları ------------------------------
echo "🔬 Yoxlamalar aparılır…"
run_sql() { docker exec -i "$TMP_CONTAINER" psql -tA -U "$DB_USER" -d "$DB_NAME" -c "$1" 2>/dev/null; }

fail=0

# pgvector extension bərpa olundu?
if [[ "$(run_sql "SELECT 1 FROM pg_extension WHERE extname='vector';")" == "1" ]]; then
  echo "  ✅ pgvector extension mövcuddur"
else
  echo "  ❌ pgvector extension YOXDUR"; fail=1
fi

# Gözlənilən bütün cədvəllər var?
for t in users notes messages tasks reminders note_links usage_log; do
  if [[ "$(run_sql "SELECT to_regclass('public.$t') IS NOT NULL;")" == "t" ]]; then
    echo "  ✅ cədvəl: $t"
  else
    echo "  ❌ cədvəl yoxdur: $t"; fail=1
  fi
done

# notes cədvəli oxunur? (sətir sayı — məlumat qorunub?)
notes_cnt="$(run_sql "SELECT count(*) FROM notes;")"
if [[ "$notes_cnt" =~ ^[0-9]+$ ]]; then
  echo "  ✅ notes oxunur (sətir sayı: $notes_cnt)"
else
  echo "  ❌ notes cədvəli oxunmadı"; fail=1
fi

# embedding sütunu vector(1536)? (pgvector-də atttypmod = ölçü)
dim="$(run_sql "SELECT atttypmod FROM pg_attribute WHERE attrelid='public.notes'::regclass AND attname='embedding';")"
if [[ "$dim" == "1536" ]]; then
  echo "  ✅ notes.embedding vector(1536)"
elif [[ -n "${dim:-}" ]]; then
  echo "  ⚠️  notes.embedding ölçüsü gözlənilməyən: $dim (gözlənilən 1536)"
fi

# --- 7) Nəticə ------------------------------------------------------------
echo
if [[ "$fail" == "0" ]]; then
  echo "✅ BACKUP-VERIFY UĞURLU — backup bərpa olunur və struktur tamdır."
  exit 0
else
  echo "❌ BACKUP-VERIFY UĞURSUZ — yuxarıdakı ❌ sətirlərinə bax."
  exit 1
fi
