# Backlog operativo de CopilotoIA

Este archivo es la pila única de tareas pendientes para avanzar el producto hacia producción. Cuando el usuario diga **"continúa con la siguiente tarea"**, el agente debe tomar la **primera tarea activa** de este documento, ejecutarla completamente, retirarla de este backlog y moverla a `docs/DONE.md` con evidencia concreta de lo realizado.

## Protocolo obligatorio para agentes

1. Leer este archivo y seleccionar la primera tarea con estado `PENDING` en orden ascendente de consecutivo.
2. Ejecutar solo esa tarea, salvo que sea imposible terminarla sin una subtarea técnica estrictamente necesaria.
3. No mover una tarea a `docs/DONE.md` si no está terminada y validada.
4. Si una tarea queda bloqueada, mantenerla en este archivo y documentar el bloqueo dentro de la misma tarea.
5. Al terminar una tarea:
   - eliminarla de este archivo;
   - agregar una entrada en `docs/DONE.md` con el mismo consecutivo;
   - resumir cambios, archivos tocados, comandos ejecutados y validaciones;
   - hacer commit de los cambios.
6. Mantener consecutivos estables: no reutilizar números ya movidos a `DONE`.
7. Agregar tareas nuevas al final, con el siguiente consecutivo disponible.
8. No recrear ni duplicar configuración local ya generada: Auth0/OIDC vive en `.env.auth0.local` creado por `scripts/configure-auth0.sh` (`AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, `AUTH0_API_IDENTIFIER`, `AUTH0_CLAIMS_NAMESPACE`, client IDs, URLs y rutas de secretos); los secretos viven en `.secrets/*` creados por `scripts/bootstrap.sh`, `scripts/generate-local-secrets.sh` o `scripts/configure-auth0.sh`. Las tareas futuras deben consumir esos nombres/archivos y no inventar variables paralelas ni hardcodear secretos.

## Stack de tareas pendientes

### TASK-0002 — Crear el esqueleto del Admin Panel MVP

- **Estado:** PENDING
- **Objetivo:** crear una aplicación web mínima para administración y operación del tenant.
- **Alcance mínimo:**
  - Definir tecnología del frontend dentro del repo.
  - Login OIDC contra Auth0 usando los valores ya generados en `.env.auth0.local` y `.secrets/auth0-admin-client-secret`; no crear variables duplicadas.
  - Layout base con selector de tenant.
  - Módulos placeholder: Tenant Setup, WhatsApp, Knowledge Studio, Operations Desk, Audit.
  - Documentar comandos de desarrollo.
- **Criterio de terminado:** un usuario puede iniciar sesión, ver el layout base y navegar los módulos placeholder.

### TASK-0003 — Implementar Tenant Setup Wizard

- **Estado:** PENDING
- **Objetivo:** permitir configurar tenants sin SQL manual.
- **Alcance mínimo:**
  - Crear tenant.
  - Editar settings del tenant.
  - Configurar horarios, política de escalamiento, PII policy, `no_train` y `max_bot_turns`.
  - Mostrar auditoría básica de cambios.
- **Criterio de terminado:** el wizard crea/configura un tenant usando endpoints REST existentes y deja evidencia en audit logs.

### TASK-0004 — Implementar onboarding WhatsApp/WABA en panel

- **Estado:** PENDING
- **Objetivo:** registrar y validar el canal WhatsApp de un tenant.
- **Alcance mínimo:**
  - Formulario para `business_id`, `waba_id`, `phone_number_id`, `token_ref`, `app_secret_ref`.
  - Health check del canal.
  - Checklist visual de onboarding WABA.
  - Documentar variables y secretos requeridos.
- **Criterio de terminado:** un admin puede registrar el canal y ver su health desde el panel.

### TASK-0005 — Implementar Knowledge Studio MVP

- **Estado:** PENDING
- **Objetivo:** cargar información que alimente la base de conocimiento por tenant.
- **Alcance mínimo:**
  - CRUD/listado de documentos de conocimiento.
  - Editor manual de FAQ/políticas.
  - Carga de archivos hacia object storage o registro de fuente.
  - Estados `draft`, `indexing`, `active`, `failed`.
  - Visibilidad por documento.
- **Criterio de terminado:** un admin puede crear documentos por tenant y verlos aislados por RLS.

### TASK-0006 — Implementar pipeline de indexación RAG

- **Estado:** PENDING
- **Objetivo:** convertir documentos del tenant en chunks vectorizados consultables.
- **Alcance mínimo:**
  - Extracción de texto.
  - Sanitización básica contra prompt injection documental.
  - Chunking con `chunk_index`, `section_path` y `token_count`.
  - Embeddings configurables.
  - Inserción en `knowledge_chunks`.
  - Publicación del documento como `active` solo si el indexado termina.
- **Criterio de terminado:** un documento activo tiene chunks asociados y nunca mezcla datos entre tenants.

### TASK-0007 — Implementar prueba de retrieval y respuesta RAG

- **Estado:** PENDING
- **Objetivo:** permitir que un admin pruebe preguntas contra la base de conocimiento del tenant.
- **Alcance mínimo:**
  - Endpoint `/v1/intents/evaluate` o endpoint equivalente de retrieval test.
  - Mostrar chunks recuperados, score, visibilidad y fuente.
  - Responder solo si hay contexto suficiente.
  - Escalar a humano si no hay evidencia.
- **Criterio de terminado:** el panel muestra una respuesta trazable y los documentos usados.

### TASK-0008 — Implementar Operations Desk mínimo

- **Estado:** PENDING
- **Objetivo:** operar conversaciones y handoff humano desde el panel.
- **Alcance mínimo:**
  - Inbox de conversaciones.
  - Detalle con mensajes.
  - Envío de mensaje outbound.
  - Crear/aceptar handoff.
  - Liberar conversación al bot.
- **Criterio de terminado:** un agente puede tomar una conversación, responder y dejar auditoría.

### TASK-0009 — Implementar gestión de recursos y agenda

- **Estado:** PENDING
- **Objetivo:** permitir configurar recursos y agendar citas.
- **Alcance mínimo:**
  - CRUD/listado de recursos por tenant.
  - Crear cita.
  - Detectar conflictos de recurso.
  - Reprogramar y cancelar citas.
- **Criterio de terminado:** un agente puede gestionar una cita sin violar constraints de agenda.

### TASK-0010 — Implementar service requests y cotización orientativa

- **Estado:** PENDING
- **Objetivo:** capturar intake operativo y generar cotizaciones orientativas.
- **Alcance mínimo:**
  - Crear/editar service request.
  - Campos por vertical.
  - Crear quote.
  - Enviar resumen de quote por canal.
- **Criterio de terminado:** un agente puede registrar una solicitud y asociarle una cotización trazable.

### TASK-0011 — Endurecer auditoría, privacidad y exportes

- **Estado:** PENDING
- **Objetivo:** cubrir mínimos de cumplimiento antes de producción piloto.
- **Alcance mínimo:**
  - Vista de audit logs.
  - Export tenant controlado.
  - Supresión de contacto.
  - Redacción de PII en logs no controlados.
  - Documentar DPA/no-training/retención.
- **Criterio de terminado:** owner/admin puede consultar auditoría y ejecutar flujos básicos de privacidad.

### TASK-0012 — Crear checklist automatizado de go-live por tenant

- **Estado:** PENDING
- **Objetivo:** validar que un tenant está listo para producción controlada.
- **Alcance mínimo:**
  - Verificar tenant activo.
  - Verificar settings.
  - Verificar canal WhatsApp.
  - Verificar documentos activos y retrieval smoke test.
  - Verificar handoff.
  - Verificar auditoría.
  - Generar reporte de readiness.
- **Criterio de terminado:** existe un comando o endpoint que devuelve `ready/not_ready` con razones.
