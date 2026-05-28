# Auth0 — modelo de credenciales y configuración

El core usa Auth0 para autenticación OIDC (RS256 + JWKS) y MFA.
Esta guía explica **por qué hay 3 capas separadas de credenciales**
(no es un accidente — es defensa en profundidad) y **cómo
configurarlas con el comando `auth0-configure`**.

---

## El modelo: 3 capas, 3 lifecycles distintos

```
┌─────────────────────────────────────────────────────────────────┐
│  Capa 1: SECRETS DEL RUNTIME LOCAL                             │
│                                                                 │
│  Archivo:   .env                                                │
│  Generador: python -m copiloto_core generate-secrets           │
│  Contiene:  JWT_SECRET, APP_DB_PASSWORD, POSTGRES_PASSWORD,    │
│             SERVICE_TOKEN, S3_SECRET_ACCESS_KEY                 │
│  Lifecycle: regenerás solo si rotás (incidente, audit)         │
│  Risk:      si leakea → comprometé tokens internos + DB local  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Capa 2: CONFIG AUTH0 DEL DEPLOYMENT                           │
│                                                                 │
│  Archivo:   .env.auth0.local        ← SEPARADO del .env       │
│  Generador: python -m copiloto_core auth0-configure            │
│  Contiene:  AUTH0_DOMAIN, AUTH0_API_AUDIENCE,                   │
│             AUTH0_CLAIMS_NAMESPACE                              │
│  Lifecycle: una sola vez por tenant Auth0 (raro cambiar)       │
│  Risk:      si leakea → info pública, no es secreto            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Capa 3: CREDENCIALES MANAGEMENT API DE AUTH0                  │
│                                                                 │
│  Archivo:   NADA EN DISCO — solo en tu shell env (ephemeral)   │
│  Set vía:   export MGMT_CLIENT_ID=xxx MGMT_CLIENT_SECRET=yyy   │
│  Usadas por: configure-auth0 al correr (UNA VEZ)               │
│  Lifecycle: "olvidás" después de cada uso (`unset` o nueva     │
│             shell). Auth0 rota el client_secret cada N meses.  │
│  Risk:      MÁXIMO. Si leakea → control total del tenant Auth0:│
│             crear/borrar users, modificar claims, ver MFA seeds│
└─────────────────────────────────────────────────────────────────┘
```

### Por qué SEPARADOS

Si todo viviera en un solo `.env`:

- Un `git status` accidental podría exponer las llaves de Capa 3.
- Backups del proyecto contienen credenciales que controlan TODO Auth0.
- Docker volumes / staging deployments heredarían el blast radius
  máximo.
- Rotar el JWT_SECRET (operación común) requeriría tocar el mismo
  archivo que las llaves más sensibles.

Con el split:

- **Capa 1** rota frecuente, sin tocar nada de Auth0.
- **Capa 2** estable, info pública (no necesita secrecy especial).
- **Capa 3** **NUNCA TOCA DISCO** en el flujo normal. La pasás
  en el momento, la usás, la olvidás.

### Settings lee ambos archivos automáticamente

En `copiloto_core/core/config.py`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '.env.auth0.local'),
        env_file_encoding='utf-8',
        ...
    )
```

Cuando uvicorn arranca, Settings lee ambos archivos en orden. No
hay que hacer nada manual.

---

## Configurar Auth0 (paso a paso)

### Pre-requisito: tener un tenant Auth0 + un Application M2M

1. Creá una cuenta en https://auth0.com (free tier sirve para dev).
2. Auth0 dashboard → **Applications → API Explorer Application** —
   esta es la app M2M con permisos del Management API.
3. Anotá `Client ID` y `Client Secret` (los necesitás abajo).
4. Anotá tu **Auth0 Domain** (algo como `tu-tenant.us.auth0.com`).

### Correr `auth0-configure`

```bash
# 1. Exportá las credenciales SOLO al shell (NO al .env)
export MGMT_CLIENT_ID='paste_del_dashboard'
export MGMT_CLIENT_SECRET='paste_del_dashboard'
export AUTH0_DOMAIN='tu-tenant.us.auth0.com'

# 2. Corré el configure
python -m copiloto_core auth0-configure
```

> **v1.5.1+**: los defaults de Callback URLs apuntan a `localhost:8000`
> (consumer flow con uvicorn). Para versiones anteriores, o si tu app
> corre en otro puerto, override con:
>
> ```bash
> export ADMIN_CALLBACKS='http://localhost:8000/admin/callback'
> export ADMIN_LOGOUTS='http://localhost:8000/,http://localhost:8000'
> export ADMIN_ORIGINS='http://localhost:8000'
> ```
>
> Para producción, agregá también tus URLs reales:
>
> ```bash
> export ADMIN_CALLBACKS='http://localhost:8000/admin/callback,https://app.satguajira.com/admin/callback'
> ```

Esto, en orden:

1. **Solicita un Management API access_token** usando tu M2M
   credentials.
2. **Crea/actualiza un Resource Server (API)** con audience =
   `https://api.<tu-domain>/`.
3. **Crea/actualiza un SPA Client** para el admin panel.
4. **Crea/actualiza un M2M Client** para el backend interno.
5. **Sube 3 Actions** al tenant (los `.js` en
   `copiloto_core/scripts/auth0_actions/`):
   - `custom_claims.js` — inyecta `tenant_id`, `roles`, etc. al
     id_token + access_token.
   - `account_linking.js` — vincula identidades sociales al usuario
     primario.
   - `mfa_challenge.js` — desafía MFA según política.
6. **Configura los hooks** para que las Actions corran en `post-login`
   y `pre-user-registration`.
7. **Escribe `.env.auth0.local`** con las URLs y audience.

### Cleanup

```bash
# 3. Olvidá las credenciales del Management API
unset MGMT_CLIENT_ID MGMT_CLIENT_SECRET AUTH0_DOMAIN

# 4. Confirmá que NO están en .env ni .env.auth0.local
grep -E "MGMT_CLIENT" .env .env.auth0.local 2>/dev/null
# Esperado: sin matches
```

### Restart la app

```bash
# Ctrl+C en uvicorn, después:
./scripts/dev-up.sh   # uvicorn lee .env.auth0.local automáticamente
```

---

## Activar MFA Policy en Auth0 (requerido para el admin SPA)

El core ENFORCE MFA por default (`MFA_ENFORCEMENT_ENABLED=true`).
`configure-auth0` instala los **factores** MFA en tu tenant (TOTP,
WebAuthn) pero **NO activa la Policy** que obliga a los users a
enrollarlos — eso queda como step manual.

**Si saltás este step**, te encontrás con un loop infinito en el
admin SPA: el core marca tu sesión como `mfa_required=true`, el SPA
hace auto-logout esperando que Auth0 pida MFA, Auth0 te loguea sin
MFA otra vez, loop.

### Pasos (una sola vez por tenant)

1. https://manage.auth0.com → **Security** (sidebar) → **Multi-Factor Auth**.
2. Sección **"Factors"**: confirmá que al menos un factor está ON
   (OTP, WebAuthn).
3. Sección **"Define policies"**: cambiá a **Always require** o
   **Use Adaptive MFA**.
4. **Save**.

A partir del próximo login, Auth0 va a pedir MFA enrollment en la
primera entrada y MFA challenge en las siguientes.

### Si querés bypass para iterar en dev local

Setealo EXPLÍCITO en tu `.env` (no hay default mágico — vos lo decidís):

```
MFA_ENFORCEMENT_ENABLED=false
```

⚠ **Solo dev local**. NUNCA en producción — desactiva una capa
crítica de seguridad para platform_owners y users con roles
privilegiados.

---

## Modo dev local SIN Auth0

Para iterar sin tener Auth0 configurado (el caso típico durante
desarrollo de un módulo), **no hace falta correr `auth0-configure`**.
El `.env.example` del scaffolder ya trae placeholders:

```
AUTH0_DOMAIN=tu-tenant.auth0.com
AUTH0_API_AUDIENCE=https://api.satguajira.local
AUTH0_MGMT_CLIENT_ID=
AUTH0_MGMT_CLIENT_SECRET=
```

La app arranca igual. Lo que cambia:

- **Endpoints SIN auth (públicos)** funcionan: `/v1/branding`,
  `/v1/<modulo>/health`, `/openapi.json`, `/metrics` (si IP allowlisted).
- **Endpoints CON auth** (`Depends(authenticate_request)`) devuelven
  `401 Unauthorized` porque el JWT no se puede validar contra un
  Auth0 inexistente.

Para testear endpoints con auth durante dev sin Auth0, podés:

- Generar JWTs mockeados con tu `JWT_SECRET` local (ver
  [docs/EXTENDING.md § Testing con auth fake](EXTENDING.md)).
- O usar el `SERVICE_TOKEN` para llamadas service-to-service (no
  pasa por OIDC, valida HMAC).

---

## Rotar credenciales

### Rotar `JWT_SECRET` (Capa 1)

```bash
# Generá un nuevo secret y appendealo
NEW=$(openssl rand -base64 48 | tr '+/' '-_' | tr -d '=')

# Editá .env manualmente y reemplazá JWT_SECRET con $NEW
# O programáticamente:
sed -i '' "s|^JWT_SECRET=.*|JWT_SECRET=$NEW|" .env

# Restart uvicorn
```

Todos los JWTs emitidos con el secret viejo van a fallar. Los
users tendrán que re-loguearse. Para rotación sin downtime ver
`docs/auth0_keys_rotation.md`.

### Rotar `AUTH0_MGMT_CLIENT_SECRET` (Capa 3)

1. Auth0 dashboard → Applications → API Explorer Application →
   Settings → **Rotate Secret**.
2. Anotá el secret nuevo, descartá el viejo.
3. Para la PRÓXIMA vez que corras `auth0-configure`, usá el nuevo.

No requiere cambios en disco — el secret viejo no estaba guardado.

### Rotar `AUTH0_DOMAIN` (Capa 2)

Cambio de tenant Auth0. Operación rara. Pasos:

1. Configurá el nuevo tenant Auth0 con `auth0-configure --domain=...`.
2. Migrá los users (Auth0 tiene tool de import/export).
3. Actualizá `.env.auth0.local` con el nuevo dominio.
4. Restart uvicorn.

---

## Troubleshooting Auth0

| Error | Causa | Fix |
|---|---|---|
| `401 Unauthorized` en endpoints con auth, app arranca OK | Auth0 no configurado | Corré `auth0-configure` o desactivá auth en dev |
| `MGMT_CLIENT_ID es obligatorio` al correr configure | Olvidaste el `export` | `export MGMT_CLIENT_ID=...` |
| `Failed to get access_token` | M2M credentials inválidas | Verificá que copiaste bien del dashboard |
| `Action `custom_claims` failed to deploy` | Versión de Actions API cambió | Ver runbook `docs/auth0_keys_rotation.md` |
| App arranca pero `Settings.auth0_domain` está vacío | `.env.auth0.local` no se creó | `configure-auth0` no terminó OK; corré con `LOG_LEVEL=DEBUG` |

---

## Referencias

- [INSTALL.md](../INSTALL.md) § Auth0 setup — guía visual con
  screenshots del dashboard.
- `docs/auth0_keys_rotation.md` — runbook operacional de rotación
  con zero-downtime.
- `copiloto_core/scripts/auth0_actions/*.js` — código fuente de
  las Actions que se suben al tenant.
- `copiloto_core/scripts/configure-auth0.sh` — el script bash que
  el subcomando invoca (1558 líneas, 2 audits cerrados).
