#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  ./scripts/generate-local-secrets.sh
fi

docker compose up -d --build postgres redis minio otel-collector api event-worker scheduler

echo "API: http://localhost:8000/docs"
echo "MinIO console: http://localhost:9001"
