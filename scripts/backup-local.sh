#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_ROOT="${BACKUP_ROOT:-backups/local}"
BACKUP_DIR="${1:-$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)}"

usage() {
  cat <<'MSG'
Uso: ./scripts/backup-local.sh [directorio-backup]

Crea un respaldo local verificable de PostgreSQL y de objetos de Knowledge Storage.
Requiere el stack Docker Compose levantado con postgres y api disponibles.

Artefactos generados:
  postgres.dump             dump lógico custom de PostgreSQL
  table-counts.tsv          conteos de validación post-restore
  knowledge-documents.tsv   manifiesto DB de documentos/objetos de conocimiento
  knowledge-files.tar       archivos del volumen local de conocimiento, si existen
  knowledge-files.sha256    checksums de archivos del volumen local, si existen
  manifest.json             resumen auditable del backup
MSG
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f .env ]]; then
  echo "Error: falta .env. Ejecuta ./scripts/bootstrap.sh o ./scripts/generate-local-secrets.sh primero." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Error: Docker Compose v2 es requerido para respaldar los servicios locales." >&2
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

# SEC-010: separar password del URL antes de pasarlo a psql/pg_dump para que
# NO aparezca en `ps aux`. El dump tarda minutos — ventana suficiente para
# que un proceso adversarial muestree el cmdline.
# shellcheck source=lib/postgres-url.sh
source "$(dirname "$0")/lib/postgres-url.sh"
parse_db_url "$DATABASE_URL_VALUE"
export PGPASSWORD="$DB_PASSWORD"

mkdir -p "$BACKUP_DIR"

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

KNOWLEDGE_DOCUMENTS_SQL="
select concat_ws(E'\t',
  tenant_id::text,
  id::text,
  coalesce(title, ''),
  coalesce(status, ''),
  coalesce(source_uri, ''),
  coalesce(checksum, ''),
  coalesce(metadata->>'storage_backend', ''),
  coalesce(metadata->>'bucket', ''),
  coalesce(metadata->>'object_key', '')
)
from app.knowledge_documents
order by tenant_id, id;
"

echo "==> Creando dump PostgreSQL en $BACKUP_DIR/postgres.dump"
docker compose exec -T -e PGPASSWORD postgres pg_dump "$DB_URL_NO_PASSWORD" \
  --format=custom \
  --no-owner \
  --no-privileges \
  > "$BACKUP_DIR/postgres.dump"

if [[ ! -s "$BACKUP_DIR/postgres.dump" ]]; then
  echo "Error: pg_dump produjo un archivo vacío en $BACKUP_DIR/postgres.dump." >&2
  exit 1
fi

echo "==> Guardando conteos de validación"
psql_app -Atc "$TABLE_COUNTS_SQL" > "$BACKUP_DIR/table-counts.tsv"

psql_app -Atc "$KNOWLEDGE_DOCUMENTS_SQL" > "$BACKUP_DIR/knowledge-documents.tsv"

echo "==> Exportando objetos locales de Knowledge Storage, si existen"
if docker compose ps --services --filter status=running | grep -Fxq api; then
  if docker compose exec -T api sh -c 'KNOWLEDGE_PATH="${KNOWLEDGE_STORAGE_LOCAL_PATH:-/app/data/knowledge}"; test -d "$KNOWLEDGE_PATH"'; then
    docker compose exec -T api sh -c 'KNOWLEDGE_PATH="${KNOWLEDGE_STORAGE_LOCAL_PATH:-/app/data/knowledge}"; cd "$KNOWLEDGE_PATH" && tar -cf - .' > "$BACKUP_DIR/knowledge-files.tar"
    docker compose exec -T api sh -c 'KNOWLEDGE_PATH="${KNOWLEDGE_STORAGE_LOCAL_PATH:-/app/data/knowledge}"; cd "$KNOWLEDGE_PATH" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum' > "$BACKUP_DIR/knowledge-files.sha256"
  else
    : > "$BACKUP_DIR/knowledge-files.sha256"
  fi
else
  echo "Aviso: servicio api no está corriendo; se omitió tar del volumen local de conocimiento." >&2
  : > "$BACKUP_DIR/knowledge-files.sha256"
fi

POSTGRES_DUMP_SHA256="$(sha256sum "$BACKUP_DIR/postgres.dump" | awk '{print $1}')"
KNOWLEDGE_TAR_SHA256=""
if [[ -f "$BACKUP_DIR/knowledge-files.tar" ]]; then
  KNOWLEDGE_TAR_SHA256="$(sha256sum "$BACKUP_DIR/knowledge-files.tar" | awk '{print $1}')"
fi

python3 - "$BACKUP_DIR" "$POSTGRES_DUMP_SHA256" "$KNOWLEDGE_TAR_SHA256" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

backup_dir = Path(sys.argv[1])
counts = {}
counts_file = backup_dir / 'table-counts.tsv'
if counts_file.exists():
    for line in counts_file.read_text(encoding='utf-8').splitlines():
        table, count = line.split('\t', 1)
        counts[table] = int(count)

manifest = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'backup_type': 'local-logical-postgres-plus-knowledge-objects',
    'artifacts': {
        'postgres_dump': {'path': 'postgres.dump', 'sha256': sys.argv[2]},
        'knowledge_files_tar': {
            'path': 'knowledge-files.tar' if sys.argv[3] else None,
            'sha256': sys.argv[3] or None,
        },
        'table_counts': {'path': 'table-counts.tsv', 'counts': counts},
        'knowledge_documents': {'path': 'knowledge-documents.tsv'},
        'knowledge_file_checksums': {'path': 'knowledge-files.sha256'},
    },
    'restore_command': f'./scripts/restore-local.sh {backup_dir}',
}
(backup_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY

echo "Backup local listo: $BACKUP_DIR"
echo "Para restaurar en una base local limpia: ./scripts/restore-local.sh $BACKUP_DIR"
