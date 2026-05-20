# Backlog API — Módulo Gestión Documental con IA

> Backlog **independiente** del producto principal (`docs/BACKLOG.md`). Cubre toda la capa de backend (API REST + workers + base de datos + integraciones + IA + auditoría) descrita en los 5 documentos fuente del cliente. Ver `README.md` de esta carpeta para reglas, mandato y prelación documental.

Prefijo de consecutivos: **`GD-API-NNNN`**. Prefijo de épicas: **`GD-API-EP-NNN`**.

---

## Índice de épicas

| # | Épica | Módulos del Mapa | Entrega objetivo |
|---|---|---|---|
| EP-001 | Identidad, acceso, roles y permisos | MOD-001 | Entrega 1 |
| EP-002 | Configuración institucional y estructura orgánica versionada | MOD-002, MOD-003 | Entrega 1 |
| EP-003 | Auditoría y trazabilidad — base transversal | MOD-016 | Entrega 1 |
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

---

## EP-001 — Identidad, acceso, roles y permisos

**Módulos:** MOD-001
**Entidades:** `entidad_publica`, `usuario`, `rol`, `permiso`, `usuario_rol`, `rol_permiso`, `usuario_dependencia`, `cargo`, `sesion`
**RNF objetivo:** RNF-005, RNF-006, RNF-007, RNF-008, RNF-019, RNF-020, RNF-041, RNF-052, RNF-055
**Roles primarios:** ROL-001 (Admin Sistema), ROL-002 (Admin Seguridad), todos los demás como consumidores.

### GD-API-0001 — Esquema de identidad y acceso (DDL)
- **Estado:** PENDING
- **Por qué:** Sin este esquema ningún endpoint subsiguiente puede validar autorización ni guardar snapshots históricos.
- **Crea:** schema `gd`, tablas `gd.entidad_publica`, `gd.usuario`, `gd.rol`, `gd.permiso`, `gd.usuario_rol`, `gd.rol_permiso`, `gd.usuario_dependencia`, `gd.cargo` (estructura mínima de Cargo; vigencia se completa en EP-002).
- **Reglas obligatorias:** PK por UUID, columnas `creado_en` / `actualizado_en` automáticas, `estado` como enum tipado, columna `eliminado_en` **prohibida** (DELETE bloqueado por trigger). Constraint `UNIQUE(numero_documento, tipo_documento)` en `usuario`. Hash + salt para `password_hash` (bcrypt/argon2id). Índices en `usuario(correo_institucional)`, `usuario(estado)`, `usuario_rol(usuario_id, fecha_fin)`.
- **Seed inicial:** roles ROL-001..ROL-019 con sus códigos, ~140 permisos del catálogo (PERM-USR-001..PERM-NOT-007) con `modulo` y `es_critico`.
- **Aceptación:** migración corre limpia en una BD vacía; `psql \dt gd.*` lista las 8 tablas; intentar `DELETE FROM gd.usuario WHERE id=...` falla por trigger; seed muestra 19 roles y > 130 permisos.

### GD-API-0002 — Endpoint de autenticación + sesiones seguras
- **Crea:** `POST /api/v1/gd/auth/login`, `POST /api/v1/gd/auth/logout`, `POST /api/v1/gd/auth/refresh`, `GET /api/v1/gd/auth/me`.
- **RNF:** RNF-005 (hash + salt + bloqueo intentos fallidos + cierre inactividad), RNF-019 (sesiones seguras), RNF-018 (TLS obligatorio), RNF-047 (sin secretos en respuesta).
- **Reglas:** bloqueo tras 5 intentos fallidos en 15 min (configurable vía `gd.configuracion_institucional`); sesión vence a los 30 min de inactividad (RNF-019); `logout` invalida el refresh token y emite evento `SesionCerrada`.
- **Eventos:** `SesionIniciada`, `SesionCerrada`, `IntentoFallidoLogin`.
- **Aceptación:** test que prueba login OK, login con password mal × 5 → bloqueo, refresh válido, refresh tras logout → 401, inactividad simulada → 401.

### GD-API-0003 — Gestión de usuarios (CRUD sin DELETE)
- **Crea:** `POST /api/v1/gd/usuarios`, `GET /api/v1/gd/usuarios`, `GET /api/v1/gd/usuarios/{id}`, `PATCH /api/v1/gd/usuarios/{id}`, `POST /api/v1/gd/usuarios/{id}/inactivar`, `POST /api/v1/gd/usuarios/{id}/bloquear`, `POST /api/v1/gd/usuarios/{id}/desbloquear`, `POST /api/v1/gd/usuarios/{id}/retirar`, `GET /api/v1/gd/usuarios/{id}/historial`.
- **Permisos:** PERM-USR-001 a PERM-USR-012.
- **RNF:** RNF-007 (mínimo privilegio: usuario nuevo sin permisos administrativos), RNF-020 (estados + fechas vinculación + reasignación de tareas), RNF-010 (no eliminación histórica), RNF-009 (auditoría integral).
- **Reglas:** crear usuario no asigna roles automáticamente; `tipo_vinculacion ∈ {planta, provisional, ops, supernumerario, practicante, externo_autorizado, administrador_tecnico}`; al inactivar, dispara job que lista tareas pendientes para reasignación (depende de GD-API-0030).
- **Eventos:** `UsuarioCreado`, `UsuarioInactivado`, `UsuarioBloqueado`.
- **Aceptación:** test crea usuario, inactiva, verifica que `estado='inactivo'` y aparece el evento de auditoría; intentar login del usuario inactivo retorna 401.

### GD-API-0004 — Gestión de roles y matriz rol↔permiso
- **Crea:** `POST/GET/PATCH /api/v1/gd/roles`, `POST /api/v1/gd/roles/{id}/inactivar`, `POST /api/v1/gd/roles/{id}/permisos`, `DELETE /api/v1/gd/roles/{id}/permisos/{permiso_id}` (revoca asociación, no borra permiso), `GET /api/v1/gd/permisos`.
- **Permisos:** PERM-ROL-001 a PERM-ROL-007.
- **RNF:** RNF-006 (roles configurables, no quemados en código), RNF-007, RNF-009.
- **Reglas:** roles seed (`es_sistema=true`) no se inactivan pero sí editan su matriz; un rol con `usuario_rol` activos no se inactiva sin antes reasignarse (devuelve 409 con lista de usuarios afectados).
- **Eventos:** `RolAsignado`, `RolRetirado`, `PermisoModificado`.

### GD-API-0005 — Asignación de roles a usuarios con alcance
- **Crea:** `POST /api/v1/gd/usuarios/{id}/roles`, `DELETE /api/v1/gd/usuarios/{id}/roles/{rol_id}` (cierra vigencia, no borra), `GET /api/v1/gd/usuarios/{id}/roles`.
- **Body:** `{ rol_id, dependencia_id?, alcance: "propio"|"dependencia"|"institucional"|"global", fecha_inicio, fecha_fin?, motivo }`.
- **RNF:** RNF-006 (alcance por dependencia), RNF-007, RNF-008 (separación de funciones).
- **Reglas:** un usuario puede tener varios roles; los roles cerrados (con `fecha_fin`) se conservan para snapshots históricos.
- **Aceptación:** un test asigna rol `Profesional Responsable` con alcance dependencia X, otro test verifica que el usuario solo lista PQRSD de X.

### GD-API-0006 — Middleware de autorización por permiso + alcance
- **Crea:** decorador / middleware `requires(permiso="PERM-PQRSD-009", alcance="dependencia")` consumible desde cada router.
- **Reglas:** valida sesión, carga roles vigentes, deriva permisos efectivos, evalúa alcance contra el recurso (radicado, PQRSD, documento, dependencia objetivo). Falla 403 + emite evento `AccesoDenegado` cuando no aplica.
- **RNF:** RNF-006, RNF-007, RNF-047 (no expone detalles del recurso en el error).
- **Aceptación:** test integración con dos usuarios (uno permitido, uno no) sobre el mismo endpoint dummy retorna 200 y 403 respectivamente, ambos con evento auditado.

### GD-API-0007 — Política de contraseñas + integración futura SSO/LDAP/MFA
- **Crea:** tabla `gd.politica_contrasena` (longitud mínima, complejidad, historial, vigencia, intentos fallidos, cooldown); endpoints `GET/PATCH /api/v1/gd/seguridad/politica`. Stub de proveedor externo `gd.proveedor_identidad_externo` (SSO, LDAP, AD) para fase futura.
- **RNF:** RNF-005 (multifactor preparado), RNF-019.
- **Aceptación:** cambiar política rechaza contraseñas que no cumplan; intentar reusar las últimas N contraseñas falla con `409 password_reused`.

### GD-API-0008 — Reasignación de tareas al inactivar usuario
- **Crea:** `GET /api/v1/gd/usuarios/{id}/tareas-pendientes`, `POST /api/v1/gd/usuarios/{id}/tareas/reasignar` (`{ tareas: [...], usuario_destino_id, motivo }`).
- **Permiso:** PERM-USR-009.
- **RNF:** RNF-020.
- **Reglas:** solo el jefe de la dependencia o el Admin Sistema puede reasignar; cada reasignación deja registro en `asignacion_pqrsd` / `tarea` con `motivo`. Se prohíbe reasignar a usuarios inactivos.

### GD-API-0009 — Snapshot de identidad por actuación
- **Crea:** función SQL `gd.capturar_snapshot_actuacion(usuario_id)` que devuelve `(usuario_id, nombre, rol_codigo, dependencia_codigo, cargo, fecha_hora)`.
- **Por qué:** RNF-006 exige conservar el rol histórico usado en una actuación. Todos los inserts de auditoría / firma / asignación llaman esta función.
- **Aceptación:** cambiar el cargo del usuario después de una firma no altera el cargo registrado en la firma.

### GD-API-0010 — Matriz de permisos como documento navegable
- **Crea:** archivo `docs/gestion documental/MATRIZ_PERMISOS.md` con la matriz Rol × Permiso (S/C/N) traducida del PDF Matriz de Roles.
- **Por qué:** el RNF-051 exige documentación; el equipo y el cliente necesitan ver la matriz sin abrir el PDF.
- **Aceptación:** el documento incluye los 19 roles y los ~140 permisos; cada celda referencia el PERM-NNN y el ROL-NNN.

---

## EP-002 — Configuración institucional y estructura orgánica versionada

**Módulos:** MOD-002, MOD-003
**Entidades:** `entidad_publica`, `configuracion_institucional`, `dependencia`, `version_estructura_organica`, `cargo`, `canal`, `calendario_institucional`, `parametro`
**RNF objetivo:** RNF-026 (estructura orgánica versionada), RNF-041 (parametrización), RNF-055 (multi-entidad).
**Roles primarios:** ROL-001 Admin Sistema, ROL-003 Admin Documental.

### GD-API-0011 — Datos y branding de la entidad pública
- Crea CRUD de `gd.entidad_publica` (NIT, nombre, dirección, teléfonos, correos oficiales, logo).
- `GET/PATCH /api/v1/gd/entidad` (un solo recurso para v1; multi-entidad queda detrás de feature flag `gd.multi_entidad=false`).
- **RNF:** RNF-041, RNF-055.
- **Reglas:** logo se guarda como `archivo_digital` (ver EP-009) y se valida tipo/tamaño; cambiar NIT requiere PERM-USR-001 + justificación.

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

## EP-003 — Auditoría y trazabilidad — base transversal

**Módulos:** MOD-016
**Entidades:** `evento_auditoria`
**RNF objetivo:** RNF-009, RNF-010, RNF-030, RNF-036, RNF-059.
**Por qué primero:** EP-001 ya emite los primeros eventos; este EP cierra el dominio antes de que se acumulen huérfanos.

### GD-API-0017 — Tabla `gd.evento_auditoria` particionada por mes
- DDL con columnas: `id`, `tipo_evento`, `usuario_id`, `rol_snapshot`, `dependencia_snapshot`, `cargo_snapshot`, `entidad_afectada_tipo`, `entidad_afectada_id`, `accion`, `valor_anterior_jsonb`, `valor_nuevo_jsonb`, `justificacion`, `ip`, `user_agent`, `fecha_hora`, `criticidad`.
- Partición por mes calendar (RANGE), índices en `(entidad_afectada_tipo, entidad_afectada_id)`, `(usuario_id, fecha_hora)`, `(tipo_evento, fecha_hora)`.
- Trigger `BEFORE UPDATE` / `BEFORE DELETE` que `RAISE EXCEPTION` — la tabla es **append-only**.
- **RNF:** RNF-009, RNF-010.
- **Aceptación:** intentar `UPDATE` o `DELETE` falla; `EXPLAIN` muestra escaneo por partición correcta para una query con rango de fecha.

### GD-API-0018 — Helper `gd.auditar(...)` para todos los módulos
- Función Postgres + helper de aplicación que recibe `(usuario_id, accion, entidad_tipo, entidad_id, valor_anterior, valor_nuevo, justificacion, criticidad)` y captura snapshot.
- Aplicación: middleware que para cada request muta `request_id`, `ip`, `user_agent` accesibles desde el helper.
- **RNF:** RNF-009.

### GD-API-0019 — Endpoints de consulta de auditoría
- `GET /api/v1/gd/auditoria?entidad_tipo=&entidad_id=&usuario_id=&desde=&hasta=&tipo_evento=&page=&size=` con paginación cursor.
- `GET /api/v1/gd/auditoria/{id}` detalle.
- **Permisos:** PERM-AUD-001..PERM-AUD-008 según la entidad consultada (radicado → AUD-001, usuario → AUD-003, etc.).
- **RNF:** RNF-009, RNF-059 (trazabilidad de consulta sensible — auditar la consulta misma cuando es sobre info clasificada/reservada).

### GD-API-0020 — Eventos de dominio + bus interno
- Bus de eventos en proceso (in-process pub/sub para v1; arquitectura prevé migrar a Kafka/Redis Streams sin tocar consumidores).
- Define interfaz `IEventBus.publish(event: DomainEvent)` y `subscribe(event_type, handler)`.
- Eventos iniciales: `RadicadoCreado`, `RadicadoClasificado`, `RadicadoAnulado`, `PQRSDCreada`, `PQRSDAsignada`, `PQRSDProximaAVencer`, `PQRSDVencida`, `DocumentoFirmado`, `UsuarioInactivado`, `IASugerenciaGenerada`. (Lista completa en GD-API-0021).
- **RNF:** RNF-027 (interoperabilidad por API + eventos), RNF-036 (observabilidad).
- **Aceptación:** test publica evento, dos suscriptores reciben; un handler que falla no impide al otro recibir.

### GD-API-0021 — Catálogo formal de eventos de dominio
- Archivo `docs/gestion documental/EVENTOS.md` con cada evento, payload, productor, consumidor, criticidad. Importa los 30+ eventos del Mapa de Arquitectura sección 7.

### GD-API-0022 — Logs técnicos separados de auditoría funcional
- Configuración de logger estructurado (JSON) hacia stdout/archivo rotado. Campos: `ts`, `level`, `request_id`, `user_id?`, `module`, `message`, `error?`.
- **RNF:** RNF-036.
- **Regla:** los logs técnicos no escriben en `evento_auditoria`. Si la línea contiene información de actuación funcional → va a `gd.auditar(...)`. Si es error/perf/info técnica → va al logger.

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

### GD-API-0057 — Repositorio documental separado del transaccional
- Configuración de storage (S3 compatible o filesystem encriptado) accedido vía `gd.archivo_digital` (rutas, hash, tamaño, MIME). Nunca el contenido vive en Postgres.
- **RNF:** RNF-004 (escalabilidad: almacén documental separado), RNF-018, RNF-046.

### GD-API-0058 — Carga de archivos con validación y antivirus
- `POST /api/v1/gd/archivos` multipart. Valida tipo MIME (lista blanca configurable), tamaño máx (parámetro), calcula hash SHA-256.
- Hook para análisis antivirus (interfaz `IAntivirusScanner` con implementación stub que se reemplaza por ClamAV en prod).
- **RNF:** RNF-046, RNF-018.
- **Aceptación:** subir un `.exe` falla con 415; subir un PDF con virus EICAR de prueba queda en cuarentena (`estado='bloqueado'`).

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

---

**Última actualización:** 2026-05-20
**Versión:** 0.1 (borrador — pendiente de validación)
