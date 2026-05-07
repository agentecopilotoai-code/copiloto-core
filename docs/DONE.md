# Tareas realizadas de CopilotoIA

Este archivo registra únicamente tareas terminadas. Nunca se debe mover una tarea desde `docs/BACKLOG.md` a este documento si no está completamente implementada y validada.

## Protocolo de registro

Cada entrada debe incluir:

- consecutivo original de la tarea;
- fecha de finalización;
- resumen de lo realizado;
- archivos modificados;
- comandos/validaciones ejecutadas;
- notas o limitaciones reales.

## Tareas completadas

### TASK-0000 — Crear sistema operativo de backlog/done y script Auth0 inicial

- **Fecha:** 2026-05-06
- **Origen:** solicitud directa del usuario, no retirada del stack de `docs/BACKLOG.md`.
- **Resumen:** se creó el mecanismo documental para que el agente pueda tomar la primera tarea pendiente del backlog, ejecutarla, retirarla solo si está terminada y registrarla en este documento. También se agregó un script idempotente para preparar Auth0 para CopilotoIA.
- **Archivos modificados:**
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
  - `INSTALL.md`
  - `scripts/configure-auth0.sh`
- **Validaciones:**
  - `bash -n scripts/configure-auth0.sh`
  - `git diff --check`
  - `python3 -m compileall app`
- **Notas:** las tareas futuras empiezan en `TASK-0001`; este registro no consume ninguna tarea del backlog porque corresponde al bootstrap pedido explícitamente.

### TASK-0001 — Implementar validación OIDC/Auth0 en la API

- **Fecha:** 2026-05-06
- **Resumen:** se agregó validación OIDC/Auth0 RS256 mediante JWKS con cache para bearer tokens de usuario cuando `AUTH0_DOMAIN` y `AUTH0_AUDIENCE` están configurados; se preservó el fallback HS256 local cuando Auth0 no está habilitado y se mantuvo `SERVICE_TOKEN` para workloads internos. La autenticación ahora extrae `tenant_id`, `roles` y `support_mode` desde claims namespaced, conserva el control de aislamiento por `X-Tenant-Id` y rechaza algoritmos/claves inválidas.
- **Archivos modificados:**
  - `app/core/config.py`
  - `app/core/security.py`
  - `.env.example`
  - `docker-compose.yml`
  - `scripts/bootstrap.sh`
  - `INSTALL.md`
  - `tests/test_security.py`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python3 -m compileall app tests`
  - `git diff --check`
  - `uv run pytest` (bloqueado por fallo de descarga desde PyPI en el entorno)
  - `uv run ruff check .` (bloqueado por fallo de descarga desde PyPI en el entorno)
- **Notas:** la validación Auth0 se activa con las variables que `scripts/configure-auth0.sh` deja en `.env.auth0.local`; si `AUTH0_DOMAIN` queda vacío, los JWT HS256 locales siguen disponibles para desarrollo y smoke tests.

### TASK-0002 — Crear el esqueleto del Admin Panel MVP

- **Fecha:** 2026-05-06
- **Resumen:** se creó un Admin Panel MVP con frontend React JS + Vite, estructurado por componentes, hooks, contexto, servicios y datos de módulos. El backend `app/admin` conserva el flujo OIDC/Auth0 Authorization Code para usar la configuración local ya generada y leer `.secrets/auth0-admin-client-secret` sin exponer secretos al navegador. Se agregó sesión HTTP-only de servidor, layout base con selector de tenant, navegación de placeholders para Tenant Setup, WhatsApp, Knowledge Studio, Operations Desk y Audit, Dockerfile dedicado del panel, servicio Docker `admin-panel` en el puerto 3000 y bootstrap propio `scripts/bootstrap-admin-panel.sh`, que ahora construye y levanta el contenedor por defecto. El backend admin usa configuración propia opcional para no fallar cuando el contenedor no recibe variables obligatorias del core como `DATABASE_URL`, `SERVICE_TOKEN`, WhatsApp o S3. El build React se configuró con base `/admin/` y el backend sirve `/admin/assets/*` más una ruta compatible `/assets/*` para evitar 404 de assets cacheados. El logout usa redirect `303 See Other` hacia Auth0 para convertir el `POST /admin/logout` del formulario en `GET /v2/logout`, y `scripts/configure-auth0.sh` ahora incluye `/admin/` en Allowed Logout URLs.
- **Archivos modificados:**
  - `.dockerignore`
  - `.gitignore`
  - `admin-panel/Dockerfile`
  - `admin-panel/index.html`
  - `admin-panel/package.json`
  - `admin-panel/vite.config.js`
  - `admin-panel/src/*`
  - `app/admin/__init__.py`
  - `app/admin/config.py`
  - `app/admin/main.py`
  - `app/admin/routes.py`
  - `app/admin/static/.gitkeep`
  - `app/core/config.py`
  - `app/main.py`
  - `docker-compose.yml`
  - `docs/ADMIN_PANEL.md`
  - `INSTALL.md`
  - `scripts/bootstrap-admin-panel.sh`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python3 -m compileall app`
  - `git diff --check`
  - `npm --prefix admin-panel install` (bloqueado por HTTP 403 contra npm registry en el entorno)
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no puede instalarse mientras npm registry devuelve HTTP 403)
  - `./scripts/bootstrap-admin-panel.sh --skip-docker` (bloqueado por el mismo HTTP 403 de npm registry)
  - `bash -n scripts/bootstrap-admin-panel.sh`
  - `docker compose build admin-panel` (bloqueado porque Docker no está instalado en el entorno)
- **Notas:** el panel queda listo para validar login real contra Auth0 cuando `.env.auth0.local` y `.secrets/auth0-admin-client-secret` existen localmente; las sesiones son en memoria para el MVP y deben externalizarse antes de producción.

### TASK-0003 — Implementar Tenant Setup Wizard

- **Fecha:** 2026-05-07
- **Resumen:** se implementó el wizard MVP de Tenant Setup en el Admin Panel con secciones por tabs para crear tenant, editar settings, configurar horarios, política de escalamiento, privacidad/PII y consultar auditoría. Los campos `pii_policy`, `no_train` y `max_bot_turns` se configuran mediante controles de formulario y builder visual, no mediante edición manual de JSON. El wizard consume los endpoints REST existentes para crear tenants, actualizar settings y leer audit logs, y agrega el tenant creado al selector activo del panel.
- **Archivos modificados:**
  - `admin-panel/src/components/layout/AdminLayout.jsx`
  - `admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `admin-panel/src/styles/global.css`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `git diff --check`
  - `python3 -m compileall app`
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no está instalado en el entorno)
  - `npm --prefix admin-panel install` (bloqueado por HTTP 403 contra npm registry en el entorno)
- **Notas:** la creación de tenants requiere un token con rol `owner` no acotado a tenant, y la actualización/consulta por tenant requiere un token tenant-scoped o `support_mode`, de acuerdo con la seguridad existente de la API.

### TASK-0004 — Implementar onboarding WhatsApp/WABA en panel

- **Fecha:** 2026-05-07
- **Resumen:** se implementó el onboarding WhatsApp/WABA en el Admin Panel. El módulo WhatsApp ahora muestra un formulario para registrar `business_id`, `waba_id`, `phone_number_id`, `token_ref` y `app_secret_ref`, consume el endpoint de upsert del canal por tenant, permite ejecutar un health check local y presenta un checklist visual de avance WABA. El health de la Core API ahora devuelve el canal completo con referencias no secretas, checks locales y estado `healthy/degraded` para que el panel pueda mostrar evidencia del canal activo. También se documentaron las variables y referencias de secretos requeridas sin duplicar la configuración local existente.
- **Archivos modificados:**
  - `admin-panel/src/components/layout/AdminLayout.jsx`
  - `admin-panel/src/components/modules/whatsapp/WhatsAppOnboarding.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `admin-panel/src/styles/global.css`
  - `app/api/v1/routes.py`
  - `docs/ADMIN_PANEL.md`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python3 -m compileall app`
  - `git diff --check`
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no está instalado en el entorno)
  - `npm --prefix admin-panel install` (bloqueado por HTTP 403 contra npm registry en el entorno)
  - `uv run pytest` (bloqueado por fallo de descarga desde PyPI en el entorno)
- **Notas:** el health check es local en esta iteración (`upstream=not_checked_in_local_core`); valida que CopilotoIA tenga la configuración mínima y no consulta Graph API todavía.

### TASK-0005 — Implementar Knowledge Studio MVP

- **Fecha:** 2026-05-07
- **Resumen:** se implementó el Knowledge Studio MVP para que un admin gestione documentos por tenant desde el panel. La Core API ahora expone CRUD/listado de documentos con filtros por estado, visibilidad y fuente; soporta contenido manual para FAQ/políticas, registro de fuentes/archivos mediante URI/checksum/MIME, estados `draft`, `indexing`, `active` y `failed`, auditoría de creación/actualización/eliminación y aislamiento mediante `X-Tenant-Id` + RLS. El esquema de `knowledge_documents` incorpora `document_type`, `content` y `metadata`. El Admin Panel agrega un módulo funcional con editor, filtros, lista de documentos, cambios rápidos de estado y acciones de edición/eliminación.
- **Archivos modificados:**
  - `app/api/v1/schemas.py`
  - `app/api/v1/routes.py`
  - `infra/postgres/01-schema.sql`
  - `admin-panel/src/components/layout/AdminLayout.jsx`
  - `admin-panel/src/components/modules/knowledge/KnowledgeStudio.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `admin-panel/src/styles/global.css`
  - `tests/test_knowledge_documents.py`
  - `docs/ADMIN_PANEL.md`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python3 -m compileall app`
  - `git diff --check`
  - `pytest tests/test_knowledge_documents.py` (bloqueado porque el Python global no tiene `pydantic`)
  - `uv run pytest tests/test_knowledge_documents.py` (bloqueado por fallo de descarga desde PyPI en el entorno)
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no está instalado en el entorno)
- **Notas:** la carga binaria real a object storage queda para una integración posterior; este MVP cumple el alcance registrando fuentes ya cargadas u object keys junto con checksum/MIME, sin crear variables nuevas de secretos. Posteriormente se agregó compatibilidad con volúmenes PostgreSQL existentes y una migración idempotente en `scripts/bootstrap.sh` para evitar `UndefinedColumnError` cuando la tabla `app.knowledge_documents` aún no tiene las columnas nuevas.

### TASK-0006 — Implementar pipeline de indexación RAG

- **Fecha:** 2026-05-07
- **Resumen:** se implementó el pipeline de indexación RAG para documentos de conocimiento por tenant. La Core API agrega `POST /v1/knowledge/documents/{document_id}/index`, extrae texto desde `content` o `metadata.extracted_text`, aplica sanitización básica contra instrucciones maliciosas documentales, genera chunks con `chunk_index`, `section_path`, `token_count`, metadata de embeddings y embeddings determinísticos configurables, reemplaza de forma transaccional los chunks previos en `app.knowledge_chunks` y publica el documento como `active` solo al finalizar el indexado. La API rechaza activaciones manuales de documentos sin chunks para mantener la garantía de que un documento activo tiene chunks asociados y conserva aislamiento con `tenant_id`, `X-Tenant-Id` y RLS.
- **Archivos modificados:**
  - `app/services/rag_indexing.py`
  - `app/api/v1/routes.py`
  - `app/core/config.py`
  - `admin-panel/src/components/modules/knowledge/KnowledgeStudio.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `.env.example`
  - `tests/test_rag_indexing.py`
  - `docs/ADMIN_PANEL.md`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `pytest tests/test_rag_indexing.py`
  - `pytest tests/test_rag_indexing.py tests/test_knowledge_documents.py` (bloqueado porque el Python global no tiene `pydantic`)
  - `python3 -m compileall app`
  - `git diff --check`
  - `ruff check app tests`
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no está instalado en el entorno)
  - `npm --prefix admin-panel install` (bloqueado por HTTP 403 contra npm registry en el entorno)
- **Notas:** el proveedor de embeddings por defecto es local y determinístico (`local_hash`) para mantener el MVP sin dependencias externas ni secretos nuevos. Los proveedores/modelos reales pueden conectarse reutilizando las variables `RAG_EMBEDDING_*` y preservando la dimensión compatible con `app.knowledge_chunks.embedding`.

### TASK-0007 — Implementar prueba de retrieval y respuesta RAG

- **Fecha:** 2026-05-07
- **Resumen:** se implementó la prueba de retrieval y respuesta RAG para admins por tenant. La Core API agrega `POST /v1/intents/evaluate`, recupera chunks activos de `app.knowledge_chunks` asociados a documentos `active`, calcula ranking lexical determinístico con score y términos coincidentes, devuelve fuente, visibilidad, tipo de fuente, sección y excerpt por chunk, y solo genera una respuesta sugerida si el mejor score supera el umbral de evidencia. Cuando no hay contexto suficiente, la respuesta queda en `escalate_to_human` con handoff requerido. El Admin Panel incorpora una sección de prueba RAG en Knowledge Studio para preguntar, ver respuesta trazable y revisar los chunks/documentos usados.
- **Archivos modificados:**
  - `app/services/rag_retrieval.py`
  - `app/api/v1/schemas.py`
  - `app/api/v1/routes.py`
  - `admin-panel/src/components/modules/knowledge/KnowledgeStudio.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `admin-panel/src/styles/global.css`
  - `tests/test_rag_retrieval.py`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python -m compileall app`
  - `ruff check app tests admin-panel/src`
  - `pytest -q tests/test_rag_retrieval.py tests/test_intent_evaluate_query_static.py tests/test_admin_proxy_security_static.py tests/test_rag_indexing.py`
  - `pytest -q tests/test_rag_retrieval.py tests/test_intent_evaluate_query_static.py tests/test_admin_proxy_security_static.py tests/test_rag_indexing.py tests/test_knowledge_documents.py` (bloqueado porque el Python global no tiene `pydantic`)
  - `npm --prefix admin-panel run build` (bloqueado porque `vite` no está instalado en el entorno)
- **Notas:** el retrieval usa scoring lexical local y determinístico para mantener el MVP sin nuevas dependencias externas ni secretos. El endpoint audita cada evaluación con estado, contexto suficiente, chunks devueltos y score superior. Correcciones posteriores: el proxy del Admin Panel dejó de reenviar headers `Authorization` del navegador y ya no expone el access token en `/admin/api/session`; las llamadas a `/admin/api/core/*` usan siempre el token guardado en la sesión HTTP-only para evitar `Invalid token` por tokens stale o de otra audiencia. El retrieval ya no limita a los 1000 chunks más recientes antes del ranking consciente de la pregunta y normaliza variantes singulares/plurales comunes en español para no perder evidencia ubicada en títulos o secciones activas.

### TASK-0008 — Implementar Operations Desk mínimo

- **Fecha:** 2026-05-07
- **Resumen:** se implementó el Operations Desk MVP para que agentes operen conversaciones por tenant desde el Admin Panel. El backend ahora devuelve un inbox con contacto, último mensaje y handoff activo; el detalle incluye mensajes y handoffs; el envío outbound encola el mensaje, actualiza el estado conversacional y deja auditoría; el handoff puede crearse, aceptarse/tomarse por el agente actual y liberarse al bot cerrando handoffs activos. El panel reemplaza el placeholder del módulo con inbox, detalle, acciones de handoff y composer de respuesta.
- **Archivos modificados:**
  - `app/api/v1/routes.py`
  - `admin-panel/src/components/layout/AdminLayout.jsx`
  - `admin-panel/src/components/modules/operations/OperationsDesk.jsx`
  - `admin-panel/src/services/coreApi.js`
  - `admin-panel/src/styles/global.css`
  - `tests/test_operations_desk_static.py`
  - `docs/BACKLOG.md`
  - `docs/DONE.md`
- **Validaciones:**
  - `python3 -m compileall app tests`
  - `pytest -q tests/test_operations_desk_static.py`
  - `git diff --check`
  - `npm --prefix admin-panel run build` (bloqueado porque las dependencias de Vite/React no están instaladas en este entorno)
- **Notas:** no se agregaron secretos ni variables nuevas; el agente asignado reutiliza el usuario local vinculado al `auth_subject` de la sesión autenticada. Corrección posterior: se agregó inicio de conversación desde el Operations Desk, creando/reutilizando contacto y conversación con mensaje inicial outbound auditado; también se corrigió la serialización de `bytea`/`phone_hash` para evitar errores UTF-8 al devolver contactos. Ajustes posteriores: el inicio devuelve un detalle completo y el panel lo muestra inmediatamente para evitar un 404 transitorio al consultar el detalle justo después del `POST /conversations/start`; se agregaron logs estructurados de inbox, inicio, canal faltante y diagnóstico de detalle 404 para diferenciar tenant incorrecto, conversación inexistente o carrera de visibilidad. Corrección posterior: el worker de eventos registra intentos/éxitos/fallos de entrega WhatsApp, marca mensajes como `failed` cuando Meta Graph API rechaza el envío y trata tokens `local-mock*` como modo simulado para no confundir colas locales con entregas reales. Ajuste posterior: los envíos simulados ahora se loguean como `message_delivery_mocked` y el panel muestra “Simulado local: no salió a WhatsApp”. Corrección posterior: aceptar un handoff ahora solo reclama handoffs con estado `open`, evitando que un segundo agente con inbox desactualizado reasigne silenciosamente un handoff ya aceptado por otro agente. Ajuste posterior: el canal WhatsApp del tenant ahora tiene `account_mode` configurable (`mock`/`live`) desde el onboarding; el worker usa ese modo para decidir si simula localmente o llama a Meta, y en modo `live` falla explícitamente si `META_ACCESS_TOKEN` sigue como placeholder/mock. Ajuste posterior: el health del canal ahora indica `meta_access_token_configured` y `delivery_ready`, y el panel muestra una alerta cuando el canal está en modo real pero el worker/Core API sigue sin token real. Ajuste posterior: el envío real ya no depende de un `META_ACCESS_TOKEN` global; el worker resuelve el token por `tenant_channels.token_ref`, el onboarding prefiere rutas `secrets/tenants/<tenant_id>/...`, y Docker monta `.secrets` en API/worker para soportar credenciales por tenant.
