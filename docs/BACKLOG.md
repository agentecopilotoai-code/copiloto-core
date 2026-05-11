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

## Revisión 2026-05-11 — Análisis de brechas hacia producción

El análisis del código contra `README.md` y `ARCHITECTURE.md` confirma que el sprint base (tenant setup, WhatsApp, Knowledge Studio, Operations Desk, Audit, Readiness, CI, cascada RAG + LLM) está completo. Quedan **siete brechas** que juntas dejan el producto listo para piloto en producción:

| Orden | Tarea | Motivo de bloqueo si no se hace |
|-------|-------|--------------------------------|
| 1 | TASK-0025: Embeddings reales | El índice HNSW de pgvector usa hashes SHA256; la búsqueda semántica no funciona |
| 2 | TASK-0026: Clasificador de intenciones | El bot no diferencia saludo, FAQ, agendar, queja — todo lo trata igual |
| 3 | TASK-0028: Policy engine | No hay control de riesgo, ventana WhatsApp ni límite de turnos integrado en el flujo |
| 4 | TASK-0030: Booking flow con disponibilidad real | El bot recolecta preferencias pero no verifica ni ofrece slots reales disponibles |
| 5 | TASK-0031: Gestión de plantillas WhatsApp | Los recordatorios fallan si no hay templates aprobados en Meta registrados en la plataforma |
| 6 | TASK-0027: Endpoints y panel de analítica | El rol `manager` no puede monitorear el piloto; no hay KPIs visibles |
| 7 | TASK-0029: Drill de restore validado | Los scripts existen pero nunca se ejecutaron con Docker real; el criterio de TASK-0015 no se cumplió |

Las tareas están ordenadas por dependencia: cada una construye sobre la anterior. Las primeras cinco son funcionalidad de producto; las últimas dos son observabilidad y operaciones.

---

## Stack de tareas pendientes

### TASK-0028 — Implementar policy engine básico con configuración por tenant

- **Objetivo:** cerrar la brecha entre la política básica actual (solo `max_bot_turns` + keywords de trigger dispersos en el orquestador) y un policy engine centralizado y configurable que evalúe riesgo, ventana de servicio WhatsApp y límites antes de cada respuesta del bot.
- **Alcance mínimo — backend:**
  - Crear `app/services/policy_engine.py` con función `evaluate_policy(tenant_settings, conversation, message_text, intent) -> PolicyResult`.
  - `PolicyResult`: `action` (`continue_bot` | `require_handoff` | `block`), `reason` (string legible para el log), `risk_level` (`low` | `medium` | `high`).
  - Reglas evaluadas en orden de prioridad:
    1. **Intención de riesgo**: si `intent == complaint_or_risk` → `require_handoff`, `risk_level=high` inmediatamente.
    2. **Keywords de riesgo adicionales**: lista configurable por tenant en `tenant_settings.escalation_policy.risk_keywords`; si alguna aparece en el texto → `require_handoff`.
    3. **Ventana de servicio WhatsApp**: si `conversation.service_window_expires_at` ya pasó → solo templates; si no hay template configurado → `require_handoff`.
    4. **Límite de turnos de bot**: si turnos del bot ≥ `tenant_settings.max_bot_turns` → `require_handoff`.
    5. **Sin contexto RAG repetido**: si el orquestador ya respondió N veces consecutivas con `sufficient_context=false`, N configurable (`consecutive_no_context_limit`, default 2) → `require_handoff`.
  - Integrar `evaluate_policy()` en `rag_orchestrator.py` como primer paso antes de cualquier respuesta bot; si el resultado es `require_handoff`, crear handoff directamente sin llamar al LLM.
  - Persistir `risk_level` en `messages.payload` para trazabilidad.
  - Tests estáticos ≥ 20 casos cubriendo las 5 reglas y su priorización.
- **Alcance mínimo — Admin Panel:**
  - En `TenantSetupWizard.jsx`, pestaña **"Escalamiento"** (ya existe, extender):
    - Campo numérico **"Máximo de turnos del bot"** (`max_bot_turns`, ya existe en settings — asegurarse de que se guarda y carga correctamente desde la UI).
    - Campo numérico **"Respuestas sin contexto antes de escalar"** (`consecutive_no_context_limit`, nuevo).
    - Lista editable de **keywords de riesgo** (agregar/eliminar tags desde la UI; se guarda en `escalation_policy.risk_keywords`).
    - Toggle **"Forzar handoff si ventana WhatsApp expiró"** (habilita/deshabilita la regla 3).
  - En `GoLiveReadiness.jsx`: agregar check **"Policy engine configurado"** que valide que `max_bot_turns > 0` y que hay al menos un trigger definido (keywords o `max_bot_turns`).
- **Criterio de aceptación:** `complaint_or_risk` fuerza handoff inmediato; keyword de riesgo personalizada del tenant dispara handoff; ventana vencida sin template activa handoff; `max_bot_turns` alcanzado escala; dos respuestas sin contexto escalan; todo configurable desde el Admin Panel sin tocar código; tests pasan en CI.
- **Dependencias:** TASK-0026 (el policy engine necesita recibir la intención clasificada del paso anterior).

---

### TASK-0030 — Booking flow con consulta de disponibilidad real

- **Objetivo:** el `conversation_flow.py` actual recolecta preferencias del usuario (servicio, fecha, hora) pero no consulta `appointments` + `resources` para verificar ni ofrecer slots reales disponibles. En producción, el bot podría crear citas en horarios ocupados o sin recursos activos. Esta tarea conecta el flujo conversacional con la disponibilidad real del negocio.
- **Alcance mínimo — backend:**
  - Agregar endpoint `GET /v1/tenants/{tenant_id}/resources/{resource_id}/availability` que recibe `date` (o rango `from`/`to`) y devuelve la lista de slots libres del día, calculada restando los `appointments` activos (`provisional`, `confirmed`, `rescheduled`) del horario laboral del recurso. El horario laboral se lee de `resources.capabilities.working_hours` (JSON: días de semana + franja horaria).
  - Agregar campo `working_hours` al schema de `Resource` (ya existe `capabilities jsonb`; documentar la estructura esperada y validarla en `POST /resources` y `PATCH /resources/{id}`).
  - Agregar configuración de duración por servicio: campo `service_durations jsonb` en `tenant_settings` (mapa `service_code → minutos`). El booking flow lo usa para calcular `ends_at` automáticamente.
  - Actualizar `conversation_flow.py`:
    - Cuando el usuario expresa intención de agendar y elige fecha, el flow llama internamente a la API de disponibilidad y le presenta los slots reales al usuario ("Tengo disponible a las 9:00, 11:00 y 15:00 — ¿cuál prefieres?").
    - Si no hay slots libres en la fecha pedida, el bot lo indica y ofrece la próxima fecha con disponibilidad.
    - Al confirmar slot, el flow crea el `appointment` con `starts_at` y `ends_at` calculados, pasando por el constraint de exclusión GiST existente.
  - Tests estáticos: cálculo de slots libres, manejo de día sin disponibilidad, integración del flow con la consulta de slots.
- **Alcance mínimo — Admin Panel:**
  - En `OperationsDesk.jsx`, sección de recursos: formulario de creación/edición de recurso incluye campo **"Horario laboral"** (builder visual por día de semana: activar/desactivar día, franja horaria inicio–fin). Se guarda en `resources.capabilities.working_hours`.
  - En `TenantSetupWizard.jsx`, pestaña **"Servicios y agenda"** (nueva):
    - Lista de pares `código de servicio → duración en minutos` editable (agregar/eliminar/editar). Se guarda en `tenant_settings.service_durations`.
    - Ejemplo: "corte_cabello → 30 min", "visita_tecnica → 60 min".
  - En `OperationsDesk.jsx`: vista de calendario semanal/diaria que muestra los appointments activos por recurso, con los slots libres resaltados. Consume el endpoint de disponibilidad.
- **Criterio de aceptación:** dado un recurso con horario 9:00–18:00 de lunes a viernes y una cita existente de 10:00–11:00, el endpoint de disponibilidad devuelve correctamente los slots libres; el conversation flow le presenta esos slots al usuario; al elegir un slot, la cita se crea sin conflicto; el Admin Panel permite configurar horarios laborales y duraciones de servicio; el calendario en Operations Desk muestra la agenda real; tests pasan en CI.
- **Dependencias:** TASK-0026 (el booking flow se activa desde la intención `book_appointment` del clasificador).

---

### TASK-0031 — Gestión de plantillas de mensajes WhatsApp por tenant

- **Objetivo:** los reminder jobs necesitan templates aprobados por Meta para enviarse fuera de la ventana de 24 h. Actualmente `reminder_jobs` almacena `template_name` pero no existe ningún mecanismo para que el tenant registre, gestione ni sincronice sus templates con Meta desde la plataforma.
- **Alcance mínimo — backend:**
  - Nueva tabla `app.whatsapp_templates` con campos: `id`, `tenant_id`, `channel_id`, `name`, `locale`, `category` (`utility` | `marketing` | `authentication`), `status` (`draft` | `pending` | `approved` | `rejected` | `paused`), `components jsonb` (header, body, footer, buttons según spec de Meta), `meta_template_id`, `rejection_reason`, timestamps. RLS por `tenant_id`.
  - Endpoints nuevos bajo `tenant_admin_router`:
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates` — registrar template (guarda en DB y llama a `/{WABA-ID}/message_templates` de Meta Graph API para enviarlo a revisión).
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates` — listar templates del tenant.
    - `GET /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — detalle con status actual.
    - `POST /v1/tenants/{tenant_id}/whatsapp/templates/sync` — llama a Meta para actualizar el `status` de todos los templates del tenant (para saber cuáles fueron aprobados/rechazados).
    - `DELETE /v1/tenants/{tenant_id}/whatsapp/templates/{template_id}` — eliminar en DB y en Meta.
  - En `scheduler.py`: antes de enviar un `reminder_job`, verificar que `template_name` existe en `whatsapp_templates` con `status='approved'` para el `channel_id` del job; si no existe o no está aprobado → marcar job como `failed` con error claro (`template_not_approved`).
  - Mapeo de propósito a template: campo `purpose` en `whatsapp_templates` (enum: `appointment_confirmation`, `appointment_reminder_24h`, `appointment_reminder_1h`, `reschedule_offer`, `handoff_notification`, `custom`). Permite que el sistema sepa qué template usar para cada tipo de recordatorio sin hardcodear nombres.
  - Tests estáticos: estructura de la tabla, validación de componentes, lógica de scheduler con template no aprobado.
- **Alcance mínimo — Admin Panel:**
  - En `WhatsAppOnboarding.jsx`: nueva sección **"Plantillas"** (tab o panel desplegable) con:
    - Lista de templates registrados con badge de estado (`Aprobado` / `Pendiente` / `Rechazado`) y motivo de rechazo visible cuando aplica.
    - Formulario para crear template: nombre, idioma, categoría, propósito (selector de los valores del enum), y editor visual de componentes (header texto/imagen, body con variables `{{1}}`, footer, botones de respuesta rápida).
    - Botón **"Sincronizar estado con Meta"** que llama al endpoint `/sync`.
    - Indicador por cada propósito de si tiene template aprobado asignado (semáforo: verde = listo, amarillo = pendiente, rojo = faltante).
  - En `GoLiveReadiness.jsx`: agregar check **"Plantillas mínimas aprobadas"** que valide que existen templates aprobados para al menos `appointment_confirmation` y `appointment_reminder_24h`.
- **Criterio de aceptación:** un admin puede crear un template desde el panel, sincronizar su estado con Meta y verlo aprobado; el scheduler rechaza el reminder con error claro si el template no está aprobado; el readiness check detecta cuando faltan templates mínimos; tests estáticos pasan en CI.
- **Dependencias:** TASK-0028 recomendada antes (el policy engine usa la ventana de servicio, cuya solución cuando expira es precisamente los templates).

---

### TASK-0027 — Implementar endpoints y panel de analítica básica

- **Objetivo:** el rol `manager` no tiene forma de monitorear el piloto en producción. Los endpoints `GET /analytics/overview` y `GET /analytics/conversations` están definidos en la arquitectura pero no existen. Sin ellos el equipo no puede responder "¿cuántas conversaciones entran?", "¿qué porcentaje escala a humano?" ni "¿qué intenciones predominan?".
- **Alcance mínimo — backend:**
  - `GET /v1/analytics/overview`: acepta `from_date` y `to_date` (default últimos 30 días); requiere rol `manager` o superior + `X-Tenant-Id`. Devuelve:
    - Conversaciones: total, abiertas, resueltas, en handoff.
    - Mensajes: inbound y outbound.
    - Tasa de handoff: `handoffs_creados / conversaciones_total`.
    - Citas: creadas, confirmadas, canceladas, completadas.
    - Service requests: por estado.
    - Conocimiento: documentos activos, chunks indexados, proveedor de embedding activo.
  - `GET /v1/analytics/conversations`: mismo filtro de fechas y tenant. Devuelve:
    - Distribución de conversaciones por estado.
    - Top 10 intenciones más frecuentes (agrupadas por `current_intent`).
    - Tiempo promedio en minutos desde apertura hasta primer handoff (cuando aplica).
    - Evolución diaria de conversaciones nuevas (array de `{date, count}`).
  - Ambos endpoints calculan directamente con SQL sobre tablas existentes; sin nuevas tablas.
  - Tests estáticos: estructura del response, controles de autorización (agent recibe 403, manager recibe 200).
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Analítica"** en `admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx`:
    - Selector de rango de fechas (últimos 7 días / 30 días / 90 días / personalizado).
    - Cards de KPIs (conversaciones, mensajes, tasa de handoff, citas).
    - Tabla de distribución de estados de conversación.
    - Tabla de top intenciones con conteo y porcentaje.
    - Tabla de service requests por estado.
    - Gráfico de evolución diaria (línea simple con datos del endpoint, sin librería externa — usar SVG nativo o tabla con mini barras en CSS).
  - Registrar el módulo en `admin-panel/src/data/modules.js` y en `AdminLayout.jsx` como nueva opción del sidebar, accesible para rol `manager` o superior.
- **Criterio de aceptación:** un usuario `manager` ve el panel con KPIs del período seleccionado; un usuario `agent` recibe 403 al llamar los endpoints; los datos son coherentes con los registros de la DB (validar con datos demo); el módulo aparece en el sidebar del Admin Panel; tests estáticos pasan en CI.
- **Dependencias:** TASK-0026 recomendada antes (para que `current_intent` tenga datos útiles en las métricas de intenciones), pero los demás KPIs pueden medirse desde ya.

---

### TASK-0029 — Ejecutar y validar drill de restore local (criterio pendiente de TASK-0015)

- **Objetivo:** los scripts `backup-local.sh` y `restore-local.sh` de TASK-0015 existen y compilan, pero nunca se ejecutaron contra un Docker Compose real con datos. El criterio de aceptación de TASK-0015 dice explícitamente "restore local probado con datos demo" y no se cumplió. Esta tarea lo valida y cierra ese pendiente.
- **Alcance mínimo:**
  - En un entorno con Docker y Docker Compose disponible:
    1. Levantar el stack completo con `./scripts/bootstrap.sh`.
    2. Ejecutar `./scripts/backup-local.sh` y verificar que genera dump SQL + manifiesto de objetos.
    3. Ejecutar `./scripts/bootstrap.sh --reset --yes --skip-smoke` para limpiar la base.
    4. Ejecutar `./scripts/restore-local.sh <backup-file>` y validar con SQL que tenants, documentos, chunks, audit logs y al menos una conversación demo están presentes.
    5. Documentar conteos antes/después en `docs/runbook-go-live-evidence.md`.
  - Si se detectan errores en los scripts durante la ejecución real, corregirlos y documentar los cambios.
  - Agregar test estático que verifique la sintaxis bash de ambos scripts con `bash -n`.
  - No hay cambios de Admin Panel en esta tarea.
- **Criterio de aceptación:** restore local ejecutado y exitoso con datos demo en Docker Compose; conteos documentados en `docs/runbook-go-live-evidence.md`; scripts pasan `bash -n`; evidencia commiteada.
- **Dependencias:** requiere entorno con Docker disponible. Si el entorno sigue sin Docker, documentar el bloqueo y no mover a DONE.
