#!/usr/bin/env bash
# Gecə pg_dump backup — notes qorunur. Nightly cron ilə çağırılmaq üçün.
# İstifadə:  ./scripts/backup.sh
# Bərpa:     gunzip -c backups/second_brain_XXXX.sql.gz | \
#              docker exec -i second_brain_db psql -U postgres -d second_brain
set -euo pipefail

CONTAINER="${DB_CONTAINER:-second_brain_db}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-second_brain}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/second_brain_${TS}.sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$OUT"
echo "✅ Backup: $OUT ($(du -h "$OUT" | cut -f1))"

# Köhnə backup-ları təmizlə (retention).
find "$BACKUP_DIR" -name 'second_brain_*.sql.gz' -type f -mtime +"$RETENTION_DAYS" -delete
echo "🧹 ${RETENTION_DAYS} gündən köhnə backup-lar silindi."
