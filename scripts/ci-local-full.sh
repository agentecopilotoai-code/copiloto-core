#!/usr/bin/env bash
# scripts/ci-local-full.sh — Réplica local COMPLETA de .github/workflows/ci.yml.
#
# Cubre los 4 jobs del CI:
#   1. api               (compile + ruff + pytest unit)
#   2. coverage-gate     (pytest --cov-fail-under=95 con Postgres ephemeral)
#   3. tests-e2e         (journey + HTTP boundary E2E con Postgres ephemeral)
#   4. admin-panel       (npm install + lint + test + a11y + coverage + build)
#
# Usa un contenedor docker `pgvector/pgvector:pg16` igual que el CI.
#
# Uso:
#   ./scripts/ci-local-full.sh
#   ./scripts/ci-local-full.sh --skip-frontend     # solo backend
#   ./scripts/ci-local-full.sh --skip-e2e          # backend rápido + frontend
#   KEEP_CONTAINER=1 ./scripts/ci-local-full.sh    # deja postgres vivo al final

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# ── Flags ─────────────────────────────────────────────────────────────────
SKIP_FRONTEND=0
SKIP_E2E=0
SKIP_COVERAGE=0
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --skip-e2e)      SKIP_E2E=1 ;;
    --skip-coverage) SKIP_COVERAGE=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Flag desconocido: $arg" >&2; exit 1 ;;
  esac
done

# ── Colores ───────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_OK=$'\033[32m'; C_FAIL=$'\033[31m'; C_INFO=$'\033[36m'; C_WARN=$'\033[33m'; C_RST=$'\033[0m'
else
  C_OK=""; C_FAIL=""; C_INFO=""; C_WARN=""; C_RST=""
fi
log()  { echo "${C_INFO}==>${C_RST} $*"; }
ok()   { echo "${C_OK}✓${C_RST} $*"; }
warn() { echo "${C_WARN}⚠${C_RST} $*" >&2; }
fail() { echo "${C_FAIL}✗${C_RST} $*" >&2; exit 1; }
section() { echo; echo "${C_INFO}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RST}"; echo "${C_INFO} $*${C_RST}"; echo "${C_INFO}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RST}"; }

START_TS=$(date +%s)
PG_CONTAINER=""

cleanup() {
  if [[ -n "$PG_CONTAINER" && "${KEEP_CONTAINER:-0}" != "1" ]]; then
    log "Limpiando contenedor postgres ($PG_CONTAINER)"
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  elif [[ -n "$PG_CONTAINER" && "${KEEP_CONTAINER:-0}" == "1" ]]; then
    warn "KEEP_CONTAINER=1 → postgres ($PG_CONTAINER) sigue corriendo en :5434"
  fi
}
trap cleanup EXIT

# ── Sanity check de tools ─────────────────────────────────────────────────
command -v python3 >/dev/null || fail "python3 no encontrado"
command -v docker  >/dev/null || fail "docker no encontrado (necesario para postgres efímero)"

# ── Venv ──────────────────────────────────────────────────────────────────
section "Setup Python venv"
if [[ ! -d .venv ]]; then
  log "Creando .venv"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if ! command -v ruff >/dev/null || ! command -v pytest >/dev/null; then
  log "Instalando deps [dev]"
  pip install --quiet -e ".[dev]"
fi
ok "venv listo ($(python --version 2>&1))"

# ── Job 1: api (compile + ruff + unit) ────────────────────────────────────
section "Job 1/4 — api (compile + ruff + unit tests)"
log "compile"; python -m compileall app -q; ok "compile"
log "ruff";    ruff check .;                  ok "ruff"
log "pytest unit (-m 'not requires_db and not e2e')"
pytest tests/ -m "not requires_db and not e2e" --tb=short -q
ok "pytest unit"

# ── Provision postgres efímero (compartido entre coverage-gate + e2e) ─────
if [[ $SKIP_COVERAGE == 0 || $SKIP_E2E == 0 ]]; then
  section "Provision Postgres efímero (pgvector/pgvector:pg16)"
  PG_CONTAINER="copilotoia-ci-local-pg-$$"
  PG_PORT=5434  # evita chocar con compose (5432) y run-e2e-http.sh (5433)
  log "Levantando $PG_CONTAINER en :$PG_PORT"
  docker run -d --rm \
    --name "$PG_CONTAINER" \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=copilotoia_e2e \
    -p "${PG_PORT}:5432" \
    pgvector/pgvector:pg16 >/dev/null
  log "Esperando readiness…"
  for _ in $(seq 1 30); do
    if docker exec "$PG_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
      ok "postgres listo"
      break
    fi
    sleep 1
  done
  docker exec "$PG_CONTAINER" pg_isready -U postgres >/dev/null 2>&1 \
    || fail "postgres no levantó a tiempo"

  export TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:${PG_PORT}/copilotoia_e2e"
  export DATABASE_URL="$TEST_DATABASE_URL"
  export RUN_E2E="1"
  export E2E_APPLY_SCHEMA="1"
  export JWT_SECRET="test-jwt-secret-min-length-16-chars"
  export SERVICE_TOKEN="test-service-token-min-length-16"
  export S3_SECRET_ACCESS_KEY="test-s3-secret"
fi

# ── Job 2: coverage-gate ──────────────────────────────────────────────────
if [[ $SKIP_COVERAGE == 0 ]]; then
  # M44 — gate alineado con `.github/workflows/ci.yml` (single source of
  # truth). Antes este script forzaba 93% mientras CI exigía 69% — los
  # locos arreglaban el local y no detectaban si CI subía/bajaba.
  # Los `--ignore` históricos apuntaban a archivos ya borrados; los quitamos.
  section "Job 2/4 — coverage-gate (≥95% backend)"
  pytest --cov=app --cov-report=xml --cov-report=term \
    --cov-fail-under=95 \
    -p no:warnings --tb=short
  ok "coverage-gate ≥90%"
else
  warn "--skip-coverage → coverage gate NO verificado"
fi

# ── Job 3: tests-e2e (journey + HTTP boundary) ────────────────────────────
if [[ $SKIP_E2E == 0 ]]; then
  section "Job 3/4 — tests-e2e (journey + HTTP boundary)"
  log "journey + RLS multitenant"
  pytest tests/test_journey_e2e.py tests/test_rls_multitenant_e2e.py \
    -m e2e --tb=short -q
  log "HTTP-boundary E2E"
  pytest tests/test_e2e_http_*.py -m e2e --tb=short -q
  ok "E2E suites"
else
  warn "--skip-e2e → E2E suites NO ejecutadas"
fi

# ── Job 4: admin-panel ────────────────────────────────────────────────────
if [[ $SKIP_FRONTEND == 0 ]]; then
  section "Job 4/4 — admin-panel (lint + test + a11y + coverage + build)"
  command -v npm >/dev/null || fail "npm no encontrado"
  pushd admin-panel >/dev/null
  if [[ ! -d node_modules ]]; then
    log "npm install"
    npm install --silent
  fi
  log "lint";          npm run --silent lint
  log "test (vitest)"; npm test --silent
  log "test:a11y";     npm run --silent test:a11y
  log "test:coverage"; npm run --silent test:coverage
  log "build";         npm run --silent build
  popd >/dev/null
  ok "admin-panel OK"
else
  warn "--skip-frontend → admin-panel NO ejecutado"
fi

ELAPSED=$(( $(date +%s) - START_TS ))
MIN=$(( ELAPSED / 60 ))
SEC=$(( ELAPSED % 60 ))
echo
section "✓ ci-local-full OK en ${MIN}m${SEC}s"
echo
echo "Listo para abrir el PR. Sugerencia: ./scripts/batch-pr.sh"
