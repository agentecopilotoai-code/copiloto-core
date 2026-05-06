#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  ./scripts/generate-local-secrets.sh
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

docker compose up -d --build postgres redis minio otel-collector api event-worker scheduler

# Validate that the application role in the existing Postgres volume matches the current .env.
# If .env was regenerated after the volume was created, Postgres keeps the old role password.
DATABASE_URL_VALUE="$(awk -F= '$1 == "DATABASE_URL" {print substr($0, index($0, "=") + 1)}' .env)"

if [[ -z "$DATABASE_URL_VALUE" ]]; then
  echo "Error: DATABASE_URL no está definido en .env." >&2
  exit 1
fi

if ! docker compose exec -T postgres psql "$DATABASE_URL_VALUE" -v ON_ERROR_STOP=1 -c 'select 1' >/dev/null 2>&1; then
  cat >&2 <<'MSG'

Error: PostgreSQL no acepta las credenciales actuales de DATABASE_URL para copiloto_app.
Esto suele pasar cuando .env fue regenerado después de crear el volumen postgres-data.

Solución para desarrollo local (borra la DB local y la recrea con el .env actual):
  ./scripts/reset-local-dev.sh --yes

Si necesitas conservar datos, no borres el volumen; cambia manualmente el password del rol en PostgreSQL.
MSG
  exit 1
fi

echo "API: http://localhost:8000/docs"
echo "MinIO console: http://localhost:9001"
