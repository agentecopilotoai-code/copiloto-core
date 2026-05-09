#!/usr/bin/env bash
# Runbook de go-live por tenant.
# Ejecuta checks de readiness, RAG smoke test, WhatsApp health, audit y operaciones básicas.
# Al finalizar imprime una plantilla de evidencia completada.
# Rollback disponible: --rollback-to-mock desactiva modo live sin SQL manual.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

env_value() {
  local key="$1"
  python3 - "${ROOT_DIR}/.env" "${ROOT_DIR}/.env.auth0.local" "${key}" <<'PY'
import sys
from pathlib import Path

wanted_key = sys.argv[-1]
for file_name in sys.argv[1:-1]:
    path = Path(file_name)
    if not path.exists():
        continue
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key == wanted_key:
            print(value.strip().strip('"').strip("'"))
            raise SystemExit
PY
}

# ── Defaults ─────────────────────────────────────────────────────────────────
API_PORT="${API_PORT:-$(env_value API_PORT 2>/dev/null || true)}"
API_PORT="${API_PORT:-8000}"
API_BASE_URL="${API_BASE_URL:-$(env_value API_BASE_URL 2>/dev/null || true)}"
API_BASE_URL="${API_BASE_URL:-http://localhost:${API_PORT}}"
TENANT_ID="${TENANT_ID:-$(env_value SMOKE_TENANT_ID 2>/dev/null || true)}"
TENANT_ID="${TENANT_ID:-}"
JWT_SECRET="${JWT_SECRET:-$(env_value JWT_SECRET 2>/dev/null || true)}"
JWT_SECRET="${JWT_SECRET:-change-me-super-long-jwt-secret}"
JWT_ISSUER="${JWT_ISSUER:-$(env_value JWT_ISSUER 2>/dev/null || true)}"
JWT_ISSUER="${JWT_ISSUER:-copilotoia-local}"
JWT_AUDIENCE="${JWT_AUDIENCE:-$(env_value JWT_AUDIENCE 2>/dev/null || true)}"
JWT_AUDIENCE="${JWT_AUDIENCE:-copilotoia-panel}"
AUTH0_CLAIMS_NAMESPACE="${AUTH0_CLAIMS_NAMESPACE:-$(env_value AUTH0_CLAIMS_NAMESPACE 2>/dev/null || true)}"
AUTH0_CLAIMS_NAMESPACE="${AUTH0_CLAIMS_NAMESPACE:-https://copilotoia.com/claims/}"
AUTH0_DOMAIN="${AUTH0_DOMAIN:-$(env_value AUTH0_DOMAIN 2>/dev/null || true)}"
export JWT_SECRET JWT_ISSUER JWT_AUDIENCE AUTH0_CLAIMS_NAMESPACE

RESPONSIBLE="${RESPONSIBLE:-}"
SMOKE_QUESTION="${SMOKE_QUESTION:-horarios políticas servicios garantías precios contacto}"
ROLLBACK_TO_MOCK=false
ROLLBACK_REASON="${ROLLBACK_REASON:-Rollback preventivo pre-go-live}"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tenant)        TENANT_ID="$2";        shift 2 ;;
    --responsible)   RESPONSIBLE="$2";      shift 2 ;;
    --smoke-question) SMOKE_QUESTION="$2";  shift 2 ;;
    --rollback-to-mock)
      ROLLBACK_TO_MOCK=true
      ROLLBACK_REASON="${2:-Rollback preventivo pre-go-live}"
      shift; [[ $# -gt 0 && "$1" != --* ]] && { ROLLBACK_REASON="$1"; shift; } || true
      ;;
    --api) API_BASE_URL="$2"; shift 2 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${TENANT_ID}" ]]; then
  echo "ERROR: Se requiere --tenant <tenant_id>" >&2
  echo "Uso: $0 --tenant <uuid> [--responsible <nombre>] [--smoke-question <texto>] [--rollback-to-mock [razón]]" >&2
  exit 1
fi

if [[ -z "${RESPONSIBLE}" ]]; then
  echo "ERROR: Se requiere --responsible <nombre>" >&2
  exit 1
fi

# ── Token helpers ─────────────────────────────────────────────────────────────
make_token() {
  local roles_csv="$1"
  local tenant_arg="${2:-}"
  JWT_ROLES="${roles_csv}" JWT_TENANT="${tenant_arg}" python3 - <<'PY'
import base64, hashlib, hmac, json, os, time

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

ns = os.environ['AUTH0_CLAIMS_NAMESPACE'].rstrip('/')
roles = [r for r in os.environ['JWT_ROLES'].split(',') if r]
header = {'alg': 'HS256', 'typ': 'JWT'}
payload = {
    'iss': os.environ['JWT_ISSUER'],
    'aud': os.environ['JWT_AUDIENCE'],
    'sub': 'runbook-operator',
    'exp': int(time.time()) + 60 * 60,
    f'{ns}/roles': roles,
}
if os.environ.get('JWT_TENANT'):
    payload[f'{ns}/tenant_id'] = os.environ['JWT_TENANT']
segs = [b64url(json.dumps(h, separators=(',',':')).encode()) for h in (header, payload)]
sig = hmac.new(os.environ['JWT_SECRET'].encode(), '.'.join(segs).encode(), hashlib.sha256).digest()
print('.'.join([*segs, b64url(sig)]))
PY
}

get_token() {
  if [[ -n "${AUTH0_DOMAIN:-}" ]]; then
    local varname="$1"
    local val="${!varname:-}"
    if [[ -z "${val}" ]]; then
      echo "ERROR: AUTH0_DOMAIN activo. Proporciona $varname=<token_real>." >&2
      exit 2
    fi
    echo "${val}"
  else
    local roles="$2"
    local tenant_scope="${3:-}"
    make_token "${roles}" "${tenant_scope}"
  fi
}

ADMIN_TOKEN="$(get_token RUNBOOK_ADMIN_TOKEN admin "${TENANT_ID}")"
ADMIN_AUTH="Authorization: Bearer ${ADMIN_TOKEN}"

# ── curl helpers ──────────────────────────────────────────────────────────────
api_get() {
  curl -fsS -X GET "${API_BASE_URL}${1}" -H "${ADMIN_AUTH}" "$@"
}

api_patch() {
  local path="$1"; local body="$2"; shift 2
  curl -fsS -X PATCH "${API_BASE_URL}${path}" -H "${ADMIN_AUTH}" \
    -H 'Content-Type: application/json' --data "${body}" "$@"
}

json_field() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d${1})" 2>/dev/null || echo ''
}

# ── Rollback mode ─────────────────────────────────────────────────────────────
if $ROLLBACK_TO_MOCK; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ROLLBACK: Cambiando canal WhatsApp a modo mock"
  echo "  Tenant: ${TENANT_ID}"
  echo "  Razón:  ${ROLLBACK_REASON}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  RESULT="$(api_patch "/v1/tenants/${TENANT_ID}/channels/whatsapp/mode" \
    "{\"account_mode\":\"mock\",\"reason\":\"${ROLLBACK_REASON}\"}")"
  NEW_MODE="$(echo "${RESULT}" | json_field "['account_mode']")"
  echo "Canal ahora en modo: ${NEW_MODE}"
  echo "Rollback completado. Ningún mensaje se enviará a Meta mientras account_mode=mock."
  exit 0
fi

# ── Runbook principal ─────────────────────────────────────────────────────────
RUNBOOK_START="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
PASS_COUNT=0
FAIL_COUNT=0
BLOCKERS=()

check_step() {
  local label="$1"
  local result="$2"  # "ok" | "fail:<razón>"
  if [[ "${result}" == "ok" ]]; then
    echo "  ✓ ${label}"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    local reason="${result#fail:}"
    echo "  ✗ ${label}  →  ${reason}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    BLOCKERS+=("${label}: ${reason}")
  fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RUNBOOK DE GO-LIVE — CopilotoIA"
echo "  Tenant:      ${TENANT_ID}"
echo "  Responsable: ${RESPONSIBLE}"
echo "  Inicio:      ${RUNBOOK_START}"
echo "  API:         ${API_BASE_URL}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Health de la API
echo "[ 1/5 ] Salud de la API"
HEALTH_OK=false
if api_get "/v1/health" 2>/dev/null | python3 -m json.tool >/dev/null 2>&1; then
  HEALTH_OK=true
  check_step "GET /v1/health responde JSON" "ok"
else
  check_step "GET /v1/health responde JSON" "fail:La API no responde o retorna error"
fi
echo ""

# 2. Readiness check completo
echo "[ 2/5 ] Readiness del tenant"
READINESS_JSON=""
READINESS_STATUS="unknown"
if $HEALTH_OK; then
  ENCODED_Q="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "${SMOKE_QUESTION}")"
  READINESS_JSON="$(api_get "/v1/tenants/${TENANT_ID}/readiness?smoke_question=${ENCODED_Q}" 2>/dev/null || true)"
  if [[ -n "${READINESS_JSON}" ]]; then
    READINESS_STATUS="$(echo "${READINESS_JSON}" | json_field "['status']")"
    # Imprimir cada check individual
    python3 - "${READINESS_JSON}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
for c in data.get('checks', []):
    icon = '✓' if c['ready'] else '✗'
    print(f"  {icon} {c['label']}: {c['reason']}")
PY
    if [[ "${READINESS_STATUS}" == "ready" ]]; then
      check_step "Tenant readiness = ready" "ok"
    else
      REASONS="$(echo "${READINESS_JSON}" | python3 -c "import json,sys; print(', '.join(json.load(sys.stdin).get('reasons',[][:3])))")"
      check_step "Tenant readiness = ready" "fail:${REASONS}"
    fi
  else
    check_step "GET /v1/tenants/${TENANT_ID}/readiness" "fail:Sin respuesta del endpoint"
  fi
else
  check_step "Readiness (saltado por fallo de API)" "fail:API no disponible"
fi
echo ""

# 3. WhatsApp channel health
echo "[ 3/5 ] Salud del canal WhatsApp"
CHANNEL_JSON="$(api_get "/v1/tenants/${TENANT_ID}/channels/whatsapp/health" 2>/dev/null || true)"
CHANNEL_HEALTH="unknown"
ACCOUNT_MODE="unknown"
if [[ -n "${CHANNEL_JSON}" ]]; then
  CHANNEL_HEALTH="$(echo "${CHANNEL_JSON}" | json_field "['status']")"
  ACCOUNT_MODE="$(echo "${CHANNEL_JSON}" | json_field "['channel']['account_mode']")"
  check_step "Canal WhatsApp status=${CHANNEL_HEALTH}" "$([ "${CHANNEL_HEALTH}" = "healthy" ] && echo ok || echo "fail:status=${CHANNEL_HEALTH}")"
  check_step "account_mode=${ACCOUNT_MODE}" "$([ "${ACCOUNT_MODE}" = "live" ] && echo ok || echo "fail:El canal no está en modo live")"
else
  check_step "GET /v1/tenants/${TENANT_ID}/channels/whatsapp/health" "fail:Canal no encontrado o error"
  ACCOUNT_MODE="unknown"
fi
echo ""

# 4. RAG smoke test
echo "[ 4/5 ] RAG smoke test"
RAG_SUFFICIENT="false"
RAG_TOP_SCORE="N/A"
if [[ -n "${READINESS_JSON}" ]]; then
  RAG_SUFFICIENT="$(echo "${READINESS_JSON}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
kc=[c for c in data.get('checks',[]) if c['key']=='knowledge_retrieval']
print(kc[0]['details'].get('sufficient_context','false') if kc else 'false')
" 2>/dev/null || echo false)"
  RAG_TOP_SCORE="$(echo "${READINESS_JSON}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
kc=[c for c in data.get('checks',[]) if c['key']=='knowledge_retrieval']
sc=kc[0]['details'].get('top_score') if kc else None
print(sc if sc is not None else 'N/A')
" 2>/dev/null || echo N/A)"
  check_step "Retrieval sufficient_context=${RAG_SUFFICIENT} (top_score=${RAG_TOP_SCORE})" \
    "$([ "${RAG_SUFFICIENT}" = "True" ] || [ "${RAG_SUFFICIENT}" = "true" ] && echo ok || echo "fail:No hay contexto suficiente en knowledge base")"
else
  check_step "RAG smoke test (saltado: readiness no disponible)" "fail:Ejecutar readiness primero"
fi
echo ""

# 5. Audit logs
echo "[ 5/5 ] Audit logs"
AUDIT_JSON="$(api_get "/v1/audit?limit=1" 2>/dev/null || true)"
if [[ -n "${AUDIT_JSON}" ]]; then
  AUDIT_COUNT="$(echo "${AUDIT_JSON}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('items',d) if isinstance(d,dict) else d))" 2>/dev/null || echo 0)"
  check_step "Audit logs disponibles (muestra: ${AUDIT_COUNT} entrada/s)" \
    "$([ "${AUDIT_COUNT}" != "0" ] && echo ok || echo "fail:No hay audit logs para este tenant")"
else
  check_step "GET /v1/audit (audit logs)" "fail:Endpoint no accesible o sin logs"
fi
echo ""

# ── Resumen final ─────────────────────────────────────────────────────────────
RUNBOOK_END="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
OVERALL="APROBADO"
[[ ${FAIL_COUNT} -gt 0 ]] && OVERALL="BLOQUEADO"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RESULTADO: ${OVERALL}  (${PASS_COUNT} ok / ${FAIL_COUNT} fallidos)"
echo "  Fin: ${RUNBOOK_END}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ ${FAIL_COUNT} -gt 0 ]]; then
  echo "Bloqueos:"
  for b in "${BLOCKERS[@]}"; do
    echo "  • ${b}"
  done
  echo ""
  echo "Opciones de rollback disponibles:"
  echo "  # Volver el canal a modo mock (sin SQL):"
  echo "  TENANT_ID=${TENANT_ID} RESPONSIBLE=${RESPONSIBLE} $0 --tenant ${TENANT_ID} --responsible \"${RESPONSIBLE}\" --rollback-to-mock \"${ROLLBACK_REASON}\""
  echo ""
fi

# ── Plantilla de evidencia generada automáticamente ───────────────────────────
echo "────────────────────────────────────────────────────────────────"
echo "  PLANTILLA DE EVIDENCIA  (copiar al registro de go-live)"
echo "────────────────────────────────────────────────────────────────"
cat <<EVIDENCE

## Evidencia de go-live — ${TENANT_ID}

| Campo           | Valor                          |
|-----------------|--------------------------------|
| Tenant ID       | ${TENANT_ID}                   |
| Responsable     | ${RESPONSIBLE}                 |
| Fecha inicio    | ${RUNBOOK_START}               |
| Fecha fin       | ${RUNBOOK_END}                 |
| Resultado       | ${OVERALL}                     |
| Readiness       | ${READINESS_STATUS}            |
| Canal WA status | ${CHANNEL_HEALTH}              |
| account_mode    | ${ACCOUNT_MODE}                |
| RAG sufficient  | ${RAG_SUFFICIENT}              |
| RAG top_score   | ${RAG_TOP_SCORE}               |
| Checks ok       | ${PASS_COUNT}                  |
| Checks fallidos | ${FAIL_COUNT}                  |

### Bloqueos
$(if [[ ${FAIL_COUNT} -eq 0 ]]; then echo "Ninguno."; else for b in "${BLOCKERS[@]}"; do echo "- ${b}"; done; fi)

### Notas del operador
<!-- completar -->

### Rollback ejecutado
<!-- Indicar si se ejecutó rollback, cuándo y razón -->

EVIDENCE

echo "────────────────────────────────────────────────────────────────"
echo ""

[[ "${OVERALL}" == "APROBADO" ]] && exit 0 || exit 1
