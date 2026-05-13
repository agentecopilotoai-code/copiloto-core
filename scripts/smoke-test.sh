#!/usr/bin/env bash
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
            print(value.strip().strip('\"').strip("'"))
            raise SystemExit
PY
}

API_PORT="${API_PORT:-$(env_value API_PORT)}"
API_PORT="${API_PORT:-8000}"
API_BASE_URL="${API_BASE_URL:-$(env_value API_BASE_URL)}"
API_BASE_URL="${API_BASE_URL:-http://localhost:${API_PORT}}"
TENANT_ID="${SMOKE_TENANT_ID:-$(env_value SMOKE_TENANT_ID)}"
TENANT_ID="${TENANT_ID:-11111111-1111-1111-1111-111111111111}"
SERVICE_TOKEN="${SERVICE_TOKEN:-$(env_value SERVICE_TOKEN)}"
SERVICE_TOKEN="${SERVICE_TOKEN:-change-me-internal-service-token}"
JWT_SECRET="${JWT_SECRET:-$(env_value JWT_SECRET)}"
JWT_SECRET="${JWT_SECRET:-change-me-super-long-jwt-secret}"
JWT_ISSUER="${JWT_ISSUER:-$(env_value JWT_ISSUER)}"
JWT_ISSUER="${JWT_ISSUER:-copilotoia-local}"
JWT_AUDIENCE="${JWT_AUDIENCE:-$(env_value JWT_AUDIENCE)}"
JWT_AUDIENCE="${JWT_AUDIENCE:-copilotoia-panel}"
WHATSAPP_VERIFY_TOKEN="${WHATSAPP_VERIFY_TOKEN:-$(env_value WHATSAPP_VERIFY_TOKEN)}"
WHATSAPP_VERIFY_TOKEN="${WHATSAPP_VERIFY_TOKEN:-change-me-whatsapp-verify-token}"
WHATSAPP_APP_SECRET="${WHATSAPP_APP_SECRET:-$(env_value WHATSAPP_APP_SECRET)}"
WHATSAPP_APP_SECRET="${WHATSAPP_APP_SECRET:-change-me-whatsapp-app-secret}"
AUTH0_CLAIMS_NAMESPACE="${AUTH0_CLAIMS_NAMESPACE:-$(env_value AUTH0_CLAIMS_NAMESPACE)}"
AUTH0_CLAIMS_NAMESPACE="${AUTH0_CLAIMS_NAMESPACE:-https://copilotoia.com/claims/}"
export JWT_SECRET JWT_ISSUER JWT_AUDIENCE AUTH0_CLAIMS_NAMESPACE WHATSAPP_APP_SECRET

AUTH0_DOMAIN="${AUTH0_DOMAIN:-$(env_value AUTH0_DOMAIN)}"

json_get() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)'"$1"')'
}

make_token() {
  local roles_csv="$1"
  local tenant_arg="${2:-}"
  JWT_ROLES="${roles_csv}" JWT_TENANT="${tenant_arg}" python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os
import time

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

namespace = os.environ['AUTH0_CLAIMS_NAMESPACE'].rstrip('/')
roles = [role for role in os.environ['JWT_ROLES'].split(',') if role]
header = {'alg': 'HS256', 'typ': 'JWT'}
payload = {
    'iss': os.environ['JWT_ISSUER'],
    'aud': os.environ['JWT_AUDIENCE'],
    'sub': 'local-smoke-test',
    'exp': int(time.time()) + 20 * 60,
    f'{namespace}/roles': roles,
}
if os.environ.get('JWT_TENANT'):
    payload[f'{namespace}/tenant_id'] = os.environ['JWT_TENANT']
segments = [
    b64url(json.dumps(header, separators=(',', ':')).encode()),
    b64url(json.dumps(payload, separators=(',', ':')).encode()),
]
signing_input = '.'.join(segments).encode()
signature = hmac.new(os.environ['JWT_SECRET'].encode(), signing_input, hashlib.sha256).digest()
print('.'.join([*segments, b64url(signature)]))
PY
}

sign_whatsapp_body() {
  local body="$1"
  BODY="${body}" python3 - <<'PY'
import hashlib
import hmac
import os
print('sha256=' + hmac.new(os.environ['WHATSAPP_APP_SECRET'].encode(), os.environ['BODY'].encode(), hashlib.sha256).hexdigest())
PY
}

curl_json() {
  local method="$1"
  local url="$2"
  local data=""
  shift 2

  if (($# > 0)) && [[ "$1" != -* ]]; then
    data="$1"
    shift
  fi

  if [[ -n "${data}" ]]; then
    curl -fsS -X "${method}" "${url}" -H 'Content-Type: application/json' "$@" --data "${data}"
  else
    curl -fsS -X "${method}" "${url}" "$@"
  fi
}

expect_json() {
  local response
  response="$(curl_json "$@")"
  printf '%s' "${response}" | python3 -m json.tool >/dev/null
}

if [[ -n "${AUTH0_DOMAIN:-}" ]]; then
  if [[ -z "${SMOKE_OWNER_TOKEN:-}" || -z "${SMOKE_ADMIN_TOKEN:-}" || -z "${SMOKE_AGENT_TOKEN:-}" ]]; then
    cat >&2 <<'EOF'
ERROR: AUTH0_DOMAIN is configured, so the API validates Auth0 RS256 tokens.
Provide real tokens with these environment variables before running this script:
  SMOKE_OWNER_TOKEN=<platform owner token>
  SMOKE_ADMIN_TOKEN=<tenant admin token>
  SMOKE_AGENT_TOKEN=<tenant agent token>

For local HS256 smoke tests, run the stack without AUTH0_DOMAIN/AUTH0_AUDIENCE.
EOF
    exit 2
  fi
  OWNER_TOKEN="${SMOKE_OWNER_TOKEN}"
  ADMIN_TOKEN="${SMOKE_ADMIN_TOKEN}"
  AGENT_TOKEN="${SMOKE_AGENT_TOKEN}"
else
  OWNER_TOKEN="${SMOKE_OWNER_TOKEN:-$(make_token owner '')}"
  ADMIN_TOKEN="${SMOKE_ADMIN_TOKEN:-$(make_token admin "${TENANT_ID}")}"
  AGENT_TOKEN="${SMOKE_AGENT_TOKEN:-$(make_token agent "${TENANT_ID}")}"
fi

SERVICE_AUTH="Authorization: Bearer ${SERVICE_TOKEN}"
ADMIN_AUTH="Authorization: Bearer ${ADMIN_TOKEN}"
AGENT_AUTH="Authorization: Bearer ${AGENT_TOKEN}"
OWNER_AUTH="Authorization: Bearer ${OWNER_TOKEN}"
TENANT_HEADER="X-Tenant-Id: ${TENANT_ID}"
RUN_ID="$(date +%s)"

printf 'API base: %s\n' "${API_BASE_URL}"

printf 'GET /v1/health -> '
expect_json GET "${API_BASE_URL}/v1/health"
printf 'ok\n'

printf 'POST /v1/tenants -> '
expect_json POST "${API_BASE_URL}/v1/tenants" "{\"slug\":\"smoke-${RUN_ID}\",\"legal_name\":\"Smoke ${RUN_ID} SAS\",\"display_name\":\"Smoke ${RUN_ID}\",\"vertical_code\":\"smoke_test\",\"business_type_label\":\"Smoke test\"}" -H "${OWNER_AUTH}"
printf 'ok\n'

printf 'GET /v1/tenants/{tenant_id} -> '
expect_json GET "${API_BASE_URL}/v1/tenants/${TENANT_ID}" '' -H "${AGENT_AUTH}"
printf 'ok\n'

printf 'PATCH /v1/tenants/{tenant_id}/settings -> '
expect_json PATCH "${API_BASE_URL}/v1/tenants/${TENANT_ID}/settings" '{"locale":"es-CO","escalation_policy":{"enabled":true,"queue":"default-support","triggers":{"keywords":["humano","asesor"],"after_bot_turns":8},"handoff_message":"Te conecto con una persona del equipo."}}' -H "${ADMIN_AUTH}"
printf 'ok\n'

printf 'POST /v1/tenants/{tenant_id}/channels/whatsapp -> '
expect_json POST "${API_BASE_URL}/v1/tenants/${TENANT_ID}/channels/whatsapp" "{\"business_id\":\"demo-business-id\",\"waba_id\":\"demo-waba-id\",\"phone_number_id\":\"demo-phone-smoke\",\"meta_access_token\":\"local-mock-smoke-token\",\"app_secret\":\"${WHATSAPP_APP_SECRET}\",\"verify_token\":\"${WHATSAPP_VERIFY_TOKEN}\"}" -H "${ADMIN_AUTH}"
printf 'ok\n'

printf 'GET /v1/tenants/{tenant_id}/channels/whatsapp/health -> '
CHANNEL_JSON="$(curl_json GET "${API_BASE_URL}/v1/tenants/${TENANT_ID}/channels/whatsapp/health" '' -H "${ADMIN_AUTH}")"
CHANNEL_ID="$(printf '%s' "${CHANNEL_JSON}" | json_get "['channel']['id']")"
printf 'ok\n'

printf 'POST /v1/contacts/upsert -> '
CONTACT_JSON="$(curl_json POST "${API_BASE_URL}/v1/contacts/upsert" "{\"tenant_id\":\"${TENANT_ID}\",\"wa_id\":\"smoke-${RUN_ID}\",\"phone_e164\":\"+1555${RUN_ID: -7}\",\"display_name\":\"Smoke Contact\",\"opt_in_status\":\"granted\"}" -H "${SERVICE_AUTH}" -H "${TENANT_HEADER}")"
CONTACT_ID="$(printf '%s' "${CONTACT_JSON}" | json_get "['id']")"
printf 'ok\n'

CONVERSATION_JSON="$(curl_json POST "${API_BASE_URL}/v1/conversations" "{\"tenant_id\":\"${TENANT_ID}\",\"contact_id\":\"${CONTACT_ID}\",\"channel_id\":\"${CHANNEL_ID}\",\"opened_by\":\"system\",\"current_intent\":\"smoke_test\"}" -H "${SERVICE_AUTH}" -H "${TENANT_HEADER}")"
CONVERSATION_ID="$(printf '%s' "${CONVERSATION_JSON}" | json_get "['id']")"

printf 'GET /v1/conversations -> '
expect_json GET "${API_BASE_URL}/v1/conversations" '' -H "${AGENT_AUTH}"
printf 'ok\n'

printf 'POST /v1/conversations/{conversation_id}/messages -> '
expect_json POST "${API_BASE_URL}/v1/conversations/${CONVERSATION_ID}/messages" "{\"tenant_id\":\"${TENANT_ID}\",\"conversation_id\":\"${CONVERSATION_ID}\",\"direction\":\"outbound\",\"sender_actor_type\":\"agent\",\"body_text\":\"Smoke test\"}" -H "${AGENT_AUTH}" -H "Idempotency-Key: smoke-message-${RUN_ID}"
printf 'ok\n'

printf 'POST /v1/conversations/{conversation_id}/handoff -> '
expect_json POST "${API_BASE_URL}/v1/conversations/${CONVERSATION_ID}/handoff" '{"reason":"smoke_test"}' -H "${AGENT_AUTH}"
printf 'ok\n'

printf 'POST /v1/service-requests -> '
SERVICE_REQUEST_JSON="$(curl_json POST "${API_BASE_URL}/v1/service-requests" "{\"tenant_id\":\"${TENANT_ID}\",\"contact_id\":\"${CONTACT_ID}\",\"conversation_id\":\"${CONVERSATION_ID}\",\"vertical_code\":\"smoke_test\",\"service_type\":\"diagnostico\",\"problem_summary\":\"Smoke test\"}" -H "${AGENT_AUTH}")"
SERVICE_REQUEST_ID="$(printf '%s' "${SERVICE_REQUEST_JSON}" | json_get "['id']")"
printf 'ok\n'

RESOURCE_ID="${SMOKE_RESOURCE_ID:-}"
POSTGRES_USER_VALUE="${POSTGRES_USER:-$(env_value POSTGRES_USER)}"
POSTGRES_USER_VALUE="${POSTGRES_USER_VALUE:-copiloto_admin}"
POSTGRES_DB_VALUE="${POSTGRES_DB:-$(env_value POSTGRES_DB)}"
POSTGRES_DB_VALUE="${POSTGRES_DB_VALUE:-copilotoia}"
if [[ -z "${RESOURCE_ID}" ]]; then
  RESOURCE_ID="$(docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres psql -U "${POSTGRES_USER_VALUE}" -d "${POSTGRES_DB_VALUE}" -Atc "select id from app.resources where tenant_id='${TENANT_ID}' and is_active order by created_at limit 1")"
fi

printf 'POST /v1/appointments -> '
expect_json POST "${API_BASE_URL}/v1/appointments" "{\"tenant_id\":\"${TENANT_ID}\",\"contact_id\":\"${CONTACT_ID}\",\"conversation_id\":\"${CONVERSATION_ID}\",\"service_request_id\":\"${SERVICE_REQUEST_ID}\",\"resource_id\":\"${RESOURCE_ID}\",\"service_code\":\"diagnostico\",\"starts_at\":\"2030-01-01T15:00:00Z\",\"ends_at\":\"2030-01-01T16:00:00Z\",\"notes\":\"Smoke test\"}" -H "${AGENT_AUTH}"
printf 'ok\n'

printf 'POST /v1/knowledge/documents -> '
expect_json POST "${API_BASE_URL}/v1/knowledge/documents" "{\"tenant_id\":\"${TENANT_ID}\",\"title\":\"Smoke ${RUN_ID}\",\"source_type\":\"manual\",\"visibility\":\"tenant\"}" -H "${ADMIN_AUTH}"
printf 'ok\n'

printf 'POST /v1/prompts -> '
expect_json POST "${API_BASE_URL}/v1/prompts" "{\"tenant_id\":\"${TENANT_ID}\",\"vertical_code\":\"smoke_test\",\"prompt_type\":\"system\",\"name\":\"smoke-${RUN_ID}\",\"version\":1,\"content\":\"Responde de forma segura.\",\"variables\":[\"tenant\"]}" -H "${ADMIN_AUTH}"
printf 'ok\n'

printf 'GET /v1/webhooks/whatsapp -> '
curl -fsS "${API_BASE_URL}/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=${WHATSAPP_VERIFY_TOKEN}&hub.challenge=smoke" >/dev/null
printf 'ok\n'

printf 'POST /v1/webhooks/whatsapp -> '
WEBHOOK_BODY='{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"metadata":{"phone_number_id":"demo-phone-smoke"}}}]}]}'
WEBHOOK_SIGNATURE="$(sign_whatsapp_body "${WEBHOOK_BODY}")"
expect_json POST "${API_BASE_URL}/v1/webhooks/whatsapp" "${WEBHOOK_BODY}" -H "X-Hub-Signature-256: ${WEBHOOK_SIGNATURE}"
printf 'ok\n'

printf 'All listed endpoints are reachable on %s.\n' "${API_BASE_URL}"
