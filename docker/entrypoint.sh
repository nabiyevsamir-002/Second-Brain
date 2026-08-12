#!/usr/bin/env bash
# Konteyner başlayanda: əvvəlcə DB migration-larını tətbiq et, sonra CMD-ni işə sal.
# RUN_MIGRATIONS=0 versən migration-lar ötürülür (məs. test/debug üçün).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] alembic upgrade head ..."
  alembic upgrade head
fi

exec "$@"
