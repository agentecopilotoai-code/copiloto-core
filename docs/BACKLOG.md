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

### TASK-0047 — Segmentos automáticos para retención y reactivación

- **Estado:** PENDING
- **Depende de:** TASK-0042 (datos de calificación) y CRM existente (TASK-0037).
- **Por qué bloquea:** las campañas existen pero el operador tiene que armar el filtro a mano cada vez, sin una vista clara de "quién es candidato". El equipo no usa campañas → recompra y reactivación quedan dependientes del agente.
- **Alcance:**
  - Nueva tabla `app.contact_segments` (`id, tenant_id, name, description, kind: dynamic|static, rules jsonb, contact_count int default 0, last_refreshed_at, created_by, created_at, updated_at`).
  - Builder de **segmentos dinámicos**: `app/services/segments.py.build_segment_query(rules) -> (sql, params)` que traduce reglas JSON (`any_of`, `all_of`, operadores `eq/in/lt/gt/between`, campos `last_appointment_at`, `total_appointments_completed`, `total_spent`, `tags`, `lead_source.channel`, `qualification.<key>`) a un `SELECT contact_id FROM ...`. Reutiliza el patrón ya usado por `campaigns.build_recipients_query`.
  - Segmentos **preconstruidos** sembrados al crear un tenant: "Sin visita en 60+ días", "Clientes recurrentes (3+ citas)", "VIP (gasto > umbral)", "Primer contacto sin agendar", "No-show reciente". Editables por el tenant.
  - Job programado (worker `scheduler.py`) que recalcula `contact_count` y persiste un snapshot en `app.contact_segment_members(segment_id, contact_id, snapshot_at)` para los segmentos dinámicos cada 1h.
  - Endpoints `/v1/tenants/{id}/segments` (CRUD + `/preview` que devuelve los primeros 25 contactos del segmento).
  - En el módulo **Campañas**, el formulario de creación permite **partir de un segmento** (en lugar de armar `segment_filter` libre). El segmento se snapshotea al lanzar la campaña (no se recalcula durante la entrega).
  - Vista de "candidatos por segmento" en `ContactsModule` con filtro de segmento.
- **Criterios de aceptación:**
  - Al crear un tenant nuevo, los 5 segmentos preconstruidos aparecen ya sembrados.
  - Operador crea una campaña "Reactivación mayo" eligiendo el segmento "Sin visita en 60+ días" → la campaña hereda los recipients.
  - `GET /v1/tenants/{id}/segments/{sid}/preview` responde en < 1s con 25 contactos.
  - El job de refresh actualiza `contact_count` y no duplica miembros (idempotente por `(segment_id, contact_id)`).
  - Tests: ≥ 12 estáticos: schema, builder de query con cada operador, segmentos preconstruidos sembrados por bootstrap, integración con campaigns, refresh worker.
- **Notas:**
  - Los segmentos **estáticos** (kind=`static`) sirven para snapshots manuales — el operador puede capturar "asistentes al taller del 12 de mayo" sin reglas.
  - Si un campo `qualification.<key>` no existe en un tenant, la regla devuelve 0 contactos (no error). Esto desacopla la deuda contra TASK-0042.

---

### TASK-0048 — Funnel de conversión y atribución de ingresos por campaña

- **Estado:** PENDING
- **Por qué bloquea:** el gerente del negocio no puede demostrar el ROI del producto. El panel muestra KPIs sueltos (conversaciones, citas, no-show rate, ingreso) pero no la **conversión punta a punta** (lead → cita agendada → cita completada → cliente recurrente) ni cuánto ingreso atribuir a una campaña específica. Sin esto, el cliente que paga la suscripción no renueva.
- **Alcance:**
  - Nuevo endpoint `GET /v1/analytics/funnel?from_date=&to_date=` que devuelve, por canal de origen (`lead_source.channel`):
    1. `leads` = contactos con `first_contact_at` en el rango.
    2. `engaged` = contactos con ≥ 1 mensaje outbound del bot/agente.
    3. `appointments_scheduled` = contactos con ≥ 1 appointment creado en el rango.
    4. `appointments_completed` = contactos con ≥ 1 appointment `status='completed'`.
    5. `repeat_customers` = contactos con ≥ 2 appointments `completed` en los últimos 90 días.
    Cada paso reporta `count`, `conversion_from_previous_pct`, `conversion_from_top_pct`.
  - Nuevo endpoint `GET /v1/analytics/campaigns?from_date=&to_date=` que devuelve, por campaña ejecutada en el rango:
    - `recipients`, `delivered`, `read`, `replied` (ya existentes).
    - `appointments_attributed` = citas creadas por contactos cuya última campaña recibida (en ventana `attribution_window_days`, default 14) fue esta.
    - `revenue_attributed` = suma de `service_catalog.price_amount` de esas citas en estado `completed`.
    - `roi_estimated` = `revenue_attributed / campaigns.cost` (si el operador captura el costo opcional).
  - Tabla nueva `app.campaign_attributions(campaign_id, contact_id, appointment_id, attributed_at)` poblada por un trigger / worker liviano cuando se crea un appointment dentro de la ventana de atribución posterior al `last_message_at` de una campaña al contacto.
  - Columna nueva `app.campaigns.cost_amount numeric(12,2)` y `cost_currency char(3)` editables desde el módulo Campañas para que el ROI sea computable.
  - UI: nueva sub-pestaña en `AnalyticsPanel`:
    - **Funnel** con gráfica de embudo (5 pasos × N canales) usando CSS-only bars.
    - **Campañas** con tabla ordenada por `revenue_attributed desc`, columnas: nombre, recipients, response rate, citas atribuidas, ingreso atribuido, costo, ROI.
- **Criterios de aceptación:**
  - Para un rango de 30 días con tráfico real, el endpoint funnel se ejecuta en < 800ms (índices ya existentes lo soportan).
  - Cada paso del funnel tiene su porcentaje correcto: si `leads=100`, `engaged=80`, `appointments_scheduled=40`, `completed=30`, `repeat=8`, los `conversion_from_previous_pct` son `80, 50, 75, 26.7`.
  - Una campaña que genera 5 citas atribuibles (en ventana de 14 días) muestra `appointments_attributed=5` y `revenue_attributed = Σ price`.
  - Tests: ≥ 10 estáticos: endpoints registrados con `require_min_role('manager')`, query SQL del funnel cubre los 5 pasos, atribución dentro/fuera de ventana, ROI con/sin costo, UI registra las dos sub-pestañas.
- **Notas:**
  - La ventana de atribución es **last-touch** simple (no multi-touch). En MVP es suficiente: un cliente vino por una campaña → la cita se le cuenta a esa campaña.
  - Si el contacto recibió varias campañas dentro de la ventana, gana la más reciente con `delivered_at` antes del `appointment.created_at`.
  - El cierre de esta tarea es el cierre del MVP comercial: con funnel + atribución + retención automática, el producto está listo para venderse con datos en mano.

---
