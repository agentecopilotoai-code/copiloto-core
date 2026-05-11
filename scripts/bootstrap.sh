#!/usr/bin/env bash
set -euo pipefail

RESET=false
ASSUME_YES=false
SKIP_SMOKE=false

usage() {
  cat <<'MSG'
Uso: ./scripts/bootstrap.sh [--reset --yes] [--skip-smoke]

Sin opciones: genera .env si falta, construye/levanta el stack, valida DB, espera la API,
ejecuta smoke test y valida métricas de OpenTelemetry.

Opciones:
  --reset       Borra volúmenes locales antes de levantar. Solo desarrollo.
  --yes         Confirma --reset.
  --skip-smoke  Levanta y valida DB/API, pero no ejecuta scripts/smoke-test.sh.
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

docker compose up -d --build postgres redis minio otel-collector api event-worker scheduler

DATABASE_URL_VALUE="$(awk -F= '$1 == "DATABASE_URL" {print substr($0, index($0, "=") + 1)}' .env)"
if [[ -z "$DATABASE_URL_VALUE" ]]; then
  echo "Error: DATABASE_URL no está definido en .env." >&2
  exit 1
fi

psql_app() {
  docker compose exec -T postgres psql "$DATABASE_URL_VALUE" -v ON_ERROR_STOP=1 "$@"
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
echo "── Pasos siguientes para habilitar el bot WhatsApp ─────────────────────"
echo " 1. Sube el CSV de servicios:"
echo "    curl -X POST http://localhost:8000/v1/knowledge/documents \\"
echo "         -H 'X-Tenant-Id: 22222222-2222-2222-2222-222222222222' \\"
echo "         -H 'X-Service-Token: \$SERVICE_TOKEN' \\"
echo "         -F 'file=@servicios.csv' -F 'title=Servicios' -F 'document_type=reference'"
echo ""
echo " 2. Verifica que Ollama corre en el host: ollama serve"
echo "    Descarga el modelo: ollama pull llama3.2:3b"
echo ""
echo " 3. En .env asegúrate de tener:"
echo "    ANSWER_ENGINE=cascade"
echo "    LOCAL_LLM_BASE_URL=http://host.docker.internal:11434  # Linux Docker Desktop"
echo "    # ó  http://172.17.0.1:11434                          # Linux nativo"
echo ""
echo " 4. Si cambiaste .env: docker compose restart api"
echo "────────────────────────────────────────────────────────────────────────"
echo "Bootstrap completo: DB, tablas, extensiones, tenants demo, API y métricas OK."
