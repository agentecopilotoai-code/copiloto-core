# Backlog operativo de CopilotoIA

Este archivo es la pila única de tareas pendientes para avanzar el producto hacia producción. Cuando el usuario diga **"continúa con la siguiente tarea"**, el agente debe tomar la **primera tarea activa** de este documento, ejecutarla completamente, retirarla de este backlog y moverla a `docs/DONE.md` con evidencia concreta de lo realizado.

---

## ⚠️ MANDATO IRREVOCABLE: ESTE PRODUCTO NO HA SALIDO A PRODUCCIÓN

**Este MVP no tiene ni un solo usuario en producción. No existe deuda técnica que proteger. No hay datos reales que migrar. No hay tenants activos que no romper.**

Por lo tanto, las siguientes reglas son absolutas y no tienen excepciones:

1. **CERO soporte a código legacy.** Si un patrón antiguo existe en el código, se elimina. No se mantiene en paralelo con el nuevo.
2. **CERO compatibilidad hacia atrás.** No hay formatos "viejos" que seguir leyendo. No hay rutas "legacy". No hay columnas "heredadas". Si algo cambió de diseño, el código viejo se borra.
3. **UNA SOLA versión de todo.** Un único esquema de base de datos. Un único formato de configuración. Un único formato de política de escalamiento. Un único tipo de embedding. No existen versiones A y B coexistiendo.
4. **Romper está bien.** Cambiar el esquema sin `IF NOT EXISTS`, cambiar una API sin backward-compat, eliminar una columna sin migración gradual — todo está permitido porque no hay producción que proteger.
5. **Si el código dice "legacy", "compat", "fallback para entornos viejos" o "no romper tenants existentes" → se elimina sin negociación.**

Cualquier tarea futura que agregue código con frases como "mantener compatibilidad con", "soporte para el formato viejo de", "fallback por si acaso", "para no romper" o "idempotente para entornos existentes" **viola este mandato y no debe ejecutarse.**

---

## Protocolo obligatorio para agentes

1. Leer este archivo y seleccionar la primera tarea con estado `PENDING` en el orden en que aparecen (no por número de consecutivo).
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
8. No recrear ni duplicar configuración local ya generada: Auth0/OIDC vive en `.env.auth0.local` creado por `scripts/configure-auth0.sh`; los secretos viven en `.secrets/*` creados por `scripts/bootstrap.sh` o `scripts/generate-local-secrets.sh`. Las tareas futuras consumen esos archivos sin inventar variables paralelas ni hardcodear secretos.
9. **Antes de escribir cualquier línea de código de compatibilidad, releer el mandato de la sección anterior. Si la justificación es "para no romper algo existente" y ese algo no está en producción, la línea no se escribe.**

---

## Análisis de brechas — 2026-05-11

### Lo que el sistema ya tiene (sprint base completo)

| Área | Estado |
|------|--------|
| Infraestructura multitenant (RLS, RBAC, Auth0, MFA) | ✅ Completo |
| Webhook WhatsApp inbound/outbound + worker de entrega | ✅ Completo |
| RAG: indexación, embeddings, retrieval léxico + ANN | ✅ Completo |
| Clasificador de intenciones 3 capas (rule→LLM→fallback) | ✅ Completo |
| Policy engine (risk, ventana 24h, max_turns) | ✅ Completo |
| Agendamiento básico: crear/reprogramar/cancelar citas | ✅ Completo |
| Operations Desk: inbox, handoff, composer | ✅ Completo |
| Knowledge Studio: documentos, RAG test, embeddings reales | ✅ Completo |
| Auditoría, privacidad GDPR, exportes | ✅ Completo |
| Go-live readiness checklist | ✅ Completo |
| CI/CD (GitHub Actions) | ✅ Completo |
| Integración LLM cloud (Claude/OpenAI) | ✅ Completo |

### Código legacy identificado (eliminado en TASK-0032 — referencia histórica)

Durante el desarrollo iterativo se acumularon patrones que deben eliminarse antes de construir encima. Ninguno está en producción, por lo que se eliminan sin migración gradual:

| Archivo | Patrón legacy | Líneas aproximadas |
|---------|--------------|-------------------|
| `infra/postgres/01-schema.sql` | `CHECK (vertical_code IN ('field_service','beauty','pet_grooming'))` en 4 lugares | 31, 190, 207, 326 |
| `infra/postgres/02-seed.sql` | Tenants demo con verticales fijos y CASE hardcodeado | 3–5, 31 |
| `app/api/v1/schemas.py` | `Field(pattern='^(field_service\|beauty\|pet_grooming)$')` en 4 esquemas | 12, 21, 104, 113 |
| `app/services/rag_orchestrator.py` | Fallback `or 'beauty'` hardcodeado | 203 |
| `app/services/policy_engine.py` | Lee campo `risk_keywords` (formato viejo de la política) | 59–74 |
| `app/api/v1/routes.py` | Detecta y acepta formato legacy de política (`handoff_required`, `risk_keywords`) | 3091–3136 |
| `app/api/v1/routes.py` | `KNOWLEDGE_DOCUMENT_COMPAT_DEFAULTS` y proyección de columnas faltantes | 303–352 |
| `app/api/v1/routes.py` | Sincronización dual `max_bot_turns` ↔ `triggers.after_bot_turns` | 769–774 |
| `scripts/bootstrap.sh` | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (migración incremental innecesaria) | 138–241 |
| `scripts/bootstrap.sh` | Conversión de formato viejo `risk_keywords` → `triggers.keywords` en SQL | 142–171 |
| `app/services/rag_indexing.py` | Fallback silencioso a SHA256 cuando falla el proveedor de embeddings | 113–117, 474–477 |
| `app/admin/routes.py` | Ruta `GET /assets/{path}` duplicada "legacy" | 231–233 |
| `admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx` | Dropdown y defaults hardcodeados a los 3 verticales | 128–130, 276, 348 |
| `admin-panel/src/components/modules/operations/OperationsDesk.jsx` | Fallback `\|\| 'field_service'` en 3 lugares | 134, 238, 509 |
| `tests/test_tenant_readiness_static.py` | Test `handles_nullable_legacy_settings` y `passes_with_legacy_handoff_required` | ~44, ~319–333 |
| `tests/test_whatsapp_rag_orchestrator.py` | Test de `risk_keywords` (formato viejo) y comentarios de helpers removidos | 59, 62, 181–195 |
| `tests/test_embedding_providers_static.py` | Test que valida el fallback a SHA256 como comportamiento correcto | ~162–167 |

### Brechas de funcionalidad MVP (TASK-0033 a TASK-0040)

| # | Brecha | Por qué bloquea producción |
|---|--------|---------------------------|
| 1 | Vertical fijo — el producto solo sirve a 3 tipos de negocio | No se puede vender a ningún otro tipo de empresa |
| 2 | Sin catálogo de servicios/precios configurable desde admin | El bot no puede informar precios ni servicios reales |
| 3 | Sin mensajes interactivos WhatsApp (botones/listas) | El booking es solo texto — máxima fricción para el cliente |
| 4 | Booking sin disponibilidad real ni flow guiado completo | El bot pide datos pero nunca completa el agendamiento |
| 5 | Sin templates WhatsApp + confirmaciones automáticas | Sin recordatorios fuera de la ventana 24h de Meta |
| 6 | Sin confirmación activa y reducción de no-show | Alta tasa de ausencias en producción |
| 7 | Sin flujo post-cita configurable | No hay seguimiento, feedback ni recompra |
| 8 | Sin CRM básico (historial, etiquetas, notas de contacto) | Agentes operan sin contexto del cliente |
| 9 | Sin analítica de negocio visible en admin | El manager no puede medir conversión ni KPIs |
| 10 | Sin campañas / mensajes masivos a segmentos | No hay retención ni recompra activa |
| 11 | Sin widget web / captura de leads desde sitio web | Solo WhatsApp como canal de entrada |
| 12 | Sin pagos básicos (link de pago + registro) | No hay cobro anticipado ni seguimiento de pagos |
| 13 | Sin gestión de equipo / cambio de roles desde el panel | Cambiar el rol de un usuario requiere UPDATE en SQL + edición manual en Auth0 |

### Orden de ejecución (dependencias explícitas)

```
TASK-0033 (vertical universal + catálogo de servicios)
    ↓
TASK-0034 (mensajes interactivos WhatsApp)
    ↓
TASK-0030 (booking flow completo con disponibilidad real)
    ↓
TASK-0031 (gestión de plantillas WhatsApp)
    ↓
TASK-0035 (confirmaciones automáticas y recordatorios)
    ↓
TASK-0036 (reducción de no-show y flujo post-cita)
    ↓
TASK-0037 (CRM básico: historial, etiquetas, notas)
    ↓
TASK-0038 (campañas y mensajes masivos)
    ↓
TASK-0039 (widget web y captura de leads)
    ↓
TASK-0040 (links de pago y registro de pagos)
    ↓
TASK-0029 (drill de restore — cierre operacional)
```

---

## Stack de tareas pendientes

---

_TASK-0038 — Campañas y mensajes masivos a segmentos de contactos: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0039 — Widget web y formulario de captura de leads desde sitio web: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0040 — Links de pago y registro de pagos en citas: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0029 — Ejecutar y validar drill de restore local (criterio pendiente de TASK-0015)

- **Objetivo:** los scripts `backup-local.sh` y `restore-local.sh` existen y pasan `bash -n`, pero nunca se ejecutaron contra un Docker Compose real con datos. El criterio de aceptación de TASK-0015 dice "restore local probado con datos demo" y no se cumplió. Esta tarea lo valida antes de go-live.
- **Alcance mínimo:**
  - En un entorno con Docker y Docker Compose disponible:
    1. Levantar el stack con `./scripts/bootstrap.sh`.
    2. Ejecutar `./scripts/backup-local.sh` y verificar dump SQL + manifiesto.
    3. Ejecutar `./scripts/bootstrap.sh --reset --yes --skip-smoke` para limpiar la base.
    4. Ejecutar `./scripts/restore-local.sh <backup-file>` y validar conteos en SQL.
    5. Documentar antes/después en `docs/runbook-go-live-evidence.md`.
  - Si se detectan errores en los scripts, corregirlos.
  - Agregar test de sintaxis bash: `bash -n scripts/backup-local.sh && bash -n scripts/restore-local.sh`.
- **Criterio de aceptación:** restore local ejecutado con datos demo en Docker Compose; conteos documentados; scripts pasan `bash -n`; evidencia commiteada.
- **Dependencias:** requiere Docker. Si el entorno no lo tiene, documentar el bloqueo y no mover a DONE.

---

_TASK-0041 — Gestión de equipo y roles del tenant: COMPLETADA. Ver `docs/DONE.md`._
