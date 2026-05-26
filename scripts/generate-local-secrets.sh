#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  if grep -q 'change-me-' .env; then
    backup=".env.incomplete.$(date +%Y%m%d%H%M%S).bak"
    mv .env "$backup"
    echo "Se encontró un .env incompleto con placeholders; se movió a $backup." >&2
  else
    echo ".env ya existe; no se sobreescribe. Borra .env si deseas regenerarlo." >&2
    exit 0
  fi
fi

random_token() {
  local bytes="${1:-48}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 "$bytes" | tr '+/' '-_' | tr -d '=\n'
    return 0
  fi

  echo "Error: se requiere openssl para generar secretos locales." >&2
  echo "Instala openssl o crea .env manualmente desde .env.example." >&2
  return 1
}

admin_password="$(random_token 32)"
app_password="$(random_token 32)"
jwt_secret="$(random_token 64)"
service_token="$(random_token 48)"
minio_password="$(random_token 32)"

# Master key (Fernet) para cifrar API keys de proveedores IA en
# `app.platform_secrets.ciphertext`. Fernet requiere 32 bytes random
# codificados en url-safe base64 (44 chars incluyendo el padding `=`).
ai_provider_master_key="$(openssl rand 32 | base64 | tr '+/' '-_' | tr -d '\n')"

cat > .env <<EOF_ENV
# Archivo local generado por scripts/generate-local-secrets.sh.
# No lo subas a git. Cambia estos valores antes de producción.
APP_ENV=local
APP_NAME=CopilotoIA Core
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=postgresql://copiloto_app:${app_password}@postgres:5432/copilotoia
DATABASE_ADMIN_URL=postgresql://copiloto_admin:${admin_password}@postgres:5432/copilotoia
POSTGRES_DB=copilotoia
POSTGRES_USER=copiloto_admin
POSTGRES_PASSWORD=${admin_password}
APP_DB_USER=copiloto_app
APP_DB_PASSWORD=${app_password}
REDIS_URL=redis://redis:6379/0
JWT_ISSUER=copilotoia-local
JWT_AUDIENCE=copilotoia-panel
JWT_SECRET=${jwt_secret}
SERVICE_TOKEN=${service_token}
META_GRAPH_VERSION=v23.0
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=copilotoia-local
S3_ACCESS_KEY_ID=copilotoia-minio
S3_SECRET_ACCESS_KEY=${minio_password}
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
AI_PROVIDER_MASTER_KEY=${ai_provider_master_key}
EOF_ENV

chmod 600 .env
mkdir -p .secrets
for key in jwt_secret service_token s3_secret_access_key; do
  value=$(awk -F= -v k="$(echo "$key" | tr '[:lower:]' '[:upper:]')" '$1==k {print substr($0, index($0,"=")+1)}' .env)
  printf '%s' "$value" > ".secrets/${key}"
  chmod 600 ".secrets/${key}"
done

echo "Secretos locales generados en .env y .secrets/ (ignorados por git)."
echo "Los módulos opt-in que requieran secrets por tenant los gestionan en su"
echo "propia carpeta bajo .secrets/tenants/<tenant_id>/."
