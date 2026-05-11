# Backlog operativo de CopilotoIA

Este archivo es la pila única de tareas pendientes para avanzar el producto hacia producción. Cuando el usuario diga **"continúa con la siguiente tarea"**, el agente debe tomar la **primera tarea activa** de este documento, ejecutarla completamente, retirarla de este backlog y moverla a `docs/DONE.md` con evidencia concreta de lo realizado.

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
8. No recrear ni duplicar configuración local ya generada: Auth0/OIDC vive en `.env.auth0.local` creado por `scripts/configure-auth0.sh` (`AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, `AUTH0_API_IDENTIFIER`, `AUTH0_CLAIMS_NAMESPACE`, client IDs, URLs y rutas de secretos); los secretos viven en `.secrets/*` creados por `scripts/bootstrap.sh`, `scripts/generate-local-secrets.sh` o `scripts/configure-auth0.sh`. Las tareas futuras deben consumir esos nombres/archivos y no inventar variables paralelas ni hardcodear secretos.

---

## Análisis de brechas MVP — 2026-05-11

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

### Brechas críticas hacia el MVP completo (lety.ai)

El sistema actual tiene buena infraestructura pero **le faltan 12 capacidades del journey cliente** que son la propuesta de valor del producto:

| # | Brecha | Impacto en producción |
|---|--------|----------------------|
| 1 | Vertical fijo (solo 3 tipos de negocio) | Bloquea vender a cualquier empresa |
| 2 | Sin catálogo de servicios/precios configurable | Bot no puede informar precios ni servicios reales |
| 3 | Sin mensajes interactivos WhatsApp (botones/listas) | Booking es solo texto plano — alta fricción |
| 4 | Booking sin disponibilidad real ni flow guiado | Bot pide datos pero no completa el agendamiento |
| 5 | Sin templates WhatsApp + confirmaciones automáticas | Sin recordatorios fuera de ventana 24h |
| 6 | Sin reducción de no-show (confirmación activa) | Alta tasa de ausencias en producción |
| 7 | Sin flujo post-cita configurable | No hay seguimiento, feedback ni recompra |
| 8 | Sin CRM básico (historial, etiquetas, notas) | Agentes operan sin contexto del cliente |
| 9 | Sin analítica de negocio visible en admin | Manager no puede medir conversión ni KPIs |
| 10 | Sin campañas / mensajes masivos | No hay retención ni recompra activa |
| 11 | Sin widget web / captura desde sitio web | Solo WhatsApp como canal de entrada |
| 12 | Sin drill de restore probado | Riesgo operacional antes de producción |

### Orden de ejecución (cada tarea construye sobre la anterior)

```
TASK-0032 → TASK-0033 → TASK-0030 → TASK-0031 → TASK-0034
    ↓
TASK-0035 → TASK-0036 → TASK-0027 → TASK-0037 → TASK-0038
    ↓
TASK-0039 → TASK-0029
```

---

## Stack de tareas pendientes

---

### TASK-0032 — Vertical universal y catálogo de servicios configurable

- **Objetivo:** el sistema está limitado a 3 verticales fijos (`field_service`, `beauty`, `pet_grooming`). Para funcionar como lety.ai y adaptarse a cualquier empresa (médicos, psicólogos, spas, talleres, tutores, abogados, etc.) debe eliminarse esa limitación. Adicionalmente, el bot no puede informar precios ni servicios reales porque no existe un catálogo configurable desde el admin: el operador lo escribe en documentos de Knowledge Base de forma libre, sin estructura. Esta tarea convierte servicios y precios en una entidad de primera clase.
- **Alcance mínimo — backend:**
  - Modificar `tenants.vertical_code` para aceptar cualquier string libre (eliminar el `CHECK` o ampliar el enum). Agregar campo `business_type_label text` (ej. "Consultorio dental", "Spa", "Taller mecánico") que se muestra en la UI y en las respuestas del bot.
  - Nueva tabla `app.service_catalog`:
    - `id uuid PK`, `tenant_id`, `category text`, `name text NOT NULL`, `description text`, `price_amount numeric(10,2)`, `price_currency char(3) DEFAULT 'COP'`, `duration_minutes int`, `preparation_notes text` (instrucciones pre-cita para el cliente), `is_active bool DEFAULT true`, `sort_order int`, `metadata jsonb`, timestamps, RLS por `tenant_id`.
  - Endpoints bajo `tenant_admin_router`:
    - `GET /v1/tenants/{tenant_id}/services` — listar servicios activos.
    - `POST /v1/tenants/{tenant_id}/services` — crear servicio.
    - `PATCH /v1/tenants/{tenant_id}/services/{service_id}` — actualizar.
    - `DELETE /v1/tenants/{tenant_id}/services/{service_id}` — desactivar (soft delete).
    - `POST /v1/tenants/{tenant_id}/services/reorder` — guardar `sort_order` para controlar el orden en que el bot los presenta.
  - El endpoint `GET /v1/tenants/{tenant_id}/services` es consumible por el bot (no requiere rol admin; requiere solo `tenant_id` válido y el token de servicio interno) para mostrar el catálogo al cliente en WhatsApp.
  - Migración idempotente en `scripts/bootstrap.sh` para añadir la tabla y el campo `business_type_label` sin romper tenants existentes.
  - Tests estáticos: CRUD de servicios, validación de campos, catálogo vacío vs. con servicios activos, desactivación lógica.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, pestaña **"Negocio"** (reemplaza "Tenant"):
    - Campo `business_type_label` (texto libre: "¿Qué tipo de negocio es?").
    - Campo `vertical_code` pasa a ser sugerencia automática o libre.
    - Badge del tipo de negocio en la cabecera del wizard.
  - Nuevo módulo **"Servicios"** (`admin-panel/src/components/modules/services/ServiceCatalog.jsx`):
    - Lista de servicios con nombre, categoría, precio, duración, estado (activo/inactivo).
    - Formulario de creación/edición: nombre, descripción, categoría (texto libre), precio, moneda, duración en minutos, notas de preparación (instrucciones al cliente antes de la cita), activo/inactivo.
    - Botones de reordenar (subir/bajar en la lista).
    - Vista previa de cómo el bot presentará el servicio al cliente en WhatsApp.
  - Registrar el módulo en `admin-panel/src/data/modules.js` y en el sidebar.
- **Criterio de aceptación:** un admin puede crear un tipo de negocio libre, agregar 3 servicios con precios y duraciones, reordenarlos y desactivar uno; el endpoint devuelve solo los activos; el bot puede obtener el catálogo internamente; el catálogo vacío no rompe el flow del bot; tests estáticos pasan en CI; `python -m compileall app` y `ruff check` pasan.
- **Dependencias:** ninguna (esta tarea es la base del catálogo que usan TASK-0030, 0033 y 0034).

---

### TASK-0033 — Mensajes interactivos WhatsApp (botones y listas)

- **Objetivo:** el bot actualmente solo envía texto plano. Para reducir fricción en el agendamiento y en cualquier interacción de decisión (elegir servicio, confirmar cita, elegir profesional, dar feedback) se necesita soporte nativo de mensajes interactivos de WhatsApp: botones de respuesta rápida y listas de opciones. Sin esto, el booking guiado del bot es solo texto y la experiencia es pobre comparada con lety.ai.
- **Alcance mínimo — backend:**
  - Ampliar `app/services/whatsapp_sender.py` (o el servicio equivalente de envío) para soportar el tipo `interactive` de la Graph API de Meta:
    - `button`: hasta 3 botones de respuesta rápida (`reply` type). Payload: `{type:'button', body:{text}, action:{buttons:[{type:'reply',reply:{id,title}}]}}`.
    - `list`: mensaje con lista de hasta 10 opciones en secciones. Payload: `{type:'list', body:{text}, action:{button:'Ver opciones', sections:[{title, rows:[{id,title,description}]}]}}`.
  - Función helper `send_interactive_buttons(conn, tenant_id, conversation_id, body_text, buttons: list[dict])` y `send_interactive_list(conn, tenant_id, conversation_id, body_text, sections: list[dict])` reutilizando el worker de entrega existente.
  - El bot (en `rag_orchestrator.py`) puede llamar estas funciones cuando el contexto lo requiere: lista de servicios → `send_interactive_list`; confirmación de cita → `send_interactive_buttons`.
  - Manejo de respuesta interactiva inbound: cuando el cliente toca un botón o elige de la lista, Meta envía un mensaje de tipo `interactive` con `type: button_reply` o `list_reply`. Añadir parsing de este tipo en el webhook inbound para extraer `button_id`/`list_row_id` y `title`, convertirlo en intención del flujo conversacional. Guardar en `messages.payload` el `interactive_id` y `interactive_title` seleccionados.
  - Campo `interactive_session jsonb` en `conversations` (o en `messages.payload`) para rastrear el estado del flow multi-turno: qué paso del booking se completó, qué botón/lista se envió, qué respondió el cliente.
  - Tests estáticos: construcción del payload de botón, construcción del payload de lista, parsing de `button_reply` inbound, parsing de `list_reply` inbound, serialización correcta para el worker.
- **Alcance mínimo — Admin Panel:**
  - En `KnowledgeStudio.jsx`, al probar el clasificador + RAG, mostrar si la respuesta generada incluiría botones interactivos y cuáles serían.
  - En `OperationsDesk.jsx`, en el historial de mensajes: renderizar los mensajes interactivos enviados (mostrar los botones/opciones) y los botones seleccionados por el cliente (mostrar la opción elegida destacada).
- **Criterio de aceptación:** el sistema puede construir y enviar mensajes de tipo `button` y `list` a través del worker existente; el webhook parsea `button_reply` y `list_reply` y los almacena correctamente; el Operations Desk muestra la visualización de mensajes interactivos; tests estáticos pasan en CI.
- **Dependencias:** ninguna técnica (puede ejecutarse en paralelo con TASK-0032).

---

### TASK-0030 — Booking flow completo con disponibilidad real y flow guiado

- **Objetivo:** el `conversation_flow.py` actual recolecta preferencias del usuario (servicio, fecha, hora) pero no consulta `appointments` + `resources` para verificar ni ofrecer slots reales. Adicionalmente, el flow debe usar el catálogo de servicios (TASK-0032) y los mensajes interactivos (TASK-0033) para guiar al cliente paso a paso: elegir servicio → elegir profesional/recurso → elegir fecha → elegir hora disponible → confirmar → cita creada. Este es el flujo más crítico del producto.
- **Alcance mínimo — backend:**
  - Endpoint `GET /v1/tenants/{tenant_id}/resources/{resource_id}/availability`:
    - Parámetros: `date` (YYYY-MM-DD) o rango `from_date`/`to_date`.
    - Calcula slots libres restando los `appointments` activos (`provisional`, `confirmed`, `rescheduled`) del horario laboral del recurso.
    - El horario laboral se lee de `resources.capabilities.working_hours` (estructura: `{mon: [{start:'09:00', end:'18:00'}], tue: [...], ...}`).
    - La duración del slot se toma de `service_catalog.duration_minutes` del servicio seleccionado o de `tenant_settings.service_durations` como fallback.
    - Devuelve: `{date, resource_id, slots: [{start_time, end_time, available: bool}]}`.
  - Endpoint `GET /v1/tenants/{tenant_id}/availability` (multi-recurso):
    - Dado un `service_id` y una `date`, devuelve todos los recursos/profesionales que pueden atender ese servicio con sus slots libres disponibles ese día.
    - Permite que el bot muestre "Hoy tienen disponibilidad con María a las 10:00 y con Carlos a las 14:00".
  - Campo `service_id uuid FK → service_catalog(id)` en `appointments` (nullable para compatibilidad).
  - Actualizar `conversation_flow.py` o `rag_orchestrator.py` con el flow de booking multi-paso usando el estado de `conversations.current_intent = book_appointment`:
    - **Paso 1:** si hay catálogo, el bot envía lista interactiva de servicios disponibles.
    - **Paso 2:** si hay más de un profesional disponible para el servicio, el bot envía lista de profesionales.
    - **Paso 3:** el bot pregunta la fecha deseada y consulta disponibilidad real.
    - **Paso 4:** el bot envía botones con los 3 próximos slots disponibles (o lista si son más).
    - **Paso 5:** al confirmar el slot, crea el `appointment` con `service_id`, `resource_id`, `starts_at`, `ends_at` calculados desde duración del servicio, `confirmation_status = pending`.
    - **Paso 6:** envía mensaje de confirmación al cliente con los detalles de la cita.
    - Si no hay slots disponibles en la fecha pedida, el bot sugiere la próxima fecha con disponibilidad.
  - Estado del flow guardado en `conversations.metadata` (JSON): `{booking_step: 'choosing_service'|'choosing_professional'|'choosing_date'|'choosing_slot'|'confirming', selected_service_id, selected_resource_id, proposed_date}`.
  - Campo `service_durations jsonb` en `tenant_settings` (mapa `service_code → minutos`) como fallback cuando no hay catálogo.
  - Tests estáticos: cálculo de slots libres, manejo de día sin disponibilidad, flow multi-paso (mock de cada estado), integración con catálogo de servicios, integración con mensajes interactivos.
- **Alcance mínimo — Admin Panel:**
  - En `OperationsDesk.jsx`, sección de recursos: formulario de creación/edición de recurso incluye builder de **horario laboral** por día de semana (toggle activo/inactivo por día, campo de hora inicio y fin, posibilidad de múltiples franjas por día). Se guarda en `resources.capabilities.working_hours`.
  - En `TenantSetupWizard.jsx`, pestaña **"Servicios y agenda"**: mapa de `service_code → duración en minutos` como fallback si no se usa el catálogo.
  - Vista de **calendario semanal** en `OperationsDesk.jsx` que muestra los appointments activos por recurso con los slots ocupados. Consume el endpoint de disponibilidad para resaltar slots libres.
- **Criterio de aceptación:** dado un recurso con horario 9:00–18:00 lunes a viernes y una cita existente de 10:00–11:00, el endpoint de disponibilidad devuelve los slots libres correctamente; el flow guiado en WhatsApp presenta opciones interactivas; al elegir un slot la cita se crea sin conflicto; el calendario del Admin Panel muestra la agenda real; tests pasan en CI.
- **Dependencias:** TASK-0032 (catálogo de servicios), TASK-0033 (mensajes interactivos).

---

### TASK-0031 — Gestión de plantillas WhatsApp y notificaciones automáticas de cita

- **Objetivo:** los `reminder_jobs` necesitan templates aprobados por Meta para enviarse fuera de la ventana de 24h. Sin templates aprobados el sistema no puede enviar confirmación de cita, recordatorios ni seguimiento post-cita — es decir, las tareas TASK-0034 y TASK-0035 no funcionan. Esta tarea crea el sistema completo de plantillas y los despachos automáticos de notificaciones.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.whatsapp_templates`:
    - `id uuid PK`, `tenant_id`, `channel_id`, `name text`, `locale char(5) DEFAULT 'es'`, `category` (`utility|marketing|authentication`), `status` (`draft|pending|approved|rejected|paused`), `purpose` (`appointment_confirmation|appointment_reminder_24h|appointment_reminder_1h|appointment_reminder_custom|no_show_followup|post_appointment_feedback|post_appointment_instructions|reschedule_offer|campaign_promo|custom`), `components jsonb` (header/body/footer/buttons según spec Meta), `meta_template_id text`, `rejection_reason text`, timestamps, RLS por `tenant_id`.
  - Endpoints bajo `tenant_admin_router`:
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates` — registrar template y enviarlo a revisión en Meta Graph API.
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates` — listar todos.
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — detalle con status actual.
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates/sync` — actualizar status de todos desde Meta.
    - `DELETE /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — eliminar en DB y en Meta.
  - Función `send_whatsapp_template(conn, tenant_id, wa_phone, template_name, variables: dict)` en el servicio de envío, que construye el payload de template y llama a la Graph API.
  - En `scheduler.py`: antes de enviar un `reminder_job`, verificar que el template existe en `whatsapp_templates` con `status='approved'`; si no → marcar job como `failed` con error `template_not_approved`.
  - Ampliar `reminder_jobs` para soportar propósito: campo `purpose` alineado con el enum de plantillas. El scheduler usa el `purpose` para elegir el template correcto del tenant.
  - Templates de texto por defecto (sin variables dinámicas): los tenants que no hayan subido templates a Meta pueden usar el canal de texto libre (dentro de ventana 24h) con mensajes de texto plano configurables.
  - Tests estáticos: estructura de tabla, validación de componentes del template, scheduler con template no aprobado, envío de template con variables.
- **Alcance mínimo — Admin Panel:**
  - En `WhatsAppOnboarding.jsx`, nueva sección **"Plantillas de mensajes"**:
    - Lista con badge de estado por plantilla y motivo de rechazo visible.
    - Formulario de creación: nombre, idioma, categoría, propósito (selector), editor de componentes (header texto, body con variables `{{1}}`, footer, botones de respuesta rápida).
    - Botón **"Sincronizar estado con Meta"**.
    - Semáforo por propósito: verde = aprobado, amarillo = pendiente, rojo = faltante.
  - En `GoLiveReadiness.jsx`: check **"Plantillas mínimas aprobadas"** que valide templates aprobados para `appointment_confirmation` y `appointment_reminder_24h`.
- **Criterio de aceptación:** admin crea template, sincroniza status y lo ve aprobado; el scheduler rechaza reminder con error claro si no hay template aprobado; readiness check detecta templates faltantes; tests pasan en CI.
- **Dependencias:** TASK-0030 recomendada antes.

---

### TASK-0034 — Flujo de confirmación automática y recordatorios configurables

- **Objetivo:** cuando se crea una cita (manualmente desde el Operations Desk o por el bot), el sistema debe enviar automáticamente: (1) confirmación inmediata al cliente con detalles, instrucciones de preparación y ubicación con link de Google Maps; (2) recordatorio configurable antes de la cita (24h, 1h o ambos); (3) instrucciones específicas del servicio. Todo configurable desde el admin sin código. Este flujo es la diferencia clave entre un sistema de agendamiento básico y un sistema que reduce no-shows.
- **Alcance mínimo — backend:**
  - Al crear un `appointment` (endpoint `POST /v1/appointments`), crear automáticamente los `reminder_jobs` configurados para el tenant:
    - Job `appointment_confirmation` → scheduled_for = `now()` (envío inmediato o en segundos).
    - Job `appointment_reminder_24h` → scheduled_for = `starts_at - 24 horas` (si el tenant lo tiene activo).
    - Job `appointment_reminder_1h` → scheduled_for = `starts_at - 1 hora` (si el tenant lo tiene activo).
  - Función `create_appointment_reminder_jobs(conn, tenant_id, appointment_id)` en un servicio dedicado. Lee `tenant_settings.notification_settings` para saber qué jobs crear.
  - Campo `notification_settings jsonb` en `tenant_settings`:
    ```json
    {
      "confirmation_enabled": true,
      "reminder_24h_enabled": true,
      "reminder_1h_enabled": true,
      "include_location_link": true,
      "location_address": "Calle 123 #45-67, Bogotá",
      "location_maps_url": "https://maps.google.com/?q=...",
      "include_service_instructions": true
    }
    ```
  - El template de confirmación incluye variables: `{{nombre_cliente}}`, `{{nombre_servicio}}`, `{{fecha_hora}}`, `{{nombre_profesional}}`, `{{ubicacion}}`, `{{instrucciones_preparacion}}` (del campo `service_catalog.preparation_notes`).
  - Al reprogramar una cita, cancelar los jobs pendientes del appointment anterior y crear nuevos para la nueva hora.
  - Al cancelar una cita, cancelar todos los jobs pendientes del appointment.
  - Tests estáticos: creación automática de jobs al crear cita, cancelación de jobs al cancelar cita, recreación de jobs al reprogramar, respeto de `notification_settings`.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, nueva pestaña **"Notificaciones"**:
    - Toggles: Confirmación inmediata ✓, Recordatorio 24h ✓, Recordatorio 1h ✓.
    - Campo: Dirección del negocio.
    - Campo: Link de Google Maps (URL completa).
    - Toggle: Incluir link de Maps en recordatorios.
    - Toggle: Incluir instrucciones de preparación del servicio.
    - Preview de cómo se verá el mensaje de confirmación al cliente.
  - En `ServiceCatalog.jsx` (TASK-0032): campo **"Instrucciones de preparación"** por servicio (textarea: "Ven en ayunas 4 horas antes", "Usa ropa cómoda", etc.).
- **Criterio de aceptación:** al crear una cita, se generan automáticamente los reminder_jobs configurados; al reprogramar, los jobs se regeneran con la nueva hora; los templates incluyen todos los campos configurados; el admin puede activar/desactivar cada tipo de recordatorio desde el panel; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates WhatsApp), TASK-0032 (catálogo con instrucciones).

---

### TASK-0035 — Reducción de no-show y flujo post-cita configurable

- **Objetivo:** cerrar el ciclo del cliente con dos flujos críticos: (A) reducción activa de no-show mediante confirmación de asistencia, rescheduling fácil y seguimiento si no responde; (B) flujo post-cita con instrucciones de post-atención, solicitud de feedback/reseña e invitación a nueva cita. Ambos flujos 100% configurables desde el admin. Este es el diferenciador que convierte pacientes únicos en clientes recurrentes.
- **Alcance mínimo — backend:**

  **A. Confirmación activa (reducción no-show):**
  - Nuevo propósito de reminder_job: `no_show_confirmation_request` — enviado N horas antes (configurable, default 4h). El mensaje pregunta "¿Confirmas tu cita de {{servicio}} el {{fecha}} a las {{hora}}? Responde Sí o No".
  - Cuando el cliente responde al mensaje de confirmación, el intent classifier detecta `confirm_appointment` o `cancel_appointment`. El orquestador actualiza `appointments.confirmation_status = confirmed | declined`.
  - Si el cliente responde "No" → el bot activa un flow de reprogramación (usando TASK-0030).
  - Si el cliente no responde N horas después del job de confirmación → nuevo job `no_show_followup` con mensaje "Tu cita está próxima, ¿necesitas cambiarla?".
  - Campo `confirmation_reminder_hours int DEFAULT 4` en `notification_settings` (tenant_settings).

  **B. Flujo post-cita:**
  - Nuevo propósito: `post_appointment_instructions` — enviado N minutos/horas después de `appointments.ends_at` (configurable, default 30min). Incluye instrucciones post-servicio del catálogo.
  - Nuevo propósito: `post_appointment_feedback` — enviado N horas después de la cita (configurable, default 2h). Mensaje: "¿Cómo fue tu experiencia? Califica del 1 al 5 ⭐".
  - Nuevo propósito: `post_appointment_rebooking` — enviado N días después (configurable, default 30 días). Mensaje: "¡Es momento de tu próxima {{servicio}}! ¿Te agendamos?".
  - Nueva tabla `app.appointment_feedback`:
    - `id uuid PK`, `tenant_id`, `appointment_id FK`, `contact_id FK`, `rating int CHECK(1..5)`, `comment text`, `created_at`.
  - Cuando el cliente responde con un número del 1 al 5, el orquestador lo registra en `appointment_feedback`.
  - El `rebooking` detecta intención positiva → activa el flow de booking (TASK-0030).
  - Campo `post_appointment_settings jsonb` en `tenant_settings`:
    ```json
    {
      "instructions_delay_minutes": 30,
      "feedback_delay_hours": 2,
      "feedback_enabled": true,
      "rebooking_delay_days": 30,
      "rebooking_enabled": true,
      "rebooking_message": "¡Es momento de tu próxima visita!"
    }
    ```
  - Tests estáticos: creación de job de confirmación activa, flow de respuesta confirmación/cancelación, creación de jobs post-cita, registro de feedback, lógica de rebooking.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, pestaña **"Notificaciones"** (extendida de TASK-0034):
    - Sección **"Reducción de no-show"**: toggle confirmación activa, horas antes del recordatorio de confirmación.
    - Sección **"Seguimiento post-cita"**: toggle instrucciones, horas delay; toggle feedback (calificación 1–5), horas delay; toggle invitación a nueva cita, días delay, mensaje personalizable.
  - En `OperationsDesk.jsx`, en el detalle de cita: badge de `confirmation_status` (pendiente / confirmada / rechazada) y calificación recibida (estrellas).
  - En `ServiceCatalog.jsx`: campo **"Instrucciones post-servicio"** (ej. "Evita el sol 24h", "No te laves el cabello hoy").
- **Criterio de aceptación:** el sistema envía confirmación activa N horas antes; la respuesta del cliente actualiza el estado de la cita; se registra el feedback cuando el cliente responde; la invitación de recompra se programa automáticamente; todo configurable desde admin sin código; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates), TASK-0034 (confirmación básica).

---

### TASK-0036 — CRM básico: historial de contacto, etiquetas y notas

- **Objetivo:** los agentes actualmente operan sin contexto de quién es el cliente que les llega. No pueden ver el historial de citas, conversaciones anteriores, etiquetas de segmentación ni notas internas. Este CRM básico es la base para que el bot y los agentes tengan contexto completo del cliente, y para que TASK-0037 (campañas) pueda segmentar.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.contact_tags`:
    - `id uuid PK`, `tenant_id`, `name text NOT NULL`, `color varchar(7)` (hex), `description text`, timestamps, RLS.
  - Nueva tabla `app.contact_tag_assignments`:
    - `contact_id FK`, `tag_id FK`, `assigned_by user_id FK`, `assigned_at`. PK compuesta `(contact_id, tag_id)`. RLS por `tenant_id` vía join.
  - Nueva tabla `app.contact_notes`:
    - `id uuid PK`, `tenant_id`, `contact_id FK`, `body text NOT NULL`, `created_by user_id FK`, timestamps, RLS.
  - Endpoints:
    - `GET /v1/tenants/{tenant_id}/contact-tags` — listar etiquetas del tenant.
    - `POST /v1/tenants/{tenant_id}/contact-tags` — crear etiqueta.
    - `DELETE /v1/tenants/{tenant_id}/contact-tags/{tag_id}` — eliminar etiqueta.
    - `POST /v1/contacts/{contact_id}/tags` — asignar etiqueta(s) al contacto (body: `{tag_ids: [...]}`).
    - `DELETE /v1/contacts/{contact_id}/tags/{tag_id}` — quitar etiqueta.
    - `POST /v1/contacts/{contact_id}/notes` — crear nota interna.
    - `GET /v1/contacts/{contact_id}/notes` — listar notas.
    - `GET /v1/contacts/{contact_id}/profile` — perfil completo del contacto: datos personales, tags asignadas, citas (últimas 10), conversaciones recientes, feedback recibido, notas internas, total de citas, fecha primera y última visita.
  - En el endpoint de `GET /v1/conversations` (inbox), incluir tags del contacto en cada item del inbox para que el agente vea inmediatamente el perfil.
  - Tests estáticos: CRUD de etiquetas, asignación/desasignación, notas, perfil completo del contacto.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Contactos"** (`admin-panel/src/components/modules/contacts/ContactsModule.jsx`):
    - Lista de contactos con búsqueda por nombre/teléfono, filtro por etiqueta.
    - Al hacer clic en un contacto: perfil completo con historial de citas, conversaciones, feedback y notas.
    - Botón para asignar/quitar etiquetas.
    - Formulario para agregar nota interna.
  - En `TenantSetupWizard.jsx`, nueva sección en pestaña "Negocio": **"Etiquetas de contactos"** — crear y gestionar las etiquetas del tenant (nombre + color).
  - En `OperationsDesk.jsx`, en el header del detalle de conversación: chips de etiquetas del contacto con botón para asignar/quitar etiquetas y campo para agregar nota rápida.
  - En el inbox del Operations Desk: chips de etiquetas visibles en cada card de conversación.
- **Criterio de aceptación:** admin crea etiquetas, agente las asigna desde la conversación, el perfil del contacto muestra historial completo; el inbox muestra etiquetas; filtro por etiqueta funciona; tests pasan en CI.
- **Dependencias:** TASK-0035 (feedback visible en perfil).

---

### TASK-0027 — Analítica completa de negocio (panel de métricas)

- **Objetivo:** el rol `manager` no tiene forma de medir si el sistema está funcionando. Sin métricas de conversión, no-show, ingresos y canales, la empresa no puede justificar la inversión. Esta tarea implementa un panel de analytics con los KPIs que más le importan al negocio según el MVP.
- **Alcance mínimo — backend:**
  - `GET /v1/analytics/overview`: acepta `from_date`, `to_date` (default últimos 30 días); requiere rol `manager` + `X-Tenant-Id`. Devuelve:
    - Conversaciones: total, abiertas, resueltas, en handoff, tasa de handoff.
    - Citas: creadas, confirmadas, completadas, canceladas, no-shows, tasa de no-show (no_shows / (completadas + no_shows)).
    - Ingresos estimados: suma de `service_catalog.price_amount` de citas completadas en el período.
    - Feedback: promedio de calificaciones, total de calificaciones recibidas.
    - Mensajes: inbound y outbound totales.
    - Retención: % de contactos con más de 1 cita completada en el período.
  - `GET /v1/analytics/conversations`: mismo filtro. Devuelve:
    - Top 10 intenciones más frecuentes con conteo y %.
    - Distribución de conversaciones por estado.
    - Tiempo promedio de primera respuesta del bot (segundos).
    - Tiempo promedio hasta handoff (cuando aplica, en minutos).
    - Evolución diaria de conversaciones nuevas: `[{date, count}]`.
  - `GET /v1/analytics/appointments`: mismo filtro. Devuelve:
    - Servicios más agendados (top 5 por `service_id`).
    - Profesionales con más citas.
    - Distribución por estado de cita.
    - No-shows por día de la semana.
    - Evolución diaria de citas creadas vs. completadas.
  - `GET /v1/analytics/contacts`: mismo filtro. Devuelve:
    - Nuevos contactos en el período vs. recurrentes.
    - Top etiquetas de contactos.
    - Tasa de opt-out.
    - Distribución de contactos por fuente (si se implementó TASK-0040) o por intención de primer contacto.
  - Todos calculan con SQL directo sobre tablas existentes + `service_catalog` y `appointment_feedback`. Sin tablas nuevas.
  - Tests estáticos: estructura de respuesta, controles de autorización (agent → 403, manager → 200), cálculos de tasa de no-show, promedio de feedback.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Analítica"** (`admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx`):
    - Selector de rango de fechas (7d / 30d / 90d / personalizado).
    - Cards de KPIs principales: conversaciones, citas completadas, tasa de no-show, ingreso estimado, calificación promedio.
    - Gráfico de evolución diaria de conversaciones (SVG nativo o tabla mini barras).
    - Gráfico de evolución diaria de citas (completadas vs. canceladas).
    - Tabla de top intenciones con conteo y %.
    - Tabla de servicios más solicitados.
    - Cards de distribución de citas por estado.
  - Registrar el módulo en `admin-panel/src/data/modules.js` y sidebar, accesible para `manager` o superior.
- **Criterio de aceptación:** manager ve KPIs del período; agent recibe 403; datos coherentes con registros de DB; tasa de no-show se calcula correctamente; módulo aparece en sidebar; tests pasan en CI.
- **Dependencias:** TASK-0035 (para feedback y no-show data), TASK-0036 (para datos de etiquetas).

---

### TASK-0037 — Campañas y mensajes masivos a segmentos de contactos

- **Objetivo:** convertir el directorio de contactos (TASK-0036) en un motor de retención activa. El negocio necesita enviar mensajes masivos a grupos de clientes (promociones, recordatorios estacionales, mensajes de reactivación) sin salir de la plataforma. Todo usando templates aprobados de WhatsApp para respetar la política de Meta.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.campaigns`:
    - `id uuid PK`, `tenant_id`, `name text`, `status` (`draft|scheduled|running|completed|cancelled`), `template_id FK → whatsapp_templates(id)`, `template_variables jsonb` (valores para `{{1}}`, `{{2}}`...), `segment_filter jsonb` (criterios: `{tags:[...], min_appointments:N, last_visit_before_days:N, last_visit_after_days:N}`), `scheduled_at timestamptz`, `sent_count int DEFAULT 0`, `delivered_count int DEFAULT 0`, `read_count int DEFAULT 0`, `failed_count int DEFAULT 0`, timestamps, RLS.
  - Endpoints:
    - `POST /v1/tenants/{tenant_id}/campaigns` — crear campaña.
    - `GET /v1/tenants/{tenant_id}/campaigns` — listar con métricas.
    - `GET /v1/tenants/{tenant_id}/campaigns/{campaign_id}` — detalle.
    - `PATCH /v1/tenants/{tenant_id}/campaigns/{campaign_id}` — actualizar.
    - `POST /v1/tenants/{tenant_id}/campaigns/{campaign_id}/preview` — devuelve conteo estimado de destinatarios según `segment_filter` y muestra los primeros 5 contactos.
    - `POST /v1/tenants/{tenant_id}/campaigns/{campaign_id}/launch` — cambia estado a `scheduled`; si `scheduled_at <= now()` inicia inmediatamente.
    - `POST /v1/tenants/{tenant_id}/campaigns/{campaign_id}/cancel` — cancela campaña pendiente o en curso.
  - Worker de campañas: el scheduler detecta campañas en estado `scheduled` con `scheduled_at <= now()`, las pasa a `running`, evalúa el `segment_filter` contra `contacts` + `contact_tag_assignments` + `appointments`, y encola mensajes individuales de template a cada destinatario respetando el opt-in y sin reenviar a `opt_in_status = suppressed | opted_out`.
  - Rate limiting: máximo 20 mensajes/segundo por tenant para no saturar la API de Meta (configurable en `tenant_settings`).
  - Actualización de contadores en tiempo real (`sent_count`, `delivered_count`, etc.) cuando el worker procesa status updates del webhook.
  - Tests estáticos: evaluación de `segment_filter`, rate limiting, exclusión de contactos opt-out, estructura de campaña, cálculo de destinatarios estimados.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Campañas"** (`admin-panel/src/components/modules/campaigns/CampaignsModule.jsx`):
    - Lista de campañas con estado, fecha, destinatarios estimados, métricas de entrega.
    - Formulario de creación: nombre, template (solo approved), variables del template, segmento de destinatarios (filtros por etiqueta, número mínimo de citas, última visita hace N días), fecha/hora de envío.
    - Botón **"Vista previa del segmento"** que muestra el conteo y los primeros 5 contactos.
    - Botones: Guardar borrador, Programar envío, Cancelar.
    - Vista de resultados: barras de progreso de enviados/entregados/leídos/fallidos.
  - Registrar en `modules.js` y sidebar, accesible para `admin` o superior.
- **Criterio de aceptación:** admin crea campaña con segmento, previsualiza destinatarios, programa envío; el worker envía solo a contactos activos y con opt-in; las métricas se actualizan con los webhooks de status; no se envía a contactos suprimidos; tests pasan en CI.
- **Dependencias:** TASK-0031 (templates), TASK-0036 (etiquetas de contactos).

---

### TASK-0038 — Widget web y formulario de captura de leads desde sitio web

- **Objetivo:** ampliar los canales de captación más allá de WhatsApp. Muchos negocios ya tienen un sitio web y quieren capturar leads directamente desde él. Esta tarea implementa un widget de chat embebible (JavaScript snippet) que el cliente del negocio añade a su web y que envía leads directamente a CopilotoIA, creando la conversación y el contacto automáticamente.
- **Alcance mínimo — backend:**
  - Nuevo canal `web` en `tenant_channels`: `provider='web'`, `account_mode='live'`. La tabla ya soporta providers adicionales.
  - Endpoint público (sin autenticación de usuario, pero firmado con `widget_token`):
    - `POST /v1/web/chat/start` — inicia una conversación web. Body: `{tenant_slug, name, phone?, email?, message, utm_source?, utm_medium?, utm_campaign?, referrer?}`. Devuelve `{conversation_id, session_token}` (token de sesión anónima).
    - `POST /v1/web/chat/{conversation_id}/messages` — enviar mensaje desde el widget (autenticado con `session_token`). Devuelve la respuesta del bot.
    - `GET /v1/web/chat/{conversation_id}/messages` — obtener historial de la sesión web (autenticado con `session_token`).
  - El `session_token` es un JWT firmado con `SECRET_KEY` que expira en 24h, contiene `conversation_id` y `contact_id`. No es el mismo JWT de admin.
  - El orquestador RAG procesa mensajes web igual que WhatsApp; el `channel_type` en `messages` refleja `web`.
  - Campo `lead_source jsonb` en `contacts`: `{channel: 'web'|'whatsapp'|'phone', utm_source, utm_medium, utm_campaign, referrer, first_contact_at}`.
  - `widget_token` configurable por tenant (secreto en `.secrets/tenants/{id}/widget_token`).
  - Tests estáticos: inicio de sesión web, envío de mensaje, generación y validación de session_token, extracción de UTMs en lead_source.
- **Alcance mínimo — Admin Panel:**
  - En `WhatsAppOnboarding.jsx` (o nuevo módulo `Canales`): sección **"Widget Web"**:
    - Toggle: activar canal web.
    - Campo: dominio(s) permitido(s) (CORS whitelist).
    - Generador de código snippet: `<script src="https://.../widget.js" data-tenant="..."></script>`.
    - Preview de cómo se ve el widget (captura de pantalla estática o iframe).
    - Botón para copiar el snippet al portapapeles.
  - En `AnalyticsPanel.jsx` (TASK-0027): en las métricas de contactos, mostrar distribución por `lead_source.channel`.
  - Widget frontend: `admin-panel/public/widget.js` — script embebible que abre un iframe de chat flotante en la esquina inferior derecha. El iframe carga desde `/web/chat?tenant={slug}`. No depende de React ni librerías externas para minimizar el impacto en el sitio del cliente. Aspecto configurable (color primario, texto de bienvenida) via atributos `data-*` del script tag.
- **Criterio de aceptación:** el snippet se puede embeber en cualquier HTML; el widget inicia una conversación, la respuesta del bot llega en < 3s; la conversación aparece en el inbox del Operations Desk; el `lead_source` queda registrado en el contacto; tests pasan en CI.
- **Dependencias:** TASK-0032 (catálogo para respuestas), TASK-0036 (lead_source en contactos).

---

### TASK-0039 — Links de pago y registro de pagos en citas

- **Objetivo:** muchos negocios requieren pago previo o al momento del servicio. Esta tarea agrega soporte básico para generar links de pago (MercadoPago / Stripe) que el bot o el agente puede enviar al cliente, y para registrar si la cita tiene pago pendiente o confirmado. No se implementa pasarela propia — solo integración con proveedores externos.
- **Alcance mínimo — backend:**
  - Campo `payment_status` en `appointments`: `not_required | pending | link_sent | paid | failed` (default `not_required`).
  - Campo `payment_amount numeric(10,2)` y `payment_currency char(3)` en `appointments`.
  - Campo `payment_link text` en `appointments` (URL generada por el proveedor).
  - Nuevo servicio `app/services/payment_provider.py`:
    - `generate_payment_link(provider, api_key, amount, currency, description, metadata) → url` con soporte para MercadoPago (Preference API) y Stripe (Payment Link API).
  - Endpoints:
    - `POST /v1/appointments/{id}/payment-link` — genera link de pago y lo guarda en el appointment. Requiere que el tenant tenga `payment_provider` y `payment_api_key_ref` configurados.
    - `POST /v1/appointments/{id}/send-payment` — envía el link por WhatsApp al cliente vía conversación del appointment.
    - `PATCH /v1/appointments/{id}/payment-status` — actualizar estado manualmente (para cuando el pago se confirma por otro canal).
  - Webhook receptor de confirmaciones de pago: `POST /v1/webhooks/payments/{provider}` — recibe notificación del proveedor, verifica firma, actualiza `appointments.payment_status = paid` y envía mensaje de confirmación al cliente.
  - Campo `payment_provider` y referencia de API key en `tenant_settings`. La API key real va en `.secrets/tenants/{id}/payment_api_key`.
  - Tests estáticos: generación de link (mock del proveedor), actualización de estado, webhook de confirmación, verificación de firma.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, nueva sección **"Pagos"**: selector de proveedor (MercadoPago / Stripe / Ninguno), campo para API key (enmascarada), moneda por defecto.
  - En `OperationsDesk.jsx`, en el detalle de cita: badge de `payment_status`, botón **"Generar link de pago"** y botón **"Enviar por WhatsApp"** cuando el link está generado. Campo editable de monto.
- **Criterio de aceptación:** admin configura proveedor desde el panel; agente genera link y lo envía al cliente; webhook del proveedor actualiza el estado a `paid`; el bot puede enviar el link automáticamente cuando el booking flow lo requiere; tests pasan en CI.
- **Dependencias:** TASK-0030 (booking flow para solicitar pago al final), TASK-0031 (template para enviar link).

---

### TASK-0029 — Ejecutar y validar drill de restore local

- **Objetivo:** los scripts `backup-local.sh` y `restore-local.sh` de TASK-0015 existen pero nunca se ejecutaron contra un Docker Compose real con datos. El criterio de aceptación de TASK-0015 dice "restore local probado con datos demo" y no se cumplió. Esta tarea lo valida y cierra ese pendiente antes de producción.
- **Alcance mínimo:**
  - En un entorno con Docker y Docker Compose disponible:
    1. Levantar el stack completo con `./scripts/bootstrap.sh`.
    2. Ejecutar `./scripts/backup-local.sh` y verificar que genera dump SQL + manifiesto de objetos.
    3. Ejecutar `./scripts/bootstrap.sh --reset --yes --skip-smoke` para limpiar la base.
    4. Ejecutar `./scripts/restore-local.sh <backup-file>` y validar con SQL que tenants, documentos, chunks, audit logs y al menos una conversación demo están presentes.
    5. Documentar conteos antes/después en `docs/runbook-go-live-evidence.md`.
  - Si se detectan errores en los scripts durante la ejecución real, corregirlos y documentar los cambios.
  - Agregar test estático que verifique la sintaxis bash de ambos scripts con `bash -n`.
- **Criterio de aceptación:** restore local ejecutado y exitoso con datos demo en Docker Compose; conteos documentados en `docs/runbook-go-live-evidence.md`; scripts pasan `bash -n`; evidencia commiteada.
- **Dependencias:** requiere entorno con Docker disponible. Si el entorno sigue sin Docker, documentar el bloqueo y no mover a DONE.
