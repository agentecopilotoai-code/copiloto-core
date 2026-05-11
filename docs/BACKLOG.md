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
TASK-0027 (analítica completa de negocio)
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

### TASK-0030 — Booking flow completo con disponibilidad real y flow guiado por bot

- **Objetivo:** el orquestador actual detecta la intención `book_appointment` pero solo recolecta preferencias en texto libre — nunca consulta disponibilidad real ni crea la cita. Para producción, el bot debe guiar al cliente paso a paso (servicio → profesional → fecha → slot disponible → confirmación → cita creada) usando los mensajes interactivos de TASK-0034 y el catálogo de TASK-0033.
- **Alcance mínimo — backend:**
  - Endpoint `GET /v1/tenants/{tenant_id}/resources/{resource_id}/availability`:
    - Parámetros: `date` (YYYY-MM-DD) obligatorio, `service_id` opcional (para calcular la duración del slot correctamente).
    - Lee `resources.capabilities.working_hours` (estructura: `{mon: [{start:'09:00', end:'18:00'}], ...}`).
    - Calcula slots libres restando citas activas (`provisional`, `confirmed`, `rescheduled`) con solapamiento.
    - La duración del slot viene de `service_catalog.duration_minutes` (si se pasa `service_id`) o del campo `service_durations` en `tenant_settings` como fallback.
    - Devuelve: `{date, resource_id, service_duration_minutes, slots: [{start_time, end_time}]}`.
  - Endpoint `GET /v1/tenants/{tenant_id}/availability`:
    - Dado `service_id` y `date`, devuelve todos los recursos activos con slots libres para ese servicio ese día.
    - Útil para que el bot ofrezca "María disponible a las 10:00, Carlos a las 14:00".
  - Campo `service_id uuid` en `appointments` (FK a `service_catalog`, nullable para no romper el endpoint existente de creación).
  - Actualizar el flow conversacional (`rag_orchestrator.py`) cuando `current_intent = book_appointment`:
    - **Paso 1:** consultar catálogo del tenant; si hay servicios, enviar lista interactiva `send_interactive_list` con los servicios disponibles.
    - **Paso 2:** si hay múltiples profesionales/recursos para ese servicio, enviar lista interactiva con opciones.
    - **Paso 3:** preguntar fecha deseada (texto libre o botones de "Hoy", "Mañana", "Elegir fecha").
    - **Paso 4:** consultar `GET /availability` con la fecha y servicio elegidos; si hay slots, enviar los primeros 3 como botones interactivos. Si no hay slots, informar y sugerir la próxima fecha disponible.
    - **Paso 5:** al confirmar slot, crear `appointment` con `service_id`, `resource_id`, `starts_at`, `ends_at` calculados desde duración del servicio. Estado inicial `provisional`.
    - **Paso 6:** confirmar al cliente con resumen de la cita (fecha, hora, servicio, profesional).
    - Estado del flow se persiste en `conversations.metadata.booking_flow` entre turnos.
  - Si el catálogo está vacío, el bot usa el flujo de texto libre anterior (sin lista interactiva) — el admin puede configurar sin catálogo en desarrollo.
  - Tests estáticos: cálculo de slots libres con citas existentes, día sin disponibilidad sugiere próxima fecha, flow multi-paso estado a estado (mock de cada transición), creación de cita al final del flow, catálogo vacío no rompe el flow.
- **Alcance mínimo — Admin Panel:**
  - En `OperationsDesk.jsx`, sección de recursos: formulario de creación/edición incluye builder de **horario laboral** (toggle por día de semana, hora inicio y fin, opción de múltiples franjas por día). Se persiste en `resources.capabilities.working_hours`.
  - Vista de **calendario semanal** en `OperationsDesk.jsx`: muestra appointments activos por recurso. Consume el endpoint de disponibilidad para resaltar slots libres en verde.
  - En `TenantSetupWizard.jsx`, pestaña existente (o integrar en "Servicios"): configurar `service_durations` como fallback cuando no hay catálogo.
- **Criterio de aceptación:** dado recurso con horario 9:00–18:00 y una cita 10:00–11:00, el endpoint devuelve los slots libres correctamente; el bot guía el booking completo en WhatsApp usando interactivos; al final crea la cita sin conflicto; el calendario muestra la agenda real; tests pasan en CI.
- **Dependencias:** TASK-0033 (catálogo de servicios), TASK-0034 (mensajes interactivos).

---

### TASK-0031 — Gestión de plantillas WhatsApp y notificaciones automáticas de cita

- **Objetivo:** las notificaciones de cita (confirmación, recordatorios, seguimiento) requieren templates aprobados por Meta para enviarse fuera de la ventana de 24h. Sin templates configurados el sistema no puede notificar al cliente — todo el trabajo de TASK-0035 y TASK-0036 no funciona en producción. Esta tarea crea el sistema completo de gestión de plantillas por tenant.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.whatsapp_templates`:
    - `id uuid PK`, `tenant_id`, `channel_id FK`, `name text NOT NULL`, `locale char(5) DEFAULT 'es'`, `category text CHECK(category IN ('utility','marketing','authentication'))`, `status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','pending','approved','rejected','paused'))`, `purpose text NOT NULL CHECK(purpose IN ('appointment_confirmation','appointment_reminder_24h','appointment_reminder_1h','appointment_reminder_custom','no_show_confirmation_request','no_show_followup','post_appointment_instructions','post_appointment_feedback','post_appointment_rebooking','reschedule_offer','campaign_promo','payment_request','custom'))`, `components jsonb NOT NULL` (header/body/footer/buttons según spec Meta), `meta_template_id text`, `rejection_reason text`, `created_at timestamptz DEFAULT now()`, `updated_at timestamptz DEFAULT now()`. RLS por `tenant_id`.
  - Función `send_whatsapp_template(conn, tenant_id, wa_phone, template_name, variables: dict)` que construye el payload de template Meta y lo encola al worker existente.
  - En `scheduler.py`: antes de ejecutar un `reminder_job`, verificar que existe un template aprobado para el `purpose` del job. Si no → job `failed` con error `template_not_approved:{purpose}`.
  - Endpoints:
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates` — registrar template y enviarlo a revisión a Meta Graph API.
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates` — listar.
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — detalle.
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates/sync` — actualizar status de todos desde Meta.
    - `DELETE /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — eliminar en DB y en Meta.
  - Tests estáticos: creación de template, validación de `purpose` y `category`, scheduler rechaza job sin template aprobado, envío con variables.
- **Alcance mínimo — Admin Panel:**
  - En `WhatsAppOnboarding.jsx`, nueva sección **"Plantillas de mensajes"**:
    - Lista con badge de estado (Aprobado/Pendiente/Rechazado) y motivo de rechazo.
    - Formulario: nombre, idioma, categoría, propósito (selector del enum), editor de componentes (header texto, body con variables `{{1}}`, footer, botones).
    - Botón **"Sincronizar estado con Meta"**.
    - Semáforo por propósito: verde = aprobado, amarillo = pendiente, rojo = faltante.
  - En `GoLiveReadiness.jsx`: check **"Plantillas mínimas aprobadas"** que exija templates aprobados para `appointment_confirmation` y `appointment_reminder_24h`.
- **Criterio de aceptación:** admin crea y sincroniza template; scheduler rechaza job con error descriptivo si template no está aprobado; readiness check detecta templates faltantes; tests pasan en CI.
- **Dependencias:** TASK-0030 (para que el booking use templates de confirmación).

---

### TASK-0035 — Confirmaciones automáticas y recordatorios configurables

- **Objetivo:** cuando se crea una cita (por el bot o desde Operations Desk), el sistema envía automáticamente: confirmación inmediata con detalles y ubicación, recordatorio configurable 24h antes, recordatorio configurable 1h antes. Todo configurable desde el admin por tenant, sin código. Este flujo es la diferencia entre un sistema de agendamiento básico y uno que reduce no-shows.
- **Alcance mínimo — backend:**
  - Al crear un `appointment` (endpoint `POST /v1/appointments`), crear automáticamente los `reminder_jobs` que el tenant tenga activos:
    - `appointment_confirmation` → `scheduled_for = now()` (envío casi inmediato).
    - `appointment_reminder_24h` → `scheduled_for = starts_at - 24h` (si está activo en settings).
    - `appointment_reminder_1h` → `scheduled_for = starts_at - 1h` (si está activo en settings).
  - Función `create_appointment_reminder_jobs(conn, tenant_id, appointment_id)` que lee `tenant_settings.notification_settings` para decidir qué jobs crear.
  - Campo `notification_settings jsonb NOT NULL DEFAULT '{}'` en `tenant_settings` con estructura:
    ```json
    {
      "confirmation_enabled": true,
      "reminder_24h_enabled": true,
      "reminder_1h_enabled": false,
      "include_location_link": true,
      "location_address": "",
      "location_maps_url": "",
      "include_preparation_notes": true
    }
    ```
  - El mensaje de confirmación incluye variables del template: nombre del cliente, nombre del servicio, fecha y hora, nombre del profesional, dirección, link Maps, instrucciones de preparación del servicio (de `service_catalog.preparation_notes`).
  - Al reprogramar una cita: cancelar jobs pendientes del appointment anterior y crear nuevos para la nueva hora.
  - Al cancelar una cita: cancelar todos los jobs pendientes (`scheduled` → `cancelled`).
  - Tests estáticos: jobs creados al crear cita, cancelación de jobs al cancelar cita, regeneración de jobs al reprogramar, cada toggle de `notification_settings` activa/desactiva correctamente el job correspondiente.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, nueva pestaña **"Notificaciones"**:
    - Sección **"Confirmación de cita"**: toggle activo/inactivo.
    - Sección **"Recordatorios"**: toggle 24h (activo/inactivo), toggle 1h (activo/inactivo).
    - Sección **"Ubicación"**: campo dirección, campo URL de Google Maps, toggle incluir en mensajes.
    - Sección **"Instrucciones"**: toggle incluir instrucciones de preparación del servicio.
    - Preview de texto de cómo se vería el mensaje de confirmación al cliente con los datos configurados.
  - En `ServiceCatalog.jsx` (TASK-0033): exponer el campo **"Instrucciones de preparación"** ya definido en el schema para que el admin lo complete por servicio.
- **Criterio de aceptación:** al crear cita se generan los jobs activos configurados; al reprogramar se regeneran; al cancelar se cancelan; el preview en el admin panel refleja la configuración actual; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates), TASK-0033 (catálogo con instrucciones).

---

### TASK-0036 — Reducción de no-show y flujo post-cita configurable

- **Objetivo:** cerrar el ciclo del cliente con dos flujos críticos: (A) confirmación activa de asistencia N horas antes con opción de reagendar fácil; (B) seguimiento post-cita automático con instrucciones, solicitud de calificación e invitación a nueva cita. Ambos flujos 100% configurables desde el admin. Este es el diferenciador que convierte clientes únicos en recurrentes.
- **Alcance mínimo — backend:**

  **A. Confirmación activa (reducción de no-show):**
  - Nuevo `reminder_job` propósito `no_show_confirmation_request`: se crea al confirmar la cita, se ejecuta N horas antes (configurable, default 4h). Mensaje: "¿Confirmas tu cita de {{servicio}} el {{fecha}} a las {{hora}}? Responde Sí o No".
  - Cuando el cliente responde, el orquestador detecta `confirm_appointment` o `cancel_appointment` y actualiza `appointments.confirmation_status = 'confirmed' | 'declined'`.
  - Si declina → el bot activa directamente el flow de reagendamiento (TASK-0030).
  - Si no responde en 2h después del job → nuevo job `no_show_followup` con mensaje "Tu cita está próxima, ¿necesitas cambiarla?".
  - Campo `confirmation_reminder_hours int DEFAULT 4` dentro de `notification_settings`.

  **B. Flujo post-cita:**
  - Job `post_appointment_instructions` → `scheduled_for = ends_at + N minutos` (configurable, default 30). Envía `service_catalog.post_service_notes`.
  - Job `post_appointment_feedback` → `scheduled_for = ends_at + N horas` (configurable, default 2). Mensaje: "¿Cómo fue tu {{servicio}}? Califica del 1 al 5 ⭐".
  - Job `post_appointment_rebooking` → `scheduled_for = ends_at + N días` (configurable, default 30). Mensaje configurable de invitación a nueva cita.
  - Nueva tabla `app.appointment_feedback`:
    - `id uuid PK`, `tenant_id`, `appointment_id FK`, `contact_id FK`, `rating int CHECK(rating BETWEEN 1 AND 5)`, `comment text`, `created_at timestamptz DEFAULT now()`. RLS por `tenant_id`.
  - Cuando el cliente responde con número 1–5, el orquestador registra en `appointment_feedback`.
  - Respuesta positiva al mensaje de rebooking → activa flow de booking (TASK-0030).
  - Configuración en `tenant_settings.notification_settings`:
    ```json
    {
      "confirmation_reminder_hours": 4,
      "post_instructions_delay_minutes": 30,
      "post_instructions_enabled": true,
      "post_feedback_delay_hours": 2,
      "post_feedback_enabled": true,
      "post_rebooking_delay_days": 30,
      "post_rebooking_enabled": false,
      "post_rebooking_message": ""
    }
    ```
  - Tests estáticos: job de confirmación activa creado al confirmar cita, respuesta "sí" actualiza `confirmation_status`, respuesta "no" inicia flow de reagendamiento, jobs post-cita creados al completar appointment, feedback registrado con calificación válida, calificación inválida ignorada.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, pestaña **"Notificaciones"** (extendida de TASK-0035):
    - Sección **"Reducción de no-show"**: toggle confirmación activa, campo horas antes.
    - Sección **"Post-cita"**: toggle instrucciones (horas delay), toggle feedback (horas delay), toggle invitación a nueva cita (días delay + campo de mensaje personalizable).
  - En `OperationsDesk.jsx`, detalle de cita: badge `confirmation_status` (Pendiente / Confirmada / Rechazada) y calificación recibida (estrellas si existe).
  - En `ServiceCatalog.jsx`: campo editable **"Instrucciones post-servicio"** por servicio.
- **Criterio de aceptación:** sistema envía confirmación activa, respuesta actualiza estado de cita, feedback se registra con calificación 1–5, invitación a rebooking está configurable; todo configurable desde admin; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates), TASK-0035 (confirmación básica).

---

### TASK-0037 — CRM básico: historial de contacto, etiquetas y notas internas

- **Objetivo:** los agentes y el bot operan sin contexto del historial del cliente. Un CRM básico permite etiquetar contactos por perfil (ej. "VIP", "Nuevo", "En tratamiento"), ver todo su historial de citas y conversaciones, y agregar notas internas. Es la base para la segmentación de TASK-0038 (campañas).
- **Alcance mínimo — backend:**
  - Nueva tabla `app.contact_tags` (etiquetas disponibles del tenant):
    - `id uuid PK`, `tenant_id`, `name text NOT NULL`, `color varchar(7)` (hex), `description text`, timestamps. UNIQUE `(tenant_id, name)`. RLS por `tenant_id`.
  - Nueva tabla `app.contact_tag_assignments`:
    - `contact_id uuid FK`, `tag_id uuid FK`, `assigned_by uuid FK → users(id)`, `assigned_at timestamptz DEFAULT now()`. PK `(contact_id, tag_id)`. RLS vía `tenant_id` en `contact_tags`.
  - Nueva tabla `app.contact_notes`:
    - `id uuid PK`, `tenant_id`, `contact_id FK`, `body text NOT NULL`, `created_by uuid FK → users(id)`, timestamps. RLS por `tenant_id`.
  - Endpoints:
    - `GET /v1/tenants/{tenant_id}/contact-tags` — listar etiquetas del tenant.
    - `POST /v1/tenants/{tenant_id}/contact-tags` — crear etiqueta.
    - `PATCH /v1/tenants/{tenant_id}/contact-tags/{tag_id}` — editar nombre/color.
    - `DELETE /v1/tenants/{tenant_id}/contact-tags/{tag_id}` — eliminar (y desasignar de todos los contactos).
    - `POST /v1/contacts/{contact_id}/tags` — asignar etiquetas (body: `{tag_ids: [...]}`).
    - `DELETE /v1/contacts/{contact_id}/tags/{tag_id}` — quitar etiqueta.
    - `POST /v1/contacts/{contact_id}/notes` — crear nota interna.
    - `GET /v1/contacts/{contact_id}/notes` — listar notas.
    - `GET /v1/contacts/{contact_id}/profile` — perfil completo: datos del contacto, etiquetas asignadas, últimas 10 citas (con estado y servicio), últimas 5 conversaciones, calificaciones promedio, notas internas, total de citas, fecha primera y última visita.
  - En el endpoint de inbox `GET /v1/conversations` (lista), incluir `tags` del contacto en cada item.
  - Tests estáticos: CRUD de etiquetas de tenant, asignación/desasignación a contacto, CRUD de notas, perfil completo del contacto con historial, inbox incluye tags.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Contactos"** (`admin-panel/src/components/modules/contacts/ContactsModule.jsx`):
    - Lista de contactos con búsqueda por nombre/teléfono, filtro por etiqueta, paginación.
    - Al hacer clic: perfil completo con historial de citas, conversaciones, calificaciones y notas.
    - Desde el perfil: asignar/quitar etiquetas, agregar nota interna.
  - En `TenantSetupWizard.jsx`, sección en pestaña "Negocio": gestión de etiquetas del tenant (crear, editar color, eliminar).
  - En `OperationsDesk.jsx`, header del detalle de conversación: chips de etiquetas del contacto, botón para asignar/quitar etiquetas, campo de nota rápida.
  - En el inbox del Operations Desk: chips de etiquetas visibles en cada card de conversación.
- **Criterio de aceptación:** admin crea etiquetas, agente las asigna desde conversación, perfil muestra historial completo, inbox muestra etiquetas, filtro por etiqueta funciona, tests pasan en CI.
- **Dependencias:** TASK-0036 (feedback visible en el perfil).

---

### TASK-0027 — Panel de analítica completa del negocio

- **Objetivo:** el rol `manager` no puede medir si el sistema está funcionando. Sin métricas de conversión, no-show, ingresos y retención, la empresa no puede justificar la inversión ni tomar decisiones. Esta tarea implementa los endpoints de analytics y el panel visual con los KPIs más importantes del journey cliente.
- **Alcance mínimo — backend:**
  - `GET /v1/analytics/overview`: `from_date`, `to_date` (default 30 días); requiere rol `manager` + `X-Tenant-Id`. Devuelve:
    - Conversaciones: total, abiertas, resueltas, en handoff, tasa de handoff `%`.
    - Citas: creadas, confirmadas, completadas, canceladas, no-shows, tasa de no-show `%` = `no_shows / (completadas + no_shows)`.
    - Ingreso estimado: suma de `service_catalog.price_amount` de citas completadas en el período.
    - Feedback: promedio de calificaciones 1–5, total de calificaciones recibidas.
    - Mensajes: inbound y outbound totales.
    - Retención: `% de contactos con ≥ 2 citas completadas` en los últimos 90 días.
  - `GET /v1/analytics/conversations`: mismo filtro. Devuelve top 10 intenciones, distribución de estados, tiempo promedio de primer mensaje del bot, evolución diaria `[{date, count}]`.
  - `GET /v1/analytics/appointments`: mismo filtro. Devuelve servicios más agendados, distribución por estado, no-shows por día de la semana, evolución diaria de creadas vs. completadas.
  - `GET /v1/analytics/contacts`: mismo filtro. Devuelve nuevos vs. recurrentes, top etiquetas, tasa de opt-out, distribución por fuente de contacto.
  - Sin tablas nuevas; todo calcula directamente con SQL sobre tablas existentes + `service_catalog` + `appointment_feedback`.
  - Tests estáticos: estructura de respuesta de cada endpoint, autorización (`agent` → 403, `manager` → 200), cálculo de tasa de no-show, cálculo de ingreso estimado, evolución diaria.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Analítica"** (`admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx`):
    - Selector de rango de fechas: 7d / 30d / 90d / personalizado.
    - Cards de KPIs: conversaciones, citas completadas, tasa de no-show, ingreso estimado, calificación promedio.
    - Gráfico de evolución diaria de conversaciones (SVG nativo o tabla con mini barras CSS — sin librerías externas).
    - Gráfico de evolución diaria de citas (completadas vs. canceladas).
    - Tabla de top intenciones con conteo y %.
    - Tabla de servicios más solicitados.
    - Cards de distribución de citas por estado.
  - Registrar en sidebar, accesible para `manager` o superior.
- **Criterio de aceptación:** manager ve KPIs coherentes con los datos de la DB; agent recibe 403; tasa de no-show se calcula correctamente; módulo en sidebar; tests pasan en CI.
- **Dependencias:** TASK-0036 (datos de feedback y no-show), TASK-0037 (datos de etiquetas).

---

### TASK-0038 — Campañas y mensajes masivos a segmentos de contactos

- **Objetivo:** convertir el directorio de contactos en un motor de retención activa. El negocio necesita enviar mensajes a grupos de clientes (promociones, recordatorios estacionales, reactivación de clientes inactivos) sin salir de la plataforma. Solo se pueden usar templates aprobados de WhatsApp para cumplir la política de Meta.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.campaigns`:
    - `id uuid PK`, `tenant_id`, `name text NOT NULL`, `status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','scheduled','running','completed','cancelled'))`, `template_id uuid FK → whatsapp_templates(id)`, `template_variables jsonb DEFAULT '{}'`, `segment_filter jsonb NOT NULL DEFAULT '{}'` (criterios: `{tags:[...], min_appointments:N, last_visit_before_days:N, last_visit_after_days:N, has_upcoming_appointment:bool}`), `scheduled_at timestamptz`, `recipient_count int`, `sent_count int DEFAULT 0`, `delivered_count int DEFAULT 0`, `read_count int DEFAULT 0`, `failed_count int DEFAULT 0`, timestamps. RLS por `tenant_id`.
  - Endpoints:
    - `POST /v1/tenants/{tenant_id}/campaigns` — crear campaña.
    - `GET /v1/tenants/{tenant_id}/campaigns` — listar con métricas.
    - `PATCH /v1/tenants/{tenant_id}/campaigns/{id}` — editar campaña en borrador.
    - `POST /v1/tenants/{tenant_id}/campaigns/{id}/preview` — devuelve conteo de destinatarios y primeros 5 contactos según `segment_filter`.
    - `POST /v1/tenants/{tenant_id}/campaigns/{id}/launch` — pasa a `scheduled`; si `scheduled_at ≤ now()` inicia inmediatamente.
    - `POST /v1/tenants/{tenant_id}/campaigns/{id}/cancel` — cancela campaña.
  - Worker de campañas (en el scheduler): detecta campañas `scheduled` con `scheduled_at ≤ now()`, pasa a `running`, evalúa `segment_filter` contra `contacts` + `contact_tag_assignments` + `appointments`, encola template message a cada destinatario con `opt_in_status NOT IN ('suppressed','opted_out')`. Rate limiting: máximo 20 mensajes/segundo por tenant. Actualiza contadores (`sent_count`, `delivered_count`) con los status updates del webhook.
  - Tests estáticos: evaluación de `segment_filter`, exclusión de contactos opt-out, rate limiting, conteo de destinatarios, estructura de campaña.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Campañas"** (`admin-panel/src/components/modules/campaigns/CampaignsModule.jsx`):
    - Lista con estado, fecha, destinatarios, métricas de entrega.
    - Formulario: nombre, template (solo `approved`), variables del template, filtros de segmento (etiquetas, mínimo de citas, última visita hace N días), fecha/hora de envío.
    - Botón **"Ver destinatarios estimados"** con conteo y muestra de los primeros 5.
    - Vista de resultados con barras de progreso enviados/entregados/leídos/fallidos.
  - Registrar en sidebar, accesible para `admin` o superior.
- **Criterio de aceptación:** admin crea campaña, previsualiza destinatarios, programa envío; worker envía solo a contactos activos con opt-in; métricas se actualizan con webhooks de status; no se envía a suprimidos; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates aprobados), TASK-0037 (etiquetas de contactos).

---

### TASK-0039 — Widget web y formulario de captura de leads desde sitio web

- **Objetivo:** ampliar los canales de captación más allá de WhatsApp. El widget es un script JavaScript que el negocio embebe en su sitio web y que abre un chat flotante conectado directamente a CopilotoIA, creando contacto y conversación automáticamente y enrutando la respuesta del bot igual que WhatsApp.
- **Alcance mínimo — backend:**
  - Canal `web` en `tenant_channels`: `provider = 'web'`. La tabla ya soporta providers adicionales — no requiere cambios de esquema.
  - Endpoints públicos (autenticados con `widget_token` firmado, no con JWT de usuario):
    - `POST /v1/web/chat/start` — inicia conversación. Body: `{tenant_slug, name, phone?, email?, message, utm_source?, utm_medium?, utm_campaign?, referrer?}`. Devuelve `{conversation_id, session_token}`. El `session_token` es JWT firmado con `SECRET_KEY`, expira en 24h, contiene `conversation_id` y `contact_id`.
    - `POST /v1/web/chat/{conversation_id}/messages` — enviar mensaje (autenticado con `session_token`). Devuelve respuesta del bot.
    - `GET /v1/web/chat/{conversation_id}/messages` — historial de la sesión.
  - El orquestador RAG procesa mensajes web igual que WhatsApp; `channel_type = 'web'` en `messages`.
  - Campo `lead_source jsonb NOT NULL DEFAULT '{}'` en `contacts`: `{channel, utm_source, utm_medium, utm_campaign, referrer, first_contact_at}`. Poblado al crear el contacto desde el widget.
  - `widget_token` del tenant en `.secrets/tenants/{id}/widget_token`.
  - Tests estáticos: inicio de sesión web, generación y validación de `session_token`, envío de mensaje, extracción de UTMs en `lead_source`, rechazo de `session_token` expirado.
- **Alcance mínimo — Admin Panel:**
  - Nueva sección en `WhatsAppOnboarding.jsx` (o módulo **"Canales"**): pestaña **"Widget Web"**:
    - Toggle: activar canal web.
    - Campo: dominio(s) permitidos (para CORS).
    - Generador de snippet: `<script src=".../widget.js" data-tenant="{slug}" data-color="{hex}" data-greeting="..."></script>`.
    - Botón copiar snippet al portapapeles.
  - Widget JS embebible: `admin-panel/public/widget.js` — script sin dependencias externas que abre iframe flotante en esquina inferior derecha. El iframe sirve `/web/chat/ui?tenant={slug}`. Configurable vía atributos `data-color` y `data-greeting` del script tag.
  - En `AnalyticsPanel.jsx` (TASK-0027): distribución de contactos por `lead_source.channel`.
- **Criterio de aceptación:** snippet embebible en cualquier HTML; widget inicia conversación y respuesta del bot llega en < 3s; la conversación aparece en Operations Desk inbox; `lead_source` queda registrado; tests pasan en CI.
- **Dependencias:** TASK-0033 (catálogo para respuestas del bot), TASK-0037 (`lead_source` en contactos).

---

### TASK-0040 — Links de pago y registro de pagos en citas

- **Objetivo:** muchos negocios requieren pago previo o al momento del servicio. Esta tarea agrega soporte básico para generar links de pago (MercadoPago / Stripe) que el bot o el agente envía al cliente, y para registrar el estado del pago en la cita. No se implementa pasarela propia: solo integración con proveedores externos vía sus APIs de links de pago.
- **Alcance mínimo — backend:**
  - Columnas en `appointments`: `payment_status text DEFAULT 'not_required' CHECK(payment_status IN ('not_required','pending','link_sent','paid','failed'))`, `payment_amount numeric(10,2)`, `payment_currency char(3) DEFAULT 'COP'`, `payment_link text`, `payment_provider_reference text`.
  - `app/services/payment_provider.py`: función `generate_payment_link(provider, api_key, amount, currency, description, external_ref) → url` con soporte para MercadoPago (Preference API) y Stripe (Payment Link API).
  - Endpoints:
    - `POST /v1/appointments/{id}/payment-link` — genera link y lo guarda en el appointment. Requiere `payment_provider` y `payment_api_key_ref` en `tenant_settings`.
    - `POST /v1/appointments/{id}/send-payment` — envía el link por WhatsApp al cliente.
    - `PATCH /v1/appointments/{id}/payment-status` — actualizar estado manualmente.
    - `POST /v1/webhooks/payments/{provider}` — webhook de confirmación; verifica firma del proveedor, actualiza `payment_status = 'paid'`, envía mensaje de confirmación al cliente.
  - Campo `payment_provider text` (enum libre: `'mercadopago'|'stripe'|'none'`) y referencia `payment_api_key_ref` en `tenant_settings`. La API key real en `.secrets/tenants/{id}/payment_api_key`.
  - Tests estáticos: generación de link con mock del proveedor, actualización de estado, webhook de confirmación, verificación de firma, rechazo si no hay proveedor configurado.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, nueva sección **"Pagos"**: selector de proveedor (MercadoPago / Stripe / Sin pagos), campo API key (enmascarada), moneda por defecto.
  - En `OperationsDesk.jsx`, detalle de cita: badge de `payment_status`, botón **"Generar link"**, botón **"Enviar por WhatsApp"** (activo cuando hay link), campo editable de monto.
- **Criterio de aceptación:** admin configura proveedor desde panel; agente genera link y lo envía al cliente; webhook del proveedor actualiza estado a `paid`; tests pasan en CI.
- **Dependencias:** TASK-0030 (el booking puede solicitar pago al final del flow), TASK-0031 (template para enviar link).

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
