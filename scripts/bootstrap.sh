#!/usr/bin/env bash
set -euo pipefail

RESET=false
ASSUME_YES=false
SKIP_SMOKE=false
# MODULES — qué módulos opt-in cargar (schemas en infra/postgres/modules/<name>.sql).
# - Default: TODOS los módulos encontrados (comportamiento legacy: el dev local
#   tiene todo activo).
# - `--module=<name>` (puede repetirse): carga solo los listados.
# - `--no-modules`: NO carga ninguno (solo core); útil para reproducir un
#   entorno con un único producto activo.
declare -a MODULES=()
NO_MODULES=false

usage() {
  cat <<'MSG'
Uso: ./scripts/bootstrap.sh [--reset --yes] [--skip-smoke]
                            [--module=<name>]... | [--no-modules]

Sin opciones: genera .env si falta, construye/levanta el stack, valida DB,
espera la API, ejecuta smoke test y valida métricas de OpenTelemetry. Sin
--module y sin --no-modules carga TODOS los módulos opt-in encontrados en
infra/postgres/modules/*.sql.

Opciones:
  --reset           Borra volúmenes locales antes de levantar. Solo desarrollo.
  --yes             Confirma --reset.
  --skip-smoke      Levanta y valida DB/API, pero no ejecuta smoke-test.sh.
  --module=<name>   Carga el módulo opt-in <name> (de infra/postgres/modules/<name>.sql).
                    Repetible. Sin esta flag (y sin --no-modules) carga TODOS
                    los módulos en infra/postgres/modules/*.sql.
  --no-modules      NO carga ningún módulo opt-in. Solo core (10-core + 20-seed).

Ejemplos:
  # Reset full con todos los módulos opt-in disponibles:
  ./scripts/bootstrap.sh --reset --yes

  # Reset minimal — solo core, sin módulos opt-in:
  ./scripts/bootstrap.sh --reset --yes --no-modules
MSG
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset)
      RESET=true
      ;;
    --yes)
      ASSUME_YES=true
      ;;
    --skip-smoke)
      SKIP_SMOKE=true
      ;;
    --module=*)
      MODULES+=("${1#--module=}")
      ;;
    --no-modules)
      NO_MODULES=true
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
  shift
done

if [[ "$NO_MODULES" == true && ${#MODULES[@]} -gt 0 ]]; then
  echo "Error: --no-modules y --module=<name> son mutuamente excluyentes." >&2
  exit 2
fi

if [[ ! -f .env ]]; then
  ./scripts/generate-local-secrets.sh
fi

if [[ ! -f .env.auth0.local ]]; then
  cat > .env.auth0.local <<'EOF_AUTH0_PLACEHOLDER'
# Archivo local opcional para Auth0/OIDC.
# scripts/configure-auth0.sh lo sobreescribe con AUTH0_DOMAIN, AUTH0_AUDIENCE y AUTH0_CLAIMS_NAMESPACE.
EOF_AUTH0_PLACEHOLDER
  chmod 600 .env.auth0.local
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker no está instalado o no está en el PATH." >&2
  echo "Instala Docker Desktop/Engine y Docker Compose v2, luego vuelve a ejecutar ./scripts/bootstrap.sh." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: Docker Compose v2 no está disponible." >&2
  echo "Actualiza Docker Desktop/Engine o instala el plugin docker compose." >&2
  exit 1
fi

if [[ "$RESET" == true ]]; then
  if [[ "$ASSUME_YES" != true ]]; then
    cat >&2 <<'MSG'
Error: --reset borra volúmenes locales, incluyendo PostgreSQL.
Confirma explícitamente con:
  ./scripts/bootstrap.sh --reset --yes
MSG
    exit 2
  fi
  docker compose down -v --remove-orphans
fi

docker compose up -d --build postgres redis minio otel-collector api event-worker scheduler admin-panel

DATABASE_URL_VALUE="$(awk -F= '$1 == "DATABASE_URL" {print substr($0, index($0, "=") + 1)}' .env)"
if [[ -z "$DATABASE_URL_VALUE" ]]; then
  echo "Error: DATABASE_URL no está definido en .env." >&2
  exit 1
fi

# SEC-010: parsear el password del DATABASE_URL y pasarlo via PGPASSWORD env
# var en lugar de argv para que NO aparezca en `ps aux` mientras psql/pg_dump
# corren. `docker compose exec -e PGPASSWORD` (sin valor) inherita del shell
# padre, así que el password tampoco aparece en el argv de `docker`.
# shellcheck source=lib/postgres-url.sh
source "$(dirname "$0")/lib/postgres-url.sh"
parse_db_url "$DATABASE_URL_VALUE"
export PGPASSWORD="$DB_PASSWORD"

psql_app() {
  docker compose exec -T -e PGPASSWORD postgres psql "$DB_URL_NO_PASSWORD" -v ON_ERROR_STOP=1 "$@"
}

POSTGRES_DB_VALUE="$(awk -F= '$1 == "POSTGRES_DB" {print substr($0, index($0, "=") + 1)}' .env)"
POSTGRES_USER_VALUE="$(awk -F= '$1 == "POSTGRES_USER" {print substr($0, index($0, "=") + 1)}' .env)"

psql_admin() {
  docker compose exec -T postgres psql -U "${POSTGRES_USER_VALUE:-copiloto_admin}" -d "${POSTGRES_DB_VALUE:-copilotoia}" -v ON_ERROR_STOP=1 "$@"
}

if ! psql_app -c 'select 1' >/dev/null 2>&1; then
  cat >&2 <<'MSG'

Error: PostgreSQL no acepta las credenciales actuales de DATABASE_URL para copiloto_app.
Esto suele pasar cuando .env fue regenerado después de crear el volumen postgres-data.

Solución para desarrollo local (borra la DB local y la recrea con el .env actual):
  ./scripts/bootstrap.sh --reset --yes

Si necesitas conservar datos, no borres el volumen; cambia manualmente el password del rol en PostgreSQL.
MSG
  exit 1
fi

missing_tables="$(psql_app -Atc "
  with required(table_name) as (
    values
      ('tenants'), ('tenant_settings'), ('tenant_channels'), ('users'), ('user_tenant_roles'),
      ('contacts'), ('conversations'), ('messages'), ('message_status_events'), ('resources'),
      ('service_requests'), ('quotes'), ('appointments'), ('reminder_jobs'), ('knowledge_documents'),
      ('knowledge_chunks'), ('prompt_templates'), ('handoffs'), ('webhook_events_raw'),
      ('domain_events'), ('audit_logs')
  )
  select string_agg(required.table_name, ', ' order by required.table_name)
  from required
  left join information_schema.tables t
    on t.table_schema = 'app' and t.table_name = required.table_name
  where t.table_name is null;
")"

if [[ -n "$missing_tables" ]]; then
  echo "Error: faltan tablas en schema app: $missing_tables" >&2
  echo "Para recrear la DB local: ./scripts/bootstrap.sh --reset --yes" >&2
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Carga selectiva de módulos opt-in (infra/postgres/modules/<name>.sql).
# ─────────────────────────────────────────────────────────────────────────────
# El init de Postgres (/docker-entrypoint-initdb.d) cargó solo el core
# (10-core.sql + 20-seed.sql). Los módulos opt-in se cargan acá porque:
#   - Permiten activar selectivamente desde la CLI (--module=<name>).
#   - Son idempotentes (`create ... if not exists`) — se pueden re-correr.
#   - Cada módulo activa su fila en `app.tenant_modules` para Demo Taller
#     al final (dev local — en prod se activan via PATCH del platform_owner).
modules_dir='infra/postgres/modules'
declare -a modules_to_load=()
if [[ "$NO_MODULES" == true ]]; then
  echo "→ --no-modules: NO se cargan módulos opt-in."
elif [[ ${#MODULES[@]} -gt 0 ]]; then
  # User pidió módulos específicos.
  for m in "${MODULES[@]}"; do
    if [[ ! -f "${modules_dir}/${m}.sql" ]]; then
      echo "Error: módulo '${m}' no encontrado en ${modules_dir}/${m}.sql" >&2
      echo "Módulos disponibles:" >&2
      ls "${modules_dir}"/*.sql 2>/dev/null | xargs -n1 basename | sed 's/\.sql$//' | sed 's/^/  /' >&2
      exit 1
    fi
    modules_to_load+=("$m")
  done
else
  # Sin flag — cargar TODOS los módulos disponibles.
  while IFS= read -r f; do
    modules_to_load+=("$(basename "$f" .sql)")
  done < <(ls "${modules_dir}"/*.sql 2>/dev/null | sort)
fi

for m in "${modules_to_load[@]}"; do
  sql_path="${modules_dir}/${m}.sql"
  echo "→ Cargando módulo '${m}' desde ${sql_path}…"
  if ! psql_admin -q < "$sql_path"; then
    echo "Error: falló la carga del módulo '${m}'. Ver output arriba." >&2
    exit 1
  fi
  echo "  ✓ módulo '${m}' cargado."
done

if [[ ${#modules_to_load[@]} -gt 0 ]]; then
  echo "→ Módulos opt-in cargados: ${modules_to_load[*]}"
fi

# ── Check ANSWER_ENGINE is configured for bot responses ───────────────────────
ANSWER_ENGINE_VALUE="$(awk -F= '$1 == "ANSWER_ENGINE" {print $2}' .env)"
if [[ -z "$ANSWER_ENGINE_VALUE" ]]; then
  echo ""
  echo "⚠  ANSWER_ENGINE no está definido en .env."
  echo "   El bot caerá siempre a handoff humano si no tiene motor configurado."
  echo "   Agrega al .env:  ANSWER_ENGINE=cascade"
  echo "   Y reinicia:      docker compose restart api"
  echo ""
fi

# ── Check Ollama availability (non-blocking) ──────────────────────────────────
LOCAL_LLM_BASE_URL_VALUE="$(awk -F= '$1 == "LOCAL_LLM_BASE_URL" {print $2}' .env)"
LOCAL_LLM_BASE_URL_VALUE="${LOCAL_LLM_BASE_URL_VALUE:-http://host.docker.internal:11434}"
# Strip host.docker.internal for host-side check
OLLAMA_CHECK_URL="${LOCAL_LLM_BASE_URL_VALUE//host.docker.internal/localhost}"
if curl -fsS --max-time 3 "${OLLAMA_CHECK_URL}/api/tags" >/dev/null 2>&1; then
  echo "→ Ollama accesible en ${LOCAL_LLM_BASE_URL_VALUE} ✓"
else
  echo ""
  echo "⚠  Ollama NO está corriendo en ${LOCAL_LLM_BASE_URL_VALUE}."
  echo "   El bot en modo cascade/local_llm caerá a handoff sin él."
  echo "   Para instalarlo:"
  echo "     curl -fsSL https://ollama.com/install.sh | sh"
  echo "     ollama pull llama3.2:3b"
  echo "     ollama serve"
  echo ""
fi

missing_extensions="$(psql_app -Atc "
  with required(extname) as (values ('pgcrypto'), ('citext'), ('vector'), ('btree_gist'))
  select string_agg(required.extname, ', ' order by required.extname)
  from required
  left join pg_extension e on e.extname = required.extname
  where e.extname is null;
")"

if [[ -n "$missing_extensions" ]]; then
  echo "Error: faltan extensiones PostgreSQL: $missing_extensions" >&2
  exit 1
fi

tenant_count="$(psql_app -Atc "select count(*) from app.tenants;")"
if [[ "$tenant_count" -lt 3 ]]; then
  echo "Error: se esperaban al menos 3 tenants demo, pero hay $tenant_count." >&2
  exit 1
fi

health_url='http://localhost:8000/v1/health'
for _ in $(seq 1 60); do
  if curl -fsS "$health_url" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$health_url" >/dev/null; then
  echo "Error: la API no respondió health en $health_url" >&2
  docker compose logs --tail=120 api >&2 || true
  exit 1
fi

if [[ "$SKIP_SMOKE" != true ]]; then
  ./scripts/smoke-test.sh >/dev/null
fi

if ! curl -fsS http://localhost:8889/metrics >/dev/null; then
  echo "Error: OpenTelemetry metrics no respondió en http://localhost:8889/metrics" >&2
  docker compose logs --tail=120 otel-collector >&2 || true
  exit 1
fi

docker compose ps

echo ""
echo "API:            http://localhost:8000/docs"
echo "Health:         http://localhost:8000/v1/health"
echo "MinIO console:  http://localhost:9001"
echo "OTel metrics:   http://localhost:8889/metrics"
echo ""
echo "────────────────────────────────────────────────────────────────────────"
echo "Bootstrap completo: DB, tablas, extensiones, tenant demo, API y métricas OK."
echo ""
echo "Los módulos opt-in (si existen en infra/postgres/modules/) ya quedaron"
echo "instalados. Cada módulo trae su propia documentación de configuración."
