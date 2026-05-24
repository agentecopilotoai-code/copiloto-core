# Matriz de Roles × Permisos — Módulo Gestión Documental

> **Generado por GD-API-0010** (RNF-051).
> Traducción navegable del PDF [`source-documents/03-matriz-roles-permisos-funciones-v0.1.pdf`](source-documents/03-matriz-roles-permisos-funciones-v0.1.pdf) + extensiones del Doc 6 (Periféricos).
>
> Convenciones de celda:
> - **S** = el rol tiene el permiso por default (alcance ver columna lateral del rol).
> - **N** = el rol NO tiene el permiso.
> - **C** = el rol puede CONFIGURAR el permiso (ej. el Admin Sistema puede otorgárselo a otros roles vía endpoint).
>
> Esta matriz refleja el **seed inicial** del módulo (`gd.rol_permiso`). Cada organización puede luego editar la matriz vía endpoints `POST /api/v1/gd/roles/{codigo}/permisos` y `DELETE /api/v1/gd/roles/{codigo}/permisos/{permiso_codigo}` (PERM-ROL-003 / PERM-ROL-004).
>
> Estado de implementación: el seed real vive en `infra/postgres/05-gd-seed.sql` (pendiente — se genera en bloque posterior cuando completemos catálogos institucionales).

## 1. Catálogo de roles (`gd.rol`)

19 roles del sistema (`es_sistema=true`). Codificados con prefijo `gd.` para no chocar con los roles del producto principal (`owner`, `admin`, `agent`, etc.).

| Código | Nombre | Descripción funcional | Doc 3 |
|---|---|---|---|
| `gd.admin_sistema` | Administrador del Sistema | Configura usuarios, roles, dependencias, parámetros institucionales | ROL-001 |
| `gd.admin_seguridad` | Administrador de Seguridad | Gestiona política de contraseñas, sesiones, auditoría de seguridad | ROL-002 |
| `gd.admin_documental` | Administrador Documental | Gestiona TRD/TVD, series, subseries, tipos documentales, expedientes | ROL-003 |
| `gd.radicador` | Radicador Ventanilla Única | Crea radicados de entrada/salida, opera periféricos | ROL-004 |
| `gd.coordinador_vu` | Coordinador Ventanilla Única | Supervisa cola VU, anulaciones, reasignaciones | ROL-005 |
| `gd.admin_pqrsd` | Administrador PQRSD | Asigna PQRSD, monitorea términos, supervisa proceso | ROL-006 |
| `gd.profesional` | Profesional Responsable | Gestiona PQRSD y correspondencia asignadas, proyecta respuestas | ROL-007 |
| `gd.revisor` | Revisor | Revisa documentos antes de aprobación (visto bueno técnico/jurídico) | ROL-008 |
| `gd.jefe_dependencia` | Jefe de Dependencia | Aprueba documentos, reasigna dentro de su dependencia | ROL-009 |
| `gd.secretario_dependencia` | Secretario de Dependencia | RW limitado en buzón de dependencia, correspondencia | ROL-010 |
| `gd.usuario_dependencia` | Usuario de Dependencia | Acceso básico a su buzón y tareas asignadas | ROL-011 |
| `gd.usuario_ci` | Usuario Comunicación Interna | Crea, envía, recibe correspondencia interna | ROL-012 |
| `gd.usuario_radicacion_externa` | Usuario Radicación Externa | Crea correspondencia externa desde dependencia | ROL-013 |
| `gd.firmante` | Firmante Autorizado | Firma electrónicamente documentos aprobados | ROL-014 |
| `gd.usuario_consulta` | Usuario Consulta | Acceso solo-lectura a radicados/documentos/trazabilidad | ROL-015 |
| `gd.auditor` | Auditor | Consulta eventos de auditoría + reportes auditables | ROL-016 |
| `gd.admin_plantillas` | Administrador de Plantillas | CRUD de plantillas institucionales + versionamiento | ROL-017 |
| `gd.agente_ia` | Agente IA (identidad técnica) | Identidad para llamadas IA — sin UI | ROL-018 |
| `gd.robot_rpa` | Robot RPA (identidad técnica) | Identidad para integraciones RPA — sin UI | ROL-019 |

## 2. Catálogo de permisos (`gd.permiso`)

~152 permisos agrupados por módulo. Los marcados con ⚠️ son **críticos** (`es_critico=true`) y se auditan en `core.evento_auditoria` con criticidad `alta` o `critica`.

### 2.1 Módulo `identidad` (PERM-USR-*)

| Código | Función | ⚠️ |
|---|---|---|
| PERM-USR-001 | Crear / configurar perfil de usuario GD | ⚠️ |
| PERM-USR-002 | Modificar atributos de perfil GD existente | |
| PERM-USR-003 | Reservado para futuro (estado MFA) | |
| PERM-USR-004 | Inactivar perfil GD | ⚠️ |
| PERM-USR-005 | Bloquear perfil GD | ⚠️ |
| PERM-USR-006 | Desbloquear perfil GD | ⚠️ |
| PERM-USR-007 | Retirar perfil GD (cierre definitivo) | ⚠️ |
| PERM-USR-008 | Suspender perfil GD temporalmente | ⚠️ |
| PERM-USR-009 | Reasignar tareas pendientes al inactivar | ⚠️ |
| PERM-USR-010 | Consultar perfiles de otros usuarios | |
| PERM-USR-011 | Asignar rol GD a un usuario | ⚠️ |
| PERM-USR-012 | Cerrar asignación de rol GD | ⚠️ |

### 2.2 Módulo `roles_catalogo` (PERM-ROL-*)

| Código | Función | ⚠️ |
|---|---|---|
| PERM-ROL-001 | Consultar catálogo de roles y permisos | |
| PERM-ROL-002 | Crear rol custom (prefijo `gd.`) | ⚠️ |
| PERM-ROL-003 | Agregar permiso a la matriz de un rol | ⚠️ |
| PERM-ROL-004 | Revocar permiso de la matriz de un rol | ⚠️ |
| PERM-ROL-005 | Inactivar rol | ⚠️ |
| PERM-ROL-006 | Editar metadata de un rol (nombre, descripción) | |
| PERM-ROL-007 | Reservado para futuro (importación masiva) | |

### 2.3 Módulo `ventanilla` (PERM-VU-*)

| Código | Función | ⚠️ |
|---|---|---|
| PERM-VU-001 | Crear radicado de entrada | |
| PERM-VU-002 | Crear radicado de salida | |
| PERM-VU-003 | Reservado | |
| PERM-VU-004 | Reservado | |
| PERM-VU-005 | Clasificar inicialmente un radicado | |
| PERM-VU-006 | Reclasificar radicado (con motivo) | ⚠️ |
| PERM-VU-014 | Corregir datos menores (asunto, descripción) | ⚠️ |
| PERM-VU-015 | Solicitar anulación de radicado | ⚠️ |
| PERM-VU-016 | Aprobar/rechazar anulación de radicado | ⚠️ |
| PERM-VU-021 | Radicación de contingencia (caída del sistema) | ⚠️ |

### 2.4 Módulo `pqrsd` (PERM-PQRSD-*)

| Código | Función | ⚠️ |
|---|---|---|
| PERM-PQRSD-001..005 | Reservados | |
| PERM-PQRSD-006 | Asignar PQRSD a dependencia | |
| PERM-PQRSD-007 | Asignar PQRSD a funcionario específico | |
| PERM-PQRSD-008 | Reasignar PQRSD | ⚠️ |
| PERM-PQRSD-009 | Proyectar respuesta a PQRSD | |
| PERM-PQRSD-012 | Enviar respuesta a revisión | |
| PERM-PQRSD-013 | Revisar respuesta (VB técnico/jurídico) | |
| PERM-PQRSD-015 | Aprobar respuesta | ⚠️ |
| PERM-PQRSD-016 | Marcar respuesta como lista para firma | |
| PERM-PQRSD-017 | Radicar salida de la respuesta | ⚠️ |
| PERM-PQRSD-018 | Enviar respuesta al ciudadano | ⚠️ |
| PERM-PQRSD-019 | Cerrar PQRSD | ⚠️ |
| PERM-PQRSD-020 | Reabrir PQRSD cerrada | ⚠️ |
| PERM-PQRSD-021 | Trasladar PQRSD por competencia | ⚠️ |
| PERM-PQRSD-022 | Solicitar información adicional al solicitante | |
| PERM-PQRSD-023 | Suspender/reanudar término PQRSD | ⚠️ |

### 2.5 Módulo `correspondencia_interna` (PERM-CI-*)

| Código | Función |
|---|---|
| PERM-CI-001 | Crear correspondencia interna |
| PERM-CI-002 | Enviar correspondencia interna |
| PERM-CI-003 | Marcar correspondencia como leída |
| PERM-CI-004 | Responder correspondencia interna |
| PERM-CI-005 | Reenviar correspondencia interna |
| PERM-CI-010 | Anular correspondencia interna ⚠️ |

### 2.6 Módulo `correspondencia_externa` (PERM-CE-*)

| Código | Función |
|---|---|
| PERM-CE-001 | Consultar correspondencia externa recibida |
| PERM-CE-002 | Gestionar correspondencia externa recibida |
| PERM-CE-003 | Crear borrador de correspondencia externa de salida |
| PERM-CE-005..009 | Workflow revisar/aprobar/firmar/radicar/enviar |
| PERM-CE-010 | Enviar correspondencia externa ⚠️ |
| PERM-CE-011 | Registrar soporte de envío |
| PERM-CE-013 | Anular correspondencia externa ⚠️ |

### 2.7 Módulo `documentos` (PERM-DOC-*)

| Código | Función |
|---|---|
| PERM-DOC-001 | Re-extraer OCR / texto de un archivo |
| PERM-DOC-005 | Cargar / crear documento |

### 2.8 Módulo `firmas` (PERM-FIR-*)

| Código | Función |
|---|---|
| PERM-FIR-001 | Firmar electrónicamente ⚠️ |
| PERM-FIR-003 | Registrar firma escaneada |
| PERM-FIR-004 | Rechazar firma pendiente |
| PERM-FIR-005 | Consultar evidencia de firma |

### 2.9 Módulo `plantillas` (PERM-PLA-*)

| Código | Función |
|---|---|
| PERM-PLA-001..005 | CRUD plantilla + versionamiento |
| PERM-PLA-006 | Asociar plantilla ↔ dependencia |
| PERM-PLA-007 | Asociar plantilla ↔ tipo de trámite |

### 2.10 Módulo `trd_tvd` (PERM-TRD-*)

| Código | Función |
|---|---|
| PERM-TRD-001..010 | CRUD TRD/TVD + versiones + activación |
| PERM-TRD-011 | Clasificar documentos/radicados |
| PERM-TRD-012..013 | Vigencias TRD/TVD |

### 2.11 Módulo `correo` (PERM-COR-*)

| Código | Función |
|---|---|
| PERM-COR-001 | Configurar buzón institucional |
| PERM-COR-003 | Convertir correo importado a radicado |
| PERM-COR-004 | Asociar correo a radicado existente |

### 2.12 Módulo `reportes` (PERM-REP-*)

| Código | Función |
|---|---|
| PERM-REP-002 | Reporte de radicados de contingencia |
| PERM-REP-004 | Reportes Ventanilla Única |
| PERM-REP-006 | Reportes PQRSD |
| PERM-REP-007 | Reportes Correspondencia |
| PERM-REP-008 | Reportes Auditoría / exportación ⚠️ |
| PERM-REP-009 | Carga de trabajo por usuario/dependencia |

### 2.13 Módulo `auditoria` (PERM-AUD-*)

| Código | Función |
|---|---|
| PERM-AUD-001 | Consultar eventos de auditoría globales |
| PERM-AUD-002 | Ver evidencia de firma con metadata completa |
| PERM-AUD-005 | Vista cruzada de uso de periféricos |
| PERM-AUD-007 | Exportar eventos de auditoría ⚠️ |

### 2.14 Módulo `perifericos` (PERM-PER-*) — Doc 6 nuevo

| Código | Función | ⚠️ |
|---|---|---|
| PERM-PER-001 | Configurar periférico | ⚠️ |
| PERM-PER-002 | Activar/inactivar/retirar periférico | ⚠️ |
| PERM-PER-003 | Imprimir etiqueta de radicado | |
| PERM-PER-004 | Reimprimir etiqueta con motivo | ⚠️ |
| PERM-PER-005 | Imprimir constancia de radicación | |
| PERM-PER-006 | Digitalizar documento físico individual | |
| PERM-PER-007 | Digitalizar lote documental | |
| PERM-PER-008 | Asociar digitalización huérfana a radicado | |
| PERM-PER-009 | Reemplazar digitalización con justificación | ⚠️ |
| PERM-PER-010 | Consultar historial de periféricos propios | |
| PERM-PER-011 | Consultar fallos / historial global de periféricos | |
| PERM-PER-012 | Registrar mantenimiento de periférico | ⚠️ |

### 2.15 Módulo `notificaciones` (PERM-NOT-*)

| Código | Función |
|---|---|
| PERM-NOT-001..005 | Consultar/marcar/configurar notificaciones |
| PERM-NOT-006 | Escalar alerta crítica al jefe |
| PERM-NOT-007 | Configurar preferencias de notificación |

## 3. Matriz Rol × Módulo (resumen)

Esta tabla resume qué módulos toca cada rol. La granularidad fina (permiso por permiso) se materializa en `gd.rol_permiso` durante el seed (bloque futuro).

| Rol \ Módulo | Identidad | Roles | VU | PQRSD | CI | CE | Doc | Firmas | Plant | TRD | Correo | Rep | Audit | Periféricos | Notif |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Admin Sistema | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| Admin Seguridad | C | C | N | N | N | N | N | N | N | N | N | N | S | N | C |
| Admin Documental | N | N | N | N | N | N | C | N | N | C | N | C | S | N | N |
| Radicador VU | N | N | S | N | N | N | N | N | N | N | N | S | N | S | S |
| Coordinador VU | N | N | S | N | N | N | N | N | N | N | N | S | N | S | S |
| Admin PQRSD | N | N | N | S | N | N | N | N | N | N | N | S | N | N | S |
| Profesional | N | N | N | S | S | S | S | S | N | N | N | N | N | N | S |
| Revisor | N | N | N | S | S | S | S | N | N | N | N | N | N | N | S |
| Jefe Dependencia | N | N | N | S | S | S | S | S | N | N | N | S | N | N | S |
| Secretario Dep | N | N | N | N | S | S | S | N | N | N | N | N | N | N | S |
| Usuario Dep | N | N | N | N | N | N | N | N | N | N | N | N | N | N | S |
| Usuario CI | N | N | N | N | S | N | S | N | N | N | N | N | N | N | S |
| Usuario Radic Ext | N | N | N | N | N | S | S | N | N | N | N | N | N | N | S |
| Firmante | N | N | N | N | N | N | N | S | N | N | N | N | N | N | S |
| Usuario Consulta | N | N | S | S | S | S | S | N | N | N | N | N | N | N | S |
| Auditor | N | N | N | N | N | N | N | N | N | N | N | S | S | S | S |
| Admin Plantillas | N | N | N | N | N | N | N | N | C | N | N | N | N | N | S |
| Agente IA | N | N | N | N | N | N | N | N | N | N | N | N | N | N | N |
| Robot RPA | N | N | N | N | N | N | N | N | N | N | N | N | N | N | N |

> **Leyenda:** S = uso operativo, C = uso administrativo (configura/edita), N = sin acceso.
> Los roles técnicos (Agente IA, Robot RPA) tienen permisos específicos vía identidad técnica + endpoints dedicados (PERM-USR-001 restringido, GD-API-0105).

## 4. Reglas especiales de seguridad (Doc 3 § 11)

1. **Separación de funciones (RNF-008):** quien proyecta una respuesta no puede firmarla. Quien solicita una anulación no puede aprobarla. Validado en handlers con check explícito.
2. **Permisos críticos exigen MFA:** los permisos marcados ⚠️ pueden requerir step-up MFA si la sesión es > 30 min. (Implementación pendiente — depende de integración con `require_mfa_for_privileged` del producto principal.)
3. **Alcance siempre default = mínimo:** asignar un rol con alcance `global` requiere `PERM-ROL-003` adicional + justificación auditada.
4. **`gd.rol_permiso` editable pero auditado:** cada agregar/revocar permiso emite evento `gd.rol_permiso.modificado` con criticidad `alta`.

## 5. Roadmap de seed real

El seed completo (`infra/postgres/05-gd-seed.sql`) generará los INSERTs reales para los 19 roles + ~152 permisos + matriz inicial. Se implementa cuando el módulo necesite operación real (Entrega 1 productiva). Hasta entonces, los tests instancian los roles/permisos vía fixtures que reflejan esta matriz.

---

**Última actualización:** 2026-05-23 (bloque 3, GD-API-0010)
**Fuente:** Doc 3 (Matriz de Roles, Permisos y Funciones v0.1) + Doc 5-rev1 § 28 + Doc 6 (Periféricos)
