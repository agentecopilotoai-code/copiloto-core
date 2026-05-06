#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  echo ".env ya existe; no se sobreescribe. Borra .env si deseas regenerarlo." >&2
  exit 0
fi

secret() {
  openssl rand -base64 48 | tr -d '\n'
}

cp .env.example .env
python - <<'PY'
from pathlib import Path
import secrets

def token(n=48):
    return secrets.token_urlsafe(n)

p = Path('.env')
content = p.read_text()
replacements = {
    'change-me-admin-password': token(32),
    'change-me-app-password': token(32),
    'change-me-super-long-jwt-secret': token(64),
    'change-me-internal-service-token': token(48),
    'change-me-whatsapp-verify-token': token(32),
    'change-me-whatsapp-app-secret': token(48),
    'change-me-meta-access-token': 'local-mock-token-replace-in-production',
    'change-me-minio-password': token(32),
}
for old, new in replacements.items():
    content = content.replace(old, new)
p.write_text(content)
PY
chmod 600 .env
mkdir -p .secrets
for key in jwt_secret service_token whatsapp_verify_token whatsapp_app_secret meta_access_token s3_secret_access_key; do
  value=$(awk -F= -v k="$(echo "$key" | tr '[:lower:]' '[:upper:]')" '$1==k {print substr($0, index($0,"=")+1)}' .env)
  printf '%s' "$value" > ".secrets/${key}"
  chmod 600 ".secrets/${key}"
done

echo "Secretos locales generados en .env y .secrets/ (ignorados por git)."
