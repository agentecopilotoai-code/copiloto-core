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

### TASK-0024 — Integrar LLM cloud (Claude API / OpenAI) como motor de respuesta

- **Estado:** PENDING
- **Objetivo:** añadir una tercera opción al flag `ANSWER_ENGINE` (`cloud_llm`) que use la API de Claude (Anthropic) o la de OpenAI para generar respuestas conversacionales, con prompt caching para reducir costos y latencia.
- **Alcance mínimo:**
  - Agregar `answer_engine=cloud_llm` en `app/core/config.py` con variables `cloud_llm_provider` (`claude`|`openai`), `cloud_llm_model`, `cloud_llm_api_key_ref` (ruta a secreto del tenant o global).
  - Crear `app/services/cloud_llm_answer.py` con soporte para Anthropic SDK (`claude-sonnet-4-6` por defecto) y OpenAI SDK, reutilizando el mismo contrato de retorno que `llm_answer.py`.
  - Implementar prompt caching de Anthropic para el bloque de contexto RAG (marca `cache_control: {“type”: “ephemeral”}`) y registrar el ahorro en `audit_logs`.
  - Exponer métricas de tokens (input/output/cache_hit) en `messages.payload` para trazabilidad de costo.
  - Permitir configurar el proveedor y modelo por tenant en `tenant_settings` (override sobre el valor global).
  - Agregar tests estáticos y unitarios equivalentes a los de `llm_answer.py`.
- **Criterio de aceptación:** con `ANSWER_ENGINE=cloud_llm` y `CLOUD_LLM_PROVIDER=claude`, un mensaje WhatsApp recibe una respuesta generada por Claude con cache hit visible en audit; los costos por token quedan registrados por tenant.
