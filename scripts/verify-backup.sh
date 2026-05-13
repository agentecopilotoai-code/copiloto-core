#!/usr/bin/env bash
# TASK-0064 — Verificación periódica de backups en cloud.
#
# Descarga el último dump cifrado del bucket S3, lo descifra con la clave
# privada GPG, restaura sobre una base efímera `copilotoia_verify`, corre 3
# sanity checks (count de tenants, conversations, messages) y reporta:
#   * éxito → `audit_logs(action='backup.verified')`
#   * fallo → `operator_alerts(kind='backup_failure')` + audit log con la causa.
#
# Diseñado para correr semanalmente (cron `0 4 * * 0` en docker-compose) o
# manualmente en el host (host: GPG_PRIVATE_KEY_PATH apunta al keyring local).
#
# Variables requeridas:
#   BACKUP_S3_BUCKET            bucket origen.
#   BACKUP_ENV                  prefijo de ambiente.
#   DATABASE_ADMIN_URL          conexión administrativa para escribir el run.
#   POSTGRES_HOST               host de PG (default 'postgres').
#   POSTGRES_SUPERUSER_URL      URL para crear/dropear la DB efímera
#                               (rol con CREATEDB; default deriva del admin url
#                               apuntando a la DB `postgres`).
#
# Variables opcionales:
#   BACKUP_S3_ENDPOINT          endpoint custom (MinIO local).
#   BACKUP_GPG_PRIVATE_KEY_PATH ruta al .asc privado (sólo para CI/host).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'MSG'
Uso: ./scripts/verify-backup.sh [--date YYYY-MM-DD]

Descarga el último backup (o el del día indicado), restaura sobre
copilotoia_verify y reporta el resultado a audit_logs / operator_alerts.
MSG
}

TARGET_DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      TARGET_DATE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opción no reconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

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

for tool in aws gpg pg_restore psql createdb dropdb sha256sum; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: falta dependencia '$tool' en el PATH." >&2
    exit 2
  fi
done

POSTGRES_SUPERUSER_URL="${POSTGRES_SUPERUSER_URL:-${DATABASE_ADMIN_URL%/*}/postgres}"
VERIFY_DB="copilotoia_verify"

AWS_CLI_ARGS=()
if [[ -n "${BACKUP_S3_ENDPOINT:-}" ]]; then
  AWS_CLI_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
fi

if [[ -z "$TARGET_DATE" ]]; then
  TARGET_DATE="$(date -u +%Y-%m-%d)"
fi
S3_KEY="backups/${BACKUP_ENV}/${TARGET_DATE}/db.dump.gpg"
S3_URI="s3://${BACKUP_S3_BUCKET}/${S3_KEY}"

WORK_DIR="$(mktemp -d -t copilotoia-verify-XXXXXX)"
trap 'rm -rf "$WORK_DIR"; dropdb -h "${POSTGRES_HOST:-postgres}" -U postgres --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true' EXIT

ENC_PATH="$WORK_DIR/db.dump.gpg"
DUMP_PATH="$WORK_DIR/db.dump"

RUN_ID="$(psql "$DATABASE_ADMIN_URL" -Atc "select gen_random_uuid()")"

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -v evidence="$S3_URI" -Atc "
  insert into app.backup_runs (id, kind, status, evidence_path, metadata)
  values (
    :'run_id'::uuid,
    'cloud_verify',
    'running',
    :'evidence',
    jsonb_build_object('target_date','${TARGET_DATE}','env','${BACKUP_ENV}')
  )
" >/dev/null

report_failure() {
  local err_msg="$1"
  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" -Atc "
    update app.backup_runs
       set status='failed', finished_at=now(), error=:'err_msg'
     where id=:'run_id'::uuid
  " >/dev/null || true

  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" \
       -v evidence="$S3_URI" -v env="$BACKUP_ENV" -Atc "
    insert into app.operator_alerts (tenant_id, kind, payload)
    values (
      null,
      'backup_failure',
      jsonb_build_object(
        'run_id', :'run_id',
        'env', :'env',
        'evidence_path', :'evidence',
        'phase', 'verify',
        'error', :'err_msg'
      )
    )
  " >/dev/null || true

  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" -Atc "
    insert into app.audit_logs (tenant_id, actor_type, action, entity_type, entity_id, metadata)
    values (
      null,
      'service',
      'backup.verify_failed',
      'backup_runs',
      :'run_id',
      jsonb_build_object('error', :'err_msg', 'evidence_path', '${S3_URI}')
    )
  " >/dev/null || true

  echo "Backup verify FAILED: $err_msg" >&2
  exit 1
}

echo "==> Descargando $S3_URI"
if ! aws "${AWS_CLI_ARGS[@]}" s3 cp "$S3_URI" "$ENC_PATH" --only-show-errors; then
  report_failure "s3_download_failed"
fi

if [[ ! -s "$ENC_PATH" ]]; then
  report_failure "downloaded_artifact_empty"
fi

REMOTE_SHA="$(aws "${AWS_CLI_ARGS[@]}" s3api head-object \
  --bucket "$BACKUP_S3_BUCKET" --key "$S3_KEY" \
  --query 'Metadata.sha256' --output text 2>/dev/null || echo "")"
LOCAL_SHA="$(sha256sum "$ENC_PATH" | awk '{print $1}')"
if [[ -n "$REMOTE_SHA" && "$REMOTE_SHA" != "None" && "$REMOTE_SHA" != "$LOCAL_SHA" ]]; then
  report_failure "sha256_mismatch:remote=${REMOTE_SHA}:local=${LOCAL_SHA}"
fi

echo "==> Descifrando con GPG"
if ! gpg --batch --yes --quiet --output "$DUMP_PATH" --decrypt "$ENC_PATH"; then
  report_failure "gpg_decrypt_failed"
fi

if [[ ! -s "$DUMP_PATH" ]]; then
  report_failure "decrypted_dump_empty"
fi

PG_HOST="${POSTGRES_HOST:-postgres}"

echo "==> Recreando DB efímera ${VERIFY_DB}"
dropdb -h "$PG_HOST" -U postgres --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true
if ! createdb -h "$PG_HOST" -U postgres "$VERIFY_DB"; then
  report_failure "createdb_failed"
fi

VERIFY_URL="postgres://postgres@${PG_HOST}/${VERIFY_DB}"

echo "==> Restaurando dump"
if ! pg_restore --dbname="$VERIFY_URL" --no-owner --no-privileges --exit-on-error "$DUMP_PATH" >/dev/null 2>"$WORK_DIR/restore.err"; then
  report_failure "pg_restore_failed:$(tail -c 200 "$WORK_DIR/restore.err" | tr '\n' ' ')"
fi

echo "==> Sanity checks"
SANITY_SQL="
select 'tenants', count(*) from app.tenants
union all select 'conversations', count(*) from app.conversations
union all select 'messages', count(*) from app.messages
"
SANITY_OUT="$(psql "$VERIFY_URL" -Atc "$SANITY_SQL" 2>"$WORK_DIR/sanity.err" || true)"
if [[ -z "$SANITY_OUT" ]]; then
  report_failure "sanity_query_failed:$(tail -c 200 "$WORK_DIR/sanity.err" | tr '\n' ' ')"
fi

TENANTS_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="tenants" {print $2}')"
CONVERSATIONS_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="conversations" {print $2}')"
MESSAGES_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="messages" {print $2}')"

# Schema fundamentally requires at least 1 tenant for a meaningful backup.
if [[ -z "$TENANTS_COUNT" || "$TENANTS_COUNT" -lt 1 ]]; then
  report_failure "sanity_check_failed:tenants_count_is_${TENANTS_COUNT}"
fi

SIZE_BYTES="$(wc -c <"$ENC_PATH" | tr -d ' ')"

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -Atc "
  update app.backup_runs
     set status='ok',
         finished_at=now(),
         sha256='${LOCAL_SHA}',
         size_bytes=${SIZE_BYTES},
         metadata = metadata || jsonb_build_object(
           'tenants_count', ${TENANTS_COUNT},
           'conversations_count', ${CONVERSATIONS_COUNT:-0},
           'messages_count', ${MESSAGES_COUNT:-0}
         )
   where id=:'run_id'::uuid
" >/dev/null

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -Atc "
  insert into app.audit_logs (tenant_id, actor_type, action, entity_type, entity_id, metadata)
  values (
    null,
    'service',
    'backup.verified',
    'backup_runs',
    :'run_id'::uuid,
    jsonb_build_object(
      'evidence_path','${S3_URI}',
      'sha256','${LOCAL_SHA}',
      'tenants_count', ${TENANTS_COUNT},
      'conversations_count', ${CONVERSATIONS_COUNT:-0},
      'messages_count', ${MESSAGES_COUNT:-0}
    )
  )
" >/dev/null

echo "Backup verify OK: tenants=${TENANTS_COUNT} conversations=${CONVERSATIONS_COUNT:-0} messages=${MESSAGES_COUNT:-0}"
