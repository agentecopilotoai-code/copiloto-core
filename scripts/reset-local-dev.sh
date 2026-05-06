#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--yes" ]]; then
  cat >&2 <<'MSG'
Este comando borra los volúmenes locales de Docker Compose, incluyendo la base PostgreSQL local.
Úsalo solo en desarrollo cuando quieras recrear la base con los secretos actuales de .env.

Ejecuta:
  ./scripts/reset-local-dev.sh --yes
MSG
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker no está instalado o no está en el PATH." >&2
  exit 1
fi

docker compose down -v --remove-orphans
./scripts/bootstrap.sh
