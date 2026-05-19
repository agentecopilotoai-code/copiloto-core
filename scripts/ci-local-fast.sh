#!/usr/bin/env bash
# scripts/ci-local-fast.sh — Réplica local del job `api` de .github/workflows/ci.yml.
#
# Corre lint + compile + unit tests rápidos (~1-2 min). Pensado para correrse
# después de CADA tarea del backlog, antes de pasar a la siguiente.
#
# Para el run completo (coverage gate + E2E + admin-panel) usar
# scripts/ci-local-full.sh — ese se corre una vez antes de abrir el PR.
#
# Uso:
#   ./scripts/ci-local-fast.sh
#   SKIP_FRONTEND_LINT=1 ./scripts/ci-local-fast.sh   # solo backend

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# Colores
if [[ -t 1 ]]; then
  C_OK=$'\033[32m'; C_FAIL=$'\033[31m'; C_INFO=$'\033[36m'; C_RST=$'\033[0m'
else
  C_OK=""; C_FAIL=""; C_INFO=""; C_RST=""
fi
log()  { echo "${C_INFO}==>${C_RST} $*"; }
ok()   { echo "${C_OK}✓${C_RST} $*"; }
fail() { echo "${C_FAIL}✗${C_RST} $*" >&2; exit 1; }

START_TS=$(date +%s)

# ── Python venv ───────────────────────────────────────────────────────────
if [[ ! -d .venv ]]; then
  log "Creando .venv"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -e ".[dev]"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Si el extras [dev] cambió y ruff/pytest no están, reinstalar.
if ! command -v ruff >/dev/null || ! command -v pytest >/dev/null; then
  log "Reinstalando deps [dev]"
  pip install --quiet -e ".[dev]"
fi

# ── Backend: compile ──────────────────────────────────────────────────────
log "Compile check (python -m compileall app)"
python -m compileall app -q
ok "compile"

# ── Backend: ruff ─────────────────────────────────────────────────────────
log "Lint (ruff check .)"
ruff check .
ok "ruff"

# ── Backend: unit tests (sin DB ni E2E) ───────────────────────────────────
log "Unit & static tests (pytest -m 'not requires_db and not e2e')"
pytest tests/ -m "not requires_db and not e2e" --tb=short -q
ok "pytest unit"

# ── Frontend: lint rápido (sin build) ─────────────────────────────────────
if [[ "${SKIP_FRONTEND_LINT:-0}" != "1" ]]; then
  if [[ -d admin-panel/node_modules ]]; then
    log "Admin panel lint (eslint)"
    (cd admin-panel && npm run --silent lint)
    ok "eslint admin-panel"
  else
    log "Skip admin-panel lint (node_modules no instalados — correr ci-local-full.sh primero)"
  fi
fi

ELAPSED=$(( $(date +%s) - START_TS ))
echo
ok "ci-local-fast OK en ${ELAPSED}s"
