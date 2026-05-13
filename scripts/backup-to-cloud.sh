#!/usr/bin/env bash
# TASK-0064 — Backup automatizado a cloud con verificación periódica.
#
# Hace un `pg_dump --format=custom` del cluster operacional, lo cifra con la
# clave pública GPG ubicada en `.secrets/backup_gpg_pubkey.asc`, lo sube a
# `s3://<bucket>/backups/<env>/<YYYY-MM-DD>/db.dump.gpg`, registra el run en
# `app.backup_runs` y aplica la política de retención (30 daily + 12 mensuales).
#
# Diseñado para correr dentro del contenedor `backup-worker` definido en
# docker-compose, o desde el host con AWS_CLI + GPG instalados localmente.
#
# Variables de entorno requeridas:
#   BACKUP_S3_BUCKET            bucket destino (sin s3://).
#   BACKUP_ENV                  prefijo de ambiente (`prod`, `staging`, …).
#   DATABASE_ADMIN_URL          conexión administrativa a PostgreSQL.
#   BACKUP_GPG_RECIPIENT        fingerprint o email de la clave pública GPG.
#
# Variables opcionales:
#   BACKUP_S3_ENDPOINT          endpoint custom (MinIO local: http://minio:9000).
#   AWS_ACCESS_KEY_ID/_SECRET   credenciales S3 (fallback a IAM profile).
#   BACKUP_RETENTION_DAYS       días de retención (default 30).
#   BACKUP_GPG_PUBKEY_PATH      ruta a la clave pública (default
#                               `.secrets/backup_gpg_pubkey.asc`).
#   BACKUP_RUN_ID               UUID externo (si no se pasa, lo genera SQL).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'MSG'
Uso: ./scripts/backup-to-cloud.sh

Variables requeridas: BACKUP_S3_BUCKET, BACKUP_ENV, DATABASE_ADMIN_URL,
BACKUP_GPG_RECIPIENT.

El script:
  1. genera un dump con pg_dump --format=custom,
  2. lo cifra con GPG (recipient public key),
  3. lo sube a s3://<bucket>/backups/<env>/<YYYY-MM-DD>/db.dump.gpg,
  4. registra metadata en app.backup_runs (sha256, size, duration),
  5. aplica retención: 30 backups diarios + 12 mensuales (el primero de mes
     se renombra db.dump.gpg.monthly para no ser purgado).
MSG
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "Error: variable $name es requerida." >&2
    exit 2
  fi
}

require_var BACKUP_S3_BUCKET
require_var BACKUP_ENV
require_var DATABASE_ADMIN_URL
require_var BACKUP_GPG_RECIPIENT

BACKUP_GPG_PUBKEY_PATH="${BACKUP_GPG_PUBKEY_PATH:-.secrets/backup_gpg_pubkey.asc}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

for tool in pg_dump gpg sha256sum aws psql; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: falta dependencia '$tool' en el PATH." >&2
    exit 2
  fi
done

if [[ ! -f "$BACKUP_GPG_PUBKEY_PATH" ]]; then
  echo "Error: clave pública GPG no encontrada en $BACKUP_GPG_PUBKEY_PATH." >&2
  echo "  Documenta el procedimiento de rotación en docs/backup-policy.md." >&2
  exit 2
fi

BACKUP_DATE_UTC="$(date -u +%Y-%m-%d)"
BACKUP_TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
S3_KEY="backups/${BACKUP_ENV}/${BACKUP_DATE_UTC}/db.dump.gpg"
S3_URI="s3://${BACKUP_S3_BUCKET}/${S3_KEY}"
WORK_DIR="$(mktemp -d -t copilotoia-backup-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

DUMP_PATH="$WORK_DIR/db.dump"
ENC_PATH="$WORK_DIR/db.dump.gpg"

AWS_CLI_ARGS=()
if [[ -n "${BACKUP_S3_ENDPOINT:-}" ]]; then
  AWS_CLI_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
fi

# Validate S3 URI shape early — defends against typos that would silently
# upload to a wrong bucket prefix and break restore.
if [[ ! "$S3_URI" =~ ^s3://[a-z0-9][a-z0-9.-]+/backups/[A-Za-z0-9_-]+/[0-9]{4}-[0-9]{2}-[0-9]{2}/db\.dump\.gpg$ ]]; then
  echo "Error: S3 path inesperado: $S3_URI" >&2
  exit 2
fi

psql_exec() {
  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 "$@"
}

# Import the GPG public key idempotently (no-op if already in keyring).
gpg --batch --quiet --import "$BACKUP_GPG_PUBKEY_PATH" >/dev/null 2>&1 || true

RUN_ID="${BACKUP_RUN_ID:-$(psql_exec -Atc "select gen_random_uuid()")}"

psql_exec -Atc "
  insert into app.backup_runs (id, kind, status, evidence_path, metadata)
  values (
    '${RUN_ID}'::uuid,
    'cloud_dump',
    'running',
    '${S3_URI}',
    jsonb_build_object(
      'env', '${BACKUP_ENV}',
      'started_ts_utc', '${BACKUP_TS_UTC}'
    )
  )
" >/dev/null

cleanup_failure() {
  local err_msg="$1"
  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" -Atc "
    update app.backup_runs
       set status='failed',
           finished_at=now(),
           error=:'err_msg',
           metadata = metadata || jsonb_build_object('failed_ts_utc', to_char(now() at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))
     where id=:'run_id'::uuid
  " >/dev/null || true
  insert_system_alert "$err_msg" || true
}

insert_system_alert() {
  local err_msg="$1"
  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" \
       -v env="$BACKUP_ENV" -v evidence="$S3_URI" -Atc "
    insert into app.operator_alerts (tenant_id, kind, payload)
    values (
      null,
      'backup_failure',
      jsonb_build_object(
        'run_id', :'run_id',
        'env', :'env',
        'evidence_path', :'evidence',
        'error', :'err_msg'
      )
    )
  " >/dev/null
}

START_TS=$(date +%s)

echo "==> pg_dump (format=custom) → $DUMP_PATH"
if ! pg_dump "$DATABASE_ADMIN_URL" --format=custom --no-owner --no-privileges --file "$DUMP_PATH"; then
  cleanup_failure "pg_dump_failed"
  exit 1
fi

if [[ ! -s "$DUMP_PATH" ]]; then
  cleanup_failure "pg_dump_empty"
  exit 1
fi

echo "==> Cifrando con GPG ($BACKUP_GPG_RECIPIENT)"
if ! gpg --batch --yes --trust-model always \
      --recipient "$BACKUP_GPG_RECIPIENT" \
      --output "$ENC_PATH" \
      --encrypt "$DUMP_PATH"; then
  cleanup_failure "gpg_encrypt_failed"
  exit 1
fi

SIZE_BYTES=$(wc -c <"$ENC_PATH" | tr -d ' ')
SHA256_HEX=$(sha256sum "$ENC_PATH" | awk '{print $1}')

echo "==> Subiendo a $S3_URI ($SIZE_BYTES bytes, sha256=$SHA256_HEX)"
if ! aws "${AWS_CLI_ARGS[@]}" s3 cp "$ENC_PATH" "$S3_URI" \
      --metadata "sha256=$SHA256_HEX,run-id=$RUN_ID,env=$BACKUP_ENV" \
      --only-show-errors; then
  cleanup_failure "s3_upload_failed"
  exit 1
fi

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo "==> Marcando run como ok"
psql_exec -Atc "
  update app.backup_runs
     set status='ok',
         finished_at=now(),
         sha256='${SHA256_HEX}',
         size_bytes=${SIZE_BYTES},
         duration_seconds=${DURATION},
         metadata = metadata || jsonb_build_object('uploaded_ts_utc', to_char(now() at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))
   where id='${RUN_ID}'::uuid
" >/dev/null

# Monthly preservation: copy the first backup of each month as
# db.dump.gpg.monthly to bypass the 30-day purge below.
DAY_OF_MONTH=$(date -u +%d)
if [[ "$DAY_OF_MONTH" == "01" ]]; then
  MONTHLY_KEY="backups/${BACKUP_ENV}/monthly/${BACKUP_DATE_UTC}/db.dump.gpg.monthly"
  echo "==> Copiando snapshot mensual a s3://${BACKUP_S3_BUCKET}/${MONTHLY_KEY}"
  aws "${AWS_CLI_ARGS[@]}" s3 cp "$S3_URI" "s3://${BACKUP_S3_BUCKET}/${MONTHLY_KEY}" --only-show-errors
fi

# Retention: list daily prefixes older than BACKUP_RETENTION_DAYS and delete.
# The monthly snapshots live under a different prefix and are not purged here.
echo "==> Aplicando retención diaria (>${BACKUP_RETENTION_DAYS}d)"
CUTOFF_EPOCH=$(date -u -d "${BACKUP_RETENTION_DAYS} days ago" +%s 2>/dev/null || date -u -v -"${BACKUP_RETENTION_DAYS}"d +%s)

aws "${AWS_CLI_ARGS[@]}" s3 ls "s3://${BACKUP_S3_BUCKET}/backups/${BACKUP_ENV}/" \
  | awk '{print $2}' | tr -d '/' \
  | while IFS= read -r prefix; do
    if [[ -z "$prefix" || "$prefix" == "monthly" ]]; then
      continue
    fi
    # Only consider valid YYYY-MM-DD prefixes.
    if [[ ! "$prefix" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
      continue
    fi
    prefix_epoch=$(date -u -d "$prefix" +%s 2>/dev/null || date -u -j -f "%Y-%m-%d" "$prefix" +%s 2>/dev/null || echo 0)
    if [[ "$prefix_epoch" -gt 0 && "$prefix_epoch" -lt "$CUTOFF_EPOCH" ]]; then
      echo "  purge s3://${BACKUP_S3_BUCKET}/backups/${BACKUP_ENV}/${prefix}/"
      aws "${AWS_CLI_ARGS[@]}" s3 rm "s3://${BACKUP_S3_BUCKET}/backups/${BACKUP_ENV}/${prefix}/" --recursive --only-show-errors || true
    fi
  done

echo "Backup cloud listo: $S3_URI ($DURATION s, $SIZE_BYTES bytes)"
