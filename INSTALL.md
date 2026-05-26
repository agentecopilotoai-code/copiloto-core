# Guía de instalación — Copiloto Core

Esta guía explica los pasos para instalar el core desde cero, qué
variables de entorno existen y cómo validar que la base de datos quedó
creada con sus tablas.

## 0. Instalación desde cero en 5 comandos

Para **desarrollo local**:

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

## 1. Requisitos

- Docker Desktop 4.x o Docker Engine 24+.
- `docker compose` v2.
- Bash + `openssl` + `curl` (vienen por defecto en macOS / Linux).
- Auth0 tenant configurado (ver § 4) para tener login funcional.

## 2. Variables de entorno

`scripts/generate-local-secrets.sh` genera un `.env` con valores aleatorios
para desarrollo local. En producción debes proveer estos valores manualmente:

| Variable                    | Descripción                                              |
| --------------------------- | -------------------------------------------------------- |
| `DATABASE_URL`              | postgresql://app_user:pass@host:5432/copilotoia          |
| `DATABASE_ADMIN_URL`        | URL con usuario admin (DDL + ROLES + RLS bypass)         |
| `JWT_SECRET`                | secreto HS256 para firmar/verificar tokens del BFF       |
| `JWT_ISSUER`                | `https://<tu-tenant>.auth0.com/`                         |
| `JWT_AUDIENCE`              | audience del API en Auth0                                |
| `SERVICE_TOKEN`             | token compartido para llamadas M2M al API                |
| `SERVICE_TOKEN_NEXT`        | (opcional) slot de rotación de SERVICE_TOKEN             |
| `S3_ENDPOINT_URL`           | endpoint S3 (MinIO en local; AWS en prod)                |
| `S3_BUCKET`                 | bucket para uploads del admin                            |
| `S3_ACCESS_KEY_ID`          | key id (MinIO o AWS)                                     |
| `S3_SECRET_ACCESS_KEY`      | secret access key                                        |
| `AI_PROVIDER_MASTER_KEY`    | Fernet key (32 bytes base64) para cifrar API keys en DB  |
| `OBSERVABILITY_ALLOWED_IPS` | CIDRs permitidos para hitear `/metrics`                  |

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

## 4. Auth0

El core asume Auth0 como Identity Provider. Necesitas:

1. **Auth0 tenant** (gratuito alcanza para dev).
2. **Application** Regular Web Application:
   - Allowed Callback URLs: `http://localhost:3000/admin/oauth/callback`
   - Allowed Logout URLs: `http://localhost:3000/admin/`
3. **API** con audience `copilotoia-core-v1` (o el valor que pongas en
   `JWT_AUDIENCE`).
4. **Rule / Action** que inyecte el claim de roles al access token (ver
   `app/core/security.py` para el shape esperado).

Setear en `.env.auth0.local`:

```
AUTH0_DOMAIN=tu-tenant.auth0.com
AUTH0_CLIENT_ID=...
AUTH0_CLIENT_SECRET=...
AUTH0_AUDIENCE=copilotoia-core-v1
```

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
