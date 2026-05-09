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

## Revisión 2026-05-08 post-DONE

La revisión de `docs/DONE.md` contra el código confirma que el sprint **Admin Panel MVP + Knowledge Ingestion MVP** ya cubre el flujo operativo principal: tenant setup, WhatsApp onboarding/health, carga e indexado de conocimiento, prueba RAG, Operations Desk, Audit Panel y readiness por tenant. También se cerró el faltante crítico de configuración de almacenamiento de archivos de conocimiento en `TASK-0013`.

Para **producción piloto real**, quedan tareas de hardening operacional y pruebas E2E que no deben confundirse con funcionalidad MVP: RLS con dos tenants en base real, backup/restore ensayado, MFA obligatorio verificado desde Auth0, runbook de go-live ejecutable y webhook/load/idempotencia con pruebas integradas.

## Stack de tareas pendientes

### TASK-0015 — Automatizar backup y restore de base de datos y objetos

- **Estado:** PENDING
- **Objetivo:** tener un procedimiento probado para respaldar y restaurar PostgreSQL y archivos de conocimiento/media antes de piloto.
- **Alcance mínimo:**
  - Script `scripts/backup-local.sh` para dump lógico y manifiesto de objetos. ✅ Implementado.
  - Script `scripts/restore-local.sh` para restaurar en una base limpia o recién inicializada con seeds. ✅ Implementado.
  - Validación post-restore de conteos, tenants, documentos, chunks y audit logs. ✅ Implementada en script; pendiente ejecutar restore real.
  - Documentar equivalentes producción: PITR gestionado, snapshots y replicación/cifrado de bucket. ✅ Documentado en `INSTALL.md`.
- **Bloqueo actual:** el entorno de ejecución del agente no tiene Docker/Compose disponible (`command -v docker` no devuelve binario), por lo que no fue posible levantar PostgreSQL/MinIO ni ejecutar un backup+restore real con datos demo. Se validaron sintaxis, compileall y tests estáticos; queda pendiente correr `./scripts/backup-local.sh`, `./scripts/bootstrap.sh --reset --yes --skip-smoke` y `./scripts/restore-local.sh <backup>` en un entorno con Docker.
- **Criterio de aceptación:** restore local probado con datos demo y checklist actualizado.


### TASK-0018 — Runbook de go-live por tenant y smoke test E2E

- **Estado:** PENDING
- **Objetivo:** convertir el checklist de readiness en un runbook ejecutable por tenant antes de activar tráfico real.
- **Alcance mínimo:**
  - Script/CLI que invoque readiness, pruebe RAG, canal WhatsApp, audit logs y operaciones básicas.
  - Plantilla de evidencia por tenant con fecha, responsable, resultado y bloqueos.
  - Integrar instrucciones de rollback: desactivar canal live, pasar a mock, pausar bot o forzar handoff.
- **Criterio de aceptación:** un operador puede ejecutar el runbook sin SQL manual.

### TASK-0019 — Extracción documental fuera del request para PDF/DOCX

- **Estado:** PENDING
- **Objetivo:** procesar archivos binarios comunes sin bloquear la API ni requerir que el admin pegue texto manualmente.
- **Alcance mínimo:**
  - Job/worker de extracción para PDF y DOCX con límite de tamaño y timeout.
  - Estados `draft/indexing/failed/active` coherentes y auditados.
  - Registro de `metadata.extracted_text`, páginas procesadas, errores y checksums.
- **Criterio de aceptación:** PDF/DOCX subidos desde Knowledge Studio quedan listos para indexar o fallan con error accionable.

### TASK-0020 — CI mínimo de calidad para API y Admin Panel

- **Estado:** PENDING
- **Objetivo:** evitar regresiones antes de piloto con una línea base automatizada.
- **Alcance mínimo:**
  - Ejecutar compileall/pytest relevantes para API.
  - Ejecutar install/build/lint del Admin Panel con cache de npm.
  - Publicar artefactos de logs y reporte de tests.
- **Criterio de aceptación:** pipeline documentado y reproducible que bloquee merges con fallos críticos.

### TASK-0021 — Orquestar respuestas automáticas WhatsApp con RAG y handoff seguro

- **Estado:** PENDING
- **Objetivo:** permitir que un cliente pregunte por WhatsApp, por ejemplo “¿qué precio tiene una manicure?”, y que CopilotoIA responda automáticamente con una respuesta clara basada solo en documentos activos/indexados; si no hay evidencia suficiente, debe escalar a un humano sin inventar información.
- **Alcance mínimo:**
  - Crear un orquestador inbound para mensajes WhatsApp de texto que, después de persistir el `inbound`, ejecute retrieval contra `knowledge_chunks` activos del tenant.
  - Reutilizar la lógica de `rank_chunks`/`build_grounded_answer` o extraerla a un servicio compartido para evitar duplicar reglas entre `/intents/evaluate`, readiness y WhatsApp.
  - Si `sufficient_context=true`, crear un mensaje `outbound` con `sender_actor_type='bot'`, encolar `domain_events.message.queued`, auditar la decisión y enviar por el worker existente.
  - Si `sufficient_context=false`, dejar la conversación en `waiting_agent`/`handoff_required=true`, crear o actualizar un handoff abierto y, si existe `escalation_policy.handoff_message`, enviar un mensaje breve indicando que se conectará con una persona.
  - Respetar límites operativos del tenant: `max_bot_turns`, conversación en `human_active`, keywords de humano/reclamo/agente, modo de canal `mock/live`, opt-in/contacto suprimido y deduplicación por `external_message_id`.
  - Incluir trazabilidad en `messages.payload`/`audit_logs`: pregunta, chunks usados, top score, decisión `answered|handoff`, razón y documento fuente.
  - Agregar pruebas integradas con payload Meta representativo: respuesta exitosa por precio de manicure desde CSV indexado, escalamiento por pregunta sin evidencia, duplicado sin doble respuesta y conversación en `human_active` sin intervención del bot.
- **Criterio de aceptación:** al cargar e indexar un documento de precios, un mensaje real o simulado de WhatsApp “¿Qué precio tiene una manicure?” genera una respuesta outbound clara y trazable; si el conocimiento no contiene la respuesta, queda escalado a humano y visible en Operations Desk.

### TASK-0022 — Activación operativa de tenant para go-live desde Admin Panel

- **Estado:** PENDING
- **Objetivo:** dar al owner/admin una forma explícita y auditada de pasar un tenant de `trial` a `active` cuando cumple los prerrequisitos, evitando que el readiness quede bloqueado con “Tenant activo” sin acción disponible.
- **Alcance mínimo:**
  - Exponer en la API una transición controlada de estado de tenant (`trial` → `active`, y rollback operativo `active` → `suspended` o equivalente seguro), validando roles privilegiados y tenant scope.
  - Extender `TenantUpdate`/endpoint o crear endpoint dedicado para cambio de estado con razón obligatoria, auditoría y protección contra estados inválidos.
  - Agregar controles en Tenant Setup o Go-live Readiness para mostrar el estado actual (`trial`, `active`, etc.) y permitir activar cuando el usuario tenga permisos.
  - En Go-live Readiness, mostrar una acción accionable cuando falle `tenant_active`, en vez de solo mostrar “El tenant no existe, no está activo o fue eliminado.”
  - Documentar diferencia entre tenant `status='active'` y canal WhatsApp `account_mode='live'`, porque ambos son necesarios pero no significan lo mismo.
- **Criterio de aceptación:** un tenant como `tenant-odontologia` en `status='trial'` puede activarse desde el panel con auditoría; después de activar, el check “Tenant activo” pasa sin intervención SQL manual.

### TASK-0023 — Corregir readiness y UX de política de handoff/escalamiento humano

- **Estado:** PENDING
- **Objetivo:** asegurar que una política de escalamiento configurada desde el Tenant Setup sea reconocida por Go-live Readiness y que el usuario pueda corregirla desde la UI si falta algo.
- **Alcance mínimo:**
  - Normalizar `escalation_policy` en readiness aunque llegue como `jsonb`, string JSON o estructura parcial.
  - Considerar válida una política con `enabled=true`, `queue`, `triggers.keywords`/`triggers.after_bot_turns`/`triggers.confidence_below` y `handoff_message`, además de formatos legacy como `handoff_required` o `risk_keywords`.
  - Mostrar en Go-live Readiness el motivo exacto del fallo de handoff: política ausente, `enabled=false`, sin cola, sin triggers o sin mensaje de handoff.
  - Agregar un acceso directo desde el check “Handoff humano” hacia la pestaña de escalamiento del Tenant Setup, o una acción rápida para guardar la política mínima recomendada.
  - Cubrir con tests el payload reportado: `{"queue":"default-support","enabled":true,"priority":"normal","triggers":{"keywords":["humano","asesor","agente","reclamo"],"after_bot_turns":5,"confidence_below":0.55},"handoff_message":"Te conecto con una persona del equipo para ayudarte mejor."}` debe pasar readiness.
- **Criterio de aceptación:** la política generada por el Tenant Setup actual pasa el check “Handoff humano”; si no pasa, el panel indica exactamente qué falta y permite corregirlo sin editar JSON ni tocar base de datos.
