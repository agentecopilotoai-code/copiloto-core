#!/usr/bin/env bash
set -euo pipefail

# Configura recursos Auth0 para CopilotoIA usando credenciales existentes de Management API.
# Requiere: curl, jq.
#
# Variables obligatorias:
#   AUTH0_DOMAIN              Dominio del tenant Auth0, ej: copilotoia.us.auth0.com
#   MGMT_ACCESS_TOKEN         Token Management API ya emitido, o...
#   MGMT_CLIENT_ID            Client ID M2M con permisos Management API
#   MGMT_CLIENT_SECRET        Client secret M2M con permisos Management API
#
# Variables opcionales (base):
#   COPILOTOIA_DOMAIN         Dominio público del producto. Default: copilotoia.local
#   AUTH0_API_IDENTIFIER      Audience del API. Default: https://$COPILOTOIA_DOMAIN/api
#   AUTH0_ADMIN_APP_NAME      Nombre app admin. Default: copilotoia-admin-web
#   AUTH0_SERVICE_APP_NAME    Nombre app M2M interna. Default: copilotoia-service-m2m
#   ADMIN_CALLBACKS           CSV callbacks admin.
#   ADMIN_LOGOUTS             CSV logout URLs admin.
#   ADMIN_ORIGINS             CSV web origins admin.
#   CLAIMS_NAMESPACE          Namespace URI para custom claims. Default: https://$COPILOTOIA_DOMAIN/claims
#   CONFIGURE_LOGIN_ACTION    true/false. Default: true
#   BIND_LOGIN_ACTION         true/false. Default: true
#   OUTPUT_SECRETS            true/false. Default: false
#   SAVE_AUTH0_CONFIG         true/false. Default: true
#   AUTH0_ENV_FILE            Archivo local de salida. Default: .env.auth0.local
#   AUTH0_SECRETS_DIR         Directorio local de secretos. Default: .secrets
#   BOOTSTRAP_PLATFORM_OWNER_EMAIL   Email del primer platform_owner. Si está
#                                    definido, el script le asigna el rol
#                                    platform_owner automáticamente Y setea
#                                    app_metadata.support_mode=true (gated por
#                                    la siguiente variable). El user debe
#                                    existir previamente en Auth0.
#   BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE  true/false. Default: true. Si false,
#                                    asigna solo el rol sin tocar support_mode
#                                    (el operador lo configura a mano después).
#
# ─── Variables opcionales avanzadas (M62 — automation completa) ─────────────
# Estas secciones son opt-in para que un upgrade del script no aplique cambios
# inesperados a tenants Auth0 ya configurados manualmente. Default = false en
# todas, salvo defaults seguros para producción nueva.
#
#   CONFIGURE_TENANT_SETTINGS   true/false. Default: true. Setea friendly_name,
#                               support_email, support_url, session_lifetime,
#                               idle_session_lifetime, default_redirection_uri.
#   TENANT_FRIENDLY_NAME        Default: CopilotoIA
#   TENANT_SUPPORT_EMAIL        Default: support@$COPILOTOIA_DOMAIN
#   TENANT_SUPPORT_URL          Default: https://$COPILOTOIA_DOMAIN/support
#   TENANT_SESSION_LIFETIME_HRS Default: 168 (7 días) — max-lifetime de la
#                               SSO session de Auth0. El access_token vive 2h
#                               (lifetime_in_seconds del admin app).
#   TENANT_IDLE_SESSION_HRS     Default: 72 (3 días).
#
#   CONFIGURE_UNIVERSAL_LOGIN   true/false. Default: true. Cambia a "new"
#                               Universal Login (responsive + customizable).
#
#   CONFIGURE_DB_CONNECTION     true/false. Default: true. Habilita la
#                               connection Username-Password-Authentication
#                               para ambas apps (admin + service) + setea
#                               password policy. Sin esto la app admin no
#                               aparece en la connection y el login email/
#                               password tira "invalid client".
#   DB_PASSWORD_POLICY          fair / good / excellent. Default: good
#                               (min 8 chars, mayúscula, número, especial).
#   DB_PASSWORD_HISTORY_SIZE    Default: 5 (no permite reusar últimas 5).
#   DB_BRUTE_FORCE_PROTECTION   true/false. Default: true.
#
#   CONFIGURE_MFA_FACTORS       true/false. Default: true. Habilita los
#                               factores OTP + WebAuthn (platform/roaming) en
#                               el tenant. Sin esto, la Action MFA-challenge
#                               de ENFORCE_MFA_ACTION puede fallar.
#   MFA_POLICY                  all-applications | confidence-score | none.
#                               Default: "" → auto-seteado a "all-applications"
#                               cuando ENFORCE_MFA_ACTION=true (la Action de
#                               MFA-challenge no funciona sin policy non-empty).
#                               - all-applications: MFA requerido para TODOS
#                                 los users en TODAS las apps. La Action
#                                 después puede customizar (e.g. solo
#                                 enrollWith para platform_owner).
#                               - confidence-score: solo MFA cuando Auth0
#                                 detecta riesgo (IP nueva, device nuevo, etc).
#                               - none: desactiva MFA enforcement completo.
#                                 La Action queda inutilizable (Auth0 rechaza
#                                 con "feature is not enabled").
#
#   CONFIGURE_ATTACK_PROTECTION true/false. Default: true. Habilita brute
#                               force + breached password detection + IP
#                               throttling (anomaly detection).
#
#   CONFIGURE_RESEND_PROVIDER   true/false. Default: false (opt-in).
#                               Configura Resend como SMTP provider del
#                               tenant Auth0 para que TODOS los emails que
#                               manda Auth0 (verification, password reset,
#                               blocked account, change_password) salgan
#                               desde TU dominio verificado en Resend.
#   RESEND_API_KEY              Key Resend (re_xxx). Obligatorio si
#                               CONFIGURE_RESEND_PROVIDER=true.
#   EMAIL_FROM_ADDRESS          Sender. Default: invites@$COPILOTOIA_DOMAIN.
#                               Tiene que ser de un dominio verificado en
#                               Resend (SPF + DKIM + DMARC).
#   EMAIL_FROM_NAME             Default: CopilotoIA
#
#   CONFIGURE_EMAIL_TEMPLATES   true/false. Default: true. Renderiza los 5
#                               templates Auth0 (verify_email, reset_email,
#                               welcome_email, blocked_account, mfa_oob) con
#                               subjects ES + branding.
#
#   CONFIGURE_ACCOUNT_LINKING   true/false. Default: true. Crea Action que
#                               auto-linkea identidades del mismo email
#                               verificado en distintas connections (e.g.
#                               Google OAuth + email/password → mismo user).
#                               Sin esto, el mismo email queda como 2 users
#                               distintos en Auth0 y rompe M57 reconciliation.
#
# ─── Scopes Management API requeridos ──────────────────────────────────────
# El app M2M `copilotoia-service-m2m` necesita estos scopes para que el
# script pueda configurar TODAS las secciones. Si faltan alguno, ESE bloque
# loguea warning y skipea (no aborta). Para habilitar en Auth0 dashboard:
# Applications → APIs → Auth0 Management API → Machine to Machine
# Applications → tu M2M app → Add Permissions:
#
#   • read/create/update:resource_servers
#   • read/create/update:clients
#   • read/create/update:client_grants
#   • read/create/update:roles
#   • read/update:role_members
#   • read/create/update:users          # bootstrap platform_owner
#   • create:user_tickets                # password-change ticket
#   • read/create/update:actions         # Post-Login Actions
#   • read:connections, update:connections  # M62 — DB connection
#   • read:tenant_settings, update:tenant_settings  # M62 — tenant cfg
#   • read:guardian_factors, update:guardian_factors  # M62 — MFA
#   • read:attack_protection, update:attack_protection  # M62 — anomaly
#   • read:email_provider, create:email_provider, update:email_provider, delete:email_provider  # M62 — Resend
#   • read:email_templates, create:email_templates, update:email_templates  # M62 — templates
#   • read:prompts, update:prompts       # M62 — Universal Login

AUTH0_DOMAIN="${AUTH0_DOMAIN:-}"
MGMT_CLIENT_ID="${MGMT_CLIENT_ID:-}"
MGMT_CLIENT_SECRET="${MGMT_CLIENT_SECRET:-}"
MGMT_ACCESS_TOKEN="${MGMT_ACCESS_TOKEN:-}"
COPILOTOIA_DOMAIN="${COPILOTOIA_DOMAIN:-copilotoia.local}"
AUTH0_API_IDENTIFIER="${AUTH0_API_IDENTIFIER:-https://$COPILOTOIA_DOMAIN/api}"
AUTH0_ADMIN_APP_NAME="${AUTH0_ADMIN_APP_NAME:-copilotoia-admin-web}"
AUTH0_SERVICE_APP_NAME="${AUTH0_SERVICE_APP_NAME:-copilotoia-service-m2m}"
ADMIN_CALLBACKS="${ADMIN_CALLBACKS:-http://localhost:3000/callback,https://$COPILOTOIA_DOMAIN/callback}"
ADMIN_LOGOUTS="${ADMIN_LOGOUTS:-http://localhost:3000/admin/,http://localhost:3000,https://$COPILOTOIA_DOMAIN/admin/,https://$COPILOTOIA_DOMAIN}"
ADMIN_ORIGINS="${ADMIN_ORIGINS:-http://localhost:3000,https://$COPILOTOIA_DOMAIN}"
CLAIMS_NAMESPACE="${CLAIMS_NAMESPACE:-https://$COPILOTOIA_DOMAIN/claims}"
CONFIGURE_LOGIN_ACTION="${CONFIGURE_LOGIN_ACTION:-true}"
BIND_LOGIN_ACTION="${BIND_LOGIN_ACTION:-true}"
OUTPUT_SECRETS="${OUTPUT_SECRETS:-false}"
SAVE_AUTH0_CONFIG="${SAVE_AUTH0_CONFIG:-true}"
AUTH0_ENV_FILE="${AUTH0_ENV_FILE:-.env.auth0.local}"
AUTH0_SECRETS_DIR="${AUTH0_SECRETS_DIR:-.secrets}"

# ── M62 — toggles avanzados (defaults seguros para producción nueva) ──────
CONFIGURE_TENANT_SETTINGS="${CONFIGURE_TENANT_SETTINGS:-true}"
TENANT_FRIENDLY_NAME="${TENANT_FRIENDLY_NAME:-CopilotoIA}"
TENANT_SUPPORT_EMAIL="${TENANT_SUPPORT_EMAIL:-support@$COPILOTOIA_DOMAIN}"
TENANT_SUPPORT_URL="${TENANT_SUPPORT_URL:-https://$COPILOTOIA_DOMAIN/support}"
TENANT_SESSION_LIFETIME_HRS="${TENANT_SESSION_LIFETIME_HRS:-168}"
TENANT_IDLE_SESSION_HRS="${TENANT_IDLE_SESSION_HRS:-72}"

CONFIGURE_UNIVERSAL_LOGIN="${CONFIGURE_UNIVERSAL_LOGIN:-true}"

CONFIGURE_DB_CONNECTION="${CONFIGURE_DB_CONNECTION:-true}"
DB_PASSWORD_POLICY="${DB_PASSWORD_POLICY:-good}"
DB_PASSWORD_HISTORY_SIZE="${DB_PASSWORD_HISTORY_SIZE:-5}"
DB_BRUTE_FORCE_PROTECTION="${DB_BRUTE_FORCE_PROTECTION:-true}"

CONFIGURE_MFA_FACTORS="${CONFIGURE_MFA_FACTORS:-true}"
MFA_POLICY="${MFA_POLICY:-}"

CONFIGURE_ATTACK_PROTECTION="${CONFIGURE_ATTACK_PROTECTION:-true}"

CONFIGURE_RESEND_PROVIDER="${CONFIGURE_RESEND_PROVIDER:-false}"
RESEND_API_KEY="${RESEND_API_KEY:-}"
EMAIL_FROM_ADDRESS="${EMAIL_FROM_ADDRESS:-invites@$COPILOTOIA_DOMAIN}"
EMAIL_FROM_NAME="${EMAIL_FROM_NAME:-CopilotoIA}"

CONFIGURE_EMAIL_TEMPLATES="${CONFIGURE_EMAIL_TEMPLATES:-true}"
CONFIGURE_ACCOUNT_LINKING="${CONFIGURE_ACCOUNT_LINKING:-true}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Falta dependencia: $1" >&2
    exit 1
  }
}

need_cmd curl
need_cmd jq

[ -n "$AUTH0_DOMAIN" ] || {
  echo "AUTH0_DOMAIN es obligatorio" >&2
  exit 1
}

if [ -z "$MGMT_ACCESS_TOKEN" ]; then
  [ -n "$MGMT_CLIENT_ID" ] || {
    echo "MGMT_CLIENT_ID es obligatorio si MGMT_ACCESS_TOKEN no está definido" >&2
    exit 1
  }
  [ -n "$MGMT_CLIENT_SECRET" ] || {
    echo "MGMT_CLIENT_SECRET es obligatorio si MGMT_ACCESS_TOKEN no está definido" >&2
    exit 1
  }
fi

json_array_from_csv() {
  local csv="$1"
  jq -Rn --arg csv "$csv" '$csv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))'
}

api_request() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local response_with_code http_code response attempt wait_s

  # M62 hotfix #5 — retry on 429 también en el wrapper original (no solo
  # en api_request_soft). Auth0 tira "Global limit has been reached" en
  # cualquier endpoint si hacés muchas calls seguidas (e.g. el loop de
  # roles hace 14 calls a /roles/* en pocos segundos → 429). Sin retry,
  # el script aborta con `exit 1` por el `set -e` global.
  #
  # Hasta 3 attempts: 15s + 30s backoff = 45s wait max. Si los 3
  # fallan, aborta (mantiene el contrato hard-fail del wrapper original).
  for attempt in 1 2 3; do
    if [ -n "$data" ]; then
      response_with_code="$(printf '%s' "$data" | curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}" --data @-)"
    else
      response_with_code="$(curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}")"
    fi

    http_code="$(tail -n1 <<<"$response_with_code")"
    response="$(sed '$d' <<<"$response_with_code")"

    if [[ "$http_code" =~ ^2 ]]; then
      printf '%s' "$response"
      return 0
    fi

    # 429 → retry con backoff.
    if [ "$http_code" = "429" ] && [ "$attempt" -lt 3 ]; then
      wait_s=$((attempt * 15))
      echo "  ⏳ $method $path → HTTP 429 — esperando ${wait_s}s (attempt $attempt/3)" >&2
      sleep "$wait_s"
      continue
    fi

    # No es 2xx ni retryable 429 → hard fail (mantiene contrato original).
    echo "Error Auth0 Management API: $method $path" >&2
    echo "HTTP status: $http_code" >&2
    echo "Respuesta:" >&2
    jq . <<<"$response" >&2 2>/dev/null || echo "$response" >&2
    if [ "$http_code" = "429" ]; then
      echo "Sugerencia: Auth0 sigue rate-limitando tras 3 intentos. Esperá 1-2 minutos y re-corré el script (es idempotente)." >&2
    fi
    exit 1
  done
}

api_get() { api_request GET "$1"; }
api_post() { api_request POST "$1" "$2"; }
api_patch() { api_request PATCH "$1" "$2"; }
api_put() { api_request PUT "$1" "$2"; }
api_delete() { api_request DELETE "$1"; }

# M62 — variante fail-soft para secciones opcionales. Si el M2M no tiene
# los scopes necesarios, loguea warning con el scope faltante y devuelve
# "" para que el caller skipee en lugar de abortar todo el script.
# Esto permite que un operator agregue scopes incrementalmente.
#
# Retry on 429: Auth0 limita rate sobre endpoints sensibles (attack-protection,
# emails/provider, prompts). Reintentamos hasta 2 veces con backoff
# (15s + 30s = 45s max) antes de soft-fail.
api_request_soft() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local label="${4:-$method $path}"
  local response_with_code http_code response attempt wait_s

  for attempt in 1 2 3; do
    if [ -n "$data" ]; then
      response_with_code="$(printf '%s' "$data" | curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}" --data @-)"
    else
      response_with_code="$(curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}")"
    fi

    http_code="$(tail -n1 <<<"$response_with_code")"
    response="$(sed '$d' <<<"$response_with_code")"

    if [[ "$http_code" =~ ^2 ]]; then
      printf '%s' "$response"
      return 0
    fi

    # 429 = rate limit. Retry con backoff.
    if [ "$http_code" = "429" ] && [ "$attempt" -lt 3 ]; then
      wait_s=$((attempt * 15))
      echo "  ⏳ $label → HTTP 429 — esperando ${wait_s}s y reintentando (attempt $attempt/3)" >&2
      sleep "$wait_s"
      continue
    fi

    # 403 = insufficient_scope. 401 = token inválido (raro). 4xx genéricos =
    # config mal (e.g. payload field-no-permitido en API nueva). Soft-fail.
    local err_message
    err_message="$(jq -r '.message // .error // "?"' <<<"$response" 2>/dev/null || echo "?")"
    echo "  ⚠ $label → HTTP $http_code ($err_message)" >&2
    if [ "$http_code" = "403" ]; then
      echo "    └─ Probablemente falta scope en el M2M. Ver header del script para la lista." >&2
    elif [ "$http_code" = "429" ]; then
      echo "    └─ Auth0 sigue rate-limitando tras 3 intentos. Re-correr el script en 1-2 minutos." >&2
    fi
    return 1
  done
}

api_get_soft() { api_request_soft GET "$1" "" "${2:-GET $1}"; }
api_post_soft() { api_request_soft POST "$1" "$2" "${3:-POST $1}"; }
api_patch_soft() { api_request_soft PATCH "$1" "$2" "${3:-PATCH $1}"; }
api_put_soft() { api_request_soft PUT "$1" "$2" "${3:-PUT $1}"; }
api_delete_soft() { api_request_soft DELETE "$1" "" "${2:-DELETE $1}"; }

# M62 hotfix #3 — espera que un Action de Auth0 termine su BUILD async
# antes de bindarlo. Necesario para Actions con `dependencies` (npm
# packages como `auth0`) — Auth0 hace `npm install` server-side antes
# de marcar la action como `built`. Si bindas antes, devuelve:
#   "Trying to create a binding for an action that has not been deployed yet"
#
# Args: action_id. Polls cada 2s hasta status=built o timeout 60s.
# Soft-fail: si timeout, loguea y devuelve 1 (el caller decide).
wait_action_built() {
  local action_id="$1"
  local label="${2:-action $action_id}"
  local max_wait=60
  local elapsed=0
  local status
  while [ "$elapsed" -lt "$max_wait" ]; do
    status="$(api_get_soft "/actions/actions/$action_id" "poll status $label" 2>/dev/null \
              | jq -r '.status // "?"')"
    case "$status" in
      built)
        return 0 ;;
      failed)
        echo "  ⚠ $label → build failed (revisar code/deps en dashboard)" >&2
        return 1 ;;
      pending|building|""|"?")
        sleep 2
        elapsed=$((elapsed + 2))
        ;;
      *)
        sleep 2
        elapsed=$((elapsed + 2))
        ;;
    esac
  done
  echo "  ⚠ $label → timeout ${max_wait}s esperando status=built (status actual: $status)" >&2
  return 1
}

write_secret_file() {
  local path="$1"
  local value="$2"

  [ -n "$value" ] || return 0
  mkdir -p "$(dirname "$path")"
  umask 077
  printf '%s\n' "$value" >"$path"
  chmod 600 "$path" 2>/dev/null || true
}

json_string_array_to_csv() {
  jq -r 'if type == "array" then join(",") else "" end' <<<"$1"
}

CALLBACKS_JSON="$(json_array_from_csv "$ADMIN_CALLBACKS")"
LOGOUTS_JSON="$(json_array_from_csv "$ADMIN_LOGOUTS")"
ORIGINS_JSON="$(json_array_from_csv "$ADMIN_ORIGINS")"
CLAIMS_NAMESPACE="${CLAIMS_NAMESPACE%/}"

if [ -n "$MGMT_ACCESS_TOKEN" ]; then
  mgmt_token="$MGMT_ACCESS_TOKEN"
else
  token_payload="$(jq -n \
    --arg client_id "$MGMT_CLIENT_ID" \
    --arg client_secret "$MGMT_CLIENT_SECRET" \
    --arg audience "https://$AUTH0_DOMAIN/api/v2/" \
    '{client_id:$client_id,client_secret:$client_secret,audience:$audience,grant_type:"client_credentials"}')"

  token_response_with_code="$(printf '%s' "$token_payload" | curl -sS -w '\n%{http_code}' "https://$AUTH0_DOMAIN/oauth/token" -H 'content-type: application/json' --data @-)"
  token_http_code="$(tail -n1 <<<"$token_response_with_code")"
  token_response="$(sed '$d' <<<"$token_response_with_code")"
  mgmt_token="$(jq -r '.access_token // empty' <<<"$token_response" 2>/dev/null || true)"

  if [ -z "$mgmt_token" ]; then
    echo "No se pudo obtener token de Management API desde https://$AUTH0_DOMAIN/oauth/token" >&2
    echo "HTTP status: $token_http_code" >&2
    echo "Respuesta recibida:" >&2
    jq . <<<"$token_response" >&2 2>/dev/null || echo "$token_response" >&2
    echo "Sugerencias:" >&2
    echo "  - AUTH0_DOMAIN debe ser el dominio del tenant (ej: <tenant>.us.auth0.com)." >&2
    echo "  - Verifica MGMT_CLIENT_ID/MGMT_CLIENT_SECRET." >&2
    echo "  - La app M2M necesita permisos Management API como create/read/update:resource_servers, create/read/update:clients, create/read:roles, update:roles, create/read/update:client_grants y create/read/update:actions si habilitas Actions." >&2
    exit 1
  fi
fi

auth_header=(-H "Authorization: Bearer $mgmt_token" -H 'content-type: application/json')

permissions_json="$(jq -n '[
  {value:"tenants:create", description:"Crear tenants"},
  {value:"tenants:read", description:"Leer tenants"},
  {value:"tenants:update", description:"Actualizar tenants"},
  {value:"tenant_settings:update", description:"Actualizar settings de tenant"},
  {value:"channels:manage", description:"Gestionar canales del tenant"},
  {value:"channels:read", description:"Leer health/configuración de canales"},
  {value:"contacts:read", description:"Leer contactos"},
  {value:"contacts:write", description:"Crear o actualizar contactos"},
  {value:"conversations:read", description:"Leer conversaciones"},
  {value:"conversations:write", description:"Enviar mensajes y actualizar conversaciones"},
  {value:"conversations:handoff", description:"Gestionar handoff humano"},
  {value:"service_requests:read", description:"Leer solicitudes de servicio"},
  {value:"service_requests:write", description:"Crear o actualizar solicitudes de servicio"},
  {value:"quotes:read", description:"Leer cotizaciones"},
  {value:"quotes:write", description:"Crear y enviar cotizaciones"},
  {value:"appointments:read", description:"Leer agenda y citas"},
  {value:"appointments:write", description:"Crear, reprogramar o cancelar citas"},
  {value:"knowledge:read", description:"Leer documentos y pruebas de conocimiento"},
  {value:"knowledge:write", description:"Crear o actualizar documentos de conocimiento"},
  {value:"knowledge:index", description:"Indexar documentos de conocimiento"},
  {value:"prompts:read", description:"Leer prompts"},
  {value:"prompts:write", description:"Crear o actualizar prompts"},
  {value:"prompts:activate", description:"Activar versiones de prompts"},
  {value:"analytics:read", description:"Leer métricas operativas"},
  {value:"audit_logs:read", description:"Leer auditoría"},
  {value:"exports:create", description:"Crear exportes controlados"},
  {value:"privacy:manage", description:"Gestionar flujos de privacidad"},
  {value:"users:manage", description:"Gestionar usuarios y membresías"},
  {value:"support:impersonate", description:"Soporte interno auditado entre tenants"}
]')"

all_permission_names="$(jq -r '.[].value' <<<"$permissions_json" | paste -sd, -)"
service_permissions="tenants:read,channels:read,contacts:read,contacts:write,conversations:read,conversations:write,service_requests:read,service_requests:write,quotes:read,quotes:write,appointments:read,appointments:write,knowledge:read,knowledge:index,prompts:read"

echo "▶ Upsert API CopilotoIA Core"
resource_servers="$(api_get '/resource-servers?per_page=100')"
api_id="$(jq -r --arg identifier "$AUTH0_API_IDENTIFIER" '.[] | select(.identifier == $identifier) | .id' <<<"$resource_servers" | head -n1)"
api_create_payload="$(jq -n \
  --arg identifier "$AUTH0_API_IDENTIFIER" \
  --argjson scopes "$permissions_json" \
  '{name:"copilotoia-core-api",identifier:$identifier,signing_alg:"RS256",allow_offline_access:true,enforce_policies:true,token_dialect:"access_token_authz",token_lifetime:86400,token_lifetime_for_web:7200,scopes:$scopes}')"
api_patch_payload="$(jq -n \
  --argjson scopes "$permissions_json" \
  '{name:"copilotoia-core-api",signing_alg:"RS256",allow_offline_access:true,enforce_policies:true,token_dialect:"access_token_authz",token_lifetime:86400,token_lifetime_for_web:7200,scopes:$scopes}')"

if [ -z "$api_id" ]; then
  api_id="$(api_post '/resource-servers' "$api_create_payload" | jq -r .id)"
else
  api_patch "/resource-servers/$api_id" "$api_patch_payload" >/dev/null
fi

echo "▶ Upsert app $AUTH0_ADMIN_APP_NAME"
clients="$(api_get '/clients?is_global=false&fields=client_id,name,app_type&include_fields=true&per_page=100')"
admin_client_id="$(jq -r --arg name "$AUTH0_ADMIN_APP_NAME" '.[] | select(.name == $name) | .client_id' <<<"$clients" | head -n1)"
admin_client_secret=""
admin_payload="$(jq -n \
  --arg name "$AUTH0_ADMIN_APP_NAME" \
  --argjson callbacks "$CALLBACKS_JSON" \
  --argjson logouts "$LOGOUTS_JSON" \
  --argjson origins "$ORIGINS_JSON" \
  '{name:$name,app_type:"regular_web",oidc_conformant:true,callbacks:$callbacks,allowed_logout_urls:$logouts,web_origins:$origins,grant_types:["authorization_code","refresh_token"],jwt_configuration:{alg:"RS256",lifetime_in_seconds:7200},refresh_token:{rotation_type:"rotating",expiration_type:"expiring",token_lifetime:2592000,idle_token_lifetime:604800}}')"

if [ -z "$admin_client_id" ]; then
  admin_client_id="$(api_post '/clients' "$admin_payload" | jq -r .client_id)"
else
  api_patch "/clients/$admin_client_id" "$admin_payload" >/dev/null
fi

echo "▶ Upsert app M2M $AUTH0_SERVICE_APP_NAME"
clients="$(api_get '/clients?is_global=false&fields=client_id,name,app_type&include_fields=true&per_page=100')"
service_client_id="$(jq -r --arg name "$AUTH0_SERVICE_APP_NAME" '.[] | select(.name == $name) | .client_id' <<<"$clients" | head -n1)"
service_client_secret=""
service_payload="$(jq -n --arg name "$AUTH0_SERVICE_APP_NAME" '{name:$name,app_type:"non_interactive",oidc_conformant:true,grant_types:["client_credentials"],jwt_configuration:{alg:"RS256",lifetime_in_seconds:3600}}')"

if [ -z "$service_client_id" ]; then
  service_response="$(api_post '/clients' "$service_payload")"
  service_client_id="$(jq -r .client_id <<<"$service_response")"
  service_client_secret="$(jq -r '.client_secret // empty' <<<"$service_response")"
else
  api_patch "/clients/$service_client_id" "$service_payload" >/dev/null
fi

admin_client_detail="$(api_get "/clients/$admin_client_id?fields=client_id,client_secret&include_fields=true")"
admin_client_secret="$(jq -r '.client_secret // empty' <<<"$admin_client_detail")"
service_client_detail="$(api_get "/clients/$service_client_id?fields=client_id,client_secret&include_fields=true")"
service_client_secret="$(jq -r '.client_secret // empty' <<<"$service_client_detail")"

echo "▶ Upsert client grant M2M hacia API"
client_grants="$(api_get '/client-grants?per_page=100')"
client_grant_id="$(jq -r --arg client_id "$service_client_id" --arg audience "$AUTH0_API_IDENTIFIER" '.[] | select(.client_id == $client_id and .audience == $audience) | .id' <<<"$client_grants" | head -n1)"
grant_payload="$(jq -n --arg audience "$AUTH0_API_IDENTIFIER" --arg client_id "$service_client_id" --arg scopes "$service_permissions" '{audience:$audience,client_id:$client_id,scope:($scopes | split(","))}')"
if [ -z "$client_grant_id" ]; then
  api_post '/client-grants' "$grant_payload" >/dev/null
else
  patch_grant_payload="$(jq -n --arg scopes "$service_permissions" '{scope:($scopes | split(","))}')"
  api_patch "/client-grants/$client_grant_id" "$patch_grant_payload" >/dev/null
fi

# BUG-001 follow-up: el script crea la app M2M (`copilotoia-service-m2m`)
# pero antes NO le autorizaba Auth0 Management API. El backend la usa
# runtime para invitar miembros (`POST /api/v2/users`), generar tickets de
# password-change (`POST /api/v2/tickets/password-change`), asignar roles
# (`POST /api/v2/users/{id}/roles`) y leer roles disponibles
# (`GET /api/v2/roles`). Sin estos scopes, el invite respondía 403 en
# `/oauth/token` y los miembros nuevos no recibían email.
#
# Los scopes son el mínimo necesario para el flow actual de invite +
# asignación de rol post-creación (BUG-009 follow-up):
#   - read:users / create:users / update:users — gestión de cuentas
#   - create:user_tickets — Auth0 emite ticket de password-change usado
#     en el email de invitación (POST /api/v2/tickets/password-change).
#     Nombre EXACTO del scope: `create:user_tickets` — `read:tickets` es
#     un scope distinto que NO autoriza la creación de tickets (codex P1).
#   - read:roles / read:role_members / create:role_members — asignar rol
#     Auth0 al user invitado para que su JWT post-login traiga el claim
MGMT_API_AUDIENCE="https://${AUTH0_DOMAIN}/api/v2/"
# M62 — scopes extendidos para automation completa del tenant (TIER 1+2):
# DB connections, tenant settings, MFA factors, attack protection, email
# provider, email templates, Universal Login prompts.
# Si alguno falla, el bloque correspondiente soft-skipea (no aborta).
MGMT_API_SCOPES="read:users,create:users,update:users,create:user_tickets,read:roles,read:role_members,create:role_members,read:connections,update:connections,read:tenant_settings,update:tenant_settings,read:guardian_factors,update:guardian_factors,read:attack_protection,update:attack_protection,read:email_provider,create:email_provider,update:email_provider,delete:email_provider,read:email_templates,create:email_templates,update:email_templates,read:prompts,update:prompts"
echo "▶ Upsert client grant M2M hacia Management API"
mgmt_grant_id="$(jq -r --arg client_id "$service_client_id" --arg audience "$MGMT_API_AUDIENCE" '.[] | select(.client_id == $client_id and .audience == $audience) | .id' <<<"$client_grants" | head -n1)"
mgmt_grant_payload="$(jq -n --arg audience "$MGMT_API_AUDIENCE" --arg client_id "$service_client_id" --arg scopes "$MGMT_API_SCOPES" '{audience:$audience,client_id:$client_id,scope:($scopes | split(","))}')"
if [ -z "$mgmt_grant_id" ]; then
  api_post '/client-grants' "$mgmt_grant_payload" >/dev/null
  echo "  Management API grant creado con scopes: $MGMT_API_SCOPES"
else
  mgmt_patch_payload="$(jq -n --arg scopes "$MGMT_API_SCOPES" '{scope:($scopes | split(","))}')"
  api_patch "/client-grants/$mgmt_grant_id" "$mgmt_patch_payload" >/dev/null
  echo "  Management API grant actualizado con scopes: $MGMT_API_SCOPES"
fi

echo "▶ Upsert roles y permisos"
role_names=(platform_owner owner admin manager agent viewer support)

role_description() {
  case "$1" in
    platform_owner) echo 'Staff de plataforma: operación cross-tenant (fleet, system health, billing). Token unscoped.' ;;
    owner) echo 'Owner del tenant: administración total, usuarios, exportes y privacidad' ;;
    admin) echo 'Administrador del tenant: canales, documentos, prompts y settings' ;;
    manager) echo 'Manager operacional: analítica, agenda y operación' ;;
    agent) echo 'Agente humano: conversaciones, handoffs, citas y solicitudes' ;;
    viewer) echo 'Lectura operacional limitada' ;;
    support) echo 'Soporte interno auditado con acceso excepcional' ;;
    *) echo "Rol $1 CopilotoIA" ;;
  esac
}

role_permissions_for() {
  case "$1" in
    platform_owner)
      echo "$all_permission_names"
      ;;
    owner)
      echo "$all_permission_names"
      ;;
    admin)
      echo 'tenants:read,tenants:update,tenant_settings:update,channels:manage,channels:read,contacts:read,contacts:write,conversations:read,conversations:write,conversations:handoff,service_requests:read,service_requests:write,quotes:read,quotes:write,appointments:read,appointments:write,knowledge:read,knowledge:write,knowledge:index,prompts:read,prompts:write,prompts:activate,analytics:read,audit_logs:read,exports:create,privacy:manage,users:manage'
      ;;
    manager)
      echo 'tenants:read,channels:read,contacts:read,conversations:read,conversations:write,conversations:handoff,service_requests:read,service_requests:write,quotes:read,appointments:read,appointments:write,knowledge:read,prompts:read,analytics:read,audit_logs:read'
      ;;
    agent)
      echo 'contacts:read,contacts:write,conversations:read,conversations:write,conversations:handoff,service_requests:read,service_requests:write,quotes:read,quotes:write,appointments:read,appointments:write,knowledge:read,prompts:read'
      ;;
    viewer)
      echo 'tenants:read,channels:read,contacts:read,conversations:read,service_requests:read,quotes:read,appointments:read,knowledge:read,prompts:read,analytics:read,audit_logs:read'
      ;;
    support)
      echo "$all_permission_names"
      ;;
    *)
      echo ''
      ;;
  esac
}

roles_json="$(api_get '/roles?per_page=100')"
for role in "${role_names[@]}"; do
  role_id="$(jq -r --arg role "$role" '.[] | select(.name == $role) | .id' <<<"$roles_json" | head -n1)"
  role_description_text="$(role_description "$role")"
  role_permissions_csv="$(role_permissions_for "$role")"

  if [ -z "$role_id" ]; then
    role_payload="$(jq -n --arg name "$role" --arg description "$role_description_text" '{name:$name,description:$description}')"
    role_id="$(api_post '/roles' "$role_payload" | jq -r .id)"
    roles_json="$(api_get '/roles?per_page=100')"
  fi

  current_permissions="$(api_get "/roles/$role_id/permissions?per_page=100")"
  missing_permissions="$(jq -n \
    --arg csv "$role_permissions_csv" \
    --arg identifier "$AUTH0_API_IDENTIFIER" \
    --argjson current "$current_permissions" \
    '($csv | split(",") | map(select(length > 0))) as $desired |
     ($current | map(select(.resource_server_identifier == $identifier) | .permission_name)) as $existing |
     {permissions: ($desired - $existing | map({resource_server_identifier:$identifier,permission_name:.}))}')"

  if [ "$(jq '.permissions | length' <<<"$missing_permissions")" -gt 0 ]; then
    api_post "/roles/$role_id/permissions" "$missing_permissions" >/dev/null
  fi
done

if [ "$CONFIGURE_LOGIN_ACTION" = "true" ]; then
  echo "▶ Upsert Action post-login de custom claims"
  action_code="$(cat <<ACTION
exports.onExecutePostLogin = async (event, api) => {
  const namespace = '$CLAIMS_NAMESPACE';
  const appMetadata = event.user.app_metadata || {};
  const roles = event.authorization && event.authorization.roles ? event.authorization.roles : [];
  const permissions = event.authorization && event.authorization.permissions ? event.authorization.permissions : [];
  const tenantId = appMetadata.tenant_id || appMetadata.default_tenant_id;

  api.idToken.setCustomClaim(\`\${namespace}/roles\`, roles);
  api.accessToken.setCustomClaim(\`\${namespace}/roles\`, roles);
  api.accessToken.setCustomClaim(\`\${namespace}/permissions\`, permissions);

  // M60/A-003 — emitir email + email_verified en el ACCESS_TOKEN como
  // claim namespaced. Auth0 los pone en el id_token + userinfo por
  // default, pero NO en el access_token, así que el Core los recibe
  // como null. Eso forzó (en M58) un fallback al header
  // \`x-admin-user-email\` inyectado por el BFF — header SPOOFABLE para
  // un caller que pegue directo al Core. Con este claim el Core lee
  // el email directo del JWT firmado por Auth0 y no necesita el header.
  if (event.user && event.user.email) {
    api.accessToken.setCustomClaim(\`\${namespace}/email\`, event.user.email);
    api.accessToken.setCustomClaim(
      \`\${namespace}/email_verified\`,
      event.user.email_verified === true,
    );
  }

  if (tenantId) {
    api.idToken.setCustomClaim(\`\${namespace}/tenant_id\`, tenantId);
    api.accessToken.setCustomClaim(\`\${namespace}/tenant_id\`, tenantId);
  }

  if (appMetadata.tenant_slug) {
    api.idToken.setCustomClaim(\`\${namespace}/tenant_slug\`, appMetadata.tenant_slug);
    api.accessToken.setCustomClaim(\`\${namespace}/tenant_slug\`, appMetadata.tenant_slug);
  }

  if (appMetadata.support_mode === true) {
    api.accessToken.setCustomClaim(\`\${namespace}/support_mode\`, true);
  }

  // Propagar AMR (Authentication Methods References) para que la API y el
  // Admin Panel puedan verificar si el login incluyó MFA.
  // Auth0 rellena event.authentication.methods con { name: 'mfa', ... }
  // cuando el usuario completa un segundo factor.
  const methods = (event.authentication && event.authentication.methods) || [];
  const mfaCompleted = methods.some(function(m) { return m.name === 'mfa'; });
  const amr = methods.map(function(m) { return m.name; }).filter(Boolean);
  if (amr.length > 0) {
    api.idToken.setCustomClaim('amr', amr);
  }
  api.idToken.setCustomClaim(\`\${namespace}/mfa_verified\`, mfaCompleted);
  api.accessToken.setCustomClaim(\`\${namespace}/mfa_verified\`, mfaCompleted);
};
ACTION
)"

  actions_response="$(api_get '/actions/actions?triggerId=post-login&per_page=100')"
  action_id="$(jq -r '.actions // [] | .[] | select(.name == "copilotoia-post-login-claims") | .id' <<<"$actions_response" | head -n1)"
  action_payload="$(jq -n \
    --arg code "$action_code" \
    '{name:"copilotoia-post-login-claims",supported_triggers:[{id:"post-login",version:"v3"}],runtime:"node18",code:$code,deploy:true}')"

  if [ -z "$action_id" ]; then
    action_id="$(api_post '/actions/actions' "$action_payload" | jq -r .id)"
  else
    update_action_payload="$(jq -n --arg code "$action_code" '{code:$code,runtime:"node18",supported_triggers:[{id:"post-login",version:"v3"}]}')"
    api_patch "/actions/actions/$action_id" "$update_action_payload" >/dev/null
    api_post "/actions/actions/$action_id/deploy" '{}' >/dev/null
  fi

  if [ "$BIND_LOGIN_ACTION" = "true" ]; then
    echo "▶ Bind Action al flujo post-login"
    bindings_response="$(api_get '/actions/triggers/post-login/bindings?per_page=100')"
    bindings_payload="$(jq -n \
      --arg action_id "$action_id" \
      --argjson existing "$bindings_response" \
      '($existing.bindings // []) as $bindings |
       ($bindings
        | map(select(.display_name != "copilotoia-post-login-claims" and (.action.id? // .ref.value? // "") != $action_id))
        | map(
            if (.ref? and .ref.value?) then
              {ref:.ref, display_name:(.display_name // .ref.value)}
            elif (.action? and .action.id?) then
              {ref:{type:"action_id",value:.action.id}, display_name:(.display_name // .action.name // .action.id)}
            else
              empty
            end
          )) as $preserved |
       {bindings: ($preserved + [{ref:{type:"action_id",value:$action_id},display_name:"copilotoia-post-login-claims"}])}')"
    api_patch '/actions/triggers/post-login/bindings' "$bindings_payload" >/dev/null
  fi
fi

# ── MFA enforcement para roles privilegiados ──────────────────────────────
# Para obligar MFA a usuarios con rol admin/owner/platform_owner, configura
# en el Dashboard Auth0 → Security → Multi-factor Auth:
#   1. Habilita al menos un factor (TOTP/OTP app, SMS, etc.).
#   2. En "Policy" selecciona "Always" o usa una regla/Action que llame a
#      api.authentication.challengeWith({ type: 'otp' }) cuando el usuario
#      tenga un rol privilegiado:
#
#      exports.onExecutePostLogin = async (event, api) => {
#        const privilegedRoles = new Set(['admin','owner','platform_owner']);
#        const roles = (event.authorization && event.authorization.roles) || [];
#        const isPrivileged = roles.some(r => privilegedRoles.has(r));
#        if (isPrivileged) {
#          const methods = (event.authentication && event.authentication.methods) || [];
#          const hasMfa = methods.some(m => m.name === 'mfa');
#          if (!hasMfa) {
#            api.authentication.challengeWith({ type: 'otp' });
#          }
#        }
#      };
#
# 3. Asegúrate de que el Action de MFA-challenge corre ANTES del Action de
#    custom-claims en el flujo post-login para que event.authentication.methods
#    ya incluya 'mfa' cuando se lean los claims.
#
# La variable ENFORCE_MFA_ACTION (true/false) controla si este script crea
# automáticamente el Action de desafío. Default: false (solo documenta).
ENFORCE_MFA_ACTION="${ENFORCE_MFA_ACTION:-false}"

if [ "$ENFORCE_MFA_ACTION" = "true" ] && [ "$CONFIGURE_LOGIN_ACTION" = "true" ]; then
  echo "▶ Upsert Action MFA-challenge para roles privilegiados"
  # BUG-065: respetar el factor MFA enrolado del usuario en vez de
  # hardcodear OTP. Si el usuario está enrolado con WebAuthn/push/SMS y la
  # Action exige OTP, Auth0 falla con "factors not properly set up" y el
  # login queda bloqueado. Pattern recomendado: leer
  # `event.user.enrolledFactors` (filtrar `status === 'confirmed'`) y
  # llamar `challengeWithAny([...])` con los enrolados; si NO hay ninguno
  # usar `enrollWithAny([...])` para que Auth0 muestre la pantalla de
  # setup MFA (QR code) automáticamente — `challengeWith` con un factor
  # no enrolado tira "Two-factor authentication is required... contact
  # your system administrator" (M62 hotfix #8).
  # M62 hotfix #11 — heredoc con quotes single ('MFA_ACTION') para evitar
  # expansion de bash. Sin las quotes, bash 3.2 de macOS (default) parsea
  # los caracteres Unicode (→, acentos) + paréntesis dentro de comentarios
  # como command substitution y tira "bad substitution: no closing ')'".
  # No necesitamos expansion en este heredoc (no hay variables del shell
  # a interpolar). Comparar con el heredoc del custom-claims Action que
  # SÍ necesita expansion para $CLAIMS_NAMESPACE → ese queda sin quotes.
  mfa_action_code="$(cat <<'MFA_ACTION'
exports.onExecutePostLogin = async (event, api) => {
  const privilegedRoles = new Set(['admin','owner','platform_owner']);
  const roles = (event.authorization && event.authorization.roles) || [];
  const isPrivileged = roles.some(function(r) { return privilegedRoles.has(r); });
  if (!isPrivileged) return;
  const methods = (event.authentication && event.authentication.methods) || [];
  const hasMfa = methods.some(function(m) { return m.name === 'mfa'; });
  if (hasMfa) return;
  // BUG-065 + M62 hotfix #8: respeta el factor enrolado del usuario.
  // Si hay enrolados → challengeWithAny (verificación).
  // Si NO hay → enrollWithAny (setup interactivo con QR code).
  const enrolled = ((event.user && event.user.enrolledFactors) || [])
    .filter(function(f) { return f && f.status === 'confirmed'; })
    .map(function(f) { return { type: f.type }; });
  if (enrolled.length > 0) {
    api.authentication.challengeWithAny(enrolled);
  } else {
    // Primer login del user con rol privilegiado — no tiene factor
    // enrolado todavía. Forzamos OTP (Google Authenticator / Authy /
    // 1Password / etc.) porque es el único factor que funciona sin
    // HTTPS — el resto (webauthn-platform, webauthn-roaming) requiere
    // HTTPS en producción. En localhost algunos browsers también
    // restringen WebAuthn → Auth0 tira "invalid_request" (M62 hotfix #9).
    //
    // Una vez enrolado OTP, el user puede agregar factores adicionales
    // desde Auth0 dashboard → Profile → Security.
    api.authentication.enrollWith({ type: 'otp' });
  }
};
MFA_ACTION
)"
  mfa_actions_response="$(api_get '/actions/actions?triggerId=post-login&per_page=100')"
  mfa_action_id="$(jq -r '.actions // [] | .[] | select(.name == "copilotoia-mfa-challenge") | .id' <<<"$mfa_actions_response" | head -n1)"
  mfa_action_payload="$(jq -n \
    --arg code "$mfa_action_code" \
    '{name:"copilotoia-mfa-challenge",supported_triggers:[{id:"post-login",version:"v3"}],runtime:"node18",code:$code,deploy:true}')"

  if [ -z "$mfa_action_id" ]; then
    mfa_action_id="$(api_post '/actions/actions' "$mfa_action_payload" | jq -r .id)"
    echo "  Action MFA-challenge creado: $mfa_action_id"
  else
    update_mfa_payload="$(jq -n --arg code "$mfa_action_code" '{code:$code,runtime:"node18",supported_triggers:[{id:"post-login",version:"v3"}]}')"
    api_patch "/actions/actions/$mfa_action_id" "$update_mfa_payload" >/dev/null
    api_post "/actions/actions/$mfa_action_id/deploy" '{}' >/dev/null
    echo "  Action MFA-challenge actualizado: $mfa_action_id"
  fi

  if [ "$BIND_LOGIN_ACTION" = "true" ]; then
    echo "▶ Bind Action MFA-challenge al flujo post-login (debe ir antes de custom-claims)"
    mfa_bindings_response="$(api_get '/actions/triggers/post-login/bindings?per_page=100')"
    mfa_bindings_payload="$(jq -n \
      --arg mfa_id "$mfa_action_id" \
      --argjson existing "$mfa_bindings_response" \
      '($existing.bindings // []) as $bindings |
       ($bindings
        | map(select(.display_name != "copilotoia-mfa-challenge" and (.action.id? // .ref.value? // "") != $mfa_id))
        | map(
            if (.ref? and .ref.value?) then
              {ref:.ref, display_name:(.display_name // .ref.value)}
            elif (.action? and .action.id?) then
              {ref:{type:"action_id",value:.action.id}, display_name:(.display_name // .action.name // .action.id)}
            else
              empty
            end
          )) as $preserved |
       # MFA challenge va primero, luego los demás bindings existentes
       {bindings: ([{ref:{type:"action_id",value:$mfa_id},display_name:"copilotoia-mfa-challenge"}] + $preserved)}')"
    api_patch '/actions/triggers/post-login/bindings' "$mfa_bindings_payload" >/dev/null
    echo "  MFA-challenge enlazado al inicio del flujo post-login"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# M62 — Automation completa del tenant (TIER 1 + TIER 2)
# Todas las secciones son idempotentes + fail-soft. Si el M2M no tiene el
# scope necesario, loguea warning y skipea (no aborta).
# ════════════════════════════════════════════════════════════════════════════

# ─── (1) Tenant settings ────────────────────────────────────────────────────
# friendly_name aparece en la pantalla de login.
# support_url/email los muestra en errores y emails.
# session_lifetime + idle_session_lifetime limitan la SSO session de Auth0
# (distinto del access_token del admin app, que vive 2h por jwt_configuration).
if [ "$CONFIGURE_TENANT_SETTINGS" = "true" ]; then
  echo "▶ Tenant settings (friendly_name + support + session TTL)"
  tenant_payload="$(jq -n \
    --arg name "$TENANT_FRIENDLY_NAME" \
    --arg email "$TENANT_SUPPORT_EMAIL" \
    --arg url "$TENANT_SUPPORT_URL" \
    --argjson session_h "$TENANT_SESSION_LIFETIME_HRS" \
    --argjson idle_h "$TENANT_IDLE_SESSION_HRS" \
    '{
      friendly_name: $name,
      support_email: $email,
      support_url: $url,
      session_lifetime: $session_h,
      idle_session_lifetime: $idle_h,
      flags: {
        revoke_refresh_token_grant: true,
        disable_clickjack_protection_headers: false
      }
    }')"
  if api_patch_soft '/tenants/settings' "$tenant_payload" 'PATCH /tenants/settings' >/dev/null; then
    echo "  ✓ friendly_name='$TENANT_FRIENDLY_NAME' session=${TENANT_SESSION_LIFETIME_HRS}h idle=${TENANT_IDLE_SESSION_HRS}h"
  fi
fi

# ─── (2) Universal Login → new ──────────────────────────────────────────────
# Auth0 tiene dos versiones de Universal Login: "classic" (UI 2018, no
# responsive) y "new" (responsive, customizable via Liquid templates).
# Para producción siempre new — classic ya no recibe features de Auth0.
if [ "$CONFIGURE_UNIVERSAL_LOGIN" = "true" ]; then
  echo "▶ Universal Login → new experience"
  ul_payload='{"universal_login_experience":"new","identifier_first":true,"webauthn_platform_first_factor":false}'
  if api_patch_soft '/prompts' "$ul_payload" 'PATCH /prompts' >/dev/null; then
    echo "  ✓ Universal Login = new + identifier_first=true (mejor UX)"
  fi
fi

# ─── (3) Database Connection + password policy ──────────────────────────────
# La connection "Username-Password-Authentication" viene creada por default
# en cada tenant Auth0 nuevo. Pero NO está habilitada por default para apps
# nuevas — hay que agregarla a `enabled_clients`. Sin esto, la app admin no
# aparece en la connection y los login email/password fallan con
# "invalid_client" sin mensaje claro.
#
# Además seteamos:
# - password_policy: fair (≥8 chars) / good (+1 num, +1 special) / excellent
#   (+1 mayúscula). Default good = compromiso UX/seguridad.
# - password_history: no permite reusar últimas N contraseñas.
# - brute_force_protection: bloquea cuenta tras N intentos fallidos.
if [ "$CONFIGURE_DB_CONNECTION" = "true" ]; then
  echo "▶ Database Connection (Username-Password-Authentication)"
  connections_response="$(api_get_soft '/connections?strategy=auth0&per_page=100' 'GET /connections')"
  if [ -n "$connections_response" ]; then
    db_conn_id="$(jq -r '.[] | select(.name == "Username-Password-Authentication") | .id' <<<"$connections_response" | head -n1)"
    if [ -z "$db_conn_id" ]; then
      echo "  ⚠ Connection 'Username-Password-Authentication' no existe en el tenant." >&2
      echo "    Es un default pero algunos tenants legacy la borraron." >&2
      echo "    Crearla manual: Auth0 Dashboard → Authentication → Database → Create DB Connection." >&2
    else
      # Auth0 dividió la API de connections — antes podías PATCH la
      # connection completa (options + enabled_clients en un solo payload).
      # Algunos tenants ya migraron a la API nueva que REJECTA enabled_clients
      # como "Additional properties not allowed". Por eso hacemos 2 PATCH
      # separados:
      #   (a) PATCH solo options (siempre funciona en ambas APIs).
      #   (b) PATCH solo enabled_clients (soft-fallback — si tira 400,
      #       el operator habilita manual en dashboard).

      # (a) Password policy + protección (always-works PATCH).
      options_payload="$(jq -n \
        --arg pwd_policy "$DB_PASSWORD_POLICY" \
        --argjson pwd_history "$DB_PASSWORD_HISTORY_SIZE" \
        --argjson brute_force "$DB_BRUTE_FORCE_PROTECTION" \
        '{
          options: {
            passwordPolicy: $pwd_policy,
            password_history: { enable: true, size: $pwd_history },
            password_no_personal_info: { enable: true },
            password_dictionary: { enable: true, dictionary: [] },
            password_complexity_options: { min_length: 8 },
            brute_force_protection: $brute_force,
            disable_signup: false,
            requires_username: false
          }
        }')"
      if api_patch_soft "/connections/$db_conn_id" "$options_payload" 'PATCH connection options' >/dev/null; then
        echo "  ✓ Password policy=$DB_PASSWORD_POLICY history=$DB_PASSWORD_HISTORY_SIZE brute_force=$DB_BRUTE_FORCE_PROTECTION"
      fi

      # (b) enabled_clients — preservar existentes + agregar admin. El M2M
      # NO va acá (usa client_credentials, no DB).
      existing_clients_json="$(jq -c --arg id "$db_conn_id" \
        '[.[] | select(.id == $id) | .enabled_clients // []] | .[0] // []' \
        <<<"$connections_response")"
      admin_already_enabled="$(jq --arg c "$admin_client_id" 'any(. == $c)' <<<"$existing_clients_json")"

      if [ "$admin_already_enabled" = "true" ]; then
        echo "  ✓ Connection ya tiene admin client '$AUTH0_ADMIN_APP_NAME' habilitado"
      else
        clients_payload="$(jq -n \
          --arg admin_client "$admin_client_id" \
          --argjson existing "$existing_clients_json" \
          '{enabled_clients: ($existing + [$admin_client] | unique)}')"
        if api_patch_soft "/connections/$db_conn_id" "$clients_payload" 'PATCH connection enabled_clients' >/dev/null; then
          echo "  ✓ Admin client '$AUTH0_ADMIN_APP_NAME' agregado a la connection"
        else
          echo "  ⓘ Tu tenant Auth0 rechaza enabled_clients via PATCH (API nueva)."
          echo "    Habilitar manual: Auth0 Dashboard → Authentication → Database →"
          echo "    Username-Password-Authentication → Applications → toggle ON"
          echo "    para '$AUTH0_ADMIN_APP_NAME'. Una sola vez, después queda."
        fi
      fi
    fi
  fi
fi

# ─── (4) MFA factors enablement ─────────────────────────────────────────────
# Auth0 soporta varios factores MFA: otp (TOTP apps como Google Auth o 1Pwd),
# webauthn-roaming (YubiKey), webauthn-platform (Face ID, Touch ID, Windows
# Hello), push (Auth0 Guardian app), sms (no recomendado por SIM swap), etc.
# Para que la Action de MFA-challenge (ENFORCE_MFA_ACTION) funcione, AL MENOS
# UN factor debe estar habilitado en el tenant.
if [ "$CONFIGURE_MFA_FACTORS" = "true" ]; then
  echo "▶ MFA factors (OTP + WebAuthn)"
  for factor in otp webauthn-roaming webauthn-platform; do
    factor_payload='{"enabled":true}'
    if api_put_soft "/guardian/factors/$factor" "$factor_payload" "PUT /guardian/factors/$factor" >/dev/null; then
      echo "  ✓ Factor '$factor' habilitado"
    fi
  done
  # Push (Auth0 Guardian app) deshabilitado por default — requiere setup
  # adicional con APNs/FCM credentials. Habilitar manualmente si querés
  # ofrecer la Auth0 Guardian app como factor.

  # M62 hotfix #10 — la MFA Action (`enrollWith`/`challengeWith`) NO
  # funciona si la MFA Policy del tenant está vacía. Auth0 rechaza con:
  #   "MFA customized via PostLogin action but feature is not enabled"
  #
  # Hay 2 niveles separados:
  #   - Factores (/guardian/factors/*): OTP, WebAuthn, etc. → QUÉ podés usar
  #   - Policy (/guardian/policies): all-applications, confidence-score, [] → SI MFA aplica
  #
  # Para que las Actions puedan custom-trigger MFA, la policy NO puede
  # estar vacía. Default `all-applications` si ENFORCE_MFA_ACTION=true
  # y el operator no overrideó MFA_POLICY explícito.
  effective_mfa_policy="$MFA_POLICY"
  if [ -z "$effective_mfa_policy" ] && [ "$ENFORCE_MFA_ACTION" = "true" ]; then
    effective_mfa_policy="all-applications"
    echo "  ⓘ MFA_POLICY auto-seteado a 'all-applications' (requerido por Action MFA-challenge)"
    echo "    Para desactivar globalmente, pasá MFA_POLICY='none' explícito (la Action queda inutilizable)."
  fi

  if [ "$effective_mfa_policy" = "none" ] || [ -z "$effective_mfa_policy" ]; then
    # Operator pidió explícitamente "ninguna policy" — vaciar.
    if api_put_soft '/guardian/policies' '[]' 'PUT /guardian/policies (empty)' >/dev/null; then
      echo "  ⓘ MFA Policy desactivada (Action MFA-challenge NO funcionará)"
    fi
  else
    echo "▶ MFA policy = $effective_mfa_policy"
    policy_payload="[\"$effective_mfa_policy\"]"
    if api_put_soft '/guardian/policies' "$policy_payload" 'PUT /guardian/policies' >/dev/null; then
      echo "  ✓ MFA enforced via tenant policy ($effective_mfa_policy)"
    fi
  fi
fi

# ─── (5) Attack protection (brute force + breached password + IP) ──────────
# Auth0 ofrece tres capas de "attack protection":
# - brute-force-protection: bloquea cuenta tras N intentos fallidos.
# - breached-password-detection: chequea contra HaveIBeenPwned al login.
# - suspicious-ip-throttling: throttle de IPs con patrones anómalos.
# Todas free, todas críticas para producción.
if [ "$CONFIGURE_ATTACK_PROTECTION" = "true" ]; then
  echo "▶ Attack protection (brute force + breached password + IP throttling)"

  bf_payload='{
    "enabled": true,
    "shields": ["block", "user_notification"],
    "allowlist": [],
    "mode": "count_per_identifier_and_ip",
    "max_attempts": 10
  }'
  if api_patch_soft '/attack-protection/brute-force-protection' "$bf_payload" 'PATCH brute-force-protection' >/dev/null; then
    echo "  ✓ Brute force protection (max 10 attempts → block + email user)"
  fi

  bp_payload='{
    "enabled": true,
    "shields": ["block", "admin_notification"],
    "admin_notification_frequency": ["immediately"],
    "method": "standard",
    "stage": {
      "pre-user-registration": { "shields": ["block"] },
      "pre-change-password": { "shields": ["block"] }
    }
  }'
  if api_patch_soft '/attack-protection/breached-password-detection' "$bp_payload" 'PATCH breached-password-detection' >/dev/null; then
    echo "  ✓ Breached password detection (HaveIBeenPwned: block signup + reset)"
  fi

  sip_payload='{
    "enabled": true,
    "shields": ["block", "admin_notification"],
    "allowlist": [],
    "stage": {
      "pre-login":          { "max_attempts": 100, "rate": 864000 },
      "pre-user-registration": { "max_attempts": 50, "rate": 1200 }
    }
  }'
  if api_patch_soft '/attack-protection/suspicious-ip-throttling' "$sip_payload" 'PATCH suspicious-ip-throttling' >/dev/null; then
    echo "  ✓ Suspicious IP throttling (100 logins/día per IP)"
  fi
fi

# ─── (6) Resend como Email Provider del tenant Auth0 ────────────────────────
# Por default Auth0 manda emails (verify, reset, blocked, change_password)
# con su propio sender genérico (no@auth0user.net) que cae a spam.
# Configurar Resend como SMTP custom hace que TODOS los emails de Auth0
# salgan desde TU dominio verificado (mismo que usa M61 para invitaciones).
#
# Resend expone SMTP en `smtp.resend.com:587` con username='resend' +
# password=<RESEND_API_KEY>. Auth0 lo soporta como "smtp" provider.
if [ "$CONFIGURE_RESEND_PROVIDER" = "true" ]; then
  if [ -z "$RESEND_API_KEY" ]; then
    echo "▶ Email Provider (Resend) — SKIPEADO (RESEND_API_KEY vacío)" >&2
  else
    echo "▶ Email Provider (Resend SMTP)"
    # Auth0 puede tener un provider previo (sendgrid, mailgun, default) que
    # hay que reemplazar. La API es:
    # - GET /emails/provider → consulta config actual
    # - PATCH para actualizar (si existe)
    # - POST si no existe
    existing_provider="$(api_get_soft '/emails/provider' 'GET /emails/provider' || echo '{}')"
    has_provider="$(jq -r '.name // ""' <<<"$existing_provider")"

    provider_payload="$(jq -n \
      --arg from "$EMAIL_FROM_NAME <$EMAIL_FROM_ADDRESS>" \
      --arg key "$RESEND_API_KEY" \
      '{
        name: "smtp",
        enabled: true,
        default_from_address: $from,
        credentials: {
          smtp_host: "smtp.resend.com",
          smtp_port: 587,
          smtp_user: "resend",
          smtp_pass: $key
        }
      }')"

    if [ -z "$has_provider" ]; then
      if api_post_soft '/emails/provider' "$provider_payload" 'POST /emails/provider' >/dev/null; then
        echo "  ✓ Resend SMTP provider creado (from='$EMAIL_FROM_NAME <$EMAIL_FROM_ADDRESS>')"
      fi
    else
      # Si era un provider distinto (sendgrid, etc.), borrar primero.
      if [ "$has_provider" != "smtp" ]; then
        api_delete_soft '/emails/provider' 'DELETE /emails/provider' >/dev/null || true
        if api_post_soft '/emails/provider' "$provider_payload" 'POST /emails/provider' >/dev/null; then
          echo "  ✓ Provider reemplazado de '$has_provider' a Resend SMTP"
        fi
      else
        if api_patch_soft '/emails/provider' "$provider_payload" 'PATCH /emails/provider' >/dev/null; then
          echo "  ✓ Resend SMTP provider actualizado"
        fi
      fi
    fi
    echo "  ⓘ Asegurate que el dominio de '$EMAIL_FROM_ADDRESS' esté VERIFICADO en https://resend.com/domains"
  fi
fi

# ─── (7) Email templates branded en español ────────────────────────────────
# Auth0 tiene 7 templates default (en inglés): verify_email, reset_email,
# welcome_email, blocked_account, stolen_credentials, enrollment_email,
# mfa_oob_code. Los renderizamos con subjects + texto en español.
# El BODY (HTML) lo deja por default — para customizarlo en serio hay que
# editar el Liquid template, que es un proyecto aparte (out-of-scope acá).
if [ "$CONFIGURE_EMAIL_TEMPLATES" = "true" ]; then
  echo "▶ Email templates (subjects + from name en español)"

  # macOS ships bash 3.2 por default (sin `declare -A` associative arrays).
  # Para compat universal usamos lookup vía case (mismo pattern que
  # role_description / role_permissions_for).
  template_subject_for() {
    case "$1" in
      verify_email)         echo "Verifica tu correo en $TENANT_FRIENDLY_NAME" ;;
      reset_email)          echo "Restablece tu contraseña en $TENANT_FRIENDLY_NAME" ;;
      welcome_email)        echo "Bienvenido a $TENANT_FRIENDLY_NAME" ;;
      blocked_account)      echo "Tu cuenta de $TENANT_FRIENDLY_NAME fue bloqueada" ;;
      stolen_credentials)   echo "Detectamos un intento sospechoso de acceso a tu cuenta" ;;
      enrollment_email)     echo "Configura tu segundo factor de autenticación" ;;
      mfa_oob_code)         echo "Tu código de verificación de $TENANT_FRIENDLY_NAME" ;;
      *)                    echo "$TENANT_FRIENDLY_NAME" ;;
    esac
  }

  template_names=(verify_email reset_email welcome_email blocked_account stolen_credentials enrollment_email mfa_oob_code)

  # Bodies Liquid específicos por template — CRÍTICO usar las variables
  # que Auth0 expone para CADA template (no son universales). Si pasás
  # una variable que no existe en el contexto del template (ej.
  # `{{ message.text }}` que NO existe en Auth0), Liquid la renderiza
  # vacía y el email llega en blanco (M62 hotfix #6).
  #
  # Variables documentadas por Auth0:
  #   verify_email/reset_email/blocked_account/stolen_credentials/
  #   enrollment_email: {{ url }} (link de acción), {{ user.email }},
  #                     {{ user.name }}, {{ application.name }},
  #                     {{ friendly_name }}
  #   welcome_email:    {{ user.name }}, {{ application.name }}
  #   mfa_oob_code:     {{ code }}, {{ user.email }}
  #
  # Templates HTML mínimos pero funcionales — el operator puede
  # customizar en dashboard sin perder el subject + from que seteamos
  # (Auth0 los preserva en el PATCH posterior).
  template_body_for() {
    case "$1" in
      verify_email)
        cat <<'TPL'
<p>Hola {{ user.email }},</p>
<p>Bienvenido a {{ application.name }}. Para activar tu cuenta, verificá tu correo electrónico haciendo clic en el siguiente enlace:</p>
<p><a href="{{ url }}">Verificar correo electrónico</a></p>
<p>Si no creaste esta cuenta, ignorá este mensaje.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      reset_email)
        cat <<'TPL'
<p>Hola,</p>
<p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en {{ application.name }}.</p>
<p>Hacé clic en el siguiente enlace para crear una nueva contraseña:</p>
<p><a href="{{ url }}">Restablecer contraseña</a></p>
<p>Si no solicitaste esto, ignorá este mensaje — tu contraseña actual seguirá siendo válida.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      welcome_email)
        cat <<'TPL'
<p>¡Hola {{ user.name }}!</p>
<p>Bienvenido a {{ application.name }}. Tu cuenta ya está lista para usar.</p>
<p>Si tenés dudas, escribinos respondiendo este correo.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      blocked_account)
        cat <<'TPL'
<p>Hola,</p>
<p>Tu cuenta de {{ application.name }} fue bloqueada por motivos de seguridad luego de detectar múltiples intentos fallidos de inicio de sesión.</p>
<p>Si fuiste vos quien intentó iniciar sesión, podés desbloquear tu cuenta haciendo clic en:</p>
<p><a href="{{ url }}">Desbloquear cuenta</a></p>
<p>Si no reconocés esta actividad, te recomendamos cambiar tu contraseña inmediatamente.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      stolen_credentials)
        cat <<'TPL'
<p>Hola,</p>
<p>Detectamos un intento de inicio de sesión en {{ application.name }} con credenciales que pudieron haber sido comprometidas en una brecha de datos externa.</p>
<p>Por tu seguridad, te recomendamos cambiar tu contraseña inmediatamente:</p>
<p><a href="{{ url }}">Cambiar contraseña</a></p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      enrollment_email)
        cat <<'TPL'
<p>Hola,</p>
<p>Para completar la configuración de la verificación en dos pasos (MFA) en tu cuenta de {{ application.name }}, hacé clic en el siguiente enlace:</p>
<p><a href="{{ url }}">Configurar MFA</a></p>
<p>Una vez configurado, vas a necesitar tu segundo factor cada vez que inicies sesión.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      mfa_oob_code)
        cat <<'TPL'
<p>Hola,</p>
<p>Tu código de verificación para {{ application.name }} es:</p>
<p style="font-size:28px;font-weight:700;letter-spacing:4px;text-align:center;padding:16px;background:#f4f5f7;border-radius:6px;">{{ code }}</p>
<p>Este código expira en pocos minutos. Si no estás intentando iniciar sesión, ignorá este mensaje.</p>
<p>— Equipo de {{ friendly_name }}</p>
TPL
        ;;
      *)
        echo '<p>Mensaje de {{ application.name }}.</p>'
        ;;
    esac
  }

  # Auth0 rechaza setear `from` en templates si NO hay email provider
  # activo (tira "From address cannot be set without an enabled email
  # provider"). Detectamos el state para construir el payload sin `from`
  # en ese caso — igual seteamos subjects ES (que SÍ funcionan sin
  # provider; Auth0 manda con su sender default no@auth0user.net).
  provider_state="$(api_get_soft '/emails/provider' 'GET email provider (template check)' 2>/dev/null || echo '{}')"
  provider_enabled="$(jq -r '.enabled // false' <<<"$provider_state")"
  if [ "$provider_enabled" != "true" ]; then
    include_from_in_templates=false
    echo "  ⓘ Sin email provider activo — templates se setean sin 'from' field."
    echo "    Auth0 usará su sender default (no@auth0user.net) — los emails"
    echo "    pueden caer a spam. Para sender propio: CONFIGURE_RESEND_PROVIDER=true"
    echo "    RESEND_API_KEY=re_xxx bash $0"
  else
    include_from_in_templates=true
  fi

  for template_name in "${template_names[@]}"; do
    template_subject="$(template_subject_for "$template_name")"
    template_body="$(template_body_for "$template_name")"

    # POST body: template name VA EN EL PAYLOAD, no en el path. El field
    # `from` solo se incluye si hay provider activo.
    # PATCH body: ahora INCLUYE el body para forzar re-render con el
    # template ES correcto (los templates de runs previos quedaron con
    # `{{ message.text }}` que renderiza vacío — hotfix #6).
    if [ "$include_from_in_templates" = "true" ]; then
      create_payload="$(jq -n \
        --arg name "$template_name" \
        --arg subject "$template_subject" \
        --arg from "$EMAIL_FROM_NAME <$EMAIL_FROM_ADDRESS>" \
        --arg body "$template_body" \
        '{template:$name, subject:$subject, from:$from, resultUrl:"", syntax:"liquid", body:$body, enabled:true}')"
      update_payload="$(jq -n \
        --arg subject "$template_subject" \
        --arg from "$EMAIL_FROM_NAME <$EMAIL_FROM_ADDRESS>" \
        --arg body "$template_body" \
        '{subject:$subject, from:$from, body:$body, enabled:true}')"
    else
      create_payload="$(jq -n \
        --arg name "$template_name" \
        --arg subject "$template_subject" \
        --arg body "$template_body" \
        '{template:$name, subject:$subject, resultUrl:"", syntax:"liquid", body:$body, enabled:true}')"
      update_payload="$(jq -n \
        --arg subject "$template_subject" \
        --arg body "$template_body" \
        '{subject:$subject, body:$body, enabled:true}')"
    fi

    # API contract Auth0:
    #   GET /email-templates/{name} → 200 si existe, 404 si no.
    #   POST /email-templates (body trae template name) → crea.
    #   PATCH /email-templates/{name} → actualiza existing.
    template_exists="$(api_get_soft "/email-templates/$template_name" "GET /email-templates/$template_name" 2>/dev/null || true)"
    if [ -n "$template_exists" ] && [ "$(jq -r '.template // ""' <<<"$template_exists")" = "$template_name" ]; then
      api_patch_soft "/email-templates/$template_name" "$update_payload" "PATCH template/$template_name" >/dev/null \
        && echo "  ✓ Template '$template_name' actualizado (subject + body ES)"
    else
      api_post_soft '/email-templates' "$create_payload" "POST template (create $template_name)" >/dev/null \
        && echo "  ✓ Template '$template_name' creado (subject + body ES)"
    fi
  done
fi

# ─── (8) Account Linking Action (auto-link por email verificado) ───────────
# Sin esto, si un user se loguea primero con Google (mismo email) y luego
# se registra con email/password (o viceversa), Auth0 crea DOS users
# distintos. Eso rompe M57 reconciliation (que busca por email) y deja al
# user con 2 identidades + 2 membresías separadas.
#
# Auth0 recomienda el Pre-User-Registration Hook o un Post-Login Action que
# detecte email-match y haga link via Management API. Usamos Action porque
# corre POST autenticación (más seguro: el email ya está verificado).
#
# Pattern: https://auth0.com/docs/customize/actions/flows-and-triggers/
#         login-flow/redirect-with-actions#account-linking
if [ "$CONFIGURE_ACCOUNT_LINKING" = "true" ] && [ "$CONFIGURE_LOGIN_ACTION" = "true" ]; then
  echo "▶ Action: Account Linking (auto-link por email verificado)"
  # Misma protección que MFA_ACTION (hotfix #11): quotes single para que
  # bash 3.2 no parsee paréntesis dentro de comentarios JS + caracteres
  # Unicode como command substitution. Este Action tampoco necesita
  # expansion de variables del shell (los `event.secrets.*` los inyecta
  # Auth0 runtime, no bash).
  linking_action_code="$(cat <<'LINKING_ACTION'
/**
 * Auto-link de identidades del mismo email verificado en distintas
 * connections (Google + email/password, etc.). Sin esto, Auth0 crea
 * users separados y rompe M57 reconciliation.
 *
 * Flow:
 *   1. Si el user actual NO tiene email_verified=true → skip (sin verif
 *      no podemos confiar que el email es realmente suyo, link sería
 *      account-takeover via signup).
 *   2. Lookup otros users con el mismo email (y email_verified=true).
 *   3. Si hay match: linkear el current al user "primary" más antiguo.
 *      El user actual queda como secondary (sus identidades suman).
 *   4. Continuar el login normal (las claims se emiten del PRIMARY).
 *
 * Requiere scope en el Action: read:users + update:users.
 */
const ManagementClient = require('auth0').ManagementClient;

exports.onExecutePostLogin = async (event, api) => {
  if (!event.user.email || event.user.email_verified !== true) return;
  // Skip si ya es secondary (ya linkeado).
  if (event.user.user_id && event.user.user_id.indexOf('|') === -1) return;
  const currentConnection = (event.connection && event.connection.strategy) || '';

  const mgmt = new ManagementClient({
    domain: event.secrets.AUTH0_DOMAIN,
    clientId: event.secrets.AUTH0_M2M_CLIENT_ID,
    clientSecret: event.secrets.AUTH0_M2M_CLIENT_SECRET,
  });

  let candidates;
  try {
    candidates = await mgmt.usersByEmail.getByEmail({ email: event.user.email });
  } catch (e) {
    console.log('account-linking: getByEmail error', e.message);
    return;
  }
  const verifiedOthers = (candidates.data || candidates || []).filter(function(u) {
    return u.user_id !== event.user.user_id && u.email_verified === true;
  });
  if (verifiedOthers.length === 0) return;

  // Primary = más viejo (created_at asc). Esto preserva el user_id histórico
  // que aparezca en audit logs antiguos como "owner" de la identidad.
  verifiedOthers.sort(function(a, b) {
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
  const primary = verifiedOthers[0];

  try {
    const [providerStrategy, providerUserIdRaw] = event.user.user_id.split('|');
    const secondaryProvider = providerStrategy;
    const secondaryUserId = providerUserIdRaw;
    await mgmt.users.link({ id: primary.user_id }, {
      provider: secondaryProvider,
      user_id: secondaryUserId,
    });
    console.log('account-linking: linked', event.user.user_id, '→', primary.user_id);
    // Re-emitir claims desde el PRIMARY. api.user.setUser no existe en post-login;
    // lo que sí podemos: redirect-to-app con primary_user_id en query para que
    // el BFF lo use. Como alternativa simpler, dejamos que el próximo login del
    // user use el primary (el current login ya está casi resuelto).
  } catch (e) {
    console.log('account-linking: link failed', e.message);
  }
};
LINKING_ACTION
)"

  linking_actions_response="$(api_get_soft '/actions/actions?triggerId=post-login&per_page=100' 'GET actions' || echo '{}')"
  if [ "$(jq -r '.actions // [] | length' <<<"$linking_actions_response")" != "0" ] || true; then
    linking_action_id="$(jq -r '.actions // [] | .[] | select(.name == "copilotoia-account-linking") | .id' <<<"$linking_actions_response" | head -n1)"
    linking_action_payload="$(jq -n \
      --arg code "$linking_action_code" \
      --arg domain "$AUTH0_DOMAIN" \
      --arg cid "$service_client_id" \
      --arg secret "$service_client_secret" \
      '{
        name: "copilotoia-account-linking",
        supported_triggers: [{id:"post-login",version:"v3"}],
        runtime: "node18",
        code: $code,
        deploy: true,
        dependencies: [{name:"auth0", version:"4.0.0"}],
        secrets: [
          {name:"AUTH0_DOMAIN", value:$domain},
          {name:"AUTH0_M2M_CLIENT_ID", value:$cid},
          {name:"AUTH0_M2M_CLIENT_SECRET", value:$secret}
        ]
      }')"

    linking_action_action_taken=""
    if [ -z "$linking_action_id" ]; then
      result="$(api_post_soft '/actions/actions' "$linking_action_payload" 'POST actions (linking)')"
      if [ -n "$result" ]; then
        linking_action_id="$(jq -r .id <<<"$result")"
        echo "  ✓ Action account-linking creado: $linking_action_id"
        linking_action_action_taken="created"
      fi
    else
      update_linking="$(jq -n --arg code "$linking_action_code" --arg domain "$AUTH0_DOMAIN" --arg cid "$service_client_id" --arg secret "$service_client_secret" \
        '{code:$code, runtime:"node18", supported_triggers:[{id:"post-login",version:"v3"}],
          dependencies:[{name:"auth0",version:"4.0.0"}],
          secrets:[{name:"AUTH0_DOMAIN",value:$domain},{name:"AUTH0_M2M_CLIENT_ID",value:$cid},{name:"AUTH0_M2M_CLIENT_SECRET",value:$secret}]}')"
      if api_patch_soft "/actions/actions/$linking_action_id" "$update_linking" 'PATCH actions (linking)' >/dev/null; then
        echo "  ✓ Action account-linking actualizado"
        linking_action_action_taken="updated"
      fi
    fi

    # M62 hotfix #3 — Action con `dependencies:['auth0']` requiere build
    # async server-side. Lifecycle correcto:
    #   1. PATCH actualiza el DRAFT → status='pending'/'building'.
    #   2. Wait hasta status='built' (Auth0 termina npm install).
    #   3. POST /deploy promueve el draft built a versión deployed activa.
    #   4. PATCH bindings ya puede apuntar al action_id.
    # Si llamáramos /deploy antes del wait, Auth0 rechaza con
    # "A draft must be in the 'built' state before it can be deployed."
    if [ -n "$linking_action_id" ] && [ -n "$linking_action_action_taken" ]; then
      echo "  ⏳ Esperando build del Action (deps npm: auth0)..."
      if wait_action_built "$linking_action_id" "account-linking"; then
        # Ahora el draft está built — promovemos a versión deployed.
        if api_post_soft "/actions/actions/$linking_action_id/deploy" '{}' "deploy account-linking" >/dev/null; then
          echo "  ✓ Action account-linking built + deployed"
        else
          echo "  ⓘ Build OK pero /deploy falló — la versión previamente deployed sigue activa." >&2
        fi
      else
        echo "  ⚠ Build no completó en 60s — bind se intentará pero puede usar versión vieja. Re-correr en 1min." >&2
      fi
    fi

    # Bindear al inicio del flow post-login (ANTES de claims + MFA challenge).
    if [ "$BIND_LOGIN_ACTION" = "true" ] && [ -n "$linking_action_id" ]; then
      echo "▶ Bind account-linking primero en post-login bindings"
      link_bindings_response="$(api_get_soft '/actions/triggers/post-login/bindings?per_page=100' 'GET bindings' || echo '{"bindings":[]}')"
      link_bindings_payload="$(jq -n \
        --arg link_id "$linking_action_id" \
        --argjson existing "$link_bindings_response" \
        '($existing.bindings // []) as $bindings |
         ($bindings
          | map(select(.display_name != "copilotoia-account-linking" and (.action.id? // .ref.value? // "") != $link_id))
          | map(
              if (.ref? and .ref.value?) then
                {ref:.ref, display_name:(.display_name // .ref.value)}
              elif (.action? and .action.id?) then
                {ref:{type:"action_id",value:.action.id}, display_name:(.display_name // .action.name // .action.id)}
              else
                empty
              end
            )) as $preserved |
         # account-linking debe correr ANTES que MFA challenge y claims
         {bindings: ([{ref:{type:"action_id",value:$link_id},display_name:"copilotoia-account-linking"}] + $preserved)}')"
      api_patch_soft '/actions/triggers/post-login/bindings' "$link_bindings_payload" 'PATCH bindings' >/dev/null \
        && echo "  ✓ account-linking enlazado al inicio"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# FIN M62 secciones avanzadas
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# Bootstrap del platform_owner inicial (opt-in via BOOTSTRAP_PLATFORM_OWNER_EMAIL)
# ════════════════════════════════════════════════════════════════════════════
#
# Si BOOTSTRAP_PLATFORM_OWNER_EMAIL está definido, el script:
#   1. Busca el user por email vía Management API.
#   2. Le asigna el rol `platform_owner` (idempotente — no duplica si ya está).
#   3. Setea `app_metadata.support_mode=true` (default; gated por
#      BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE para opt-out).
#
# Sin esto, el operador tenía que:
#   - Crear el user en Auth0 (lo sigue haciendo a mano — el script no crea
#     users porque eso requiere consent del owner del email).
#   - Asignar rol `platform_owner` desde el dashboard (Pestaña Roles → Assign).
#   - Editar `app_metadata` para agregar `{"support_mode": true}` (sin esto
#     el botón "Ver como tenant" en /platform/tenants no funciona — el
#     resolveActiveRoles del frontend requiere support_mode para que el rol
#     global aplique cuando hay tenant activo, ver TASK-0077).
#
# Variables opcionales:
#   BOOTSTRAP_PLATFORM_OWNER_EMAIL          email del user a bootstrappear
#                                           (debe existir previamente en Auth0).
#   BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE   true/false. Default true. Si false,
#                                           solo asigna el rol sin tocar
#                                           app_metadata.support_mode.
#
# **Trade-off de seguridad**: support_mode=true permanente significa que el
# platform_owner SIEMPRE puede operar en cualquier tenant (sin opt-in
# temporal). Para producción endurecida, dejarlo en false y manejar el
# toggle via un endpoint dedicado (ver `BUG-008` en docs/UI_BACKLOG.md).
BOOTSTRAP_PLATFORM_OWNER_EMAIL="${BOOTSTRAP_PLATFORM_OWNER_EMAIL:-}"
BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE="${BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE:-true}"

if [ -n "$BOOTSTRAP_PLATFORM_OWNER_EMAIL" ]; then
  echo "▶ Bootstrap platform_owner: $BOOTSTRAP_PLATFORM_OWNER_EMAIL"

  # 1. Localizar el user por email. La API espera el email URL-encoded.
  bootstrap_email_encoded="$(jq -rn --arg e "$BOOTSTRAP_PLATFORM_OWNER_EMAIL" '$e | @uri')"
  bootstrap_users_response="$(api_get "/users-by-email?email=$bootstrap_email_encoded")"
  # codex P1 fix: Auth0 permite el mismo email en múltiples connections
  # (database + Google OAuth + Microsoft, etc.). `/users-by-email` puede
  # devolver MÁS DE UN user. Si silenciosamente tomamos `.[0]`, podríamos
  # asignar `platform_owner` + `support_mode` a la identidad equivocada y
  # dejar al operador previsto sin acceso. Fail-closed si hay 0 o >1; el
  # operador desambigua manualmente borrando duplicates o asignando vía
  # dashboard al user_id correcto.
  bootstrap_user_count="$(jq 'length' <<<"$bootstrap_users_response")"

  if [ "$bootstrap_user_count" -eq 0 ]; then
    echo "  ⚠ User '$BOOTSTRAP_PLATFORM_OWNER_EMAIL' NO existe en Auth0." >&2
    echo "    Crealo primero en Auth0 Dashboard → Users → Create User," >&2
    echo "    luego re-corré este script con la misma variable." >&2
    echo "    (El script no crea users automáticamente porque requiere consent" >&2
    echo "    del dueño del email — Auth0 le manda email de invitación.)" >&2
    exit 2
  fi

  if [ "$bootstrap_user_count" -gt 1 ]; then
    echo "  ⚠ Email '$BOOTSTRAP_PLATFORM_OWNER_EMAIL' tiene MÁS DE UN user en Auth0." >&2
    echo "    Auth0 permite el mismo email en múltiples connections (database +" >&2
    echo "    Google OAuth + Microsoft, etc.). Para evitar asignar privilegios a" >&2
    echo "    la identidad equivocada, el script aborta — desambiguá manualmente." >&2
    echo "" >&2
    echo "    User IDs encontrados:" >&2
    jq -r '.[] | "      - \(.user_id) (connection=\(.identities[0].connection // "?"))"' <<<"$bootstrap_users_response" >&2
    echo "" >&2
    echo "    Acciones posibles:" >&2
    echo "      1. Borrá las identidades duplicadas que no querés en Auth0 Dashboard." >&2
    echo "      2. O asigná rol + app_metadata MANUALMENTE desde el dashboard al" >&2
    echo "         user_id correcto, y re-corré este script con BOOTSTRAP_PLATFORM_OWNER_EMAIL" >&2
    echo "         vacío para que skipee el bloque de bootstrap." >&2
    exit 2
  fi

  bootstrap_user_id="$(jq -r '.[0].user_id' <<<"$bootstrap_users_response")"

  # BUG-194 (codex HIGH): la cuenta Auth0 debe estar `email_verified=true`
  # antes de asignarle `platform_owner` + `support_mode`. Un atacante puede
  # crear una cuenta sin verificar con el email del platform owner antes que
  # la víctima active su propia cuenta — si el bootstrap silenciosamente
  # promueve la cuenta no verificada, el atacante recibe el rol más alto del
  # sistema y `support_mode` (cross-tenant). Fail-closed: el operador debe
  # disparar `verify email` desde el Auth0 dashboard antes de re-correr.
  bootstrap_user_verified="$(jq -r '.[0].email_verified // false' <<<"$bootstrap_users_response")"
  if [ "$bootstrap_user_verified" != "true" ]; then
    echo "  ⚠ User '$BOOTSTRAP_PLATFORM_OWNER_EMAIL' (user_id=$bootstrap_user_id)" >&2
    echo "    tiene email_verified=false en Auth0. Por seguridad, no se asigna" >&2
    echo "    'platform_owner' + 'support_mode' a una cuenta sin verificar — un" >&2
    echo "    atacante puede haber registrado el email antes que el dueño legítimo." >&2
    echo "" >&2
    echo "    Acción requerida:" >&2
    echo "      1. Auth0 Dashboard → Users → '$BOOTSTRAP_PLATFORM_OWNER_EMAIL'" >&2
    echo "      2. Verificá manualmente que la identidad corresponde al owner" >&2
    echo "         (chequeá el campo 'identities[0].connection' y los logs de" >&2
    echo "         creación)." >&2
    echo "      3. Disparar 'Send Verification Email' o setear email_verified=true" >&2
    echo "         manualmente si confiás en la identidad." >&2
    echo "      4. Re-correr este script." >&2
    exit 2
  fi

  # codex P1 fix: Auth0 user_ids tienen prefijo de connection con un pipe
  # (auth0|abc123, google-oauth2|123456, etc.). El pipe `|` no es URL-safe
  # y debe encodearse a `%7C` cuando va como path segment. Sin esto, los
  # endpoints `/users/{id}/roles` y `/users/{id}` pueden fallar con 404 o
  # 400 en algunos backends de proxy.
  bootstrap_user_id_encoded="$(jq -rn --arg id "$bootstrap_user_id" '$id | @uri')"

  # 2. Asignar rol platform_owner (idempotente).
  bootstrap_platform_role_id="$(jq -r '.[] | select(.name == "platform_owner") | .id' <<<"$roles_json" | head -n1)"
  if [ -z "$bootstrap_platform_role_id" ]; then
    echo "  ⚠ Rol 'platform_owner' no encontrado (¿se borró del bloque de roles?)" >&2
    exit 2
  fi

  bootstrap_existing_roles="$(api_get "/users/$bootstrap_user_id_encoded/roles?per_page=100")"
  bootstrap_already_assigned="$(jq -r --arg rid "$bootstrap_platform_role_id" '.[] | select(.id == $rid) | .id' <<<"$bootstrap_existing_roles" | head -n1)"

  if [ -z "$bootstrap_already_assigned" ]; then
    bootstrap_role_payload="$(jq -n --arg rid "$bootstrap_platform_role_id" '{roles:[$rid]}')"
    api_post "/users/$bootstrap_user_id_encoded/roles" "$bootstrap_role_payload" >/dev/null
    echo "  Rol 'platform_owner' asignado a $BOOTSTRAP_PLATFORM_OWNER_EMAIL"
  else
    echo "  Rol 'platform_owner' ya estaba asignado (idempotente)"
  fi

  # 3. (Opcional) setear app_metadata.support_mode=true. El user debe
  # logout+login después para que la PostLogin Action de claims lo propague
  # al JWT — los JWT existentes siguen con el valor viejo hasta expiración.
  if [ "$BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE" = "true" ]; then
    bootstrap_user_payload="$(jq -n '{app_metadata:{support_mode:true}}')"
    api_patch "/users/$bootstrap_user_id_encoded" "$bootstrap_user_payload" >/dev/null
    echo "  app_metadata.support_mode=true seteado (logout+login para que el JWT lo refleje)"
    echo "  ⚠ Trade-off: support_mode permanente — el platform_owner puede operar"
    echo "    en cualquier tenant sin opt-in temporal. Ver BUG-008 para el toggle."
  else
    echo "  app_metadata.support_mode NO modificado (BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE=false)"
    echo "  ⚠ Sin support_mode, el botón 'Ver como tenant' del Platform Owner"
    echo "    rechazará acceso a tenants ajenos. Setealo a true para destrabar"
    echo "    o setealo manualmente vía Auth0 Dashboard → Users → app_metadata."
  fi
fi

if [ "$SAVE_AUTH0_CONFIG" = "true" ]; then
  echo "▶ Guardar configuración Auth0 local"
  umask 077
  cat >"$AUTH0_ENV_FILE" <<EOF_AUTH0_ENV
# Generado por scripts/configure-auth0.sh. No versionar este archivo.
AUTH0_DOMAIN=$AUTH0_DOMAIN
AUTH0_ISSUER=https://$AUTH0_DOMAIN/
AUTH0_AUDIENCE=$AUTH0_API_IDENTIFIER
AUTH0_API_IDENTIFIER=$AUTH0_API_IDENTIFIER
AUTH0_CLAIMS_NAMESPACE=$CLAIMS_NAMESPACE
# AUTH0_ADMIN_* corresponde a la regular web app del panel
# (authorization_code + refresh_token). El backend la usa SOLO para el
# login del Admin Panel; las llamadas a Management API (invitar miembros,
# asignar roles, revocar acceso) usan AUTH0_SERVICE_* (app M2M
# non_interactive con grant_type=client_credentials). Ver BUG-001.
AUTH0_ADMIN_APP_NAME=$AUTH0_ADMIN_APP_NAME
AUTH0_ADMIN_CLIENT_ID=$admin_client_id
AUTH0_ADMIN_CLIENT_SECRET_FILE=$AUTH0_SECRETS_DIR/auth0-admin-client-secret
AUTH0_SERVICE_APP_NAME=$AUTH0_SERVICE_APP_NAME
AUTH0_SERVICE_CLIENT_ID=$service_client_id
AUTH0_SERVICE_CLIENT_SECRET_FILE=$AUTH0_SECRETS_DIR/auth0-service-client-secret
AUTH0_SERVICE_AUDIENCE=$AUTH0_API_IDENTIFIER
AUTH0_CALLBACK_URLS=$(json_string_array_to_csv "$CALLBACKS_JSON")
AUTH0_LOGOUT_URLS=$(json_string_array_to_csv "$LOGOUTS_JSON")
AUTH0_WEB_ORIGINS=$(json_string_array_to_csv "$ORIGINS_JSON")
EOF_AUTH0_ENV
  chmod 600 "$AUTH0_ENV_FILE" 2>/dev/null || true
  write_secret_file "$AUTH0_SECRETS_DIR/auth0-admin-client-secret" "$admin_client_secret"
  write_secret_file "$AUTH0_SECRETS_DIR/auth0-service-client-secret" "$service_client_secret"
fi

cat <<SUMMARY

✅ Auth0 CopilotoIA configurado
═══════════════════════════════════════════════════════════════════════
AUTH0_DOMAIN=$AUTH0_DOMAIN
AUTH0_AUDIENCE=$AUTH0_API_IDENTIFIER
AUTH0_CLAIMS_NAMESPACE=$CLAIMS_NAMESPACE
AUTH0_ADMIN_APP_NAME=$AUTH0_ADMIN_APP_NAME
AUTH0_ADMIN_CLIENT_ID=$admin_client_id
AUTH0_SERVICE_APP_NAME=$AUTH0_SERVICE_APP_NAME
AUTH0_SERVICE_CLIENT_ID=$service_client_id
AUTH0_ENV_FILE=$AUTH0_ENV_FILE
AUTH0_SECRETS_DIR=$AUTH0_SECRETS_DIR

─── M62 secciones aplicadas ──────────────────────────────────────────
  Tenant settings        : $CONFIGURE_TENANT_SETTINGS
  Universal Login (new)  : $CONFIGURE_UNIVERSAL_LOGIN
  DB Connection + policy : $CONFIGURE_DB_CONNECTION
  MFA factors            : $CONFIGURE_MFA_FACTORS  (policy=$MFA_POLICY)
  Attack protection      : $CONFIGURE_ATTACK_PROTECTION
  Resend email provider  : $CONFIGURE_RESEND_PROVIDER
  Email templates ES     : $CONFIGURE_EMAIL_TEMPLATES
  Account linking Action : $CONFIGURE_ACCOUNT_LINKING
  MFA enforcement Action : $ENFORCE_MFA_ACTION

─── Próximos pasos manuales (si aplica) ─────────────────────────────
  1. Verificar el dominio del sender en Resend (https://resend.com/domains)
     si CONFIGURE_RESEND_PROVIDER=true y querés que los emails no caigan
     a spam. Default sender: $EMAIL_FROM_ADDRESS

  2. Si algún bloque arriba mostró ⚠ "HTTP 403", agregar los scopes
     listados al M2M en Auth0 dashboard → Applications → APIs →
     Auth0 Management API → Machine to Machine → '$AUTH0_SERVICE_APP_NAME' →
     Add Permissions. Re-correr el script para que apliquen las
     secciones skipeadas.

  3. Setear AUTH0_TRUST_ADMIN_EMAIL_HEADER=false en .env del Core una vez
     verificado que el access_token trae el claim 'email' (post-A-003).
     Chequear con: docker compose logs admin-panel | grep email_from_header
     (no debería aparecer = claim llega bien).

SUMMARY

if [ "$OUTPUT_SECRETS" = "true" ] && [ -n "$service_client_secret" ]; then
  echo "AUTH0_SERVICE_CLIENT_SECRET=$service_client_secret"
else
  echo "# Nota: no se imprimen secretos. Usa OUTPUT_SECRETS=true solo en un entorno seguro si necesitas ver el secret inicial de la app M2M recién creada."
fi
