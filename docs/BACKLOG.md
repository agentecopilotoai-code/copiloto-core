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

_TASK-0029 — Ejecutar y validar drill de restore local (criterio pendiente de TASK-0015): COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0041 — Gestión de equipo y roles del tenant: COMPLETADA. Ver `docs/DONE.md`._

---

## Análisis de brechas para go-live comercial — 2026-05-12

Se revisó el código contra el **flujo clave del paciente/cliente** definido por producto (captación → primer contacto → calificación → orientación → agendamiento → confirmación → reducción de no-show → seguimiento → retención → métricas). El sistema cubre el camino feliz end-to-end en español sobre WhatsApp y Widget Web, con booking guiado, recordatorios automáticos, panel operativo, analítica básica, CRM, campañas y links de pago hospedados. **No está bloqueado por una falla estructural**, pero hay siete brechas funcionales que impiden vender el producto a una empresa real sin trabajo manual sobre el bot:

| # | Brecha detectada | Evidencia en código | Impacto operativo |
|---|------------------|---------------------|-------------------|
| 1 | El bot no califica al lead antes del booking (motivo de consulta, urgencia, primera vez vs. recurrente). Solo clasifica intención. | `app/services/intent_classifier.py` solo devuelve `intent + confidence`; el booking flow salta directo a elegir servicio sin preguntar el motivo. | Se agendan citas equivocadas (servicio incorrecto, urgencias no priorizadas). Resta conversión y aumenta no-show. |
| 2 | El cliente no puede **cancelar ni reprogramar** su cita por WhatsApp. La intención se detecta (`cancel_appointment`, `reschedule_appointment`) pero no hay state machine que la ejecute — solo lo hace un humano desde Operations Desk. | `app/services/rag_orchestrator.py:495` reconoce los intents; `booking_flow.maybe_run_booking_flow` solo opera sobre crear. | Cliente llama o se queda sin cancelar → no-show. Carga manual sobre el agente. |
| 3 | Cuando el cliente responde **"no"** al pedido de confirmación activa, queda `confirmation_status='declined'` y un humano interviene. No hay auto-rebooking guiado por el bot. Reconocido como pendiente en notas de TASK-0035. | `app/services/feedback_flow.py:127` solo escribe el status; el orquestador no lanza un sub-flujo de "elegí otro horario". | Cita declinada se queda en el aire; oportunidad de rescate se pierde. |
| 4 | El feedback **1-2 estrellas no escala** automáticamente a un humano para "service recovery". Se guarda en `app.appointment_feedback` y no genera alerta ni handoff. | `app/services/feedback_flow.py:80` (`maybe_record_feedback`) solo persiste; no toca `conversations.handoff_required`. | Quejas se pierden en silencio. Reputación y recompra dañadas. |
| 5 | El bot no puede enviar **media proactiva** (fotos del local, videos del procedimiento, imagen de promoción activa) durante la orientación. Hay soporte de transporte (`whatsapp.py` acepta `media_url`) pero no hay UI, ni tabla para registrar promociones, ni regla que dispare el envío. | `app/services/whatsapp.py:219` acepta media; no existe `app.media_assets` ni regla de orquestación. | Cliente no ve evidencia visual → más fricción para cerrar el agendamiento. |
| 6 | No hay **segmentos automáticos para retención**: clientes sin visita en N días, citas perdidas sin recuperar, top-spenders. Las campañas existen pero requieren armar el filtro a mano cada vez. | `app/services/campaigns.py:53-185` arma `segment_filter` libre; no hay segmentos predefinidos ni evaluación por reglas (sin visita > X días, total gastado > Y, etc.). | Equipo no usa campañas porque toca pensar SQL implícito. Recompra y reactivación quedan dependientes del agente. |
| 7 | No hay **métrica de funnel** (lead → cita → completada → recurrente) ni atribución por campaña (citas/ingreso generados por una campaña en particular). El panel muestra KPIs sueltos pero no la conversión punta a punta. | `app/api/v1/routes.py:6537+` (`analytics_overview`) calcula KPIs aislados; `campaigns.refresh_campaign_counters` solo cuenta sent/delivered/read. | Gerente no ve el ROI por canal/campaña → no puede invertir. Bloqueo comercial. |

### Lo que **sí** está listo (no requiere ajuste)

- Captura multi-canal (WhatsApp, Widget Web con UTM/referrer en `contacts.lead_source`, importación desde campañas saliente).
- Primer contacto sub-segundo: cascade `template → local LLM → cloud LLM` en `rag_orchestrator.py` + RAG con embeddings reales y answer engine configurable.
- Agendamiento conversacional completo con mensajes interactivos, disponibilidad real desde `resources.capabilities.working_hours`, exclusión por `EXCLUDE USING GIST` en `appointments`.
- Confirmaciones, recordatorios 24h/1h, no-show prompt y post-cita (instrucciones + feedback + rebooking message) — `notifications.py` + gate de plantillas aprobadas en `scheduler.py`.
- CRM básico (etiquetas, notas internas, historial de citas/conversaciones por contacto) + Operations Desk con badges de confirmación/feedback/pago.
- Panel de analítica con KPIs por rango (no-show rate, ingreso, retención 90d, top intenciones/servicios, distribución por origen de lead, top etiquetas).
- Links de pago Stripe/MercadoPago con webhook verificado, badges de estado por cita, envío del link por WhatsApp desde el desk.
- Gestión de equipo + tenant switcher tipo Slack + RLS multitenant + Auth0/MFA + auditoría completa + drill de backup/restore validado.

### Orden de ejecución sugerido (dependencias explícitas)

```
TASK-0042 (calificación previa al booking)        # prerrequisito de cualquier mejora de conversión
    ↓
TASK-0043 (cancelación / reprogramación self-service por WhatsApp)
    ↓
TASK-0044 (auto-rebooking al declinar la confirmación activa)   # depende de TASK-0043
    ↓
TASK-0045 (escalamiento automático en feedback negativo)
    ↓
TASK-0046 (biblioteca de medios + promociones activas)
    ↓
TASK-0047 (segmentos automáticos para retención y reactivación)  # depende de TASK-0042 y CRM
    ↓
TASK-0048 (funnel de conversión y atribución por campaña)        # cierre comercial del MVP
```

---

## Stack de tareas pendientes (post go-live técnico)

---

_TASK-0042 — Calificación conversacional previa al booking: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0043 — Cancelación y reprogramación self-service por WhatsApp: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0044 — Auto-rebooking conversacional al declinar la confirmación activa: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0045 — Escalamiento automático en feedback negativo: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0046 — Biblioteca de medios y promociones activas: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0047 — Segmentos automáticos para retención y reactivación: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0048 — Funnel de conversión y atribución de ingresos por campaña: COMPLETADA. Ver `docs/DONE.md`._

---

## Análisis de readiness vs. flujo clave del paciente/cliente — 2026-05-12 (segunda revisión)

Se confrontó el código contra los 10 estadios del **flujo del paciente/cliente** definidos por producto (captación → primer contacto → calificación → orientación → agendamiento → confirmación → no-show → seguimiento → retención → métricas) y los "drivers de interés" para empresa (más citas, menos ausencias, agenda controlada, recompra, historial, pagos, rendimiento del equipo) y para cliente (rapidez, claridad, facilidad, recordatorios, ubicación, atención personalizada).

**Veredicto:** el MVP cubre **funcionalmente** el camino feliz, pero hay **11 ajustes adicionales** (más allá de TASK-0047 y TASK-0048 ya planificados) que **impiden vender el producto a una empresa real** sin trabajo manual o impacto en conversión. No hay un bloqueo estructural; son ausencias concretas en orientación (identidad del especialista, paquetes), agenda multi-sede, seguimiento programado (recall), calificación financiera/urgencia, cierre de ciclos declinados, alertas operativas, NFR de producción (rate limiting, observabilidad, retención de datos).

### Tabla de brechas

| # | Brecha | Evidencia en código | Impacto |
|---|--------|---------------------|---------|
| 1 | Sin identidad del especialista (bio/foto/especialidad) durante el booking | `app.resources` solo tiene `id, name, code, capabilities`. `booking_flow.py` solo manda `resource_name`. | Cliente no confía → más no-show y baja conversión en clínicas/salones de múltiples profesionales. |
| 2 | Sin multi-sede explícita: el cliente no elige "sede" en el flow | `tenant_settings.location_address/lat/lng/maps_url` son **únicos por tenant**. No existe `app.branches`. El booking lista recursos sin agrupar por sede. | Cadenas con 2+ ubicaciones no pueden operar; cliente recibe la dirección equivocada. |
| 3 | Sin paquetes / planes multi-cita | No hay tabla `treatment_packages`. `appointments` es 1:1 con un servicio. No hay descuento por paquete ni saldo de sesiones. | Imposible vender "5 sesiones de fisioterapia" o "limpieza + blanqueamiento" → recompra estancada. |
| 4 | Sin recall automático ("control en 6 meses") | `service_catalog` no tiene `recall_interval_days`. El scheduler no programa recordatorio para próxima visita tras `completed`. | Ingresos recurrentes (odontología, dermatología, fitness) se pierden si el cliente no agenda solo. |
| 5 | Calificación no captura presupuesto ni urgencia | `qualification_flow.py` soporta `yes_no/single_choice/multi_choice/free_text/number` pero no presets de `budget_tier` ni `urgency_level`. | No se prioriza al cliente VIP ni se fast-tracka un caso urgente → conversión pareja en lugar de selectiva. |
| 6 | El booking no filtra servicios por respuestas de calificación | `booking_flow._present_services` lista todos los `service_catalog.is_active`. Solo se "salta" con `prefilled_service_id` cuando una opción específica trae `service_id`. | Cliente recibe servicios irrelevantes → fricción y abandono. |
| 7 | Sin referido distinto del `lead_source.channel` | `contacts.lead_source` guarda `channel/utm` pero no `referrer_contact_id`. | No se mide qué clientes generan más referidos → no se incentiva la palanca de crecimiento orgánico. |
| 8 | Auto-rebook tras decline no tiene timeout/escalado si el cliente se queda en silencio | `appointment_self_service.start_auto_rebook_flow` arranca el flow, pero si el cliente no responde no hay job de seguimiento ni escalado a humano. | Cita declinada se queda en limbo; se pierde la última oportunidad de rescate. |
| 9 | Feedback negativo escala con handoff pero sin alerta activa al agente | `feedback_flow._escalate_negative_feedback` marca `handoff_required=true` y aparece en pestaña "Quejas" del Desk; no genera notificación push/email ni alerta visible si el agente no está en el panel. | Queja sigue en silencio fuera de horario → reputación y churn. |
| 10 | Maps link no se autogenera desde la dirección | `notifications.py` lee `notification_settings.location_maps_url` configurado a mano. No hay builder desde `location_address`. | Onboarding lento; cliente recibe enlace inválido si el admin lo pega mal. |
| 11 | NFR de producción ausentes: rate limiting de webhooks, métricas Prometheus, política de retención TTL | Sin middleware de throttling, sin `/metrics`, sin job de purgado de `audit_logs`/`domain_events`. | Webhook flood de Meta puede tumbar el API; sin alertas no hay detección de fallas silenciosas; GDPR "derecho al olvido" depende de operación manual. |

### Lo que **sí** está listo (no requiere ajuste adicional)

- Captura multi-canal (WhatsApp + Widget Web con UTM y `lead_source.channel`).
- Primer contacto sub-2s (cascada template → local LLM → cloud LLM con RAG real).
- Calificación conversacional (4+ tipos, persistencia en `contacts.qualification`).
- Agendamiento interactivo (servicio → recurso → fecha → hora con disponibilidad real y `EXCLUDE USING GIST`).
- Confirmación + recordatorios (24h/1h/inmediato) con Maps link + prep notes + active confirmation.
- Auto-rebook al declinar la confirmación (TASK-0044).
- Self-service cancel/reschedule por WhatsApp con política de ventana (TASK-0043).
- Feedback ≤2★ → handoff + etiqueta "Atención prioritaria" + reply empático (TASK-0045).
- Biblioteca de medios + promociones activas durante orientación (TASK-0046).
- CRM básico (etiquetas, notas, historial), Operations Desk con badges, links de pago Stripe/MercadoPago.
- KPIs sueltos en analítica, RLS multitenant, Auth0 + MFA, auditoría, drill backup/restore.

### Orden de ejecución sugerido (dependencias explícitas)

```
TASK-0047 (segmentos automáticos)                          # ya en backlog
    ↓
TASK-0048 (funnel + atribución)                            # ya en backlog
    ↓
TASK-0049 (perfil del especialista en booking)
    ↓
TASK-0050 (multi-sede / branches en booking y confirmación)
    ↓
TASK-0051 (paquetes y planes de tratamiento multi-cita)
    ↓
TASK-0052 (recall automático por servicio tras completar)
    ↓
TASK-0053 (calificación de presupuesto y urgencia + triage)
    ↓
TASK-0054 (filtrado dinámico de servicios por calificación)  # depende de TASK-0053
    ↓
TASK-0055 (tracking de referido entre contactos)
    ↓
TASK-0056 (timeout y escalado del auto-rebook declinado)
    ↓
TASK-0057 (alerta operativa activa en feedback negativo)
    ↓
TASK-0058 (auto-generación del link Google Maps desde dirección)
    ↓
TASK-0059 (rate limiting + circuit breaker en webhooks y LLM)
    ↓
TASK-0060 (observabilidad: métricas Prometheus + alertas básicas)
    ↓
TASK-0061 (política de retención y purgado TTL — GDPR operativo)
```

---

_TASK-0049 — Perfil del especialista (bio/foto/especialidad) visible durante el booking: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0050 — Multi-sede (branches) con selección explícita durante el booking

- **Estado:** PENDING
- **Por qué bloquea:** una cadena con 2+ ubicaciones no puede operar — `tenant_settings.location_address/lat/lng/maps_url` son únicos por tenant. El cliente no elige sede y los recordatorios mandan siempre la misma dirección. Cubrir esto destraba la venta a cadenas (que son los tickets más altos del pipeline).
- **Alcance:**
  - Nueva tabla `app.branches(id, tenant_id, name, code unique per tenant, address, city, state, country, lat, lng, maps_url, phone_e164, timezone, opening_hours jsonb, is_active, sort_order, created_at, updated_at)` con FK al tenant, índice por `(tenant_id, is_active, sort_order)`, RLS, trigger touch.
  - `app.resources` y `app.appointments` ganan columna `branch_id uuid` con FK tenant-scoped (`fk_resources_tenant_branch`, `fk_appointments_tenant_branch`).
  - **Booking flow:** si el tenant tiene >1 branch activa, `booking_flow` inserta un paso nuevo **antes** de `_present_resources`: lista de branches (interactive list); el branch elegido filtra los recursos. Si hay solo 1 branch, se salta el paso (igual que `_present_services` con un único servicio).
  - **Confirmación / recordatorios:** `notifications.py` deja de leer `notification_settings.location_maps_url` para citas con `branch_id != null` y arma las variables `{address, maps_url, phone}` desde la branch correspondiente.
  - **Admin Panel:** módulo nuevo `BranchesModule.jsx` con CRUD (incluye selector de zona horaria, horarios por día, lat/lng con preview de Maps), pestaña en `TenantSetupWizard` para sembrar la primera branch, y filtro de branch en `AnalyticsPanel`/`OperationsDesk`/`CalendarView`.
  - **Migración (sin compat):** un solo branch "Principal" se crea automáticamente con los datos actuales de `tenant_settings.location_*` al sembrar el primer tenant; recursos y citas existentes se asocian a esa branch. Luego se eliminan las columnas legacy en `tenant_settings` (location_*) — siguiendo el mandato del backlog.
- **Criterios de aceptación:**
  - Tenant con 3 branches: cliente en WhatsApp ve "elige sede" (3 botones/lista) → el listado de recursos solo muestra los de esa sede → confirmación trae la dirección y Maps link de esa sede.
  - Tenant con 1 branch: flujo idéntico al actual (sin paso adicional).
  - Analytics permite filtrar KPIs por branch (`?branch_id=...`).
  - Tests: ≥ 14 estáticos: schema, RLS, FKs compuestas, branch picker en booking, branch=1 skip path, notifications usa branch en lugar de tenant_settings, calendar filter, audit `branch.created/updated/deleted`.
- **Notas:**
  - Cada branch tiene `opening_hours` propios; los `working_hours` siguen viviendo en `resources.capabilities` y se intersectan con los de la branch para calcular slots libres.
  - El `widget_config` del canal web puede preseleccionar una branch (atributo `data-branch` en el snippet) para sitios separados por sede.

---

### TASK-0051 — Paquetes y planes de tratamiento multi-cita

- **Estado:** PENDING
- **Depende de:** TASK-0049 (recurso/especialista) opcional, no bloqueante.
- **Por qué bloquea:** el modelo "5 sesiones de fisioterapia", "limpieza + blanqueamiento + control", o "membresía 10 visitas/mes" no se puede vender. `appointments` es 1:1 con `service_catalog`; no hay saldo de sesiones, ni descuento por paquete, ni vencimiento. Sin esto los negocios con LTV alto (estética, fitness, terapias) no convierten.
- **Alcance:**
  - Nuevas tablas:
    - `app.treatment_packages(id, tenant_id, name, description, total_sessions int, validity_days int, price_amount, price_currency, includes_service_ids uuid[], is_active, sort_order, metadata jsonb)`.
    - `app.contact_packages(id, tenant_id, contact_id, package_id, purchased_at, expires_at, remaining_sessions, status check in ('active','exhausted','expired','refunded'), payment_status, payment_amount, payment_currency, notes)`.
    - `app.appointment_package_links(appointment_id, contact_package_id)` para descontar sesión al `status='completed'`.
  - `booking_flow` detecta si el contacto tiene paquetes activos para el servicio elegido y ofrece "Usar 1 de tus 3 sesiones restantes del paquete X" como primer botón antes de pedir pago.
  - Trigger `trg_appointments_consume_package` resta una sesión al pasar a `completed` y marca el paquete `exhausted` cuando `remaining_sessions=0`.
  - **API:** CRUD de packages bajo `tenant_admin_router`, asignación/refund de packages a contactos bajo `tenant_ops_router` (`POST /contacts/{id}/packages`, `DELETE /contacts/{id}/packages/{cp_id}`).
  - **Admin Panel:** módulo nuevo `PackagesModule.jsx` (rol admin), bloque "Paquetes activos" en el perfil de contacto en `ContactsModule.jsx`, badge "Pkg: 3 sesiones" en cada cita en `OperationsDesk.jsx`.
  - **Notificaciones:** al consumir la penúltima sesión, el sistema dispara una `campaign_template` que ofrece la renovación.
- **Criterios de aceptación:**
  - Operador crea paquete "5 sesiones de masaje" → asigna a un contacto → contacto recibe link de pago → al pagar, `contact_packages.status='active'` con `remaining_sessions=5`.
  - Contacto agenda usando el paquete → al completar la cita, `remaining_sessions=4`; en la quinta cita queda en `exhausted`.
  - Tests: ≥ 16 estáticos: schemas, trigger de consumo (idempotente), expiración por `expires_at`, refund libera sesiones, notificación de renovación.
- **Notas:**
  - El precio del paquete vive en `treatment_packages.price_amount`; el pago se hace por el flujo existente de TASK-0040 (Stripe/MercadoPago link).
  - `validity_days` es opcional; si está, el paquete vence aunque queden sesiones.

---

### TASK-0052 — Recall automático ("control en 6 meses") por servicio tras completar

- **Estado:** PENDING
- **Por qué bloquea:** el negocio recurrente (limpieza dental cada 6m, control de dermatología trimestral, mantenimiento de fisioterapia) **depende** de que el cliente vuelva. Hoy, si el cliente no agenda solo, no hay recordatorio: ese ingreso se pierde. `service_catalog` ya tiene `post_service_notes` pero no `recall_interval_days`.
- **Alcance:**
  - Schema:
    - `service_catalog.recall_interval_days int check (recall_interval_days > 0)`.
    - `service_catalog.recall_template_id uuid references app.whatsapp_templates(id)`.
    - `reminder_jobs.kind` extiende el check para aceptar `'service_recall'`.
  - Al pasar una cita a `completed`, un trigger (o un hook en el endpoint que la cierra) inserta un `reminder_job` programado para `completed_at + recall_interval_days`, idempotente por `(appointment_id, kind='service_recall')`.
  - El scheduler envía el template y deja el inbound del cliente listo para entrar al booking (la respuesta dispara `intent_classifier` → `book_appointment` con `prefilled_service_id` del servicio original).
  - **Admin Panel:** `ServiceCatalog.jsx` agrega inputs "Recordatorio de control cada N días" y selector de template; preview de la fecha en que se enviaría tras una cita hipotética.
  - **Cancelación de recall:** si el cliente agenda otra cita del mismo servicio antes de que llegue el recall, el job se cancela (`status='cancelled'`).
- **Criterios de aceptación:**
  - Servicio "Limpieza dental" con `recall_interval_days=180` → cita completada el 1-mar genera un job programado al 28-ago; al disparar, llega el template "¿ya pasó tu control de 6 meses?".
  - Cliente que reagenda el mismo servicio dentro del periodo cancela el recall.
  - Tests: ≥ 10 estáticos: schema, trigger de creación, idempotencia, cancelación al rebook, integración con el scheduler.
- **Notas:**
  - `recall_interval_days` puede dejarse null → no se programa recall (default).
  - El template debe estar `approved` (gate ya existente en `scheduler.py`).

---

### TASK-0053 — Calificación de presupuesto y urgencia con triage automático

- **Estado:** PENDING
- **Depende de:** TASK-0042 (qualification_flow).
- **Por qué bloquea:** la calificación actual no distingue al **lead VIP** (presupuesto > umbral) del frugal, ni al **caso urgente** del rutinario. Resultado: todos los leads compiten parejo por los slots y el agente no sabe priorizar. Esto resta conversión en negocios con backlog (clínicas, abogados, dentistas).
- **Alcance:**
  - `qualification_flow.py`: dos nuevos `kind` presets:
    - `budget_tier` — renderiza una lista con 3-5 rangos configurables por tenant (`< $X`, `$X–$Y`, `> $Y`) y persiste `qualification.budget_tier` con `tier_label` + `tier_value` numérico.
    - `urgency_level` — renderiza yes/no o single_choice con valores normalizados (`emergency, high, normal, low`) → persiste `qualification.urgency_level`.
  - **Triage:** cuando `urgency_level in ('emergency','high')`, el orquestador hace `_do_handoff` con `reason='urgency_triage'` y bypasea el booking; el `OperationsDesk` muestra el caso con badge rojo "🚨 Urgente" en el tope del inbox.
  - **VIP routing:** si `budget_tier.tier_value >= notification_settings.vip_budget_threshold`, el contacto recibe la etiqueta automática "VIP" y aparece en el segmento preconstruido de TASK-0047.
  - **Admin Panel:** `QualificationQuestionsPanel.jsx` gana botones "Insertar pregunta de presupuesto" e "Insertar pregunta de urgencia" que crean las preguntas con los presets correctos. `TenantSetupWizard` agrega input "Umbral VIP" en la pestaña Calificación.
- **Criterios de aceptación:**
  - Cliente responde "Emergencia" → bot saluda con un mensaje de espera y conversación llega al tope del Desk con badge rojo en < 5s.
  - Cliente responde "> $1.000.000" cuando el umbral VIP es 800k → contacto queda con etiqueta "VIP" persistente.
  - Tests: ≥ 10 estáticos: presets registrados, normalización de tier_value, triage handoff, etiqueta VIP, badge UI.
- **Notas:**
  - Las preguntas siguen siendo opcionales por tenant; sin ellas el comportamiento es el actual.
  - La etiqueta "VIP" se idempotenta por `(tenant_id, name)` igual que "Atención prioritaria" (TASK-0045).

---

### TASK-0054 — Filtrado dinámico de servicios en booking según respuestas de calificación

- **Estado:** PENDING
- **Depende de:** TASK-0042 y TASK-0053 (ideal pero no estrictamente).
- **Por qué bloquea:** un cliente que respondió "primera vez" no debería ver "control de seguimiento". Hoy `booking_flow._present_services` lista **todos** los servicios activos; solo el `prefilled_service_id` puede saltarse la pantalla y solo cuando la opción de calificación trae `service_id` exacto.
- **Alcance:**
  - `service_catalog.applies_when jsonb` — reglas en formato `{ all_of: [{key, op, value}] }` (igual operadores que el segmento de TASK-0047). Ejemplos: `{ all_of: [{key:'first_visit', op:'eq', value:true}] }`.
  - `booking_flow._present_services` evalúa `applies_when` contra `conversations.metadata.qualification.answered` y filtra la lista; si tras filtrar queda 1 servicio, se salta a `_present_resources` directo. Si quedan 0, retorna a calificación con una pregunta adicional configurada (`fallback_service_id` opcional) o escala a humano.
  - **Admin Panel:** `ServiceCatalog.jsx` gana un mini-builder de reglas (mismo componente que el de campañas, reutilizable) para definir `applies_when` sin escribir JSON.
- **Criterios de aceptación:**
  - Cliente que respondió `first_visit=true` solo ve servicios con `applies_when.first_visit=true` o sin regla.
  - Si queda un solo servicio aplicable, el flow lo selecciona automáticamente y avanza a recurso.
  - Tests: ≥ 8 estáticos: evaluador de reglas con todos los operadores, filtro en el flow, skip a recurso, escalado cuando 0 matches.
- **Notas:**
  - Si `applies_when` está vacío (default), el servicio se muestra siempre (back-compat dentro del MVP — todavía no hay producción).
  - El evaluador reusa `app/services/segments.py.evaluate_rules` (que se construye en TASK-0047).

---

### TASK-0055 — Tracking de referido entre contactos (referrer_contact_id)

- **Estado:** PENDING
- **Por qué bloquea:** los referidos son la palanca de crecimiento orgánico más rentable en servicios locales (peluquerías, clínicas, dentistas). Hoy no se puede medir "quién trae más clientes" porque `contacts.lead_source` solo guarda canal/UTM. Sin esto no hay programa de incentivos ni tablero de "embajadores".
- **Alcance:**
  - `contacts.referrer_contact_id uuid` con FK auto-referencial tenant-scoped (`fk_contacts_referrer`) y check `referrer_contact_id <> id`.
  - Booking flow agrega una pregunta opcional ("¿quién te recomendó?") solo si `notification_settings.ask_referrer=true`. La respuesta se busca por nombre/teléfono en `contacts` y se asigna; si no se encuentra, se guarda en `contacts.lead_source.referred_by_name` como texto libre.
  - Widget web: el snippet acepta `data-ref=<contact_id>` o `?ref=<contact_id>` en la URL → poblado automáticamente.
  - Endpoint `GET /v1/analytics/referrals?from_date=&to_date=` que devuelve top 20 referidores con `count_referrals`, `appointments_generated`, `revenue_generated`.
  - `AnalyticsPanel`: nueva tarjeta "Top referidores" con foto/nombre del contacto y métricas.
  - `ContactsModule`: bloque "Referidos" en el perfil que muestra a quién refirió y quién lo refirió.
- **Criterios de aceptación:**
  - Bot pregunta "¿quién te recomendó?" → el cliente escribe "María Pérez" → si existe, queda `referrer_contact_id=...`; si no, `lead_source.referred_by_name='María Pérez'`.
  - `/analytics/referrals` devuelve top referidores con su contribución.
  - Tests: ≥ 8 estáticos: schema, FK auto-referencial, endpoint, integración booking, widget read-param.
- **Notas:**
  - El campo `ask_referrer` default `false` — no contamina el flow para tenants que no lo necesitan.
  - El UTM ya existente (`lead_source.utm_*`) se mantiene; el referrer es ortogonal.

---

### TASK-0056 — Timeout y escalado del flujo auto-rebook tras decline silencioso

- **Estado:** PENDING
- **Depende de:** TASK-0044.
- **Por qué bloquea:** TASK-0044 arrancó el auto-rebook al declinar, pero si el cliente recibe los 3 slots y no responde, el flow queda colgado: ni se cancela la cita, ni se escala. La cita declinada se queda en limbo y es un no-show seguro.
- **Alcance:**
  - Al iniciar `start_auto_rebook_flow`, se inserta un `reminder_job` programado a `now() + auto_rebook_timeout_minutes` (default 90) con `kind='auto_rebook_timeout'`, `payload={conversation_id, appointment_id, source='auto_rebook'}`.
  - El scheduler corre este job: si la conversación sigue en mid-flow `self_service` con `source='auto_rebook'` y no hubo nuevos inbound del cliente desde el envío del rebook, ejecuta `_execute_cancel`, emite `bot.appointment_cancelled` con `reason='auto_rebook_timeout'` y `_do_handoff` con `reason='auto_rebook_timeout'`.
  - Si el cliente responde antes del timeout, el job se cancela (`status='cancelled'`) cuando `maybe_run_self_service_flow` procesa el inbound.
  - `TenantSetupWizard` agrega input "Tiempo máximo del auto-rebook" (10–240 min, default 90).
- **Criterios de aceptación:**
  - Cliente recibe slots y no responde en 90 min → cita cancelada, conversación escalada a humano, etiqueta "Necesita seguimiento" asignada.
  - Cliente responde a los 30 min → flow normal, job timeout cancelado.
  - Tests: ≥ 8 estáticos: kind nuevo en check, job programado al arrancar el rebook, cancel al responder, ejecución del timeout, integración con scheduler.
- **Notas:**
  - El timeout es por conversación, no global; un mismo contacto puede tener varios timeouts si hay varias citas en juego.
  - No se reusa la cita declinada: si el cliente vuelve después del timeout, agenda como nuevo.

---

### TASK-0057 — Alerta operativa activa en feedback negativo y quejas

- **Estado:** PENDING
- **Depende de:** TASK-0045.
- **Por qué bloquea:** TASK-0045 deja la queja en la pestaña "Quejas" del Desk, pero si el agente no está mirando el panel (fin de semana, fuera de horario) la queja se duerme. Reputación y churn dependen de respuestas en horas, no en días.
- **Alcance:**
  - Nuevo campo `notification_settings.complaint_alert_channels jsonb` con keys `email` (array), `whatsapp` (array de números), `webhook_url`. Permite combinar.
  - `feedback_flow._escalate_negative_feedback` emite ahora también un `pending_notification` (insert en una tabla nueva `app.operator_alerts(id, tenant_id, kind, payload, status check in ('pending','sent','failed'), attempts, last_error, created_at, sent_at)`).
  - Worker nuevo `app/workers/alerts_worker.py` (o ampliación del scheduler) procesa `operator_alerts.status='pending'`:
    - Email vía SMTP del tenant (config existente o SES con remitente del producto).
    - WhatsApp vía template aprobado `complaint_alert_v1` con variables `{contact_name, rating, comment_preview, conversation_url}`.
    - Webhook genérico POST JSON con HMAC.
  - **Admin Panel:** pestaña Notificaciones del `TenantSetupWizard` agrega bloque "Alertas al equipo" con los 3 canales.
- **Criterios de aceptación:**
  - Feedback de 1★ con email configurado → 2 minutos después llega correo al manager con resumen y link al desk.
  - Si el SMTP del tenant falla, `operator_alerts.attempts` se incrementa con retry exponencial hasta 5 intentos.
  - Tests: ≥ 10 estáticos: schema, helpers de cada canal (mock SMTP, mock webhook), retry, link al desk, registro de la tab.
- **Notas:**
  - El primer canal recomendado es WhatsApp al manager — un humano lee WhatsApp más rápido que email.
  - El payload del webhook lleva HMAC firmado con `notification_settings.alerts_webhook_secret` (almacenado en `.secrets/tenants/{id}/alerts_webhook_secret`).

---

### TASK-0058 — Auto-generación del link de Google Maps desde la dirección

- **Estado:** PENDING
- **Depende de:** TASK-0050 (branches).
- **Por qué bloquea:** hoy el admin pega manualmente el `location_maps_url` y se equivoca el 30% de las veces (pega URL de búsqueda en lugar de pin, formato inválido, etc.). Cliente recibe link que no abre el lugar correcto y se queja.
- **Alcance:**
  - Helper `app/services/maps.py.build_maps_url(lat, lng, address) -> str` que prioriza `lat,lng` si están y cae a búsqueda por dirección url-encoded. Formato canónico `https://www.google.com/maps/search/?api=1&query=...`.
  - Al guardar una branch (TASK-0050) o un tenant con dirección, se construye el `maps_url` automáticamente si el campo viene vacío.
  - Admin Panel: el input "Maps URL" en branch tiene un botón "Generar desde la dirección" + preview que abre el link en una nueva pestaña.
- **Criterios de aceptación:**
  - Branch con `lat=4.65, lng=-74.05, address='Cra 7 #45-20, Bogotá'` → maps_url generado abre el pin correcto en Google Maps mobile y web.
  - Branch sin lat/lng pero con address → maps_url cae a búsqueda por texto.
  - Tests: ≥ 6 estáticos: builder con coords, builder sin coords, encoding correcto de caracteres especiales, integración con branch save, preview UI.
- **Notas:**
  - No se hace geocoding (ahorra API key); se confía en lo que el admin meta. Geocoding queda para una fase posterior.

---

### TASK-0059 — Rate limiting y circuit breaker en webhooks Meta y LLMs externos

- **Estado:** PENDING
- **Por qué bloquea:** el endpoint `/webhooks/whatsapp/{tenant_id}` está abierto a Meta y a Internet (Meta puede reintentar miles de veces ante un 500). Los endpoints del LLM cloud no tienen retry con backoff ni circuit breaker — un Claude/OpenAI lento bloquea el worker. En producción esto significa caída del API ante un flood o una caída del LLM.
- **Alcance:**
  - Middleware `app/main.py.rate_limit_middleware` con bucket por IP + tenant_id (token bucket, refill 60 req/min por IP por defecto, configurable por env `RATE_LIMIT_PER_MIN`). Respuesta `429 Too Many Requests` con header `Retry-After`. Excepción explícita para `/webhooks/whatsapp/*` (Meta debe poder reintentar) que aplica un cap más permisivo de 600/min.
  - Helper `app/services/circuit_breaker.py` con estado `closed/open/half_open`, contador de fallos consecutivos (default 5) y cooldown (default 30s). Se aplica a `cloud_llm_answer.call_claude/call_openai` y a `payment_provider.generate_payment_link`. Cuando está `open`, el orquestador cae automáticamente al siguiente nivel (template → local LLM → cloud LLM).
  - Logs estructurados con `rate_limited=true` y `circuit_open=true` para correlación.
- **Criterios de aceptación:**
  - 200 requests/min al mismo endpoint desde una IP → la #61 recibe 429.
  - 5 fallos consecutivos del cloud LLM → cascada del orquestador omite cloud LLM y usa local; tras 30s prueba 1 request half-open.
  - Tests: ≥ 12 estáticos: middleware registrado, exclusión para webhook Meta, builder de bucket, circuit breaker transitions, integración con cloud_llm_answer, logs.
- **Notas:**
  - El bucket en memoria es suficiente para MVP; si se escala a >2 instancias se cambia a Redis (ya disponible en el compose).
  - Meta puede mandar bursts legítimos; por eso el cap es por tenant y la signature ya filtra requests no firmadas.

---

### TASK-0060 — Observabilidad: métricas Prometheus + alertas básicas

- **Estado:** PENDING
- **Por qué bloquea:** hoy si el bot deja de responder o el LLM cloud cae, nadie se entera hasta que un cliente se queja. Sin observabilidad operativa no hay SLA contractual ni soporte fuera de horario.
- **Alcance:**
  - Endpoint `GET /metrics` con `prometheus_client`, expuesto solo a IPs en `OBSERVABILITY_ALLOWED_IPS` (env). Métricas:
    - `cpi_messages_total{tenant_id, direction, channel, status}`
    - `cpi_response_latency_seconds{tenant_id, tier}` (histogram con buckets 0.5/1/2/5/10s)
    - `cpi_llm_calls_total{provider, status}`
    - `cpi_appointments_total{tenant_id, status}`
    - `cpi_handoff_total{tenant_id, reason}`
    - `cpi_circuit_breaker_state{provider}` (gauge 0=closed 1=half_open 2=open)
    - `cpi_worker_queue_depth{worker}` (gauge)
  - Reglas de Prometheus (archivo `infra/observability/alerts.yaml`) con 6 alertas seed: alta tasa de error (> 5% en 5min), latencia P95 > 5s, queue depth > 1000, circuit breaker open > 2min, scheduler atrasado > 5min, sin métricas durante 3min.
  - `docker-compose.yml` agrega servicio `prometheus` opt-in (perfil `observability`) y Grafana opt-in (sin dashboards detallados en MVP — solo `/metrics` accesible).
- **Criterios de aceptación:**
  - `curl http://api:8000/metrics` desde una IP allowlisted retorna métricas Prometheus.
  - Reglas de alerta cargan en Prometheus sin error.
  - Tests: ≥ 8 estáticos: endpoint registrado, métricas declaradas, IP allowlist, archivo `alerts.yaml` válido (parsing YAML), perfil compose.
- **Notas:**
  - Dashboards de Grafana se entregarán post-MVP — el cierre de esta tarea es solo el contrato de métricas + alertas backend.
  - Las métricas no incluyen PII (sin `phone_e164`, sin contenido del mensaje); solo IDs y agregados.

---

### TASK-0061 — Política de retención y purgado TTL — GDPR operativo

- **Estado:** PENDING
- **Por qué bloquea:** `audit_logs`, `domain_events`, `webhook_events_raw`, `messages`, `conversations` crecen indefinidamente. Una empresa con 30k conversaciones/mes acumula >1M registros/año. Aparte del costo, GDPR exige plazos de retención **definidos** y purgado automático, no manual.
- **Alcance:**
  - Nueva tabla `app.data_retention_policies(tenant_id, entity check in ('messages','conversations','audit_logs','domain_events','webhook_events_raw','reminder_jobs'), retention_days int check (retention_days >= 30), anonymize_instead_of_delete boolean default false, updated_at)`.
  - Worker `app/workers/retention_worker.py` corre 1 vez al día (3am UTC). Por cada (tenant, entity):
    - Si `anonymize_instead_of_delete=false`: `DELETE FROM <entity> WHERE created_at < now() - retention_days * interval '1 day' AND tenant_id = ...` paginado (`LIMIT 5000` por iteración).
    - Si `anonymize_instead_of_delete=true` (caso de `messages` y `conversations`): `UPDATE` que reemplaza `content_text`, `phone_e164` y `display_name` con tokens hash. Mantiene los IDs y las foreign keys.
  - Defaults sembrados al crear tenant: messages 365d, conversations 365d, audit_logs 1825d (5 años, requisito legal), domain_events 90d, webhook_events_raw 30d, reminder_jobs 30d (solo `completed/cancelled/failed`).
  - **Admin Panel:** pestaña Privacidad del `TenantSetupWizard` con tabla editable y preview "se borrarán X registros mañana".
  - Audit log de cada ciclo de purgado: `retention.purged` con `entity, deleted_count, anonymized_count`.
- **Criterios de aceptación:**
  - Tenant con 100k `messages` de más de 365 días → tras una corrida del worker, esos 100k quedan eliminados o anonimizados según la política.
  - Endpoint `GET /v1/tenants/{id}/retention/preview` devuelve cuántos registros se purgarían mañana por entidad.
  - Tests: ≥ 12 estáticos: schema, defaults sembrados, worker paginado, anonimización idempotente, integración con audit, endpoint preview, UI panel.
- **Notas:**
  - `audit_logs` no se puede anonimizar (debe quedar tal cual por compliance); por eso solo soporta DELETE.
  - El worker emite `domain_events('retention.cycle_completed')` con un resumen, útil para que `operator_alerts` (TASK-0057) notifique si una corrida elimina >10% del histórico (señal de error).

---
