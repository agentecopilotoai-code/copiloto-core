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

### TASK-0064 — Backups automatizados a cloud con verificación periódica

- **Estado:** PENDING
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

### TASK-0065 — DLQ de mensajes outbound visible en panel + alerta

- **Estado:** PENDING
- **Depende de:** TASK-0057 (operator_alerts).
- **Por qué bloquea:** `event_worker.py` reintenta envíos a Meta, pero cuando agota retries el mensaje queda con `messages.status='failed'` y `messages.error_*`. No hay panel para verlo. El operador descubre el problema cuando el cliente reclama por otro canal.
- **Alcance:**
  - Endpoint `GET /v1/tenants/{tenant_id}/outbound/dlq?since=...&until=...&limit=...` que lista mensajes con `status='failed'` agrupados por `error_code`, con counters y previews. Devuelve `{items, totals_by_error_code}`.
  - Endpoint `POST /v1/tenants/{tenant_id}/outbound/dlq/{message_id}/retry` que vuelve a encolar el mensaje (resetea `status='queued'`, `retry_count=0`, dispara evento `message.outbound.requested`).
  - **Alerta automática:** cuando el conteo de `messages.status='failed'` en la última hora supera `dlq_alert_threshold` (default 10), el scheduler emite `operator_alerts(kind='outbound_dlq_threshold')` con preview de los últimos 5 errores.
  - **Admin Panel:** nuevo módulo `outbound/OutboundDLQ.jsx` listado en el nav lateral, con filtro por código de error, botón "reintentar" y modal de detalle con el payload completo y el error de Meta.
  - **Métricas Prometheus:** nuevo counter `cpi_outbound_dlq_total{tenant, error_code}` incrementado por `event_worker` al marcar fail definitivo; nueva regla de alerta `OutboundDLQGrowing` en `infra/observability/alerts.yaml` (>5 fails en 5 min).
- **Criterios de aceptación:**
  - 12 mensajes con error 131026 (recipient unreachable) → endpoint devuelve grupo con count=12.
  - Click "reintentar" en uno → re-encolado y eventualmente entregado.
  - Alerta dispara cuando >10 fails en 1h.
  - Tests: ≥ 10 estáticos: schema del endpoint, agrupación por error_code, retry idempotente, threshold de alerta, regla Prometheus, módulo en admin panel.
- **Notas:**
  - El reintento manual no afecta a `retry_count` automático; el operador decide cuántos intentos hacer.

---

### TASK-0066 — Runbooks operacionales por tipo de incidente

- **Estado:** PENDING
- **Depende de:** TASK-0060 (alertas), TASK-0064 (backups).
- **Por qué bloquea:** sin runbook, cada incidente requiere reinventar la respuesta. Lo que diferencia un MVP operacional de un SaaS vendible es la capacidad de responder a un incidente con un procedimiento conocido. Hoy solo existe `docs/runbook-go-live-evidence.md`.
- **Alcance:**
  - Carpeta `docs/runbooks/` con un archivo por escenario, cada uno con: **síntoma**, **diagnóstico (queries SQL / curl / kubectl)**, **mitigación inmediata**, **fix definitivo**, **post-mortem checklist**.
  - Runbooks mínimos:
    - `meta-token-expired.md` — síntoma: `cpi_outbound_dlq_total` con error 190; mitigación: rotar token vía panel y reencolar.
    - `meta-quality-rating-dropped.md` — síntoma: `tenant_channels.quality_rating='RED'`; mitigación: bajar volumen de templates UTILITY, revisar plantillas activas.
    - `postgres-down.md` — síntoma: alerta `BotResponseLatencyP95High` sostenida + healthcheck rojo; mitigación: failover/restore desde backup.
    - `rate-limit-meta-hit.md` — síntoma: error 80007 en `error_code`; mitigación: bajar rate del scheduler, aumentar backoff.
    - `cloud-llm-rate-limited.md` — síntoma: circuit breaker `cloud_llm:claude` open; mitigación: degradar a `answer_engine=local_llm` temporalmente.
    - `circuit-breaker-open-sustained.md` — síntoma: gauge `cpi_circuit_breaker_state=2` >5 min; mitigación: verificar proveedor + cambiar al alterno.
    - `worker-queue-backlog.md` — síntoma: `cpi_worker_queue_depth >1000`; mitigación: escalar `event-worker` réplicas.
    - `webhook-flood.md` — síntoma: 429s en `rate_limit.blocked` >100/min; mitigación: validar firma del payload, sospechar de fuente externa.
    - `consent-violation-claim.md` — síntoma: queja del cliente; entrega: extracto del `consent_ledger`.
  - Cada runbook linkeado desde la regla de alerta correspondiente en `alerts.yaml` con anotación `runbook_url`.
  - Test estático: `tests/test_runbooks_static.py` valida que cada regla de alerta tenga un `runbook_url` válido apuntando a un archivo existente.
- **Criterios de aceptación:**
  - 9 runbooks creados, cada uno con las 5 secciones mínimas.
  - Cada regla de alerta apunta a su runbook; el test estático verifica el wiring.
- **Notas:**
  - Los runbooks viven en el repo (no en Notion) para versionarlos con el código.

---

### TASK-0067 — Digest periódico (diario y semanal) por email/WhatsApp al manager

- **Estado:** PENDING
- **Depende de:** TASK-0048 (funnel), TASK-0057 (alerts SMTP infra reutilizable).
- **Por qué bloquea:** el manager no entra al panel cada día. Sin un resumen empujado al canal del manager, los KPIs no se ven y las decisiones no se toman. Esto causa churn del SaaS aunque el producto funcione.
- **Alcance:**
  - Tabla `app.digest_subscriptions(id, tenant_id, recipient_email, recipient_whatsapp, cadence check in ('daily','weekly'), enabled, last_sent_at, created_at, updated_at)`.
  - Worker dedicado `app/workers/digest_worker.py` que corre 1x al día a las 08:00 hora del tenant (`tenants.timezone`) y arma:
    - **Daily:** citas confirmadas hoy, citas para mañana, no-shows de ayer, top 3 quejas abiertas, mensajes recibidos (24h), conversión funnel del día.
    - **Weekly (lunes):** lo del daily + ingreso semanal, top campañas, top servicios, retención 90d, comparación vs semana anterior.
  - Generador `app/services/digest.py` con `build_daily_digest(conn, tenant_id) -> {text, html, whatsapp_template_components}` que reusa los endpoints de analytics.
  - Email vía SMTP (infra existente de TASK-0057); WhatsApp via template `digest_daily_v1` / `digest_weekly_v1`.
  - **Admin Panel:** sección "Suscripciones a resúmenes" en pestaña Notificaciones del wizard, con input para emails y WhatsApp, toggle daily/weekly.
- **Criterios de aceptación:**
  - Manager configura email y recibe a las 08:00 del día siguiente un email con los 6 KPIs del daily.
  - Lunes a las 08:00 recibe el weekly con la comparación vs semana anterior.
  - Tests: ≥ 10 estáticos: schema de `digest_subscriptions`, builder del payload (snapshot test), wiring del worker en compose, idempotencia (`last_sent_at`).
- **Notas:**
  - Reusar `operator_alerts._send_email_channel` / `_send_whatsapp_channel` para no duplicar SMTP.

---

### TASK-0068 — KPIs de rendimiento por agente en analytics

- **Estado:** PENDING
- **Depende de:** TASK-0041 (team management), TASK-0048 (funnel).
- **Por qué bloquea:** el manager quiere saber qué agente cierra más, responde más rápido y deja menos handoffs abiertos. Hoy `analytics_*` agrega solo a nivel tenant.
- **Alcance:**
  - Endpoint `GET /v1/analytics/agents?since=...&until=...` que devuelve por agente: `messages_sent`, `handoffs_accepted`, `handoffs_resolved`, `avg_response_time_seconds`, `appointments_confirmed`, `revenue_attributed`, `feedback_avg_rating`.
  - Cálculos: `avg_response_time_seconds` = avg(diff entre el último inbound del cliente y la primera respuesta del agente en `messages.sender_actor_type='agent'`).
  - **Admin Panel:** nuevo módulo `analytics/AgentPerformance.jsx` con tabla ranqueable y badge "top performer" del mes.
  - Atribución de ingresos: cuando un agente cierra una cita por el desk, `appointments.metadata.closed_by_user_id` se setea; `revenue_attributed` agrega por ese campo.
- **Criterios de aceptación:**
  - Endpoint devuelve métricas por agente con 5 agentes activos.
  - Tests: ≥ 8 estáticos: SQL de las métricas, persistencia de `closed_by_user_id`, módulo en admin panel.

---

### TASK-0069 — Wizard de onboarding self-service con verificación paso-a-paso

- **Estado:** PENDING
- **Depende de:** TASK-0003 (wizard base), TASK-0033 (catálogo).
- **Por qué bloquea:** cada cliente nuevo consume 4-8h de soporte humano. Para escalar comercialmente el cliente tiene que poder onboardearse solo con un wizard guiado que verifique cada paso antes de avanzar.
- **Alcance:**
  - Wizard de 7 pasos: (1) datos del negocio, (2) timezone + locale + moneda, (3) canal WhatsApp (con verificación de la firma del webhook contra Meta), (4) primer template `consent_request_v1` (cargado vía Meta API), (5) catálogo de servicios mínimo (≥ 1 servicio), (6) horarios de atención, (7) test E2E: el wizard envía un mensaje de prueba al wa_id del admin y verifica que el inbound llegue.
  - Cada paso emite un evento `tenant_onboarding.step_completed(step=N)` y solo desbloquea el siguiente cuando el actual pasó su check.
  - Estado del onboarding visible en `GET /v1/tenants/{tenant_id}/readiness` (ya existe; se extiende con `onboarding_progress: {step, total, last_completed_step}`).
- **Criterios de aceptación:**
  - Un cliente nuevo termina onboarding en <30 min sin soporte humano.
  - Si un paso falla (token Meta inválido), el wizard explica el error y bloquea.
  - Tests: ≥ 12 estáticos: cada paso valida sus precondiciones, ningún paso permite saltar al siguiente sin completar, estado persistido en `tenant_settings.onboarding_progress`.

---

### TASK-0070 — Widget JS embebible distribuido por CDN

- **Estado:** PENDING
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

- **Estado:** PENDING
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

### TASK-0072 — Pruebas de carga + SLA documentado

- **Estado:** PENDING
- **Depende de:** TASK-0060 (métricas).
- **Por qué bloquea:** vender con SLA sin medirlo es contraproducente. Sin medir, ¿cuántos mensajes/segundo aguanta el API? ¿Cuándo se degrada?
- **Alcance:**
  - Escenario Locust en `tests/load/test_journey_load.py` con perfil mixto: 70% inbound message, 20% panel queries, 10% admin actions.
  - Job `load-test` en GitHub Actions corriendo cada release contra un compose efímero, con baseline en `docs/sla.md`.
  - **`docs/sla.md`:** SLA propuesto (99% requests <2s, 99.9% disponibilidad) y resultado del último load test (p50/p95/p99).
- **Criterios de aceptación:**
  - Load test con 50 msg/s sostenidos durante 5 min sin degradación (p95 <2s).
  - `docs/sla.md` se regenera con cada run.

---

### TASK-0073 — i18n multi-país: locale, currency, timezone, formato de teléfono

- **Estado:** PENDING
- **Depende de:** TASK-0033 (catálogo).
- **Por qué bloquea:** `locale='es-CO'` y `COP` están hardcodeados en defaults, en formatos de fecha y en validación de teléfono. El primer cliente de México exige refactor.
- **Alcance:**
  - `tenants.country_code` ya existe; ampliar a soportar `MX, AR, CL, PE, EC, UY`.
  - `tenant_settings.currency char(3)` con default derivado de `country_code` (MX→MXN, AR→ARS, etc.).
  - Validador de teléfono pasa de regex CO a `phonenumbers` library con `country_code` como hint.
  - Strings del bot vienen de `app/i18n/<locale>.toml`; `es-CO`, `es-MX`, `es-AR`, `es-CL` inicialmente.
- **Criterios de aceptación:**
  - Tenant MX con currency MXN muestra precios "$ 1,500.00 MXN" en lugar de "$ 1.500 COP".
  - Validación de teléfono acepta `+52 55 1234 5678`.
  - Tests: ≥ 10 estáticos por país soportado.

---

### TASK-0074 — Canal Instagram DM / Facebook Messenger

- **Estado:** PENDING
- **Depende de:** TASK-0021 (orquestación).
- **Por qué bloquea:** el flujo del producto dice "redes sociales". Hoy solo WhatsApp + Widget Web. El lead que escribe por Instagram queda sin atención.
- **Alcance:**
  - `tenant_channels.provider` extiende a `'instagram_messenger', 'facebook_messenger'`.
  - Webhook `/v1/webhooks/meta/{provider}` reusa la validación HMAC (mismo App Secret de la app Meta del tenant).
  - Adaptador en `app/services/instagram.py` y `app/services/facebook.py` que normaliza payloads al formato canónico que ya consume `rag_orchestrator`.
  - **Limitación:** Instagram solo permite responder a un DM iniciado por el usuario en ventana 24h. El policy engine ya respeta la ventana 24h de WhatsApp; mismo gate aplica.
- **Criterios de aceptación:**
  - Inbound desde Instagram persiste un mensaje y dispara el mismo flujo que WhatsApp.
  - Outbound a Instagram fuera de la ventana 24h se bloquea con error `outside_service_window`.
  - Tests: ≥ 12 estáticos: extensión del enum, normalizador de Instagram, normalizador de Facebook, gate de ventana 24h por provider.

---

### TASK-0075 — Suscripciones / membresías con cobro recurrente

- **Estado:** PENDING
- **Depende de:** TASK-0040 (payment links), TASK-0051 (packages).
- **Por qué bloquea:** `treatment_packages` cubre paquetes finitos (5 sesiones). Gimnasios, dental anual, spa mensual necesitan **cobro recurrente** con notificación al cliente cuando el cobro falla. Hoy no es vendible a esos verticales.
- **Alcance:**
  - Nueva tabla `app.subscription_plans(id, tenant_id, name, billing_period check in ('monthly','quarterly','yearly'), price_amount, currency, included_services jsonb, status)`.
  - `app.contact_subscriptions(id, tenant_id, contact_id, plan_id, status check in ('active','past_due','cancelled'), started_at, next_billing_at, payment_provider_subscription_id, payment_method_id)`.
  - Webhook de Stripe/MercadoPago para eventos `invoice.payment_succeeded` / `invoice.payment_failed` actualiza el status y, en `payment_failed`, dispara WhatsApp template `subscription_payment_failed_v1`.
  - **Admin Panel:** módulo `subscriptions/SubscriptionsModule.jsx` con CRUD de planes + lista de suscriptores activos.
- **Criterios de aceptación:**
  - Cliente compra plan mensual, se cobra automáticamente cada 30 días.
  - Si falla el cobro, el cliente recibe WhatsApp con el link de reintentar pago.
  - Tests: ≥ 14 estáticos: schemas, webhook handlers Stripe y MercadoPago, template de fallo, módulo en panel.

---

### TASK-0076 — Páginas legales por tenant: Términos y Privacidad

- **Estado:** PENDING
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
