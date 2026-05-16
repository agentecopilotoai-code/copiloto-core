# Runbook: Auth0 PostLogin Action MFA error

> ⚠️ **Severidad: BLOQUEO TOTAL.** Mientras la Action esté activa en un
> tenant Auth0 sin MFA bien configurado, **NINGÚN usuario** (incluyendo el
> `platform_owner`) puede completar el login. La pantalla blanca con
> "Something Went Wrong — Two-factor authentication is required to access
> this application" en Auth0 es este bug. Es una acción operativa, no de
> código: el panel no se puede arreglar desde el repo.

---

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
3. **En tenant logs** (Auth0 Dashboard → Monitoring → Logs), el evento es de tipo `mfar` (`MFA Required` fallido) con descripciones como:
   - `"MFA customized via PostLogin action but feature is not enabled"` — sub-caso 2a.
   - `"An MFA challenge is used in a PostLogin action but the requested factors are not properly set up. To perform MFA, enable the requested factors and ensure the user is enrolled with them."` — sub-caso 2b.

El usuario queda en la página de error sin poder entrar al panel — y los
roles globales (incluido `platform_owner`) tampoco pueden bypassear esto,
porque la Action se ejecuta ANTES de emitir el token.

---

## Root cause

El tenant de Auth0 tiene una **PostLogin Action** (probablemente generada
por `scripts/configure-auth0.sh` con `ENFORCE_MFA_ACTION=true`) que llama a
`api.authentication.challengeWith(...)` para forzar MFA en cuentas
privilegiadas. Esa API requiere que el tenant Auth0 tenga **MFA bien
configurado al nivel correcto**: factor habilitado **y** usuario enrolado
**y** la API extensible de MFA disponible para Actions.

Tres puntos de fallo distintos producen el mismo síntoma:

| Sub-caso | Qué falla | Cómo lo identificas |
|---|---|---|
| **2a** | El factor MFA (OTP/WebAuthn/etc.) NO está habilitado en **Security > Multi-factor Auth**. | Log dice `feature is not enabled`. |
| **2b** | El factor SÍ está habilitado pero el **usuario nunca lo enroló**. Común con usuarios de Google OAuth2 u otro IdP externo, que nunca pasaron por el flow de enrollment de Auth0. | Log dice `the requested factors are not properly set up. To perform MFA, enable the requested factors and ensure the user is enrolled with them`. |
| **2c** | El factor SÍ está habilitado y el usuario SÍ está enrolado, pero la Action ve `event.authorization.roles = []` y nunca dispara MFA (porque la Action de claims `copilotoia-post-login-claims` no está bindeada al flow). El usuario logueó "sin MFA" y el panel/backend lo rechaza con 403 al primer call a un endpoint privilegiado. | No hay error visible al login pero `/v1/tenant-signup` (u otro endpoint con `require_min_role`) devuelve `403 admin role or higher is required`. |

---

## Pre-requisito: las dos Actions deben estar en el flow Login, en orden

El script `configure-auth0.sh` con `ENFORCE_MFA_ACTION=true` crea **DOS**
Actions independientes que deben coexistir en el flow Login:

1. **`copilotoia-post-login-claims`** — inyecta `roles`, `permissions`,
   `tenant_id`, `tenant_slug`, `support_mode` como custom claims en el
   access token. Sin esta, todas las verificaciones de rol (en la Action
   de MFA y en el backend) ven `roles=[]`.
2. **`copilotoia-mfa-challenge`** — lee los roles ya cargados por la
   Action anterior y, si son privilegiados (`owner`/`admin`/`platform_owner`),
   dispara MFA.

**Orden crítico**: `copilotoia-post-login-claims` debe ejecutarse **ANTES** que
`copilotoia-mfa-challenge`. Si están al revés (o si la de claims no está
en el flow), MFA ve roles vacíos y no dispara — el síntoma 2c.

### Verificación visual

1. Auth0 Dashboard → **Actions** → **Flows** → **Login**.
2. En el diagrama central (columna del medio entre **Start** y **Complete**)
   deben aparecer **AMBOS** bloques en este orden:
   ```
   Start
     ↓
   copilotoia-post-login-claims   ← primero
     ↓
   copilotoia-mfa-challenge       ← segundo
     ↓
   Complete
   ```
3. Si alguna falta (vive solo en la columna derecha "Library"), arrastrala
   al flow y **Apply**.

---

## Pre-requisito: el toggle de Actions MFA debe estar ON

Las llamadas `api.authentication.challengeWith(...)` y
`api.authentication.enrollWith(...)` que usan las Actions requieren un
feature flag del tenant:

1. Auth0 Dashboard → **Security** → **Multi-factor Auth** → scroll al final
   ("Additional Settings").
2. **`Customize MFA Factors using Actions`** debe estar **ON**.

Sin esto, las Actions pueden silenciosamente no enrolar/desafiar y producís
el sub-caso 2b incluso con OTP habilitado y usuario enrolado.

---

## Decisión: arreglar en Auth0, no en el código

El backend (`app/admin/routes.py`) ya parsea el query string del callback
y debería re-renderizar la página de error correctamente. El fix de
verdad es en Auth0 — tres caminos posibles según el sub-caso:

### Opción A — Habilitar MFA en Auth0 (producción)

**Aplica a sub-caso 2a** (factor no habilitado).

1. Auth0 Dashboard → **Security** → **Multi-factor Auth**.
2. Activar al menos un factor: **One-time Password** (OTP, recomendado;
   compatible con Google Authenticator/Authy) o **WebAuthn with FIDO
   Security Keys**.
3. (Recomendado) en "Additional Settings", activar **`Customize MFA
   Factors using Actions`** (requerido por las Actions del script).
4. Dejar la policy "Require Multi-factor Auth" en **Never** — la Action
   `copilotoia-mfa-challenge` toma precedencia y solo aplica MFA a
   privilegiados (owner/admin/platform_owner), que es lo que querés.
5. Re-correr el callback. La PostLogin Action ahora podrá llamar a
   `api.authentication.challengeWith(...)` sin error... **siempre que
   los usuarios privilegiados YA estén enrolados** (ver Opción B abajo).

### Opción B — Modificar la Action para que enrolle + desafíe (recomendado producción)

**Aplica a sub-caso 2b** (factor habilitado pero usuario sin enrollment),
muy común con usuarios que vienen de un IdP externo (Google OAuth2,
Microsoft, etc.) y nunca pasaron por el flow de enrollment de Auth0.

La Action que genera el script solo desafía con `challengeWith`, que
falla si no hay enrollment previo. Modificala para que enrolle automá-
ticamente en el primer login privilegiado:

1. Auth0 Dashboard → **Actions** → **Library** → click sobre
   `copilotoia-mfa-challenge` → **Edit**.
2. Reemplazá el código por:

   ```javascript
   /**
    * copilotoia-mfa-challenge — fuerza MFA solo en roles privilegiados.
    *
    * El script `scripts/configure-auth0.sh` genera una versión más simple
    * que SOLO desafía (`challengeWith`). Esta versión también ENROLLA
    * cuando el usuario aún no tiene un factor configurado — necesario
    * para usuarios que vienen de IdP externos (Google OAuth2, etc.) que
    * nunca pasaron por el flow nativo de Auth0.
    *
    * Pre-requisitos en el tenant:
    *   - Al menos un factor MFA habilitado (Security > Multi-factor Auth).
    *   - `Customize MFA Factors using Actions` activado (Additional Settings).
    *   - Action `copilotoia-post-login-claims` corriendo ANTES en el flow
    *     Login (sino `event.authorization.roles` viene vacío y esta
    *     Action skipea silenciosamente).
    */
   exports.onExecutePostLogin = async (event, api) => {
     const privilegedRoles = new Set(['admin', 'owner', 'platform_owner']);
     const roles = (event.authorization && event.authorization.roles) || [];
     const isPrivileged = roles.some(function (r) {
       return privilegedRoles.has(r);
     });
     if (!isPrivileged) return;

     // Si esta sesión ya completó MFA, no re-desafiamos.
     const methods = (event.authentication && event.authentication.methods) || [];
     const hasMfa = methods.some(function (m) { return m.name === 'mfa'; });
     if (hasMfa) return;

     // Si el usuario tiene al menos un factor enrolado, desafía con OTP.
     // Si no, enrolla primero (Auth0 muestra el QR + pide confirmar el código).
     const enrolledFactors = (event.user && event.user.enrolledFactors) || [];
     if (enrolledFactors.length > 0) {
       api.authentication.challengeWith({ type: 'otp' });
     } else {
       api.authentication.enrollWith({ type: 'otp' });
     }
   };
   ```

3. **Save Draft** → **Deploy**.
4. **Actions** → **Flows** → **Login** → verificá que la Action sigue en
   el flow central (debería). Si necesita re-aplicar, click **Apply**.
5. Logout completo del panel + login. En el primer login post-cambio,
   Auth0 te muestra:
   - QR code para escanear con Google Authenticator / Authy / 1Password.
   - Input para confirmar el código de 6 dígitos generado por la app.
   - Una vez confirmado, ya tenés el factor enrolado para siempre y los
     próximos logins solo te piden el código (challengeWith).

### Opción C — Deshabilitar la PostLogin Action (dev / sandboxes sin add-on)

**Aplica para dev rápido sin MFA**.

1. Auth0 Dashboard → **Actions** → **Flows** → **Login**.
2. Arrastrá el bloque `copilotoia-mfa-challenge` **fuera** del flow (a la
   columna derecha "Library").
3. **Apply**. Los logins funcionan sin segundo factor.

> Sin la Action, los usuarios privilegiados NO tendrán MFA forzada. Solo
> OK para tenants de dev.

> `ENFORCE_MFA_ACTION=false` en el script **no** desbindea una Action ya
> creada — solo evita que la cree de cero. Para quitarla usa este Opción C
> en el dashboard, no la variable de entorno.

Equivalente vía CLI (si querés que el script no la cree desde cero al
re-correrlo): `ENFORCE_MFA_ACTION=false ./scripts/configure-auth0.sh`.

---

## Recomendación

- **Producción / staging**: Opciones A + B en conjunto. MFA es
  non-negotiable para roles privilegiados (ver SEC-004 cluster), y la
  Opción B asegura que el primer login post-asignación de rol enrolle
  automáticamente sin intervención del operador. Para usuarios reales
  esto es el flow más fluido.
- **Dev / sandbox sin add-on**: Opción C. Quita la Action del flow para
  no tener que rotar config manualmente entre tenants efímeros.

---

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

### Smoke test del fix completo

1. Logout total → login con usuario `platform_owner`.
2. Si aplicaste Opción A + B y el usuario no enrolaba aún: Auth0 muestra
   QR → escaneá con Authenticator → ingresá código de 6 dígitos.
3. Tras MFA, Auth0 redirige a `/admin/callback` y luego a
   `/admin/platform/tenants` (vista de Platform Owner — BUG-006 fix).
4. Una vez en el panel, navegá a `/admin/account/sessions` — debes ver al
   menos una sesión con `current: true` (UI-016.7-FU-SESSIONS).

### Si NO aparece el prompt MFA pero entrás al panel

Estás en el sub-caso 2c (Action de claims no bindeada). Los síntomas son:

1. Login pasa sin MFA prompt (porque la Action de MFA ve `roles=[]` y
   skipea).
2. El panel te aterriza en `/admin/onboarding` (tarjeta "Aún no estás
   asignada a un negocio") en vez de `/admin/platform/tenants`.
3. Si intentás crear tenant desde el onboarding, el backend rechaza con
   `403 admin role or higher is required`.

**Fix**: aplicá el "Pre-requisito: las dos Actions deben estar en el flow
Login, en orden" arriba. La Action de claims muy probablemente está en la
Library pero no fue arrastrada al flow.

---

## Referencia

- Auth0 docs · [api.authentication.challengeWith](https://auth0.com/docs/customize/actions/flows-and-triggers/login-flow/api-object#authentication)
- Auth0 docs · [api.authentication.enrollWith](https://auth0.com/docs/customize/actions/flows-and-triggers/login-flow/api-object#authentication)
- Auth0 docs · [Customize MFA Factors using Actions](https://auth0.com/docs/secure/multi-factor-authentication/customize-mfa-actions)
- `scripts/configure-auth0.sh` — sección PostLogin Actions
- `INSTALL.md` § 4 "Auth0 desde cero: tutorial completo" — setup inicial.
- `INSTALL.md` § 15 "Troubleshooting Auth0" — los 3 bugs documentados.
- BUG-001 / SEC-006 — relacionados al setup correcto del M2M client para
  el invite endpoint (`POST /v1/tenants/{id}/members`).
- BUG-006 — `platform_owner` cayendo al onboarding por roles vacíos en el
  JWT; relacionado con sub-caso 2c.
