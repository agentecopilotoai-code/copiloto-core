# Guía de instalación - Copiloto IA Core

Esta guía explica **todos los pasos para instalar desde cero** el core Docker de Copiloto IA, qué comandos debes ejecutar, qué secretos/keys existen, qué significa cada variable y cómo validar que la base de datos quedó creada con sus tablas.

## 0. Instalación desde cero en 5 comandos

Usa esta ruta cuando estás en un entorno de **desarrollo local** y no necesitas conservar una base anterior:

```bash
git clone <URL_DEL_REPOSITORIO> CopilotoIA
cd CopilotoIA
./scripts/generate-local-secrets.sh
./scripts/bootstrap.sh --reset --yes
./scripts/smoke-test.sh
```

Si ya tienes el repo clonado:

```bash
cd /ruta/a/CopilotoIA
git pull
./scripts/bootstrap.sh --reset --yes
./scripts/smoke-test.sh
```

> `--reset --yes` borra los volúmenes locales de Docker Compose, incluida la base PostgreSQL local. Úsalo solo en desarrollo.

## 1. Requisitos por plataforma

### macOS

1. Instala Docker Desktop: <https://www.docker.com/products/docker-desktop/>.
2. Instala Homebrew si no lo tienes: <https://brew.sh/>.
3. Instala utilidades:

```bash
brew install git curl openssl python@3.12
```

4. Verifica:

```bash
docker compose version
git --version
python3 --version
openssl version
```

### Windows 11 / Windows 10 con WSL2

1. Instala Docker Desktop.
2. Activa el backend WSL2 en Docker Desktop.
3. Instala Ubuntu desde Microsoft Store.
4. Abre Ubuntu/WSL e instala utilidades:

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv ca-certificates
```

5. Verifica dentro de WSL:

```bash
docker compose version
git --version
python3 --version
openssl version
```

> Recomendado: clona el repo dentro de WSL, por ejemplo `~/projects/CopilotoIA`, no en `C:\`, para evitar problemas de permisos/performance.

### Linux Ubuntu/Debian

1. Instala utilidades base:

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv ca-certificates
```

2. Instala Docker Engine y Docker Compose v2 siguiendo la guía oficial de Docker para tu distribución.
3. Si aplica, agrega tu usuario al grupo Docker:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

4. Verifica:

```bash
docker compose version
git --version
python3 --version
openssl version
```

## 2. Python soportado

El proyecto soporta **Python 3**. Los contenedores usan `python:3.12-slim` y los comandos internos usan `python3`.

Para correr el stack con Docker **no necesitas instalar dependencias Python localmente**; Docker construye la imagen. Python3 local solo es necesario para herramientas de desarrollo fuera de Docker, por ejemplo `python3 -m compileall app`.

## 3. Archivos importantes

| Archivo | Se versiona | Propósito |
|---|---:|---|
| `.env.example` | Sí | Plantilla de variables sin secretos reales. |
| `.env` | No | Variables reales de desarrollo local usadas por Docker Compose. |
| `.secrets/*` | No | Copia local de secretos sensibles con permisos `600`. |
| `docker-compose.yml` | Sí | Define API, workers, PostgreSQL, Redis, MinIO y OpenTelemetry. |
| `infra/postgres/*.sql` | Sí | Crea extensiones, schema, tablas, RLS, grants y datos demo. |
| `scripts/bootstrap.sh` | Sí | Script único para levantar y validar todo. |
| `scripts/smoke-test.sh` | Sí | Prueba rápida de API health y OpenAPI. |

## 4. Variables, keys y secrets: qué significa cada una

### Variables generales

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `APP_ENV` | `local` | No | Entorno de ejecución: `local`, `staging`, `production`. |
| `APP_NAME` | `CopilotoIA Core` | No | Nombre mostrado por FastAPI/OpenAPI. |
| `API_HOST` | `0.0.0.0` | No | Host interno para bind de la API. |
| `API_PORT` | `8000` | No | Puerto interno de la API. |

### Base de datos PostgreSQL

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `POSTGRES_DB` | `copilotoia` | No | Nombre de la base creada por el contenedor PostgreSQL. |
| `POSTGRES_USER` | `copiloto_admin` | No | Usuario administrador usado solo para bootstrap local. |
| `POSTGRES_PASSWORD` | generado | Sí | Password del usuario administrador. |
| `APP_DB_USER` | `copiloto_app` | No | Usuario aplicativo con permisos sobre schema `app`. |
| `APP_DB_PASSWORD` | generado | Sí | Password del usuario aplicativo. |
| `DATABASE_URL` | `postgresql://copiloto_app:<pass>@postgres:5432/copilotoia` | Sí | URL usada por API/workers para conectarse a PostgreSQL. |
| `DATABASE_ADMIN_URL` | `postgresql://copiloto_admin:<pass>@postgres:5432/copilotoia` | Sí | URL admin local para tareas de mantenimiento. |

> Importante: PostgreSQL solo aplica `POSTGRES_PASSWORD` y `APP_DB_PASSWORD` cuando se inicializa el volumen por primera vez. Si regeneras `.env` después, usa `./scripts/bootstrap.sh --reset --yes` para recrear la DB local.

### Redis

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `REDIS_URL` | `redis://redis:6379/0` | No en local | URL interna para cache, locks y sesiones efímeras. En producción debería usar auth/TLS si el proveedor lo soporta. |

### JWT / autenticación interna

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `JWT_ISSUER` | `copilotoia-local` | No | Emisor esperado de tokens JWT. |
| `JWT_AUDIENCE` | `copilotoia-panel` | No | Audiencia esperada de tokens JWT. |
| `JWT_SECRET` | generado | Sí en local | Secreto HMAC para validar JWT HS256 solo cuando `AUTH0_DOMAIN` no está configurado. Mantén un valor robusto para desarrollo/smoke local. |
| `AUTH0_DOMAIN` | `tu-tenant.us.auth0.com` | No | Dominio del tenant Auth0. Lo genera `scripts/configure-auth0.sh` en `.env.auth0.local`; si está definido, la API valida tokens OIDC/Auth0 RS256 contra JWKS. |
| `AUTH0_ISSUER` | `https://tu-tenant.us.auth0.com/` | No | Issuer esperado. También lo genera `scripts/configure-auth0.sh` en `.env.auth0.local`; la API lo usa si está presente y si no lo deriva de `AUTH0_DOMAIN`. |
| `AUTH0_AUDIENCE` | `https://api.tu-dominio.com` | No | Audience esperado en los access tokens RS256 de Auth0. Debe coincidir con el API identifier creado por `scripts/configure-auth0.sh` y se carga desde `.env.auth0.local`. |
| `AUTH0_CLAIMS_NAMESPACE` | `https://tu-dominio.com/claims` | No | Namespace desde el que la API lee `tenant_id`, `roles` y `support_mode`; debe coincidir con la Action post-login generada. No requiere slash final. |
| `AUTH0_JWKS_CACHE_TTL_SECONDS` | `300` | No | TTL local de cache para las claves públicas JWKS de Auth0. Es opcional; si no aparece en `.env.auth0.local`, se usa el default de la app. |
| `SERVICE_TOKEN` | generado | Sí | Token interno para automatizaciones/servicios. Sigue funcionando aunque Auth0 esté habilitado y permite soporte interno/operaciones tenant-aware. Protégelo como secreto crítico. |


### Auth0 para panel administrativo

El repo incluye `scripts/configure-auth0.sh` para preparar Auth0 de forma idempotente para CopilotoIA. El script crea/actualiza:

1. API `copilotoia-core-api` con audience `AUTH0_API_IDENTIFIER` y RBAC habilitado.
2. App regular web `copilotoia-admin-web` para el futuro panel administrativo.
3. App M2M `copilotoia-service-m2m` y client grant contra el API.
4. Roles `owner`, `admin`, `manager`, `agent`, `viewer` y `support` con permisos por alcance.
5. Action post-login `copilotoia-post-login-claims` para emitir claims namespaced de roles, permisos, `tenant_id`, `tenant_slug` y `support_mode`.

Ejemplo:

```bash
export AUTH0_DOMAIN=tu-tenant.us.auth0.com
export MGMT_CLIENT_ID=xxxx
export MGMT_CLIENT_SECRET=xxxx
export COPILOTOIA_DOMAIN=copilotoia.tu-dominio.com
./scripts/configure-auth0.sh
```

También puedes usar `MGMT_ACCESS_TOKEN` si ya tienes un token de Management API válido. La aplicación M2M de Management API debe tener permisos suficientes para gestionar resource servers, clients, client grants, roles y actions.

Al terminar, el script guarda automáticamente la configuración necesaria en archivos locales ignorados por git:

| Archivo | Contenido | Se versiona |
|---|---|---:|
| `.env.auth0.local` | `AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, namespace de claims, client IDs, URLs permitidas y rutas de secretos | No |
| `.secrets/auth0-admin-client-secret` | client secret de la app web admin si Auth0 lo entrega | No |
| `.secrets/auth0-service-client-secret` | client secret de la app M2M interna | No |

Puedes cambiar la salida con `AUTH0_ENV_FILE`, `AUTH0_SECRETS_DIR` o desactivarla con `SAVE_AUTH0_CONFIG=false`. Estos archivos son locales y sensibles; no los subas al repositorio ni los compartas por chat.

> Nota: no dupliques estas variables en `.env`. La app carga `.env` y `.env.auth0.local` en ese orden, y `docker-compose.yml` inyecta ambos archivos en los servicios Python. Cuando `AUTH0_DOMAIN` y `AUTH0_AUDIENCE` existen en `.env.auth0.local`, los bearer tokens de usuario se validan como access tokens Auth0 RS256 usando JWKS. Si `AUTH0_DOMAIN` queda vacío, la API conserva la validación HS256 local para desarrollo.

### Admin Panel local

El Admin Panel MVP vive en `admin-panel/` y se compila con React JS + Vite. El backend OIDC/Auth0 vive en `app/admin` para mantener el Authorization Code Flow y leer el secreto desde `.secrets/auth0-admin-client-secret` sin exponerlo en el navegador. Consume la configuración generada por `scripts/configure-auth0.sh` desde `.env.auth0.local`; no requiere variables duplicadas en `.env`.

Para instalar dependencias, compilar React, construir la imagen Docker dedicada y levantar el contenedor:

```bash
./scripts/bootstrap-admin-panel.sh
```

El script termina mostrando `docker compose ps admin-panel`; ahí debe aparecer el servicio. Si prefieres hacerlo manualmente:

```bash
docker compose up -d --build admin-panel
```

Luego abre `http://localhost:3000/admin/` e inicia sesión con Auth0. Más detalles y comandos de desarrollo están en `docs/ADMIN_PANEL.md`.

### WhatsApp / Meta Graph API

| Variable | Ejemplo local | Secreto | Significado | Dónde obtenerlo |
|---|---|---:|---|---|
| `META_GRAPH_VERSION` | `v23.0` | No | Versión de Graph API usada por el adaptador. | Meta Developers docs / versión elegida. |
| `META_ACCESS_TOKEN` | `local-mock-token-replace-in-production` | Sí | Token para enviar mensajes por WhatsApp Cloud API. En local puede quedar mock. | Meta for Developers > WhatsApp > API Setup, o System User token en Business Settings. |
| `WHATSAPP_VERIFY_TOKEN` | generado/definido por ti | Sí | Token que Meta usa para verificar tu webhook. Debe coincidir en Meta y en `.env`. | Lo defines tú. |
| `WHATSAPP_APP_SECRET` | generado/local o App Secret real | Sí | Secreto de la app Meta usado para validar `X-Hub-Signature-256`. | Meta for Developers > App Settings > Basic > App Secret. |

Además necesitarás estos IDs para registrar el canal por tenant:

| Dato | Significado | Dónde obtenerlo |
|---|---|---|
| `business_id` | ID del Business Manager. | Meta Business Settings > Business Info. |
| `waba_id` | ID de WhatsApp Business Account. | WhatsApp Manager / API Setup. |
| `phone_number_id` | ID del número que envía mensajes. | Meta for Developers > WhatsApp > API Setup. |

### MinIO / S3

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `S3_ENDPOINT_URL` | `http://minio:9000` | No | Endpoint S3-compatible. En local apunta a MinIO. |
| `S3_BUCKET` | `copilotoia-local` | No | Bucket para media/documentos/exportaciones. |
| `S3_ACCESS_KEY_ID` | `copilotoia-minio` | Sí | Usuario/access key local de MinIO. |
| `S3_SECRET_ACCESS_KEY` | generado | Sí | Password/secret key local de MinIO. |

### Observabilidad

| Variable | Ejemplo local | Secreto | Significado |
|---|---|---:|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | No | Endpoint OTLP HTTP del collector. |

## 5. Generar secretos locales

Ejecuta:

```bash
./scripts/generate-local-secrets.sh
```

Qué hace:

1. Crea `.env` si no existe.
2. Genera passwords/tokens con OpenSSL.
3. Crea `.secrets/*` con permisos `600`.
4. Si detecta un `.env` incompleto con placeholders `change-me-*`, lo respalda como `.env.incomplete.<timestamp>.bak` y genera uno nuevo.

Verifica permisos:

```bash
ls -l .env .secrets
```

## 6. Instalar/levantar desde cero con un único script

Para levantar todo y validar instalación:

```bash
./scripts/bootstrap.sh
```

Para borrar todo lo local y reinstalar desde cero:

```bash
./scripts/bootstrap.sh --reset --yes
```

Qué valida `bootstrap.sh`:

1. Que exista `.env`; si no existe, lo genera.
2. Que Docker y Docker Compose v2 estén disponibles.
3. Si usas `--reset --yes`, borra volúmenes locales con `docker compose down -v --remove-orphans`.
4. Construye y levanta PostgreSQL, Redis, MinIO, OpenTelemetry, API, scheduler y event worker.
5. Valida que `DATABASE_URL` conecte como `copiloto_app`.
6. Valida extensiones PostgreSQL: `pgcrypto`, `citext`, `vector`, `btree_gist`.
7. Valida tablas principales del schema `app`.
8. Valida que existan al menos 3 tenants demo.
9. Espera que `http://localhost:8000/v1/health` responda.
10. Ejecuta `scripts/smoke-test.sh`.
11. Valida métricas en `http://localhost:8889/metrics`.

Al finalizar deberías ver un mensaje similar:

```text
Bootstrap completo: DB, tablas, extensiones, tenants demo, API y métricas OK.
```

## 7. URLs locales

| Servicio | URL |
|---|---|
| API health | `http://localhost:8000/v1/health` |
| Swagger/OpenAPI | `http://localhost:8000/docs` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |
| MinIO consola | `http://localhost:9001` |
| MinIO API | `http://localhost:9000` |
| OpenTelemetry OTLP HTTP | `http://localhost:4318` |
| OpenTelemetry métricas Prometheus | `http://localhost:8889/metrics` |

> `http://localhost:8889/` devuelve `404 page not found` porque el exporter Prometheus publica métricas en `/metrics`, no en la raíz.

## 8. Verificación manual

```bash
docker compose ps
curl -fsS http://localhost:8000/v1/health
./scripts/smoke-test.sh
curl -fsS http://localhost:8889/metrics | head
```

Ver logs:

```bash
docker compose logs -f api event-worker scheduler otel-collector
```

## 9. Base de datos: cómo saber si se instaló bien

`./scripts/bootstrap.sh` ya valida automáticamente que la DB quedó instalada. Si quieres revisar manualmente:

Entrar como admin local:

```bash
docker compose exec postgres psql -U copiloto_admin -d copilotoia
```

Listar tablas:

```sql
\dt app.*
```

Ver extensiones:

```sql
select extname from pg_extension where extname in ('pgcrypto','citext','vector','btree_gist');
```

Contar tenants demo:

```sql
select slug, vertical_code, status from app.tenants order by slug;
```

Tenants esperados:

| Vertical | Tenant ID | Slug |
|---|---|---|
| Taller/servicio técnico | `11111111-1111-1111-1111-111111111111` | `demo-taller` |
| Barbería/peluquería | `22222222-2222-2222-2222-222222222222` | `demo-barberia` |
| Mascotas no clínico | `33333333-3333-3333-3333-333333333333` | `demo-mascotas` |

Probar endpoint tenant-aware con service token local:

```bash
curl -fsS \
  -H "Authorization: Bearer $(grep '^SERVICE_TOKEN=' .env | cut -d= -f2-)" \
  -H 'X-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8000/v1/conversations
```

## 10. Configurar WhatsApp real en desarrollo

Para pruebas locales sin WhatsApp real, no cambies nada: el adaptador opera en modo mock si `META_ACCESS_TOKEN` no es real.

Para WhatsApp real:

1. Crea/abre una app en <https://developers.facebook.com/>.
2. Agrega el producto **WhatsApp**.
3. Copia `Phone number ID` y `WhatsApp Business Account ID`.
4. Copia un token temporal para pruebas o crea un System User token más estable.
5. Copia el `App Secret` en App Settings > Basic.
6. Define tu propio `WHATSAPP_VERIFY_TOKEN`.
7. Para webhooks locales, crea un túnel HTTPS hacia `http://localhost:8000`, por ejemplo ngrok o Cloudflare Tunnel.
8. En Meta, configura el webhook público hacia:

```text
https://<TU_DOMINIO_PUBLICO>/v1/webhooks/whatsapp
```

Edita `.env`:

```env
META_ACCESS_TOKEN=<TOKEN_REAL_DE_META>
WHATSAPP_VERIFY_TOKEN=<TOKEN_QUE_DEFINISTE>
WHATSAPP_APP_SECRET=<APP_SECRET_DE_META>
META_GRAPH_VERSION=v23.0
```

Reinicia servicios:

```bash
docker compose restart api event-worker scheduler
```

Registra el canal del tenant demo:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $(grep '^SERVICE_TOKEN=' .env | cut -d= -f2-)" \
  http://localhost:8000/v1/tenants/11111111-1111-1111-1111-111111111111/channels/whatsapp \
  -d '{
    "business_id":"<BUSINESS_ID>",
    "waba_id":"<WABA_ID>",
    "phone_number_id":"<PHONE_NUMBER_ID>",
    "token_ref":"secrets/meta_access_token",
    "app_secret_ref":"secrets/whatsapp_app_secret"
  }'
```

## 11. Producción: pasos y equivalencias

En producción no uses MinIO local ni `.env` en disco como fuente final de secretos. Usa servicios gestionados.

| Capa | Desarrollo local | Producción recomendada |
|---|---|---|
| Runtime | Docker Compose | ECS/Fargate, Kubernetes, Cloud Run, App Service o similar |
| PostgreSQL | `pgvector/pgvector:pg16` | RDS PostgreSQL / Cloud SQL / Azure PostgreSQL con backups/PITR |
| Redis | `redis:7.4-alpine` | Redis gestionado con TLS/auth |
| Objetos | MinIO | S3 / GCS / Azure Blob con cifrado |
| Secretos | `.env` / `.secrets` | Secrets Manager / Secret Manager / Key Vault |
| TLS | Local sin TLS | Load balancer/API gateway con HTTPS |
| Observabilidad | OTel Collector local | OTel Collector + CloudWatch/Datadog/Grafana/etc. |

Checklist producción:

1. Crear base PostgreSQL administrada.
2. Ejecutar `infra/postgres/01-schema.sql` como migración inicial.
3. Crear usuario aplicativo con permisos equivalentes a `copiloto_app`.
4. Crear Redis gestionado.
5. Crear bucket de objetos y política por prefijo de tenant.
6. Crear secretos en el gestor cloud.
7. Construir y publicar la imagen Docker.
8. Desplegar `api`, `event-worker` y `scheduler` como servicios separados.
9. Exponer solo `api` por HTTPS.
10. Configurar webhook público de Meta hacia `/v1/webhooks/whatsapp`.
11. Activar backups/PITR de PostgreSQL.
12. Configurar logs, métricas y alertas.

Variables mínimas de producción:

```env
APP_ENV=production
DATABASE_URL=postgresql://<APP_USER>:<PASSWORD>@<HOST>:5432/<DB>
REDIS_URL=redis://<HOST>:6379/0
# Auth0/OIDC: usar .env.auth0.local generado por scripts/configure-auth0.sh
# AUTH0_DOMAIN=<TENANT>.us.auth0.com
# AUTH0_ISSUER=https://<TENANT>.us.auth0.com/
# AUTH0_AUDIENCE=<API_IDENTIFIER_AUTH0>
# AUTH0_CLAIMS_NAMESPACE=https://<DOMINIO>/claims
# AUTH0_JWKS_CACHE_TTL_SECONDS=300
JWT_ISSUER=copilotoia-local
JWT_AUDIENCE=copilotoia-panel
JWT_SECRET=<SECRETO_LOCAL_FALLBACK>
SERVICE_TOKEN=<TOKEN_INTERNO_LARGO>
WHATSAPP_VERIFY_TOKEN=<TOKEN_WEBHOOK>
WHATSAPP_APP_SECRET=<APP_SECRET_META>
META_GRAPH_VERSION=v23.0
META_ACCESS_TOKEN=<TOKEN_META>
S3_ENDPOINT_URL=<ENDPOINT_S3_SI_APLICA>
S3_BUCKET=<BUCKET_PROD>
S3_ACCESS_KEY_ID=<ACCESS_KEY_O_IAM_ROLE>
S3_SECRET_ACCESS_KEY=<SECRET_KEY_O_IAM_ROLE>
OTEL_EXPORTER_OTLP_ENDPOINT=<OTEL_ENDPOINT>
```

## 12. Comandos útiles

Levantar/validar todo:

```bash
./scripts/bootstrap.sh
```

Reinstalar desde cero en desarrollo:

```bash
./scripts/bootstrap.sh --reset --yes
```

Alias compatible:

```bash
./scripts/reset-local-dev.sh --yes
```

Ver estado:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f api event-worker scheduler otel-collector
```

Reiniciar servicios de aplicación:

```bash
docker compose restart api event-worker scheduler
```

Apagar sin borrar datos:

```bash
docker compose down
```

Apagar y borrar volúmenes:

```bash
docker compose down -v
```

## 13. Troubleshooting

### `InvalidPasswordError: password authentication failed for user "copiloto_app"`

Tu volumen PostgreSQL fue creado con una contraseña anterior, pero `.env` tiene otra. En desarrollo:

```bash
./scripts/bootstrap.sh --reset --yes
```

### `curl: (56) Recv failure: Connection reset by peer`

La API arrancó y se cayó durante startup. Revisa logs:

```bash
docker compose logs --tail=200 api event-worker scheduler
```

Si ves `InvalidPasswordError`, aplica el reset local anterior.

### `python: command not found`

El proyecto usa `python3`. Actualiza repo y reconstruye:

```bash
git pull
docker compose up -d --build
```

### `docker: command not found`

Instala Docker Desktop/Engine y verifica:

```bash
docker compose version
```

### `otel-collector-1` aparece detenido

```bash
docker compose logs --tail=200 otel-collector
```

### `event-worker-1` o `scheduler-1` aparecen detenidos

```bash
docker compose logs --tail=200 event-worker scheduler
docker compose up -d --build event-worker scheduler
```

### Cambié SQL pero no se refleja

Los scripts de inicialización corren solo cuando el volumen de PostgreSQL se crea por primera vez. En desarrollo:

```bash
./scripts/bootstrap.sh --reset --yes
```

### Puerto ocupado

Si `8000`, `5432`, `6379`, `9000` o `9001` están ocupados, cambia los puertos en `docker-compose.yml` o detén el servicio que los usa.
