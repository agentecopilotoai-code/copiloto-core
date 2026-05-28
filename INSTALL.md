# Instalación — CopilotoIA Core

Guía completa de instalación: desde dev local (5 minutos) hasta
producción endurecida (Auth0 + Resend + S3 + observability).

---

## Tabla de contenidos

1. [Pre-flight check](#1-pre-flight-check)
2. [Dev local — 5 minutos](#2-dev-local--5-minutos)
3. [Setup completo de Auth0](#3-setup-completo-de-auth0)
4. [Setup completo de Resend](#4-setup-completo-de-resend)
5. [Configurar AI providers](#5-configurar-ai-providers)
6. [Variables de entorno — referencia](#6-variables-de-entorno--referencia)
7. [Verificación post-bootstrap](#7-verificación-post-bootstrap)
8. [Perfiles opt-in: backups y observability](#8-perfiles-opt-in-backups-y-observability)
9. [Checklist de producción](#9-checklist-de-producción)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Pre-flight check

### Requisitos del host

| Herramienta | Versión mínima | Verificar |
|-------------|----------------|-----------|
| Docker Desktop | 4.x | `docker --version` |
| docker compose | v2 | `docker compose version` |
| bash | 4+ | `bash --version` |
| openssl | 1.1+ | `openssl version` |
| curl | 7.6+ | `curl --version` |
| git | 2.x | `git --version` |
| python | 3.12+ (opcional, solo si corrés tests fuera del container) | `python3 --version` |
| node | 22+ (opcional, solo si desarrollás admin-panel localmente) | `node --version` |

### Cuentas externas necesarias

| Servicio | Requerido | Plan free alcanza | Para qué |
|----------|-----------|-------------------|----------|
| **Auth0** | ✅ Sí | Sí (7K MAUs) | Login + MFA + Management API |
| **Resend** | ⚠️ Recomendado | Sí (3K emails/mes) | Email transaccional (invitaciones) |
| **OpenAI** | ⚠️ Si usás IA cloud | Pay-as-you-go | LLM / Image / TTS / STT |
| **Anthropic** | Alternativo a OpenAI | Pay-as-you-go | LLM (Claude) |
| **xAI** | Alternativo (multimodal) | Pay-as-you-go | LLM / Image / Video / TTS / STT |
| **ElevenLabs** | Si usás voice cloning premium | Sí (limited) | TTS premium |
| **AWS S3 / Cloudflare R2** | Solo prod | Sí | Backups off-site + uploads prod |

**Para dev local podés saltarte todos los servicios externos** — el
stack levanta con providers locales y emails NO-OP por default.

---

## 2. Dev local — 5 minutos

### Setup mínimo (sin Auth0 ni IA cloud)

```bash
# 1. Clonar
git clone https://github.com/agentecopilotoai-code/copiloto-core.git
cd copiloto-core

# 2. Generar secrets random
./scripts/generate-local-secrets.sh

# 3. Bootstrap completo (postgres + redis + minio + api + admin-panel)
./scripts/bootstrap.sh --reset --yes

# 4. Smoke test
./scripts/smoke-test.sh

# 5. Abrir admin
open http://localhost:3000/admin
```

> `--reset --yes` **borra los volúmenes locales de Docker**, incluida
> la base PostgreSQL. **Úsalo solo en desarrollo.**

### Setup completo (con Auth0 real + invitaciones por email)

Necesitás haber completado [§ 3 (Auth0)](#3-setup-completo-de-auth0) y
[§ 4 (Resend)](#4-setup-completo-de-resend) antes.

```bash
# Variables Auth0 obtenidas del setup manual del bootstrap M2M
export AUTH0_DOMAIN="copilotai.us.auth0.com"
export MGMT_CLIENT_ID="..."
export MGMT_CLIENT_SECRET="..."
export COPILOTOIA_DOMAIN="copilotoia.local"

# Variables Resend (opcional)
export CONFIGURE_RESEND_PROVIDER=true
export RESEND_API_KEY="re_..."
export EMAIL_FROM_ADDRESS="invites@app.copilotoia.com"
export EMAIL_FROM_NAME="CopilotoIA"

# Variables opcionales
export ENFORCE_MFA_ACTION=true        # MFA forzado para roles privilegiados
export BOOTSTRAP_PLATFORM_OWNER_EMAIL="tu@email.com"  # primer admin

# Correr setup automatizado (17 secciones, idempotente)
bash scripts/configure-auth0.sh

# Levantar el stack
./scripts/bootstrap.sh --reset --yes
```

---

## 3. Setup completo de Auth0

`scripts/configure-auth0.sh` automatiza 17 secciones del setup del
tenant Auth0. **Solo 2 cosas son manuales** antes del script y **1
después**.

### 3.1 Crear el tenant Auth0 (manual, una vez)

1. Abrí **https://auth0.com/signup**.
2. Sign-up con email + password (o Google login).
3. En "What's your tenant name?":
   - **Tenant name:** `copilotai` (o el que prefieras — esto NO se cambia
     después; queda como tu domain forever).
   - **Region:** `US` para Norteamérica/Latam, `EU` para Europa, `AU`
     para Asia/Pacífico.
   - **Environment Type:** `Development` para empezar (después podés
     crear un `Production` tenant aparte para el deploy real).
4. Click "Create Account" → te redirige al dashboard del tenant nuevo.

URL del dashboard:
```
https://manage.auth0.com/dashboard/<region>/<tenant-name>/
```

Tu **`AUTH0_DOMAIN`** será `<tenant-name>.<region>.auth0.com`
(ej. `copilotai.us.auth0.com`).

> El free tier alcanza para dev + producción chica (~7K MAUs). Para SSO
> enterprise o MFA add-on agresivo, considerá B2B Essentials.

### 3.2 Bootstrap del Management API M2M (manual, una vez)

Auth0 no permite que un script se cree a sí mismo — necesita un M2M
client pre-existente para llamar Management API.

#### Paso 1 — Confirmar tu `AUTH0_DOMAIN`

1. En el dashboard, esquina superior IZQUIERDA → tenant name + bandera.
2. Click → menú con:
   - **Domain:** `copilotai.us.auth0.com` ← **valor de `AUTH0_DOMAIN`**.
   - Region badge (US/EU/AU).

#### Paso 2 — Crear el M2M client

1. Sidebar izquierdo → **`Applications`** → sub-item **`Applications`**.
2. Botón naranja arriba a la derecha: **`+ Create Application`**.
3. Modal:
   - **Name:** `bootstrap-m2m`
   - **Choose an application type:** **"Machine to Machine Applications"** (4to tile).
4. Click **`Create`**.

#### Paso 3 — Autorizar el M2M contra Management API + scopes

5. Modal **"Authorize Machine to Machine Application"**:
   - **Select an API:** **"Auth0 Management API"** (auto-creada por Auth0).
6. Marcá los **34 scopes** siguientes (Ctrl+F en el browser para
   encontrarlos rápido):

   <details>
   <summary>Lista completa de scopes (click para expandir)</summary>

   **Resource Servers (APIs):**
   - `read:resource_servers`
   - `create:resource_servers`
   - `update:resource_servers`

   **Clients (apps):**
   - `read:clients`
   - `create:clients`
   - `update:clients`

   **Client Grants:**
   - `read:client_grants`
   - `create:client_grants`
   - `update:client_grants`

   **Roles:**
   - `read:roles`
   - `create:roles`
   - `update:roles`
   - `read:role_members`
   - `create:role_members`

   **Users:**
   - `read:users`
   - `create:users`
   - `update:users`
   - `create:user_tickets`

   **Actions:**
   - `read:actions`
   - `create:actions`
   - `update:actions`

   **Connections:**
   - `read:connections`
   - `update:connections`

   **Tenants:**
   - `read:tenant_settings`
   - `update:tenant_settings`

   **Guardian (MFA factors):**
   - `read:guardian_factors`
   - `update:guardian_factors`

   **Attack Protection:**
   - `read:attack_protection`
   - `update:attack_protection`

   **Email Provider:**
   - `read:email_provider`
   - `create:email_provider`
   - `update:email_provider`
   - `delete:email_provider`

   **Email Templates:**
   - `read:email_templates`
   - `create:email_templates`
   - `update:email_templates`

   **Prompts (Universal Login):**
   - `read:prompts`
   - `update:prompts`

   </details>

7. Click **`Authorize`**.

#### Paso 4 — Copiar Client ID y Secret

8. Auth0 te redirige al detalle de la app `bootstrap-m2m`.
9. Tab **`Settings`** → sección "Basic Information":
   - **Client ID:** ícono "copy" a la derecha. → **`MGMT_CLIENT_ID`**.
   - **Client Secret:** ojo / "copy". → **`MGMT_CLIENT_SECRET`**.

   ⚠️ El **Client Secret es ÚNICO y no se vuelve a mostrar después**.
   Si lo perdés, Auth0 te obliga a rotarlo. Guardalo en password manager:

   ```bash
   export AUTH0_DOMAIN="copilotai.us.auth0.com"
   export MGMT_CLIENT_ID="<pegá acá>"
   export MGMT_CLIENT_SECRET="<pegá acá>"
   ```

#### Paso 5 — Verificar scopes (opcional pero recomendado)

10. Sidebar → **`Applications` → `APIs`** → **"Auth0 Management API"**.
11. Tab **`Machine to Machine Applications`** → expandir `bootstrap-m2m`.
12. Confirmar los 34 scopes chequeados.

> **Si más adelante el script falla con HTTP 403 en alguna sección**:
> te faltó un scope. Volvé acá, agregá el scope que falta, click
> `Update`, y re-corré el script.

### 3.3 Correr el script (configura todo lo demás automático)

```bash
# Variables obligatorias
export AUTH0_DOMAIN="copilotai.us.auth0.com"
export MGMT_CLIENT_ID="..."
export MGMT_CLIENT_SECRET="..."
export COPILOTOIA_DOMAIN="app.copilotoia.com"   # tu dominio (o copilotoia.local en dev)

# (Opcional, recomendado) Resend integration
export CONFIGURE_RESEND_PROVIDER=true
export RESEND_API_KEY="re_..."
export EMAIL_FROM_ADDRESS="invites@app.copilotoia.com"
export EMAIL_FROM_NAME="CopilotoIA"

# (Opcional) MFA forzado para roles privilegiados
export ENFORCE_MFA_ACTION=true

# (Opcional) Mostrar el service_client_secret en el output
export OUTPUT_SECRETS=true

bash scripts/configure-auth0.sh
```

**17 secciones idempotentes** (re-correr es seguro):

| # | Sección | Configura |
|---|---------|-----------|
| 1 | API resource server | `copilotoia-core-api` con 30+ scopes |
| 2 | Admin app (`copilotoia-admin-web`) | Regular Web App + callbacks + refresh token rotation |
| 3 | Service M2M (`copilotoia-service-m2m`) | M2M con Management API scopes |
| 4 | Roles + permisos | platform_owner, owner, admin, manager, agent, viewer, support |
| 5 | Action: custom claims | Emite `roles`, `permissions`, `tenant_id`, `email`, `mfa_verified` en access_token |
| 6 | Action: MFA challenge | Fuerza MFA si rol privilegiado y no verificado (`ENFORCE_MFA_ACTION`) |
| 7 | Tenant settings | friendly_name, support_url, session_lifetime |
| 8 | Universal Login → new UI 2024 | Responsive, identifier_first |
| 9 | DB Connection policy | password_policy=good, history=5, brute_force_protection |
| 10 | MFA factors | OTP + WebAuthn habilitados |
| 11 | Attack protection | Brute force + breached password (HIBP) + IP throttling |
| 12 | Resend SMTP provider | Todos los emails de Auth0 salen vía Resend con TU dominio |
| 13 | Email templates ES | 7 templates con subjects en español |
| 14 | Action: account linking | Auto-link de identidades del mismo email verificado |
| 15 | Platform owner bootstrap | Si seteás `BOOTSTRAP_PLATFORM_OWNER_EMAIL` |
| 16 | `.env.auth0.local` | Guarda los IDs de las apps + paths a los secret files |
| 17 | `.secrets/auth0-*-secret` | Persiste client secrets con chmod 600 |

### 3.4 Habilitar DB connection para el admin app (manual, una vez)

Auth0 movió `enabled_clients` a una API no mutable via script en tenants
nuevos. **Un click manual:**

1. Sidebar → **`Authentication`** → **`Database`**.
2. Click en **`Username-Password-Authentication`** (default que Auth0 creó).
3. Tab **`Applications`** (último de 5 tabs).
4. Encontrá **`copilotoia-admin-web`** en la lista.
5. Toggle a la derecha → debe pasar a **verde (ON)**.

> Sin esto: el form email+password NO aparece en login y los users no
> pueden registrarse con email/password.

### 3.5 (Opcional) Crear el primer Platform Owner

#### Paso 1 — Crear el user

1. Sidebar → **`User Management`** → **`Users`** → **`+ Create User`**.
2. Modal:
   - **Email:** tu email
   - **Password:** ≥12 chars, mayúscula, número, especial
   - **Connection:** `Username-Password-Authentication`
3. Click **`Create`**.

#### Paso 2 — Verificar el email

4. En el detail del user, sección "Details":
   - **Email Verified: ❌ false** ← arreglar.
5. Opción A (recomendada): `Actions` → **`Send Verification Email`** →
   click en el link.
   Opción B (testing): `Edit` → toggle Email Verified → `Save`.

#### Paso 3 — Asignar rol platform_owner

```bash
export BOOTSTRAP_PLATFORM_OWNER_EMAIL="tu@email.com"
bash scripts/configure-auth0.sh
```

El script:
- Busca el user por email.
- Verifica `email_verified=true` (sino aborta).
- Asigna rol `platform_owner` (idempotente).
- Setea `app_metadata.support_mode=true` (cross-tenant access).

#### Paso 4 — Verificación

1. Auth0 dashboard → `User Management` → `Users` → click tu user.
2. Tab `Roles` → debe aparecer `platform_owner`.
3. Tab `Raw JSON` → `app_metadata.support_mode: true`.

### 3.6 Cargar config en el Core

El script generó `.env.auth0.local` y `.secrets/auth0-*-secret`.
Tu `.env` principal:

```bash
AUTH0_DOMAIN=copilotai.us.auth0.com
AUTH0_AUDIENCE=https://app.copilotoia.com/api
AUTH0_ISSUER=https://copilotai.us.auth0.com/
AUTH0_CLAIMS_NAMESPACE=https://app.copilotoia.com/claims

# Empezá en true (compat). Pasar a false una vez verificado:
AUTH0_TRUST_ADMIN_EMAIL_HEADER=true
```

Restart:
```bash
docker compose restart admin-panel api
```

### 3.7 Verificación end-to-end

```bash
open http://localhost:3000/admin/
# Click "Iniciar sesión" → Auth0 login → MFA → aterriza en /admin/
```

Si sos `platform_owner`:
```bash
open http://localhost:3000/admin/platform/platform-fleet
```

### 3.8 Hardening post-deploy (prod)

```bash
# Verificar que el access_token trae el claim 'email' namespaced:
docker compose logs admin-panel | grep email_from_header_fallback | tail
# Si NO aparece → el Action está populando bien.
# Si aparece → re-correr scripts/configure-auth0.sh.

# Cerrar el último vector de hijack:
# .env:
AUTH0_TRUST_ADMIN_EMAIL_HEADER=false
docker compose restart api
```

### 3.9 Rotación de keys (proceso humano)

Ver [docs/runbooks/auth0-key-rotation.md](docs/runbooks/auth0-key-rotation.md).

---

## 4. Setup completo de Resend

### 4.1 Sign-up

1. **https://resend.com/signup** con email + password (o GitHub).
2. Free tier: **3000 emails/mes** + 100/día.

### 4.2 Crear API Key

1. Sidebar izquierdo → **`API Keys`** → **`+ Create API Key`**.
2. Modal:
   - **Name:** `copilotoia-prod` o `copilotoia-dev`.
   - **Permission:** **"Sending access"** (NO "Full access").
   - **Domain:** dejar en `All domains` por ahora.
3. Click **`Add`** → la key `re_xxxxxxxxxxxxxxxx` se muestra **una sola
   vez**. Copiá YA.

### 4.3 Verificar dominio (sender real, no spam)

1. Sidebar → **`Domains`** → **`+ Add Domain`**.
2. Ej. `app.copilotoia.com` → click `Add`.
3. Resend te muestra **3 DNS records**:
   - **SPF:** TXT en `app.copilotoia.com`, value
     `v=spf1 include:amazonses.com ~all`
   - **DKIM:** CNAME en `resend._domainkey.app.copilotoia.com` →
     `resend._domainkey.amazonses.com`
   - **DMARC:** TXT en `_dmarc.app.copilotoia.com`, value
     `v=DMARC1; p=none;`
4. Agregar en tu DNS provider (Cloudflare/Route53/etc.).
5. Click **`Verify DNS Records`** (5-30 min propagación).
6. Records en VERDE → dominio verificado.

> **Atajo testing:** `onboarding@resend.dev` como sender — Resend solo
> deja mandar a TU email registrado.

### 4.4 Guardar API key en el repo

```bash
cd /ruta/a/copilotoia
mkdir -p .secrets
echo -n 're_xxxxxxxxxxxxxxxx' > .secrets/resend-api-key
chmod 600 .secrets/resend-api-key

# Verificar que está ignored:
git check-ignore .secrets/resend-api-key
# Output: ".secrets/resend-api-key"
```

### 4.5 Configurar el Core para usar Resend

`.env`:

```bash
RESEND_API_KEY_FILE=/run/secrets/resend-api-key  # o path al file local
EMAIL_FROM_ADDRESS=invites@app.copilotoia.com
EMAIL_FROM_NAME=CopilotoIA
APP_PUBLIC_URL=https://app.copilotoia.com
INVITATION_TOKEN_TTL_SECONDS=604800       # 7 días
INVITATION_SEND_RATE_PER_HOUR=20          # anti-spam por inviter
```

Restart:
```bash
docker compose restart api
```

Verificación:
```bash
# Crear invitación → debería llegar el email
docker compose logs api | grep 'email.resend' | tail
# Esperás: "email.resend.sent message_id=msg-xxx"
```

---

## 5. Configurar AI providers

El Core soporta 7 providers IA (4 cloud + 3 locales). Configurar **al
menos uno** si los módulos opt-in lo requieren.

### 5.1 Cloud — agregar key via admin UI

1. Login como `platform_owner`.
2. `/admin/platform/ai-providers`.
3. **`+ Add provider`** → seleccionar provider + modality + pegar key.
4. La key se cifra con `AI_PROVIDER_MASTER_KEY` (Fernet) antes de
   persistir en `app.platform_ai_providers`.

### 5.2 Cloud — agregar key via env var

`.env`:

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# xAI (Grok)
XAI_API_KEY=xai-...

# ElevenLabs
ELEVENLABS_API_KEY=...
```

El registry resuelve estas keys cuando `secret_ref="env:NOMBRE_VAR"`.

### 5.3 Local providers

```bash
# Ollama (LLM local)
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull llama3.1:8b

# faster-whisper-server (STT local)
docker run -d --name whisper -p 9001:8000 \
  fedirz/faster-whisper-server:latest-cpu

# AUTOMATIC1111 SDXL (Image local) — requiere GPU
# Ver https://github.com/AUTOMATIC1111/stable-diffusion-webui
```

`.env`:
```bash
OLLAMA_BASE_URL=http://localhost:11434
LOCAL_SDXL_BASE_URL=http://localhost:7860
LOCAL_WHISPER_BASE_URL=http://localhost:9001
```

### 5.4 Configurar fallback chain

Via admin UI: `/admin/platform/ai-providers` → cada provider tiene
campo `params.fallback` con lista de providers en orden de preferencia.

Ejemplo: si `grok` (primary) falla, intentar `openai` → `anthropic`:
```json
{"fallback": ["openai", "anthropic"]}
```

El dispatcher (`app/ai/dispatcher.py`) honra esto con backoff
exponencial + jitter + `Retry-After` (PERF-022).

---

## 6. Variables de entorno — referencia

`scripts/generate-local-secrets.sh` genera un `.env` con valores
aleatorios para dev. En producción debés proveer manualmente.

### 6.1 Backend (api + admin-panel)

| Variable | Tipo | Default | Descripción |
|----------|------|---------|-------------|
| `DATABASE_URL` | conn-string | — | `postgresql://app_user:pass@host:5432/copilotoia` |
| `DATABASE_ADMIN_URL` | conn-string | — | URL con user admin (DDL + RLS bypass) |
| `DB_POOL_MIN_SIZE` | int | 1 | Min conns en el pool asyncpg |
| `DB_POOL_MAX_SIZE` | int | 10 | Max conns en el pool |
| `DB_POOL_COMMAND_TIMEOUT_SECONDS` | float | 30.0 | Timeout por query |
| `REDIS_URL` | url | — | `redis://host:6379/0` |
| `JWT_SECRET` | random 32b | — | HS256 fallback (solo dev) |
| `JWT_ISSUER` | url | — | `https://<tenant>.auth0.com/` |
| `JWT_AUDIENCE` | str | — | API identifier en Auth0 |
| `SERVICE_TOKEN` | random | — | Token M2M interno entre workers |
| `SERVICE_TOKEN_NEXT` | random | — | Slot de rotación de SERVICE_TOKEN |
| `APP_PUBLIC_URL` | url | — | URL pública del SPA |

### 6.2 Auth0

| Variable | Tipo | Descripción |
|----------|------|-------------|
| `AUTH0_DOMAIN` | str | `<tenant>.<region>.auth0.com` |
| `AUTH0_CLIENT_ID` | str | Client ID de `copilotoia-admin-web` |
| `AUTH0_CLIENT_SECRET_FILE` | path | Path al secret del admin app |
| `AUTH0_ADMIN_CLIENT_ID` | str | Client ID del service M2M |
| `AUTH0_ADMIN_CLIENT_SECRET` | str | Secret del service M2M |
| `AUTH0_AUDIENCE` | str | API identifier (ver § 6.1 JWT_AUDIENCE) |
| `AUTH0_ISSUER` | url | Mismo que `JWT_ISSUER` |
| `AUTH0_CLAIMS_NAMESPACE` | url | Namespace para custom claims |
| `AUTH0_TRUST_ADMIN_EMAIL_HEADER` | bool | `true` compat / `false` post-A-003 |
| `ADMIN_STATE_SECRET` | random 32b | HMAC para OAuth state cookie |
| `ADMIN_SESSION_SECRET` | random 32b | HMAC para session cookie |

### 6.3 Email (Resend)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RESEND_API_KEY_FILE` | — | Path al file con la API key (chmod 600) |
| `EMAIL_FROM_ADDRESS` | — | Sender (dominio verificado en Resend) |
| `EMAIL_FROM_NAME` | `CopilotoIA` | Display name |
| `INVITATION_TOKEN_TTL_SECONDS` | 604800 | TTL del token (7d) |
| `INVITATION_SEND_RATE_PER_HOUR` | 20 | Anti-spam por inviter |

### 6.4 S3 / MinIO

| Variable | Descripción |
|----------|-------------|
| `S3_ENDPOINT_URL` | MinIO en local; AWS endpoint en prod |
| `S3_BUCKET` | Bucket para uploads del admin |
| `S3_ACCESS_KEY_ID` | Key id |
| `S3_SECRET_ACCESS_KEY` | Secret access key |

### 6.5 Backups (perfil `backups`)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BACKUP_S3_BUCKET` | — | Bucket para dumps cifrados |
| `BACKUP_S3_ENDPOINT` | — | Endpoint S3 cloud |
| `BACKUP_ENV` | local | Etiqueta del entorno (`prod`/`staging`) |
| `BACKUP_GPG_RECIPIENT` | — | Email/ID del recipient GPG |
| `BACKUP_GPG_PUBKEY_PATH` | `/app/.secrets/backup_gpg_pubkey.asc` | Path a la public key |
| `BACKUP_SIGNER_FPR` | — | Fingerprint de la signing key |
| `BACKUP_SIGNER_PRIVKEY_PATH` | `/app/.secrets/backup_signer_privkey.asc` | Signing key privada |
| `BACKUP_VERIFY_SKIP_EPHEMERAL` | **1** | **SEC-021-N: default skip; opt-in con `0`** |
| `BACKUP_RETENTION_DAYS` | 30 | Días antes de rotar |

### 6.6 AI providers

| Variable | Descripción |
|----------|-------------|
| `AI_PROVIDER_MASTER_KEY` | Fernet (32b base64) para cifrar API keys en DB |
| `OPENAI_API_KEY` | (opcional) Si querés inyectar via env |
| `ANTHROPIC_API_KEY` | idem |
| `XAI_API_KEY` | idem |
| `ELEVENLABS_API_KEY` | idem |
| `OLLAMA_BASE_URL` | URL del Ollama local |
| `LOCAL_SDXL_BASE_URL` | URL del SDXL local |
| `LOCAL_WHISPER_BASE_URL` | URL del Whisper local |
| `AI_DEFAULT_LLM_PROVIDER` | Fallback si no hay row en `platform_ai_providers` |
| `AI_DEFAULT_IMAGE_PROVIDER` | idem |
| `AI_DEFAULT_VIDEO_PROVIDER` | idem |
| `AI_DEFAULT_TTS_PROVIDER` | idem |
| `AI_DEFAULT_STT_PROVIDER` | idem |

### 6.7 Observabilidad

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OBSERVABILITY_ALLOWED_IPS` | — | CIDRs permitidos para hitear `/metrics` |
| `WORKER_METRICS_PORT` | 9100 | Puerto Prometheus de cada worker |
| `GRAFANA_ADMIN_PASSWORD` | random | Admin password de Grafana |

### 6.8 Rate limiting

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RATE_LIMIT_PER_MIN` | 60 | Default per actor per minute |
| `RATE_LIMIT_WEBHOOK_PER_MIN` | 300 | Webhook endpoints |
| `RATE_LIMIT_BUCKET_MAX_ENTRIES` | 10000 | LRU cap |
| `RATE_LIMIT_BUCKET_TTL_SECONDS` | 3600 | Eviction por idle |

---

## 7. Verificación post-bootstrap

### 7.1 Tablas del core

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "\dt app.*"
```

Debe listar al menos: `tenants`, `users`, `user_tenant_roles`,
`user_preferences`, `auth_sessions`, `audit_log`, `operator_alerts`,
`data_retention_policies`, `backup_runs`, `tenant_legal_documents`,
`tenant_modules`, `tenant_invitations`, `platform_secrets`,
`platform_ai_providers`, `provider_dispatch`, `feature_flags`,
`role`, `capability`, `role_capability`.

### 7.2 Endpoints liveness

```bash
# API liveness
curl -s http://localhost:8000/healthz
# Esperás: {"status": "ok"}

# Admin panel
curl -s http://localhost:3000/admin/healthz
# Esperás: {"status": "ok"}

# Métricas (desde IP allowlisted)
curl -s http://localhost:8000/metrics | grep cpi_db_pool
```

### 7.3 Primer login

1. `open http://localhost:3000/admin/`.
2. Click "Iniciar sesión" → flow Auth0.
3. Primera vez aterriza en `/no-tenant` (no tenés tenant todavía).
4. Si sos `platform_owner` → también ves `/platform`.

### 7.4 Crear el primer tenant

Desde `/no-tenant`:
1. Llenar form: nombre, slug, vertical, país.
2. Submit → `POST /v1/tenant-signup`.
3. Backend te crea como `owner` del tenant nuevo.
4. Redirige a `/t/<slug>/tenant-setup`.

O como `platform_owner` desde Fleet (`/platform/platform-fleet` →
"Crear tenant" → invitar owner por email).

### 7.5 Activar un módulo opt-in

Como `platform_owner`, en Fleet → seleccionar tenant → panel
"Módulos": toggle ON. Cada módulo puede tener pre-requisitos
(modalidades IA configuradas, etc.). Ver README del módulo específico.

---

## 8. Perfiles opt-in: backups y observability

### 8.1 Backups

```bash
docker compose --profile backups up -d backup-worker
```

Configurar en `.env`:
- `BACKUP_S3_BUCKET` (bucket destino).
- `BACKUP_GPG_RECIPIENT` (email del recipient — debe matchear una key
  importada en el container).
- `BACKUP_GPG_PUBKEY_PATH` (path a la pubkey ASCII-armored).
- `BACKUP_VERIFY_SKIP_EPHEMERAL=1` (default seguro post SEC-021-N).

**Para activar verificación efímera** (requiere docker.sock + nodo
dedicado): `BACKUP_VERIFY_SKIP_EPHEMERAL=0`. Ver
[`docs/runbooks/backup-stale.md`](docs/runbooks/backup-stale.md).

### 8.2 Observability

```bash
docker compose --profile observability up -d
```

- Prometheus en `http://localhost:9090`.
- Grafana en `http://localhost:3001` (admin / `GRAFANA_ADMIN_PASSWORD`).

Importar el dashboard:
```bash
# Ver instrucciones detalladas:
cat infra/observability/grafana/dashboards/README.md
```

Alertas activadas: ver
[`infra/observability/alerts/core.yml`](infra/observability/alerts/core.yml).

---

## 9. Checklist de producción

Antes de poner tráfico real:

### Infra

- [ ] Postgres administrado (RDS, Cloud SQL, etc.), NO docker-compose.
- [ ] Backups del Postgres administrado **además de** `backup-worker`
      (defense in depth).
- [ ] Redis administrado con persistence (ElastiCache, etc.).
- [ ] S3 cloud real (no MinIO).
- [ ] Load balancer con TLS terminado + WAF.
- [ ] Edge rate-limit (Cloudflare / AWS Shield).
- [ ] Logs centralizados (CloudWatch / Datadog / Loki).

### Secrets

- [ ] **Todos** los secrets en un vault (AWS Secrets Manager, HashiCorp
      Vault, Kubernetes Secrets — NO en `.env` plain en disco).
- [ ] `AI_PROVIDER_MASTER_KEY` rotada cada 90 días.
- [ ] `AUTH0_ADMIN_CLIENT_SECRET` rotada cada 90 días. Ver
      [auth0-key-rotation.md](docs/runbooks/auth0-key-rotation.md).
- [ ] `.secrets/` directory con chmod 600.
- [ ] Audit trail de quién accede a qué secret.

### Config

- [ ] `AUTH0_TRUST_ADMIN_EMAIL_HEADER=false` (cerrar vector A-003).
- [ ] `APP_PUBLIC_URL=https://...` (HTTPS enforce vía DiD-3).
- [ ] `DB_POOL_MAX_SIZE` tuneado al baseline observado.
- [ ] `OBSERVABILITY_ALLOWED_IPS` restringido al subnet del scraper.
- [ ] Resend dominio verificado + DMARC en `p=quarantine` (ya no `p=none`).

### Tests + CI

- [ ] CI corre `pytest` + `ruff check` + `vitest run` en cada PR.
- [ ] Coverage gate ≥ 86% para frontend y ≥ 90% para backend.
- [ ] Tests de smoke post-deploy automáticos (`scripts/smoke-test.sh`).

### Observabilidad

- [ ] Prometheus scrapeando `/metrics` correctamente.
- [ ] Grafana dashboard `core-health` importado.
- [ ] Alertas Prometheus configuradas + apuntando al Alertmanager.
- [ ] Runbooks accesibles vía link en cada alerta.
- [ ] On-call rotation definida.

### Seguridad

- [ ] Auditoría manual de OAuth flow (verificar nonce, state, PKCE).
- [ ] Penetration test inicial (recomendado para SaaS B2B).
- [ ] Política de retención de PII alineada con regulaciones (Ley 1581
      en Colombia, GDPR si UE).
- [ ] Plan de incident response documentado.

---

## 10. Troubleshooting

### El admin panel no carga (`502 Bad Gateway`)

```bash
docker compose logs admin-panel | tail -50
# Buscar: ImportError, ConnectionError a postgres/redis, ENV var missing.

# Si dice "Database pool is not initialized":
docker compose logs postgres | tail -20
# Postgres debe estar healthy. Si no, restart:
docker compose restart postgres
```

### Login falla con `state_invalid`

- Cookie de state expiró (default TTL 10 min).
- Click en el mismo "Login" 2 veces → el segundo callback ya invalidó
  el state.
- Solución: click "Iniciar sesión" otra vez.

### `401 unauthorized` desde el SPA al hitear `/admin/api/*`

- Session expiró (TTL = access_token.exp).
- `kubectl logs admin-panel | grep session_expired | tail`.
- Solución: re-login.

### `cpi_db_pool_idle == 0`

Ver [docs/runbooks/db-pool-exhausted.md](docs/runbooks/db-pool-exhausted.md).

### `ai_provider_health == 0`

Ver [docs/runbooks/ai-provider-down.md](docs/runbooks/ai-provider-down.md).

### Email no llega tras crear invitación

```bash
# 1. Verificar que Resend está configurado:
docker compose exec api env | grep RESEND
# Debe haber RESEND_API_KEY_FILE seteado.

# 2. Logs del send:
docker compose logs api | grep email.resend | tail

# 3. Si dice "noop" → estás en provider NO-OP (Resend no configurado).
# 4. Si dice "bounced" → revisar Resend dashboard → Emails → status.
# 5. Si dice "queued" pero no llega → verificar SPF/DKIM/DMARC del dominio.
```

### Bootstrap falla en `00-init-roles.sh`

- Postgres acaba de levantar y no terminó startup. Esperá 5s y
  re-correr `./scripts/bootstrap.sh --yes` (sin `--reset`).

### `configure-auth0.sh` falla con `HTTP 403`

- Te falta un scope en el M2M bootstrap. Ver § 3.2 paso 6 y verificar
  que los 34 scopes están chequeados.

### Tests fallan con `ModuleNotFoundError: phonenumbers`

```bash
source .venv/bin/activate
pip install -e .
pytest
```

---

## Anexos

- [README.md](README.md) — visión rápida + quick start
- [ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura completa
- [docs/runbooks/](docs/runbooks/) — guías operativas
- `scripts/` — todos los scripts de bootstrap + tooling
- `infra/observability/` — Prometheus + Grafana + alertas

---

**Última revisión:** 2026-05-27 — post audit#4 + TASK-OBSERV + TASK-PROD + TASK-DOCS.
