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
| 8 | ~~Auto-rebook tras decline no tiene timeout/escalado si el cliente se queda en silencio~~ → **resuelto en TASK-0056**: `start_auto_rebook_flow` inserta un `reminder_job` con `kind='auto_rebook_timeout'`, el scheduler lo despacha y `execute_auto_rebook_timeout` cancela la cita, abre handoff `reason='auto_rebook_timeout'` y tagea al contacto `Necesita seguimiento`. Ver `docs/DONE.md`. | — | — |
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

_TASK-0050 — Multi-sede (branches) con selección explícita durante el booking: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0051 — Paquetes y planes de tratamiento multi-cita: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0052 — Recall automático ("control en 6 meses") por servicio tras completar: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0052 — Recall automático ("control en 6 meses") por servicio tras completar

- **Estado:** DONE
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

_TASK-0054 — Filtrado dinámico de servicios en booking según respuestas de calificación: COMPLETADA. Ver `docs/DONE.md`._

_TASK-0056 — Timeout y escalado del flujo auto-rebook tras decline silencioso: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0055 — Tracking de referido entre contactos (referrer_contact_id): COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0056 — Timeout y escalado del flujo auto-rebook tras decline silencioso

- **Estado:** COMPLETADA — ver `docs/DONE.md`.
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

_TASK-0057 — Alerta operativa activa en feedback negativo y quejas: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0058 — Auto-generación del link de Google Maps desde la dirección: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0059 — Rate limiting y circuit breaker en webhooks Meta y LLMs externos: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0058 — Auto-generación del link de Google Maps desde la dirección

- **Estado:** DONE
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

_TASK-0060 — Observabilidad: métricas Prometheus + alertas básicas: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0061 — Política de retención y purgado TTL — GDPR operativo: COMPLETADA. Ver `docs/DONE.md`._

---

## Análisis de readiness vs. flujo clave del paciente/cliente — 2026-05-13 (tercera revisión, pre go-live comercial)

Se cruzó el código actual (61 tareas completadas, 25.7 k LOC en `app/`, 38 tablas en `infra/postgres/01-schema.sql`, 150 endpoints REST, 1020 tests + 11 skipped) contra el **flujo de 10 estadios del paciente/cliente** definido por producto y contra los "drivers de interés para empresa y cliente". El veredicto general es:

| Estadio del flujo | Estado | Evidencia |
|---|---|---|
| 1. Captación del interesado | ✅ Parcial | WhatsApp (`/v1/webhooks/whatsapp`) + Widget Web (`/v1/web/chat/*`) + import por campañas. Falta Instagram DM / Facebook Messenger y voz. |
| 2. Primer contacto inmediato | ✅ | Cascade `template → local LLM → cloud LLM` con RAG cerrado por tenant. Latencia sub-2 s observada vía `cpi_response_latency_seconds`. |
| 3. Calificación del cliente | ✅ | `qualification_flow.py` con 5 tipos de pregunta + tier de presupuesto/urgencia (TASK-0053). |
| 4. Orientación y educación | ✅ | Biblioteca de medios + promociones activas (TASK-0046), perfil de especialista con bio/foto (TASK-0049). |
| 5. Agendamiento sin fricción | ✅ | Booking conversacional interactivo + multi-sede (TASK-0050) + paquetes (TASK-0051) + filtrado por calificación (TASK-0054). |
| 6. Confirmación y recordatorios | ✅ | Plantillas (TASK-0031), recordatorios 24h/1h, Maps URL auto (TASK-0058). |
| 7. Reducción de no-show | ✅ | Confirmación activa + auto-rebook (TASK-0044) + timeout (TASK-0056) + self-service cancel/reschedule (TASK-0043). |
| 8. Seguimiento posterior | ✅ | Post-cita feedback (TASK-0036), escalamiento negativo (TASK-0045), alerta operativa (TASK-0057), recall automático (TASK-0052). |
| 9. Retención y recompra | ⚠️ Parcial | Campañas + segmentos automáticos (TASK-0047) + atribución (TASK-0048). **Falta:** suscripciones/membresías recurrentes y reactivación por canal alternativo cuando opt-out. |
| 10. Métricas para la empresa | ⚠️ Parcial | 7 endpoints de analytics + Prometheus (TASK-0060). **Falta:** KPIs por agente, digest periódico, vista de DLQ outbound. |

### Drivers de interés cruzados con el código

| Driver para la empresa | Cubierto | Brecha |
|---|---|---|
| Más citas / menos lead perdido | ✅ | — |
| Menos trabajo manual | ✅ | El onboarding aún es manual (templates Meta, canal, primer test). |
| Control de agenda | ✅ | — |
| Menos ausencias | ✅ | — |
| Más seguimiento | ✅ | — |
| Más ventas recurrentes | ⚠️ | Faltan suscripciones; sin notificación de cobro recurrente fallido. |
| Centralizar conversaciones | ✅ | Solo WhatsApp + Web. Sin Instagram/Facebook DM. |
| Historial del cliente | ✅ | — |
| Pagos | ✅ | Stripe + MercadoPago links. Falta cobro automático recurrente. |
| Promociones | ✅ | — |
| Rendimiento del equipo | ❌ | Analytics agrega a nivel tenant; no hay vista por agente. |

| Driver para el cliente | Cubierto | Brecha |
|---|---|---|
| Rapidez | ✅ | — |
| Claridad | ✅ | — |
| Facilidad de agendar sin llamar | ✅ | — |
| Recordatorios | ✅ | — |
| Reprogramar fácil | ✅ | — |
| Ubicación / instrucciones | ✅ | — |
| Atención personalizada | ⚠️ | Tono del bot no es configurable por tenant; falta `personality_prompt`. |

### Brechas reales para go-live comercial — 2026-05-13

| # | Brecha | Evidencia en código | Impacto | Severidad |
|---|--------|---------------------|---------|-----------|
| 1 | Sin doble opt-in con registro de consentimiento auditable | `app.contacts.opt_in_status` se setea por upsert sin trazabilidad; no hay tabla `consent_ledger`. La Ley 1581 exige autorización previa **documentada** con timestamp, base legal, finalidad y canal. | Riesgo regulatorio: una queja a la SIC bloquea la operación. | P0 |
| 2 | Sin tests E2E reales con DB efímera | De 60 archivos de test, 48 son estáticos. Solo `test_rls_multitenant_e2e.py` y un puñado tocan Postgres real. No hay un journey full webhook → respuesta → booking → recordatorio → no-show → feedback. | Regresiones silenciosas en flujos críticos pasan a producción. | P0 |
| 3 | Backups en cloud no automatizados | `scripts/` contiene drill local (TASK-0029) pero no hay job programado de snapshot a S3/RDS con cifrado SSE-KMS ni verificación periódica de integridad. | RPO real desconocido; si el host muere el sábado, ¿qué se pierde? | P0 |
| 4 | Outbound DLQ no observable desde el panel | `event_worker.py` reintenta y persiste `messages.status='failed'`, pero no hay endpoint `GET /v1/outbound/dlq` ni vista en el Admin Panel. El operador descubre el problema cuando el cliente reclama. | Mensajes perdidos sin alarma; reputación dañada. | P0 |
| 5 | Sin runbooks por incidente | Solo existe `docs/runbook-go-live-evidence.md`. Falta: "Meta token expirado", "WABA quality rating bajado", "Postgres replica lag", "rate limit Meta golpeado", "cloud LLM rate limited", "circuit breaker abierto >5 min". | Operación reactiva sin guía; tiempo de respuesta de incidente alto. | P1 |
| 6 | Sin digest periódico (diario/semanal) por email/WhatsApp al manager | `analytics_overview` requiere que alguien entre al panel. No hay job programado que envíe el resumen del día/semana al manager. | El gerente no usa el panel → no ve oportunidades de mejora → churn del SaaS. | P1 |
| 7 | Métricas de rendimiento por agente ausentes | `analytics_*` solo agrega por tenant. No hay vista de "mensajes resueltos por agente", "tiempo medio de respuesta humano", "% handoffs cerrados por agente", "satisfaction por agente". | Manager no puede gestionar al equipo con datos. | P2 |
| 8 | Onboarding tenant requiere intervención manual | `POST /v1/tenant-signup` crea el shell, pero el admin tiene que pegar templates Meta, configurar canal, cargar servicios, calibrar prompt. No hay wizard guiado paso-a-paso con verificación de cada paso. | Cada cliente nuevo consume 4-8h de soporte; bloquea escalado comercial. | P2 |
| 9 | Sin widget JS embebible distribuible | El backend `/v1/web/chat/*` está listo (TASK-0039) pero el cliente recibe solo endpoints. No hay un `widget.js` minificado en CDN que se pegue como `<script>` y renderice el chat. | El cliente pyme no sabe programar React; widget queda inservible para 80% del mercado. | P2 |
| 10 | Tono / personalidad del bot no configurable por tenant | `prompt_templates` permite cambiar prompt entero pero no expone "tono" como atributo de UI. Todos los tenants suenan igual. | Salones premium suenan como talleres económicos → percepción de marca dañada. | P3 |
| 11 | Sin pruebas de carga ni SLA documentado | No hay artefacto Locust/k6 ni `docs/sla.md`. ¿Aguanta 100 msg/s? ¿200? ¿Cuándo se degrada? | Vender con SLA sin medirlo es contraproducente. | P3 |
| 12 | i18n limitada a es-CO; otros mercados sin formato local | `locale='es-CO'` hardcodeado en defaults, monedas y formatos. México, Argentina, Chile usan otra moneda, otra zona horaria y formato de teléfono. | Bloquea expansión regional; el primer cliente fuera de CO requiere refactor. | P3 |
| 13 | Sin canal Instagram DM / Facebook Messenger | Solo `tenant_channels.provider='whatsapp_cloud_api'`. El flujo del producto dice "redes sociales". | Lead que escribe por Instagram queda sin atención. | P3 |
| 14 | Sin suscripciones / membresías recurrentes | `treatment_packages` cubre paquetes finitos. No hay `subscriptions` con cobro recurrente ni notificación al cliente cuando el cobro falla. | Negocios de membresía (gym, dental anual) no pueden vender con el bot. | P3 |
| 15 | Sin páginas legales por tenant (Términos / Privacidad) | No existe `tenant_legal_documents`. El admin no puede subir su T&C y el bot no puede mandarlo al cliente. | Cumplimiento contractual con el usuario final ausente. | P3 |

### Lo que **sí** está listo (no requiere ajuste adicional)

- **Captación:** WhatsApp + Widget Web con `lead_source.channel/utm/referrer`, tracking `referrer_contact_id` (TASK-0055).
- **Primer contacto:** cascade RAG con local LLM (Ollama) + cloud LLM (Claude/OpenAI), circuit breaker por proveedor (TASK-0059), embeddings reales con `pgvector` HNSW.
- **Calificación:** flujo conversacional con 5 tipos de pregunta, tier de presupuesto/urgencia, triage automático.
- **Orientación:** biblioteca de medios (`app.media_assets`) + promociones activas (`app.promotions`) + perfil de especialista (bio/foto/especialidad).
- **Agendamiento:** booking conversacional interactivo (botones/listas), multi-sede (`app.branches`), paquetes multi-cita (`app.treatment_packages`), disponibilidad real con `EXCLUDE USING GIST`.
- **Confirmación:** plantillas WhatsApp sincronizadas con Meta, recordatorios 24h/1h, Maps URL autogenerado desde lat/lng/dirección (TASK-0058).
- **No-show:** confirmación activa + auto-rebook al declinar (TASK-0044) con timeout (TASK-0056) + self-service cancel/reschedule (TASK-0043).
- **Seguimiento:** feedback post-cita, escalamiento ≤2★ con etiqueta "Atención prioritaria" + alerta operativa multicanal (email/WhatsApp/webhook con HMAC) (TASK-0057), recall automático por servicio (TASK-0052).
- **Retención:** campañas a segmentos automáticos (`app.contact_segments` con reglas), atribución de ingresos por campaña (TASK-0048).
- **Métricas backend:** 7 endpoints analytics (overview, conversations, appointments, contacts, funnel, campaigns, referrals) + `/metrics` Prometheus protegido por IP allowlist + 6 reglas de alerta seed.
- **Infraestructura:** RLS multitenant + Auth0/OIDC + MFA obligatoria por rol + auditoría completa (`audit_logs`) + rate limiting por bucket + circuit breaker por proveedor + retención GDPR con anonimización/purgado por entidad (TASK-0061).
- **Pagos:** links Stripe/MercadoPago con webhook firmado, badges de estado por cita.

### Orden de ejecución sugerido (dependencias explícitas)

```
TASK-0062 (consentimiento doble opt-in + ledger auditable)        # P0 — bloqueo regulatorio
    ↓
TASK-0063 (tests E2E con DB efímera para el journey completo)     # P0 — bloqueo de calidad
    ↓
TASK-0064 (backups automatizados a cloud + verificación)          # P0 — bloqueo operacional
    ↓
TASK-0065 (DLQ outbound visible en panel + alerta)                # P0 — bloqueo operacional
    ↓
TASK-0066 (runbooks por incidente)                                # P1
    ↓
TASK-0067 (digest periódico al manager)                           # P1
    ↓
TASK-0068 (KPIs por agente en analytics)                          # P2
    ↓
TASK-0069 (wizard de onboarding self-service con verificación)    # P2
    ↓
TASK-0070 (widget JS embebible distribuido por CDN)               # P2
    ↓
TASK-0071 (tono/personalidad configurable por tenant)             # P3
    ↓
TASK-0072 (pruebas de carga + SLA documentado)                    # P3
    ↓
TASK-0073 (i18n multi-país: locale, currency, timezone)           # P3
    ↓
TASK-0074 (canal Instagram DM / Facebook Messenger)               # P3
    ↓
TASK-0075 (suscripciones / membresías con cobro recurrente)       # P3
    ↓
TASK-0076 (páginas legales por tenant: T&C + privacidad)          # P3
```

---

## Stack de tareas pendientes (pre go-live comercial)

---

_TASK-0063 — Tests E2E con DB efímera para el journey completo del paciente: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0064 — Backups automatizados a cloud con verificación periódica: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0064 — Backups automatizados a cloud con verificación periódica

- **Estado:** DONE
- **Depende de:** TASK-0029 (drill local) — ya completada.
- **Por qué bloquea:** el drill local valida la mecánica pero no protege contra pérdida del host. Sin job programado de backup a un bucket externo cifrado y sin verificación regular, el RPO real es "indefinido". Cualquier cliente serio exige evidencia de backups con prueba reciente.
- **Alcance:**
  - Script `scripts/backup-to-cloud.sh` que: hace `pg_dump --format=custom` comprimido + GPG-encrypted con la clave del tenant operacional, sube a `s3://<bucket>/backups/<env>/<YYYY-MM-DD>/db.dump.gpg`, registra metadata (hash sha256, size, duration) en una tabla `app.backup_runs(id, started_at, finished_at, status, sha256, size_bytes, error, evidence_path)`.
  - Cron en docker-compose: nuevo servicio `backup-worker` con cronicle ligero (`schedule: 0 3 * * *` UTC) que invoca el script.
  - **Verificación semanal:** script `scripts/verify-backup.sh` baja el último backup, restaura a una base efímera (`copilotoia_verify`), corre 3 consultas de sanity (`select count(*) from app.tenants/conversations/messages`) y reporta a `audit_logs(action='backup.verified')`. Si falla, emite `operator_alerts(kind='backup_failure')`.
  - **Retención de backups:** 30 días diarios + 12 mensuales (el primero de cada mes se renombra para no ser purgado). Política implementada en el script con `aws s3 ls` + `aws s3 mv`.
  - **Documentación:** `docs/backup-policy.md` con RPO objetivo (≤24h), procedimiento de restore, y cómo rotar la clave GPG.
- **Criterios de aceptación:**
  - Backup diario corre y deja evidencia en `backup_runs` con `status='ok'`.
  - Restore de prueba semanal pasa los 3 sanity checks; falla → alerta operativa.
  - Backups con >30 días se purgan; mensuales se preservan.
  - Tests: ≥ 8 estáticos: schema de `backup_runs`, parsing de la salida de `pg_dump`, validación del path S3, integración con `operator_alerts`, scheduler hour wiring.
- **Notas:**
  - En MVP no usamos AWS Backup gestionado para no atar el producto a un cloud; el script habla S3 estándar (compatible con MinIO local para tests).
  - La clave GPG vive en `.secrets/backup_gpg_pubkey.asc`; rotación documentada en el runbook.

---

_TASK-0065 — DLQ de mensajes outbound visible en panel + alerta: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0066 — Runbooks operacionales por tipo de incidente: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0067 — Digest periódico (diario y semanal) por email/WhatsApp al manager: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0068 — KPIs de rendimiento por agente en analytics: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0069 — Wizard de onboarding self-service con verificación paso-a-paso: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0070 — Widget JS embebible distribuido por CDN

- **Estado:** COMPLETADA (ver `docs/DONE.md`).
- **Depende de:** TASK-0039 (web widget backend).
- **Por qué bloquea:** el backend del widget está listo, pero el cliente pyme recibe solo endpoints. No sabe programar React. Sin un `<script>` que se pegue y renderice un chat, el widget queda inservible para 80% del mercado.
- **Alcance:**
  - Nuevo paquete `web-widget/` con un build Vite que produce `widget.js` (≤ 30 KB gzipped), `widget.css` (≤ 5 KB), y un snippet de inicialización:
    ```html
    <script src="https://cdn.copilotoia.com/widget.js" data-tenant="<UUID>"></script>
    ```
  - El widget hace `POST /v1/web/chat/start` al cargar, abre un panel flotante en bottom-right, mantiene polling cada 3s a `GET /v1/web/chat/{conversation_id}/messages`.
  - **Customización por tenant:** colores, logo, copy de bienvenida, posición del botón, vienen de `GET /v1/tenants/{tenant_id}/channels/web` (ya existe).
  - **Distribución:** GitHub Action que publica el artefacto a `s3://copilotoia-cdn/widget/v1/widget.js` con cache headers y versionado.
- **Criterios de aceptación:**
  - Pegando el snippet en un HTML estático aparece el chat en <1s.
  - Tests: ≥ 6 (lint + size + smoke en headless Chrome con Playwright).

---

### TASK-0071 — Tono / personalidad del bot configurable por tenant

- **Estado:** COMPLETADA (ver `docs/DONE.md`).
- **Depende de:** TASK-0024 (cloud LLM).
- **Por qué bloquea:** un spa premium y un taller de motos no pueden sonar igual. Hoy todos los tenants comparten el mismo system prompt base. Esto daña la percepción de marca y la conversión en tenants premium.
- **Alcance:**
  - `tenant_settings.bot_personality jsonb default '{"tone":"neutral","formality":"tu","emoji_level":"moderate","custom_persona":""}'`.
  - El builder del system prompt (`rag_orchestrator._build_system_prompt`) inyecta la personalidad como sección dedicada antes del template RAG.
  - **Admin Panel:** pestaña "Voz del bot" con previews: 3 ejemplos de respuesta renderizados con la configuración actual ("Hola, ¿en qué te ayudo?" en formal vs informal vs amigable con emoji).
- **Criterios de aceptación:**
  - Cambiar `tone=playful` produce respuestas notoriamente distintas vs `tone=formal` con el mismo input.
  - Tests: ≥ 6 estáticos: schema del jsonb, builder del prompt incorpora cada campo, preview en admin panel.

---

_TASK-0072 — Pruebas de carga + SLA documentado: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0073 — i18n multi-país (locale, currency, timezone, teléfono): COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0074 — Canal Instagram DM / Facebook Messenger: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0075 — Suscripciones / membresías con cobro recurrente: COMPLETADA. Ver `docs/DONE.md`._

---

### TASK-0076 — Páginas legales por tenant: Términos y Privacidad

- **Estado:** COMPLETADA (ver `docs/DONE.md`).
- **Depende de:** Ninguno.
- **Por qué bloquea:** la Circular SIC 002 exige aviso de privacidad. Hoy no hay forma de que el admin suba su T&C y el bot lo envíe o linkee. Cumplimiento contractual ausente.
- **Alcance:**
  - Tabla `app.tenant_legal_documents(id, tenant_id, kind check in ('terms','privacy','consent'), language, content_md, version, published_at, archived_at)` con append-only por versión.
  - Endpoint público `GET /v1/tenants/{tenant_id}/legal/{kind}` que devuelve la versión publicada vigente como HTML renderizado desde Markdown.
  - El bot puede insertar el link en el opt-in template (`consent_request_v1` de TASK-0062) y en pie de campañas.
  - **Admin Panel:** módulo `legal/LegalModule.jsx` con editor Markdown + preview + control de versión + auditoría de publicaciones.
- **Criterios de aceptación:**
  - Admin sube T&C v1, lo publica, el endpoint devuelve la versión v1.
  - Publica v2, el endpoint devuelve v2 y archiva v1 (sin borrar).
  - Tests: ≥ 8 estáticos: schema, append-only por trigger, render Markdown→HTML seguro, link en template de consentimiento.

---

## Backlog de bugs reportados — 2026-05-13 (auditoría de seguridad)

Se incorporan 25 hallazgos de la auditoría almacenada en `docs/BUGS/BUG01`–`docs/BUGS/BUG25`. **Todos están marcados como `Severidad: High` y validados con evidencia dinámica por el revisor (ChatGPT Codex Security).** Cada hallazgo se convirtió en una tarea con dos fases obligatorias:

1. **Verificación en HEAD:** confirmar si el bug **sigue presente** en el árbol actual. La auditoría se ejecutó contra commits específicos (ver campo `Referencia` por tarea). Tareas posteriores (TASK-0059 rate limit, TASK-0060 observabilidad, TASK-0061 retention, TASK-0062 consent ledger, TASK-0063 E2E, etc.) pueden haberlo mitigado parcial o totalmente. **El agente debe primero auditar el código actual contra el rubric de validación del bug y dejar evidencia escrita** (comando ejecutado, archivos leídos, líneas relevantes, snippet de prueba).
2. **Remediación si persiste:** si la verificación demuestra que el comportamiento vulnerable sigue activo, aplicar el fix mínimo necesario, agregar tests estáticos que cubran el rubric, validar con `uv run pytest` y `uv run ruff check`. Si la verificación demuestra que ya está mitigado, registrar **cómo** se mitigó (tarea o commit que lo cerró) y mover la tarea a `DONE.md` con la evidencia de la verificación.

**Patrón común — autorización tenant-scoped:** BUG03, BUG07, BUG08, BUG11, BUG16, BUG17, BUG23, BUG24, BUG25 son **variantes del mismo bug raíz**: `require_min_role(...)` valida solo `request.state.roles` del JWT y `ensure_tenant_access` acepta cualquier fila en `app.user_tenant_roles` sin exigir el rol mínimo en **ese** tenant. La tarea TASK-0092 (BUG16) propone la fix estructural; el resto se cierra por dependencia. **No fragmentar el fix:** la solución correcta es una sola función `ensure_tenant_role(request, tenant_id, conn, min_role)` que reemplace los dos chequeos y se use en todos los routers tenant-scoped. Cada tarea hija valida que su endpoint específico ya quedó cubierto por esa función.

**Patrón común — visibilidad RAG `agents_only`:** BUG10, BUG12, BUG13 son variantes del mismo bug raíz: la consulta de retrieval no excluye documentos con `visibility='agents_only'` antes de construir la respuesta. La fix estructural va en TASK-0089 (BUG13); las otras dos validan que los caminos cloud y multi-chunk respeten el filtro.

**Patrón común — webhooks Meta/Payments públicos:** BUG04, BUG20, BUG21 tocan la cadena de validación previa a `orchestrate_inbound_message` y el binding `phone_number_id → tenant_channel`. Si TASK-0095 / TASK-0096 / TASK-0097 sobreviven a la verificación, deben resolverse antes que cualquier nueva ingesta (riesgo de cross-tenant data write o forged payment confirmation).

**Orden de ejecución sugerido (P0 → P3 por severidad operativa real):**

```
TASK-0092 (BUG16 — fix raíz de tenant-role mismatch) ── prerrequisito común
    ├── TASK-0079 (BUG03)   media/promotions
    ├── TASK-0083 (BUG07)   templates
    ├── TASK-0084 (BUG08)   service catalog
    ├── TASK-0087 (BUG11)   tenant lifecycle status (+ owner-only gate)
    ├── TASK-0093 (BUG17)   data export (owner real)
    ├── TASK-0099 (BUG23)   Knowledge Studio
    ├── TASK-0100 (BUG24)   tenant profile update + tenant-signup hijack
    └── TASK-0101 (BUG25)   tenant DB membership bypass (cierre)

TASK-0089 (BUG13 — visibilidad RAG raíz)
    ├── TASK-0086 (BUG10)  cloud LLM context filter
    └── TASK-0088 (BUG12)  multi-chunk + local LLM filter

TASK-0080 (BUG04)  payment webhooks fail-closed   ── P0
TASK-0094 (BUG18)  S3 endpoint SSRF                ── P0
TASK-0077 (BUG01)  alert webhook SSRF              ── P0
TASK-0091 (BUG15)  MFA enforcement server-side     ── P0
TASK-0090 (BUG14)  MFA UI no dismissible (depende de TASK-0091)
TASK-0096 (BUG20)  webhook per-change phone_number_id
TASK-0097 (BUG21)  webhook secret unique constraint
TASK-0095 (BUG19)  media proxy host allowlist
TASK-0098 (BUG22)  conversation start no rewrite phone
TASK-0078 (BUG02)  package mutation admin-only
TASK-0082 (BUG06)  Auth0 invite ticket no-leak
TASK-0081 (BUG05)  web widget phone challenge
TASK-0085 (BUG09)  classifier async + timeout
```

Cada tarea cita el archivo del bug y los `Validation rubric` que el agente debe re-ejecutar como check-list. **No se acepta cerrar un bug sin antes ejecutar la verificación rubric-por-rubric en el código actual y dejar el resultado escrito en `DONE.md`.**

---

### TASK-0077 — Verificar y corregir SSRF en webhooks de alertas operativas (BUG01)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG01` — commit `517add2` (TASK-0057) — severidad High, SSRF.
- **Depende de:** —
- **Resumen del hallazgo:** `notification_settings.complaint_alert_channels.webhook_url` se persiste en `PATCH /v1/tenants/{tenant_id}/settings` sin validación. El worker de alertas (`app/services/operator_alerts.py::_send_webhook_channel`) hace `httpx.AsyncClient.post(url, ...)` desde el backend sin allowlist, sin enforce HTTPS, sin bloquear loopback/RFC1918/link-local/169.254.169.254 ni redirects. Un admin tenant puede usar el sink para POSTear a servicios internos.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `app/api/v1/routes.py::patch_settings` (≈ línea 35 del bug) y confirmar si `notification_settings` sigue aceptándose sin schema Pydantic estricto.
  2. Re-leer `app/services/operator_alerts.py::normalize_alert_channels` y verificar si **hoy** valida scheme/host/IP del `webhook_url`.
  3. Re-leer `_send_webhook_channel` y comprobar si `httpx.AsyncClient` se construye con `transport`/`limits` que bloqueen redirects + private IPs.
  4. Buscar en el repo (`grep -rn "webhook_url" app/`) cualquier mitigación introducida después del commit `517add2` (puede haber llegado vía TASK-0059, TASK-0061 o un fix posterior).
  5. Documentar el resultado: bug presente / bug mitigado / mitigado parcialmente (con qué brecha residual).
- **Fase 2 — remediación (si persiste):**
  - Validar `webhook_url` en el helper compartido `app/services/url_guard.py` (crear si no existe): exige `https://`, resuelve DNS, bloquea `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, `fc00::/7`, `fe80::/10`, hostname `metadata.google.internal`, hostname `localhost`.
  - Aplicar la validación en `normalize_alert_channels` (rechaza al guardar) **y** justo antes del POST (defensa en profundidad, por si la DB trae un registro viejo).
  - Construir `httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5))` y validar `response.next_request` para detener redirects manuales.
  - `notification_settings` debe validarse vía Pydantic `NotificationSettingsUpdate` en lugar de aceptar `dict` libre.
- **Criterios de aceptación:**
  - Tests estáticos ≥ 8 que prueben: rechazo de `http://`, rechazo de loopback, rechazo de `169.254.169.254`, rechazo de redirect-to-private, sanitización en PATCH `/settings`, sanitización en helper compartido, integración con el dispatcher, evento de auditoría `webhook.rejected_unsafe_url`.
  - Una prueba dinámica documentada en `DONE.md` que muestre rechazo de `http://127.0.0.1:6379/`.

---

### TASK-0078 — Verificar y corregir mutaciones de paquetes pagados accesibles a `agent` (BUG02)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG02` — commit `177389d` (TASK-0051) — severidad High, RBAC + tampering financiero.
- **Depende de:** —
- **Resumen del hallazgo:** los endpoints de asignación, patch y refund de `contact_packages` se montaron en `tenant_ops_router` (rol mínimo `agent`). Los schemas aceptan `payment_status='paid'` y `payment_amount=0`. Un agente puede otorgar paquetes pagados, marcar refunds y vaciar saldo de sesiones sin pasar por la pasarela de pago.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "contact_packages\|treatment_package" app/api/v1/routes.py` para listar los endpoints actuales y el router al que están montados.
  2. Confirmar si `POST /v1/contact-packages`, `PATCH /v1/contact-packages/{id}`, `DELETE /v1/contact-packages/{id}` siguen en `tenant_ops_router` o ya se movieron a `tenant_admin_router`.
  3. Revisar `app/api/v1/schemas.py` para `ContactPackageCreate/Patch`: ¿`payment_status` sigue siendo campo libre del cliente?
  4. Buscar en `DONE.md` si TASK-0075 (suscripciones) u otra introdujo el flujo "el `payment_status` solo lo escribe el webhook firmado del proveedor".
- **Fase 2 — remediación (si persiste):**
  - Mover los endpoints de mutación de paquetes a `tenant_admin_router` (mínimo `admin`) o crear un `tenant_manager_router` específico.
  - En los schemas, restringir `payment_status` a `unpaid` para writes del cliente; la transición a `paid` solo ocurre en el handler del webhook de pago (`POST /v1/webhooks/payments/{provider}`) con firma verificada.
  - El refund (`DELETE` que pone `status='refunded'`) requiere `admin` **y** auditoría con `action='contact_package.refunded'` capturando user_id, monto, motivo.
- **Criterios de aceptación:**
  - Test estático que muestra el router montado en `tenant_admin_router`.
  - Test que un POST con `payment_status='paid'` desde un cliente externo es rechazado / sobreescrito a `unpaid`.
  - Test de auditoría que confirma la entrada `contact_package.refunded` por `admin`.

---

### TASK-0079 — Verificar y corregir media/promotions con admin no tenant-scoped (BUG03)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG03` — commit `7ca68ea` (TASK-0046) — severidad High, RBAC cross-tenant.
- **Depende de:** TASK-0092 (fix raíz `ensure_tenant_role`).
- **Resumen del hallazgo:** los CRUD de `media_assets` y `promotions` se montaron en `tenant_admin_router` y validan acceso al tenant vía `ensure_tenant_access` (acepta cualquier membresía). Un usuario con JWT `admin` y membresía `viewer/agent` en el tenant B puede listar, subir y borrar media + promociones de B.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer la sección de routes que cubre `/tenants/{tenant_id}/media` y `/tenants/{tenant_id}/promotions`.
  2. Confirmar si la dependencia es `Depends(ensure_tenant_role(min_role='admin'))` (post TASK-0092) o todavía `Depends(ensure_tenant_access(...))`.
  3. Reproducir el escenario en test estático con un mock de JWT scope A + DB membership B viewer.
- **Fase 2 — remediación (si persiste):**
  - Sustituir la dependencia por la helper unificada de TASK-0092.
  - Agregar test que el caller con rol DB < admin en el tenant target reciba 403 incluso si su JWT trae `roles=['admin']`.
- **Criterios de aceptación:**
  - Test estático que cubre el rubric: JWT admin A + DB viewer B → 403 en GET/POST/PATCH/DELETE de `media` y `promotions`.

---

### TASK-0080 — Verificar y corregir webhooks de pago fail-open sin firma (BUG04)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG04` — commit `3201a6c` (TASK-0040) — severidad High, falsificación financiera.
- **Depende de:** —
- **Resumen del hallazgo:** `POST /v1/webhooks/payments/{provider}` inicializa `signature_ok = True` y solo verifica firma si el tenant tiene `webhook_secret_ref` configurado. Si el secreto falta, cualquier payload anónimo con un UUID de `appointment` válido marca la cita como `payment_status='paid'` y dispara mensajería de confirmación. La UI admin explícitamente etiqueta el secret como "recomendado" y muestra "sin verificación de firma".
- **Fase 1 — verificación en HEAD:**
  1. Re-leer el handler del webhook de pago en `app/api/v1/routes.py` y el helper `verify_stripe_signature` / `verify_mercadopago_signature` que llama.
  2. Confirmar si **hoy** el handler rechaza la request con 401/403 cuando el tenant no tiene `webhook_secret_ref`.
  3. Confirmar si la UI del módulo de pagos sigue permitiendo activar un provider sin secret.
- **Fase 2 — remediación (si persiste):**
  - `signature_ok` debe inicializar en `False`. Sin secret configurado → 503 `payment.webhook_unconfigured` (no aceptar nada).
  - El módulo admin de pagos debe exigir el secret antes de habilitar el provider (front + Pydantic).
  - Test estático que un payload sin header `Stripe-Signature` recibe 401 incluso si el tenant tiene secret.
  - Test estático que un tenant sin secret rechaza el webhook con 503 (no procesa el appointment).
- **Criterios de aceptación:**
  - Test PoC: payload Stripe `checkout.session.completed` falso con UUID válido → la cita NO se marca `paid`.
  - Entrada de auditoría `payment.webhook_rejected` cuando se rechaza.

---

### TASK-0081 — Verificar y corregir impersonación por teléfono en el widget web (BUG05)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG05` — commit `eb786e8` (TASK-0039) — severidad High, suplantación de contacto.
- **Depende de:** —
- **Resumen del hallazgo:** `POST /v1/web/chat/start` acepta `phone` opcional del browser anónimo y, si coincide con un `contact` existente del tenant, reusa ese `contact_id` para crear la conversación. El orquestador procesa los mensajes como si fueran del contacto real: un atacante que conoce el teléfono del cliente puede responder "no" a la última confirmación o registrar feedback en su nombre.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `web_chat_start` y `web_chat_message` en routes; revisar si el contacto se reusa por `phone` o se crea uno nuevo aislado por `widget_session_token`.
  2. Confirmar si el flujo de orquestación distingue entre "contacto verificado" (WhatsApp inbound con MSISDN validado por Meta) y "contacto web" (no verificado).
- **Fase 2 — remediación (si persiste):**
  - El widget web NO debe reusar un contacto existente por `phone` solo. Crear siempre un `contact` nuevo de canal `web` con `wa_id=null`. La reconciliación (merge web ↔ WhatsApp) ocurre cuando el cliente prueba propiedad del MSISDN (OTP).
  - Si se requiere captura de teléfono, encolar un `phone_verification_challenge` (OTP por SMS/WhatsApp) y solo entonces hacer el merge.
  - El orquestador no debe ejecutar acciones contact-scoped (cancelar cita, registrar feedback) si el contacto está en estado `unverified_web`.
- **Criterios de aceptación:**
  - Test estático que `phone` enviado por el widget NO altera ni reusa ningún `contact` existente.
  - Test que mensaje "no" desde un widget sin OTP NO cambia `confirmation_status` de ninguna cita pre-existente.

---

### TASK-0082 — Verificar y corregir filtración de Auth0 reset tickets en invitaciones (BUG06)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG06` — commit `500953d` (TASK-0041) — severidad High, account takeover.
- **Depende de:** —
- **Resumen del hallazgo:** el endpoint de invitación de miembros (`POST /v1/tenants/{id}/users` o equivalente) acepta cualquier email. Si el email no existe en `app.users`, el backend llama a Auth0 `/tickets/password-change` usando el email como pivote. Auth0 devuelve un password-reset ticket válido para cualquier cuenta Auth0 existente que comparta ese email — incluyendo cuentas plataforma/soporte/admin. El backend retorna el ticket URL al frontend, que lo muestra para copiar.
- **Fase 1 — verificación en HEAD:**
  1. Localizar el helper de invitación (`grep -rn "tickets/password-change\|invite_user" app/`).
  2. Confirmar si **hoy** la invitación crea/binda un Auth0 user nuevo por `user_id` antes de generar el ticket, o si todavía pivotea por email.
  3. Confirmar si el ticket URL se propaga al admin que invita o si se envía directamente al destinatario por email.
- **Fase 2 — remediación (si persiste):**
  - Crear primero un usuario Auth0 (`POST /api/v2/users`) con email y `email_verified=false`. Capturar el `user_id` devuelto.
  - Generar el ticket con `user_id` (no con email) y enviarlo **directamente** al destinatario vía Auth0 Email (template `welcome`) o vía nuestro propio mail. La API NO devuelve el ticket URL al inviter.
  - Si el email ya existe en Auth0, retornar 409 "user already exists" sin generar ticket. El admin debe usar el flujo "add existing user to tenant" (que requiere que el user-target acepte por su propio inbox).
- **Criterios de aceptación:**
  - Test estático: la respuesta de invitación NO incluye el ticket URL.
  - Test estático: si el email ya existe en Auth0 (mock), 409.
  - Test que el evento de auditoría `user.invited` capture `auth0_user_id` (no email plano).

---

### TASK-0083 — Verificar y corregir templates de WhatsApp cross-tenant (BUG07)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG07` — commit `3d62d3f` (TASK-0031) — severidad High, RBAC cross-tenant.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** los endpoints `GET/POST/PATCH/DELETE /v1/tenants/{id}/whatsapp/templates` y `POST .../sync` están en `tenant_admin_router`. Un usuario con JWT `admin` para A y membresía cualquiera para B puede listar, crear, editar, sincronizar y **borrar templates de B en Meta** — golpeando la mensajería del otro tenant.
- **Fase 1 — verificación en HEAD:**
  1. Localizar las rutas `whatsapp/templates` y su dependency stack.
  2. Confirmar si ya usan la helper de TASK-0092.
- **Fase 2 — remediación (si persiste):**
  - Aplicar `ensure_tenant_role(min_role='admin')` a todos los endpoints de templates.
  - El `sync` y el `delete` deben emitir `action='whatsapp_template.deleted_remote'` en auditoría con el `meta_template_name` y el `user_id` para forense.
- **Criterios de aceptación:**
  - Test: JWT admin A + viewer B → 403 en cualquier verb sobre `/tenants/B/whatsapp/templates`.
  - Test que el sync con Meta solo se ejecuta cuando el rol DB en el tenant target es `admin` o superior.

---

### TASK-0084 — Verificar y corregir service catalog admin no tenant-scoped (BUG08)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG08` — commit `39f5c49` (TASK-0033) — severidad High, RBAC cross-tenant.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** los endpoints `/v1/tenants/{id}/services` usan `require_min_role('admin')` + `ensure_tenant_access`. Un caller con JWT admin de A y membresía agent de B puede leer, crear, actualizar, desactivar y reordenar el `service_catalog` de B — afectando precios y disponibilidad mostrados al cliente final.
- **Fase 1 — verificación en HEAD:**
  1. Localizar `service_catalog` routes y confirmar dependencias.
  2. Verificar si TASK-0092 los cubrió.
- **Fase 2 — remediación (si persiste):**
  - Aplicar `ensure_tenant_role(min_role='admin')`.
  - Agregar tests que cubran el rubric: list/create/update/deactivate/reorder con la combinación JWT A admin + DB B agent → 403.
- **Criterios de aceptación:**
  - Test estático del rubric completo en `test_service_catalog_authorization.py`.

---

### TASK-0085 — Verificar y corregir bloqueo del event loop por classifier LLM cloud (BUG09)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG09` — commit `bced236` (TASK-0024 / clasificador 3 capas) — severidad High, DoS.
- **Depende de:** —
- **Resumen del hallazgo:** `app/services/intent_classifier.py::_llm_classify` (o equivalente) instancia clientes **síncronos** Anthropic/OpenAI y llama `create()` desde dentro de una función `async`. El timeout configurado no se pasa al SDK. Cada mensaje WhatsApp que no matchea regla regex de alta confianza bloquea el event loop hasta que el proveedor cloud responde o cuelga. Un atacante puede inundar el webhook con mensajes ambiguos para tumbar el servicio.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `app/services/intent_classifier.py` y comprobar si usa `AsyncAnthropic` / `AsyncOpenAI` con `await`.
  2. Confirmar si `timeout_seconds` configurado en `tenant_settings` se propaga al SDK.
  3. Confirmar si TASK-0059 (rate limit + circuit breaker) ya envuelve estas llamadas.
- **Fase 2 — remediación (si persiste):**
  - Migrar a `AsyncAnthropic(api_key=..., timeout=settings.cloud_llm_timeout)` y `AsyncOpenAI(...)` con `await client.messages.create(...)`.
  - Si por alguna razón se mantiene un cliente síncrono (no recomendado), ejecutar en `asyncio.to_thread` con `asyncio.wait_for(timeout=...)`.
  - El classifier debe correr **después** del dedup/idempotency/rate-limit gate para que un attacker no llegue al sink LLM.
- **Criterios de aceptación:**
  - Test estático que confirma uso de `AsyncAnthropic`/`AsyncOpenAI` y `timeout` parametrizado.
  - Test que un mensaje que rompe el LLM (provider mock que `raise asyncio.TimeoutError`) cae en `fallback` sin colgar el event loop.

---

### TASK-0086 — Verificar y corregir leak de chunks `agents_only` al LLM cloud (BUG10)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG10` — commit `197c6ab` (TASK-0024 cloud LLM) — severidad High, fuga de datos internos al proveedor externo.
- **Depende de:** TASK-0089 (fix raíz visibility).
- **Resumen del hallazgo:** el camino `cloud_llm` (standalone y cascade fallback) construye el contexto con TODOS los matches sobre threshold sin excluir `visibility='agents_only'`. El contenido interno del tenant termina enviado a Anthropic/OpenAI y reflejado al cliente final.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `app/services/rag_orchestrator.py::_build_context` y `build_cloud_llm_answer`.
  2. Confirmar si la query base ya filtra `kd.visibility != 'agents_only'`.
- **Fase 2 — remediación (si persiste):**
  - El filtro se aplica en la consulta SQL del retrieval (no en post-filter) — depende de TASK-0089.
  - Test que el path cloud_llm con un chunk `agents_only` ranqueado #1 lo descarta y no se incluye en el prompt enviado al SDK.
- **Criterios de aceptación:**
  - Test estático que captura el `messages` payload enviado al SDK (con stub) y verifica ausencia del texto agents_only.

---

### TASK-0087 — Verificar y corregir tenant lifecycle status mutable por admin (BUG11)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG11` — commit `562fa70` — severidad High, bypass del control de plataforma.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** el commit agrega `status` a `TenantUpdate` y lo persiste vía `PATCH /v1/tenants/{tenant_id}` con `require_min_role('admin')`. Un admin tenant puede mover su propio tenant de `trial` a `active`, o revertir una suspensión, sin pasar por el gate `platform_owner`.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `TenantUpdate` Pydantic y `update_tenant_record`.
  2. Confirmar si `status` se separa hoy en un campo `platform-only`.
- **Fase 2 — remediación (si persiste):**
  - `TenantUpdate` (tenant-admin) NO acepta `status`. Crear `PlatformTenantUpdate` separado con `status` y montarlo en `platform_admin_router` (rol mínimo `platform_owner`).
  - `update_tenant_record` recibe un flag `actor_is_platform_owner` y rechaza `status` si es False.
- **Criterios de aceptación:**
  - Test: PATCH tenant admin con `{status: 'active'}` → 422 (campo no permitido) o ignorado.
  - Test: el mismo PATCH desde `platform_owner` lo persiste.

---

### TASK-0088 — Verificar y corregir respuestas RAG que incluyen multiple chunks sin filtro de visibilidad (BUG12)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG12` — commit `c8e7238` — severidad High, fuga al cliente final.
- **Depende de:** TASK-0089.
- **Resumen del hallazgo:** el template-based answer ahora concatena todos los chunks con score suficiente (no solo el best), y el `local_llm` builder hace lo mismo. Un chunk `agents_only` rankeado #2 ahora aparece en la respuesta saliente sin haber pasado un filtro de visibilidad.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `build_grounded_answer` y `_build_local_llm_context`.
  2. Confirmar si los chunks que entran ya están pre-filtrados por la query SQL.
- **Fase 2 — remediación (si persiste):**
  - El filtro vive en la query SQL (fix raíz TASK-0089). Los builders de respuesta no deben aceptar chunks marcados `agents_only` ni siquiera si llegan; assert defensivo + log si llega uno.
- **Criterios de aceptación:**
  - Test estático: builder al que se le pasa un chunk `agents_only` lo descarta y emite `log.warning('agents_only.leaked_into_builder')`.

---

### TASK-0089 — Verificar y corregir fuga de `agents_only` en RAG WhatsApp (BUG13 — fix raíz)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG13` — commit `760284a` (TASK-0014 RAG inicial) — severidad High, fuga al cliente final.
- **Depende de:** —
- **Resumen del hallazgo:** la consulta de retrieval del orquestador WhatsApp filtra solo `tenant_id` + `status='active'`. NO excluye `visibility='agents_only'`. Como el builder devuelve un excerpt del best chunk, cualquier contacto WhatsApp puede recibir contenido staff-only (políticas internas, precios reservados, instrucciones de escalado).
- **Fase 1 — verificación en HEAD:**
  1. Re-leer la query SQL del orquestador (ANN + lexical) y `build_grounded_answer`.
  2. Confirmar si TASK-0024 o posterior agregó `and kd.visibility <> 'agents_only'` o equivalente en el `WHERE`.
- **Fase 2 — remediación (si persiste):**
  - Agregar el filtro en la query SQL para los tres caminos: lexical (`pg_trgm`), ANN (HNSW `pgvector`), y la fusion. El filtro vive en el `JOIN` con `knowledge_documents`.
  - Path "admin RAG test" (Knowledge Studio) puede pasar `include_agents_only=true` solo cuando el caller tiene rol `admin`.
  - Definir constante `END_USER_VISIBILITY = ('public', 'tenant')` y usarla en todas las queries que sirven al cliente final.
- **Criterios de aceptación:**
  - Reproducir el rubric dinámico: agents_only chunk → respuesta saliente NO lo contiene.
  - Tests ≥ 6 estáticos: query lexical, query ANN, query fusion, admin RAG test con override explícito, builder defense-in-depth (TASK-0088), cloud LLM defense (TASK-0086).

---

### TASK-0090 — Verificar y corregir MFA banner dismissible en UI admin (BUG14)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG14` — commit `ff7c0dc` — severidad High, MFA bypass.
- **Depende de:** TASK-0091 (server-side enforcement).
- **Resumen del hallazgo:** `_session_mfa_required()` sigue reportando `true` para admin/owner/platform_owner sin MFA, pero la UI ahora renderiza la app detrás del overlay y ofrece un botón "Continuar sin MFA" que solo oculta el banner. Como el proxy BFF y los routers Core no exigen `require_mfa_for_privileged`, el usuario hace acciones privilegiadas sin segundo factor.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `admin-panel/src/components/.../MfaOverlay.jsx` (o el componente equivalente) y confirmar si el botón "Continuar sin MFA" sigue existiendo.
  2. Confirmar si el proxy `admin/api/core` rechaza requests con `mfa_required=true`.
- **Fase 2 — remediación (si persiste):**
  - El overlay MFA debe ser un **gate bloqueante** (no dismissible). No renderizar children mientras `mfa_required=true && mfa_verified=false`.
  - El proxy BFF (`admin-panel/server/...` o equivalente FastAPI) debe retornar 403 si la sesión está flagged.
  - Esto es defensa de UX; la defensa real es TASK-0091.
- **Criterios de aceptación:**
  - Test E2E (Playwright) que con MFA pendiente NO se puede ejecutar PATCH desde la UI.
  - Test que el proxy rechaza con 403 una request privilegiada cuando `mfa_required=true`.

---

### TASK-0091 — Verificar y corregir MFA enforcement nunca aplicado en routers Core (BUG15)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG15` — commit `3ba2e2f` — severidad High, MFA bypass server-side.
- **Depende de:** —
- **Resumen del hallazgo:** la dependency `require_mfa_for_privileged` existe y funciona aisladamente, pero **no está importada ni montada en ningún router productivo**. Los routers privileged dependen solo de `authenticate_request` + role check. El BFF reenvía cualquier sesión admin activa sin chequear `_session_mfa_required`. Tests cubren el helper en aislamiento pero no su integración.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "require_mfa_for_privileged" app/`.
  2. Confirmar a qué routers está adjuntada hoy (si a alguno).
  3. Confirmar política: ¿qué endpoints son "privileged"? Mínimo: tenant settings PATCH, channels PUT, knowledge document PATCH, tenant-signup, platform admin completo.
- **Fase 2 — remediación (si persiste):**
  - Adjuntar `Depends(require_mfa_for_privileged)` en `tenant_admin_router` y `platform_admin_router` a nivel de router (no por endpoint).
  - El proxy BFF debe propagar el header `X-Session-MFA-Verified` y el dependency lo lee de `request.state.session`.
  - Tests de integración que cada endpoint privileged rechace una sesión `mfa_verified=false` con 403 `mfa_required`.
- **Criterios de aceptación:**
  - Test que cubre los ~30 endpoints privileged enumerados: todos retornan 403 cuando MFA no se verificó.
  - Test que el path `service-account` (no humano) sigue funcionando porque MFA no aplica.

---

### TASK-0092 — Verificar y corregir bypass de rol tenant-scoped por unscoped JWT + membership fallback (BUG16 — fix raíz de RBAC)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG16` — commit `bc5c4ed` — severidad High, **prerrequisito de BUG03/07/08/11/17/23/24/25**.
- **Depende de:** —
- **Resumen del hallazgo:** se removió el rechazo previo de `X-Tenant-Id` con JWT unscoped. La nueva `ensure_tenant_access` solo verifica que exista una fila en `app.user_tenant_roles` para `(user, tenant)`, **sin validar el rol DB contra el rol mínimo del endpoint**. `require_min_role('admin')` solo lee roles del JWT. Combinación letal: JWT con admin "global" + membership viewer en tenant B → admin completo sobre tenant B (settings, channels, knowledge, audit logs, exports).
- **Fase 1 — verificación en HEAD:**
  1. Leer `app/api/v1/dependencies.py` (o donde vivan `authenticate_request`, `require_min_role`, `ensure_tenant_access`).
  2. Confirmar la cascada actual: ¿se valida el rol DB en el tenant target?
  3. Identificar todos los call sites de `ensure_tenant_access` (`grep -rn "ensure_tenant_access" app/`).
- **Fase 2 — remediación (si persiste):**
  - Crear una única helper `ensure_tenant_role(request, tenant_id, conn, min_role)` que:
    1. Resuelve el `user_id` desde `request.state.session`.
    2. Lee `app.user_tenant_roles.role` para `(user_id, tenant_id)`.
    3. Compara contra `min_role` con el ranking `viewer < agent < manager < admin < owner`.
    4. Bypass solo para `support_mode` real (no JWT-encoded) y `platform_owner` cuando aplique.
  - Reemplazar la combinación `require_min_role(...) + ensure_tenant_access(...)` por la nueva helper en TODOS los routers tenant-scoped.
  - `require_min_role` se conserva SOLO para endpoints "platform-wide" sin `tenant_id` en path (e.g. `GET /v1/platform/tenants`).
- **Criterios de aceptación:**
  - Una helper compartida en lugar de dos chequeos.
  - Tests del rubric: JWT admin A + DB viewer B → 403. JWT admin A + DB admin B → 200. JWT no-admin + DB admin B → 403 (porque el JWT también debe ser valid).
  - Una matriz de tests por cada endpoint tenant-scoped (autogenerada).

---

### TASK-0093 — Verificar y corregir data-export con global role + any membership (BUG17)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG17` — commit `fffccbb` (TASK-0027 GDPR exports) — severidad High, fuga masiva de datos.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** `GET /v1/tenants/{id}/data-export` exige `require_min_role('owner')` + `ensure_tenant_access`. JWT owner A + membership viewer B → export completo del tenant B (tenant record, settings, channel metadata, operational counts). El export es de máximo riesgo de privacidad.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer el endpoint y la dependency stack.
  2. Confirmar si TASK-0092 lo cubrió con `ensure_tenant_role(min_role='owner')`.
- **Fase 2 — remediación (si persiste):**
  - Aplicar `ensure_tenant_role(min_role='owner')`.
  - Agregar rate limit por user (no más de 3 exports/día) y auditoría obligatoria.
- **Criterios de aceptación:**
  - Test del rubric: owner JWT A + viewer B → 403; owner JWT A + sin membership B → 403; no-owner JWT + owner DB B → 403; owner JWT A + owner DB A → 200.

---

### TASK-0094 — Verificar y corregir SSRF por endpoint S3 controlado por tenant (BUG18)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG18` — commit `2798e80` — severidad High, SSRF + uso de credenciales plataforma.
- **Depende de:** —
- **Resumen del hallazgo:** la config S3 per-tenant acepta `endpoint_url` y `prefix` como strings libres. `store_knowledge_file` los pasa a `boto3.client(endpoint_url=...)` y ejecuta `put_object`. Sin allowlist de hosts, sin HTTPS enforced, sin bloqueo de loopback/RFC1918/metadata. Si el tenant omite `access_key_id/secret_access_key`, boto3 usa las credenciales **plataforma** — el server firma con las llaves globales contra un endpoint atacante.
- **Fase 1 — verificación en HEAD:**
  1. Localizar `tenant_storage_settings` schema + endpoint PATCH.
  2. Localizar `store_knowledge_file` y la creación del cliente boto3.
  3. Confirmar si hay allowlist o validación URL.
- **Fase 2 — remediación (si persiste):**
  - Schema Pydantic: `endpoint_url` valida HTTPS, host en allowlist (AWS regional endpoints + MinIO local explícito para dev), bloquea private IP via `url_guard` (reuso de TASK-0077).
  - `prefix` debe empezar con `tenants/<tenant_id>/` enforced server-side.
  - Si no hay tenant credentials, REJECTAR la config (no fallback a credenciales plataforma).
  - El cliente boto3 se construye con `Config(signature_version='s3v4', s3={'addressing_style':'virtual'})` y `proxies=None`.
- **Criterios de aceptación:**
  - Tests del rubric: endpoint con HTTP → 422; endpoint loopback → 422; sin credenciales tenant → 422; prefix fuera de `tenants/<id>/` → 422.

---

### TASK-0095 — Verificar y corregir leak de token WhatsApp por media proxy (BUG19)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG19` — commit `8f048cf` — severidad High, leak de credenciales de canal.
- **Depende de:** —
- **Resumen del hallazgo:** el media proxy lee `message.media_id` y lo interpola string-wise en la URL Graph API (sin URL-encode). Luego confía en `media_info['url']` y hace un segundo GET con `Authorization: Bearer <tenant Meta token>` **sin allowlist de host**. Un `media_id` crafted persistido por un agente compromised redirige el segundo GET a una URL atacante y filtra el token.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `get_whatsapp_media_info` y `download_whatsapp_media`.
  2. Confirmar si `media_id` se valida con regex `^\d{10,30}$` antes de usar.
  3. Confirmar si `media_info['url']` se chequea contra host `lookaside.fbsbx.com` / `scontent.*.fbcdn.net`.
- **Fase 2 — remediación (si persiste):**
  - `media_id` se valida con regex estricta de Meta antes de cualquier construcción de URL. URL-encode con `urllib.parse.quote(media_id, safe='')`.
  - La URL devuelta por Graph se valida contra una allowlist de hosts Meta CDN (`*.fbcdn.net`, `*.fbsbx.com`). Cualquier host distinto → reject + audit + alerta de seguridad.
  - El POST de mensajes outbound rechaza `media_id` que no respete la regex (el agente no puede persistir basura).
- **Criterios de aceptación:**
  - Test estático: `media_id="../foo"` → 422 en POST de mensaje.
  - Test del proxy: Graph mock devuelve `url='http://attacker.com'` → proxy rechaza con 502 sin hacer el segundo GET.

---

### TASK-0096 — Verificar y corregir webhook WhatsApp escribe en el tenant equivocado por phone_number_id (BUG20)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG20` — commit `af1e91c` — severidad High, cross-tenant data corruption.
- **Depende de:** —
- **Resumen del hallazgo:** los payloads Meta son arrays de entries y changes; cada change tiene su propio `metadata.phone_number_id`. El handler resuelve un único `channel` usando el primer phone_number_id del payload y persiste **todos** los messages bajo ese channel/tenant. Una request Meta con changes para múltiples phone_number_ids escribe los messages de tenants B+ bajo el tenant A.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer el handler webhook WhatsApp en `app/api/v1/routes.py` (≈ `whatsapp_webhook_post`).
  2. Confirmar si el handler re-resuelve el canal por change/message o si sigue usando el primero.
- **Fase 2 — remediación (si persiste):**
  - Iterar `entry → changes → metadata.phone_number_id`. Para cada change, re-resolver `channel = lookup_channel(phone_number_id)` y verificar que el `app_secret` que firmó la request matchea el secret del channel resuelto.
  - Si no matchea, descartar ese change con audit `webhook.phone_number_id_mismatch`.
  - Setear `app.tenant_id` por change antes de cada insert. Usar transacciones por change para no contaminar el state.
- **Criterios de aceptación:**
  - Test del rubric: payload firmado con app_secret del tenant A que contiene un change con phone_number_id de B → el change B se descarta, no se inserta en A.

---

### TASK-0097 — Verificar y corregir shadowing del webhook secret por phone_number_id duplicado (BUG21)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG21` — commit `9cfbead` — severidad High, takeover de canal Meta.
- **Depende de:** —
- **Resumen del hallazgo:** el webhook POST extrae `metadata.phone_number_id` del body (sin auth previa) y selecciona la **primera** fila activa en `tenant_channels` que matchea. `create_channel` acepta cualquier `phone_number_id` del admin sin uniqueness constraint global. Un tenant atacante registra el mismo `phone_number_id` que la víctima → su `app_secret` se usa para validar firma; el atacante puede firmar payloads aceptados para el número de la víctima.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `infra/postgres/01-schema.sql` para `tenant_channels` — ¿hay `UNIQUE (phone_number_id) WHERE status='active'`?
  2. Re-leer `create_channel` admin endpoint.
  3. Re-leer el lookup en el handler webhook.
- **Fase 2 — remediación (si persiste):**
  - Migration: índice único parcial `CREATE UNIQUE INDEX ux_tenant_channels_phone_number_active ON app.tenant_channels(phone_number_id) WHERE status='active';`
  - `create_channel` valida que ningún otro tenant tiene ese `phone_number_id` activo antes de aceptar. Si ya existe, requiere "claim verification" (proveer un token enviado por Meta a ese número) o aprobación platform_owner.
  - El lookup del webhook usa `ORDER BY created_at` y verifica que `app_secret` matchea antes de aceptar.
- **Criterios de aceptación:**
  - Test que `create_channel` con un `phone_number_id` ya activo en otro tenant → 409.
  - Test del rubric: dos channels con mismo `phone_number_id` activos → la DB lo previene a nivel de constraint.

---

### TASK-0098 — Verificar y corregir hijack de teléfono de contacto vía conversation/start (BUG22)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG22` — commit `1ec5213` — severidad High, redirección de mensajes del cliente.
- **Depende de:** —
- **Resumen del hallazgo:** `POST /v1/conversations/start` está en `tenant_ops_router` (`agent`+). `ConversationStart` acepta `wa_id` y `phone_e164` separados. El handler hace upsert por `(tenant_id, wa_id)` y **sobrescribe `phone_e164` y `phone_hash`** con lo que el agente mande. El worker outbound envía a `contacts.phone_e164`. Un agente compromised puede redirigir todos los mensajes futuros del contacto víctima al teléfono del atacante.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer el handler y el schema.
  2. Confirmar si el upsert hoy preserva `phone_e164` cuando el contacto ya existe.
- **Fase 2 — remediación (si persiste):**
  - `conversation/start` NO acepta `wa_id` del cliente. Si el agente quiere iniciar una conversación con un contacto existente, debe pasar `contact_id` (UUID). Si quiere crear uno nuevo, pasa `phone_e164` y el handler valida que NO existe ya un contacto con ese `wa_id` (o lo crea sin reusar).
  - Cambiar `phone_e164`/`phone_hash` de un contacto existente requiere endpoint separado `PATCH /v1/contacts/{id}/phone` con rol `manager`+ y auditoría obligatoria.
- **Criterios de aceptación:**
  - Test del rubric: agente envía POST con `wa_id` de víctima + `phone_e164` atacante → 403 o 422.
  - Test que `PATCH /v1/contacts/{id}/phone` requiere `manager` y produce audit.

---

### TASK-0099 — Verificar y corregir Knowledge Studio sin per-tenant admin check (BUG23)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG23` — commit `f98c19e` (TASK-0016 Knowledge Studio) — severidad High, RBAC cross-tenant.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** los endpoints list/get/update/delete de `knowledge_documents` están en `tenant_admin_router`. Combinación JWT admin global + membership low en tenant target → admin completo de Knowledge Studio en B (cambiar visibilidad, contenido, borrar).
- **Fase 1 — verificación en HEAD:**
  1. Re-leer los endpoints y la dependency stack.
  2. Confirmar si TASK-0092 ya los cubrió.
- **Fase 2 — remediación (si persiste):**
  - Aplicar `ensure_tenant_role(min_role='admin')`.
- **Criterios de aceptación:**
  - Test del rubric: list/get/patch/delete con JWT admin A + DB viewer B → 403.

---

### TASK-0100 — Verificar y corregir tenant profile updates y tenant-signup hijack (BUG24)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG24` — commit `f6d8e15` — severidad High, RBAC cross-tenant + signup hijack.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** dos paths:
  1. `PATCH /v1/tenants/{id}` permite a JWT admin A + viewer B modificar slug, legal name, vertical, country, timezone del tenant B.
  2. `POST /v1/tenant-signup` ahora **actualiza** el primer tenant del actor sin chequear que el rol de membership sea `owner`/`admin`. Devuelve `user_role='owner'` engañosamente.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `update_tenant_record`, PATCH endpoint, `tenant-signup` flow.
  2. Confirmar si signup hoy chequea membership role antes de update.
- **Fase 2 — remediación (si persiste):**
  - PATCH: `ensure_tenant_role(min_role='owner')` (cambiar slug/legal es operación owner).
  - `tenant-signup`: si el actor ya tiene una membership en algún tenant, el endpoint NO debe actualizar nada. Retornar 409 "user already onboarded" y dirigir a la UI normal.
  - Crear tenant nuevo solo si el user no tiene memberships previas.
- **Criterios de aceptación:**
  - Test del rubric: PATCH B con JWT admin A + viewer B → 403.
  - Test: tenant-signup llamado por user con membership previa → 409 sin modificar `app.tenants`.

---

### TASK-0101 — Verificar y corregir DB membership fallback ignora role mínimo (BUG25 — cierre de la familia)

- **Estado:** PENDING
- **Referencia:** `docs/BUGS/BUG25` — commit `e942cfd` — severidad High, RBAC cross-tenant.
- **Depende de:** TASK-0092.
- **Resumen del hallazgo:** el nuevo "tenant-membership fallback" solo chequea **existencia** de fila en `user_tenant_roles`, no el rol. Combinado con `require_min_role('admin')` mirando solo JWT, da escalamiento completo a cualquier tenant donde el atacante tenga viewer/agent.
- **Fase 1 — verificación en HEAD:**
  1. Confirmar que TASK-0092 reemplazó el fallback con `ensure_tenant_role`.
  2. Buscar usos residuales de `has_user_tenant_role` sin role check.
- **Fase 2 — remediación (si persiste):**
  - Eliminar `has_user_tenant_role` con semántica "existe fila" y reemplazar por `get_user_tenant_role` que devuelve el rol exacto o `None`.
  - Cualquier llamada al helper que no compare contra `min_role` es un bug — refactor + grep CI.
- **Criterios de aceptación:**
  - `grep -rn "has_user_tenant_role" app/` → 0 resultados.
  - Test de regresión que un endpoint tenant-admin rechace JWT admin global + DB viewer.
  - **Última tarea de la familia RBAC**: al cerrarla, TASK-0079, TASK-0083, TASK-0084, TASK-0087, TASK-0093, TASK-0099, TASK-0100 deben quedar verificadas como cubiertas por la helper compartida.

---
