# Integración E1 — Identidad, configuración institucional y auditoría base

> Cubre las épicas **EP-001** (Identidad/permisos), **EP-002** (Perfil de organización + estructura orgánica), **EP-019** (Auditoría transversal `core.evento_auditoria`) — fundamentales para que cualquier otro flujo funcione.
>
> Pre-lectura obligatoria: [`README.md`](README.md) de esta carpeta — define convenciones, errores comunes, headers, paginación, snapshots.

## Convención de paths admin (2026-05-25)

Todos los endpoints de **configuración/administración del módulo** viven bajo el prefix `/api/v1/gd/admin/*`:

| Familia | Prefix admin |
|---|---|
| Estructura orgánica + dependencias | `/api/v1/gd/admin/dependencias`, `/api/v1/gd/admin/estructura/*` |
| Catálogos institucionales | `/api/v1/gd/admin/cargos`, `/canales`, `/calendarios`, `/tipos-pqrsd`, `/tipos-correspondencia`, `/reglas/comunicacion` |
| Parámetros institucionales | `/api/v1/gd/admin/parametros` |
| Seguridad (política contraseñas) | `/api/v1/gd/admin/seguridad/politica` |

**Endpoints de identidad/auth/perfil del usuario** (NO admin) siguen al nivel del módulo, sin el prefix `/admin/`:

| Familia | Prefix |
|---|---|
| Usuario actual | `/api/v1/gd/me` |
| Perfil de usuarios | `/api/v1/gd/perfil-usuario/*` |
| Roles y permisos del catálogo | `/api/v1/gd/roles`, `/api/v1/gd/permisos` |
| Asignación de roles | `/api/v1/gd/usuarios/{id}/roles` |
| Perfil de organización | `/api/v1/gd/organizacion` |

Esta separación facilita el filtrado por permisos en el sidebar de la UI y la navegación: el operador encuentra TODO lo configurable bajo "Administración".

## Índice

- [1. Identidad del usuario actual](#1-identidad-del-usuario-actual)
- [2. Perfil institucional del usuario (`gd.perfil_usuario`)](#2-perfil-institucional-del-usuario)
- [3. Catálogo de roles y permisos GD](#3-catálogo-de-roles-y-permisos-gd)
- [4. Asignación de roles con alcance por dependencia](#4-asignación-de-roles-con-alcance-por-dependencia)
- [5. Política de contraseñas](#5-política-de-contraseñas)
- [6. Reasignación de tareas al inactivar usuario](#6-reasignación-de-tareas-al-inactivar-usuario)
- [7. Perfil de organización + módulos activables](#7-perfil-de-organización--módulos-activables)
- [8. Estructura orgánica versionada (dependencias)](#8-estructura-orgánica-versionada)
- [9. Cargos institucionales](#9-cargos-institucionales)
- [10. Canales, calendarios, parámetros institucionales](#10-canales-calendarios-parámetros)
- [11. Consulta de eventos de auditoría](#11-consulta-de-eventos-de-auditoría)

---

## 1. Identidad del usuario actual

### GET `/api/v1/gd/me`
**Tarea backend:** GD-API-0002
**Tarea(s) UI consumidoras:** GD-UI-0001 (matriz permisos en runtime), GD-UI-0002 (sidebar), GD-UI-0006 (`<GdShell />`)
**Permiso requerido:** ninguno (cualquier usuario autenticado con perfil GD activo en el tenant)
**Evento emitido:** ninguno (solo lectura no auditable)

#### Request
Sin body. Headers estándar.

#### Response 200
```json
{
  "user_id": "uuid",
  "email": "juan@entidad.gov.co",
  "nombres": "Juan Carlos",
  "apellidos": "Pérez García",
  "perfil_gd": {
    "tipo_vinculacion": "planta",
    "estado_gd": "activo",
    "fecha_inicio_vinculacion": "2025-01-15",
    "fecha_fin_vinculacion": null,
    "ultimo_acceso": "2026-05-23T08:11:00.000Z"
  },
  "dependencia_actual": {
    "id": "uuid",
    "codigo": "JUR-001",
    "nombre": "Oficina Asesora Jurídica"
  },
  "cargo_actual": {
    "id": "uuid",
    "nombre": "Profesional Especializado"
  },
  "roles_gd_vigentes": [
    {
      "asignacion_alcance_id": "uuid",
      "rol_codigo": "gd.profesional",
      "rol_nombre": "Profesional Responsable",
      "dependencia_id": "uuid",
      "dependencia_nombre": "Oficina Asesora Jurídica",
      "alcance": "dependencia",
      "fecha_inicio": "2025-01-15",
      "fecha_fin": null
    }
  ],
  "permisos_efectivos": [
    "PERM-PQRSD-009",
    "PERM-PQRSD-012",
    "PERM-DOC-005",
    "..."
  ],
  "modulos_activos_organizacion": [
    "pqrsd_legal",
    "correspondencia_interna",
    "firma_electronica",
    "ventanilla_presencial_con_perifericos"
  ]
}
```

#### Errores específicos
- **403 `gd_profile_missing_or_inactive`** — el usuario está autenticado en el producto principal pero no tiene `gd.perfil_usuario` para el tenant, o lo tiene en estado distinto de `activo`. Mensaje útil para que la UI muestre "Solicite a su administrador activarlo en Gestión Documental".

---

## 2. Perfil institucional del usuario

### POST `/api/v1/gd/perfil-usuario`
**Tarea backend:** GD-API-0003
**Tarea(s) UI consumidoras:** GD-UI-0066 (gestión de usuarios — pendiente, EP-008 UI)
**Permiso requerido:** `PERM-USR-001` (alcance: institucional)
**Evento emitido:** `gd.perfil_usuario.creado` (criticidad: media)

#### Request
```json
{
  "user_id": "uuid (debe existir ya en app.users — invitación de tenant)",
  "tipo_vinculacion": "planta | provisional | ops | supernumerario | practicante | externo_autorizado | administrador_tecnico",
  "fecha_inicio_vinculacion": "2026-05-23",
  "fecha_fin_vinculacion": "2026-12-31 (opcional, requerido si tipo_vinculacion ∈ {ops, provisional, supernumerario, practicante})",
  "dependencia_actual_id": "uuid",
  "cargo_actual_id": "uuid (opcional)"
}
```

#### Response 201
```json
{
  "user_id": "uuid",
  "tipo_vinculacion": "planta",
  "estado_gd": "activo",
  "fecha_inicio_vinculacion": "2026-05-23",
  "fecha_fin_vinculacion": null,
  "dependencia_actual_id": "uuid",
  "cargo_actual_id": "uuid",
  "creado_en": "2026-05-23T14:32:11.000Z",
  "creado_por_user_id": "uuid"
}
```

#### Errores específicos
- **404 `user_not_in_tenant`** — el `user_id` no existe en `app.users` para este tenant. La UI debe invitar primero por el flujo del producto principal.
- **409 `perfil_ya_existe`** — el usuario ya tiene perfil GD en este tenant. Usar PATCH si se quiere modificar.
- **422 `fecha_fin_requerida`** — si tipo_vinculacion es temporal y no se incluye `fecha_fin_vinculacion`.

---

### PATCH `/api/v1/gd/perfil-usuario/{user_id}`
**Tarea backend:** GD-API-0003
**Tarea(s) UI consumidoras:** GD-UI-0066
**Permiso requerido:** `PERM-USR-002` (alcance: institucional)
**Evento emitido:** `gd.perfil_usuario.modificado` (criticidad: media)

#### Request
```json
{
  "tipo_vinculacion": "..." (opcional),
  "fecha_fin_vinculacion": "2026-12-31" (opcional, set o null),
  "dependencia_actual_id": "uuid" (opcional),
  "cargo_actual_id": "uuid" (opcional, set o null)
}
```
> Solo se aceptan los campos listados. `estado_gd` se modifica por endpoints dedicados (siguientes).

#### Response 200
Mismo shape que POST.

---

### POST `/api/v1/gd/perfil-usuario/{user_id}/{accion}`
Acciones: `inactivar | bloquear | desbloquear | retirar | suspender`.

**Tarea backend:** GD-API-0003
**Tarea(s) UI consumidoras:** GD-UI-0066, GD-UI-0019 (reasignación masiva al inactivar)
**Permiso requerido:** `PERM-USR-{004..008}` (uno por acción, alcance: institucional)
**Evento emitido:** `gd.perfil_usuario.{accion}` (criticidad: alta)

#### Request
```json
{
  "motivo": "Cambio de proyecto. Reasignaron tareas a María González."
}
```
> `motivo` es obligatorio, min 10 caracteres, max 500.

#### Response 200
```json
{
  "user_id": "uuid",
  "estado_gd_anterior": "activo",
  "estado_gd_nuevo": "inactivo",
  "motivo": "...",
  "ejecutado_por_user_id": "uuid",
  "ejecutado_en": "2026-05-23T14:32:11.000Z"
}
```

#### Errores específicos
- **409 `pending_tasks`** — el usuario tiene tareas pendientes y la acción (inactivar/retirar/suspender) lo dejaría sin asignación. Response incluye:
  ```json
  {
    "error": "conflict",
    "code": "pending_tasks",
    "message": "El usuario tiene 14 tareas pendientes",
    "detalles": {
      "tareas_pendientes": 14,
      "url_reasignacion": "/api/v1/gd/perfil-usuario/{user_id}/tareas-pendientes"
    }
  }
  ```
  La UI dirige al usuario a `GD-UI-0019` para reasignar antes.

---

### GET `/api/v1/gd/perfil-usuario`
**Tarea backend:** GD-API-0003
**Tarea(s) UI consumidoras:** GD-UI-0066
**Permiso requerido:** `PERM-USR-010` (alcance: institucional)

#### Request (query)
- `dependencia_id?: UUID` — filtrar por dependencia actual.
- `estado_gd?: string` — uno o varios separados por coma.
- `tipo_vinculacion?: string`.
- `q?: string` — búsqueda por nombre/email.
- `limit?: int (default 50, max 200)`, `cursor?: string`.

#### Response 200
```json
{
  "items": [
    {
      "user_id": "uuid",
      "email": "juan@entidad.gov.co",
      "nombres": "Juan Carlos",
      "apellidos": "Pérez García",
      "tipo_vinculacion": "planta",
      "estado_gd": "activo",
      "dependencia_actual": { "id": "uuid", "nombre": "Oficina Jurídica" },
      "cargo_actual": { "id": "uuid", "nombre": "Profesional Especializado" },
      "roles_gd_count": 2,
      "ultimo_acceso": "2026-05-22T17:00:00.000Z"
    }
  ],
  "pagina": { "siguiente_cursor": "...", "total_estimado": 247, "limit_aplicado": 50 }
}
```

---

### GET `/api/v1/gd/perfil-usuario/{user_id}/historial`
**Tarea backend:** GD-API-0003
**Tarea(s) UI consumidoras:** GD-UI-0066 (tab "Historial" en ficha de usuario)
**Permiso requerido:** `PERM-USR-010`

#### Response 200
```json
{
  "user_id": "uuid",
  "eventos": [
    {
      "evento_auditoria_id": "uuid",
      "tipo_evento": "gd.perfil_usuario.modificado",
      "campo_modificado": "dependencia_actual_id",
      "valor_anterior": "JUR-001",
      "valor_nuevo": "CON-002",
      "ejecutado_por": { "user_id": "uuid", "nombre": "Admin Pérez" },
      "fecha": "2026-05-23T14:32:11.000Z",
      "motivo": "Traslado por reestructura"
    }
  ]
}
```

---

## 3. Catálogo de roles y permisos GD

### GET `/api/v1/gd/roles`
**Tarea backend:** GD-API-0004
**Tarea(s) UI consumidoras:** GD-UI-0001 (matriz), GD-UI-0067 (gestión de roles — pendiente)
**Permiso requerido:** `PERM-ROL-001` (alcance: institucional)

#### Response 200
```json
{
  "items": [
    {
      "codigo": "gd.profesional",
      "nombre": "Profesional Responsable",
      "descripcion": "Funcionario que gestiona PQRSD y proyecta respuestas",
      "es_sistema": true,
      "estado": "activo",
      "permisos_count": 23
    }
  ]
}
```

---

### POST `/api/v1/gd/roles`
**Tarea backend:** GD-API-0004
**Permiso requerido:** `PERM-ROL-002` (alcance: institucional)
**Evento emitido:** `gd.rol.creado` (criticidad: alta — afecta autorización global)

#### Request
```json
{
  "codigo": "gd.custom_revisor_juridico (debe empezar por 'gd.' y no chocar con seed)",
  "nombre": "Revisor Jurídico Especial",
  "descripcion": "Rol custom para revisión jurídica de casos especiales"
}
```

#### Response 201
Mismo shape que el item de GET.

#### Errores específicos
- **409 `rol_codigo_reservado`** — código colisiona con rol seed del sistema.

---

### POST `/api/v1/gd/roles/{codigo}/inactivar`
**Tarea backend:** GD-API-0004
**Permiso requerido:** `PERM-ROL-005`
**Evento emitido:** `gd.rol.inactivado` (criticidad: alta)

#### Request
```json
{ "motivo": "..." }
```

#### Errores específicos
- **409 `role_in_use`** — el rol tiene asignaciones activas. Response:
  ```json
  {
    "error": "conflict",
    "code": "role_in_use",
    "message": "El rol está asignado a 12 usuarios activos",
    "detalles": { "usuarios_afectados": 12, "tenants_afectados": ["uuid"] }
  }
  ```

---

### POST `/api/v1/gd/roles/{codigo}/permisos`
**Tarea backend:** GD-API-0004
**Permiso requerido:** `PERM-ROL-003`
**Evento emitido:** `gd.rol_permiso.modificado` (criticidad: alta)

#### Request
```json
{
  "permiso_codigo": "PERM-PQRSD-009",
  "alcance_default": "propio | dependencia | dependencias_autorizadas | institucional | global"
}
```

#### Response 201
```json
{
  "rol_codigo": "gd.custom_revisor_juridico",
  "permiso_codigo": "PERM-PQRSD-009",
  "alcance_default": "dependencia",
  "agregado_en": "2026-05-23T14:32:11.000Z"
}
```

---

### DELETE `/api/v1/gd/roles/{codigo}/permisos/{permiso_codigo}`
**Tarea backend:** GD-API-0004
**Permiso requerido:** `PERM-ROL-004`
**Evento emitido:** `gd.rol_permiso.modificado` (criticidad: alta)

> Esto **NO destruye** el permiso, solo lo remueve de la matriz rol↔permiso (Mandato #3).

#### Response 204
Sin body.

---

### GET `/api/v1/gd/permisos`
**Tarea backend:** GD-API-0004
**Permiso requerido:** `PERM-ROL-001`

#### Response 200
```json
{
  "items": [
    {
      "codigo": "PERM-PQRSD-009",
      "nombre": "Proyectar respuesta PQRSD",
      "modulo": "pqrsd",
      "descripcion": "Permite crear borradores de respuesta a PQRSD asignadas",
      "es_critico": false
    }
  ]
}
```

---

## 4. Asignación de roles con alcance por dependencia

### POST `/api/v1/gd/usuarios/{user_id}/roles`
**Tarea backend:** GD-API-0005
**Tarea(s) UI consumidoras:** GD-UI-0066 (asignar rol en ficha usuario)
**Permiso requerido:** `PERM-USR-011` (alcance: institucional)
**Evento emitido:** `gd.rol_asignado` (criticidad: alta)

#### Request
```json
{
  "rol_codigo": "gd.profesional",
  "dependencia_id": "uuid (requerido si alcance ∈ {dependencia, dependencias_autorizadas})",
  "alcance": "propio | dependencia | dependencias_autorizadas | institucional | global",
  "fecha_inicio": "2026-05-23",
  "fecha_fin": "2026-12-31 (opcional)",
  "motivo": "Asignación por acto administrativo 1234"
}
```

#### Response 201
```json
{
  "asignacion_alcance_id": "uuid",
  "user_id": "uuid",
  "rol_codigo": "gd.profesional",
  "dependencia_id": "uuid",
  "alcance": "dependencia",
  "fecha_inicio": "2026-05-23",
  "fecha_fin": null,
  "estado": "activa",
  "asignado_por_user_id": "uuid"
}
```

#### Errores específicos
- **422 `alcance_requiere_dependencia`** — si `alcance` requiere `dependencia_id` y no se proporcionó.
- **409 `usuario_inactivo`** — el usuario destino tiene `estado_gd != 'activo'`.

---

### POST `/api/v1/gd/usuarios/{user_id}/roles/{asignacion_alcance_id}/cerrar`
**Tarea backend:** GD-API-0005
**Permiso requerido:** `PERM-USR-012`
**Evento emitido:** `gd.rol_retirado` (criticidad: alta)

#### Request
```json
{ "motivo": "Traslado a otra dependencia" }
```

#### Response 200
```json
{
  "asignacion_alcance_id": "uuid",
  "fecha_fin": "2026-05-23T14:32:11.000Z",
  "estado": "cerrada"
}
```

> Nota: las asignaciones cerradas se conservan permanentemente (RNF-006) — sirven para reconstruir snapshots históricos.

---

### GET `/api/v1/gd/usuarios/{user_id}/roles`
**Tarea backend:** GD-API-0005
**Permiso requerido:** `PERM-USR-010` (o el propio usuario)

#### Request (query)
- `incluir_historicas?: bool (default false)` — si true, incluye asignaciones cerradas.

#### Response 200
```json
{
  "vigentes": [
    {
      "asignacion_alcance_id": "uuid",
      "rol_codigo": "gd.profesional",
      "rol_nombre": "Profesional Responsable",
      "dependencia": { "id": "uuid", "nombre": "Oficina Jurídica" },
      "alcance": "dependencia",
      "fecha_inicio": "2025-01-15",
      "fecha_fin": null
    }
  ],
  "historicas": [
    {
      "asignacion_alcance_id": "uuid",
      "rol_codigo": "gd.radicador",
      "dependencia": { "id": "uuid", "nombre": "Ventanilla Única" },
      "alcance": "propio",
      "fecha_inicio": "2024-01-15",
      "fecha_fin": "2024-12-31",
      "motivo_cierre": "Traslado"
    }
  ]
}
```

---

## 5. Política de contraseñas

### GET `/api/v1/gd/admin/seguridad/politica`
**Tarea backend:** GD-API-0007
**Tarea(s) UI consumidoras:** GD-UI-0053 (config seguridad — pendiente)
**Permiso requerido:** `PERM-USR-001`

#### Response 200
```json
{
  "longitud_minima": 12,
  "complejidad_regex": "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[^\\w]).+$",
  "historial_no_reuso": 12,
  "vigencia_dias": 90,
  "intentos_fallidos_max": 5,
  "cooldown_segundos": 300,
  "vigente_desde": "2026-01-01T00:00:00.000Z"
}
```

---

### PATCH `/api/v1/gd/admin/seguridad/politica`
**Tarea backend:** GD-API-0007
**Permiso requerido:** `PERM-USR-001` (alcance: institucional)
**Evento emitido:** `gd.politica_contrasena.modificada` (criticidad: alta)

#### Request
Cualquier subset de los campos del GET. Cambios entran en vigor para nuevas contraseñas.

---

## 6. Reasignación de tareas al inactivar usuario

### GET `/api/v1/gd/perfil-usuario/{user_id}/tareas-pendientes`
**Tarea backend:** GD-API-0008
**Tarea(s) UI consumidoras:** GD-UI-0019 (wizard reasignación masiva)
**Permiso requerido:** `PERM-USR-009`

#### Response 200
```json
{
  "user_id": "uuid",
  "total_pendientes": 14,
  "por_tipo": {
    "pqrsd_asignadas": 8,
    "documentos_por_revisar": 3,
    "documentos_por_firmar": 2,
    "correspondencia_recibida": 1
  },
  "items": [
    {
      "tarea_id": "uuid",
      "tipo_tarea": "responder_pqrsd",
      "entidad_origen_tipo": "pqrsd",
      "entidad_origen_id": "uuid",
      "titulo": "PQRSD RAD-2026-001234 — solicitud de información",
      "fecha_limite": "2026-06-15T17:00:00.000Z",
      "prioridad": "alta",
      "dias_para_vencimiento": 23
    }
  ]
}
```

---

### POST `/api/v1/gd/perfil-usuario/{user_id}/tareas/reasignar`
**Tarea backend:** GD-API-0008
**Permiso requerido:** `PERM-USR-009`
**Evento emitido:** `gd.tarea.reasignada` (criticidad: media) — uno por tarea

#### Request
```json
{
  "tareas": ["uuid1", "uuid2", "uuid3"],
  "user_destino_id": "uuid",
  "motivo": "Reasignación por inactivación de usuario origen"
}
```

#### Response 200
```json
{
  "reasignadas": 3,
  "fallidas": 0,
  "detalles": [
    { "tarea_id": "uuid1", "estado": "reasignada", "evento_auditoria_id": "uuid" },
    { "tarea_id": "uuid2", "estado": "reasignada", "evento_auditoria_id": "uuid" }
  ]
}
```

#### Errores específicos
- **422 `usuario_destino_inactivo`** — el usuario destino tiene `estado_gd != 'activo'`.
- **207 Multi-Status** — algunas reasignaciones fallaron (ej. tarea ya finalizada por otro). El body incluye detalle por tarea.

---

## 7. Perfil de organización + módulos activables

### GET `/api/v1/gd/organizacion`
**Tarea backend:** GD-API-0011
**Tarea(s) UI consumidoras:** GD-UI-0052 (config organización), GD-UI-0003 (logo en `<InstitutionalLetterhead />`)
**Permiso requerido:** ninguno (cualquier usuario GD activo)

#### Response 200
```json
{
  "tenant_id": "uuid",
  "tipo_organizacion": "publica | privada | mixta | ong | gremial | cooperativa",
  "identificacion_fiscal": "900123456-7",
  "tipo_identificacion_fiscal": "NIT",
  "razon_social_legal": "Alcaldía Municipal de Ejemplo",
  "nombre_corto": "Alcaldía Ejemplo",
  "direccion_oficial": "Cra 10 # 20-30",
  "telefono_oficial": "+57 600 1234567",
  "correo_oficial": "info@ejemplo.gov.co",
  "sitio_web": "https://ejemplo.gov.co",
  "logo": {
    "archivo_digital_id": "uuid",
    "url_publica": "https://cdn.../logos/uuid.png",
    "mime_type": "image/png"
  },
  "politica_firma_default": "electronica",
  "formato_radicado": "{prefijo}-{vigencia}-{consecutivo:06d}",
  "dias_alerta_vencimiento_default": 3,
  "pais_iso": "CO",
  "zona_horaria_default": "America/Bogota"
}
```

---

### PATCH `/api/v1/gd/organizacion`
**Tarea backend:** GD-API-0011
**Permiso requerido:** `PERM-USR-001` (alcance: institucional)
**Evento emitido:** `gd.organizacion.modificada` (criticidad: alta)

#### Request
Subset de los campos editables (no se permite cambiar `tipo_organizacion` después de la primera vez sin migración manual).

---

### GET `/api/v1/gd/organizacion/modulos`
**Tarea backend:** GD-API-0011.b
**Tarea(s) UI consumidoras:** GD-UI-0001 (sidebar visibility), GD-UI-0052
**Permiso requerido:** ninguno (necesario para que la UI sepa qué pantallas ocultar)

#### Response 200
```json
{
  "modulos": [
    { "modulo_codigo": "pqrsd_legal", "activado": true, "configuracion": null },
    { "modulo_codigo": "pqrsd_tickets", "activado": false, "configuracion": null },
    { "modulo_codigo": "correspondencia_interna", "activado": true, "configuracion": null },
    { "modulo_codigo": "correspondencia_externa", "activado": true, "configuracion": null },
    { "modulo_codigo": "firma_escaneada", "activado": false, "configuracion": null },
    { "modulo_codigo": "firma_electronica", "activado": true, "configuracion": null },
    { "modulo_codigo": "firma_digital_certificada", "activado": false, "configuracion": null },
    { "modulo_codigo": "expedientes", "activado": true, "configuracion": null },
    { "modulo_codigo": "trd_tvd", "activado": true, "configuracion": null },
    { "modulo_codigo": "integracion_correo", "activado": true, "configuracion": null },
    { "modulo_codigo": "agentes_ia", "activado": true, "configuracion": null },
    { "modulo_codigo": "radicacion_externa_desde_dependencia", "activado": true, "configuracion": null },
    { "modulo_codigo": "consulta_publica_radicado", "activado": true, "configuracion": null },
    { "modulo_codigo": "ventanilla_presencial_con_perifericos", "activado": true, "configuracion": { "default_dpi": 300, "max_paginas_lote": 100 } }
  ]
}
```

---

### PATCH `/api/v1/gd/organizacion/modulos`
**Tarea backend:** GD-API-0011.b
**Tarea(s) UI consumidoras:** GD-UI-0052
**Permiso requerido:** `PERM-USR-001`
**Evento emitido:** `gd.modulo.activado` o `gd.modulo.desactivado` (criticidad: alta)

#### Request
```json
{
  "modulos": [
    { "modulo_codigo": "pqrsd_legal", "activado": false },
    { "modulo_codigo": "pqrsd_tickets", "activado": true }
  ]
}
```

#### Response 200
Mismo shape que GET.

#### Errores específicos
- **409 `modulo_con_datos`** — intentar desactivar un módulo con datos vivos (ej. desactivar `pqrsd_legal` con PQRSD abiertas). Response sugiere "Cerrar todas las PQRSD primero o usar `forzar=true` (audit critical)".

---

## 8. Estructura orgánica versionada

### POST `/api/v1/gd/admin/dependencias`
**Tarea backend:** GD-API-0012
**Tarea(s) UI consumidoras:** GD-UI-0058 (admin dependencias — pendiente)
**Permiso requerido:** `PERM-USR-001` (alcance: institucional)
**Evento emitido:** `gd.dependencia.creada` (criticidad: media)

#### Request
```json
{
  "codigo_organico": "JUR-001",
  "nombre": "Oficina Asesora Jurídica",
  "dependencia_padre_id": "uuid (opcional, null si es raíz)",
  "fecha_inicio_vigencia": "2026-05-23",
  "version_estructura_id": "uuid (la versión vigente)"
}
```

#### Response 201
```json
{
  "id": "uuid",
  "codigo_organico": "JUR-001",
  "nombre": "Oficina Asesora Jurídica",
  "dependencia_padre_id": "uuid",
  "estado": "activa",
  "fecha_inicio_vigencia": "2026-05-23",
  "fecha_fin_vigencia": null,
  "version_estructura_id": "uuid",
  "creada_en": "2026-05-23T14:32:11.000Z"
}
```

---

### GET `/api/v1/gd/admin/dependencias`
**Tarea backend:** GD-API-0012
**Tarea(s) UI consumidoras:** GD-UI-0058, `<DependenciaPicker />` (GD-UI-0004), filtros en multiples vistas
**Permiso requerido:** ninguno (catálogo público dentro del tenant)

#### Request (query)
- `estado?: string` — `activa | inactiva | cerrada | fusionada`.
- `version_estructura_id?: uuid` — default: vigente.
- `incluir_jerarquia?: bool (default false)` — si true, response devuelve árbol.
- `q?: string` — búsqueda por nombre o código.

#### Response 200 (lista plana)
```json
{
  "items": [
    {
      "id": "uuid",
      "codigo_organico": "JUR-001",
      "nombre": "Oficina Asesora Jurídica",
      "dependencia_padre_id": "uuid",
      "estado": "activa",
      "fecha_inicio_vigencia": "2026-05-23",
      "fecha_fin_vigencia": null
    }
  ]
}
```

#### Response 200 (jerarquía)
Si `incluir_jerarquia=true`:
```json
{
  "raiz": [
    {
      "id": "uuid",
      "codigo_organico": "DESPACHO",
      "nombre": "Despacho del Alcalde",
      "hijos": [
        { "id": "uuid", "codigo_organico": "JUR-001", "nombre": "Oficina Asesora Jurídica", "hijos": [] }
      ]
    }
  ]
}
```

---

### PATCH `/api/v1/gd/admin/dependencias/{id}`
**Tarea backend:** GD-API-0012
**Permiso requerido:** `PERM-USR-001`

#### Request
```json
{
  "nombre": "..." (opcional),
  "dependencia_padre_id": "uuid" (opcional)
}
```
> ⚠️ Cambios en `nombre` o `codigo_organico` exigen abrir nueva versión de estructura (no se mutan vigentes con actuaciones). El endpoint responde **409 `dependencia_con_actuaciones`** si la dependencia tiene radicados.

---

### POST `/api/v1/gd/admin/dependencias/{id}/cerrar-vigencia`
**Tarea backend:** GD-API-0012
**Permiso requerido:** `PERM-USR-001`
**Evento emitido:** `gd.dependencia.cerrada` (criticidad: alta)

#### Request
```json
{
  "motivo": "Reestructura administrativa",
  "fecha_fin": "2026-06-30",
  "acto_administrativo": "Decreto 0123 de 2026"
}
```

---

### POST `/api/v1/gd/admin/estructura/versiones`
**Tarea backend:** GD-API-0012
**Permiso requerido:** `PERM-USR-001`
**Evento emitido:** `gd.estructura_organica.versionada` (criticidad: alta)

#### Request
```json
{
  "numero_version": "v2.0",
  "descripcion": "Reestructura por Decreto 0123 de 2026",
  "fecha_inicio_vigencia": "2026-07-01",
  "acto_administrativo": "Decreto 0123/2026"
}
```

#### Response 201
```json
{
  "version_estructura_id": "uuid",
  "numero_version": "v2.0",
  "estado": "borrador",
  "dependencias_clonadas": 47
}
```
> La versión nueva entra como `borrador`. Activación requiere endpoint adicional `POST /api/v1/gd/admin/estructura/versiones/{id}/activar` (no documentado aquí — flujo de revisión).

---

### GET `/api/v1/gd/admin/estructura/vigente`
**Tarea backend:** GD-API-0012
**Permiso requerido:** ninguno

#### Response 200
```json
{
  "version_estructura_id": "uuid",
  "numero_version": "v1.5",
  "fecha_inicio_vigencia": "2025-01-01",
  "dependencias_count": 47
}
```

---

### GET `/api/v1/gd/admin/estructura/historica?fecha=YYYY-MM-DD`
**Tarea backend:** GD-API-0012
**Tarea(s) UI consumidoras:** GD-UI-0015 (timeline radicado), GD-UI-0058 (consulta histórica)
**Permiso requerido:** ninguno

#### Response 200
Mismo shape que `/vigente`, pero retorna la versión que estaba vigente en `fecha`.

---

### GET `/api/v1/gd/admin/estructura/dependencias/{id}/historial`
**Tarea backend:** GD-API-0124 (EP-020 — historial jerárquico)
**Tarea(s) UI consumidoras:** GD-UI-0058
**Permiso requerido:** `PERM-USR-010`

#### Response 200
```json
{
  "dependencia_id": "uuid",
  "eventos": [
    {
      "fecha_inicio_vigencia": "2024-01-01",
      "fecha_fin_vigencia": "2024-12-31",
      "nombre_en_periodo": "Oficina Jurídica",
      "dependencia_padre_id": "uuid",
      "padre_nombre": "Despacho",
      "tipo_cambio": "creacion"
    },
    {
      "fecha_inicio_vigencia": "2025-01-01",
      "fecha_fin_vigencia": null,
      "nombre_en_periodo": "Oficina Asesora Jurídica",
      "tipo_cambio": "cambio_nombre"
    }
  ]
}
```

---

### POST `/api/v1/gd/admin/estructura/fusionar`
**Tarea backend:** GD-API-0124
**Permiso requerido:** `PERM-USR-001`
**Evento emitido:** `gd.dependencia.fusionada` (criticidad: crítica)

#### Request
```json
{
  "dependencias_origen": ["uuid1", "uuid2"],
  "dependencia_destino_id": "uuid",
  "fecha_vigencia": "2026-07-01",
  "motivo": "Reestructura",
  "acto_administrativo": "Decreto 0123/2026"
}
```

---

## 9. Cargos institucionales

### POST/GET/PATCH `/api/v1/gd/admin/cargos`
**Tarea backend:** GD-API-0013
**Tarea(s) UI consumidoras:** GD-UI-0059 (admin cargos — pendiente)
**Permiso requerido:** `PERM-USR-001`

#### POST Request
```json
{
  "nombre": "Profesional Especializado",
  "dependencia_id": "uuid (opcional, null si es transversal)",
  "fecha_inicio_vigencia": "2026-05-23"
}
```

#### Response (item)
```json
{
  "id": "uuid",
  "nombre": "Profesional Especializado",
  "dependencia_id": "uuid",
  "estado": "activo",
  "fecha_inicio_vigencia": "2026-05-23",
  "fecha_fin_vigencia": null
}
```

> ⚠️ El cargo usado en una firma o actuación se preserva como snapshot (RNF-006). Modificar el nombre del cargo no afecta firmas pasadas.

---

## 10. Canales, calendarios, parámetros

### GET `/api/v1/gd/admin/canales`
**Tarea backend:** GD-API-0014
**Tarea(s) UI consumidoras:** GD-UI-0007 (selector canal en radicado), GD-UI-0060 (admin canales — pendiente)
**Permiso requerido:** ninguno

#### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "codigo": "presencial",
      "nombre": "Presencial — Ventanilla Única",
      "descripcion": "Atención personal en counter",
      "requiere_punto_atencion": true,
      "estado": "activo"
    },
    {
      "id": "uuid",
      "codigo": "correo_postal",
      "nombre": "Correo postal certificado",
      "requiere_punto_atencion": false,
      "estado": "activo"
    }
  ]
}
```

---

### GET `/api/v1/gd/admin/calendarios`
**Tarea backend:** GD-API-0014
**Permiso requerido:** ninguno

#### Response 200
```json
{
  "calendario_default_id": "uuid",
  "items": [
    {
      "id": "uuid",
      "nombre": "Calendario hábil Colombia",
      "vigencia_anual": 2026,
      "festivos": ["2026-01-01", "2026-01-11", "..."],
      "dias_no_laborales": ["sabado", "domingo"]
    }
  ]
}
```

---

### GET/PATCH `/api/v1/gd/admin/parametros`
**Tarea backend:** GD-API-0015
**Tarea(s) UI consumidoras:** GD-UI-0061 (admin parámetros)
**Permiso requerido:** `PERM-USR-001`

#### GET Response 200
```json
{
  "items": [
    {
      "clave": "gd.archivo.tamano_max",
      "valor": "20971520",
      "tipo": "integer",
      "descripcion": "Tamaño máximo de anexo en bytes (20 MB default)",
      "vigente_desde": "2026-01-01T00:00:00.000Z",
      "vigente_hasta": null
    }
  ]
}
```

#### PATCH Request
```json
{
  "parametros": [
    { "clave": "gd.archivo.tamano_max", "valor": "52428800", "motivo": "Aumento por solicitud área documental" }
  ]
}
```

---

### GET `/api/v1/gd/admin/parametros/{clave}`
**Tarea backend:** GD-API-0015
**Permiso requerido:** ninguno

Retorna un parámetro individual incluyendo su historial de valores (para auditoría visible en la UI).

---

## 11. Consulta de eventos de auditoría

### GET `/api/v1/core/auditoria`
**Tarea backend:** GD-API-0115 (EP-019)
**Tarea(s) UI consumidoras:** GD-UI-0067 (vista auditor), GD-UI-0005 (`useGdAudit()` hook), GD-UI-0015 (timeline radicado), GD-UI-0022 (timeline PQRSD), todas las fichas
**Permiso requerido:** `PERM-AUD-001` para vista global; cualquier usuario para su propio historial; alcance dependencia para auditor de dependencia
**Evento emitido:** `gd.auditoria.consultada` (criticidad: media) — solo cuando se consulta info clasificada

#### Request (query)
- `dominio?: "core" | "app" | "gd" | "knowledge"` — filtrar por dominio emisor.
- `entidad_tipo?: string` — `radicado | pqrsd | documento | usuario | dependencia | periferico | ...`.
- `entidad_id?: UUID` — eventos de un recurso específico.
- `usuario_id?: UUID` — eventos de un usuario.
- `tipo_evento?: string` — uno o varios separados por coma.
- `criticidad?: "baja" | "media" | "alta" | "critica"` — filtro por nivel.
- `desde?: timestamp`, `hasta?: timestamp`.
- `q?: string` — búsqueda en justificación / mensaje.
- `limit?: int (default 50, max 200)`, `cursor?: string`.

#### Response 200
```json
{
  "items": [
    {
      "evento_auditoria_id": "uuid",
      "dominio": "gd",
      "tipo_evento": "gd.radicado.creado",
      "criticidad": "media",
      "fecha_hora": "2026-05-23T14:32:11.000Z",
      "actor_snapshot": {
        "usuario_id": "uuid",
        "nombre_completo": "Juan Carlos Pérez García",
        "rol_codigo": "gd.radicador",
        "rol_nombre": "Radicador VU",
        "dependencia_codigo": "VU-001",
        "dependencia_nombre": "Ventanilla Única",
        "cargo": "Auxiliar Administrativo"
      },
      "entidad_afectada": {
        "tipo": "radicado",
        "id": "uuid",
        "identificador_legible": "RAD-2026-001234"
      },
      "accion": "crear",
      "valor_anterior": null,
      "valor_nuevo": { "numero_radicado": "RAD-2026-001234", "canal_id": "uuid" },
      "justificacion": null,
      "request_metadata": {
        "ip": "10.0.0.123",
        "user_agent": "Mozilla/5.0 ...",
        "request_id": "req_xxxx"
      }
    }
  ],
  "pagina": { "siguiente_cursor": "...", "total_estimado": 1247, "limit_aplicado": 50 }
}
```

#### Errores específicos
- **403 `auditoria_alcance_excedido`** — el usuario intenta consultar eventos fuera de su alcance (ej. profesional consultando eventos de otra dependencia sin permiso).

---

### GET `/api/v1/core/auditoria/{evento_id}`
**Tarea backend:** GD-API-0115
**Permiso requerido:** mismo que el listado, validando alcance del evento específico

#### Response 200
Mismo shape que un item del listado pero con campos `detalles_jsonb` adicional (estructura completa del evento al momento de emisión).

---

### POST `/api/v1/core/auditoria/exportar?formato=csv|excel|pdf`
**Tarea backend:** GD-API-0115
**Tarea(s) UI consumidoras:** GD-UI-0067 (reporte auditor)
**Permiso requerido:** `PERM-AUD-007` + `PERM-REP-008`
**Evento emitido:** `gd.auditoria.exportada` (criticidad: alta)

#### Request
```json
{
  "filtros": { ... mismos query params de GET ... },
  "formato": "csv | excel | pdf",
  "incluir_metadata_request": false,
  "motivo": "Solicitud Contraloría — auditoría externa 2026"
}
```

#### Response 202 (procesamiento asíncrono)
```json
{
  "exportacion_id": "uuid",
  "estado": "procesando",
  "estimacion_segundos": 45,
  "url_descarga_polling": "/api/v1/core/auditoria/exportaciones/{exportacion_id}"
}
```

---

**Última actualización:** 2026-05-23
