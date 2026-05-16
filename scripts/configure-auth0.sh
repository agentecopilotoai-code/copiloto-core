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
# Variables opcionales:
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
  local response_with_code http_code response

  if [ -n "$data" ]; then
    response_with_code="$(printf '%s' "$data" | curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}" --data @-)"
  else
    response_with_code="$(curl -sS -w '\n%{http_code}' -X "$method" "https://$AUTH0_DOMAIN/api/v2$path" "${auth_header[@]}")"
  fi

  http_code="$(tail -n1 <<<"$response_with_code")"
  response="$(sed '$d' <<<"$response_with_code")"

  if [[ ! "$http_code" =~ ^2 ]]; then
    echo "Error Auth0 Management API: $method $path" >&2
    echo "HTTP status: $http_code" >&2
    echo "Respuesta:" >&2
    jq . <<<"$response" >&2 2>/dev/null || echo "$response" >&2
    exit 1
  fi

  printf '%s' "$response"
}

api_get() { api_request GET "$1"; }
api_post() { api_request POST "$1" "$2"; }
api_patch() { api_request PATCH "$1" "$2"; }

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
MGMT_API_SCOPES="read:users,create:users,update:users,create:user_tickets,read:roles,read:role_members,create:role_members"
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
  mfa_action_code="$(cat <<MFA_ACTION
exports.onExecutePostLogin = async (event, api) => {
  const privilegedRoles = new Set(['admin','owner','platform_owner']);
  const roles = (event.authorization && event.authorization.roles) || [];
  const isPrivileged = roles.some(function(r) { return privilegedRoles.has(r); });
  if (!isPrivileged) return;
  const methods = (event.authentication && event.authentication.methods) || [];
  const hasMfa = methods.some(function(m) { return m.name === 'mfa'; });
  if (!hasMfa) {
    api.authentication.challengeWith({ type: 'otp' });
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
AUTH0_DOMAIN=$AUTH0_DOMAIN
AUTH0_AUDIENCE=$AUTH0_API_IDENTIFIER
AUTH0_CLAIMS_NAMESPACE=$CLAIMS_NAMESPACE
AUTH0_ADMIN_APP_NAME=$AUTH0_ADMIN_APP_NAME
AUTH0_ADMIN_CLIENT_ID=$admin_client_id
AUTH0_SERVICE_APP_NAME=$AUTH0_SERVICE_APP_NAME
AUTH0_SERVICE_CLIENT_ID=$service_client_id
AUTH0_ENV_FILE=$AUTH0_ENV_FILE
AUTH0_SECRETS_DIR=$AUTH0_SECRETS_DIR
SUMMARY

if [ "$OUTPUT_SECRETS" = "true" ] && [ -n "$service_client_secret" ]; then
  echo "AUTH0_SERVICE_CLIENT_SECRET=$service_client_secret"
else
  echo "# Nota: no se imprimen secretos. Usa OUTPUT_SECRETS=true solo en un entorno seguro si necesitas ver el secret inicial de la app M2M recién creada."
fi
