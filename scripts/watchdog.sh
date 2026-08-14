#!/usr/bin/env bash
# Host watchdog (Phase 6.1) — 3-cü tərəf İSTƏMİRSƏNSƏ alternativ monitoring.
# Konteyner işləmirsə birbaşa Telegram Bot API ilə SƏNƏ DM atır.
# Host cron ilə işlədilir (VPS-də), Docker-dən KƏNARDA:
#   */5 * * * * cd /root/AI-Assistant && ./scripts/watchdog.sh >> ./backups/watchdog.log 2>&1
#
# Qeyd: VPS-in ÖZÜ düşərsə bu skript də düşür → tam örtük üçün healthcheck_url
# (dead man's switch, healthchecks.io) daha yaxşıdır. Bu, imzasız/ödənişsiz variantdır.
set -euo pipefail

CONTAINER="${BOT_CONTAINER:-second_brain_bot}"
ENV_FILE="${ENV_FILE:-.env}"
STATE="${WATCHDOG_STATE:-/tmp/watchdog_${CONTAINER}_down}"
ALERT_COOLDOWN=3600   # eyni nasazlıq üçün təkrar alert arası minimum (san) — spam-a qarşı

# .env-dən token + chat id (ALLOWED_USER_IDS ilk dəyəri).
TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
CHAT="$(grep -E '^ALLOWED_USER_IDS=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | cut -d, -f1 || true)"

send() {
  [ -n "$TOKEN" ] && [ -n "$CHAT" ] || { echo "⚠️ TOKEN/CHAT tapılmadı ($ENV_FILE)"; return 0; }
  curl -s -m 15 "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d chat_id="$CHAT" -d text="$1" >/dev/null || true
}

STATUS="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo missing)"

if [ "$STATUS" != "running" ]; then
  # Nasazlıq — cooldown keçibsə (və ya ilk dəfədirsə) alert at.
  now="$(date +%s)"
  last=0
  [ -f "$STATE" ] && last="$(cat "$STATE" 2>/dev/null || echo 0)"
  if [ $((now - last)) -ge "$ALERT_COOLDOWN" ]; then
    send "🔴 second_brain_bot DÜŞÜB (status=${STATUS}) — $(hostname) $(date '+%Y-%m-%d %H:%M')"
    echo "$now" > "$STATE"
  fi
  echo "DOWN status=$STATUS"
  exit 1
fi

# İşləyir — əvvəl düşmüşdüsə bərpa bildirişi göndər.
if [ -f "$STATE" ]; then
  send "🟢 second_brain_bot yenidən işləyir — $(hostname) $(date '+%Y-%m-%d %H:%M')"
  rm -f "$STATE"
fi
echo "OK status=running"
