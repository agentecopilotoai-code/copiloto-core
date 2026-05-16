#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR=""
ALLOW_NON_EMPTY=false
RESTORE_OBJECTS=true

usage() {
  cat <<'MSG'
Uso: ./scripts/restore-local.sh <directorio-backup> [--allow-non-empty] [--skip-objects]

Restaura un backup generado por scripts/backup-local.sh en el stack local.
Por defecto exige una base limpia o recién inicializada con seeds para evitar sobreescribir datos accidentalmente.

Opciones:
  --allow-non-empty  Permite ejecutar pg_restore --clean sobre una DB con datos existentes.
  --skip-objects     No restaura knowledge-files.tar aunque exista.
MSG
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-non-empty)
      ALLOW_NON_EMPTY=true
      ;;
    --skip-objects)
      RESTORE_OBJECTS=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$BACKUP_DIR" ]]; then
        BACKUP_DIR="$1"
      else
        echo "Opción no reconocida: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [[ -z "$BACKUP_DIR" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f "$BACKUP_DIR/postgres.dump" || ! -f "$BACKUP_DIR/table-counts.tsv" ]]; then
  echo "Error: $BACKUP_DIR no parece un backup válido; faltan postgres.dump o table-counts.tsv." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Error: falta .env. Ejecuta ./scripts/bootstrap.sh o ./scripts/generate-local-secrets.sh primero." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Error: Docker Compose v2 es requerido para restaurar el stack local." >&2
  exit 1
fi

read_env() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1)}' .env | tail -n 1
}

DATABASE_URL_VALUE="$(read_env DATABASE_ADMIN_URL)"
if [[ -z "$DATABASE_URL_VALUE" ]]; then
  DATABASE_URL_VALUE="$(read_env DATABASE_URL)"
fi
if [[ -z "$DATABASE_URL_VALUE" ]]; then
  echo "Error: DATABASE_ADMIN_URL o DATABASE_URL deben estar definidos en .env." >&2
  exit 1
fi

# SEC-010: separar password del URL antes de pasarlo a psql/pg_restore para
# que NO aparezca en `ps aux`. El restore tarda minutos — ventana suficiente
# para que un proceso adversarial muestree el cmdline.
# shellcheck source=lib/postgres-url.sh
source "$(dirname "$0")/lib/postgres-url.sh"
parse_db_url "$DATABASE_URL_VALUE"
export PGPASSWORD="$DB_PASSWORD"

psql_app() {
  docker compose exec -T -e PGPASSWORD postgres psql "$DB_URL_NO_PASSWORD" -v ON_ERROR_STOP=1 "$@"
}

TABLE_COUNTS_SQL="
with counts(table_name, row_count) as (
  values
    ('tenants', (select count(*)::bigint from app.tenants)),
    ('tenant_settings', (select count(*)::bigint from app.tenant_settings)),
    ('tenant_channels', (select count(*)::bigint from app.tenant_channels)),
    ('contacts', (select count(*)::bigint from app.contacts)),
    ('conversations', (select count(*)::bigint from app.conversations)),
    ('messages', (select count(*)::bigint from app.messages)),
    ('message_status_events', (select count(*)::bigint from app.message_status_events)),
    ('knowledge_documents', (select count(*)::bigint from app.knowledge_documents)),
    ('knowledge_chunks', (select count(*)::bigint from app.knowledge_chunks)),
    ('domain_events', (select count(*)::bigint from app.domain_events)),
    ('audit_logs', (select count(*)::bigint from app.audit_logs))
)
select table_name || E'\t' || row_count from counts order by table_name;
"

NON_EMPTY_SQL="
select coalesce(sum(row_count), 0) from (
  select count(*)::bigint as row_count from app.contacts
  union all select count(*)::bigint from app.conversations
  union all select count(*)::bigint from app.messages
  union all select count(*)::bigint from app.message_status_events
  union all select count(*)::bigint from app.knowledge_documents
  union all select count(*)::bigint from app.knowledge_chunks
  union all select count(*)::bigint from app.domain_events
  union all select count(*)::bigint from app.audit_logs
) s;
"

if [[ "$ALLOW_NON_EMPTY" != true ]]; then
  existing_rows="$(psql_app -Atc "$NON_EMPTY_SQL" 2>/dev/null || echo unknown)"
  if [[ "$existing_rows" != "0" ]]; then
    cat >&2 <<MSG
Error: la DB local no está limpia ($existing_rows filas en tablas operativas críticas).
Para desarrollo, recrea volúmenes antes de restaurar:
  ./scripts/bootstrap.sh --reset --yes --skip-smoke
  ./scripts/restore-local.sh $BACKUP_DIR

Si sabes que quieres sobreescribir el contenido actual, usa:
  ./scripts/restore-local.sh $BACKUP_DIR --allow-non-empty
MSG
    exit 1
  fi
fi

echo "==> Restaurando PostgreSQL desde $BACKUP_DIR/postgres.dump"
docker compose exec -T -e PGPASSWORD postgres pg_restore \
  --dbname="$DB_URL_NO_PASSWORD" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error < "$BACKUP_DIR/postgres.dump"

if [[ "$RESTORE_OBJECTS" == true && -f "$BACKUP_DIR/knowledge-files.tar" ]]; then
  if docker compose ps --services --filter status=running | grep -Fxq api; then
    echo "==> Restaurando objetos locales de Knowledge Storage"
    docker compose exec -T api sh -c 'KNOWLEDGE_PATH="${KNOWLEDGE_STORAGE_LOCAL_PATH:-/app/data/knowledge}"; test -n "$KNOWLEDGE_PATH" && test "$KNOWLEDGE_PATH" != "/" && mkdir -p "$KNOWLEDGE_PATH" && find "$KNOWLEDGE_PATH" -mindepth 1 -maxdepth 1 -exec rm -rf {} +'
    docker compose exec -T api sh -c 'KNOWLEDGE_PATH="${KNOWLEDGE_STORAGE_LOCAL_PATH:-/app/data/knowledge}"; cd "$KNOWLEDGE_PATH" && tar -xf -' < "$BACKUP_DIR/knowledge-files.tar"
  else
    echo "Aviso: servicio api no está corriendo; se omitió restore de knowledge-files.tar." >&2
  fi
fi

echo "==> Validando conteos post-restore"
RESTORED_COUNTS_FILE="$(mktemp)"
trap 'rm -f "$RESTORED_COUNTS_FILE"' EXIT
psql_app -Atc "$TABLE_COUNTS_SQL" > "$RESTORED_COUNTS_FILE"
if ! diff -u "$BACKUP_DIR/table-counts.tsv" "$RESTORED_COUNTS_FILE"; then
  echo "Error: los conteos post-restore no coinciden con el backup." >&2
  exit 1
fi

echo "Restore local validado: conteos, tenants, documentos, chunks y audit logs coinciden."
