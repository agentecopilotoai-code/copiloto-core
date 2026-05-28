#!/usr/bin/env bash
# Smoke test del core: verifica que los endpoints públicos básicos respondan.
# Llamado por bootstrap.sh tras `docker compose up`. Sin auth (los endpoints
# que verifica no la requieren).
#
# Falla con exit ≠ 0 si algún check no pasa — bootstrap aborta.
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ADMIN_BASE="${ADMIN_BASE:-http://localhost:3000}"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

echo "→ Smoke test core (API=${API_BASE}, ADMIN=${ADMIN_BASE})"

# 1. API health.
if ! curl -fsS --max-time 5 "${API_BASE}/v1/health" >/dev/null; then
  fail "GET ${API_BASE}/v1/health no responde 2xx"
fi
ok "GET /v1/health → 2xx"

# 2. /metrics solo accesible desde IP allowlisted (esperamos 403 desde
#    127.0.0.1 si no está en OBSERVABILITY_ALLOWED_IPS). Solo verificamos
#    que responde algo (no que sea OK).
metrics_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${API_BASE}/metrics" || true)"
if [[ "$metrics_status" != "200" && "$metrics_status" != "403" ]]; then
  fail "GET ${API_BASE}/metrics retornó ${metrics_status} (esperado 200 o 403)"
fi
ok "GET /metrics → ${metrics_status} (200=allowlisted, 403=gated)"

# 3. Admin BFF responde la SPA (con o sin sesión, debe servir HTML).
admin_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${ADMIN_BASE}/admin/" || true)"
if [[ "$admin_status" != "200" && "$admin_status" != "302" ]]; then
  fail "GET ${ADMIN_BASE}/admin/ retornó ${admin_status} (esperado 200 o 302)"
fi
ok "GET /admin/ → ${admin_status}"

# 4. Endpoint platform_admin sin token → 401/403.
fleet_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${API_BASE}/v1/tenants" || true)"
if [[ "$fleet_status" != "401" && "$fleet_status" != "403" ]]; then
  fail "GET ${API_BASE}/v1/tenants sin auth retornó ${fleet_status} (esperado 401/403)"
fi
ok "GET /v1/tenants sin auth → ${fleet_status}"

# 5. OpenAPI / docs disponible.
docs_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${API_BASE}/docs" || true)"
if [[ "$docs_status" != "200" ]]; then
  fail "GET ${API_BASE}/docs retornó ${docs_status} (esperado 200)"
fi
ok "GET /docs → 200"

echo "→ Smoke test OK."
