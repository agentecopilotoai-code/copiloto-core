#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--yes" ]]; then
  cat >&2 <<'MSG'
Este comando borra los volúmenes locales de Docker Compose, incluyendo la base PostgreSQL local.
Úsalo solo en desarrollo cuando quieras recrear la base con los secretos actuales de .env.

Ejecuta:
  ./scripts/reset-local-dev.sh --yes

Equivalente recomendado:
  ./scripts/bootstrap.sh --reset --yes
MSG
  exit 2
fi

./scripts/bootstrap.sh --reset --yes
