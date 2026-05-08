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
