# Acuerdo de Procesamiento de Datos (DPA) — CopilotoIA v1.0

**Versión:** 1.0  
**Fecha de vigencia:** 2026-05-08  
**Partes:** Anthropic/CopilotoIA (Encargado del Tratamiento) · Tenant (Responsable del Tratamiento)

---

## 1. Objeto y roles

CopilotoIA actúa como **Encargado del Tratamiento** de datos personales en nombre del Tenant (empresa u organización), quien actúa como **Responsable del Tratamiento** conforme a la Ley 1581 de 2012 (Colombia), el GDPR (EU) y demás normativas aplicables.

Los datos tratados incluyen: número de teléfono, nombre de contacto, historial de conversaciones WhatsApp, solicitudes de servicio y cotizaciones.

---

## 2. No entrenamiento de modelos (`no_train`)

- **Por defecto**, el campo `no_train` de cada tenant está establecido en `true`.
- Ningún dato de conversación, mensaje, contacto ni documento de conocimiento del tenant se usa para entrenar, afinar ni evaluar modelos de IA de terceros.
- Las llamadas a modelos externos (p. ej. proveedores de embeddings) se hacen únicamente para generar representaciones vectoriales del contenido del tenant con fines de búsqueda semántica local; los datos no se almacenan en los proveedores externos.
- Si el tenant modifica `no_train` a `false`, acepta explícitamente que sus datos anónimos de uso pueden contribuir a métricas de calidad de servicio internas (nunca a entrenamiento de modelos publicados).

---

## 3. Retención de datos

| Categoría | Retención | Justificación |
|-----------|-----------|---------------|
| Mensajes y conversaciones | 365 días desde última actividad del tenant | Operación y resolución de disputas |
| Contactos activos | Mientras el tenant esté activo | Continuidad del servicio |
| Contactos suprimidos | Seudónimo permanente | Cumplimiento (derecho al olvido ejecutado) |
| Audit logs | 730 días | Cumplimiento regulatorio y evidencia de auditoría |
| Webhooks raw | 30 días | Diagnóstico técnico |
| Documentos de conocimiento | Hasta eliminación manual | Configuración del tenant |
| Datos de tenant (config) | Hasta baja del tenant + 90 días | Portabilidad y disputas |

Tras los plazos indicados, los datos se eliminan o pseudonimizan de forma automatizada.

---

## 4. Derechos del interesado

El Tenant es responsable de gestionar las solicitudes de derechos de los interesados (contactos). CopilotoIA provee las herramientas técnicas:

### 4.1 Derecho al olvido / supresión

- Endpoint: `POST /v1/contacts/{contact_id}/suppress`
- UI: módulo **Audit → Supresión de contacto**
- Efecto: `display_name`, `phone_e164` y `wa_id` se sustituyen por seudónimos únicos basados en el UUID del contacto; `opt_in_status` se establece a `suppressed`; los campos `metadata` y `tags` se vacían.
- La acción queda registrada en `audit_logs` con `action='contact.suppressed'`.
- Plazo de ejecución: inmediato (sincrónico).
- Las conversaciones y mensajes históricos se conservan sin vínculo legible al contacto (el `contact_id` permanece como referencia opaca).

### 4.2 Portabilidad de datos

- Endpoint: `GET /v1/tenants/{tenant_id}/data-export`
- UI: módulo **Audit → Exportación de datos del tenant**
- Devuelve configuración del tenant, ajustes de privacidad, canales y conteos de datos operativos en formato JSON.
- No incluye mensajes en texto claro ni datos personales de contactos en el export de configuración.

### 4.3 Consulta de auditoría

- Endpoint: `GET /v1/audit-logs` (con filtros) · `GET /v1/audit-logs/export` (CSV)
- UI: módulo **Audit → Audit logs**
- Roles requeridos: `admin` o superior.

---

## 5. Medidas técnicas y organizativas

### 5.1 Pseudonimización y redacción de PII

- Los logs de sistema (structlog JSON) redactan automáticamente teléfonos en formato E.164 (`[PHONE]`) y direcciones de correo (`[EMAIL]`) antes de escribirlos a stdout.
- Los campos `phone_e164`, `wa_id` y `display_name` nunca aparecen en texto claro en logs de aplicación.

### 5.2 Aislamiento por tenant

- Row-Level Security (RLS) de PostgreSQL en todas las tablas de datos.
- Cada transacción establece `app.tenant_id` antes de cualquier operación; los datos de otros tenants son físicamente inaccesibles.

### 5.3 Control de acceso

- Autenticación JWT (Auth0 RS256) o token de servicio HS256 local.
- RBAC con roles `owner > admin > manager > agent > viewer`.
- La supresión de contactos requiere rol `admin` mínimo.
- La exportación de datos del tenant requiere rol `owner`.

### 5.4 Canales cifrados

- Toda comunicación cliente-servidor usa TLS 1.2+.
- Los secretos de canal WhatsApp (tokens, app secrets) se almacenan en archivos del sistema de ficheros del servidor con permisos `0600`, nunca en base de datos.

---

## 6. Subencargados

| Subencargado | Servicio | Región | Garantía |
|---|---|---|---|
| Meta Platforms | WhatsApp Cloud API | Global | Cláusulas contractuales estándar (SCCs) |
| OpenAI / proveedor de embeddings | Generación de vectores semánticos (si se habilita) | EE.UU. | DPA propio del proveedor |
| Proveedor de infraestructura | Alojamiento de base de datos y aplicación | Según configuración del tenant | DPA del proveedor |

---

## 7. Notificación de brechas

En caso de brecha de seguridad que afecte datos personales, CopilotoIA notificará al Tenant en un plazo máximo de **72 horas** desde la detección, con descripción del incidente, datos afectados y medidas tomadas.

---

## 8. Baja del servicio

Cuando el tenant pasa a estado `churned` o solicita la baja:
1. Los datos operativos se retienen 90 días adicionales para facilitar exportaciones.
2. Transcurrido ese plazo, todos los datos del tenant se eliminan de forma permanente.
3. El tenant recibe confirmación escrita de la eliminación.
