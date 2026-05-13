#!/usr/bin/env bash
# TASK-0064 — Entrypoint del backup-worker.
#
# cron no hereda el environment del proceso padre, así que volcamos las
# variables relevantes a /etc/cron.d/copilotoia-env y la crontab hace
# `. /etc/cron.d/copilotoia-env` antes de invocar el script.
set -euo pipefail

ENV_FILE="/etc/cron.d/copilotoia-env"

: >"$ENV_FILE"
for var in BACKUP_S3_BUCKET BACKUP_ENV BACKUP_S3_ENDPOINT \
           BACKUP_GPG_RECIPIENT BACKUP_GPG_PUBKEY_PATH \
           BACKUP_RETENTION_DAYS \
           DATABASE_ADMIN_URL POSTGRES_HOST POSTGRES_SUPERUSER_URL \
           AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION \
           AWS_REGION; do
  if [[ -n "${!var:-}" ]]; then
    printf 'export %s=%q\n' "$var" "${!var}" >>"$ENV_FILE"
  fi
done
chmod 0600 "$ENV_FILE"

touch /var/log/copilotoia-backup.log
mkdir -p /app/.secrets

# Import GPG keys at boot so cron jobs find them ready.
if [[ -f "${BACKUP_GPG_PUBKEY_PATH:-/app/.secrets/backup_gpg_pubkey.asc}" ]]; then
  gpg --batch --quiet --import "${BACKUP_GPG_PUBKEY_PATH:-/app/.secrets/backup_gpg_pubkey.asc}" >/dev/null 2>&1 || true
fi
if [[ -f "/app/.secrets/backup_gpg_privkey.asc" ]]; then
  gpg --batch --quiet --import "/app/.secrets/backup_gpg_privkey.asc" >/dev/null 2>&1 || true
fi

echo "backup-worker booted at $(date -u +%FT%TZ) — schedule: daily 03:00 UTC / verify Sun 04:00 UTC" \
  >>/var/log/copilotoia-backup.log

# Start cron in the foreground and tail the log so docker can stream it.
cron -f &
CRON_PID=$!
tail -F /var/log/copilotoia-backup.log &
trap 'kill -TERM "$CRON_PID" 2>/dev/null || true' SIGTERM SIGINT
wait "$CRON_PID"
