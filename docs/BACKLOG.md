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
TASK-0041 (gestión de equipo y roles del tenant)
    ↓
TASK-0029 (drill de restore — cierre operacional)
```

---

## Stack de tareas pendientes

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

---

### TASK-0041 — Gestión de equipo y roles del tenant

- **Objetivo:** hoy no hay forma de invitar colaboradores ni cambiar el rol de un usuario dentro de un tenant. El único rol que se asigna automáticamente es `owner` al crear el tenant (`app/api/v1/routes.py:632`); cualquier otro cambio requiere `UPDATE` directo en `app.user_tenant_roles` y editar el usuario en Auth0 a mano. Esta tarea cierra esa brecha entregando endpoints + UI para administrar miembros y roles desde el Admin Panel, con sincronización a Auth0 vía Management API.
- **Alcance mínimo — backend:**
  - Endpoints (todos requieren rol `admin` o superior del tenant + `X-Tenant-Id`):
    - `GET /v1/tenants/{tenant_id}/members` — lista miembros (`user_id, auth_subject, email, display_name, roles[], is_default_role, created_at`). Una fila por usuario con sus roles agregados.
    - `POST /v1/tenants/{tenant_id}/members` — invitar usuario. Body: `{email, display_name?, role}` donde `role ∈ {'admin','manager','agent','viewer'}`. Si el usuario no existe en `app.users` se crea con `auth_subject` pendiente; se inserta una fila en `user_tenant_roles`; se dispara invitación vía Auth0 Management API (endpoint `POST /api/v2/tickets/password-change` con `result_url` al admin panel) si las credenciales Auth0 están configuradas. Si Auth0 no está disponible (modo desarrollo), se persiste el registro y se devuelve un flag `auth0_skipped: true`.
    - `PATCH /v1/tenants/{tenant_id}/members/{user_id}` — cambia rol. Body: `{role}`. El owner no puede ser degradado por nadie distinto de otro owner. Un usuario no puede degradarse a sí mismo si es el único `owner` del tenant. Tras actualizar la fila, sincronizar con Auth0 Management API (`PATCH /api/v2/users/{auth_subject}/roles`) para que el próximo JWT lleve el claim correcto.
    - `DELETE /v1/tenants/{tenant_id}/members/{user_id}` — revoca acceso al tenant. Borra todas las filas de `user_tenant_roles` para `(user_id, tenant_id)`. No elimina al usuario de `app.users` (puede pertenecer a otros tenants). Auditoría: `tenant_member.removed`. No permitir borrar al último `owner`.
  - Servicio nuevo `app/services/auth0_admin.py` con `get_management_token() → str` (cachea token Auth0 con TTL del `expires_in`), `invite_user(email, role, tenant_id) → ticket_url`, `assign_roles(auth_subject, roles) → None`, `revoke_tenant_roles(auth_subject, tenant_id) → None`. Si `AUTH0_DOMAIN` o `AUTH0_MGMT_CLIENT_ID/SECRET` no están en settings, el servicio retorna no-op con flag `disabled=true` (modo dev). Secrets viven en `.secrets/auth0_mgmt_*` siguiendo el patrón actual.
  - Auditoría: `tenant_member.invited`, `tenant_member.role_updated`, `tenant_member.removed` con `entity_id = user_id` y `metadata = {previous_role, new_role}`.
  - Tests estáticos: endpoints registrados con `require_min_role('admin')`, schema `MemberInvite`/`MemberRoleUpdate`, prevención de degradación de último owner, no-op de Auth0 cuando no está configurado, acciones de auditoría correctas.
- **Alcance mínimo — Admin Panel:**
  - Nuevo módulo **"Equipo"** (`admin-panel/src/components/modules/team/TeamModule.jsx`):
    - Tabla de miembros con columnas: nombre, email, rol actual (chip de color), último login (si Auth0 lo entrega), acciones.
    - Formulario "Invitar miembro": email, nombre opcional, select de rol (`admin`, `manager`, `agent`, `viewer`). Tras crear muestra el `ticket_url` para copiar al portapapeles si Auth0 está en modo no-op.
    - Acción **"Cambiar rol"** por fila: select inline con confirmación. Deshabilitado si el rol objetivo es `owner` y el usuario actual no es owner.
    - Acción **"Revocar acceso"** por fila con confirmación. Deshabilitada para el último owner.
    - Banner informativo cuando Auth0 Management API no está configurada: "Los cambios se reflejarán en el próximo login del usuario. Auth0 Management API no está habilitada — sincroniza manualmente desde el dashboard si es necesario."
  - Helpers en `admin-panel/src/services/coreApi.js`: `listTenantMembers`, `inviteTenantMember`, `updateTenantMemberRole`, `removeTenantMember`.
  - Registrar en `data/modules.js` y `AdminLayout.jsx`. Accesible para rol `admin` o superior; si el usuario es `manager` o menor, el módulo se oculta del sidebar.
- **Criterio de aceptación:** owner ve la lista de miembros del tenant; invita a un nuevo usuario con rol `manager` y aparece en la tabla; cambia el rol de un agente a manager y el siguiente JWT del usuario refleja el nuevo claim; intenta revocar al último owner y recibe 409; tests pasan en CI; un usuario con rol `agent` no ve el módulo en el sidebar y recibe 403 al pegar la URL.
- **Dependencias:** ninguna técnica nueva; usa `app.user_tenant_roles` existente y Auth0 ya integrado para auth. Bloquea la utilidad de TASK-0027 (analítica), TASK-0038 (campañas) y TASK-0040 (pagos) porque los tres asumen roles `manager`/`admin` configurables.
