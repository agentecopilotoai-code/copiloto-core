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

El Admin Panel MVP vive en `admin-panel/` y se compila con React JS + Vite. El backend OIDC/Auth0 vive en `app/admin` para mantener el Authorization Code Flow y leer el secreto desde `.secrets/auth0-admin-client-secret` sin exponerlo en el navegador. Consume la configuración generada por `scripts/configure-auth0.sh` desde `.env.auth0.local`; no requiere variables duplicadas en `.env` ni las variables obligatorias del core para arrancar la pantalla `/admin/`.

Para instalar dependencias, compilar React, construir la imagen Docker dedicada y levantar el contenedor:

```bash
./scripts/bootstrap-admin-panel.sh
```

El script termina mostrando `docker compose ps admin-panel`; ahí debe aparecer el servicio. Si prefieres hacerlo manualmente:

```bash
docker compose up -d --build admin-panel
```

Luego abre `http://localhost:3000/admin/` e inicia sesión con Auth0. El puerto `3000` es solo para el Admin Panel; los endpoints core `/v1/*` viven en la API del puerto `8000`. En Docker, el Admin Panel se comunica con esa API mediante `ADMIN_CORE_API_BASE_URL=http://api:8000` y expone al navegador el proxy `/admin/api/core/v1/*`, por lo que el frontend no debe intentar llamar `/v1/*` en `http://localhost:3000`. Si el usuario autenticado no tiene `tenant_id`, el panel muestra un botón central para crear su primer tenant vía `POST /tenant-signup`; ese usuario queda asociado como `owner` del tenant creado. Si tu aplicación Auth0 fue configurada antes de esta versión, vuelve a ejecutar `scripts/configure-auth0.sh` para agregar `http://localhost:3000/admin/` a Allowed Logout URLs. Más detalles y comandos de desarrollo están en `docs/ADMIN_PANEL.md`.

### WhatsApp / Meta Graph API

| Variable | Ejemplo local | Secreto | Significado | Dónde obtenerlo |
|---|---|---:|---|---|
| `META_GRAPH_VERSION` | `v23.0` | No | Versión de Graph API usada por el adaptador. | Meta Developers docs / versión elegida. |
| Meta access token por tenant | Guardado por el Admin Panel en `.secrets/tenants/<TENANT_ID>/meta_access_token` | Sí | Token para enviar mensajes por WhatsApp Cloud API desde el canal de ese tenant. | Meta for Developers > WhatsApp > API Setup, o System User token en Business Settings. |
| Verify token por tenant | Guardado por el Admin Panel en `.secrets/tenants/<TENANT_ID>/whatsapp_verify_token` | Sí | Token que Meta usa para verificar el webhook. El `GET /v1/webhooks/whatsapp` lo lee únicamente desde ese secreto por tenant. | Admin Panel > WhatsApp del tenant. |
| App Secret por tenant | Guardado por el Admin Panel en `.secrets/tenants/<TENANT_ID>/whatsapp_app_secret` | Sí | Secreto de la app Meta usado para validar `X-Hub-Signature-256` de ese número/canal. El archivo final debe contener solo el App Secret; si pegas `APP_ID|APP_SECRET` en el panel, CopilotoIA guarda solo `APP_SECRET`. No pegues App ID ni access token como secreto final. | Meta for Developers > App Settings > Basic > App Secret. |

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

## 10. Configurar WhatsApp real para que funcione de punta a punta

Para pruebas locales sin WhatsApp real, deja el canal del tenant en modo `mock`. Para recibir mensajes reales y enviar respuestas por Cloud API, debes configurar **dos portales de Meta** y luego registrar el canal del tenant en CopilotoIA:

- **Meta for Developers:** <https://developers.facebook.com/apps/>. Aquí creas/abres la app, agregas el producto WhatsApp, copias `Phone Number ID`, `WhatsApp Business Account ID`, configuras webhooks y obtienes el `App Secret`.
- **Meta Business Settings / Business Manager:** <https://business.facebook.com/settings/>. Aquí verificas el negocio, encuentras el `Business ID`, administras el WABA, creas un System User y generas el token estable para producción.

Documentación oficial recomendada de Meta:

- Cloud API: <https://developers.facebook.com/docs/whatsapp/cloud-api>
- Get Started / API Setup: <https://developers.facebook.com/docs/whatsapp/cloud-api/get-started>
- Webhooks: <https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks>
- Access Tokens: <https://developers.facebook.com/docs/whatsapp/cloud-api/get-started#access-tokens>

### 10.1 Prerrequisitos antes de tocar CopilotoIA

1. Tener una cuenta personal de Meta con acceso administrativo al negocio.
2. Tener o crear un **Business Portfolio / Business Manager** en <https://business.facebook.com/settings/>.
3. Completar **Business Info** y, para producción, **Business Verification**. En modo prueba puedes usar el número de prueba que Meta crea en API Setup, pero para operar con clientes reales necesitas negocio verificado, número real registrado y cumplimiento de políticas de WhatsApp Business.
4. Tener CopilotoIA accesible por HTTPS público. Meta no puede verificar `localhost`; para desarrollo usa un túnel como ngrok o Cloudflare Tunnel apuntando a `http://localhost:8000`.

Ejemplo con ngrok:

```bash
ngrok http 8000
```

Anota la URL HTTPS pública que te entregue, por ejemplo `https://abc123.ngrok-free.app`.

### 10.2 Crear o abrir la app en Meta for Developers

1. Entra a <https://developers.facebook.com/apps/>.
2. Crea una app nueva de tipo **Business** o abre la app existente del negocio.
3. En el menú de la app, selecciona **Add product** y agrega **WhatsApp**.
4. En **WhatsApp > API Setup**:
   - Selecciona o crea el Business Portfolio correcto.
   - Copia el **Phone Number ID** del número de prueba o del número real.
   - Copia el **WhatsApp Business Account ID**; ese valor será `waba_id` en CopilotoIA.
   - Si estás en pruebas, agrega tu número personal como destinatario permitido para poder recibir mensajes del número de prueba.
5. En **App Settings > Basic**, copia el **App ID** si necesitas identificar la app y copia el **App Secret**. Pega el App Secret en el campo secreto del tenant del Admin Panel; CopilotoIA lo guardará en `.secrets/tenants/<TENANT_ID>/whatsapp_app_secret`.

### 10.3 Obtener Business ID, WABA ID y Phone Number ID

Usa esta tabla para no confundir los identificadores:

| Dato en CopilotoIA | Portal Meta | Ruta típica | Qué copiar |
|---|---|---|---|
| `business_id` | Meta Business Settings | <https://business.facebook.com/settings/> > **Business Info** | **Business Manager ID** / **Business ID** del negocio dueño del WABA. |
| `waba_id` | Meta for Developers o WhatsApp Manager | App > **WhatsApp > API Setup** o <https://business.facebook.com/wa/manage/home/> | **WhatsApp Business Account ID**. |
| `phone_number_id` | Meta for Developers | App > **WhatsApp > API Setup** | **Phone Number ID**, no el número en formato `+57...`. |
| App Secret del tenant | Meta for Developers | App > **App Settings > Basic** | **App Secret** de la app; pégalo en el Admin Panel para que CopilotoIA lo guarde en `.secrets/tenants/<TENANT_ID>/whatsapp_app_secret`. |
| Meta access token del tenant | Meta for Developers / Business Settings | API Setup para token temporal, o System Users para token estable | Token con permisos de WhatsApp Business Platform; pégalo en el Admin Panel para que CopilotoIA lo guarde en `.secrets/tenants/<TENANT_ID>/meta_access_token`. |
| Verify token | Admin Panel > WhatsApp del tenant | Campo **Verify token del webhook** | Define un token de verificación, pégalo en el panel para guardarlo en `.secrets/tenants/<TENANT_ID>/whatsapp_verify_token` y usa exactamente ese mismo valor en Meta Webhooks. |

### 10.4 Token temporal vs token estable

Para una prueba rápida puedes usar el token temporal que aparece en **Meta for Developers > WhatsApp > API Setup**, pero expirará y no sirve para producción.

Para que WhatsApp funcione de forma estable:

1. Entra a <https://business.facebook.com/settings/>.
2. Ve a **Users > System Users**.
3. Crea un System User para CopilotoIA, por ejemplo `copilotoia-whatsapp`.
4. Asígnale activos del negocio:
   - La app de Meta usada para WhatsApp.
   - El WhatsApp Business Account correspondiente.
5. Genera un token para esa app con estos permisos mínimos:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `business_management`
6. Si el portal lo permite, usa expiración **Never** para producción controlada; si no, documenta fecha de expiración y rota el secreto antes de que venza.
7. No edites código ni `.env` por tenant: pega ese token en el campo **Meta access token del tenant** del Admin Panel. CopilotoIA lo guarda en `.secrets/tenants/<TENANT_ID>/meta_access_token`; la referencia interna se deriva automáticamente.

### 10.5 Configurar secretos por tenant desde el Admin Panel

En el módulo **WhatsApp** del tenant, completa:

- `business_id`, `waba_id` y `phone_number_id` con los valores de Meta.
- **Meta access token del tenant** con el token real de Meta. CopilotoIA lo escribe en `.secrets/tenants/<TENANT_ID>/meta_access_token`.
- **App secret del tenant** con el App Secret de Meta. CopilotoIA lo escribe en `.secrets/tenants/<TENANT_ID>/whatsapp_app_secret`.
- **Verify token del webhook** con el mismo token que configurarás en Meta Webhooks. CopilotoIA lo escribe en `.secrets/tenants/<TENANT_ID>/whatsapp_verify_token`.
- **Modo de entrega** en `mock` o `live`.

No configures `token_ref` ni `app_secret_ref` desde el panel: la Core API deriva esas referencias internas automáticamente con la misma estructura para todos los tenants.

Reinicia servicios después de guardar o rotar secretos locales:

```bash
docker compose restart api event-worker
```

### 10.6 Configurar el webhook en Meta

En **Meta for Developers > tu app > WhatsApp > Configuration** configura:

| Campo de Meta | Valor para CopilotoIA |
|---|---|
| Callback URL | `https://<TU_DOMINIO_PUBLICO>/v1/webhooks/whatsapp` |
| Verify token | El valor que pegaste en **Verify token del webhook** dentro del Admin Panel del tenant |

Notas importantes:

- La URL debe ser HTTPS pública, sin autenticación, sin redirecciones y apuntar al puerto público que termina en la API de CopilotoIA.
- Si usas ngrok/Cloudflare Tunnel, la ruta final sigue siendo `/v1/webhooks/whatsapp`.
- Al guardar, Meta hará un `GET` de verificación. CopilotoIA responde el `hub.challenge` solo si `hub.verify_token` coincide con el secreto `.secrets/tenants/<TENANT_ID>/whatsapp_verify_token` de algún canal activo.
- Después de verificar, en **Webhook fields / Manage** suscribe al menos el campo **messages** del objeto **WhatsApp Business Account** para recibir mensajes entrantes y estados de mensajes.

Puedes probar manualmente la verificación antes de guardar en Meta:

```bash
curl -fsS "https://<TU_DOMINIO_PUBLICO>/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=<VERIFY_TOKEN_DEL_TENANT>&hub.challenge=ok"
```

Debe devolver:

```text
ok
```

### 10.7 Registrar el canal en CopilotoIA

Opción recomendada desde el Admin Panel:

1. Levanta el panel con `./scripts/bootstrap-admin-panel.sh` o `docker compose up -d --build admin-panel`.
2. Abre `http://localhost:3000/admin/`.
3. Inicia sesión con Auth0.
4. Selecciona el tenant.
5. Entra al módulo **WhatsApp**.
6. Completa:
   - **Business ID:** `business_id` de Business Settings.
   - **WABA ID:** `waba_id` / WhatsApp Business Account ID.
   - **Phone Number ID:** ID del número en API Setup.
   - **Meta access token del tenant:** pega el token real para que CopilotoIA escriba el secreto.
   - **App secret del tenant:** pega el App Secret real para que CopilotoIA escriba el secreto.
   - **Verify token del webhook:** pega el token de verificación que también configurarás en Meta Webhooks.
7. Pulsa **Registrar canal** para guardar el canal y los tres secretos en la estructura fija del tenant.
8. Pulsa **Ver health**. El estado local debe quedar `healthy` cuando todos los campos y referencias estén presentes y el canal esté activo.

Opción por API para el tenant demo:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $(grep '^SERVICE_TOKEN=' .env | cut -d= -f2-)" \
  -H 'X-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8000/v1/tenants/11111111-1111-1111-1111-111111111111/channels/whatsapp \
  -d '{
    "business_id":"<BUSINESS_ID>",
    "waba_id":"<WABA_ID>",
    "phone_number_id":"<PHONE_NUMBER_ID>",
    "meta_access_token":"<TOKEN_REAL_DE_META_DEL_TENANT>",
    "app_secret":"<APP_SECRET_DE_META_DEL_TENANT>",
    "verify_token":"<VERIFY_TOKEN_DEL_TENANT>"
  }'
```

Consultar health por API:

```bash
curl -fsS \
  -H "Authorization: Bearer $(grep '^SERVICE_TOKEN=' .env | cut -d= -f2-)" \
  -H 'X-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8000/v1/tenants/11111111-1111-1111-1111-111111111111/channels/whatsapp/health
```

### 10.8 Validar que WhatsApp ya funciona

1. En Meta, usa **WhatsApp > API Setup > Send and receive messages** para enviar un mensaje de prueba desde el número de prueba hacia tu teléfono permitido.
2. Responde desde tu WhatsApp personal al número de prueba o al número real conectado.
3. Revisa que CopilotoIA recibió el webhook:

```bash
docker compose logs -f api
```

4. En base de datos debe aparecer un registro en `app.webhook_events_raw`. Puedes consultarlo con:

```bash
docker compose exec postgres psql -U copiloto_admin -d copilotoia \
  -c "select provider, event_type, created_at from app.webhook_events_raw order by created_at desc limit 5;"
```

5. Para envío outbound real, asegúrate de que `event-worker` esté corriendo, que el contacto/conversación usen el `channel_id` registrado y que `.secrets/tenants/<TENANT_ID>/meta_access_token` contenga un token real del tenant. El worker llama a Graph API con `POST /<PHONE_NUMBER_ID>/messages` usando `META_GRAPH_VERSION`.

### 10.9 Checklist de errores comunes

| Síntoma | Causa probable | Qué corregir |
|---|---|---|
| Meta dice que no puede validar el callback | URL no pública, redirección, TLS inválido o verify token distinto | Usa HTTPS público directo a `/v1/webhooks/whatsapp` y usa exactamente el Verify token guardado desde el Admin Panel para ese tenant. |
| El GET manual devuelve 403 | `hub.verify_token` no coincide con `.secrets/tenants/<TENANT_ID>/whatsapp_verify_token` | Registra/rota el Verify token del tenant desde el Admin Panel y usa ese mismo valor. |
| Los webhooks no llegan aunque el callback verificó | No suscribiste el campo `messages` del WABA | En Meta > WhatsApp > Configuration > Webhook fields / Manage, activa `messages`. |
| Envío outbound queda mock | el secreto `meta_access_token` del tenant no resuelve a un token real o sigue como `local-mock...` | Pega/rota el token real en el Admin Panel y reinicia `event-worker`. |
| Graph API responde permisos insuficientes | Token sin permisos o System User sin activos asignados | Regenera token con `whatsapp_business_messaging`, `whatsapp_business_management` y `business_management`; asigna app y WABA al System User. |
| El número real no recibe mensajes | Número no registrado en Cloud API, negocio no verificado o app en modo/test limitado | Completa Business Verification, registra el número en WhatsApp Manager y revisa modo Live/App Review según aplique. |
| La firma del webhook falla | el secreto `whatsapp_app_secret` del tenant no corresponde a la app que envía webhooks | Pega/rota el App Secret correcto en el Admin Panel y reinicia `api`. |

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
META_GRAPH_VERSION=v23.0
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
