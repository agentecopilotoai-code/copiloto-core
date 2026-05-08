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

### TASK-0014 — Probar RLS end-to-end con dos tenants reales

- **Estado:** PENDING
- **Objetivo:** validar en PostgreSQL real que ninguna lectura/escritura operativa cruza tenants, incluyendo conocimiento, conversaciones, contactos, audit logs, service requests, quotes, appointments y canales.
- **Alcance mínimo:**
  - Crear fixture o script que levante dos tenants con datos solapados.
  - Ejecutar consultas vía API y, cuando aplique, SQL con `app.tenant_id`/`app.support_mode`.
  - Probar casos negativos: `X-Tenant-Id` incorrecto, JWT sin tenant, soporte sin modo válido y escritura con `tenant_id` ajeno.
  - Documentar evidencia en `docs/DONE.md` y dejar test automatizado.
- **Criterio de aceptación:** suite reproducible en CI/local que falla ante cualquier fuga básica cross-tenant.

### TASK-0015 — Automatizar backup y restore de base de datos y objetos

- **Estado:** PENDING
- **Objetivo:** tener un procedimiento probado para respaldar y restaurar PostgreSQL y archivos de conocimiento/media antes de piloto.
- **Alcance mínimo:**
  - Script `scripts/backup-local.sh` para dump lógico y manifiesto de objetos.
  - Script `scripts/restore-local.sh` para restaurar en una base limpia.
  - Validación post-restore de conteos, tenants, documentos, chunks y audit logs.
  - Documentar equivalentes producción: PITR gestionado, snapshots y replicación/cifrado de bucket.
- **Criterio de aceptación:** restore local probado con datos demo y checklist actualizado.

### TASK-0016 — Enforzar MFA y roles privilegiados en Auth0/Admin Panel

- **Estado:** PENDING
- **Objetivo:** impedir acceso privilegiado sin MFA comprobado y dejar evidencia visible para owner/admin/platform_owner.
- **Alcance mínimo:**
  - Validar claim de MFA/AMR en tokens Auth0 para roles `admin`, `owner` y `platform_owner` cuando Auth0 esté activo.
  - Mostrar en Admin Panel un aviso bloqueante si la sesión privilegiada no tiene MFA.
  - Actualizar `scripts/configure-auth0.sh` o documentación con la política exacta requerida.
- **Criterio de aceptación:** pruebas para token con/sin MFA y documentación de configuración Auth0.

### TASK-0017 — Pruebas integradas de webhook rápido, worker idempotente y trazabilidad outbound

- **Estado:** PENDING
- **Objetivo:** probar el flujo completo webhook → inbox → handoff/outbound → worker con idempotencia y trazas de mensajes.
- **Alcance mínimo:**
  - Test integrado con payloads Meta representativos y duplicados.
  - Verificar respuesta rápida del webhook y procesamiento asincrónico.
  - Verificar que `messages`, `events`, estados de delivery y audit logs enlazan el mismo mensaje.
  - Confirmar que duplicados no reenvían outbound ni duplican inbound.
- **Criterio de aceptación:** suite automatizada que cubre reintentos y duplicados.

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
