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

echo "▶ Upsert roles y permisos"
role_names=(owner admin manager agent viewer support)

role_description() {
  case "$1" in
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
AUTH0_ADMIN_APP_NAME=$AUTH0_ADMIN_APP_NAME
AUTH0_ADMIN_CLIENT_ID=$admin_client_id
AUTH0_SERVICE_APP_NAME=$AUTH0_SERVICE_APP_NAME
AUTH0_SERVICE_CLIENT_ID=$service_client_id
AUTH0_SERVICE_AUDIENCE=$AUTH0_API_IDENTIFIER
AUTH0_CALLBACK_URLS=$(json_string_array_to_csv "$CALLBACKS_JSON")
AUTH0_LOGOUT_URLS=$(json_string_array_to_csv "$LOGOUTS_JSON")
AUTH0_WEB_ORIGINS=$(json_string_array_to_csv "$ORIGINS_JSON")
AUTH0_ADMIN_CLIENT_SECRET_FILE=$AUTH0_SECRETS_DIR/auth0-admin-client-secret
AUTH0_SERVICE_CLIENT_SECRET_FILE=$AUTH0_SECRETS_DIR/auth0-service-client-secret
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
