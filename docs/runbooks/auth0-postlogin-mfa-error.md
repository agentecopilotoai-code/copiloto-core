# Runbook: Auth0 PostLogin Action MFA error

> ⚠️ **Severidad: BLOQUEO TOTAL.** Mientras la Action esté activa en un
> tenant Auth0 sin MFA habilitado, **NINGÚN usuario** (incluyendo el
> `platform_owner`) puede completar el login. La pantalla blanca con
> "Something Went Wrong — Two-factor authentication is required to access
> this application" en Auth0 es este bug. Es una acción operativa, no de
> código: el panel no se puede arreglar desde el repo.

## Síntoma

1. **Pantalla del browser** (renderizada por Auth0, no por el panel):
   ```
   Something Went Wrong
   Two-factor authentication is required to access this application.
   To enable this, please contact your system administrator.
   ```
2. **Si llega al callback** (`/admin/callback`), responde:
   ```json
   {"detail":"invalid_request: MFA customized via PostLogin action but feature is not enabled."}
   ```

El usuario queda en la página de error sin poder entrar al panel — y los
roles globales (incluido `platform_owner`) tampoco pueden bypassear esto,
porque la Action se ejecuta ANTES de emitir el token.

## Root cause

El tenant de Auth0 tiene una **PostLogin Action** (probablemente generada
por `scripts/configure-auth0.sh` con `ENFORCE_MFA_ACTION=true`) que llama a
`api.multifactor.enable(...)` para forzar MFA en cuentas privilegiadas. Esa
API requiere que el tenant Auth0 tenga el **feature flag MFA habilitado**
en la consola.

Si el tenant es un developer/sandbox (default `dev-*.auth0.com`) sin el
add-on de MFA, la PostLogin Action falla en la fase de validación de
Auth0 con `invalid_request: MFA customized via PostLogin action but
feature is not enabled` ANTES de redirigir al callback. El user nunca
completa la auth → no hay sesión.

## Decisión: arreglar en Auth0, no en el código

El backend (`app/admin/routes.py`) ya parsea el query string del callback
y debería re-renderizar la página de error correctamente. El fix de
verdad es en Auth0 — dos caminos posibles:

### Opción A — Habilitar MFA en Auth0 (producción)

1. Auth0 Dashboard → **Security** → **Multi-factor Auth**.
2. Activar al menos un factor (OTP, WebAuthn, SMS — recomendado OTP/WebAuthn).
3. Re-correr el callback. La PostLogin Action ahora podrá llamar a
   `api.multifactor.enable(...)` sin error.
4. Los usuarios privilegiados (Owner/Admin/Platform Owner) deberán
   completar el setup de MFA en su primer login después de este cambio.

### Opción B — Deshabilitar la PostLogin Action (dev / sandboxes sin add-on)

1. Auth0 Dashboard → **Actions** → **Library** → buscar la action que el
   script generó (típicamente `copilotoia-enforce-mfa` o similar).
2. Auth0 Dashboard → **Actions** → **Flows** → **Login**.
3. Quitar la action del flujo PostLogin (drag fuera) y guardar.
4. Re-correr el callback — funcionará sin MFA enforcement.
5. **Importante:** sin la Action, los usuarios privilegiados NO tendrán
   MFA forzada. Solo OK para tenants de dev.

Equivalente vía CLI: re-correr `scripts/configure-auth0.sh` con
`ENFORCE_MFA_ACTION=false` (verificar que el script soporta este
override; si no, hacerlo manualmente vía dashboard).

## Recomendación

- **Producción / staging**: Opción A. MFA es non-negotiable para roles
  privilegiados (ver SEC-004 cluster).
- **Dev / sandbox sin add-on**: Opción B.

## Verificación post-fix

```bash
# Borra cualquier sesión vieja
curl -X POST 'http://localhost:3000/admin/logout' \
  -b 'copilotoia_admin_session=<SESSION_ID>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data ''

# Re-entra desde la landing
open 'http://localhost:3000/admin/login'
```

El callback debe devolver 303 a `/admin/` con `Set-Cookie:
copilotoia_admin_session=...` en lugar del JSON de error.

## Referencia

- Auth0 docs · [api.multifactor.enable](https://auth0.com/docs/customize/actions/flows-and-triggers/login-flow/api-object#multifactor)
- `scripts/configure-auth0.sh` — sección PostLogin Actions
- BUG-001 / SEC-006 — relacionados al setup correcto del M2M client para
  el invite endpoint (`POST /v1/tenants/{id}/members`).
