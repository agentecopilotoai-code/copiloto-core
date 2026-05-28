# Runbook — Rotación de signing keys de Auth0

**Categoría:** Seguridad / Operaciones
**Alcance:** Tenant de Auth0 que firma los `id_token` / `access_token` que
recibe el BFF (`app/admin/routes.py`) y los handlers `/v1/*` (`app/core/security.py`).
**Audiencia:** SRE on-call, Security engineer.
**Frecuencia esperada:** cada 90 días (auto-recovery cubre rotaciones
no planificadas también — ver § "Cuándo no necesitas este runbook").

---

## TL;DR

El sistema **auto-recupera** rotaciones de Auth0 (M-001 audit#2). El JWKS cache
hace `force_refresh` en cuanto detecta un `kid` desconocido. **No necesitas
intervención manual para rotaciones automáticas de Auth0**.

Este runbook documenta:

1. Cuándo (raramente) necesitas forzar el refresh manualmente.
2. Cómo verificar que la rotación se propagó sin downtime.
3. Cómo rotar las **otras** credenciales asociadas al tenant Auth0
   (M2M client secret, Management API token, action secrets) — esas
   no auto-recuperan y sí requieren proceso humano.

---

## Cuándo NO necesitas este runbook

Auth0 rota las signing keys del tenant automáticamente o cuando lo
disparás desde el dashboard. El backend tiene tres mecanismos:

| Mecanismo | Implementación | Cubre |
|-----------|----------------|-------|
| JWKS cache TTL | `_JWKS_CACHE_TTL_SECONDS = 300` (`app/core/security.py:46`) | rotación regular post-TTL |
| Force-refresh on unknown kid | `_fetch_auth0_jwks(force_refresh=True)` cuando `_select_jwk` retorna None (M-001) | rotación mid-TTL |
| Métrica + log | `auth0.jwks.force_refreshed` con `new_kids=[...]` | observabilidad post-mortem |

**Si solo Auth0 rotó la signing key**, no hagás nada — los tokens
nuevos serán validados al próximo request que llegue con el `kid`
nuevo (un `force_refresh` se dispara, el cache se actualiza, todos
los workers convergen en ≤ TTL).

---

## Cuándo SÍ necesitas este runbook

1. **Rotación planificada del M2M client secret** (Auth0 → Applications
   → Machine-to-Machine → Settings → Client Secret → Rotate). Esto NO
   está en JWKS — está en `AUTH0_ADMIN_CLIENT_SECRET` que el backend
   usa para llamar al Management API.

2. **Sospecha de compromiso** — necesitas invalidar todas las sesiones
   actuales además de rotar keys.

3. **Force JWKS refresh sin esperar TTL** — debug rápido en incidente.

4. **Rotación del state secret del BFF** (`ADMIN_STATE_SECRET` /
   `ADMIN_SESSION_SECRET`) — invalida cookies de OAuth state y sessions
   existentes. Útil tras un leak.

---

## Procedimiento 1 — Rotación del M2M client secret (planificada)

### Pre-requisitos

- Acceso owner al tenant de Auth0.
- Acceso al secret store de producción (Kubernetes Secrets, Vault, AWS
  Secrets Manager — según deployment).
- Ventana de mantenimiento de **5 minutos** para overlap rolling.

### Pasos

1. **En Auth0 dashboard**:
   - Applications → Machine-to-Machine → `<copilotoia-backend>` → Settings.
   - Bajo "Client Secret" → "Rotate".
   - Copiar el NUEVO secret (visible una sola vez).
   - **NO clickear "Revoke old secret yet"** — los dos coexisten hasta paso 5.

2. **Actualizar el secret store** sin tocar el viejo todavía:

   ```bash
   # Kubernetes
   kubectl create secret generic auth0-admin-new \
     --from-literal=client_secret='<NUEVO_SECRET>' \
     -n copilotoia

   # Verificar
   kubectl get secret auth0-admin-new -o jsonpath='{.data.client_secret}' \
     | base64 -d | wc -c
   ```

3. **Rolling restart de los pods** que usan `AUTH0_ADMIN_CLIENT_SECRET`
   (api + workers) montando el nuevo secret:

   ```bash
   # Actualizar el deployment para que apunte a auth0-admin-new
   kubectl patch deployment copilotoia-api \
     --patch '{"spec":{"template":{"spec":{"containers":[{"name":"api","env":[{"name":"AUTH0_ADMIN_CLIENT_SECRET","valueFrom":{"secretKeyRef":{"name":"auth0-admin-new","key":"client_secret"}}}]}]}}}}'

   kubectl rollout status deployment/copilotoia-api --timeout=300s
   ```

4. **Smoke test** — verificar que el Management API responde con el
   nuevo secret:

   ```bash
   # Llamar a un endpoint admin que internamente use Management API.
   # Ejemplo: list users del tenant Auth0.
   curl -s -H "Authorization: Bearer $ADMIN_JWT" \
     https://api.copilotoia.com/v1/platform/auth0/users?limit=1 \
     | jq '.users | length'   # debe retornar 1
   ```

   En logs del pod buscar:

   ```bash
   kubectl logs -l app=copilotoia-api --tail=100 \
     | grep -E 'auth0_admin|management_api' | head
   ```

   No debe haber `401 unauthorized` ni `invalid_client`.

5. **Revocar el secret viejo en Auth0**:
   - Auth0 dashboard → mismo M2M app → "Revoke old secret".
   - A partir de este momento cualquier pod no actualizado falla
     401 en su próximo call al Management API → si tu rolling
     deployment dejó pods viejos, los vas a ver crashar.

6. **Verificar métricas**:

   ```promql
   # Errores 401 del backend hacia Auth0 — debería estar en 0 post-rotación.
   sum(rate(cpi_outbound_http_errors_total{provider="auth0",status="401"}[5m]))
   ```

7. **Audit log**: registrar la rotación con quién y cuándo:

   ```sql
   insert into app.audit_log (
     tenant_id, actor_type, actor_id, action, entity_type, payload_despues
   ) values (
     null, 'operator', current_setting('app.actor_email', true),
     'rotated_auth0_m2m_client_secret', 'auth0_application',
     jsonb_build_object('rotated_at', now(), 'reason', 'scheduled_90d')
   );
   ```

### Rollback

Si el smoke test falla, **NO revocar el secret viejo**. Volver el
deployment al secret anterior:

```bash
kubectl rollout undo deployment/copilotoia-api
```

El secret viejo sigue válido en Auth0 hasta que clickees "Revoke".

---

## Procedimiento 2 — Force JWKS refresh (incidente)

Útil si:
- Sospechás que el cache tiene una key obsoleta.
- Auth0 rotó y los logs del backend no muestran `auth0.jwks.force_refreshed`
  (puede pasar si no hubo tráfico con tokens del kid nuevo todavía).

### Pasos

```bash
# Opción A — desde el pod (preferida para producción)
kubectl exec -it deployment/copilotoia-api -- python -c "
from app.core.security import clear_jwks_cache
clear_jwks_cache()
print('cache cleared')
"

# Opción B — restart rolling (más drástico, garantiza convergencia
# si tenés múltiples workers y querés todos a la vez)
kubectl rollout restart deployment/copilotoia-api

# Verificar que el próximo request reload el JWKS:
kubectl logs -l app=copilotoia-api --tail=20 -f | grep 'auth0.jwks'
```

Esperá ver una línea `auth0.jwks.force_refreshed` con `new_kids=[...]`
incluyendo el `kid` esperado.

---

## Procedimiento 3 — Rotación del state secret del BFF (post-leak)

Si el `ADMIN_STATE_SECRET` se filtró, **todas las cookies OAuth
state existentes deben invalidarse**. Eso significa que cualquier
usuario en medio del flow `/admin/auth/login` → callback va a fallar
y necesitará reiniciar el login.

### Impacto

- Usuarios con session activa: no afectados (la session usa
  `ADMIN_SESSION_SECRET`, diferente).
- Usuarios en login flow al momento de la rotación: fallan en el
  callback con `state_invalid` → click "Login" de nuevo.

### Pasos

1. Generar nuevo secret:

   ```bash
   # 32 bytes random base64
   openssl rand -base64 32
   ```

2. Actualizar el secret store:

   ```bash
   kubectl create secret generic admin-state-secret-new \
     --from-literal=value='<NUEVO_SECRET>' -n copilotoia
   ```

3. Rolling restart con el nuevo env var:

   ```bash
   kubectl set env deployment/copilotoia-api \
     ADMIN_STATE_SECRET="$(kubectl get secret admin-state-secret-new \
       -o jsonpath='{.data.value}' | base64 -d)"
   kubectl rollout status deployment/copilotoia-api
   ```

4. Notificar al equipo de support que usuarios pueden ver
   `state_invalid` por 5 minutos.

5. Audit log + incident ticket (categoría `security/secret_leak`).

### Rotación del session secret (mucho más invasivo)

Si `ADMIN_SESSION_SECRET` también se filtró:
- TODAS las sessions activas se invalidan al rotar.
- TODOS los usuarios deben re-login.
- Coordinar con product (anuncio en banner) ANTES de rotar.

---

## Procedimiento 4 — Verificación post-rotación end-to-end

Independientemente del tipo de rotación, ejecutá este checklist:

### Checklist

- [ ] El gauge `cpi_ai_provider_health` se mantiene en 1 para
      provider=`auth0` (si lo exponés — el core no lo expone para
      auth0 explícitamente pero el módulo opt-in `iam` sí puede).

- [ ] `kubectl logs -l app=copilotoia-api --since=10m | grep -E 'invalid_token|invalid_client|kid_unknown'`
      retorna 0 líneas tras los primeros 60s post-rotación.

- [ ] El endpoint `/admin/api/me` responde 200 con un token reciente
      emitido por el `kid` nuevo:

      ```bash
      # Login fresh en el frontend, capturar la cookie `session`.
      curl -s -b "session=$SESSION_COOKIE" \
        https://api.copilotoia.com/admin/api/me | jq '.email'
      ```

- [ ] Métricas Prometheus muestran tráfico estable (no spike de 5xx):

      ```promql
      sum(rate(http_requests_total{status=~"5.."}[5m])) by (status)
      ```

- [ ] Audit log entry creado (ver paso 7 del procedimiento 1).

---

## Anexo — Variables de entorno relevantes

| Variable | Default | Rotar si… | Impacto |
|----------|---------|-----------|---------|
| `AUTH0_DOMAIN` | n/a | NUNCA (cambiar tenant es migración full) | Total |
| `AUTH0_CLIENT_ID` | n/a | Cambias la app M2M en Auth0 | Total |
| `AUTH0_ADMIN_CLIENT_SECRET` | n/a | Cada 90 días o post-leak | Procedimiento 1 |
| `AUTH0_AUDIENCE` | API identifier | Solo en migración de API | Sesiones expiran |
| `ADMIN_STATE_SECRET` | n/a | Post-leak | OAuth state cookies invalidadas |
| `ADMIN_SESSION_SECRET` | n/a | Post-leak (drastic) | TODOS los users re-login |
| `JWT_SECRET` (HS256 fallback dev) | n/a | Producción NO lo usa (Auth0 es RS256) | Solo dev |

JWKS cache TTL: hardcoded a 300s en `app/core/security.py`. Si
necesitás reducirlo (rotaciones frecuentes), hacer un PR — no hay
env var para esto.

---

## Anexo — Glosario

- **JWKS** = JSON Web Key Set. Endpoint `https://<tenant>.auth0.com/.well-known/jwks.json`.
- **kid** = key id. Header del JWT que identifica con qué key se firmó.
- **M2M** = Machine-to-Machine. App de Auth0 para que el backend llame al Management API.
- **TTL** = Time To Live. Cuánto cachea el backend el JWKS antes de re-fetch.
- **Force refresh** = re-fetch del JWKS ANTES del TTL, disparado por
  `kid` desconocido (M-001).

---

## Postmortems vinculados

- Ninguno aún (M-001 implementado preventivo). Cuando ocurra un
  incidente de rotación, agregar link aquí.

---

## Última revisión

| Fecha | Por | Cambio |
|-------|-----|--------|
| 2026-05-27 | TASK-DOCS post audit#4 | Creación inicial |
