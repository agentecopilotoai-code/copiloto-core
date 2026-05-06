# Guía de instalación - Copiloto IA Core

Esta guía explica cómo poner a funcionar el core Docker de Copiloto IA en **desarrollo local** y cómo preparar la información necesaria para **producción**.

## 0. Estado esperado de Docker Desktop

Cuando el stack está sano, en Docker Desktop deberías ver estos servicios del proyecto `copilotoia`:

| Servicio | Debe estar corriendo | Comentario |
|---|---:|---|
| `postgres-1` | Sí | Base de datos PostgreSQL + `pgvector`. |
| `redis-1` | Sí | Cache/locks/sesiones efímeras. |
| `minio-1` | Sí | S3 local para desarrollo. |
| `api-1` | Sí | API REST en `http://localhost:8000/docs`. |
| `event-worker-1` | Sí | Worker de eventos salientes. No expone puertos. |
| `scheduler-1` | Sí | Worker de recordatorios. No expone puertos. |
| `otel-collector-1` | Sí, recomendado | Observabilidad local. Si está apagado, la API puede responder, pero falta telemetría. |

Si `api`, `postgres`, `redis` y `minio` están en verde, la API local probablemente ya está funcionando. Si `event-worker`, `scheduler` u `otel-collector` aparecen detenidos, revisa logs con:

```bash
docker compose logs --tail=200 event-worker scheduler otel-collector
```

## 1. Requisitos por sistema operativo

### macOS

1. Instala Docker Desktop desde <https://www.docker.com/products/docker-desktop/>.
2. Instala Git si no lo tienes:

```bash
git --version
```

3. Instala herramientas útiles con Homebrew si hacen falta:

```bash
brew install git curl openssl python@3.12
```

4. Verifica:

```bash
docker compose version
python3 --version
openssl version
```

### Windows 11 / Windows 10 con WSL2

1. Instala Docker Desktop y activa WSL2 backend.
2. Instala Ubuntu desde Microsoft Store si no lo tienes.
3. Abre Ubuntu/WSL y ejecuta:

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv
```

4. Verifica dentro de WSL:

```bash
docker compose version
python3 --version
openssl version
```

> Recomendado: clona el repo dentro del filesystem de WSL, por ejemplo `~/projects/CopilotoIA`, no en `C:\`, para evitar problemas de performance/permisos.

### Linux Ubuntu/Debian

1. Instala dependencias base:

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv ca-certificates
```

2. Instala Docker Engine siguiendo la guía oficial de Docker para tu distro.
3. Agrega tu usuario al grupo Docker si aplica:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

4. Verifica:

```bash
docker compose version
python3 --version
openssl version
```

## 2. Decisión de runtime Python

El proyecto soporta **Python 3**. En contenedores usamos `python:3.12-slim`, y los comandos Docker ejecutan `python3` explícitamente.

Para correr el stack local no necesitas instalar paquetes Python en tu máquina, porque Docker construye la imagen. Python3 local solo es necesario si quieres desarrollar o correr herramientas fuera de Docker.

## 3. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO> CopilotoIA
cd CopilotoIA
```

Si ya tienes el repo:

```bash
cd /ruta/a/CopilotoIA
git pull
```

## 4. Configuración local de secretos

Genera `.env` local y archivos `.secrets/*`:

```bash
./scripts/generate-local-secrets.sh
```

El script usa Bash + OpenSSL, no Python. Si un intento anterior dejó `.env` con placeholders `change-me-*`, el script lo respalda como `.env.incomplete.<timestamp>.bak` y genera uno nuevo.

Archivos generados:

| Archivo | Se sube a git | Uso |
|---|---:|---|
| `.env` | No | Variables locales de Docker Compose. |
| `.secrets/*` | No | Copia local de secretos sensibles con permisos `600`. |
| `.env.example` | Sí | Plantilla sin secretos reales. |

## 5. Levantar desarrollo local

```bash
./scripts/bootstrap.sh
```

Ese comando valida Docker, genera secretos si faltan, construye la imagen y levanta:

- API: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `http://localhost:9000`
- MinIO consola: `http://localhost:9001`
- OpenTelemetry OTLP HTTP: `http://localhost:4318`
- Métricas Prometheus del collector: `http://localhost:8889`

## 6. Verificación local

Revisa contenedores:

```bash
docker compose ps
```

Prueba health:

```bash
curl -fsS http://localhost:8000/v1/health
```

Ejecuta smoke test:

```bash
./scripts/smoke-test.sh
```

Abre Swagger:

```text
http://localhost:8000/docs
```

## 7. Base de datos local

La base se inicializa automáticamente la primera vez que se crea el volumen `postgres-data`.

Orden de scripts:

1. `infra/postgres/00-init-roles.sh`: crea el rol aplicativo.
2. `infra/postgres/01-schema.sql`: crea extensiones, tablas, índices, triggers, RLS y grants.
3. `infra/postgres/02-seed.sql`: crea tenants demo.

Tenants demo:

| Vertical | Tenant ID | Slug |
|---|---|---|
| Taller/servicio técnico | `11111111-1111-1111-1111-111111111111` | `demo-taller` |
| Barbería/peluquería | `22222222-2222-2222-2222-222222222222` | `demo-barberia` |
| Mascotas no clínico | `33333333-3333-3333-3333-333333333333` | `demo-mascotas` |

Entrar a PostgreSQL:

```bash
docker compose exec postgres psql -U copiloto_admin -d copilotoia
```

Probar tenant demo:

```bash
curl -fsS \
  -H 'X-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8000/v1/conversations
```

## 8. Información que debes obtener de Meta / WhatsApp

Para desarrollo local puedes operar en modo mock sin token real. Para probar WhatsApp real o ir a producción necesitas obtener esta información en Meta for Developers / Meta Business:

| Variable | Dónde se obtiene | Para qué sirve |
|---|---|---|
| `META_ACCESS_TOKEN` | Meta for Developers > App > WhatsApp > API Setup, o token permanente vía System User en Business Settings | Enviar mensajes por Graph API. |
| `WHATSAPP_APP_SECRET` | Meta for Developers > App Settings > Basic > App Secret | Validar firma `X-Hub-Signature-256` de webhooks. |
| `WHATSAPP_VERIFY_TOKEN` | Lo defines tú, por ejemplo un token aleatorio largo | Meta lo usa para verificar el webhook. Debe coincidir con tu `.env`. |
| `META_GRAPH_VERSION` | Versión Graph API elegida, ejemplo `v23.0` | Versionar endpoints de Meta. |
| `phone_number_id` | WhatsApp > API Setup > From phone number ID | Identifica el número que envía mensajes. |
| `waba_id` | WhatsApp Manager / Business Settings | Identifica la cuenta WhatsApp Business. |
| `business_id` | Business Settings > Business Info | Identifica tu Business Manager. |

### Pasos en Meta para desarrollo real

1. Crea o abre una app en <https://developers.facebook.com/>.
2. Agrega el producto **WhatsApp**.
3. Copia `Phone number ID` y `WhatsApp Business Account ID`.
4. Copia el `Temporary access token` para pruebas o crea un System User token para uso más estable.
5. Copia el `App Secret` desde App Settings > Basic.
6. Define tu propio `WHATSAPP_VERIFY_TOKEN` y ponlo también al configurar el webhook en Meta.
7. Configura el webhook apuntando a una URL pública que llegue a:

```text
https://<TU_DOMINIO_PUBLICO>/v1/webhooks/whatsapp
```

Para desarrollo local con webhook real necesitas un túnel HTTPS, por ejemplo ngrok o Cloudflare Tunnel, apuntando a `http://localhost:8000`.

## 9. Configurar WhatsApp real en `.env`

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

Registra el canal en el tenant:

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

## 10. Producción: qué debes preparar

Para producción no uses MinIO local ni `.env` con secretos en disco como fuente final. Prepara equivalentes gestionados:

| Capa | Desarrollo local | Producción recomendada |
|---|---|---|
| Runtime | Docker Compose | ECS/Fargate, Kubernetes, Cloud Run, App Service o similar |
| PostgreSQL | `pgvector/pgvector:pg16` | RDS PostgreSQL/Cloud SQL/Azure PostgreSQL con backups/PITR |
| Redis | `redis:7.4-alpine` | Redis gestionado con TLS/auth |
| Objetos | MinIO | S3/GCS/Azure Blob con cifrado |
| Secretos | `.env` / `.secrets` | Secrets Manager/Secret Manager/Key Vault |
| TLS | Local sin TLS | Load balancer/API gateway con HTTPS |
| Observabilidad | OTel Collector local | OTel Collector + CloudWatch/Datadog/Grafana/etc. |

### Checklist de variables para producción

Define estas variables en el gestor de secretos o sistema de configuración de tu plataforma:

```env
APP_ENV=production
DATABASE_URL=postgresql://<APP_USER>:<PASSWORD>@<HOST>:5432/<DB>
REDIS_URL=redis://<HOST>:6379/0
JWT_ISSUER=<ISSUER_REAL>
JWT_AUDIENCE=<AUDIENCE_REAL>
JWT_SECRET=<SECRETO_LARGO>
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

### Checklist de despliegue producción

1. Crear base PostgreSQL y ejecutar `infra/postgres/01-schema.sql` como migración inicial.
2. Crear usuario aplicativo con permisos mínimos equivalentes a `copiloto_app`.
3. Crear bucket de objetos y política por prefijo de tenant.
4. Crear secretos en el gestor cloud.
5. Construir y publicar imagen Docker de la API/workers.
6. Desplegar `api`, `event-worker` y `scheduler` como servicios separados.
7. Exponer solo `api` por HTTPS.
8. Configurar webhook público de Meta hacia `/v1/webhooks/whatsapp`.
9. Activar backups/PITR de PostgreSQL.
10. Configurar logs, métricas y alertas.

## 11. Comandos útiles

Ver logs:

```bash
docker compose logs -f api event-worker scheduler otel-collector
```

Reiniciar servicios:

```bash
docker compose restart api event-worker scheduler otel-collector
```

Apagar sin borrar datos:

```bash
docker compose down
```

Apagar y borrar volúmenes:

```bash
docker compose down -v
```

Regenerar todo desde cero con el script seguro de desarrollo:

```bash
./scripts/reset-local-dev.sh --yes
```

Equivalente manual:

```bash
docker compose down -v --remove-orphans
./scripts/bootstrap.sh
```

## 12. Troubleshooting

### `InvalidPasswordError: password authentication failed for user "copiloto_app"`

Esto indica que tu volumen local de PostgreSQL fue creado con una contraseña anterior, pero tu `.env` actual tiene otra. PostgreSQL solo usa `POSTGRES_PASSWORD` y `APP_DB_PASSWORD` durante la primera inicialización del volumen; si luego regeneras `.env`, la base queda con la contraseña vieja.

En desarrollo local, la solución más simple es borrar el volumen y recrear la base con el `.env` actual:

```bash
./scripts/reset-local-dev.sh --yes
```

Luego valida:

```bash
docker compose ps
curl -fsS http://localhost:8000/v1/health
./scripts/smoke-test.sh
```

Si necesitas conservar datos, no uses `down -v`; cambia manualmente la contraseña del rol `copiloto_app` dentro de PostgreSQL o restaura un backup.

### `curl: (56) Recv failure: Connection reset by peer`

Normalmente significa que la API arrancó y se cayó durante startup. Revisa primero los logs de API y workers:

```bash
docker compose logs --tail=200 api event-worker scheduler
```

Si ves `InvalidPasswordError` para `copiloto_app`, aplica el reset local anterior.

### `python: command not found`

El stack soporta Python3. Los scripts y contenedores deben usar `python3`. Actualiza el repo y vuelve a construir:

```bash
git pull
docker compose up -d --build
```

### `docker: command not found`

Docker no está instalado o no está en el `PATH`. Instala Docker Desktop/Engine y verifica:

```bash
docker compose version
```

### `otel-collector-1` aparece detenido

Revisa logs:

```bash
docker compose logs --tail=200 otel-collector
```

La configuración actual usa el exporter `debug`, compatible con el collector actual.

### `event-worker-1` o `scheduler-1` aparecen detenidos

Revisa logs:

```bash
docker compose logs --tail=200 event-worker scheduler
```

Luego reconstruye y reinicia:

```bash
docker compose up -d --build event-worker scheduler
```

### Cambié SQL pero no se refleja

Los scripts de inicialización solo corren cuando el volumen de PostgreSQL se crea por primera vez:

```bash
docker compose down -v
./scripts/bootstrap.sh
```

### Puerto ocupado

Si `8000`, `5432`, `6379`, `9000` o `9001` están ocupados, cambia los puertos en `docker-compose.yml` o detén el servicio que los usa.
