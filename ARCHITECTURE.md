# Core Docker de referencia para Copiloto IA

Este core implementa la arquitectura del `README.md` como un MVP ejecutable en Docker: API REST, recepción de webhooks, workers asíncronos, PostgreSQL con RLS, Redis, MinIO/S3 y OpenTelemetry.

## Componentes y responsabilidades

| Servicio Docker | Componente de referencia | Responsabilidad |
|---|---|---|
| `api` | `api-gateway`, `desk-api`, `webhook-receiver` | Expone REST `/v1`, valida JWT/service token, aplica `X-Tenant-Id`, persiste webhooks raw y responde rápido. |
| `event-worker` | `event-normalizer`, `conversation-orchestrator`, `action-engine` parcial | Publica mensajes salientes desde `domain_events`, usa adaptador estable para Meta Graph API y funciona en modo mock si no hay token real. |
| `scheduler` | `scheduler` | Busca `reminder_jobs` vencidos y los convierte en eventos de dominio idempotentes. |
| `postgres` | `postgres` | Estado transaccional, tablas del dominio, extensiones `pgcrypto`, `citext`, `pgvector`, `btree_gist` y Row-Level Security por tenant. |
| `redis` | `redis` | Base para cache, locks, sesiones efímeras e idempotencia distribuida. |
| `minio` | `object-storage` | S3 local para media, documentos, exports y artefactos. |
| `otel-collector` | `otel/monitoring` | Receptor OTLP y exportador local de logs/Prometheus. |

## Seguridad local de secretos

- `.env.example` contiene valores de plantilla y nombres de variables.
- `scripts/generate-local-secrets.sh` crea `.env` y `.secrets/*` con permisos `600`.
- `.env`, `.env.*` y `.secrets/*` están ignorados por git; solo se versiona `.secrets/.gitkeep`.
- En producción, reemplaza estos archivos por Secrets Manager, Secret Manager, Key Vault o Docker/Kubernetes secrets.

## Arranque

```bash
./scripts/bootstrap.sh
```

La inicialización de PostgreSQL replica el modelo del README mediante scripts montados en `/docker-entrypoint-initdb.d`:

1. `infra/postgres/00-init-roles.sh`: crea el rol aplicativo `copiloto_app` con contraseña tomada de `.env`.
2. `infra/postgres/01-schema.sql`: crea schema `app`, tablas, índices, triggers, RLS y grants.
3. `infra/postgres/02-seed.sql`: crea tenants demo para los tres verticales, settings, canales WhatsApp y recursos base.

## Conexiones

- API/worker/scheduler usan `DATABASE_URL` con el usuario aplicativo `copiloto_app`.
- El contenedor PostgreSQL usa `POSTGRES_USER`/`POSTGRES_PASSWORD` para bootstrap admin.
- La API establece `app.tenant_id` y `app.support_mode` en cada transacción para que PostgreSQL aplique RLS.
- Webhooks de WhatsApp requieren `WHATSAPP_VERIFY_TOKEN` para verificación GET y `WHATSAPP_APP_SECRET` para validar `X-Hub-Signature-256`.

## Endpoints principales

- `GET /v1/health`
- `POST /v1/tenants`
- `GET /v1/tenants/{tenant_id}`
- `PATCH /v1/tenants/{tenant_id}/settings`
- `POST /v1/tenants/{tenant_id}/channels/whatsapp`
- `GET /v1/tenants/{tenant_id}/channels/whatsapp/health`
- `POST /v1/contacts/upsert`
- `GET /v1/conversations`
- `POST /v1/conversations/{conversation_id}/messages`
- `POST /v1/conversations/{conversation_id}/handoff`
- `POST /v1/service-requests`
- `POST /v1/appointments`
- `POST /v1/knowledge/documents`
- `POST /v1/prompts`
- `GET/POST /v1/webhooks/whatsapp`

## Tenants demo

| Vertical | Tenant ID | Slug |
|---|---|---|
| Taller/servicio técnico | `11111111-1111-1111-1111-111111111111` | `demo-taller` |
| Barbería/peluquería | `22222222-2222-2222-2222-222222222222` | `demo-barberia` |
| Mascotas no clínico | `33333333-3333-3333-3333-333333333333` | `demo-mascotas` |
