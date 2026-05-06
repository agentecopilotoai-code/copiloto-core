# Guía de instalación local - Copiloto IA Core

Esta guía explica cómo levantar en tu máquina el core Docker de referencia del Copiloto IA: API REST, workers, PostgreSQL con `pgvector`, Redis, MinIO/S3 local y OpenTelemetry Collector.

## 1. Requisitos

Instala estas herramientas antes de empezar:

| Herramienta | Versión recomendada | Uso |
|---|---:|---|
| Docker Engine / Docker Desktop | 24+ | Ejecutar contenedores |
| Docker Compose v2 | 2.20+ | Orquestar los servicios locales |
| Git | 2.40+ | Clonar y versionar el proyecto |
| Bash | 5+ | Ejecutar scripts de instalación |
| curl | cualquiera reciente | Smoke tests locales |
| OpenSSL | cualquiera reciente | Generar secretos locales |

> No necesitas instalar PostgreSQL, Redis, MinIO ni Python en tu máquina para correr el stack local, porque todo corre dentro de Docker. Python solo es necesario si quieres desarrollar o ejecutar tests fuera de contenedores. El script de secretos usa `openssl`, que normalmente ya viene instalado en Linux/macOS; si no lo tienes, instálalo o crea `.env` manualmente desde `.env.example`.

## 2. Clonar o entrar al repositorio

Si aún no tienes el repositorio:

```bash
git clone <URL_DEL_REPOSITORIO> CopilotoIA
cd CopilotoIA
```

Si ya estás en el proyecto:

```bash
cd /workspace/CopilotoIA
```

## 3. Generar secretos locales seguros

El repositorio incluye `.env.example` como plantilla. No edites secretos reales sobre ese archivo; genera un `.env` local ignorado por git:

```bash
./scripts/generate-local-secrets.sh
```

Este script crea:

- `.env` con passwords/tokens locales generados automáticamente.
- `.secrets/*` con copias de secretos sensibles y permisos `600`.

Ambos están ignorados por git. Puedes cambiar esos valores cuando quieras; en producción deberías reemplazarlos por un gestor de secretos como AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, Docker secrets o Kubernetes secrets.

## 4. Levantar todo con Docker

La forma recomendada es usar el bootstrap:

```bash
./scripts/bootstrap.sh
```

Ese comando construye la imagen de la API y levanta:

- `api`: FastAPI REST en `http://localhost:8000`.
- `event-worker`: worker de eventos de dominio.
- `scheduler`: worker de recordatorios.
- `postgres`: PostgreSQL 16 con `pgvector`.
- `redis`: cache/locks/sesiones efímeras.
- `minio`: almacenamiento S3 local.
- `otel-collector`: collector local de observabilidad.

También puedes levantar manualmente:

```bash
docker compose up -d --build
```

## 5. Verificar que quedó corriendo

Revisa el estado de contenedores:

```bash
docker compose ps
```

Ejecuta el health check:

```bash
curl -fsS http://localhost:8000/v1/health
```

Abre la documentación interactiva de la API:

```text
http://localhost:8000/docs
```

Abre la consola de MinIO:

```text
http://localhost:9001
```

Las credenciales de MinIO están en tu `.env`:

- Usuario: `S3_ACCESS_KEY_ID`
- Password: `S3_SECRET_ACCESS_KEY`

## 6. Base de datos inicial

PostgreSQL se inicializa automáticamente la primera vez que se crea el volumen `postgres-data`.

Los scripts se ejecutan en este orden:

1. `infra/postgres/00-init-roles.sh`: crea el usuario aplicativo definido por `APP_DB_USER` y `APP_DB_PASSWORD`.
2. `infra/postgres/01-schema.sql`: crea extensiones, schema `app`, tablas, índices, triggers, RLS y grants.
3. `infra/postgres/02-seed.sql`: crea tenants demo para los tres verticales.

Tenants demo incluidos:

| Vertical | Tenant ID | Slug |
|---|---|---|
| Taller/servicio técnico | `11111111-1111-1111-1111-111111111111` | `demo-taller` |
| Barbería/peluquería | `22222222-2222-2222-2222-222222222222` | `demo-barberia` |
| Mascotas no clínico | `33333333-3333-3333-3333-333333333333` | `demo-mascotas` |

Para entrar a PostgreSQL desde Docker:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Si tu shell no tiene esas variables cargadas, usa los valores de `.env`, por ejemplo:

```bash
docker compose exec postgres psql -U copiloto_admin -d copilotoia
```

## 7. Probar endpoints multitenant

El core usa `X-Tenant-Id` para fijar el tenant de la transacción y activar Row-Level Security.

Ejemplo para listar conversaciones del tenant demo de taller:

```bash
curl -fsS \
  -H 'X-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8000/v1/conversations
```

Ejemplo para consultar health del canal WhatsApp demo:

```bash
curl -fsS \
  http://localhost:8000/v1/tenants/11111111-1111-1111-1111-111111111111/channels/whatsapp/health
```

## 8. Configurar WhatsApp real

Por defecto el adaptador de WhatsApp puede operar en modo local/mock si no configuras un token real. Para usar Meta/WhatsApp Cloud API real, cambia en `.env`:

```env
META_ACCESS_TOKEN=<TU_TOKEN_REAL>
WHATSAPP_VERIFY_TOKEN=<TOKEN_QUE_CONFIGURAS_EN_META>
WHATSAPP_APP_SECRET=<APP_SECRET_DE_META>
META_GRAPH_VERSION=v23.0
```

Luego registra o actualiza el canal de un tenant con el `phone_number_id` real usando el endpoint:

```text
POST /v1/tenants/{tenant_id}/channels/whatsapp
```

Reinicia los servicios para tomar los cambios:

```bash
docker compose restart api event-worker scheduler
```

## 9. Comandos útiles

Ver logs de la API:

```bash
docker compose logs -f api
```

Ver logs de workers:

```bash
docker compose logs -f event-worker scheduler
```

Apagar servicios sin borrar datos:

```bash
docker compose down
```

Apagar y borrar volúmenes locales, incluyendo la base de datos:

```bash
docker compose down -v
```

Regenerar la base desde cero:

```bash
docker compose down -v
./scripts/bootstrap.sh
```

## 10. Troubleshooting


### `python: command not found` al generar secretos

El generador de secretos ya no depende de Python. Actualiza el repositorio y vuelve a ejecutar:

```bash
./scripts/generate-local-secrets.sh
```

Si el intento anterior dejó un `.env` incompleto con placeholders `change-me-*`, el script lo moverá automáticamente a `.env.incomplete.<timestamp>.bak` y generará uno nuevo.

### `docker: command not found`

Docker no está instalado o no está en el `PATH`. Instala Docker Desktop o Docker Engine y vuelve a ejecutar `docker compose version`.

### El puerto `8000`, `5432`, `6379`, `9000` o `9001` ya está ocupado

Cambia el mapeo de puertos en `docker-compose.yml` o detén el servicio local que usa ese puerto.

### Cambié SQL pero no se refleja en PostgreSQL

Los scripts de `/docker-entrypoint-initdb.d` solo corren cuando el volumen de PostgreSQL se crea por primera vez. Para reinicializar:

```bash
docker compose down -v
./scripts/bootstrap.sh
```

### Error de firma en webhook WhatsApp

Verifica que `WHATSAPP_APP_SECRET` en `.env` sea el mismo App Secret configurado en Meta y que el webhook envíe el header `X-Hub-Signature-256`.

## 11. ¿Por qué se hizo en Python?

Se eligió Python para este core inicial por razones pragmáticas:

- FastAPI permite crear una API REST clara y rápida, con documentación OpenAPI automática.
- El ecosistema Python es muy fuerte para IA/RAG, embeddings, procesamiento de texto, automatización y workers.
- La imagen Docker mantiene el runtime aislado, así que no obliga a instalar Python localmente para usar el producto.
- Para un MVP permite avanzar rápido y luego extraer servicios a otro lenguaje si alguna pieza lo requiere.

No es una decisión irreversible. Si prefieres Node.js/TypeScript, Java/Kotlin, Go o .NET, la arquitectura se puede mantener igual: API REST, eventos, PostgreSQL con RLS, Redis, object storage y workers. Lo que cambiaría sería la implementación del runtime, no el modelo ni los contenedores base.
