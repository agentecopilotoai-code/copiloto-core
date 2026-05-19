#!/usr/bin/env bash
# scripts/run-e2e-http.sh — Run the HTTP E2E suite against an ephemeral
# PostgreSQL container.
#
# This complements `scripts/run-e2e.sh` (TASK-0063 — journey suite via DB) by
# exercising the FastAPI app boundary: middleware, auth dependencies,
# webhook entrypoints, AUDIT-46..51 fixes via real HTTP requests.
#
# Usage:
#   ./scripts/run-e2e-http.sh                # ephemeral docker container
#   PG_URL=postgresql://...  ./scripts/run-e2e-http.sh    # external DB
#   ONLY=test_e2e_http_auth.py  ./scripts/run-e2e-http.sh # subset
#
# Environment:
#   PG_URL                — postgres DSN (if unset, spins up a container)
#   ONLY                  — optional file or `nodeid::` pattern to filter
#   KEEP_CONTAINER        — `1` keeps the postgres container alive on exit
#                            (useful for poking around after failures)
set -euo pipefail

cd "$(dirname "$0")/.."

# ── Bootstrap python deps if running locally ──────────────────────────────
if [[ ! -d .venv ]]; then
  echo "==> Creating .venv"
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
fi

# ── Provision ephemeral postgres if PG_URL not set ────────────────────────
CONTAINER=""
if [[ -z "${PG_URL:-}" ]]; then
  CONTAINER="copilotoia-e2e-http-pg-$$"
  echo "==> Starting ephemeral postgres container (${CONTAINER})"
  docker run -d --rm \
    --name "${CONTAINER}" \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=copilotoia_e2e_http \
    -p 5433:5432 \
    pgvector/pgvector:pg16 >/dev/null

  # Wait until ready (`pg_isready` inside the container).
  echo "==> Waiting for postgres readiness…"
  for _ in $(seq 1 30); do
    if docker exec "${CONTAINER}" pg_isready -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  cleanup() {
    if [[ -z "${KEEP_CONTAINER:-}" ]]; then
      docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
    else
      echo "==> Leaving container ${CONTAINER} running (KEEP_CONTAINER=1)"
    fi
  }
  trap cleanup EXIT
  PG_URL="postgresql://postgres:postgres@localhost:5433/copilotoia_e2e_http"
fi

echo "==> Using DB: ${PG_URL}"

# ── Run the HTTP E2E suite ────────────────────────────────────────────────
export RUN_E2E=1
export E2E_APPLY_SCHEMA=1
export TEST_DATABASE_URL="${PG_URL}"
# Wipe stale .secrets seeded by previous runs (webhooks test recreates).
rm -rf .secrets/test-whatsapp-app-secret 2>/dev/null || true

FILTER="${ONLY:-tests/test_e2e_http_*.py}"
echo "==> Running: pytest ${FILTER}"
.venv/bin/pytest -v --tb=short -m e2e ${FILTER}
