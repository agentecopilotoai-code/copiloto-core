# Backlog API — Módulo Gestión Documental con IA

> Backlog **independiente** del producto principal (`docs/BACKLOG.md`). Cubre toda la capa de backend (API REST + workers + base de datos + integraciones + IA + auditoría) descrita en los 5 documentos fuente del cliente. Ver `README.md` de esta carpeta para reglas, mandato y prelación documental.

Prefijo de consecutivos: **`GD-API-NNNN`**. Prefijo de épicas: **`GD-API-EP-NNN`**.

---

## Índice de épicas

| # | Épica | Módulos del Mapa | Entrega objetivo |
|---|---|---|---|
| EP-001 | Identidad, acceso, roles y permisos | MOD-001 | Entrega 1 |
| EP-002 | Perfil de organización y estructura organizacional versionada | MOD-002, MOD-003 | Entrega 1 |
| EP-003 | ~~Auditoría base en `gd.*`~~ **→ deprecada, fusionada en EP-019** | MOD-016 | Entrega 1 |
| EP-004 | Ventanilla Única y radicación | MOD-004, MOD-005 | Entrega 2 |
| EP-005 | Terceros, ciudadanos y entidades externas | MOD-006 | Entrega 2 |
| EP-006 | Buzón de trabajo, tareas, notificaciones y alertas | MOD-009, MOD-015 | Entrega 3 |
| EP-007 | PQRSD — ciclo de vida completo | MOD-007 | Entrega 4 |
| EP-008 | Correspondencia interna y externa | MOD-008 | Entrega 5 |
| EP-009 | Documentos, anexos y versiones | MOD-010 | Entrega 6 |
| EP-010 | Plantillas documentales | MOD-011 | Entrega 6 |
| EP-011 | Firmas (escaneada, electrónica, preparación digital) | MOD-012 | Entrega 6 |
| EP-012 | Integración con correo institucional | MOD-018 | Entrega 7 |
| EP-013 | Agentes IA asistidos | MOD-019 | Entrega 7 |
| EP-014 | Reportes e indicadores | MOD-017 | Entrega 7 |
| EP-015 | TRD, TVD, series, subseries y clasificación documental | MOD-013 | Entrega 8 |
| EP-016 | Expediente electrónico básico | MOD-014 | Entrega 8 |
| EP-017 | Preparación para RPA y APIs públicas | MOD-020 | Futura |
| EP-018 | Servicio transversal de archivos, extracción y OCR | Compartido con Knowledge | Entrega 6 (precede EP-009) |
| EP-019 | Auditoría transversal `core.evento_auditoria` | Compartido con app/Knowledge/gd | Entrega 1 (precede EP-001) |
| EP-020 | Gaps de cobertura cerrados tras auditoría 2026-05-20 | Múltiples | Distribuida (cada tarea entra en la entrega donde corresponde su dominio) |
| EP-021 | Periféricos de Ventanilla Única (impresoras, escáneres, códigos de barras/QR, agente local) | MOD-004, MOD-016 | Entrega 2 (extiende EP-004) |

---

## EP-001 — Identidad, acceso, roles y permisos

**Módulos:** MOD-001
**Entidades del módulo GD (nuevas):** `gd.rol`, `gd.permiso`, `gd.rol_permiso` (catálogos del dominio), `gd.perfil_usuario` (1:1 con `app.users`, campos institucionales), `gd.asignacion_alcance` (alcance por dependencia para roles GD), `gd.cargo` (estructura mínima; vigencia en EP-002).
**Entidades reutilizadas del producto principal (NO se duplican):** `app.users` (identidad y autenticación), `app.user_tenant_roles` (membresía usuario↔tenant↔rol — el `role` lleva prefijo `gd.*` para los roles del módulo), `app.tenants` (la organización pagadora — ver EP-002).
**RNF objetivo:** RNF-005, RNF-006, RNF-007, RNF-008, RNF-019, RNF-020, RNF-041, RNF-052, RNF-055
**Roles primarios:** ROL-001 (Admin Sistema), ROL-002 (Admin Seguridad), todos los demás como consumidores.

> **Decisión de diseño explícita.** El módulo Gestión Documental **no crea** `gd.usuario` ni `gd.usuario_rol` ni tablas paralelas de identidad. Los usuarios ya viven en `app.users`; la pertenencia a una organización con un rol vive en `app.user_tenant_roles` con `role` texto libre (ya migrado a libre por TASK-0033). Lo único genuinamente nuevo del dominio institucional es: (a) el catálogo de roles y permisos GD, (b) los atributos institucionales por usuario (tipo de vinculación, fechas, estado GD, dependencia actual) que viven en `gd.perfil_usuario` 1:1, y (c) el alcance por dependencia que un rol puede tener — eso es `gd.asignacion_alcance`. Esto evita duplicar tabla de usuarios, evita problemas de sincronización y reutiliza el tenant switcher, RLS y Auth0/JWT existentes.

### GD-API-0001 — Esquema GD de identidad/permisos (DDL, sin duplicar usuarios)
- **Estado:** PENDING
- **Por qué:** sin estas tablas no se puede validar autorización GD ni guardar snapshots históricos del rol y dependencia usados en una actuación. **No se duplica** `app.users` ni `app.user_tenant_roles`.
- **Crea (schema `gd`):**
  - `gd.rol` — catálogo: `codigo` (PK textual, ej. `gd.radicador`), `nombre`, `descripcion`, `es_sistema` bool (true para los 19 roles seed), `estado`. Es **catálogo de tipos**, no de membresías.
  - `gd.permiso` — catálogo: `codigo` (PK, ej. `PERM-PQRSD-009`), `nombre`, `modulo`, `descripcion`, `es_critico` bool, `estado`.
  - `gd.rol_permiso(rol_codigo, permiso_codigo, alcance_default)` — matriz N:N entre roles GD y permisos GD.
  - `gd.perfil_usuario(user_id PK FK→app.users, tipo_vinculacion ∈ {planta, provisional, ops, supernumerario, practicante, externo_autorizado, administrador_tecnico}, fecha_inicio_vinculacion, fecha_fin_vinculacion, estado_gd ∈ {activo, suspendido, inactivo, bloqueado, retirado}, dependencia_actual_id FK, cargo_actual_id FK)`. **1:1 con `app.users`**, solo agrega campos institucionales. Es por-usuario, no por-tenant — un mismo usuario que pertenezca a varios tenants GD tendrá un perfil distinto en cada uno, modelado vía `(user_id, tenant_id)` UNIQUE.
  - `gd.asignacion_alcance(id, user_id FK, tenant_id FK, rol_codigo FK→gd.rol, dependencia_id FK?, alcance ∈ {propio, dependencia, dependencias_autorizadas, institucional, global}, fecha_inicio, fecha_fin?, motivo, asignado_por_user_id FK)`. Esta tabla añade la dimensión que `app.user_tenant_roles` no tiene: **a qué dependencia aplica un rol GD**. Un usuario puede tener `gd.profesional` con alcance "Oficina Jurídica" y `gd.usuario_consulta` con alcance "toda la entidad" — dos filas.
  - `gd.cargo(id, nombre, dependencia_id, fecha_inicio_vigencia, fecha_fin_vigencia, estado)`. Vigencia se profundiza en EP-002.
- **Reglas obligatorias:**
  - PK por UUID donde aplique; FK con `ON DELETE RESTRICT` siempre.
  - Trigger `BEFORE UPDATE` / `BEFORE DELETE` sobre `gd.perfil_usuario` y `gd.asignacion_alcance` que prohíbe DELETE; UPDATE solo permitido en columnas marcadas como "mutables" (`estado_gd`, `dependencia_actual_id`, `cargo_actual_id`, `fecha_fin_vinculacion`).
  - Índices: `gd.perfil_usuario(user_id, tenant_id)`, `gd.asignacion_alcance(user_id, tenant_id, fecha_fin)`, `gd.asignacion_alcance(dependencia_id, rol_codigo)`.
  - RLS sobre `gd.perfil_usuario`, `gd.asignacion_alcance`, `gd.cargo` con política `tenant_id = app.current_tenant_id()`. (Las tablas-catálogo `gd.rol`, `gd.permiso`, `gd.rol_permiso` son globales y sin RLS — son enums.)
- **Seed inicial:** 19 roles ROL-001..ROL-019 (con `codigo` prefijado `gd.*`: `gd.admin_sistema`, `gd.radicador`, `gd.profesional`, etc.), ~140 permisos del catálogo (PERM-USR-001..PERM-NOT-007), matriz `gd.rol_permiso` derivada de la sección 9 del PDF Matriz de Roles.
- **Aceptación:** migración limpia sobre BD existente que ya tiene `app.users` y `app.user_tenant_roles`; intentar `DROP TABLE app.users` falla por FK; intentar `DELETE FROM gd.perfil_usuario` falla por trigger; seed lista 19 roles GD y >130 permisos GD; `gd.rol` no contiene rol `owner` ni `agent` del producto principal (zonas de responsabilidad separadas).

### GD-API-0002 — Reutilización de la autenticación existente (sin endpoints duplicados)
- **No crea endpoints de auth nuevos.** El producto ya tiene Auth0/JWT, sesiones, refresh, MFA preparada y un endpoint `GET /v1/me/tenants` para tenant switcher. Duplicarlo bajo `/api/v1/gd/auth/*` rompería SSO y obligaría a mantener dos sistemas de tokens en paralelo.
- **Sí crea:**
  - Middleware/dependency `require_gd_perfil(user, tenant_id)` que valida que el usuario autenticado tenga `gd.perfil_usuario.estado_gd='activo'` para el tenant activo; si no, responde `403 gd_profile_missing_or_inactive` con un mensaje claro al cliente.
  - Endpoint `GET /api/v1/gd/me` que extiende `GET /v1/me` con los campos GD: tipo_vinculacion, dependencia_actual, cargo_actual, roles GD vigentes y permisos efectivos calculados.
  - Mapeo de claims Auth0: documentar cómo `app_metadata.gd_perfil` aparece en el JWT (si la entidad usa Auth0 con SAML institucional) y cómo se sincroniza con `gd.perfil_usuario` en cada login (job idempotente que lee claims y mantiene perfil al día).
  - Validación al login (hook): si el usuario no tiene `gd.perfil_usuario` para el tenant pero su rol en `app.user_tenant_roles` tiene prefijo `gd.*`, se autocrea perfil con valores neutros pendientes de completar por Admin Sistema.
- **RNF:** RNF-005, RNF-019 (la política de sesiones es la del sistema existente, no se redefine), RNF-018, RNF-047.
- **Eventos:** los existentes (`user.login`, `user.logout`) ya cubren — solo se añade `dominio='gd'` cuando el contexto activo es módulo Gestión Documental, en `core.evento_auditoria` (ver EP-019).
- **Aceptación:** un usuario con `app.user_tenant_roles.role='gd.profesional'` y sin perfil GD recibe perfil auto-creado en su primer login; un usuario con perfil `estado_gd='inactivo'` que se autentica con Auth0 recibe 403 al llamar cualquier endpoint `/api/v1/gd/*` pero puede seguir usando `/v1/*` del producto principal si tiene otros roles ahí.

### GD-API-0003 — Gestión institucional del usuario sobre `gd.perfil_usuario`
- **No CRUD de identidad** (eso vive en el producto principal vía endpoints de tenant admin existentes). Esta tarea **administra el lado institucional** del usuario que ya existe en `app.users`.
- **Crea:**
  - `POST /api/v1/gd/perfil-usuario` body `{ user_id, tipo_vinculacion, fecha_inicio_vinculacion, fecha_fin_vinculacion?, dependencia_actual_id, cargo_actual_id? }` — invitar a un usuario existente al módulo GD del tenant activo.
  - `PATCH /api/v1/gd/perfil-usuario/{user_id}` — actualizar tipo_vinculacion, dependencia, cargo, fecha_fin_vinculacion.
  - `POST /api/v1/gd/perfil-usuario/{user_id}/inactivar | bloquear | desbloquear | retirar | suspender` con motivo.
  - `GET /api/v1/gd/perfil-usuario` (listar usuarios GD del tenant) y `GET /api/v1/gd/perfil-usuario/{user_id}/historial` (cambios de estado, dependencia, cargo).
- **Permisos:** PERM-USR-001..PERM-USR-012. El permiso PERM-USR-001 ("crear usuario") en realidad significa "invitar un usuario existente al módulo GD"; **crear** el `app.users` real lo hace el flujo de invitación del producto principal (que envía email Auth0, etc.). Esto separa "alta del sistema" de "alta institucional".
- **Reglas:**
  - Inactivar perfil GD revoca todos los `app.user_tenant_roles` con prefijo `gd.*` para ese tenant (deja `owner`/`agent`/`manager` intactos si existen para otros módulos del mismo tenant). Si solo era usuario GD, el efecto es "no aparece más para módulos GD".
  - Retirar dispara job que lista tareas pendientes (PQRSD asignadas, documentos por firmar) y exige reasignación previa (GD-API-0008).
  - El `app.users.email` no se toca desde GD — gestionarlo solo desde tenant admin del producto principal.
- **RNF:** RNF-007, RNF-020, RNF-010, RNF-009.
- **Eventos:** `gd.perfil_usuario.creado`, `gd.perfil_usuario.inactivado`, `gd.perfil_usuario.bloqueado`, `gd.perfil_usuario.retirado` — todos en `core.evento_auditoria` con `dominio='gd'`.
- **Aceptación:** invitar a `juan@ejemplo.com` (usuario existente en `app.users`) como `gd.profesional` de la "Oficina Jurídica"; `gd.perfil_usuario` se crea y aparece una fila en `app.user_tenant_roles`; inactivar el perfil revoca el rol GD pero el usuario sigue autenticándose y puede acceder a otros módulos del tenant.

### GD-API-0004 — Catálogo de roles GD y matriz rol↔permiso (sin runtime)
- **Aclaración:** `gd.rol` es un catálogo de **tipos de rol** (los 19 ROL-001..ROL-019). No es la tabla de "qué roles tiene Juan" — eso vive en `app.user_tenant_roles` (membresía) + `gd.asignacion_alcance` (dimensión dependencia).
- **Crea:** `POST/GET/PATCH /api/v1/gd/roles`, `POST /api/v1/gd/roles/{codigo}/inactivar`, `POST /api/v1/gd/roles/{codigo}/permisos` (agregar permiso a la matriz), `DELETE /api/v1/gd/roles/{codigo}/permisos/{permiso_codigo}` (revoca de matriz, no borra el permiso), `GET /api/v1/gd/permisos`.
- **Permisos:** PERM-ROL-001..PERM-ROL-007.
- **RNF:** RNF-006, RNF-007, RNF-009.
- **Reglas:** roles seed (`es_sistema=true`) no se inactivan pero se puede editar su matriz; intentar inactivar un rol que tiene asignaciones activas en `app.user_tenant_roles`+`gd.asignacion_alcance` retorna `409 role_in_use` con lista de tenants y usuarios afectados.
- **Eventos:** `gd.rol.creado`, `gd.rol.inactivado`, `gd.rol_permiso.modificado`.

### GD-API-0005 — Asignación de un rol GD a un usuario con alcance por dependencia
- **Crea:**
  - `POST /api/v1/gd/usuarios/{user_id}/roles` body `{ rol_codigo, dependencia_id?, alcance: "propio"|"dependencia"|"dependencias_autorizadas"|"institucional"|"global", fecha_inicio, fecha_fin?, motivo }`. La operación es transaccional:
    1. Inserta fila en `app.user_tenant_roles(user_id, tenant_id, role=rol_codigo)` si no existe.
    2. Inserta fila en `gd.asignacion_alcance(user_id, tenant_id, rol_codigo, dependencia_id, alcance, fecha_inicio, fecha_fin, motivo, asignado_por_user_id)`.
  - `POST /api/v1/gd/usuarios/{user_id}/roles/{asignacion_alcance_id}/cerrar` body `{ motivo }` — cierra la vigencia. Si era la última asignación de ese rol para ese usuario+tenant, también remueve la fila de `app.user_tenant_roles`.
  - `GET /api/v1/gd/usuarios/{user_id}/roles` retorna roles vigentes + alcance.
- **RNF:** RNF-006, RNF-007, RNF-008.
- **Reglas:**
  - Un usuario puede tener varios roles distintos en el mismo tenant — múltiples filas en `gd.asignacion_alcance` con `rol_codigo` distinto.
  - Un mismo `rol_codigo` con alcance distinto en dos dependencias se modela con dos filas en `gd.asignacion_alcance` (mismo `user_tenant_role` apunta a ambas — la matriz es 1 → N).
  - Asignaciones cerradas con `fecha_fin` se conservan permanentemente — son la base de los snapshots históricos que `core.evento_auditoria` necesita.
- **Aceptación:**
  - Asignar `gd.profesional` con alcance "Oficina Jurídica" a Juan: aparece fila en `app.user_tenant_roles(user_id=juan, role='gd.profesional')` (si no existía) y en `gd.asignacion_alcance`. Listar PQRSD como Juan retorna solo las de Oficina Jurídica.
  - Reasignar a "Secretaría de Salud" (cerrar la anterior + crear nueva): aparecen dos filas en `gd.asignacion_alcance` (una con `fecha_fin`, una abierta); las PQRSD históricas asignadas mantienen el snapshot original "Oficina Jurídica" en `core.evento_auditoria` aunque Juan ya no esté allá.

### GD-API-0006 — Middleware de autorización por permiso + alcance
- **Crea:** decorador / middleware `requires(permiso="PERM-PQRSD-009", alcance="dependencia")` consumible desde cada router.
- **Reglas:** valida sesión, carga roles vigentes, deriva permisos efectivos, evalúa alcance contra el recurso (radicado, PQRSD, documento, dependencia objetivo). Falla 403 + emite evento `AccesoDenegado` cuando no aplica.
- **RNF:** RNF-006, RNF-007, RNF-047 (no expone detalles del recurso en el error).
- **Aceptación:** test integración con dos usuarios (uno permitido, uno no) sobre el mismo endpoint dummy retorna 200 y 403 respectivamente, ambos con evento auditado.

### GD-API-0007 — Política de contraseñas + historial + integración futura SSO/LDAP/MFA
- **Crea:**
  - Tabla `gd.politica_contrasena` (longitud mínima, complejidad regex, historial N últimas, vigencia días, intentos fallidos máx, cooldown segundos).
  - **Tabla `gd.historico_contrasena(user_id, hash, salt, creada_en)`** — guarda las últimas N contraseñas del usuario para validar no-reuso (cierra GAP-4 detectado en TRAZABILIDAD.md).
  - Endpoints `GET/PATCH /api/v1/gd/seguridad/politica`.
  - Stub `gd.proveedor_identidad_externo` (SSO/SAML/LDAP/AD) para fase futura.
- **Doc fuente:** RNF-005 ("Debe existir política de complejidad de contraseña" + "bloqueo o protección ante intentos fallidos repetidos").
- **RNF:** RNF-005 (multifactor preparado), RNF-019.
- **Reglas:** la verificación de no-reuso compara el nuevo hash contra los N hashes históricos del usuario (no contra el hash actual solamente).
- **Aceptación:** cambiar política rechaza contraseñas que no cumplan; intentar reusar las últimas N contraseñas falla con `409 password_reused`; auditado en `core.evento_auditoria`.

### GD-API-0008 — Reasignación de tareas al inactivar perfil GD del usuario
- **Crea:** `GET /api/v1/gd/perfil-usuario/{user_id}/tareas-pendientes`, `POST /api/v1/gd/perfil-usuario/{user_id}/tareas/reasignar` (`{ tareas: [...], user_destino_id, motivo }`).
- **Permiso:** PERM-USR-009.
- **RNF:** RNF-020.
- **Reglas:**
  - "Inactivar usuario GD" significa cambiar `gd.perfil_usuario.estado_gd` (no toca `app.users.status` — esa decisión es del producto principal).
  - Antes de marcar `estado_gd='inactivo'` o `'retirado'`, el sistema **bloquea** la operación con `409 pending_tasks` si hay tareas abiertas; el admin debe reasignar primero o usar el wizard de reasignación masiva (GD-UI-0019).
  - Cada reasignación deja registro en `gd.asignacion_pqrsd` / `gd.tarea` con `motivo` + emite evento `gd.tarea.reasignada` en `core.evento_auditoria`.
  - Se prohíbe reasignar a usuarios con `gd.perfil_usuario.estado_gd != 'activo'`.
  - El historial de asignaciones cerradas (`gd.asignacion_alcance.fecha_fin`) permite reconstruir, dado un radicado histórico, en qué dependencia estaba el usuario que actuó.

### GD-API-0009 — Snapshot de identidad por actuación
- **Crea:** función SQL `gd.capturar_snapshot_actuacion(usuario_id)` que devuelve `(usuario_id, nombre, rol_codigo, dependencia_codigo, cargo, fecha_hora)`.
- **Por qué:** RNF-006 exige conservar el rol histórico usado en una actuación. Todos los inserts de auditoría / firma / asignación llaman esta función.
- **Aceptación:** cambiar el cargo del usuario después de una firma no altera el cargo registrado en la firma.

### GD-API-0010 — Matriz de permisos como documento navegable
- **Crea:** archivo `docs/gestion documental/MATRIZ_PERMISOS.md` con la matriz Rol × Permiso (S/C/N) traducida del PDF Matriz de Roles.
- **Por qué:** el RNF-051 exige documentación; el equipo y el cliente necesitan ver la matriz sin abrir el PDF.
- **Aceptación:** el documento incluye los 19 roles y los ~140 permisos; cada celda referencia el PERM-NNN y el ROL-NNN.

---

## EP-002 — Perfil de organización y estructura organizacional versionada

**Módulos:** MOD-002, MOD-003
**Entidades:** `gd.perfil_organizacion` (1:1 con `app.tenants`), `gd.configuracion_institucional`, `gd.dependencia`, `gd.version_estructura_organica`, `gd.cargo`, `gd.canal`, `gd.calendario_institucional`, `gd.parametro`
**RNF objetivo:** RNF-026, RNF-041, RNF-055.
**Roles primarios:** ROL-001 Admin Sistema, ROL-003 Admin Documental.
**Decisión clave:** este módulo **no asume sector público**. El cliente final puede ser una empresa privada (manufactura, salud, financiero), una ONG, una entidad mixta o una entidad pública. La nomenclatura "PQRSD", "TRD/TVD", "constancia", "Ventanilla Única" se conserva (la documentación fuente lo exige), pero su comportamiento se ajusta por configuración por organización — no por código distinto.

### GD-API-0011 — Perfil de organización 1:1 con tenant (neutro de sector)
- **No crea concepto paralelo de "entidad".** La organización pagadora ya existe en `app.tenants` (RLS activo en 44 tablas, tenant switcher, `user_tenant_roles`). Esta tarea crea `gd.perfil_organizacion` con FK **UNIQUE** sobre `app.tenants(id)`, agregando solo los campos institucionales que `tenants` no tiene.
- **Columnas del perfil:** `tenant_id` (PK + FK UNIQUE), `tipo_organizacion ∈ {publica, privada, mixta, ong, gremial, cooperativa}`, `identificacion_fiscal` (NIT en Colombia / RFC / EIN / CUIT — texto libre), `tipo_identificacion_fiscal`, `razon_social_legal`, `nombre_corto`, `direccion_oficial`, `telefono_oficial`, `correo_oficial`, `sitio_web`, `logo_archivo_digital_id` (FK a `core.archivo_digital`), `politica_firma_default ∈ {escaneada, electronica, digital_certificada}`, `formato_radicado` (template como `{prefijo}-{vigencia}-{consecutivo:06d}`), `dias_alerta_vencimiento_default`, `pais_iso`, `zona_horaria_default`.
- **Aceptación:** un tenant existente puede crear su perfil sin migrar datos; un tenant nuevo creado para una empresa privada (`tipo_organizacion='privada'`) recibe valores default coherentes (firma electrónica, calendario laboral genérico, sin PQRSD legal activado).

### GD-API-0011.b — Catálogo de módulos activables por organización
- Tabla `gd.organizacion_modulo_activacion(tenant_id, modulo_codigo, activado bool, configuracion jsonb)`.
- **Módulos individualmente activables:** `pqrsd_legal` (con términos legales y constancias formales), `pqrsd_tickets` (versión simplificada para empresa privada sin obligación legal), `correspondencia_interna`, `correspondencia_externa`, `firma_escaneada`, `firma_electronica`, `firma_digital_certificada`, `expedientes`, `trd_tvd`, `integracion_correo`, `agentes_ia`, `radicacion_externa_desde_dependencia`, `consulta_publica_radicado` (constancias con QR verificables sin login — típico sector público).
- **Endpoint:** `GET/PATCH /api/v1/gd/organizacion/modulos` (PERM-USR-001).
- **Aceptación:** empresa privada activa `pqrsd_tickets` + `correspondencia_interna` + `firma_electronica` y desactiva `trd_tvd`, `consulta_publica_radicado`; el menú lateral de UI no muestra TRD ni la página pública de verificación.
- **Por qué:** RNF-055 (multi-entidad). El documento fuente describe una alcaldía pero el producto debe operar en hospital privado, holding empresarial, ONG, sin reescribir.

### GD-API-0011.c — Defaults sensatos por tipo de organización
- Job que al crear el perfil aplica configuración inicial coherente:
  - `tipo_organizacion='publica'` → todos los módulos activos, calendario hábil colombiano (Ley 1755 PQRSD), TRD obligatoria, constancias públicas con QR.
  - `tipo_organizacion='privada'` → módulos básicos (correspondencia + documentos + firma electrónica + IA), PQRSD desactivado por default, TRD opcional, sin consulta pública.
  - `tipo_organizacion='ong'` → similar a privada pero con expedientes activos por default (importante para donantes).
  - `tipo_organizacion='mixta'` → como pública pero con FAQ explicativa al admin sobre cuáles módulos legales aplican.
- El admin puede sobreescribir cualquier default desde la UI (GD-UI-0052).

### GD-API-0012 — Estructura orgánica versionada
- Crea tablas `gd.version_estructura_organica`, `gd.dependencia` (con `version_estructura_id`, `dependencia_padre_id`, vigencia).
- Endpoints: `POST/GET/PATCH /api/v1/gd/dependencias`, `POST /api/v1/gd/dependencias/{id}/cerrar-vigencia`, `POST /api/v1/gd/estructura/versiones` (abre nueva versión y clona estado anterior), `GET /api/v1/gd/estructura/vigente`, `GET /api/v1/gd/estructura/historica?fecha=YYYY-MM-DD`.
- **Reglas:** una dependencia con radicados asociados no se modifica en su versión vigente; cambio de nombre exige abrir nueva versión. Bloqueo a `DELETE`.
- **RNF:** RNF-026, RNF-010.
- **Aceptación:** crear radicado en dependencia X, cerrar vigencia de X, consultar el radicado → muestra dependencia "X" original; consultar dependencia X hoy → muestra estado `cerrada`.

### GD-API-0013 — Cargos institucionales con vigencia
- CRUD `gd.cargo` con `dependencia_id`, `fecha_inicio_vigencia`, `fecha_fin_vigencia`, `estado`.
- **RNF:** RNF-026 (cargo histórico no se altera). Las firmas y actuaciones guardan el cargo como snapshot — ver GD-API-0009.

### GD-API-0014 — Canales, calendarios y términos de respuesta configurables
- Tablas `gd.canal`, `gd.calendario_institucional` (días hábiles, festivos), `gd.tipo_pqrsd` (con `termino_dias`, `tipo_dias hábiles|calendario`), `gd.tipo_correspondencia`.
- Endpoints CRUD + lectura agregada para frontend.
- **RNF:** RNF-023 (cálculo de términos hábiles), RNF-041, RNF-042 (manejo de estados controlados).
- **Aceptación:** dado un calendario con feriados, crear una PQRSD un viernes con término 5 días hábiles produce fecha_limite correcta saltando fin de semana y feriados.

### GD-API-0015 — Parámetros institucionales clave-valor con vigencia
- Tabla `gd.parametro` (clave, valor, descripcion, vigencia).
- Endpoints `GET/PATCH /api/v1/gd/parametros`, `GET /api/v1/gd/parametros/{clave}`.
- **Parámetros mínimos seed:** formato de radicado (prefijo, longitud consecutivo, formato fecha), días de alerta antes vencimiento (default 3), tamaño máx anexo (default 25 MB), tipos MIME permitidos, política de firma (escaneada habilitada sí/no), reglas de acuse de recibido.
- **RNF:** RNF-041, RNF-043 (parametrización de flujos).

### GD-API-0016 — Reglas de comunicación entre dependencias
- Tabla `gd.regla_comunicacion_interdependencia(dependencia_origen_id, dependencia_destino_id, permitido bool, requiere_jefe bool)`.
- Endpoints CRUD + endpoint `GET /api/v1/gd/reglas/comunicacion/validar?origen=&destino=`.
- **RNF:** RNF-056 (trazabilidad y permisos de comunicaciones internas).
- **Consumido por:** EP-008 (correspondencia interna) — un intento de enviar mensaje entre dependencias no permitidas devuelve 403.

---

## EP-003 — ~~Auditoría base en `gd.*`~~ → **DEPRECADA, FUSIONADA EN EP-019**

> Las tareas que estaban aquí (GD-API-0017..0022) se reemplazaron por el servicio transversal en `core.*` (ver **EP-019** al final del backlog). Razón: el sistema actual ya tiene `app.audit_logs` con 121 acciones auditadas (citas, contactos, planes, exportes GDPR) — duplicarlo en `gd.evento_auditoria` para los 33 eventos del documento PQRSD partía la verdad de auditoría en dos tablas. Pero `app.audit_logs` tiene **tres limitaciones técnicas** que lo descalifican como tabla canónica sin refactor: (1) no es append-only (sin triggers contra UPDATE/DELETE — solo `consent_ledger` los tiene), (2) no está particionada (volumen PQRSD puede superar 10M/año en organizaciones medianas), (3) no guarda `valor_anterior` / `valor_nuevo` / `criticidad` / `justificacion` / `request_id` que el documento PQRSD exige en RNF-009.
>
> EP-019 resuelve las tres limitaciones creando `core.evento_auditoria` con append-only por trigger, particionado mensual y snapshots completos, **migrando** `app.audit_logs` y `app.consent_ledger` al modelo unificado.

---

## EP-004 — Ventanilla Única y radicación

**Módulos:** MOD-004 (Ventanilla), MOD-005 (Radicación)
**Entidades:** `radicado`, `consecutivo_radicacion`, `canal`, `clasificacion_radicado`, `solicitud_anulacion`, `constancia`.
**RNF objetivo:** RNF-011 (radicado único), RNF-012 (trazabilidad), RNF-058 (control anulación), RNF-044 (calidad datos), RNF-045 (anexos), RNF-003 (rendimiento <3s crear radicado).
**Roles primarios:** ROL-004 Radicador, ROL-005 Coordinador VU.

### GD-API-0023 — Consecutivos transaccionales por vigencia y tipo
- Tabla `gd.consecutivo_radicacion` (`vigencia`, `tipo_radicado`, `prefijo`, `ultimo_numero`, `formato`). `SELECT ... FOR UPDATE` o `ADVISORY LOCK` para concurrencia.
- Función `gd.siguiente_radicado(vigencia, tipo)` retorna `numero_radicado` ya formateado.
- **RNF:** RNF-011, RNF-003 (debe responder < 50 ms incluso con 50 inserciones concurrentes).
- **Aceptación:** test de carga con 100 inserciones concurrentes — sin duplicados, consecutivos contiguos.

### GD-API-0024 — Crear radicado de entrada
- `POST /api/v1/gd/ventanilla/radicados/entrada` con body `{ canal_id, tercero_id?, tercero_nuevo?, asunto, descripcion, anexos: [archivo_id], clasificacion_sugerida?, sugerencia_ia_id? }`.
- **Permisos:** PERM-VU-001, PERM-VU-003, PERM-VU-005.
- **Reglas:** genera consecutivo, crea `constancia` con QR/código verificación (RNF-011 último criterio), guarda anexos como `anexo` apuntando a `archivo_digital` ya cargado, emite `RadicadoCreado`.
- **Eventos:** `RadicadoCreado`, `ConstanciaGenerada`.
- **Aceptación:** test crea radicado, response incluye `numero_radicado`, `constancia_url`; intentar editar `numero_radicado` vía PATCH falla con 405.

### GD-API-0025 — Crear radicado de salida
- `POST /api/v1/gd/ventanilla/radicados/salida` con `{ radicado_relacionado_id?, dependencia_origen_id, tercero_destinatario_id, asunto, documento_id }`.
- **Permisos:** PERM-VU-002 + validación de que el documento adjunto esté en estado `aprobado` o `firmado` (depende de EP-009/EP-011).
- **Reglas:** si viene `radicado_relacionado_id`, se valida que sea de tipo entrada y esté en estado válido para respuesta. Permite la radicación directa desde dependencia (PERM-CE-009) sólo si el rol tiene ese permiso.

### GD-API-0026 — Clasificación inicial y derivación
- `POST /api/v1/gd/ventanilla/radicados/{id}/clasificar` body `{ tipo_clasificacion: "pqrsd"|"correspondencia_externa"|"correspondencia_interna"|"tramite"|"expediente", sub_tipo?, dependencia_destino_id?, justificacion?, sugerencia_ia_id? }`.
- **Permiso:** PERM-VU-008 + PERM-VU-009..012.
- **Reglas:** guarda historial en `clasificacion_radicado`; al clasificar como `pqrsd` dispara creación de `gd.pqrsd` con cálculo de término (EP-007); al clasificar como `correspondencia_externa` crea `gd.correspondencia` (EP-008).
- **Eventos:** `RadicadoClasificado`, `RadicadoDerivado`, `PQRSDCreada` (si aplica).

### GD-API-0027 — Reclasificación con trazabilidad
- `POST /api/v1/gd/ventanilla/radicados/{id}/reclasificar` con `justificacion` obligatoria; conserva la clasificación anterior con `estado='reemplazada'`.
- **RNF:** RNF-012 (trazabilidad), RNF-042 (manejo de estados).

### GD-API-0028 — Anulación de radicados (flujo de aprobación)
- `POST /api/v1/gd/ventanilla/radicados/{id}/solicitar-anulacion` body `{ motivo }`.
- `POST /api/v1/gd/ventanilla/anulaciones/{solicitud_id}/aprobar` o `/rechazar` body `{ observacion }`.
- **Permisos:** PERM-VU-015 para solicitar, PERM-VU-016 para aprobar (distintos usuarios — RNF-008).
- **Reglas:** al aprobar, el radicado pasa a `anulado`; el número queda quemado; sigue visible en consultas y auditoría (RNF-058).
- **Eventos:** `RadicadoAnulacionSolicitada`, `RadicadoAnulado`.

### GD-API-0029 — Consulta y búsqueda de radicados
- `GET /api/v1/gd/ventanilla/radicados?numero=&tercero=&asunto=&estado=&fecha_desde=&fecha_hasta=&dependencia=&serie=&page=&size=`.
- **Permiso:** PERM-VU-019 + alcance del rol.
- **RNF:** RNF-003 (<2s consulta por número), RNF-039 (búsqueda multi-criterio), RNF-053 (clasificación info reservada).
- **Reglas:** quien no tiene alcance no ve el radicado; consultar uno marcado como `reservado` deja registro de consulta (RNF-059).

### GD-API-0030 — Constancia con QR + endpoint público de verificación
- `GET /api/v1/gd/ventanilla/constancias/{codigo}` (sin auth, solo lectura) devuelve `{ numero_radicado, fecha_radicacion, asunto_resumido, estado_actual }` — no expone datos sensibles del tercero ni del cuerpo del trámite.
- Generación de PDF con plantilla (depende de EP-010 plantilla "Constancia de radicación").
- **RNF:** RNF-011, RNF-017 (protege datos personales).

### GD-API-0031 — Cola de pendientes de clasificación
- `GET /api/v1/gd/ventanilla/cola/pendientes-clasificacion` con paginación.
- Permite al coordinador (ROL-005) monitorear cuántos radicados están registrados pero no clasificados.

### GD-API-0032 — Corrección menor de datos del radicado (con auditoría)
- `PATCH /api/v1/gd/ventanilla/radicados/{id}/datos-menores` body `{ asunto?, descripcion?, tercero_id?, justificacion }`.
- **Permiso:** PERM-VU-014. **Nunca** permite cambiar `numero_radicado` ni `fecha_radicacion`.

---

## EP-005 — Terceros, ciudadanos y entidades externas

**Módulos:** MOD-006
**Entidades:** `tercero`, `contacto_tercero`
**RNF:** RNF-017 (datos personales), RNF-044 (calidad de datos / duplicados), RNF-053 (clasificación información).

### GD-API-0033 — CRUD de terceros con detección de duplicados
- `POST/GET/PATCH /api/v1/gd/terceros`, `GET /api/v1/gd/terceros/buscar?documento=&nombre=&email=` retorna posibles duplicados con score.
- **Reglas:** índices únicos por `(tipo_documento, numero_documento)` cuando no sea `anonimo`; ciudadano anónimo permite múltiples radicados sin documento.
- **RNF:** RNF-017, RNF-044.

### GD-API-0034 — Contactos múltiples (correo, teléfono, dirección)
- CRUD `gd.contacto_tercero` con flag `principal`; auditar cada cambio.

### GD-API-0035 — Endpoint de consulta histórica de un tercero (radicados + PQRSD + correspondencia)
- `GET /api/v1/gd/terceros/{id}/historial` agrega todos los trámites del tercero ordenados por fecha. Respeta permisos del consultante.

---

## EP-006 — Buzón de trabajo, tareas, notificaciones y alertas

**Módulos:** MOD-009 (Buzón + Tareas), MOD-015 (Notificaciones + Alertas)
**Entidades:** `tarea`, `notificacion`, `alerta`
**RNF:** RNF-021 (buzón por usuario y dependencia), RNF-022 (alertas y notificaciones), RNF-023 (cálculo de términos).
**Por qué antes de PQRSD:** PQRSD genera tareas; sin el dominio de Tareas no se puede modelar la asignación.

### GD-API-0036 — Modelo de Tarea genérico (no acoplado a PQRSD)
- DDL `gd.tarea` con `entidad_origen_tipo`, `entidad_origen_id` polimórficos (`pqrsd|correspondencia|documento|radicado`).
- Endpoints `GET /api/v1/gd/tareas?asignadas_a=me&estado=&fecha_limite_antes=`, `PATCH /api/v1/gd/tareas/{id}/{accion}` donde acción ∈ `iniciar|devolver|finalizar|reasignar|escalar|anular`.

### GD-API-0037 — Asignación y reasignación de tareas con motivo
- `POST /api/v1/gd/tareas/{id}/reasignar` body `{ usuario_destino_id, dependencia_destino_id?, motivo }`.
- **Permisos:** depende del tipo origen (PERM-PQRSD-008 para PQRSD, etc.) + alcance.
- **Reglas:** una tarea reasignada conserva la asignación anterior con `estado='reasignada'` y mantiene historial completo (RNF-012).

### GD-API-0038 — Endpoint del buzón de trabajo agregado
- `GET /api/v1/gd/buzon` retorna en una sola llamada: `{ pqrsd_asignadas, correspondencia_recibida, correspondencia_enviada, tareas_pendientes, borradores, doc_por_revisar, doc_por_aprobar, doc_por_firmar, notificaciones, alertas, vencimientos_proximos }` — todo filtrado por permisos y alcance.
- **RNF:** RNF-021. La respuesta agrega contadores y la primera página de cada lista (10 ítems c/u).
- **Aceptación:** un usuario sin rol Profesional no ve `doc_por_firmar`.

### GD-API-0039 — Buzón por dependencia (vista de jefe)
- `GET /api/v1/gd/buzon/dependencia/{id}` — exige rol ROL-009 (Jefe) o ROL-010 (Secretario) con alcance sobre esa dependencia.

### GD-API-0040 — Sistema de notificaciones in-app + correo
- DDL `gd.notificacion`; emisor que reacciona a eventos del bus (`PQRSDAsignada`, `RespuestaDevuelta`, `DocumentoAprobado`, etc.) y genera notificación in-app + correo opcional según preferencia del usuario.
- Endpoints `GET /api/v1/gd/notificaciones`, `POST /api/v1/gd/notificaciones/{id}/marcar-leida`.

### GD-API-0041 — Sistema de alertas críticas con escalado
- DDL `gd.alerta` con `severidad` y `tipo_alerta`. Job programado que detecta PQRSD próximas a vencer (umbral configurable RNF-022) y emite `PQRSDProximaAVencer` / `PQRSDVencida`.
- Endpoint para escalar alerta no atendida al jefe inmediato (PERM-NOT-006).

### GD-API-0042 — Cálculo de términos hábiles con calendario
- Servicio `calcular_fecha_limite(tipo_pqrsd_id, fecha_radicacion, calendario_id)` que considera días hábiles vs. calendario y suspensiones.
- Endpoint `POST /api/v1/gd/pqrsd/{id}/registrar-suspension` (PERM-PQRSD-023) que recalcula la fecha límite y deja trazabilidad.
- **RNF:** RNF-023.

---

## EP-007 — PQRSD — ciclo de vida completo

**Módulos:** MOD-007
**Entidades:** `pqrsd`, `tipo_pqrsd`, `asignacion_pqrsd`, `respuesta_pqrsd`
**RNF:** todos los anteriores + RNF-052 (cumplimiento normativo).
**Roles primarios:** ROL-006 Admin PQRSD, ROL-007 Profesional, ROL-008 Revisor, ROL-009 Jefe Dependencia, ROL-014 Firmante.

### GD-API-0043 — Creación automática de PQRSD al clasificar radicado
- Trigger / handler del evento `RadicadoClasificado` con tipo_clasificacion="pqrsd". Crea `gd.pqrsd` con fecha_limite calculada, estado `nueva`.
- **Eventos:** `PQRSDCreada`.

### GD-API-0044 — Asignación de PQRSD a dependencia y funcionario
- `POST /api/v1/gd/pqrsd/{id}/asignar-dependencia` (PERM-PQRSD-006).
- `POST /api/v1/gd/pqrsd/{id}/asignar-funcionario` (PERM-PQRSD-007).
- Crea entrada en `asignacion_pqrsd` con historial completo.
- **Eventos:** `PQRSDAsignada`.

### GD-API-0045 — Reasignación con justificación
- `POST /api/v1/gd/pqrsd/{id}/reasignar` (PERM-PQRSD-008). Cierra asignación anterior, abre nueva.
- **Eventos:** `PQRSDReasignada`.

### GD-API-0046 — Proyección de respuesta
- `POST /api/v1/gd/pqrsd/{id}/respuestas` body `{ documento_id?, plantilla_id?, contenido_borrador? }`.
- Si trae `plantilla_id`, llama a EP-010 para generar documento base.
- **Permiso:** PERM-PQRSD-009.
- **Eventos:** `RespuestaProyectada`.

### GD-API-0047 — Workflow revisión → aprobación → firma → radicación → envío
- `POST /api/v1/gd/respuestas/{id}/enviar-a-revision` (PERM-PQRSD-012).
- `POST /api/v1/gd/respuestas/{id}/revisar` (PERM-PQRSD-013) body `{ resultado: "ok"|"devolver", observaciones? }`.
- `POST /api/v1/gd/respuestas/{id}/aprobar` (PERM-PQRSD-015).
- `POST /api/v1/gd/respuestas/{id}/firmar` — delega en EP-011.
- `POST /api/v1/gd/respuestas/{id}/radicar-salida` (PERM-PQRSD-017) crea radicado de salida via EP-004.
- `POST /api/v1/gd/respuestas/{id}/enviar` (PERM-PQRSD-018).
- **RNF:** RNF-008 (separación funciones: quien proyecta ≠ quien aprueba ≠ quien firma cuando el flujo lo exija — validado por backend).
- **Eventos:** `RespuestaEnviadaARevision`, `RespuestaDevuelta`, `RespuestaAprobada`, `RespuestaFirmada`.

### GD-API-0048 — Cierre y reapertura de PQRSD
- `POST /api/v1/gd/pqrsd/{id}/cerrar` (PERM-PQRSD-019) requiere respuesta enviada o causal de cierre.
- `POST /api/v1/gd/pqrsd/{id}/reabrir` (PERM-PQRSD-020) requiere justificación.
- **Eventos:** `PQRSDCerrada`, `PQRSDReabierta`.

### GD-API-0049 — Traslado por competencia
- `POST /api/v1/gd/pqrsd/{id}/trasladar-competencia` (PERM-PQRSD-021). Genera oficio de traslado via plantilla.

### GD-API-0050 — Solicitud de información adicional
- `POST /api/v1/gd/pqrsd/{id}/solicitar-info-adicional` (PERM-PQRSD-022). Pausa el término (registrando suspensión vía GD-API-0042) y notifica al solicitante.

### GD-API-0051 — Dashboard agregado de PQRSD
- `GET /api/v1/gd/pqrsd/dashboard?dependencia_id=&desde=&hasta=` retorna conteos por estado, vencidas, próximas, por tipo, tiempo promedio.

---

## EP-008 — Correspondencia interna y externa

**Módulos:** MOD-008
**Entidades:** `correspondencia`, `destinatario_correspondencia`
**Roles:** ROL-012 (correspondencia interna), ROL-013 (radicación externa desde dependencia).
**RNF:** RNF-056 (trazabilidad interna), RNF-057 (radicación externa desde dependencia).

### GD-API-0052 — Correspondencia interna (creación, envío, lectura)
- `POST /api/v1/gd/correspondencia/interna` (PERM-CI-001/002), valida regla de comunicación entre dependencias (GD-API-0016).
- `POST /api/v1/gd/correspondencia/{id}/marcar-leida` (PERM-CI-003).
- `POST /api/v1/gd/correspondencia/{id}/responder` (PERM-CI-004).
- `POST /api/v1/gd/correspondencia/{id}/reenviar` (PERM-CI-005).
- **Eventos:** `CorrespondenciaInternaCreada`, `CorrespondenciaInternaEnviada`, `CorrespondenciaInternaLeida`.

### GD-API-0053 — Correspondencia externa recibida (derivación desde Ventanilla)
- Auto-creada al clasificar un radicado como `correspondencia_externa` (handler de `RadicadoClasificado`).
- `GET /api/v1/gd/correspondencia/externa/recibida?dependencia=&estado=` (PERM-CE-001).
- `POST /api/v1/gd/correspondencia/{id}/gestionar` (PERM-CE-002).

### GD-API-0054 — Correspondencia externa enviada (workflow completo)
- `POST /api/v1/gd/correspondencia/externa/borrador` (PERM-CE-003) crea borrador desde dependencia.
- Workflow revisar → aprobar → firmar → solicitar radicación / radicar directa → enviar (PERM-CE-005..010).
- `POST /api/v1/gd/correspondencia/{id}/registrar-soporte-envio` (PERM-CE-011).
- **Eventos:** `CorrespondenciaExternaPreparada`, `CorrespondenciaExternaAprobada`, `CorrespondenciaExternaRadicadaSalida`, `CorrespondenciaExternaEnviada`.

### GD-API-0055 — Múltiples destinatarios por comunicación
- `gd.destinatario_correspondencia` con `tipo_destinatario`, `tipo_copia` (principal|copia|copia_oculta).

### GD-API-0056 — Anulación de correspondencia interna/externa
- `POST /api/v1/gd/correspondencia/{id}/anular` (PERM-CI-010 / PERM-CE-013) con flujo de aprobación equivalente a anulación de radicado.

---

## EP-009 — Documentos, anexos y versiones

**Módulos:** MOD-010
**Entidades:** `documento`, `version_documento`, `archivo_digital`, `anexo`
**RNF:** RNF-013 (versionamiento), RNF-038 (conservación documental), RNF-045 (gestión anexos), RNF-046 (archivos maliciosos), RNF-018 (cifrado).

### GD-API-0057 — `gd.documento` referencia al servicio transversal de archivos
- **No implementa storage propio.** Apunta a `core.archivo_digital` introducido por **EP-018 / GD-API-0110**. Cuando el caller crea un documento institucional, ya recibió un `archivo_digital_id` desde el endpoint compartido `POST /api/v1/core/archivos`.
- Crea la tabla `gd.documento` con FK `archivo_digital_id → core.archivo_digital(id)` y los campos institucionales propios (estado, clasificación, snapshots, asociaciones polimórficas a radicado/PQRSD/correspondencia/expediente). Esos campos viven en el dominio GD; el binario nunca.
- **Por qué no duplica:** el módulo Knowledge ya tiene el storage operativo en `knowledge_storage.py` con soporte filesystem + S3 por tenant; EP-018 lo eleva a servicio compartido. Forzar a Gestión Documental a tener su propio storage acoplaría dos cosas que la operación quiere unificadas (un solo backup, un solo antivirus, una sola política de retención de bytes).
- **RNF:** RNF-004, RNF-018, RNF-038.

### GD-API-0058 — Reglas adicionales de archivo para documentos institucionales
- El servicio compartido (GD-API-0110) acepta cualquier archivo bajo política global. Esta tarea añade **reglas suplementarias** que solo aplican cuando el archivo se usa como `gd.documento` o `gd.anexo` de un radicado / PQRSD / correspondencia: tamaño máx más estricto que el global, lista blanca MIME reducida (PDF, DOCX, XLSX, imágenes), hash inmutable una vez asociado a una versión aprobada.
- Las reglas se configuran en `gd.configuracion_institucional` (parámetros `gd.archivo.tamano_max`, `gd.archivo.mime_whitelist`); el servicio compartido las consulta cuando recibe `proposito=gd.documento` en el upload.
- **RNF:** RNF-045, RNF-046.
- **Aceptación:** subir un `.exe` para Knowledge funciona si la política global lo permite; subir el mismo `.exe` con `proposito=gd.documento` falla con 415.

### GD-API-0059 — Modelo de Documento con versiones
- DDL `gd.documento`, `gd.version_documento`. Una versión apunta a un `archivo_digital`. Versión aprobada/firmada no se sobrescribe — se crea nueva versión.
- Endpoints `POST /api/v1/gd/documentos`, `POST /api/v1/gd/documentos/{id}/versiones`, `GET /api/v1/gd/documentos/{id}`, `GET /api/v1/gd/documentos/{id}/versiones`.
- **RNF:** RNF-013.

### GD-API-0060 — Anexos polimórficos
- `gd.anexo` con `entidad_relacionada_tipo` y `entidad_relacionada_id`; endpoint `POST /api/v1/gd/anexos` para asociar archivos ya cargados.

### GD-API-0061 — Descarga controlada con auditoría
- `GET /api/v1/gd/archivos/{id}/descargar` valida permiso, registra evento `DocumentoDescargado` con clasificación de la información. Si es reservada/confidencial → criticidad `alta` (RNF-059).

### GD-API-0062 — Anulación y reemplazo de documentos
- `POST /api/v1/gd/documentos/{id}/anular` con justificación.
- `POST /api/v1/gd/documentos/{id}/reemplazar` crea nueva versión y marca la anterior como `reemplazada`.

### GD-API-0063 — Clasificación de información sensible por documento
- Campo `clasificacion_informacion ∈ {pública, interna, reservada, confidencial, datos_personales, sensible}`.
- Backend filtra resultados según permisos del consultante.
- **RNF:** RNF-053, RNF-017.

---

## EP-010 — Plantillas documentales

**Módulos:** MOD-011
**Entidades:** `plantilla_documental`, `version_plantilla`, `documento_generado`
**RNF:** RNF-014, RNF-015 (control borradores).
**Plantillas seed mínimas:** Oficio de respuesta, Memorando interno, Constancia de radicación, Traslado por competencia, Solicitud de información adicional, Respuesta a PQRSD, Comunicación externa de salida.

### GD-API-0064 — CRUD de plantillas + versionamiento
- Endpoints `POST/GET/PATCH /api/v1/gd/plantillas`, `POST /api/v1/gd/plantillas/{id}/versiones`, `POST /api/v1/gd/plantillas/{id}/activar`, `POST /api/v1/gd/plantillas/{id}/inactivar`.
- Cada versión guarda el contenido del template (formato DOCX/PDF base + campos dinámicos definidos como JSON Schema).

### GD-API-0065 — Generación de documento desde plantilla
- `POST /api/v1/gd/plantillas/{id}/generar-documento` body `{ radicado_id?, pqrsd_id?, datos_adicionales? }`. Resuelve datos institucionales + datos del trámite + datos del usuario + plantilla y devuelve un `documento_id` con primera versión en estado `borrador`.
- **RNF:** RNF-014. Datos autocompletados: logo, NIT, dirección, ciudad/fecha, radicado relacionado, destinatario, asunto, dependencia, funcionario que proyecta, firmante autorizado, cargo, anexos, código TRD.
- **Aceptación:** generar respuesta de PQRSD trae automáticamente datos del solicitante, del radicado de entrada y del funcionario responsable.

### GD-API-0066 — Asociación plantilla ↔ dependencia y tipo de trámite
- `POST /api/v1/gd/plantillas/{id}/asociar-dependencia/{dep_id}` (PERM-PLA-006), `POST /api/v1/gd/plantillas/{id}/asociar-tipo-tramite/{tipo}` (PERM-PLA-007).

### GD-API-0067 — Seed de plantillas institucionales
- Cargar las 7 plantillas mínimas con sus campos dinámicos. Usar formato compatible con LibreOffice/MS Word para que el cliente pueda editarlas externamente.

---

## EP-011 — Firmas (escaneada, electrónica, preparación digital)

**Módulos:** MOD-012
**Entidades:** `firma_documento`
**RNF:** RNF-016.

### GD-API-0068 — Firma escaneada con autorización
- Almacenar imagen de firma asociada al usuario (vault propio del usuario). Endpoint `POST /api/v1/gd/firmas/escaneadas` (PERM-FIR-003).
- Solo se usa cuando la entidad lo autorice por política.

### GD-API-0069 — Firma electrónica interna
- `POST /api/v1/gd/documentos/{id}/firmar-electronica` (PERM-FIR-001).
- Captura: autenticación reciente (no re-login si la sesión es < 5 min, sino step-up), fecha, hora, IP, rol, dependencia y cargo del firmante (snapshot), hash del archivo firmado.
- Bloqueos: documento debe estar en estado `aprobado`; firmante debe estar `activo`; firma sobre versión final, no sobre borrador.
- **Eventos:** `DocumentoFirmado`.

### GD-API-0070 — Preparación de integración con firma digital certificada
- Interface `IFirmaDigitalProvider` con implementación stub. Define operación `firmar(documento, certificado, pin)` y validación criptográfica.
- **RNF:** RNF-016 (preparación futura).

### GD-API-0071 — Revocación / rechazo de firma con observación
- `POST /api/v1/gd/firmas/{id}/rechazar` body `{ observacion }` (PERM-FIR-004) — sólo posible si la firma no se ha consumado (estado `pendiente`).

### GD-API-0072 — Consulta de evidencia de firma
- `GET /api/v1/gd/firmas/{id}/evidencia` devuelve metadatos + hash + snapshot del firmante; permitido a auditor (PERM-FIR-005, PERM-AUD-002).

---

## EP-012 — Integración con correo institucional

**Módulos:** MOD-018
**Entidades:** `buzon_correo_institucional`, `correo_importado`
**RNF:** RNF-028.

### GD-API-0073 — Configuración segura de buzones institucionales
- DDL `gd.buzon_correo_institucional`. Credenciales y configuración (IMAP/Graph/Gmail API) guardadas cifradas (referencia a secret vault — no en columna texto).
- Endpoints `POST/GET/PATCH /api/v1/gd/correo/buzones` (PERM-COR-001).

### GD-API-0074 — Worker de lectura periódica de correos
- Worker que recorre buzones activos, descarga correos no procesados (filtro por `message_id` único en `correo_importado` para evitar duplicados — RNF-028).
- Importa: remitente, destinatarios, asunto, cuerpo (texto plano + HTML), anexos como `archivo_digital`.

### GD-API-0075 — Conversión correo → radicado (validación humana)
- `POST /api/v1/gd/correo/{id}/convertir-a-radicado` (PERM-COR-003) — usuario valida y crea radicado de entrada con remitente sugerido (creando tercero si no existe).
- `POST /api/v1/gd/correo/{id}/asociar-radicado/{rad_id}` (PERM-COR-004).
- `POST /api/v1/gd/correo/{id}/descartar` con motivo.
- **Regla absoluta (RNF-028):** un correo nunca se convierte en radicado automáticamente, salvo reglas expresas habilitadas por parámetro institucional.

### GD-API-0076 — Acuse de recibido automático configurable
- Plantilla de acuse + decisión por buzón si se envía o no. Solo se envía cuando el radicado se crea exitosamente.

---

## EP-013 — Agentes IA asistidos

**Módulos:** MOD-019
**Entidades:** `solicitud_ia`, `resultado_ia`
**RNF:** RNF-029 (uso responsable), RNF-030 (trazabilidad IA).
**Mandato:** la IA solo sugiere. Toda materialización requiere endpoint humano separado.

### GD-API-0077 — Plataforma IA: cliente desacoplado + cola de procesamiento
- Interface `IIAProvider` con métodos `clasificar`, `extraer_datos`, `resumir`, `sugerir_dependencia`, `sugerir_borrador_respuesta`, `detectar_duplicados`, `sugerir_termino`.
- Implementación con Claude (default) y stub local. Endpoints encolan trabajo y devuelven `solicitud_ia_id`.
- **RNF:** RNF-029, RNF-030.

### GD-API-0078 — Sugerir clasificación de un radicado
- `POST /api/v1/gd/ia/clasificar` body `{ radicado_id }` → crea `solicitud_ia(tipo_asistencia='clasificacion')` y dispara worker que llama al proveedor IA.
- Resultado en `resultado_ia` con `confianza` y `explicacion`.
- **Eventos:** `IASolicitada`, `IASugerenciaGenerada`.

### GD-API-0079 — Extracción de datos desde correo o documento
- `POST /api/v1/gd/ia/extraer` body `{ entidad_origen_tipo, entidad_origen_id }` → extrae tercero, asunto, fechas relevantes, anexos referenciados.

### GD-API-0080 — Resumen de caso
- `POST /api/v1/gd/ia/resumir` retorna resumen ejecutivo de la PQRSD o radicado para mostrar en la ficha.

### GD-API-0081 — Sugerencia de dependencia responsable
- Basado en historial de clasificaciones humanas + descripción del caso.

### GD-API-0082 — Detección de duplicados
- Embeddings + búsqueda por similitud sobre `radicado`/`pqrsd` reciente; devuelve top-5 candidatos.

### GD-API-0083 — Borrador inicial de respuesta
- `POST /api/v1/gd/ia/borrador-respuesta` body `{ pqrsd_id }` retorna texto sugerido; el funcionario decide aceptar/modificar/rechazar.

### GD-API-0084 — Aceptación / modificación / rechazo de sugerencias
- `POST /api/v1/gd/ia/sugerencias/{id}/decidir` body `{ decision: "aceptar"|"modificar"|"rechazar", contenido_modificado? }`.
- Solo el usuario solicitante o un rol superior puede decidir. La aceptación dispara el endpoint humano correspondiente (clasificar radicado, asignar dependencia, crear respuesta).
- **Eventos:** `IASugerenciaAceptada`, `IASugerenciaModificada`, `IASugerenciaRechazada`.

### GD-API-0085 — Trazabilidad de IA (RNF-030)
- `GET /api/v1/gd/ia/trazabilidad?entidad_tipo=&entidad_id=` muestra todas las sugerencias, decisiones humanas y tiempos. Auditable.

### GD-API-0086 — Política de minimización de datos sensibles enviados al proveedor
- Función `redactar_datos_sensibles(texto)` que enmascara números de identificación, correos personales, teléfonos antes de enviar al proveedor externo.
- **RNF:** RNF-029, RNF-017.

---

## EP-014 — Reportes e indicadores

**Módulos:** MOD-017
**Entidades:** `reporte_generado`
**RNF:** RNF-040, RNF-054.

### GD-API-0087 — Reporte de radicados por fecha/canal/dependencia
- `GET /api/v1/gd/reportes/radicados?...` retorna agregados; `POST /api/v1/gd/reportes/radicados/exportar?formato=pdf|excel|csv` retorna URL al archivo generado (PERM-REP-004).

### GD-API-0088 — Reporte de PQRSD (por tipo, dependencia, vencidas, próximas, tiempo promedio)
- Endpoints similares a 0087, scoped al dominio PQRSD. PERM-REP-006.

### GD-API-0089 — Reporte de correspondencia interna y externa
- PERM-REP-007.

### GD-API-0090 — Reporte de cargas de trabajo por usuario y por dependencia
- PERM-REP-009.

### GD-API-0091 — Reporte de uso de IA (aceptada / modificada / rechazada)
- Para evaluar adopción y precisión.

### GD-API-0092 — Reporte de anulaciones y reasignaciones
- Para control interno.

### GD-API-0093 — Reporte de auditoría (consultas a información sensible)
- PERM-REP-008 + PERM-AUD-007. Especialmente útil al rol Auditor.

### GD-API-0094 — Exportación con auditoría de cada export
- Cada export crea registro en `reporte_generado` (con filtros aplicados, formato, contiene_datos_sensibles) y emite evento auditado.
- **RNF:** RNF-054.

---

## EP-015 — TRD, TVD, series, subseries y clasificación documental

**Módulos:** MOD-013
**Entidades:** `trd`, `version_trd`, `tvd`, `version_tvd`, `serie_documental`, `subserie_documental`, `tipo_documental`, `clasificacion_documental`
**RNF:** RNF-024 (preparación TRD/TVD), RNF-025 (versionamiento TRD/TVD), RNF-038 (conservación), RNF-060 (expediente electrónico).
**Roles:** ROL-003 Admin Documental.

### GD-API-0095 — DDL completo de TRD, TVD, series, subseries, tipos documentales
- Tablas y endpoints CRUD + versionado (PERM-TRD-001..PERM-TRD-013).

### GD-API-0096 — Activación / cierre de vigencia de versiones TRD/TVD
- Una versión "vigente" se vuelve "histórica" al activar la siguiente; documentos clasificados con la versión anterior la conservan.

### GD-API-0097 — Asociación dependencia ↔ código documental
- Permite que al clasificar un documento se sugieran series/subseries pertinentes a la dependencia.

### GD-API-0098 — Clasificación de radicados y documentos por serie/subserie
- `POST /api/v1/gd/clasificacion-documental` body `{ entidad_tipo, entidad_id, version_trd_id, serie_id, subserie_id, tipo_documental_id, justificacion? }` (PERM-TRD-011).

### GD-API-0099 — Consulta de clasificación histórica
- `GET /api/v1/gd/clasificacion-documental?entidad=&fecha=` devuelve la versión TRD/TVD vigente al momento.

### GD-API-0100 — Auditoría de cambios TRD/TVD (RNF-025)
- Especializa eventos `TRDVersionada`, `TVDVersionada` en `evento_auditoria`.

---

## EP-016 — Expediente electrónico básico

**Módulos:** MOD-014
**Entidades:** `expediente`, `expediente_documento`, `expediente_radicado`
**RNF:** RNF-060.
**Alcance v1:** preparación. Funciones avanzadas (índice electrónico, hoja de control, transferencias) quedan para fase 2.

### GD-API-0101 — CRUD básico de expedientes
- Endpoints `POST/GET/PATCH /api/v1/gd/expedientes`, `POST /api/v1/gd/expedientes/{id}/cerrar`.
- Asociación a dependencia, serie, subserie, fecha apertura, fecha cierre.

### GD-API-0102 — Asociar/retirar radicados y documentos del expediente
- `POST /api/v1/gd/expedientes/{id}/documentos` body `{ documento_id, orden }`.
- `POST /api/v1/gd/expedientes/{id}/radicados` body `{ radicado_id }`.
- `POST /api/v1/gd/expedientes/{id}/documentos/{documento_id}/retirar` con justificación (no borra el documento, sólo el vínculo `estado='retirado'`).

### GD-API-0103 — Consulta agregada del expediente
- `GET /api/v1/gd/expedientes/{id}/contenido` devuelve documentos + radicados + actuaciones ordenadas.

### GD-API-0104 — Metadatos básicos del expediente
- `expediente.metadata` JSONB con campos definidos en plantilla (por serie). Útil para futuras transferencias.

---

## EP-017 — Preparación para RPA y APIs públicas (futuro)

**Módulos:** MOD-020
**RNF:** RNF-031 (RPA), RNF-027 (interoperabilidad).

### GD-API-0105 — Identidad técnica para RPA y bots IA
- Usuario tipo `agente_ia` y `robot_rpa` (RNF-029, RNF-031). Credenciales propias, no comparten cuenta humana.
- Endpoints `POST /api/v1/gd/identidades-tecnicas` (PERM-USR-001 restringido al Admin Sistema).

### GD-API-0106 — Bandejas de trabajo para RPA
- Tabla `gd.tarea_rpa` con tipo y payload. Robot consulta `GET /api/v1/gd/rpa/tareas-pendientes` y reporta resultado en `POST /api/v1/gd/rpa/tareas/{id}/resultado`.

### GD-API-0107 — Documentación OpenAPI completa y versionada
- `/api/v1/gd/openapi.json` con cobertura 100% de los endpoints; versionado `v1`.
- **RNF:** RNF-027, RNF-051.

### GD-API-0108 — Webhooks salientes para integradores
- Tabla `gd.webhook_subscripcion` (eventos suscritos, URL, secret). Worker que entrega eventos con retry exponencial.

### GD-API-0109 — Rate limiting por consumidor de API
- Middleware con cuotas por identidad técnica. Devuelve `429` con `Retry-After`.

---

## EP-018 — Servicio transversal de archivos, extracción y OCR

**Naturaleza:** este EP **no vive bajo `gd`**. Crea un servicio en `core.*` compartido entre el módulo Knowledge (RAG conversacional) existente y el módulo Gestión Documental nuevo.

**Por qué transversal:** el dominio Knowledge ya tiene un repositorio operativo (`app/services/knowledge_storage.py` con filesystem + S3 por tenant), un worker de extracción para PDF/DOCX (`app/services/extraction_worker.py`) y tablas `app.knowledge_documents`/`knowledge_chunks`. Construir un storage paralelo para Gestión Documental duplicaría backup, antivirus, política MIME, validaciones y código de extracción. Construir un único modelo `documento` para los dos dominios mezcla concerns incompatibles (chunks de RAG re-indexables vs. versiones SGDEA inmutables con firma). La solución es: **una sola capa baja de bytes + extracción de texto**, **dos modelos de dominio encima** (Knowledge sigue siendo Knowledge, Gestión Documental tiene su propio `gd.documento`).

**Módulos del Mapa:** infraestructura transversal (no es un MOD-NNN).
**RNF objetivo:** RNF-004 (escalabilidad — almacén documental separado del transaccional), RNF-018 (cifrado en reposo y tránsito), RNF-038 (conservación documental), RNF-039 (búsqueda y recuperación), RNF-044 (calidad de datos), RNF-045 (anexos), RNF-046 (archivos maliciosos).
**Dependencias del producto principal:** refactor de `app/services/knowledge_storage.py` y `app/services/extraction_worker.py` para que vivan bajo `app/core/files/` y `app/core/extraction/`, con compatibilidad para Knowledge.

### GD-API-0110 — Servicio transversal `core.archivo_digital` + storage compartido
- **Mueve** `app/services/knowledge_storage.py` → `app/core/files/storage.py`. Conserva la API actual (`save_file`, `get_file`, `delete_file`) y agrega `attach_proposito(archivo_id, proposito, contexto_id)` para que el caller declare si el archivo es `knowledge`, `gd.documento`, `gd.anexo`, `gd.constancia`, `gd.firma_imagen`, etc.
- **Tabla nueva** `core.archivo_digital` con columnas: `id`, `tenant_id`, `nombre_original`, `extension`, `mime_type`, `tamano`, `ruta_almacenamiento`, `hash_sha256`, `estado` (cargado / extrayendo / listo / bloqueado / anulado), `analisis_antivirus` (`pendiente|limpio|infectado`), `cargado_por_usuario_id`, `cargado_en`. El binario sigue viviendo en filesystem o S3 según config tenant — esta tabla solo es metadatos + referencia.
- **Migración de Knowledge:** `app.knowledge_documents.storage_path` se reemplaza por FK `archivo_digital_id → core.archivo_digital(id)`. Backfill: crear una fila en `core.archivo_digital` por cada `knowledge_documents` existente. RNF-010 prohíbe DELETE; los documentos Knowledge migrados conservan su id.
- **Endpoint compartido:** `POST /api/v1/core/archivos` (multipart) que recibe `proposito` + reglas adicionales del dominio caller. Devuelve `archivo_digital_id` que luego se pasa a `POST /api/v1/gd/documentos` o al endpoint de Knowledge según corresponda.
- **Antivirus:** interfaz `IAntivirusScanner` con stub para dev + implementación ClamAV para prod (RNF-046). Tras `save_file`, el archivo entra a cola asincrónica de análisis; mientras está `pendiente` no se puede usar para crear documento institucional (gate de GD-API-0057).
- **Aceptación:**
  1. Knowledge sigue subiendo PDFs igual que hoy; los nuevos archivos viven en `core.archivo_digital` sin que los usuarios noten cambio.
  2. Gestión Documental sube un PDF llamando al endpoint compartido, recibe `archivo_digital_id`, lo asocia a un radicado vía `POST /api/v1/gd/anexos`.
  3. Subir un archivo con virus EICAR queda en `analisis_antivirus='infectado'` y `estado='bloqueado'`; intentar crear `gd.documento` con ese id falla con 422.
  4. Backup del repositorio cubre con un solo job ambos dominios.

### GD-API-0111 — OCR para imágenes y PDFs escaneados
- **Por qué:** `pypdf` solo lee texto embebido. Un oficio escaneado que llega a Ventanilla Única hoy entra como PDF "vacío" — sin búsqueda léxica, sin extracción IA, sin asistente de clasificación, sin previews legibles. Igualmente bloqueante: cédulas, fotos de contratos, facturas en JPG/PNG que ciudadanos suben por correo o widget.
- **Worker** `app/core/extraction/ocr_worker.py` que escucha un job `OCRRequested(archivo_digital_id)` emitido cuando:
  - El MIME es `image/*` (JPG, PNG, TIFF).
  - El MIME es `application/pdf` y el extractor PDF base devuelve `< 50` caracteres por página (heurística: PDF probablemente escaneado).
- **Motor:** [Tesseract](https://tesseract-ocr.github.io/) v5 con paquetes `spa` + `eng` como default local; interfaz `IOCRProvider` permite cambiar a AWS Textract o Google Vision por configuración (parámetro `core.ocr.provider`). Tesseract es libre y suficiente para documentos institucionales típicos; los servicios cloud quedan disponibles para casos con tablas complejas o calidad baja.
- **Salida:** texto extraído + bbox por palabra + confianza promedio, guardados en `core.extraccion_resultado(archivo_digital_id, motor, version, texto_completo, paginas_jsonb, confianza, extraido_en)`. Esta tabla la consumen tanto Knowledge (para chunking RAG) como Gestión Documental (para búsqueda léxica y resumen IA).
- **Pre-procesamiento:** deskew, denoise y conversión a grayscale antes de Tesseract (mejora 10–20% precisión en escaneos sucios).
- **Política de costos:** OCR se ejecuta una sola vez por archivo (idempotente por `hash_sha256`); resultado se cachea. Re-ejecución manual disponible vía `POST /api/v1/core/archivos/{id}/reextraer` (PERM-DOC-001).
- **Eventos:** `OCRRequested`, `OCRCompleted`, `OCRFailed`. Auditados.
- **Aceptación:**
  1. Subir foto JPG de un oficio dispara OCR, queda texto extraído consultable.
  2. Subir PDF nativo con texto embebido NO ejecuta OCR (la heurística lo evita).
  3. Subir PDF escaneado SÍ ejecuta OCR y el texto queda disponible.
  4. Texto extraído de un radicado escaneado alimenta la sugerencia IA de clasificación (GD-API-0078) — antes era imposible.
  5. Métrica de confianza < 60% emite warning visible para el radicador, que decide si confiar o re-digitalizar.

### GD-API-0112 — Extracción nativa de XLSX, XLSM y CSV mejorada
- **Por qué:** el extractor actual reconoce CSV por heurística y devuelve texto concatenado. XLSX binario no se soporta — un anexo Excel típico (matrices PQRSD, listados de citados, formatos de seguimiento) llega como blob ininteligible para búsqueda y IA.
- **Librerías:** `openpyxl` para `.xlsx`/`.xlsm` (lectura, sin macros), `pandas` opcional para tablas grandes. Stub para `.xls` legacy (informa al usuario que convierta a `.xlsx`).
- **Estrategia de extracción:**
  - Cada hoja produce un bloque con `nombre_hoja`, `rango`, `headers` (primera fila con encabezados), `rows` (lista de diccionarios).
  - Texto plano agregado para búsqueda léxica: `"Hoja: X\n<headers>\n<rows tabuladas>"`.
  - Metadatos JSON estructurado en `core.extraccion_resultado.paginas_jsonb` para que IA pueda razonar sobre la estructura tabular (ej. "¿cuántas filas tiene la columna 'fecha_vencimiento' antes del 2026-06-01?").
- **Límites:** archivos > 50 MB o > 100k filas se truncan con warning audit visible. Fórmulas no se evalúan — se extrae el valor calculado guardado por Excel; si la celda no tiene valor calculado (archivo nuevo sin abrir), se reporta `null`.
- **Aceptación:**
  1. Anexar un XLSX con 3 hojas a una PQRSD; el sistema indexa las 3 hojas + permite buscar por valor de celda.
  2. La IA de resumen (GD-API-0080) recibe la estructura tabular y la describe correctamente.
  3. Un XLSX con macro `.xlsm` se extrae sin ejecutar macros (seguridad).

### GD-API-0113 — Detección de duplicados por hash de archivo (consumida por GD-API-0082)
- Aprovecha `core.archivo_digital.hash_sha256` para detectar archivos idénticos antes de re-extraer.
- Si un PDF llega a Ventanilla con el mismo hash que otro radicado del último año, advertir al radicador con link al radicado anterior — antes incluso de pasar por la IA de duplicados semántica.
- Endpoint `GET /api/v1/core/archivos/duplicados?hash=...`.
- **RNF:** RNF-044.

### GD-API-0114 — Política de retención de bytes vs. retención de metadatos (RNF-038)
- Los metadatos `core.archivo_digital` y `gd.documento` son **append-only** (RNF-010): nunca se borran.
- Los **bytes** sí pueden purgarse cuando la TRD/TVD lo indique y haya pasado el plazo de archivo central + histórico (años, no días). Worker `core.retencion_bytes` programado por jobs.
- Al purgar bytes: el archivo binario se elimina del storage, `core.archivo_digital.ruta_almacenamiento = NULL`, `estado = 'purgado'`, hash y metadatos permanecen para evidencia.
- **Trámites firmados, PQRSD cerradas con respuesta enviada y expedientes en archivo histórico siguen reglas distintas** — la purga consulta `gd.clasificacion_documental.serie.disposicion_final`.
- **Aceptación:** un documento clasificado como "Conservación total" nunca se purga, incluso si se ejecuta el worker; un documento "Eliminación" pasados los plazos de archivo de gestión + central se purga y queda registro en auditoría.

---

## EP-019 — Auditoría transversal `core.evento_auditoria`

**Naturaleza:** servicio en `core.*` compartido entre los tres dominios — el producto principal (CopilotoIA: citas, conversaciones, campañas, exportes GDPR), Knowledge (indexación, descargas) y Gestión Documental (radicados, PQRSD, firmas, IA, anulaciones). **Reemplaza** a `app.audit_logs` y absorbe `app.consent_ledger` como caso especial.

**Por qué transversal:** el sistema actual ya audita 121 acciones via `app.audit_logs` con helper `app/services/audit.py::audit()` y `audit_durably()`. Construir un sistema paralelo en `gd.*` partiría la verdad de auditoría — un auditor tendría que mirar dos tablas para reconstruir un incidente que cruzó dominios (ej. un usuario que cambió de tenant tras anular una PQRSD). Y al revés, el sistema actual tiene tres carencias estructurales (no append-only, no particionado, sin snapshots) que de todas formas obligan a un refactor mayor para cumplir RNF-009 / RNF-010 del documento PQRSD. La solución es **un solo refactor** que unifica.

**Módulos del Mapa:** MOD-016, transversal a todos los demás.
**RNF objetivo:** RNF-009 (auditoría integral), RNF-010 (no eliminación), RNF-030 (trazabilidad IA), RNF-036 (observabilidad), RNF-059 (lectura sensible).

### GD-API-0115 — Tabla `core.evento_auditoria` particionada append-only
- DDL con columnas: `id` (bigserial), `tenant_id` (uuid, FK → `app.tenants`), `dominio ∈ {core, app, gd, knowledge}` (separa fuente), `tipo_evento` (texto controlado), `actor_tipo ∈ {usuario, sistema, bot, agente_ia, robot_rpa, support}`, `actor_id`, `actor_nombre_snapshot`, `rol_codigo_snapshot`, `dependencia_codigo_snapshot`, `cargo_snapshot`, `entidad_afectada_tipo`, `entidad_afectada_id`, `accion`, `valor_anterior` (jsonb), `valor_nuevo` (jsonb), `justificacion`, `request_id` (uuid), `ip` (inet), `user_agent`, `criticidad ∈ {baja, media, alta, critica}`, `idempotency_key`, `creado_en` (timestamptz).
- **Particionado** `BY RANGE (creado_en)` mensual; índices `(tenant_id, creado_en DESC)`, `(entidad_afectada_tipo, entidad_afectada_id)`, `(actor_id, creado_en)`, `(tipo_evento, creado_en)`, `(dominio, tipo_evento)`.
- **Append-only declarativo:** triggers `BEFORE UPDATE` / `BEFORE DELETE` → `RAISE EXCEPTION`. Solo `INSERT` permitido (mismo patrón que `consent_ledger` actual).
- **RLS** habilitada con política `tenant_id = app.current_tenant_id() OR app.support_mode()`.
- **UNIQUE** `(tenant_id, idempotency_key)` para prevenir doble-inserción cuando el caller reintenta.
- **Aceptación:** `UPDATE` y `DELETE` fallan con excepción; `INSERT` con `idempotency_key` repetida falla con `23505`; `EXPLAIN` muestra escaneo por partición correcta para query con rango de fecha.

### GD-API-0116 — Refactor de `app/services/audit.py` para escribir a `core.evento_auditoria`
- La firma actual `audit(conn, *, tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)` se mantiene **backward-compatible** — los 121 call sites no se tocan.
- Por debajo, escribe a `core.evento_auditoria` con `dominio='app'`, `metadata` se reparte entre `valor_anterior` / `valor_nuevo` / `justificacion` cuando los call sites llaman con la nueva firma extendida; en su defecto, queda en `valor_nuevo`.
- Helper nuevo `audit_extended(..., valor_anterior, valor_nuevo, criticidad, justificacion)` para los call sites futuros (incluidos todos los de `gd.*`).
- `audit_durably()` se preserva igual — autocommit propio para fallos rollback-eados.
- **Aceptación:** los tests existentes de auditoría siguen pasando sin modificar; el campo `dominio='app'` aparece en cada fila.

### GD-API-0117 — Migración de `app.audit_logs` y `app.consent_ledger` → `core.evento_auditoria`
- Migración online: la nueva tabla recibe inserts desde el momento del deploy; un job de fondo copia el histórico de `app.audit_logs` (con `dominio='app'`) y de `app.consent_ledger` (con `dominio='app'` + `tipo_evento='consent.*'` + `criticidad='alta'`).
- Las tablas viejas se conservan en read-only (renombradas a `app.audit_logs__deprecated`) durante 90 días para auditoría doble. Luego se borran (las copias quedan en `core.evento_auditoria`).
- Vista de compatibilidad `app.audit_logs` (VIEW sobre `core.evento_auditoria WHERE dominio='app'`) para que consultas legadas no se rompan.
- **Aceptación:** después de la migración, los reportes legales de Ley 1581 (consent_ledger) siguen funcionando contra la vista; total de filas en `core.evento_auditoria` ≥ suma de las dos tablas originales.

### GD-API-0118 — Helper de aplicación + middleware
- Module `app/core/audit/__init__.py` expone:
  - `audit(...)` — sincrónico, dentro de la transacción del handler.
  - `audit_async(...)` — encola para escritura asíncrona (alta volumetría: queries de IA, descargas masivas).
  - `audit_durably(...)` — preserva el comportamiento actual.
- Middleware genera `request_id` por request (UUID v4), accesible vía contextvar.
- Snapshot helpers `capturar_snapshot_actor(user_id, tenant_id)` y `capturar_snapshot_entidad(entidad_tipo, entidad_id)`.
- **Aceptación:** cualquier handler puede llamar `audit_extended(action="gd.radicado.anulado", valor_anterior={...}, valor_nuevo={...}, criticidad="alta", justificacion="...")` y el evento se persiste con todos los campos snapshot.

### GD-API-0119 — Endpoints de consulta de auditoría con permisos
- `GET /api/v1/core/auditoria?dominio=&tipo_evento=&actor_id=&entidad_tipo=&entidad_id=&criticidad=&desde=&hasta=&page=&size=` (cursor paginated).
- `GET /api/v1/core/auditoria/{id}` detalle.
- `GET /api/v1/core/auditoria/export?formato=csv|json` (asincrónico, devuelve job_id; archivo queda en `core.archivo_digital` con TTL 7 días).
- **Permisos:** `PERM-AUD-001..PERM-AUD-008` cuando es módulo gd; rol `tenant-admin` o `owner` cuando es módulo app/knowledge. Compartido con el endpoint existente `/v1/tenant-admin/audit-logs` (que pasa a ser un alias sobre `core.evento_auditoria` con filtro `dominio in (app, knowledge)`).
- **RNF:** RNF-059 — consultar un evento marcado como `criticidad='alta'` o sobre entidad reservada genera un evento meta `auditoria.consultada` con `actor_id` del consultante.

### GD-API-0120 — Catálogo formal de eventos auditados
- Archivo `docs/gestion documental/EVENTOS_AUDITORIA.md` con la tabla completa: `tipo_evento`, `dominio`, `productor` (módulo que lo emite), `criticidad`, `RNF cubierto`, `permiso de lectura`, `campos snapshot`.
- Incluye los 33 eventos del Anexo A del documento PQRSD **+** los 121 actions existentes en `app.audit_logs` clasificados por dominio.
- Sirve como contrato: cualquier acción nueva que requiera auditoría debe primero declarar su `tipo_evento` aquí.

### GD-API-0121 — Logger técnico estructurado separado
- `app/core/logging/__init__.py` configura logger JSON (`structlog` o `python-json-logger`) hacia stdout con campos `ts`, `level`, `request_id`, `tenant_id?`, `user_id?`, `module`, `message`, `error?`.
- **Regla absoluta:** los logs técnicos **nunca** escriben a `core.evento_auditoria`. Si una línea contiene una actuación funcional (cambio de estado, decisión humana, acceso a info sensible) → `audit()`. Si es operación técnica (latencia, error de red, retry) → logger.
- Linter en CI que detecta llamadas a `logger.info` con `action=` o `actor_id=` y obliga a rebautizarlas como `audit()` (RNF-036).

---

## EP-020 — Gaps cerrados tras auditoría de cobertura 2026-05-20

> Tareas añadidas tras la auditoría cruzada documentada en `TRAZABILIDAD.md` § 6. Cada tarea cita la sección exacta del PDF fuente que la motiva. Cobertura tras estas tareas: **100%** de los 5 documentos del cliente.

### GD-API-0122 — Página pública de verificación de constancia con QR (sin login)
- **Doc fuente:** Doc 1 § 6.1 (Ventanilla Única genera constancia) + RNF-011 ("Debe poder verificarse el radicado mediante código de verificación o QR") + Doc 1 § 19.1 (plantilla constancia).
- **Crea:** ruta pública `GET /gd/verificar/{codigo_verificacion}` (sin auth) — escaneable desde el QR impreso en la constancia.
- **Devuelve:** `{ numero_radicado, fecha_radicacion, tipo (PQRSD|correspondencia|...), estado_actual, dependencia_actual_publica, asunto_resumido }`. **NO** expone datos personales del tercero ni el cuerpo del trámite — RNF-017.
- **Activación:** solo si `gd.organizacion_modulo_activacion.modulo_codigo='consulta_publica_radicado'` está activo para el tenant (por default ON para `tipo_organizacion='publica'`, OFF para privada).
- **Rate limit:** 60 req/min por IP para prevenir scraping.
- **Aceptación:** escanear el QR de una constancia y abrir el link en modo incógnito muestra el estado actual del radicado sin pedir login; el mismo link con `tipo_organizacion='privada'` y módulo desactivado retorna 404.

### GD-API-0123 — Catálogo configurable de tipos de documento de identificación por país/organización
- **Doc fuente:** Doc 5 § 9.1 (`Tercero.tipo_documento ∈ {CC, CE, NIT, pasaporte, otro}` — restringido a Colombia) + neutralidad de sector (README sección 0).
- **Por qué:** una empresa con operación regional (México, Argentina, USA) necesita aceptar RFC, DNI, EIN, etc. Si el catálogo es enum hardcoded, hay que recompilar.
- **Crea:**
  - Tabla `gd.catalogo_tipo_documento(codigo PK, nombre, pais_iso, formato_regex?, validador_funcion?, activo)`. Globales (sin RLS).
  - Tabla `gd.organizacion_tipo_documento_activo(tenant_id, codigo_tipo_doc, activado, default bool)` — qué tipos acepta esta organización.
  - Endpoints `GET /api/v1/gd/catalogos/tipos-documento` (catálogo global) y `GET/PATCH /api/v1/gd/organizacion/tipos-documento` (selección de la organización).
- **Seed:** CC, CE, NIT, TI, RC, PA (Colombia); RFC, CURP (México); DNI, CUIT (Argentina); EIN, SSN, ITIN (USA); ID genérico, pasaporte como fallback.
- **Aceptación:** una empresa argentina configura `DNI` y `CUIT` como activos; el formulario de tercero en GD-UI-0007 solo muestra esos dos; si llega un correo con remitente colombiano, la IA sugiere "tipo_documento=CC" pero el sistema marca el caso como `documento_extranjero` para revisión.

### GD-API-0124 — Versionado jerárquico de dependencias (fusiones, divisiones, traslados)
- **Doc fuente:** Doc 5 § 6.1 (`Dependencia.dependencia_padre_id`) + Doc 4 MOD-003 ("Las dependencias podrán cambiar de nombre, fusionarse, dividirse o cerrarse mediante nuevas versiones o relaciones históricas") + RNF-026.
- **Por qué:** GD-API-0012 versionaba la dependencia pero no el **vínculo** padre-hijo. Si la "Oficina Jurídica" se fusiona con la "Oficina de Contratación" en 2025, los radicados de 2024 deben seguir mostrando la jerarquía vigente al momento.
- **Crea:**
  - Tabla `gd.relacion_dependencia_historica(id, dependencia_id, dependencia_padre_id, fecha_inicio_vigencia, fecha_fin_vigencia, motivo_cambio)`.
  - Tipos de cambio: `creacion`, `cambio_nombre`, `cambio_padre`, `fusion_origen`, `fusion_destino`, `division_origen`, `division_destino`, `cierre`.
  - Endpoint `GET /api/v1/gd/estructura/dependencias/{id}/historial` retorna el árbol completo en el que esa dependencia ha estado a lo largo del tiempo.
  - Endpoint `POST /api/v1/gd/estructura/fusionar` body `{ dependencias_origen: [...], dependencia_destino_id, fecha_vigencia, motivo, acto_administrativo? }` — operación transaccional que cierra orígenes y abre destino con trazabilidad.
- **Aceptación:** un radicado creado en 2024-03 en "Oficina Jurídica" sigue mostrando esa dependencia en su trazabilidad después de fusionarse con "Contratación" en 2025-01 a "Oficina Asesora Jurídica y de Contratación". La consulta histórica reconstruye la jerarquía vigente al 2024-03.

### GD-API-0125 — Radicación de contingencia para caída del sistema
- **Doc fuente:** RNF-002 ("Deben existir procedimientos de contingencia para radicación manual en caso de caída del sistema") + Doc 1 § 25 supuesto 10.
- **Por qué:** una entidad pública que opera bajo Ley 1755 no puede dejar de radicar PQRSD durante una caída — los términos legales corren igualmente. Cuando el sistema vuelve, los radicados manuales que se hicieron en papel durante la caída deben ingresarse con su timestamp original.
- **Crea:**
  - Endpoint `POST /api/v1/gd/ventanilla/radicados/contingencia` con permiso especial PERM-VU-021 (nuevo, solo coordinador VU + admin sistema).
  - Body: `{ numero_radicado_manual, fecha_radicacion_real (timestamp del momento de caída), justificacion (obligatorio), evidencia_contingencia_archivo_digital_id (foto/escaneo de la planilla manual), ...resto de campos normales }`.
  - El radicado se crea con flag `es_radicacion_contingencia=true`, fecha real preservada, fecha de ingreso al sistema en `creado_en` separada.
  - **Evento crítico** `gd.radicado.contingencia` en `core.evento_auditoria` con `criticidad='alta'`.
  - Reporte específico de radicados de contingencia para control interno (PERM-REP-002).
- **Aceptación:** durante una caída de 3 horas, el coordinador registra 12 radicados manuales en papel; al restablecer servicio, los carga vía contingencia con foto de la planilla; los términos PQRSD se calculan desde la fecha real (no la fecha de carga); el auditor puede listar todos los radicados de contingencia del período.

### GD-API-0126 — Preparación de hoja de control e índice electrónico del expediente
- **Doc fuente:** Doc 5 § 17 + RNF-060 ("La estructura deberá permitir hoja de control o índice electrónico en versiones futuras").
- **Por qué:** el cliente exige que la **estructura quede preparada en v1** aunque la funcionalidad sea fase 2 — para evitar migración compleja después.
- **Crea (DDL preparatorio, sin endpoints expuestos en v1):**
  - Tabla `gd.expediente_indice_electronico(id, expediente_id, version_indice, generado_en, generado_por_user_id, contenido_jsonb)` — vacía en v1, alimentada por job futuro.
  - Tabla `gd.expediente_hoja_control(id, expediente_id, fecha, evento, descripcion, usuario_id, snapshot_jsonb)` — eventos cronológicos del expediente (apertura, incorporación documento, retiro, cierre, transferencia).
  - Trigger sobre `gd.expediente_documento` que inserta automáticamente en `expediente_hoja_control` cuando hay alta/baja.
- **Aceptación:** crear expediente y asociar 3 documentos produce 4 filas en `expediente_hoja_control` (1 apertura + 3 asociaciones); `expediente_indice_electronico` queda preparada para que fase 2 genere el índice firmado conforme a estándares de archivo (Acuerdo 027 AGN Colombia o equivalente).

### GD-API-0127 — Suspensión / reanudación formal de términos PQRSD con eventos auditados
- **Doc fuente:** RNF-023 ("Debe permitir registrar suspensiones, requerimientos o eventos que afecten el término, si la entidad lo define") + Doc 1 § 12.2 paso 13 ("Se conserva trazabilidad").
- **Por qué:** GD-API-0042 mencionaba la suspensión pero sin endpoints formales separados; la entidad necesita ver el historial de eventos que afectaron un término legal.
- **Crea:**
  - Tabla `gd.evento_termino_pqrsd(id, pqrsd_id, tipo_evento ∈ {suspension, reanudacion, ampliacion, solicitud_info_adicional, traslado_competencia}, fecha_evento, motivo, justificacion_legal, dias_afectados, usuario_id)`.
  - Endpoint `POST /api/v1/gd/pqrsd/{id}/suspender-termino` (PERM-PQRSD-023) body `{ motivo, justificacion_legal, fecha_efectiva, dias_estimados_suspension? }`.
  - Endpoint `POST /api/v1/gd/pqrsd/{id}/reanudar-termino` body `{ motivo, fecha_efectiva }`.
  - Endpoint `GET /api/v1/gd/pqrsd/{id}/historial-terminos` retorna lista cronológica de todos los eventos que afectaron el término + recálculo de fecha_limite por cada uno.
- **Eventos:** `gd.pqrsd.termino_suspendido`, `gd.pqrsd.termino_reanudado` con `criticidad='alta'`.
- **Aceptación:** crear PQRSD con término 15 días hábiles, suspender al día 5 por "solicitud info adicional" (justificación legal: art. X), reanudar al día 12; la fecha_limite final refleja el cálculo correcto; el historial muestra ambos eventos con su impacto en días.

---

## EP-021 — Periféricos de Ventanilla Única (impresoras, escáneres, códigos de barras/QR, agente local)

**Módulos:** MOD-004 (Ventanilla), MOD-016 (Auditoría — eventos de hardware).
**Entidades nuevas:** `gd.periferico`, `gd.punto_atencion`, `gd.impresion_radicado`, `gd.digitalizacion_documento`, `gd.codigo_barras_radicado`, `gd.evento_periferico`.
**Doc fuente:** Doc 5 v0.1-rev1 § 28 (Interacción con periféricos) + Doc 6 v0.1 (Componente de Comunicación con Periféricos — completo).
**RNF objetivo:** RNF-002 (continuidad operativa con periférico alterno), RNF-009 (auditoría exhaustiva de uso de hardware), RNF-011 (integridad del radicado impreso ≡ radicado digital), RNF-018 (protección de canal local), RNF-039 (búsqueda de archivos digitalizados), RNF-045/046 (validación de anexos escaneados), RNFP-001..006 (los seis específicos del Doc 6).
**Roles primarios:** ROL-004 (Radicador VU — usa periféricos), ROL-005 (Coordinador VU — configura puntos), ROL-001 (Admin Sistema — registra hardware), ROL-016 (Auditor — consulta historial).
**Permisos nuevos:** `PERM-PER-001..PERM-PER-012` (12 permisos del Doc 6 § 9).
**Eventos nuevos:** `gd.periferico.registrado`, `gd.periferico.estado_cambiado`, `gd.impresion.generada`, `gd.impresion.reimpresion`, `gd.impresion.fallida`, `gd.digitalizacion.completada`, `gd.digitalizacion.fallida`, `gd.digitalizacion.reemplazada`, `gd.agente_local.handshake`, `gd.agente_local.intento_no_autorizado`.

**Mandato de la épica.** La plataforma web no puede acceder de forma confiable a impresoras de etiquetas, escáneres profesionales o lectores de código de barras directamente desde el navegador (Doc 6 § 2). Por eso esta épica define **dos capas**:
1. **Capa servidor (`/api/v1/gd/perifericos/*`)** — registra hardware, autoriza operaciones, audita todo, almacena artefactos generados (etiquetas como PDF, archivos digitalizados).
2. **Capa de "agente local"** — proceso instalado en el equipo de Ventanilla Única que recibe instrucciones firmadas del servidor y las traduce a comandos del periférico físico. La autenticación entre servidor y agente local vive en GD-API-0139. El binario del agente es responsabilidad de un proyecto/repositorio aparte; este backlog solo define el contrato.

> **Importante para neutralidad de sector.** Esta épica solo se activa cuando la organización marca `gd.organizacion_modulo_activacion.modulo_codigo='ventanilla_presencial_con_perifericos'`. Una empresa privada que opera solo por correo y web puede tener el módulo Ventanilla Única activo pero esta sub-funcionalidad desactivada — no la verá en menús ni endpoints (404).

### GD-API-0128 — DDL completo de entidades de periféricos
- **Estado:** PENDING
- **Por qué:** sin las tablas no se puede registrar hardware, asociar impresiones a radicados ni auditar uso. La operación presencial es de muy alta trazabilidad (cada etiqueta impresa equivale a un acto oficial).
- **Crea (schema `gd`):**
  - `gd.punto_atencion(id UUID PK, tenant_id FK, nombre, direccion, dependencia_responsable_id FK→gd.dependencia, estado ∈ {activo, inactivo}, creado_en, creado_por_user_id)`.
  - `gd.periferico(id UUID PK, tenant_id FK, tipo_periferico ∈ {impresora_etiquetas, impresora_termica, impresora_convencional, escaner_plano, escaner_automatico, lector_codigo_barras, otro}, nombre, marca, modelo, serial, dependencia_id FK?, punto_atencion_id FK?, estado ∈ {activo, inactivo, mantenimiento, retirado}, configuracion jsonb, fecha_registro, registrado_por_user_id FK)`.
  - `gd.impresion_radicado(id UUID PK, tenant_id FK, radicado_id FK→gd.radicado, documento_id FK?, periferico_id FK→gd.periferico, usuario_id FK, tipo_impresion ∈ {etiqueta_codigo_barras, etiqueta_qr, constancia_radicacion, sello_documento, sticker, comprobante}, contenido_impreso jsonb (snapshot de qué se imprimió — no el bitmap, los datos), archivo_digital_id FK→core.archivo_digital? (PDF/PNG de la etiqueta o constancia), fecha_impresion, estado ∈ {generada, fallida, anulada, reemplazada}, motivo_reimpresion text?, intentos_reimpresion smallint default 0)`.
  - `gd.digitalizacion_documento(id UUID PK, tenant_id FK, radicado_id FK, documento_id FK?, archivo_digital_id FK→core.archivo_digital, periferico_id FK→gd.periferico, usuario_id FK, tipo_digitalizacion ∈ {plano, automatico, lote, individual}, numero_paginas int, calidad_dpi int?, fecha_digitalizacion, estado ∈ {correcta, fallida, incompleta, reemplazada}, observacion text?, lote_id UUID?)`.
  - `gd.codigo_barras_radicado(id UUID PK, tenant_id FK, tipo_codigo ∈ {codigo_barras, qr, otro}, radicado_id FK?, documento_id FK?, expediente_id FK?, valor_codigo text (URL de verificación + token, nunca datos sensibles), fecha_generacion, generado_por_user_id FK, estado ∈ {activo, anulado, reemplazado})`.
  - `gd.evento_periferico(id UUID PK, tenant_id FK, periferico_id FK, usuario_id FK?, tipo_evento ∈ {comando_enviado, comando_exitoso, comando_fallido, conexion_perdida, conexion_recuperada, mantenimiento_iniciado, mantenimiento_finalizado, autenticacion_fallida_agente, configuracion_modificada}, entidad_relacionada_tipo text?, entidad_relacionada_id UUID?, resultado ∈ {exito, fallo, timeout, parcial}, mensaje_error text?, latencia_ms int?, fecha_hora)`.
- **Reglas obligatorias:**
  - FK con `ON DELETE RESTRICT` siempre; trigger `BEFORE DELETE` que prohíbe DELETE en `gd.impresion_radicado`, `gd.digitalizacion_documento`, `gd.codigo_barras_radicado` y `gd.evento_periferico` (son registros históricos de actos oficiales, equivalentes a `gd.radicado`).
  - UNIQUE `(tenant_id, periferico.serial)` para evitar registrar dos veces el mismo equipo físico.
  - RLS por `tenant_id` en las 6 tablas. `gd.periferico` y `gd.punto_atencion` adicionalmente con política por dependencia para roles no admin.
  - Índices: `gd.impresion_radicado(radicado_id, fecha_impresion DESC)`, `gd.digitalizacion_documento(radicado_id)`, `gd.evento_periferico(periferico_id, fecha_hora DESC)`, `gd.evento_periferico(resultado, fecha_hora DESC)` (para dashboard de fallos).
- **Aceptación:** migración limpia; intentar `DELETE FROM gd.impresion_radicado` falla; `INSERT` con `serial` repetido para el mismo tenant falla con conflicto.

### GD-API-0129 — CRUD de periféricos autorizados (RFP-001)
- **Crea:**
  - `POST /api/v1/gd/perifericos` body `{ tipo_periferico, nombre, marca?, modelo?, serial, dependencia_id?, punto_atencion_id?, configuracion? }` (PERM-PER-001).
  - `GET /api/v1/gd/perifericos?dependencia_id=&punto_atencion_id=&estado=&tipo_periferico=` (PERM-PER-010).
  - `GET /api/v1/gd/perifericos/{id}` retorna detalle + últimas 10 operaciones.
  - `PATCH /api/v1/gd/perifericos/{id}` modifica nombre, configuración o asignación (PERM-PER-001).
  - `POST /api/v1/gd/perifericos/{id}/activar | inactivar | poner-mantenimiento | retirar` con `{ motivo }` (PERM-PER-002).
- **Reglas:**
  - Inactivar un periférico que tiene impresiones/digitalizaciones en curso devuelve `409 periferico_en_uso` con lista de operaciones; el admin debe esperar o forzar con flag `forzar=true` (audited critical).
  - El cambio de `configuracion jsonb` no afecta operaciones pasadas (las impresiones históricas guardan snapshot suficiente en `contenido_impreso`).
- **Permisos:** PERM-PER-001 (config), PERM-PER-002 (estado), PERM-PER-010 (consultar).
- **Eventos:** `gd.periferico.registrado`, `gd.periferico.estado_cambiado`, `gd.periferico.configuracion_modificada` — todos en `core.evento_auditoria`.
- **Aceptación:** registrar impresora Zebra GK420t en el "Punto de Atención Principal" con `serial='ZB-12345'`; listar periféricos del punto retorna 1; intentar registrar otra con el mismo serial falla; inactivar la impresora bloquea nuevos comandos pero las impresiones históricas siguen consultables.

### GD-API-0130 — CRUD de puntos de atención
- **Crea:**
  - `POST/GET/PATCH /api/v1/gd/puntos-atencion` (PERM-PER-001).
  - `POST /api/v1/gd/puntos-atencion/{id}/activar | inactivar` con motivo.
  - `GET /api/v1/gd/puntos-atencion/{id}/perifericos` retorna lista de periféricos asignados al punto.
- **Reglas:**
  - Un punto de atención inactivo no acepta crear radicados con `punto_atencion_id` apuntando a él (validación en GD-API-0024).
  - Al cerrar un punto se debe reasignar o desactivar los periféricos (igual que dependencia → usuarios — GD-API-0008).
- **Eventos:** `gd.punto_atencion.creado`, `gd.punto_atencion.cerrado`.
- **Aceptación:** crear punto "Sede Sur", asignar 2 impresoras + 1 escáner, listar perifericos del punto retorna los 3; inactivar el punto sin reasignar periféricos retorna `409 perifericos_huerfanos`.

### GD-API-0131 — Generación de códigos de barras y QR por radicado (RFP-002, § 14)
- **Crea:**
  - `POST /api/v1/gd/radicados/{id}/codigo-barras` body `{ tipo_codigo: "codigo_barras"|"qr" }` → genera entrada en `gd.codigo_barras_radicado` con `valor_codigo` que sigue el patrón **URL de verificación + token opaco** (ej. `https://entidad.gov.co/v/RAD-2026-001234?t=ab12cd34ef56`). El token resuelve al radicado vía GD-API-0030.
  - `GET /api/v1/gd/radicados/{id}/codigo-barras` retorna el último código vigente.
  - `POST /api/v1/gd/radicados/{id}/codigo-barras/{cod_id}/anular` body `{ motivo }` — marca como anulado y opcionalmente genera reemplazo.
- **Regla absoluta (Doc 6 § 14):** el `valor_codigo` **nunca contiene datos personales del solicitante, cédula, teléfono, ni la descripción de la PQRSD**. Solo el identificador del radicado y un token de verificación. Esto se valida con un linter en CI sobre la implementación.
- **Permisos:** PERM-VU-001 (generación implícita al radicar) + PERM-PER-003 (regenerar manualmente).
- **Eventos:** `gd.codigo_barras.generado`, `gd.codigo_barras.anulado`.
- **Aceptación:** generar QR de radicado `RAD-2026-001234`; decodificar la imagen produce solo la URL + token; visitar la URL (pública, sin auth) muestra fecha de radicación + asunto enmascarado + estado, no datos del solicitante.

### GD-API-0132 — Impresión de etiqueta de radicado (RFP-002)
- **Crea:**
  - `POST /api/v1/gd/perifericos/{periferico_id}/imprimir-etiqueta` body `{ radicado_id, formato_etiqueta?: "estandar"|"compacta"|"sticker", incluir_qr?: bool default true, incluir_codigo_barras?: bool default true }`.
  - Devuelve `{ impresion_id, estado: "encolada", archivo_digital_id }` donde `archivo_digital_id` apunta al PDF/PNG renderizado de la etiqueta lista para enviar al agente local.
  - El servidor **no habla** con el periférico directamente. Encola el job; el agente local autenticado (GD-API-0139) hace polling o suscripción de jobs y reporta resultado vía `POST /api/v1/gd/perifericos/{periferico_id}/impresiones/{impresion_id}/resultado` body `{ estado: "generada"|"fallida", mensaje_error?, latencia_ms? }`.
- **Reglas (Doc 6 § 7 RFP-002):**
  - El periférico debe estar `estado='activo'`; si no, `409 periferico_no_disponible`.
  - El radicado debe existir y no estar `anulado`; si está anulado, **se permite la impresión pero la etiqueta lleva marca visible "RADICADO ANULADO"** (Doc 5 § 28.3 regla 4) — esto se renderiza en el PDF generado.
  - El usuario debe tener `PERM-PER-003` y alcance sobre la dependencia del radicado.
- **Permisos:** PERM-PER-003.
- **Eventos:** `gd.impresion.generada` (cuando agente reporta éxito) o `gd.impresion.fallida` (con mensaje_error). Criticidad `media`.
- **Aceptación:** imprimir etiqueta de `RAD-2026-001234` desde Zebra GK420t; aparece registro en `gd.impresion_radicado` con `estado='generada'`; el agente local reporta `latencia_ms=850`; el QR de la etiqueta resuelve correctamente al radicado.

### GD-API-0133 — Reimpresión controlada de etiqueta con motivo (RFP-003)
- **Crea:**
  - `POST /api/v1/gd/perifericos/{periferico_id}/reimprimir-etiqueta` body `{ radicado_id, motivo (obligatorio, mínimo 10 caracteres), impresion_original_id? }`.
  - Reusa la lógica de GD-API-0132 pero **exige motivo** y **incrementa contador** `intentos_reimpresion` en `gd.impresion_radicado` original (o crea nueva fila con FK a la original).
- **Reglas:**
  - Permiso separado `PERM-PER-004` (reimprimir) ≠ `PERM-PER-003` (imprimir por primera vez). Un radicador puede tener uno sin el otro.
  - Si `intentos_reimpresion > 3`, requerir aprobación del coordinador VU antes de imprimir (flujo similar a anulación).
  - El historial de reimpresiones es consultable desde la ficha del radicado.
- **Eventos:** `gd.impresion.reimpresion` con criticidad `alta` si `intentos_reimpresion > 1`.
- **Aceptación:** reimprimir etiqueta sin motivo falla con 422; reimprimir con motivo "Etiqueta original se dañó al pegar" funciona; al cuarto intento exige aprobación del coordinador.

### GD-API-0134 — Impresión de constancia de radicación (RFP-004)
- **Crea:**
  - `POST /api/v1/gd/perifericos/{periferico_id}/imprimir-constancia` body `{ radicado_id, formato?: "estandar"|"compacta", incluir_qr?: bool default true }`.
  - Reusa el motor de plantillas de EP-010 — la plantilla "Constancia de Radicación" (seed mínima GD-API-0067) se renderiza con datos del radicado + entidad institucional + QR.
  - Devuelve `archivo_digital_id` del PDF generado, lo encola al agente local para impresión.
- **Diferencia vs etiqueta (GD-API-0132):** la constancia es un **documento institucional formal** que se entrega al ciudadano. La etiqueta es **identificación física** del documento que se queda en el sistema.
- **Reglas:** la constancia incluye obligatoriamente: número de radicado, fecha y hora, datos del remitente (con consentimiento), asunto, canal de recepción, QR de verificación, código alfanumérico de verificación. **No incluye** detalles internos como dependencia destino o clasificación.
- **Permisos:** PERM-PER-005.
- **Eventos:** `gd.impresion.generada` con `tipo_impresion='constancia_radicacion'`.
- **Aceptación:** imprimir constancia para ciudadano que radicó presencialmente; el PDF generado es A4, contiene QR escaneable + código `R2X9F4`; al consultar `GET /gd/verificar/R2X9F4` (público, sin auth) se muestra estado del radicado.

### GD-API-0135 — Registro de digitalización individual (RFP-005)
- **Crea:**
  - `POST /api/v1/gd/perifericos/{periferico_id}/digitalizar` body `{ radicado_id, tipo_digitalizacion: "individual", calidad_dpi?: int default 300, observacion? }`. Encola comando al agente local que opera el escáner.
  - Webhook desde agente local: `POST /api/v1/gd/perifericos/{periferico_id}/digitalizaciones/{op_id}/resultado` body `{ estado: "correcta"|"fallida"|"incompleta", archivo_digital_id? (si éxito), numero_paginas?, mensaje_error? }`. El `archivo_digital_id` lo crea el agente subiendo el PDF/imagen al endpoint compartido `POST /api/v1/core/archivos` (EP-018) con `proposito='gd.digitalizacion'`.
  - Al recibir resultado exitoso, el servidor:
    1. Inserta fila en `gd.digitalizacion_documento` con FK a `archivo_digital`.
    2. Crea `gd.anexo` asociado al radicado (vía GD-API-0060).
    3. Si el archivo es PDF escaneado o imagen, dispara `OCRRequested` (GD-API-0111).
    4. Emite evento `gd.digitalizacion.completada`.
- **Permisos:** PERM-PER-006.
- **Reglas:**
  - El radicado debe existir y no estar cerrado; digitalizar sobre un radicado cerrado requiere `PERM-PER-008` adicional (asociar a radicados cerrados).
  - El archivo digitalizado pasa por las mismas validaciones que cualquier anexo: antivirus, MIME whitelist, tamaño máximo (GD-API-0058).
  - Si el agente local reporta `incompleta` (ej. atasco de papel en escáner automático), el sistema deja la digitalización registrada con `estado='incompleta'` y permite reintentar (nueva digitalización, no se sobreescribe la anterior).
- **Eventos:** `gd.digitalizacion.completada`, `gd.digitalizacion.fallida`, `gd.digitalizacion.incompleta`.
- **Aceptación:** digitalizar un oficio físico recibido en VU; el PDF resultante queda como anexo del radicado, OCR se ejecuta y el texto extraído alimenta sugerencia IA de clasificación.

### GD-API-0136 — Digitalización por lote con escáner automático (RFP-006)
- **Crea:**
  - `POST /api/v1/gd/perifericos/{periferico_id}/digitalizar-lote` body `{ radicado_id_default?, modo_separacion: "por_pagina"|"por_codigo_barras"|"manual", calidad_dpi?, observacion? }` — inicia un lote y devuelve `lote_id`.
  - Agente local procesa lote y reporta cada documento vía webhook con `lote_id`:
    - Si `modo_separacion='por_codigo_barras'`, el agente intenta leer códigos de barras intercalados y separa documentos por radicado.
    - Si `modo_separacion='por_pagina'`, cada página es un documento.
    - Si `modo_separacion='manual'`, el usuario asocia páginas después en GD-UI-0092.
  - `GET /api/v1/gd/perifericos/lotes/{lote_id}` retorna progreso + lista de digitalizaciones individuales.
  - `POST /api/v1/gd/perifericos/lotes/{lote_id}/finalizar` confirma asociación final al radicado(s).
- **Permisos:** PERM-PER-007.
- **Reglas:**
  - Si `modo_separacion='por_codigo_barras'` y se detectan radicados anulados o inexistentes, las páginas correspondientes quedan en estado `pendiente_asociacion` (no se asocian automáticamente).
  - El lote tiene un timeout configurable (default 30 min); si el usuario no finaliza, queda como `abandonado` y los archivos digitalizados quedan disponibles pero no asociados (auditable).
- **Eventos:** `gd.digitalizacion.lote_iniciado`, `gd.digitalizacion.lote_finalizado`, `gd.digitalizacion.lote_abandonado`.
- **Aceptación:** lote de 50 páginas con 5 códigos de barras intercalados se separa correctamente en 5 digitalizaciones individuales, cada una asociada a su radicado.

### GD-API-0137 — Asociación automática de scan a radicado activo (RFP-007)
- **Crea:**
  - El cliente UI mantiene un `radicado_activo_id` (el que está siendo radicado/consultado en ese momento). Al disparar digitalización (GD-API-0135 o 0136), el sistema usa este contexto.
  - Endpoint helper `POST /api/v1/gd/perifericos/contexto-activo` body `{ usuario_id, radicado_activo_id, periferico_id, expira_en (seg, default 300) }` — registra el contexto temporalmente. El agente local lee este contexto al iniciar digitalización sin requerir input manual del usuario.
  - `DELETE /api/v1/gd/perifericos/contexto-activo` libera el contexto.
  - Si el usuario digitaliza sin contexto activo y sin `radicado_id` en el body, el archivo queda en estado `pendiente_asociacion` y se muestra en una bandeja para asociar después (con permiso PERM-PER-008).
- **Reglas:** la corrección posterior de asociación requiere `PERM-PER-009` (reemplazar/corregir digitalización) + justificación.
- **Eventos:** `gd.digitalizacion.contexto_asignado`, `gd.digitalizacion.asociacion_corregida`.
- **Aceptación:** radicador escanea un oficio mientras tiene abierto `RAD-2026-001234`; el archivo queda automáticamente asociado a ese radicado sin clicks adicionales.

### GD-API-0138 — Registro de fallos de periféricos y dashboard de salud (RFP-008)
- **Crea:**
  - `GET /api/v1/gd/perifericos/{id}/eventos?desde=&hasta=&resultado=` retorna lista paginada de `gd.evento_periferico` (PERM-PER-011).
  - `GET /api/v1/gd/perifericos/eventos/fallos?desde=` retorna agregado de fallos por periférico (PERM-PER-011) — útil para soporte técnico.
  - `POST /api/v1/gd/perifericos/{id}/mantenimiento` body `{ tipo: "preventivo"|"correctivo", descripcion, fecha_estimada_fin? }` (PERM-PER-012) — marca el periférico en mantenimiento y agenda recordatorio.
  - `POST /api/v1/gd/perifericos/{id}/mantenimiento/{mant_id}/finalizar` body `{ observacion_final, costo?, repuestos? }`.
- **Permisos:** PERM-PER-011 (consultar), PERM-PER-012 (mantenimiento).
- **Reglas:**
  - Si un periférico acumula > 5 fallos en 1 hora, el sistema lo pasa automáticamente a `mantenimiento` y notifica al admin (auto-protección).
  - Los eventos de fallo persisten indefinidamente (no se purgan) — son evidencia de operación.
- **Eventos:** `gd.periferico.auto_protegido`, `gd.mantenimiento.programado`, `gd.mantenimiento.finalizado`.
- **Aceptación:** simular 6 fallos consecutivos de impresión; el periférico pasa a `mantenimiento` automáticamente; el dashboard muestra al periférico en rojo.

### GD-API-0139 — Protocolo de autenticación y autorización del agente local (RNFP-001)
- **Crea:**
  - DDL `gd.agente_local_registro(id UUID PK, tenant_id, periferico_ids UUID[] (uno o varios periféricos que el agente controla), nombre_equipo, version_agente, fingerprint_publico bytea (clave pública del agente), token_emparejamiento_hash text, ultimo_handshake timestamptz, estado ∈ {pendiente, activo, revocado}, registrado_por_user_id FK)`.
  - `POST /api/v1/gd/agentes-locales/emparejar` body `{ nombre_equipo, perifericos: [id], fingerprint_publico }` retorna `{ agente_id, token_emparejamiento (one-shot, expira 10 min) }` — debe ejecutarlo el Admin Sistema desde la consola, no el agente.
  - El agente local usa el `token_emparejamiento` en su primer handshake; tras éxito recibe un JWT de larga duración (configurable, default 30 días) firmado con clave del servidor. Renovación automática con refresh token.
  - Cada llamada del agente al backend incluye el JWT + firma HMAC del body usando su `fingerprint_publico` (defense in depth).
  - `POST /api/v1/gd/agentes-locales/{id}/revocar` (PERM-PER-001) invalida todas las sesiones del agente — útil si el equipo se compromete.
- **Reglas (Doc 6 § 8 RNFP-001):**
  - Intentos de autenticación fallidos se registran en `gd.evento_periferico(tipo_evento='autenticacion_fallida_agente')`.
  - Si un mismo `fingerprint_publico` intenta conectarse desde 2 IPs diferentes en 5 min, se bloquea automáticamente y notifica al admin (posible ataque).
  - **Nunca** se acepta un comando del agente que no esté firmado con el HMAC esperado, aunque el JWT sea válido — protege contra exfiltración de tokens.
- **Eventos:** `gd.agente_local.emparejado`, `gd.agente_local.handshake`, `gd.agente_local.intento_no_autorizado` (criticidad `alta`), `gd.agente_local.revocado`.
- **RNF:** RNF-005, RNF-018, RNFP-001, RNFP-003.
- **Aceptación:** emparejar agente "Counter-1" con 2 periféricos; el agente se conecta y obtiene JWT; revocar al agente invalida el JWT inmediatamente (próxima llamada falla con 401); un atacante con el JWT pero sin la clave privada no puede enviar comandos válidos.

### GD-API-0140 — Seed de permisos PERM-PER-001..012 y matriz rol↔permiso
- **Crea:** inserta los 12 permisos `PERM-PER-001..012` en `gd.permiso` con `modulo='perifericos'`, los marca como críticos `PERM-PER-001`, `PERM-PER-002`, `PERM-PER-004`, `PERM-PER-009`, `PERM-PER-012`.
- **Matriz inicial:**
  - ROL-001 Admin Sistema: todos los 12.
  - ROL-005 Coordinador VU: 002, 003, 004, 005, 006, 007, 008, 010, 011.
  - ROL-004 Radicador VU: 003, 005, 006, 007, 008, 010.
  - ROL-016 Auditor: 010, 011.
  - ROL-002 Admin Seguridad: 010, 011, 012.
- **Actualiza:** `MATRIZ_PERMISOS.md` con los 12 nuevos permisos.
- **Aceptación:** un radicador puede imprimir etiquetas/constancias y digitalizar, pero no configurar periféricos; un auditor solo consulta historial.

### GD-API-0141 — Historial de uso de periféricos auditable (consultas para auditor)
- **Crea:**
  - `GET /api/v1/gd/perifericos/{id}/historial?desde=&hasta=&tipo_operacion=` retorna lista cronológica unificada de impresiones, digitalizaciones, eventos técnicos.
  - `GET /api/v1/gd/perifericos/historial-uso-global?usuario_id=&periferico_id=&desde=` (PERM-AUD-005 + PERM-PER-011) — vista cruzada para Auditor.
  - Exportable como CSV vía `POST /api/v1/gd/perifericos/historial/exportar?formato=csv|excel` (PERM-PER-011 + PERM-REP-008).
- **Permisos:** PERM-PER-010 (su propio uso), PERM-PER-011 (uso de otros — coordinador/auditor).
- **Eventos:** `gd.perifericos.historial_consultado` con criticidad `media`.
- **Aceptación:** auditor consulta historial de impresora "Counter-1" en febrero; obtiene 1247 impresiones + 89 digitalizaciones + 3 fallos; exporta a Excel y la exportación queda registrada.

### GD-API-0142 — Validación de archivos digitalizados (calidad mínima + integridad)
- **Crea:**
  - Worker `validar_calidad_digitalizacion(archivo_digital_id)` que se dispara tras `OCRCompleted` y verifica: confianza OCR > 60%, resolución mínima 200 DPI, sin páginas en blanco contiguas > 2, hash íntegro.
  - Si la calidad es baja, emite `gd.digitalizacion.calidad_baja` y notifica al radicador para que decida si re-digitalizar o aceptar.
  - Endpoint `POST /api/v1/gd/digitalizaciones/{id}/reemplazar` body `{ motivo, archivo_digital_id_nuevo }` (PERM-PER-009) — marca la digitalización original como `reemplazada` y crea la nueva con FK al original (no pierde trazabilidad).
- **Reglas (Doc 6 § 7 RFP-005, RNFP-006):**
  - El archivo original digitalizado **nunca se borra**, incluso si se reemplaza — queda en `core.archivo_digital` con `estado='reemplazado'`.
  - La razón del reemplazo es obligatoria.
- **Eventos:** `gd.digitalizacion.calidad_baja`, `gd.digitalizacion.reemplazada`.
- **Aceptación:** digitalizar un oficio con calidad pobre (DPI=100); el sistema avisa al radicador; el radicador re-digitaliza a 300 DPI; ambas digitalizaciones coexisten en la tabla, la primera marcada como reemplazada.

---

## Anexo A — Resumen de eventos de dominio (referencia)

```
RadicadoCreado · RadicadoClasificado · RadicadoDerivado · RadicadoAnulacionSolicitada · RadicadoAnulado · ConstanciaGenerada
PQRSDCreada · PQRSDClasificada · PQRSDAsignada · PQRSDReasignada · PQRSDProximaAVencer · PQRSDVencida ·
   RespuestaProyectada · RespuestaEnviadaARevision · RespuestaDevuelta · RespuestaAprobada · RespuestaFirmada · PQRSDCerrada · PQRSDReabierta
CorrespondenciaInternaCreada · CorrespondenciaInternaEnviada · CorrespondenciaInternaLeida
CorrespondenciaExternaRecibida · CorrespondenciaExternaPreparada · CorrespondenciaExternaAprobada · CorrespondenciaExternaRadicadaSalida · CorrespondenciaExternaEnviada
DocumentoCargado · DocumentoGeneradoDesdePlantilla · DocumentoVersionado · DocumentoEnviadoARevision · DocumentoAprobado · DocumentoFirmado · DocumentoAnulado · DocumentoDescargado
UsuarioCreado · UsuarioInactivado · UsuarioBloqueado · RolAsignado · RolRetirado · PermisoModificado · SesionIniciada · SesionCerrada · IntentoFallidoLogin
IASolicitada · IASugerenciaGenerada · IASugerenciaAceptada · IASugerenciaModificada · IASugerenciaRechazada
ArchivoCargado · ArchivoAnalizadoAntivirus · ArchivoBloqueado · OCRRequested · OCRCompleted · OCRFailed · ExtraccionXLSXCompletada · BytesPurgadosPorRetencion
RadicadoContingencia · DependenciaFusionada · DependenciaDividida · TerminoSuspendido · TerminoReanudado · VerificacionPublicaConstancia
gd.periferico.registrado · gd.periferico.estado_cambiado · gd.periferico.configuracion_modificada · gd.periferico.auto_protegido
gd.punto_atencion.creado · gd.punto_atencion.cerrado
gd.codigo_barras.generado · gd.codigo_barras.anulado
gd.impresion.generada · gd.impresion.reimpresion · gd.impresion.fallida
gd.digitalizacion.completada · gd.digitalizacion.fallida · gd.digitalizacion.incompleta · gd.digitalizacion.calidad_baja · gd.digitalizacion.reemplazada · gd.digitalizacion.contexto_asignado · gd.digitalizacion.asociacion_corregida · gd.digitalizacion.lote_iniciado · gd.digitalizacion.lote_finalizado · gd.digitalizacion.lote_abandonado
gd.agente_local.emparejado · gd.agente_local.handshake · gd.agente_local.intento_no_autorizado · gd.agente_local.revocado
gd.mantenimiento.programado · gd.mantenimiento.finalizado
gd.perifericos.historial_consultado
```

## Anexo B — Trazabilidad RNF cubiertos

| RNF | Cubierto en épica | Ítem destacado |
|---|---|---|
| RNF-001 Disponibilidad | EP-003 (observabilidad) + infra | Health checks por dominio |
| RNF-002 Continuidad | Infra (backup/restore — fuera del backlog API, pero referenciado) | — |
| RNF-003 Rendimiento | EP-004, EP-006 | <3s crear radicado, <2s consulta |
| RNF-004 Escalabilidad | EP-009, EP-013 | Repositorio doc separado, IA asíncrona |
| RNF-005..008 Seguridad/autorización | EP-001 | Login + RBAC + alcance + mínimo privilegio |
| RNF-009 Auditoría integral | EP-003 | tabla append-only + helper |
| RNF-010 No eliminación histórica | EP-001, EP-002, EP-004 + triggers globales | DELETE bloqueado por trigger |
| RNF-011 Integridad radicado | EP-004 | consecutivos + QR + 405 en edit |
| RNF-012 Trazabilidad ciclo de vida | EP-004, EP-007, EP-008 | historial de estados completo |
| RNF-013 Versionamiento doc | EP-009 | tabla version_documento |
| RNF-014 Plantillas | EP-010 | seed + generación |
| RNF-015 Control borradores | EP-009, EP-010 | estados |
| RNF-016 Firmas | EP-011 | tres niveles |
| RNF-017 Datos personales | EP-005, EP-009 | clasificacion_informacion |
| RNF-018 Cifrado | EP-009 + infra | TLS + secretos en vault |
| RNF-019 Sesiones | EP-001 | timeout + invalidate |
| RNF-020 Usuarios OPS/temporales | EP-001 | estados + reasignación |
| RNF-021 Buzón | EP-006 | endpoint agregado |
| RNF-022 Alertas | EP-006 | jobs + escalado |
| RNF-023 Términos | EP-006 | calendario + suspensiones |
| RNF-024..025 TRD/TVD | EP-015 | versiones + clasificación histórica |
| RNF-026 Estructura orgánica versionada | EP-002 | versión + dependencia |
| RNF-027 APIs | EP-017 | OpenAPI + webhooks |
| RNF-028 Correo institucional | EP-012 | sin auto-radicación |
| RNF-029..030 IA | EP-013 | sugerencia + trazabilidad + redacción |
| RNF-031 RPA | EP-017 | identidad técnica |
| RNF-032..033 Usabilidad/Accesibilidad | UI BACKLOG | — |
| RNF-034 Compatibilidad web | UI BACKLOG | — |
| RNF-035 Mantenibilidad | EP-001..EP-017 (modular) | módulos prefijo `gd` |
| RNF-036 Observabilidad | EP-003 | logs JSON + métricas |
| RNF-037 Backups | Infra | — |
| RNF-038 Conservación documental | EP-009, EP-016 | repositorio + expediente |
| RNF-039 Búsqueda | EP-004, EP-007, EP-009 | endpoints multi-criterio |
| RNF-040 Reportes | EP-014 | dashboards + export |
| RNF-041 Parametrización | EP-002 | configuracion_institucional |
| RNF-042 Estados | Todas las épicas | enums + transiciones validadas |
| RNF-043 Flujos parametrizables | EP-002, EP-007, EP-008 | reglas configurables |
| RNF-044 Calidad de datos | EP-005, EP-009 | duplicados + validaciones |
| RNF-045 Anexos | EP-009 | gestión + permisos |
| RNF-046 Archivos maliciosos | EP-009 | antivirus + lista blanca |
| RNF-047 Vulnerabilidades web | Transversal | OWASP + tests |
| RNF-048..050 DevOps/Tests | Infra | — |
| RNF-051 Documentación | EP-001 (matriz), EP-017 (OpenAPI), README | — |
| RNF-052 Cumplimiento normativo | EP-004, EP-007 | términos + constancias + trazabilidad |
| RNF-053 Clasificación información | EP-009, EP-014 | filtro de exportes |
| RNF-054 Exportación | EP-014 | reporte_generado auditado |
| RNF-055 Multi-entidad | EP-002 | feature flag |
| RNF-056 Comunicaciones internas | EP-008 | trazabilidad |
| RNF-057 Radicación externa desde dependencia | EP-008 | workflow CE |
| RNF-058 Control anulación | EP-004 | flujo aprobación |
| RNF-059 Lectura sensible | EP-003, EP-009 | auditoría de consulta |
| RNF-060 Expediente | EP-016 | tablas base |
| RNFP-001 Seguridad comunicación local | EP-021 | JWT + HMAC + handshake firmado |
| RNFP-002 Trazabilidad uso periféricos | EP-021 | `gd.evento_periferico` + historial auditor |
| RNFP-003 Operación controlada por permisos | EP-021 | PERM-PER-001..012 + matriz rol-permiso |
| RNFP-004 Independencia del hardware | EP-021 | Abstracción agente local + tipos genéricos |
| RNFP-005 Continuidad operativa | EP-021 | Periférico alterno + carga manual trazable |
| RNFP-006 Protección archivos digitalizados | EP-021 + EP-018 | Validación + antivirus + repositorio controlado |

---

**Última actualización:** 2026-05-23 (rev. EP-021 — periféricos)
**Versión:** 0.1 (borrador — pendiente de validación)
