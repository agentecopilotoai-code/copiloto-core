# Guía de instalación — Copiloto Core

Esta guía explica los pasos para instalar el core desde cero, qué
variables de entorno existen y cómo validar que la base de datos quedó
creada con sus tablas.

## 0. Instalación desde cero

### 0.1 Pre-condiciones (una sola vez)

Antes de levantar el stack, configurá los servicios externos:

1. **Auth0** — un tenant + 1 M2M client bootstrap (ver § 4.1–4.2).
2. **Resend** (opcional pero recomendado) — cuenta + dominio
   verificado para emails de invitación (ver § 4.3).

Después, automatizá TODA la configuración del tenant Auth0 con:

```bash
# Variables de la pre-condición:
export AUTH0_DOMAIN="copilotai.us.auth0.com"
export MGMT_CLIENT_ID="..."
export MGMT_CLIENT_SECRET="..."

bash scripts/configure-auth0.sh
```

Esto crea apps, API, roles, Actions, MFA, attack protection, etc. — 17
secciones idempotentes (ver § 4.4 para detalle completo).

### 0.2 Levantar el stack local

```bash
git clone https://github.com/agentecopilotoai-code/copiloto-core.git
cd copiloto-core
./scripts/generate-local-secrets.sh
./scripts/bootstrap.sh --reset --yes
./scripts/smoke-test.sh
```

Si ya tienes el repo clonado:

```bash
cd /ruta/a/copiloto-core
git pull
./scripts/bootstrap.sh --reset --yes
./scripts/smoke-test.sh
```

> `--reset --yes` borra los volúmenes locales de Docker Compose, incluida
> la base PostgreSQL local. Úsalo solo en desarrollo.

### 0.3 Pasos manuales restantes (después del script Auth0)

| # | Acción | Dónde | Una sola vez |
|---|---|---|---|
| 1 | Habilitar `copilotoia-admin-web` en DB connection | Auth0 Dashboard → Authentication → Database → Username-Password-Authentication → Applications → toggle ON | ✓ |
| 2 | Crear el primer Platform Owner user | Auth0 Dashboard → User Management → Users → Create + Verify Email | ✓ |
| 3 | Asignarle rol `platform_owner` | Re-correr el script con `BOOTSTRAP_PLATFORM_OWNER_EMAIL=...` | ✓ |
| 4 | Verificar dominio en Resend | Resend Dashboard → Domains → agregar DNS records | ✓ |
| 5 | Pasar `AUTH0_TRUST_ADMIN_EMAIL_HEADER=false` | `.env` (después de verificar que el claim email llega) | ✓ |

Detalle de cada uno en § 4.5–4.9.

## 1. Requisitos

- Docker Desktop 4.x o Docker Engine 24+.
- `docker compose` v2.
- Bash + `openssl` + `curl` (vienen por defecto en macOS / Linux).
- Auth0 tenant configurado (ver § 4) para tener login funcional.

## 2. Variables de entorno

`scripts/generate-local-secrets.sh` genera un `.env` con valores aleatorios
para desarrollo local. En producción debes proveer estos valores manualmente:

| Variable                          | Descripción                                              |
| --------------------------------- | -------------------------------------------------------- |
| `DATABASE_URL`                    | postgresql://app_user:pass@host:5432/copilotoia          |
| `DATABASE_ADMIN_URL`              | URL con usuario admin (DDL + ROLES + RLS bypass)         |
| `JWT_SECRET`                      | secreto HS256 para firmar/verificar tokens del BFF       |
| `JWT_ISSUER`                      | `https://<tu-tenant>.auth0.com/`                         |
| `JWT_AUDIENCE`                    | audience del API en Auth0                                |
| `SERVICE_TOKEN`                   | token compartido para llamadas M2M al API                |
| `SERVICE_TOKEN_NEXT`              | (opcional) slot de rotación de SERVICE_TOKEN             |
| `S3_ENDPOINT_URL`                 | endpoint S3 (MinIO en local; AWS en prod)                |
| `S3_BUCKET`                       | bucket para uploads del admin                            |
| `S3_ACCESS_KEY_ID`                | key id (MinIO o AWS)                                     |
| `S3_SECRET_ACCESS_KEY`            | secret access key                                        |
| `AI_PROVIDER_MASTER_KEY`          | Fernet key (32 bytes base64) para cifrar API keys en DB  |
| `OBSERVABILITY_ALLOWED_IPS`       | CIDRs permitidos para hitear `/metrics`                  |
| `AUTH0_TRUST_ADMIN_EMAIL_HEADER`  | `true` por compat / `false` cuando A-003 esté deployado  |
| `RESEND_API_KEY_FILE`             | path al file con la Resend API key (chmod 600)           |
| `EMAIL_FROM_ADDRESS`              | sender de los emails (dominio verificado en Resend)      |
| `EMAIL_FROM_NAME`                 | display name del sender (ej. "CopilotoIA")               |
| `APP_PUBLIC_URL`                  | URL pública del SPA para construir links de invitación   |
| `INVITATION_TOKEN_TTL_SECONDS`    | TTL del token de invitación (default 7d)                 |
| `INVITATION_SEND_RATE_PER_HOUR`   | rate-limit anti-spam por inviter (default 20)            |

## 3. Tablas del core (verificación)

Tras `bootstrap.sh`, deberías ver el schema `app.*` poblado. Verificación
mínima:

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "\dt app.*"
```

Debe listar al menos: `tenants`, `users`, `user_tenant_roles`,
`user_preferences`, `auth_sessions`, `audit_logs`, `operator_alerts`,
`data_retention_policies`, `backup_runs`, `tenant_legal_documents`,
`tenant_modules`, `platform_secrets`, `platform_ai_providers`,
`provider_dispatch`, `feature_flags`, `role`, `capability`,
`role_capability`.

## 4. Auth0 — setup completo desde tenant limpio

`scripts/configure-auth0.sh` automatiza **17 secciones** de configuración
del tenant Auth0 (apps, API, roles, Actions, MFA, attack protection,
email provider, etc.). Solo necesitas hacer **2 cosas a mano** antes de
correrlo y **1 después**.

### 4.1 Crear el tenant Auth0 (manual, una vez)

1. Sign-up gratis en https://auth0.com → "Create tenant".
2. Elegí region (US/EU) y nombre, ej. `copilotai`.
3. Tu domain resultante: `copilotai.us.auth0.com` (lo vas a usar
   abajo como `AUTH0_DOMAIN`).

> **Sin upgrade**: el free tier alcanza para dev + producción chica
> (~7K MAUs). Si vas a producción seria con SSO enterprise o MFA add-on
> agresivo, considerá B2B Essentials.

### 4.2 Bootstrap del Management API M2M (manual, una vez)

Auth0 no permite que un script se cree a sí mismo — necesita un M2M
client pre-existente para llamar Management API. Es **el único paso
manual obligatorio** antes del script.

1. Dashboard → **Applications** → Applications → "+ Create Application"
2. Name: `bootstrap-m2m` (o el nombre que prefieras)
3. Type: **Machine to Machine Applications** → Create
4. "Authorize Auth0 Management API" → seleccioná **TODOS** estos
   scopes (la lista que el script necesita):

   ```
   read:resource_servers, create:resource_servers, update:resource_servers
   read:clients, create:clients, update:clients
   read:client_grants, create:client_grants, update:client_grants
   read:roles, create:roles, update:roles
   read:role_members, create:role_members
   read:users, create:users, update:users
   create:user_tickets
   read:actions, create:actions, update:actions
   read:connections, update:connections
   read:tenant_settings, update:tenant_settings
   read:guardian_factors, update:guardian_factors
   read:attack_protection, update:attack_protection
   read:email_provider, create:email_provider, update:email_provider, delete:email_provider
   read:email_templates, create:email_templates, update:email_templates
   read:prompts, update:prompts
   ```

5. Click "Authorize". Después abre el app → tab **Settings** → copia
   `Client ID` y `Client Secret`. Los vas a usar abajo.

> **Por qué no se puede automatizar**: para crear un M2M autorizado
> necesitás llamar Management API, y para llamar Management API
> necesitás un M2M autorizado. Catch-22 — Auth0 lo resuelve forzando
> que el primer M2M se cree a mano.

### 4.3 (Opcional pero recomendado) Crear cuenta Resend

Si querés que el flow de invitaciones M61 mande emails reales (en lugar
de quedar en modo NO-OP loggeando "would_send"):

1. Sign-up gratis en https://resend.com (free tier: 3K emails/mes).
2. **API Keys** → "Create API Key" → Name: `copilotoia-prod` (o `dev`)
   → Permission: "Sending access" → Create. Copiá la key `re_xxx...`.
3. **Domains** → "Add Domain" → entrá tu dominio (ej. `app.copilotoia.com`)
   → Resend te da 3 DNS records (SPF + DKIM + DMARC) para agregar en
   tu DNS provider. Verificación toma ~5 minutos.

> Si no querés verificar dominio ya: podés usar `onboarding@resend.dev`
> como sender — Resend solo te deja mandar a TU MISMO email registrado
> en Resend. Útil para testing del flow, NO para producción.

Guardá la API key:

```bash
mkdir -p .secrets
echo -n 're_xxxxxxxxxxxx' > .secrets/resend-api-key
chmod 600 .secrets/resend-api-key
```

### 4.4 Correr el script (configura todo lo demás automático)

Con el M2M bootstrap ya creado y los credenciales en mano:

```bash
# Variables obligatorias
export AUTH0_DOMAIN="copilotai.us.auth0.com"   # de § 4.1
export MGMT_CLIENT_ID="..."                     # de § 4.2
export MGMT_CLIENT_SECRET="..."                 # de § 4.2
export COPILOTOIA_DOMAIN="app.copilotoia.com"   # tu dominio (o copilotoia.local en dev)

# (Opcional pero recomendado) Resend integration
export CONFIGURE_RESEND_PROVIDER=true
export RESEND_API_KEY="re_..."                  # de § 4.3
export EMAIL_FROM_ADDRESS="invites@app.copilotoia.com"  # dominio verificado en Resend
export EMAIL_FROM_NAME="CopilotoIA"

# (Opcional) MFA forzado para roles privilegiados
export ENFORCE_MFA_ACTION=true

# (Opcional) Mostrar el service_client_secret en el output para copiarlo
export OUTPUT_SECRETS=true

bash scripts/configure-auth0.sh
```

El script ejecuta **17 secciones idempotentes** (re-correrlo es seguro):

| # | Sección | Qué configura |
|---|---|---|
| 1 | API resource server | `copilotoia-core-api` con 30+ scopes (tenants:*, conversations:*, etc.) |
| 2 | Admin app (`copilotoia-admin-web`) | Regular Web App + callbacks + refresh token rotation |
| 3 | Service M2M (`copilotoia-service-m2m`) | M2M con Management API scopes para que el backend invite users |
| 4 | Roles + permisos | platform_owner, owner, admin, manager, agent, viewer, support |
| 5 | Action: custom claims | Emite `roles`, `permissions`, `tenant_id`, `email`, `mfa_verified` en access_token |
| 6 | Action: MFA challenge | Fuerza MFA si rol privilegiado y no verificado (opcional, vía `ENFORCE_MFA_ACTION`) |
| 7 | Tenant settings | friendly_name, support_url, session_lifetime |
| 8 | Universal Login → new | UI 2024, responsive, identifier_first |
| 9 | DB Connection policy | password_policy=good, history=5, brute_force_protection |
| 10 | MFA factors | OTP + WebAuthn (roaming + platform) habilitados |
| 11 | Attack protection | Brute force + breached password (HIBP) + IP throttling |
| 12 | Resend SMTP provider | Todos los emails de Auth0 salen vía Resend con TU dominio |
| 13 | Email templates ES | 7 templates con subjects en español |
| 14 | Action: account linking | Auto-link de identidades del mismo email verificado |
| 15 | Platform owner bootstrap | Si seteás `BOOTSTRAP_PLATFORM_OWNER_EMAIL`, le asigna el rol |
| 16 | `.env.auth0.local` | Guarda los IDs de las apps + paths a los secret files |
| 17 | `.secrets/auth0-*-secret` | Persiste client secrets con chmod 600 |

Al terminar imprime un summary con qué se aplicó. Si ves ⚠ HTTP 403,
faltan scopes al M2M bootstrap — re-corré § 4.2 agregando los que faltan.

### 4.5 Habilitar la connection database para el admin app (manual, una vez)

Auth0 movió `enabled_clients` a una API que no se puede mutar via script
en tenants nuevos. Un click manual:

1. Dashboard → **Authentication** → Database
2. Click en **Username-Password-Authentication**
3. Tab **Applications**
4. Toggle **ON** para `copilotoia-admin-web`
5. (Opcional) toggle OFF para apps de otros proyectos si tu tenant es compartido

Sin esto: el form email+password no aparece en la pantalla de login y los
users no pueden registrarse.

### 4.6 (Opcional) Crear el primer Platform Owner

El script puede asignarle el rol `platform_owner` automático si el user
ya existe en Auth0. Pero crear el user inicial es manual (Auth0 exige
consent del dueño del email):

1. Dashboard → **User Management** → Users → "+ Create User"
2. Connection: `Username-Password-Authentication`
3. Email + password
4. Después del create → "Send Verification Email" → seguí el link del
   email para verificar.
5. Re-correr el script con `BOOTSTRAP_PLATFORM_OWNER_EMAIL=<email>` para
   asignar el rol + setear `app_metadata.support_mode=true`:

   ```bash
   export BOOTSTRAP_PLATFORM_OWNER_EMAIL="vos@copilotoia.com"
   bash scripts/configure-auth0.sh
   ```

### 4.7 Cargar la config en el Core

El script generó `.env.auth0.local` y `.secrets/auth0-*-secret`. Tu
`.env` principal debe tener (ya viene en `.env.example`):

```bash
# Para que el Core lea el access_token con audience correcto:
AUTH0_DOMAIN=copilotai.us.auth0.com
AUTH0_AUDIENCE=https://app.copilotoia.com/api
AUTH0_ISSUER=https://copilotai.us.auth0.com/
AUTH0_CLAIMS_NAMESPACE=https://app.copilotoia.com/claims

# Para el BFF admin (OAuth flow):
# Los valores de AUTH0_ADMIN_* vienen de .env.auth0.local
# (se sourcea automático si lo agregás en el `env_file:` del docker-compose).

# M60/A-003 — empezá en true (compat). Pasalo a false una vez que
# verificás que el access_token trae el claim 'email' namespaced:
AUTH0_TRUST_ADMIN_EMAIL_HEADER=true
```

Restart del Core para que cargue la config:

```bash
docker compose restart admin-panel api
```

### 4.8 Verificación end-to-end

```bash
# 1. Logueo en el SPA
open http://localhost:3000/admin/

# 2. Click "Iniciar sesión" → Auth0 login → MFA (si forzaste con ENFORCE_MFA_ACTION)
# 3. Deberías aterrizar en /admin/ con tu profile cargado

# 4. (Si sos platform_owner) ver Fleet:
open http://localhost:3000/admin/platform/platform-fleet

# 5. Crear un tenant + invitar a otro user (a tu propio email si usás
#    onboarding@resend.dev sender) → debería llegar el email de invitación.
docker compose logs api | grep -i 'email.resend' | tail -10
# Esperás ver: "email.resend.sent message_id=msg-xxx"
```

### 4.9 Hardening post-deploy (recomendado para producción)

Después de validar el flow completo:

```bash
# 1. Verificar que el access_token trae el claim 'email' namespaced:
docker compose logs admin-panel | grep email_from_header_fallback | tail -5
# Si NO aparece nada → el Action está populating bien.
# Si aparece → re-correr scripts/configure-auth0.sh (el Action se re-deploya).

# 2. Cuando ya no aparece el warning, deshabilitar el header trust:
# Editar .env:
AUTH0_TRUST_ADMIN_EMAIL_HEADER=false
docker compose restart api
```

> Este toggle existía como fallback para compat M58. Una vez verificado
> que el Auth0 Action emite el `email` claim correctamente, cerrarlo
> elimina el último vector de hijack de invitaciones (A-003).

### 4.10 Variables del script — referencia completa

Ver header de `scripts/configure-auth0.sh` para la lista exhaustiva.
Toggles principales:

| Variable | Default | Qué hace |
|---|---|---|
| `CONFIGURE_TENANT_SETTINGS` | `true` | friendly_name + support_url + session TTL |
| `CONFIGURE_UNIVERSAL_LOGIN` | `true` | UI 2024 responsive |
| `CONFIGURE_DB_CONNECTION` | `true` | password policy + brute force |
| `CONFIGURE_MFA_FACTORS` | `true` | OTP + WebAuthn habilitados |
| `CONFIGURE_ATTACK_PROTECTION` | `true` | brute force + breached + IP throttle |
| `CONFIGURE_RESEND_PROVIDER` | `false` | opt-in: SMTP de Auth0 vía Resend |
| `CONFIGURE_EMAIL_TEMPLATES` | `true` | 7 templates con subjects ES |
| `CONFIGURE_ACCOUNT_LINKING` | `true` | Action de auto-link por email |
| `ENFORCE_MFA_ACTION` | `false` | opt-in: Action que challengea MFA para roles privilegiados |
| `BOOTSTRAP_PLATFORM_OWNER_EMAIL` | `""` | si se setea, asigna rol platform_owner al user |
| `OUTPUT_SECRETS` | `false` | imprime client secret del M2M (solo primera vez) |

## 5. Primer login

Una vez levantado el stack y configurado Auth0:

1. Abre `http://localhost:3000/admin/`.
2. Click en "Iniciar sesión" → completa el flow Auth0.
3. La primera vez aterrizas en `/no-tenant` (no tienes tenant todavía).
4. Si tu profile tiene el rol global `platform_owner` (configurable en
   Auth0 vía `app_metadata.roles`), también ves el panel `/platform`.

## 6. Crear el primer tenant

Desde la pantalla `/no-tenant`:

1. Llena el form: nombre, slug, vertical, país.
2. Submit → llama `POST /v1/tenant-signup`.
3. El backend te crea como `owner` del tenant nuevo.
4. Redirige a `/t/<slug>/tenant-setup`.

Alternativamente, un `platform_owner` puede crear tenants para terceros
desde Fleet (`/platform/platform-fleet` → "Crear tenant"). El owner del
tenant se invita después por email.

## 7. Activar un módulo opt-in para un tenant

Como `platform_owner`, en Fleet → seleccionar tenant → panel "Módulos":
toggle ON. Cada módulo opt-in puede tener pre-requisitos (modalidades IA
configuradas, etc.). Ver el README del módulo específico.

## 8. Observabilidad opt-in

```bash
docker compose --profile observability up -d
```

Prometheus en `:9090`, Grafana en `:3001` (admin/`GRAFANA_ADMIN_PASSWORD`).

## 9. Backups

```bash
docker compose --profile backups up -d backup-worker
```

Configurar `BACKUP_S3_BUCKET`, `BACKUP_GPG_RECIPIENT`,
`BACKUP_GPG_PUBKEY_PATH` en `.env`.

## 10. Producción

- Tu cluster ofrece TLS (load balancer → API + admin-panel).
- `POSTGRES_*` apunta a un Postgres administrado (no compose).
- `S3_*` apunta a S3 (AWS, GCS, etc.), no MinIO.
- Backups habilitados con GPG firmado.
- Observabilidad apuntando a tu Prometheus/Grafana del cluster.
- Auth0 en su propio tenant productivo (no compartido con dev).
