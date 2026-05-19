#!/usr/bin/env bash
# scripts/batch-pr.sh — Abre un PR cuando la branch actual tenga ≥N tareas (commits)
# por encima de la base. Pensado para el flujo "6 tareas → 1 PR" que evita
# disparar GitHub Actions por cada tarea individual.
#
# Subcomandos:
#   ./scripts/batch-pr.sh status                # cuántas tareas (commits) hay en la branch
#   ./scripts/batch-pr.sh ship                  # corre full CI + push + crea PR (si hay ≥6)
#   ./scripts/batch-pr.sh next "<título>"       # crea una nueva branch para el próximo batch
#
# Flags de `ship`:
#   --target <branch>   Base del PR (default: develop)
#   --count <N>         Tareas mínimas requeridas (default: 6)
#   --force             Abre el PR aunque haya menos commits que --count
#   --skip-full         No corre ci-local-full.sh (NO recomendado — solo para emergencias)
#   --draft             Abre el PR como draft
#
# Variables de entorno:
#   BATCH_TARGET        Base del PR (default: develop). Equivalente a --target.
#   BATCH_COUNT         Tareas mínimas (default: 6). Equivalente a --count.

set -euo pipefail

cd "$(dirname "$0")/.."

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

TARGET="${BATCH_TARGET:-develop}"
COUNT="${BATCH_COUNT:-6}"

command -v git >/dev/null || fail "git no encontrado"

current_branch() { git rev-parse --abbrev-ref HEAD; }

ensure_base() {
  # Asegura que origin/<TARGET> esté disponible localmente.
  if ! git rev-parse --verify --quiet "origin/${TARGET}" >/dev/null; then
    log "Trayendo origin/${TARGET}"
    git fetch origin "${TARGET}" --quiet || fail "no pude hacer fetch de origin/${TARGET}"
  fi
}

commits_ahead() {
  ensure_base
  local base
  base="$(git merge-base "origin/${TARGET}" HEAD)"
  git rev-list --count "${base}..HEAD"
}

cmd_status() {
  local n branch
  branch="$(current_branch)"
  n="$(commits_ahead)"
  echo "Branch:       ${branch}"
  echo "Base:         origin/${TARGET}"
  echo "Tareas (commits): ${n}/${COUNT}"
  if (( n >= COUNT )); then
    ok "Listo para ship. Corre: ./scripts/batch-pr.sh ship"
  else
    echo "Faltan $(( COUNT - n )) tarea(s) antes de abrir el PR."
  fi
}

cmd_next() {
  local title="${1:-}"
  [[ -n "$title" ]] || fail "Uso: ./scripts/batch-pr.sh next \"<título corto>\""
  ensure_base

  # Sanitiza el título → slug
  local slug
  slug="$(echo "$title" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g' \
    | cut -c1-50)"
  [[ -n "$slug" ]] || fail "Título inválido"

  local stamp
  stamp="$(date +%Y%m%d)"
  local new_branch="claude/batch-${stamp}-${slug}"

  log "Creando branch ${new_branch} desde origin/${TARGET}"
  git checkout -b "$new_branch" "origin/${TARGET}"
  ok "Branch lista. Empieza a hacer commits — un commit por tarea."
}

cmd_ship() {
  local force=0 skip_full=0 draft=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target)      TARGET="$2"; shift 2 ;;
      --count)       COUNT="$2"; shift 2 ;;
      --force)       force=1; shift ;;
      --skip-full)   skip_full=1; shift ;;
      --draft)       draft=1; shift ;;
      *) fail "Flag desconocido en ship: $1" ;;
    esac
  done

  command -v gh >/dev/null || fail "gh (GitHub CLI) no encontrado. Instálalo: brew install gh"

  local branch
  branch="$(current_branch)"
  case "$branch" in
    main|develop|master)
      fail "Estás en '$branch'. Cambia a una branch de feature antes de ship." ;;
  esac

  local n
  n="$(commits_ahead)"
  if (( n < COUNT )) && (( force == 0 )); then
    fail "Solo hay ${n} tarea(s) en la branch. Faltan $(( COUNT - n )). Usa --force para ignorar."
  fi
  log "Tareas en batch: ${n} (mínimo ${COUNT}${force:+, force activo})"

  # Working tree limpio
  if [[ -n "$(git status --porcelain)" ]]; then
    fail "Working tree con cambios sin commitear. Limpia o commitea antes de ship."
  fi

  # Full CI local
  if (( skip_full == 0 )); then
    log "Corriendo scripts/ci-local-full.sh — esto puede tardar 10-20 min"
    ./scripts/ci-local-full.sh
  else
    warn "--skip-full → NO se verificó coverage / E2E / admin-panel localmente"
  fi

  # Push
  log "Pusheando ${branch} a origin"
  git push -u origin "$branch"

  # Cuerpo del PR — lista los commits del batch
  ensure_base
  local base
  base="$(git merge-base "origin/${TARGET}" HEAD)"

  local body_file
  body_file="$(mktemp)"
  {
    echo "## Batch de ${n} tarea(s)"
    echo
    echo "Branch base: \`${TARGET}\`"
    echo
    echo "### Commits incluidos"
    echo
    git log --reverse --pretty=format:"- %s" "${base}..HEAD"
    echo
    echo
    echo "### CI local"
    echo
    echo "- \`scripts/ci-local-full.sh\` ejecutado localmente antes del push (lint + unit + coverage ≥90% + E2E + admin-panel build)"
    echo
    echo "### Test plan"
    echo
    echo "- [ ] CI de GitHub verde (gate final)"
    echo "- [ ] Revisar diff por tarea (1 commit = 1 tarea)"
  } > "$body_file"

  local title
  title="Batch: $(git log -1 --pretty=%s | head -c 60)"
  [[ $n -gt 1 ]] && title="Batch (${n} tareas) — desde $(git log "${base}..HEAD" --reverse --pretty=%s | head -1 | head -c 50)"

  local draft_flag=""
  [[ $draft == 1 ]] && draft_flag="--draft"

  log "Abriendo PR (base: ${TARGET})"
  # shellcheck disable=SC2086
  gh pr create \
    --base "${TARGET}" \
    --head "${branch}" \
    --title "${title}" \
    --body-file "${body_file}" \
    ${draft_flag}

  rm -f "$body_file"
  ok "PR abierto."
}

# ── Dispatch ──────────────────────────────────────────────────────────────
sub="${1:-status}"
shift || true
case "$sub" in
  status) cmd_status "$@" ;;
  next)   cmd_next   "$@" ;;
  ship)   cmd_ship   "$@" ;;
  -h|--help|help)
    sed -n '2,22p' "$0" ;;
  *) fail "Subcomando desconocido: $sub (usa: status | next | ship)" ;;
esac
