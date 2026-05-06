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

echo "API: http://localhost:8000/docs"
echo "MinIO console: http://localhost:9001"
