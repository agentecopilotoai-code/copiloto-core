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


## Backlog de bugs reportados — 2026-05-13 (auditoría de seguridad, consolidado por causa raíz)

Se auditaron los 25 hallazgos almacenados en `docs/BUGS/BUG01`–`docs/BUGS/BUG25` (todos `Severidad: High`, validados con evidencia dinámica por ChatGPT Codex Security). El análisis encontró que **los 25 bugs se reducen a 10 tareas estructurales**: cinco grupos comparten causa raíz y se cierran con un único fix, y seis hallazgos quedan como tareas individuales por no compartir patrón.

**Protocolo obligatorio por tarea (dos fases):**

1. **Verificación en HEAD:** la auditoría se ejecutó contra commits viejos (ver `Commits auditados` por tarea). Tareas posteriores (TASK-0059 rate limit, TASK-0060 observabilidad, TASK-0061 retention, TASK-0062 consent ledger, TASK-0063 E2E, etc.) pueden haberlo mitigado parcial o totalmente. **Antes de tocar código, ejecutar el rubric de validación de cada BUG cubierto** y dejar evidencia escrita (comando ejecutado, archivos leídos, líneas relevantes). Si **todos** los rubrics dan negativo en HEAD, mover la tarea a `DONE.md` con la evidencia y sin escribir patch.
2. **Remediación de la causa raíz:** si **algún** rubric persiste, aplicar el fix estructural una sola vez (no por endpoint), agregar tests estáticos que cubran cada BUG del grupo, validar con `uv run pytest` y `uv run ruff check`. Documentar en `DONE.md` qué bug del grupo quedó cubierto por qué assertion.

**Trazabilidad bug → tarea:**

| Tarea | Causa raíz / patrón | Bugs cubiertos |
|---|---|---|
| TASK-0077 | RBAC tenant-scoped: JWT role + DB role en el tenant target | BUG03, BUG07, BUG08, BUG11, BUG16, BUG17, BUG23, BUG24, BUG25 |
| TASK-0078 | Visibilidad RAG `agents_only` en retrieval SQL | BUG10, BUG12, BUG13 |
| TASK-0079 | SSRF desde URLs/endpoints controlados por tenant | BUG01, BUG18, BUG19 |
| TASK-0080 | MFA enforcement server-side + gate UI bloqueante | BUG14, BUG15 |
| TASK-0081 | Binding webhook WhatsApp ↔ tenant_channel | BUG20, BUG21 |
| TASK-0082 | Identidad de contacto: validación de fuente y mutación | BUG05, BUG22 |
| TASK-0083 | Webhook de pagos fail-closed | BUG04 |
| TASK-0084 | Operaciones financieras requieren admin + payment_status server-only | BUG02 |
| TASK-0085 | Auth0 invite por user_id, nunca por email | BUG06 |
| TASK-0086 | Clasificador LLM async + timeout efectivo | BUG09 |

**Orden de ejecución (P0 → P2):**

```
P0 — bloqueo regulatorio / financiero / cross-tenant inmediato
    TASK-0083 (BUG04)  webhook de pagos fail-closed
    TASK-0079 (BUG01, BUG18, BUG19)  SSRF tenant-controlled URLs
    TASK-0077 (familia RBAC, 9 bugs)  fix raíz de tenant-role mismatch
    TASK-0081 (BUG20, BUG21)  webhook tenant binding
    TASK-0080 (BUG14, BUG15)  MFA server-side

P1 — fuga de datos al cliente final / suplantación
    TASK-0078 (BUG10, BUG12, BUG13)  RAG agents_only
    TASK-0082 (BUG05, BUG22)  identidad de contacto
    TASK-0084 (BUG02)  paquetes pagados admin-only

P2 — abuso lateral / DoS / leakage de credenciales secundarias
    TASK-0085 (BUG06)  Auth0 invite
    TASK-0086 (BUG09)  clasificador async
```

---

### TASK-0077 — Fix estructural: autorización tenant-scoped con doble chequeo JWT + DB role

- **Estado:** DONE (2026-05-13) — ver `docs/DONE.md`.
- **Causa raíz:** `require_min_role('admin')` (o `'owner'`) valida únicamente `request.state.roles` del JWT (rol "global" o de la sesión). `ensure_tenant_access` luego acepta cualquier fila en `app.user_tenant_roles` para el tenant target sin verificar **rol mínimo en ese tenant**. La combinación permite que un JWT con rol alto + membership viewer/agent en un tenant víctima escale a operaciones admin/owner sobre ese tenant.
- **Bugs cubiertos (9):**
  - **BUG03** (`docs/BUGS/BUG03`, commit `7ca68ea`): media/promotions CRUD cross-tenant.
  - **BUG07** (`docs/BUGS/BUG07`, commit `3d62d3f`): WhatsApp templates list/create/update/sync/delete cross-tenant — incluye borrado remoto en Meta.
  - **BUG08** (`docs/BUGS/BUG08`, commit `39f5c49`): service catalog read/write/reorder cross-tenant.
  - **BUG11** (`docs/BUGS/BUG11`, commit `562fa70`): tenant lifecycle `status` mutable por admin tenant — debe ser `platform_owner` only.
  - **BUG16** (`docs/BUGS/BUG16`, commit `bc5c4ed`): unscoped JWT + `X-Tenant-Id` + cualquier membership pasa controles admin.
  - **BUG17** (`docs/BUGS/BUG17`, commit `fffccbb`): `GET /tenants/{id}/data-export` permite owner JWT A + viewer DB B.
  - **BUG23** (`docs/BUGS/BUG23`, commit `f98c19e`): Knowledge Studio list/get/update/delete cross-tenant.
  - **BUG24** (`docs/BUGS/BUG24`, commit `f6d8e15`): tenant profile PATCH cross-tenant + `tenant-signup` hijack (actualiza la primera membership sin verificar rol).
  - **BUG25** (`docs/BUGS/BUG25`, commit `e942cfd`): tenant DB membership fallback acepta cualquier rol.
- **Fase 1 — verificación en HEAD (ejecutar antes de patch):**
  1. `grep -rn "ensure_tenant_access\|has_user_tenant_role\|require_min_role" app/` para inventariar los call sites.
  2. Re-leer `app/api/v1/dependencies.py` (o donde vivan los helpers) y confirmar el estado actual de cada cascada.
  3. Re-ejecutar cada rubric de los 9 BUGs en archivos `docs/BUGS/BUG{03,07,08,11,16,17,23,24,25}`: para cada uno, identificar el endpoint vulnerable, montar mentalmente la combinación JWT/DB del atacante y confirmar si HEAD lo rechaza con 403 o lo acepta.
  4. Documentar en `DONE.md` cuántos de los 9 BUGs siguen reproducibles. Si los 9 dan negativo, no escribir patch.
- **Fase 2 — remediación (causa raíz, un solo fix):**
  - Crear `app/api/v1/auth.py::ensure_tenant_role(request, tenant_id, conn, *, min_role)` que aplica **dos chequeos AND**:
    1. **JWT role gate:** `request.state.roles` (lista de roles del token) debe contener al menos uno con rango ≥ `min_role` según el ranking `viewer < agent < manager < admin < owner < platform_owner`. Sin esto, 403 `insufficient_token_role`. *Esto preserva el comportamiento de `require_min_role` y responde al review del bot que señaló la regresión.*
    2. **DB role gate:** `select role from app.user_tenant_roles where user_id=$1 and tenant_id=$2` debe existir Y `rank(role) ≥ rank(min_role)`. Sin esto, 403 `insufficient_tenant_role`.
  - Bypass solo para `support_mode='true'` real (proceso scheduler/worker con flag de sesión Postgres) y para `platform_owner` cuando el endpoint lo permite explícitamente.
  - Reemplazar las parejas `Depends(require_min_role(...)) + ensure_tenant_access(...)` por `Depends(ensure_tenant_role(min_role=...))` en TODOS los routers tenant-scoped. `require_min_role` queda válido SOLO para endpoints sin `tenant_id` en path (`/v1/platform/...`).
  - **Casos especiales del grupo:**
    - **BUG11:** el campo `status` se mueve de `TenantUpdate` a `PlatformTenantUpdate` y solo `platform_admin_router` lo persiste. `update_tenant_record` recibe flag `actor_is_platform_owner` y rechaza `status` si False.
    - **BUG24 (tenant-signup):** si el actor ya tiene membership, retornar 409 sin tocar `app.tenants`. Sólo crear tenant nuevo si no hay memberships previas.
    - **BUG25:** eliminar `has_user_tenant_role` (semántica "existe fila") y reemplazar por `get_user_tenant_role` (devuelve el rol o `None`). `grep -rn "has_user_tenant_role" app/` debe quedar en 0.
- **Criterios de aceptación:**
  - Suite estática `tests/test_tenant_role_authz.py` con una matriz que cubre cada uno de los 9 BUGs:
    - BUG03: JWT admin A + DB viewer B → 403 en `/tenants/B/media/*` y `/tenants/B/promotions/*` (GET/POST/PATCH/DELETE).
    - BUG07: misma combinación contra `/tenants/B/whatsapp/templates/*` incluyendo `sync` y `delete` (con stub Meta que verifica que NO se llamó).
    - BUG08: misma combinación contra `/tenants/B/services` (reorder incluido).
    - BUG11: PATCH tenant con `{status: 'active'}` desde tenant-admin → 422 / ignorado; el mismo PATCH desde `platform_owner` → 200.
    - BUG16: unscoped JWT admin + DB viewer B en cualquier endpoint tenant-admin → 403. Negative control: DB admin B → 200.
    - BUG17: owner JWT A + viewer DB B → 403; owner JWT A + sin membership B → 403; admin JWT A + owner DB B → 403; owner JWT A + owner DB A → 200.
    - BUG23: list/get/patch/delete Knowledge Studio con JWT admin A + DB viewer B → 403.
    - BUG24: PATCH `/tenants/B` con JWT admin A + DB viewer B → 403; `POST /tenant-signup` por user con membership previa → 409.
    - BUG25: `grep -rn "has_user_tenant_role" app/` → 0; test de regresión global.
  - Auditoría: cada 403 emite `audit_logs(action='authz.denied', detail={endpoint, reason})`.
- **Notas:**
  - El review del bot revisor en PR #111 corrigió el draft anterior: el doble chequeo (JWT AND DB) es defensa en profundidad y mantiene el invariante "el token debe portar el rol que el endpoint exige" además del nuevo "la DB debe confirmarlo para ese tenant".
  - Esta es **una sola tarea**, no nueve. La verificación rubric-por-rubric ocurre dentro de Fase 1; el fix es estructural.

---

_TASK-0078 — Fix estructural: filtro `agents_only` en retrieval RAG: COMPLETADA. Ver `docs/DONE.md`._

---

_TASK-0079 — Fix estructural: bloqueo de SSRF en URLs/endpoints controlados por tenant: COMPLETADA. Ver `docs/DONE.md`._

<!--
### TASK-0079 — Fix estructural: bloqueo de SSRF en URLs/endpoints controlados por tenant (archivado)

- **Estado:** DONE (2026-05-13)
- **Causa raíz:** el backend hace requests HTTP outbound a URLs cuyos componentes (host, scheme) están bajo control del tenant — sin enforce HTTPS, sin allowlist, sin bloqueo de loopback / RFC1918 / link-local / metadata. El proceso adjunta credenciales sensibles (token Meta del tenant, credenciales S3 plataforma) a esas requests, generando SSRF + leak de secretos.
- **Bugs cubiertos (3):**
  - **BUG01** (`docs/BUGS/BUG01`, commit `517add2`): `complaint_alert_channels.webhook_url` aceptado sin validar → POST desde `_send_webhook_channel` a 127.0.0.1, 169.254.169.254, etc.
  - **BUG18** (`docs/BUGS/BUG18`, commit `2798e80`): `tenant_storage_settings.endpoint_url` aceptado sin validar → `boto3.client(endpoint_url=...)` + `put_object`. Si el tenant omite credenciales, fallback a credenciales **plataforma** firmando contra el endpoint atacante.
  - **BUG19** (`docs/BUGS/BUG19`, commit `8f048cf`): `download_whatsapp_media` confía en `media_info['url']` devuelto por Graph y adjunta `Bearer <tenant Meta token>` sin allowlist de host CDN Meta. `media_id` interpolado sin URL-encode permite crafted IDs.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "httpx.AsyncClient\|boto3.client\|requests.post\|requests.get" app/` para inventariar sinks outbound.
  2. Confirmar si existe `app/services/url_guard.py` (o similar) y si los tres sinks lo usan.
  3. Reproducir los tres rubrics: PoC dinámico con webhook → loopback, S3 → endpoint loopback con credenciales plataforma, media proxy → host fuera de `*.fbcdn.net/*.fbsbx.com`.
- **Fase 2 — remediación (causa raíz, un solo fix):**
  - Crear `app/services/url_guard.py::validate_outbound_url(url, *, allowed_schemes=('https',), host_allowlist=None, allow_http_for_local_dev=False) -> str`:
    - Rechaza scheme no permitido.
    - Resuelve DNS y bloquea `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, `fc00::/7`, `fe80::/10`, hostname `metadata.google.internal`, `localhost`.
    - Si `host_allowlist` se pasa, exige match (wildcard subdominio permitido: `*.fbcdn.net`).
    - Devuelve la URL canónica para usar; raise `UnsafeOutboundURLError` si no pasa.
  - **Cliente HTTP compartido:** wrapper `app/services/http_client.py::safe_post(url, ...)` que:
    - Pre-valida con `validate_outbound_url`.
    - Construye `httpx.AsyncClient(follow_redirects=False, timeout=Timeout(connect=5, read=10, write=5, pool=5))`.
    - Detecta redirects manualmente y re-valida la `Location` antes de seguirla.
  - **Aplicación por bug:**
    - **BUG01:** `normalize_alert_channels` rechaza al guardar; `_send_webhook_channel` re-valida antes del POST (defensa en profundidad por si la DB trae un registro viejo). `notification_settings` se valida con Pydantic `NotificationSettingsUpdate` (no `dict` libre).
    - **BUG18:** schema Pydantic `TenantStorageSettings` valida `endpoint_url` con HTTPS + host allowlist (regional AWS endpoints + MinIO solo en `LOCAL_DEV_MODE=true`). `prefix` debe empezar con `tenants/<tenant_id>/` enforced server-side. **Si tenant no provee `access_key_id/secret_access_key`, rechazar la config (no fallback a credenciales plataforma).**
    - **BUG19:** `media_id` validado con regex `^\d{10,30}$` antes de cualquier interpolación; usar `urllib.parse.quote(media_id, safe='')`. `media_info['url']` validado contra allowlist `('*.fbcdn.net', '*.fbsbx.com', 'lookaside.fbsbx.com')` antes del segundo GET con el token. POST de mensajes outbound rechaza `media_id` que viole la regex.
- **Criterios de aceptación:**
  - Suite `tests/test_url_guard.py` ≥ 12 tests:
    - Reject HTTP, reject loopback, reject 169.254.169.254, reject `metadata.google.internal`, reject redirect-to-private.
    - Webhook alert: `webhook_url='http://127.0.0.1:6379'` → 422 en PATCH; `_send_webhook_channel` re-valida y rechaza.
    - S3: endpoint HTTP / loopback / fuera de allowlist → 422.
    - S3 sin credenciales tenant → 422 (no fallback).
    - Media proxy: `media_id='../foo'` → 422 en POST de mensaje; `media_info['url']='http://attacker.com'` → 502 sin segundo GET.
  - PoC dinámico documentado en `DONE.md` para cada uno de los 3 BUGs.
-->

---

_TASK-0080 — Fix estructural: MFA enforcement server-side + gate UI bloqueante: COMPLETADA. Ver `docs/DONE.md`._

<!--
### TASK-0080 — Fix estructural: MFA enforcement server-side + gate UI bloqueante (archivado)

- **Estado:** DONE (2026-05-13)
- **Causa raíz:** el control MFA es solo UI: la dependency `require_mfa_for_privileged` existe pero no está cableada a ningún router productivo, y el proxy BFF no chequea `_session_mfa_required`. La UI permite "Continuar sin MFA" descartando el banner. Resultado: cualquier sesión admin/owner/platform_owner sin segundo factor accede a operaciones privilegiadas.
- **Bugs cubiertos (2):**
  - **BUG14** (`docs/BUGS/BUG14`, commit `ff7c0dc`): UI overlay dismissible + proxy reenvía sin chequear MFA.
  - **BUG15** (`docs/BUGS/BUG15`, commit `3ba2e2f`): `require_mfa_for_privileged` no está adjunta a `tenant_admin_router` ni `platform_admin_router`; tests cubren la dependency aislada pero no su integración.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "require_mfa_for_privileged" app/` — confirmar dónde está adjunta hoy.
  2. Revisar `admin-panel/src/components/.../MfaOverlay.jsx` (o equivalente) — confirmar si el botón "Continuar sin MFA" sigue existiendo.
  3. Revisar el proxy BFF — confirmar si rechaza con 403 cuando `mfa_required=true`.
- **Fase 2 — remediación (causa raíz):**
  - **Server-side (fix de BUG15):** adjuntar `Depends(require_mfa_for_privileged)` a nivel de router en `tenant_admin_router` y `platform_admin_router`. Path "service account" (no humano) sigue funcionando porque `require_mfa_for_privileged` solo aplica a identidades Auth0 humanas.
  - **Proxy BFF (fix de BUG14, mitad servidor):** rechazar con 403 toda request privilegiada cuando la sesión tiene `mfa_required=true && mfa_verified=false`. Propagar el header `X-Session-MFA-Verified` al Core API.
  - **UI (fix de BUG14, mitad cliente):** el overlay MFA es bloqueante — no renderizar children mientras `mfa_required=true && mfa_verified=false`. Quitar el botón "Continuar sin MFA".
- **Criterios de aceptación:**
  - Test de integración por cada uno de los ~30 endpoints privileged enumerados: sesión `mfa_verified=false` → 403 `mfa_required`.
  - Test E2E (Playwright o stub) que con MFA pendiente NO se puede ejecutar PATCH desde la UI.
  - Test que el proxy rechaza con 403 una request privilegiada cuando `mfa_required=true`.
  - Test que service-account (sin MFA porque no aplica) sigue funcionando.
-->

---

_TASK-0081 — Fix estructural: binding webhook WhatsApp ↔ tenant_channel por phone_number_id: COMPLETADA. Ver `docs/DONE.md`._

<!--
### TASK-0081 — Fix estructural: binding webhook WhatsApp ↔ tenant_channel por phone_number_id (archivado)

- **Estado:** DONE (2026-05-13)
- **Causa raíz:** la cadena de validación del webhook WhatsApp ata el tenant al **primer** `phone_number_id` del payload y no garantiza uniqueness global de `phone_number_id` entre tenants. Resultado: (a) changes posteriores en el mismo payload se escriben en el tenant equivocado, y (b) un tenant puede registrar el `phone_number_id` de otro y secuestrar la validación de firma.
- **Bugs cubiertos (2):**
  - **BUG20** (`docs/BUGS/BUG20`, commit `af1e91c`): handler usa un único `channel/tenant_id` para todos los changes del payload, no re-resuelve por change.
  - **BUG21** (`docs/BUGS/BUG21`, commit `9cfbead`): `tenant_channels.phone_number_id` no tiene unique constraint global activa; el lookup del webhook puede seleccionar la fila duplicada del atacante y validar firma con su app_secret.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `infra/postgres/01-schema.sql` → ¿hay `UNIQUE INDEX ... WHERE status='active'` sobre `phone_number_id`?
  2. Re-leer `whatsapp_webhook_post` en routes → ¿itera por change re-resolviendo channel?
  3. Re-leer `create_channel` admin endpoint → ¿valida que el `phone_number_id` no esté activo en otro tenant?
- **Fase 2 — remediación (causa raíz, un solo fix):**
  - **Schema (fix de BUG21):** migration que agrega `CREATE UNIQUE INDEX ux_tenant_channels_phone_number_active ON app.tenant_channels(phone_number_id) WHERE status='active';`. Si la migration detecta duplicados existentes, falla con instrucción operacional (drill local pre-prod).
  - **Admin endpoint (fix de BUG21):** `create_channel` y `update_channel` rechazan con 409 si otro tenant ya tiene el `phone_number_id` activo. Claim de un número que ya estuvo en otro tenant requiere `platform_owner` (operación manual auditada).
  - **Webhook handler (fix de BUG20):** iterar `entry → changes → metadata.phone_number_id`. Para cada change: (a) re-resolver `channel = lookup_channel(phone_number_id, status='active')`; (b) verificar que el `app_secret` que firmó el payload matchea el del channel resuelto; si no matchea, descartar ese change con `audit_logs(action='webhook.phone_number_id_mismatch', detail={...})`; (c) setear `app.tenant_id` per change con transacción aislada antes de cada insert.
- **Criterios de aceptación:**
  - Test de schema: `create_channel` con `phone_number_id` activo en otro tenant → 409.
  - Test de handler (BUG20): payload firmado con app_secret de A que contiene un change con `phone_number_id` de B → change B descartado, audit emitido, ningún insert en A.
  - Test del rubric BUG21: dos rows con mismo `phone_number_id` activo → la DB lo previene (la migration tiraba antes).
  - PoC dinámico de las dos rutas documentado.
-->

---

### TASK-0082 — Fix estructural: validación de fuente y mutación de identidad de contacto

- **Estado:** PENDING
- **Causa raíz:** dos rutas distintas permiten que un actor no-confiable afecte la identidad/routing de un `contact` existente: el widget web (anónimo) lo hace por phone-match implícito; el endpoint de "iniciar conversación" lo hace por `wa_id` controlado por el agent. Ambos casos comparten el patrón "el contacto se resuelve por un campo que el caller controla, y luego se reusa/sobrescribe sin proof of ownership".
- **Bugs cubiertos (2):**
  - **BUG05** (`docs/BUGS/BUG05`, commit `eb786e8`): `POST /v1/web/chat/start` acepta `phone` del browser y reusa el contacto existente del tenant si coincide → impersonación.
  - **BUG22** (`docs/BUGS/BUG22`, commit `1ec5213`): `POST /v1/conversations/start` (rol `agent`+) acepta `wa_id` + `phone_e164` separados, upsertea por `(tenant_id, wa_id)` y sobrescribe `phone_e164/phone_hash` → redirige outbound al teléfono del atacante.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `web_chat_start` → ¿reusa contacto por `phone`?
  2. Re-leer `conversation_start` y `ConversationStart` schema → ¿acepta `wa_id` del cliente? ¿sobrescribe `phone_e164` en conflict?
- **Fase 2 — remediación (causa raíz):**
  - **Principio compartido:** un contacto solo se identifica por canal de origen verificado. Mutación de campos de identidad (`phone_e164`, `wa_id`) requiere flujo separado con auth elevada.
  - **BUG05 — widget web:** crear siempre un `contact` nuevo con `channel='web'` y `wa_id=null`. Si el widget captura phone, encolar `phone_verification_challenge` (OTP via SMS/WhatsApp) y solo entonces mergear con un contacto existente. Orquestador rechaza acciones contact-scoped (cancel/feedback) si el contacto está en estado `unverified_web`.
  - **BUG22 — conversation/start:** `ConversationStart` schema NO acepta `wa_id`. El cliente pasa `contact_id` (UUID) si quiere conversar con uno existente; o pasa `phone_e164` para crear uno nuevo (validando que NO existe ya). Cambiar `phone_e164` de un contacto existente requiere un endpoint separado `PATCH /v1/contacts/{id}/phone` con rol `manager`+ y `audit_logs(action='contact.phone_changed')` obligatorio.
- **Criterios de aceptación:**
  - BUG05: test estático que `phone` enviado por widget NO altera/reusa ningún `contact` existente; test que mensaje "no" desde widget sin OTP NO cambia `confirmation_status` de citas pre-existentes.
  - BUG22: test que agente con POST `wa_id=<victima>` + `phone_e164=<atacante>` → 403/422; test que `PATCH /contacts/{id}/phone` requiere `manager` y produce audit.

---

### TASK-0083 — Webhook de pagos fail-closed con secret obligatorio

- **Estado:** PENDING
- **Causa raíz:** `POST /v1/webhooks/payments/{provider}` inicializa `signature_ok = True` y solo verifica firma si el tenant tiene `webhook_secret_ref` configurado. Sin secret → cualquier payload anónimo con un UUID de `appointment` válido marca la cita como `payment_status='paid'`. Es el único bug en su clase (las otras superficies webhook son Meta o suscripciones, ya cubiertas).
- **Bugs cubiertos (1):**
  - **BUG04** (`docs/BUGS/BUG04`, commit `3201a6c`): payment webhook fail-open + UI permite habilitar provider sin secret.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer el handler del webhook de pago y el helper `verify_stripe_signature` / `verify_mercadopago_signature`.
  2. Confirmar si HEAD rechaza con 401/503 cuando el tenant no tiene `webhook_secret_ref`.
  3. Confirmar si el módulo admin de pagos exige el secret antes de habilitar el provider.
- **Fase 2 — remediación:**
  - `signature_ok = False` por default. Sin secret configurado → 503 `payment.webhook_unconfigured`. NO procesar el appointment.
  - Admin schema Pydantic `PaymentProviderConfig` exige `webhook_secret` antes de aceptar `enabled=true`. La UI del módulo de pagos refleja la restricción.
  - Audit obligatorio `payment.webhook_rejected` con el motivo (`missing_secret`, `bad_signature`).
- **Criterios de aceptación:**
  - Test PoC: payload Stripe `checkout.session.completed` falso con UUID válido y sin secret tenant → 503, cita NO se marca `paid`.
  - Test: tenant con secret pero payload sin header `Stripe-Signature` → 401.
  - Test: admin habilita provider sin secret → 422.

---

### TASK-0084 — Operaciones financieras de paquetes requieren admin + `payment_status` server-only

- **Estado:** PENDING
- **Causa raíz:** los endpoints de asignación, patch y refund de `contact_packages` se montaron en `tenant_ops_router` (rol `agent`+) y los schemas aceptan `payment_status='paid'` y `payment_amount=0`. Un agent puede otorgar paquetes pagados y disparar refunds sin pasar por la pasarela. Es un bug aislado de input hardening + RBAC del módulo paquetes.
- **Bugs cubiertos (1):**
  - **BUG02** (`docs/BUGS/BUG02`, commit `177389d`): contact package mutation accessible to agent + `payment_status` controlable por cliente.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "contact_packages\|treatment_package" app/api/v1/routes.py` y confirmar el router actual.
  2. Re-leer `ContactPackageCreate/Patch` en `app/api/v1/schemas.py`.
  3. Buscar si TASK-0075 u otra ya migró el patrón "payment_status solo lo escribe el webhook firmado".
- **Fase 2 — remediación:**
  - Mover los endpoints de mutación a `tenant_admin_router` (mínimo `admin`).
  - En los schemas, restringir `payment_status` a `'unpaid'` para writes del cliente. La transición a `'paid'` solo ocurre en el handler del webhook de pago (TASK-0083 hardened).
  - El refund (transición a `'refunded'`) requiere `admin` + `audit_logs(action='contact_package.refunded')` con user_id, monto, motivo.
- **Criterios de aceptación:**
  - Test estático del router montado en `tenant_admin_router`.
  - Test que POST con `payment_status='paid'` desde cliente externo → 422 / sobrescrito a `unpaid`.
  - Test de auditoría con la entrada `contact_package.refunded` por `admin`.

---

### TASK-0085 — Invitación Auth0 por user_id en lugar de email

- **Estado:** PENDING
- **Causa raíz:** el endpoint de invitación de miembros llama a Auth0 `/tickets/password-change` pivoteando por email del invitado. Auth0 devuelve un password-reset ticket válido para cualquier cuenta Auth0 existente con ese email (incluyendo cuentas plataforma/soporte). El backend retorna el ticket URL al admin que invita, convirtiendo el flow en un account takeover primitive.
- **Bugs cubiertos (1):**
  - **BUG06** (`docs/BUGS/BUG06`, commit `500953d`): Auth0 reset ticket exposed via tenant invite.
- **Fase 1 — verificación en HEAD:**
  1. `grep -rn "tickets/password-change\|invite_user" app/` para localizar el helper.
  2. Confirmar si HEAD crea/bind un Auth0 user nuevo por `user_id` antes de generar el ticket.
  3. Confirmar si el ticket URL se propaga al inviter o se envía directamente al destinatario.
- **Fase 2 — remediación:**
  - Crear primero el usuario Auth0 (`POST /api/v2/users`) con email y `email_verified=false`. Capturar el `user_id`.
  - Generar el ticket con `user_id` (no con email) y enviarlo directamente al destinatario vía Auth0 Email Template o nuestro propio mail. La API NO devuelve el ticket URL al inviter.
  - Si el email ya existe en Auth0, retornar 409. El admin usa el flow alterno "add existing user to tenant" que requiere accept del destinatario.
- **Criterios de aceptación:**
  - Test: la respuesta de invitación NO incluye `ticket_url`.
  - Test: si el email ya existe en Auth0 (mock) → 409.
  - Test: `audit_logs(action='user.invited')` captura `auth0_user_id`, no email plano.

---

### TASK-0086 — Clasificador LLM cloud asíncrono con timeout efectivo

- **Estado:** PENDING
- **Causa raíz:** `app/services/intent_classifier.py::_llm_classify` instancia clientes **síncronos** Anthropic/OpenAI y llama `create()` desde dentro de una función `async`, sin pasar `timeout`. Cada mensaje WhatsApp que no matchea regla regex de alta confianza bloquea el event loop hasta que el proveedor responde o cuelga. Un attacker puede inundar el webhook con mensajes ambiguos y tumbar el servicio.
- **Bugs cubiertos (1):**
  - **BUG09** (`docs/BUGS/BUG09`, commit `bced236`): blocking cloud LLM classifier enables webhook DoS.
- **Fase 1 — verificación en HEAD:**
  1. Re-leer `app/services/intent_classifier.py` → ¿usa `AsyncAnthropic` / `AsyncOpenAI` con `await`?
  2. Confirmar si `cloud_llm_timeout` configurado en `tenant_settings` se propaga al SDK.
  3. Confirmar si TASK-0059 (rate limit + circuit breaker) ya envuelve estas llamadas.
- **Fase 2 — remediación:**
  - Migrar a `AsyncAnthropic(api_key=..., timeout=settings.cloud_llm_timeout)` y `AsyncOpenAI(...)` con `await client.messages.create(...)`.
  - Si por alguna razón se mantiene un cliente síncrono, ejecutar en `asyncio.to_thread` envuelto en `asyncio.wait_for(timeout=...)`.
  - El classifier corre **después** del dedup/idempotency/rate-limit gate para que un attacker no llegue al sink LLM sin pagar el costo de los gates baratos.
- **Criterios de aceptación:**
  - Test estático que confirma uso de `AsyncAnthropic`/`AsyncOpenAI` y `timeout` parametrizado.
  - Test que un proveedor mock que `raise asyncio.TimeoutError` cae en `fallback` sin colgar el event loop (medido con event loop monitor: latencia P99 de otras tareas concurrentes < 200ms).

---
