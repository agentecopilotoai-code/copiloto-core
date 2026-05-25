"""Bootstrap automático del módulo Gestión Documental para un tenant.

Se invoca desde el PATCH ``/v1/platform/tenant-modules/{tenant_id}/gestion_documental``
cuando el ``platform_owner`` activa el módulo. Reemplaza al script manual
``scripts/dev-local/asignar-rol-gd-admin.sql`` (dev-only) por un hook
estructural que corre dentro de la misma transacción del PATCH.

Responsabilidades (todas idempotentes):

1. **Seed de los 19 roles GD del sistema** en ``gd.rol`` (``es_sistema=true``).
   La tabla es global (sin RLS) — el seed es seguro de re-correr.

2. **Crear ``gd.perfil_usuario`` con ``estado_gd='activo'``** para cada
   miembro del tenant con rol producto ``owner`` o ``admin``
   (``app.user_tenant_roles``). Sin perfil GD, el frontend muestra
   "SIN ROL" porque ``GET /api/v1/gd/me`` devuelve perfil vacío.

3. **Asignar ``gd.admin_sistema`` con alcance ``global``** a esos mismos
   usuarios en ``gd.asignacion_alcance``. Es el rol más alto de GD
   (ROL-001 de la Matriz de Roles) — el equivalente "owner" del módulo.
   Sin esto el usuario entra al módulo sin permisos.

Diseño:
- Llamado DENTRO de la transacción del PATCH handler, que ya tiene
  ``set_config('app.support_mode', 'true', true)`` activo → RLS permite
  el INSERT cross-tenant que necesita el platform_owner.
- ``ON CONFLICT DO NOTHING`` / ``DO UPDATE`` en todos los INSERT — la
  función es segura de re-correr cuando se desactiva y reactiva el módulo.
- Devuelve un dict con counters útiles para audit/log.
"""
from __future__ import annotations

from typing import Final

import asyncpg


# Los 19 roles seed de GD (Matriz de Roles, PDF Doc 3). Sincronizar con
# scripts/dev-local/asignar-rol-gd-admin.sql y docs/gestion documental/
# MATRIZ_PERMISOS.md. `es_sistema=true` los protege de DELETE/UPDATE
# vía gate de UI (ningún rol con es_sistema=true puede borrarse).
_GD_SYSTEM_ROLES: Final[tuple[tuple[str, str, str], ...]] = (
    ('gd.admin_sistema', 'Administrador del Sistema',
     'Configura usuarios, roles, dependencias, parámetros institucionales'),
    ('gd.admin_seguridad', 'Administrador de Seguridad',
     'Gestiona política de contraseñas, sesiones, auditoría de seguridad'),
    ('gd.admin_documental', 'Administrador Documental',
     'Gestiona TRD/TVD, series, subseries, tipos documentales, expedientes'),
    ('gd.radicador', 'Radicador Ventanilla Única',
     'Crea radicados de entrada/salida, opera periféricos'),
    ('gd.coordinador_vu', 'Coordinador Ventanilla Única',
     'Supervisa cola VU, anulaciones, reasignaciones'),
    ('gd.admin_pqrsd', 'Administrador PQRSD',
     'Asigna PQRSD, monitorea términos, supervisa proceso'),
    ('gd.profesional', 'Profesional Responsable',
     'Gestiona PQRSD y correspondencia asignadas, proyecta respuestas'),
    ('gd.revisor', 'Revisor',
     'Revisa documentos antes de aprobación'),
    ('gd.jefe_dependencia', 'Jefe de Dependencia',
     'Aprueba documentos, reasigna dentro de su dependencia'),
    ('gd.secretario_dependencia', 'Secretario de Dependencia',
     'RW limitado en buzón de dependencia, correspondencia'),
    ('gd.usuario_dependencia', 'Usuario de Dependencia',
     'Acceso básico a su buzón y tareas asignadas'),
    ('gd.usuario_ci', 'Usuario Comunicación Interna',
     'Crea, envía, recibe correspondencia interna'),
    ('gd.usuario_radicacion_externa', 'Usuario Radicación Externa',
     'Crea correspondencia externa desde dependencia'),
    ('gd.firmante', 'Firmante Autorizado',
     'Firma electrónicamente documentos aprobados'),
    ('gd.usuario_consulta', 'Usuario Consulta',
     'Acceso solo-lectura a radicados/documentos/trazabilidad'),
    ('gd.auditor', 'Auditor',
     'Consulta eventos de auditoría + reportes auditables'),
    ('gd.admin_plantillas', 'Administrador de Plantillas',
     'CRUD de plantillas institucionales + versionamiento'),
    ('gd.agente_ia', 'Agente IA (identidad técnica)',
     'Identidad para llamadas IA — sin UI'),
    ('gd.robot_rpa', 'Robot RPA (identidad técnica)',
     'Identidad para integraciones RPA — sin UI'),
)


# Roles producto cuyos miembros reciben gd.admin_sistema automáticamente.
# `owner` y `admin` del tenant (app.user_tenant_roles) — los managers/agents
# no califican por default; un admin_sistema dentro de GD puede ampliar luego.
_TENANT_ROLES_FOR_AUTO_BOOTSTRAP: Final[tuple[str, ...]] = ('owner', 'admin')


# ─── Catálogo de permisos GD ────────────────────────────────────────────────
# Fuente: docs/gestion documental/MATRIZ_PERMISOS.md § 2.1 – 2.15.
# Cada tupla = (codigo, modulo, nombre, es_critico).
# `modulo` matchea con los keys de `_GD_MATRIZ_ROL_MODULO` abajo.
_GD_PERMISOS_CATALOGO: Final[tuple[tuple[str, str, str, bool], ...]] = (
    # § 2.1 identidad (PERM-USR-*)
    ('PERM-USR-001', 'identidad', 'Crear / configurar perfil de usuario GD', True),
    ('PERM-USR-002', 'identidad', 'Modificar atributos de perfil GD existente', False),
    ('PERM-USR-003', 'identidad', 'Reservado para futuro (estado MFA)', False),
    ('PERM-USR-004', 'identidad', 'Inactivar perfil GD', True),
    ('PERM-USR-005', 'identidad', 'Bloquear perfil GD', True),
    ('PERM-USR-006', 'identidad', 'Desbloquear perfil GD', True),
    ('PERM-USR-007', 'identidad', 'Retirar perfil GD (cierre definitivo)', True),
    ('PERM-USR-008', 'identidad', 'Suspender perfil GD temporalmente', True),
    ('PERM-USR-009', 'identidad', 'Reasignar tareas pendientes al inactivar', True),
    ('PERM-USR-010', 'identidad', 'Consultar perfiles de otros usuarios', False),
    ('PERM-USR-011', 'identidad', 'Asignar rol GD a un usuario', True),
    ('PERM-USR-012', 'identidad', 'Cerrar asignación de rol GD', True),
    # § 2.2 roles_catalogo (PERM-ROL-*)
    ('PERM-ROL-001', 'roles_catalogo', 'Consultar catálogo de roles y permisos', False),
    ('PERM-ROL-002', 'roles_catalogo', 'Crear rol custom (prefijo gd.)', True),
    ('PERM-ROL-003', 'roles_catalogo', 'Agregar permiso a la matriz de un rol', True),
    ('PERM-ROL-004', 'roles_catalogo', 'Revocar permiso de la matriz de un rol', True),
    ('PERM-ROL-005', 'roles_catalogo', 'Inactivar rol', True),
    ('PERM-ROL-006', 'roles_catalogo', 'Editar metadata de un rol (nombre, descripción)', False),
    ('PERM-ROL-007', 'roles_catalogo', 'Reservado para futuro (importación masiva)', False),
    # § 2.3 ventanilla (PERM-VU-*)
    ('PERM-VU-001', 'ventanilla', 'Crear radicado de entrada', False),
    ('PERM-VU-002', 'ventanilla', 'Crear radicado de salida', False),
    ('PERM-VU-003', 'ventanilla', 'Reservado', False),
    ('PERM-VU-004', 'ventanilla', 'Reservado', False),
    ('PERM-VU-005', 'ventanilla', 'Clasificar inicialmente un radicado', False),
    ('PERM-VU-006', 'ventanilla', 'Reclasificar radicado (con motivo)', True),
    ('PERM-VU-014', 'ventanilla', 'Corregir datos menores (asunto, descripción)', True),
    ('PERM-VU-015', 'ventanilla', 'Solicitar anulación de radicado', True),
    ('PERM-VU-016', 'ventanilla', 'Aprobar/rechazar anulación de radicado', True),
    ('PERM-VU-021', 'ventanilla', 'Radicación de contingencia (caída del sistema)', True),
    # § 2.4 pqrsd (PERM-PQRSD-*)
    ('PERM-PQRSD-006', 'pqrsd', 'Asignar PQRSD a dependencia', False),
    ('PERM-PQRSD-007', 'pqrsd', 'Asignar PQRSD a funcionario específico', False),
    ('PERM-PQRSD-008', 'pqrsd', 'Reasignar PQRSD', True),
    ('PERM-PQRSD-009', 'pqrsd', 'Proyectar respuesta a PQRSD', False),
    ('PERM-PQRSD-012', 'pqrsd', 'Enviar respuesta a revisión', False),
    ('PERM-PQRSD-013', 'pqrsd', 'Revisar respuesta (VB técnico/jurídico)', False),
    ('PERM-PQRSD-015', 'pqrsd', 'Aprobar respuesta', True),
    ('PERM-PQRSD-016', 'pqrsd', 'Marcar respuesta como lista para firma', False),
    ('PERM-PQRSD-017', 'pqrsd', 'Radicar salida de la respuesta', True),
    ('PERM-PQRSD-018', 'pqrsd', 'Enviar respuesta al ciudadano', True),
    ('PERM-PQRSD-019', 'pqrsd', 'Cerrar PQRSD', True),
    ('PERM-PQRSD-020', 'pqrsd', 'Reabrir PQRSD cerrada', True),
    ('PERM-PQRSD-021', 'pqrsd', 'Trasladar PQRSD por competencia', True),
    ('PERM-PQRSD-022', 'pqrsd', 'Solicitar información adicional al solicitante', False),
    ('PERM-PQRSD-023', 'pqrsd', 'Suspender/reanudar término PQRSD', True),
    # § 2.5 correspondencia_interna (PERM-CI-*)
    ('PERM-CI-001', 'correspondencia_interna', 'Crear correspondencia interna', False),
    ('PERM-CI-002', 'correspondencia_interna', 'Enviar correspondencia interna', False),
    ('PERM-CI-003', 'correspondencia_interna', 'Marcar correspondencia como leída', False),
    ('PERM-CI-004', 'correspondencia_interna', 'Responder correspondencia interna', False),
    ('PERM-CI-005', 'correspondencia_interna', 'Reenviar correspondencia interna', False),
    ('PERM-CI-010', 'correspondencia_interna', 'Anular correspondencia interna', True),
    # § 2.6 correspondencia_externa (PERM-CE-*)
    ('PERM-CE-001', 'correspondencia_externa', 'Consultar correspondencia externa recibida', False),
    ('PERM-CE-002', 'correspondencia_externa', 'Gestionar correspondencia externa recibida', False),
    ('PERM-CE-003', 'correspondencia_externa', 'Crear borrador de correspondencia externa de salida', False),
    ('PERM-CE-005', 'correspondencia_externa', 'Workflow revisar correspondencia externa', False),
    ('PERM-CE-006', 'correspondencia_externa', 'Workflow aprobar correspondencia externa', False),
    ('PERM-CE-007', 'correspondencia_externa', 'Workflow firmar correspondencia externa', False),
    ('PERM-CE-008', 'correspondencia_externa', 'Workflow radicar correspondencia externa', False),
    ('PERM-CE-009', 'correspondencia_externa', 'Workflow enviar correspondencia externa', False),
    ('PERM-CE-010', 'correspondencia_externa', 'Enviar correspondencia externa', True),
    ('PERM-CE-011', 'correspondencia_externa', 'Registrar soporte de envío', False),
    ('PERM-CE-013', 'correspondencia_externa', 'Anular correspondencia externa', True),
    # § 2.7 documentos (PERM-DOC-*)
    ('PERM-DOC-001', 'documentos', 'Re-extraer OCR / texto de un archivo', False),
    ('PERM-DOC-005', 'documentos', 'Cargar / crear documento', False),
    # § 2.8 firmas (PERM-FIR-*)
    ('PERM-FIR-001', 'firmas', 'Firmar electrónicamente', True),
    ('PERM-FIR-003', 'firmas', 'Registrar firma escaneada', False),
    ('PERM-FIR-004', 'firmas', 'Rechazar firma pendiente', False),
    ('PERM-FIR-005', 'firmas', 'Consultar evidencia de firma', False),
    # § 2.9 plantillas (PERM-PLA-*)
    ('PERM-PLA-001', 'plantillas', 'CRUD plantilla — crear', False),
    ('PERM-PLA-002', 'plantillas', 'CRUD plantilla — editar', False),
    ('PERM-PLA-003', 'plantillas', 'CRUD plantilla — nueva versión', False),
    ('PERM-PLA-004', 'plantillas', 'CRUD plantilla — activar versión', False),
    ('PERM-PLA-005', 'plantillas', 'CRUD plantilla — inactivar', False),
    ('PERM-PLA-006', 'plantillas', 'Asociar plantilla a dependencia', False),
    ('PERM-PLA-007', 'plantillas', 'Asociar plantilla a tipo de trámite', False),
    # § 2.10 trd_tvd (PERM-TRD-*)
    ('PERM-TRD-001', 'trd_tvd', 'CRUD TRD — versiones', False),
    ('PERM-TRD-002', 'trd_tvd', 'CRUD TRD — series', False),
    ('PERM-TRD-003', 'trd_tvd', 'CRUD TRD — subseries', False),
    ('PERM-TRD-004', 'trd_tvd', 'CRUD TRD — tipos documentales', False),
    ('PERM-TRD-005', 'trd_tvd', 'CRUD TVD — versiones', False),
    ('PERM-TRD-006', 'trd_tvd', 'CRUD TVD — disposiciones', False),
    ('PERM-TRD-007', 'trd_tvd', 'Activación TRD', False),
    ('PERM-TRD-008', 'trd_tvd', 'Activación TVD', False),
    ('PERM-TRD-009', 'trd_tvd', 'Asociación dependencia-código documental', False),
    ('PERM-TRD-010', 'trd_tvd', 'Inactivación TRD/TVD', False),
    ('PERM-TRD-011', 'trd_tvd', 'Clasificar documentos/radicados', False),
    ('PERM-TRD-012', 'trd_tvd', 'Vigencia TRD', False),
    ('PERM-TRD-013', 'trd_tvd', 'Vigencia TVD', False),
    # § 2.11 correo (PERM-COR-*)
    ('PERM-COR-001', 'correo', 'Configurar buzón institucional', False),
    ('PERM-COR-003', 'correo', 'Convertir correo importado a radicado', False),
    ('PERM-COR-004', 'correo', 'Asociar correo a radicado existente', False),
    # § 2.12 reportes (PERM-REP-*)
    ('PERM-REP-002', 'reportes', 'Reporte de radicados de contingencia', False),
    ('PERM-REP-004', 'reportes', 'Reportes Ventanilla Única', False),
    ('PERM-REP-006', 'reportes', 'Reportes PQRSD', False),
    ('PERM-REP-007', 'reportes', 'Reportes Correspondencia', False),
    ('PERM-REP-008', 'reportes', 'Reportes Auditoría / exportación', True),
    ('PERM-REP-009', 'reportes', 'Carga de trabajo por usuario/dependencia', False),
    # § 2.13 auditoria (PERM-AUD-*)
    ('PERM-AUD-001', 'auditoria', 'Consultar eventos de auditoría globales', False),
    ('PERM-AUD-002', 'auditoria', 'Ver evidencia de firma con metadata completa', False),
    ('PERM-AUD-005', 'auditoria', 'Vista cruzada de uso de periféricos', False),
    ('PERM-AUD-007', 'auditoria', 'Exportar eventos de auditoría', True),
    # § 2.14 perifericos (PERM-PER-*)
    ('PERM-PER-001', 'perifericos', 'Configurar periférico', True),
    ('PERM-PER-002', 'perifericos', 'Activar/inactivar/retirar periférico', True),
    ('PERM-PER-003', 'perifericos', 'Imprimir etiqueta de radicado', False),
    ('PERM-PER-004', 'perifericos', 'Reimprimir etiqueta con motivo', True),
    ('PERM-PER-005', 'perifericos', 'Imprimir constancia de radicación', False),
    ('PERM-PER-006', 'perifericos', 'Digitalizar documento físico individual', False),
    ('PERM-PER-007', 'perifericos', 'Digitalizar lote documental', False),
    ('PERM-PER-008', 'perifericos', 'Asociar digitalización huérfana a radicado', False),
    ('PERM-PER-009', 'perifericos', 'Reemplazar digitalización con justificación', True),
    ('PERM-PER-010', 'perifericos', 'Consultar historial de periféricos propios', False),
    ('PERM-PER-011', 'perifericos', 'Consultar fallos / historial global de periféricos', False),
    ('PERM-PER-012', 'perifericos', 'Registrar mantenimiento de periférico', True),
    # § 2.15 notificaciones (PERM-NOT-*)
    ('PERM-NOT-001', 'notificaciones', 'Consultar notificaciones', False),
    ('PERM-NOT-002', 'notificaciones', 'Marcar notificación leída', False),
    ('PERM-NOT-003', 'notificaciones', 'Reservado', False),
    ('PERM-NOT-004', 'notificaciones', 'Reservado', False),
    ('PERM-NOT-005', 'notificaciones', 'Configurar notificaciones', False),
    ('PERM-NOT-006', 'notificaciones', 'Escalar alerta crítica al jefe', False),
    ('PERM-NOT-007', 'notificaciones', 'Configurar preferencias de notificación', False),
)


# ─── Matriz Rol × Módulo ────────────────────────────────────────────────────
# Fuente: docs/gestion documental/MATRIZ_PERMISOS.md § 3.
# - 'C' = uso administrativo (alcance_default 'institucional')
# - 'S' = uso operativo (alcance_default 'dependencia')
# - 'N' = sin acceso (no se inserta fila)
#
# La granularidad fina (qué permiso específico de cada módulo recibe el rol)
# se materializa en `_seed_matriz_rol_permiso` aplicando: para cada par
# (rol, módulo) con C o S, insertar TODOS los permisos de ese módulo con
# el alcance_default correspondiente.
_GD_MATRIZ_ROL_MODULO: Final[dict[str, dict[str, str]]] = {
    'gd.admin_sistema': {
        'identidad': 'C', 'roles_catalogo': 'C', 'ventanilla': 'C',
        'pqrsd': 'C', 'correspondencia_interna': 'C',
        'correspondencia_externa': 'C', 'documentos': 'C', 'firmas': 'C',
        'plantillas': 'C', 'trd_tvd': 'C', 'correo': 'C',
        'reportes': 'C', 'auditoria': 'C', 'perifericos': 'C',
        'notificaciones': 'C',
    },
    'gd.admin_seguridad': {
        'identidad': 'C', 'roles_catalogo': 'C', 'auditoria': 'S',
        'notificaciones': 'C',
    },
    'gd.admin_documental': {
        'documentos': 'C', 'trd_tvd': 'C', 'reportes': 'C', 'auditoria': 'S',
    },
    'gd.radicador': {
        'ventanilla': 'S', 'reportes': 'S', 'perifericos': 'S',
        'notificaciones': 'S',
    },
    'gd.coordinador_vu': {
        'ventanilla': 'S', 'reportes': 'S', 'perifericos': 'S',
        'notificaciones': 'S',
    },
    'gd.admin_pqrsd': {
        'pqrsd': 'S', 'reportes': 'S', 'notificaciones': 'S',
    },
    'gd.profesional': {
        'pqrsd': 'S', 'correspondencia_interna': 'S',
        'correspondencia_externa': 'S', 'documentos': 'S', 'firmas': 'S',
        'notificaciones': 'S',
    },
    'gd.revisor': {
        'pqrsd': 'S', 'correspondencia_interna': 'S',
        'correspondencia_externa': 'S', 'documentos': 'S',
        'notificaciones': 'S',
    },
    'gd.jefe_dependencia': {
        'pqrsd': 'S', 'correspondencia_interna': 'S',
        'correspondencia_externa': 'S', 'documentos': 'S', 'firmas': 'S',
        'reportes': 'S', 'notificaciones': 'S',
    },
    'gd.secretario_dependencia': {
        'correspondencia_interna': 'S', 'correspondencia_externa': 'S',
        'documentos': 'S', 'notificaciones': 'S',
    },
    'gd.usuario_dependencia': {
        'notificaciones': 'S',
    },
    'gd.usuario_ci': {
        'correspondencia_interna': 'S', 'documentos': 'S',
        'notificaciones': 'S',
    },
    'gd.usuario_radicacion_externa': {
        'correspondencia_externa': 'S', 'documentos': 'S',
        'notificaciones': 'S',
    },
    'gd.firmante': {
        'firmas': 'S', 'notificaciones': 'S',
    },
    'gd.usuario_consulta': {
        'ventanilla': 'S', 'pqrsd': 'S', 'correspondencia_interna': 'S',
        'correspondencia_externa': 'S', 'documentos': 'S',
        'notificaciones': 'S',
    },
    'gd.auditor': {
        'reportes': 'S', 'auditoria': 'S', 'perifericos': 'S',
        'notificaciones': 'S',
    },
    'gd.admin_plantillas': {
        'plantillas': 'C', 'notificaciones': 'S',
    },
    # Roles técnicos: SIN permisos UI (operan via service tokens / identidad técnica).
    'gd.agente_ia': {},
    'gd.robot_rpa': {},
}

# Mapeo C/S → alcance_default según la guía del doc.
_USO_TO_ALCANCE: Final[dict[str, str]] = {
    'C': 'institucional',   # uso administrativo (configura)
    'S': 'dependencia',     # uso operativo (opera dentro de su dependencia)
}


async def _seed_system_roles(conn: asyncpg.Connection) -> int:
    """INSERT idempotente de los 19 roles GD del sistema.

    Devuelve la cantidad de filas insertadas (0 si ya existían todos).
    """
    rows_inserted = 0
    for codigo, nombre, descripcion in _GD_SYSTEM_ROLES:
        status = await conn.execute(
            '''
            insert into gd.rol (codigo, nombre, descripcion, es_sistema, estado)
            values ($1, $2, $3, true, 'activo')
            on conflict (codigo) do nothing
            ''',
            codigo, nombre, descripcion,
        )
        # asyncpg devuelve 'INSERT 0 N' donde N es la cantidad de filas afectadas.
        if status.endswith(' 1'):
            rows_inserted += 1
    return rows_inserted


async def _seed_permisos_catalogo(conn: asyncpg.Connection) -> int:
    """INSERT idempotente de los 98 permisos del catálogo GD.

    Fuente: `docs/gestion documental/MATRIZ_PERMISOS.md` § 2.
    Tabla global (sin RLS) — seguro de re-correr.

    Devuelve la cantidad de filas insertadas (0 si todos ya existían).
    """
    rows_inserted = 0
    for codigo, modulo, nombre, es_critico in _GD_PERMISOS_CATALOGO:
        status = await conn.execute(
            '''
            insert into gd.permiso (codigo, nombre, modulo, es_critico, estado)
            values ($1, $2, $3, $4, 'activo')
            on conflict (codigo) do nothing
            ''',
            codigo, nombre, modulo, es_critico,
        )
        if status.endswith(' 1'):
            rows_inserted += 1
    return rows_inserted


async def _seed_matriz_rol_permiso(conn: asyncpg.Connection) -> int:
    """INSERT idempotente de la matriz `gd.rol_permiso`.

    Para cada par (rol, módulo) con C o S en `_GD_MATRIZ_ROL_MODULO`:
    - Si C → alcance_default='institucional' (uso administrativo).
    - Si S → alcance_default='dependencia' (uso operativo).
    Se asigna TODOS los permisos del módulo al rol con ese alcance.

    Idempotente: ON CONFLICT DO NOTHING contra la unique (rol_codigo, permiso_codigo).

    Devuelve la cantidad de filas insertadas (0 si la matriz ya estaba completa).
    """
    # Indexa permisos por módulo para iterar eficiente.
    permisos_por_modulo: dict[str, list[str]] = {}
    for codigo, modulo, _nombre, _critico in _GD_PERMISOS_CATALOGO:
        permisos_por_modulo.setdefault(modulo, []).append(codigo)

    rows_inserted = 0
    for rol_codigo, matriz_rol in _GD_MATRIZ_ROL_MODULO.items():
        for modulo, uso in matriz_rol.items():
            alcance_default = _USO_TO_ALCANCE.get(uso)
            if alcance_default is None:
                continue  # 'N' = sin acceso, no insertamos
            permisos_modulo = permisos_por_modulo.get(modulo, [])
            for permiso_codigo in permisos_modulo:
                status = await conn.execute(
                    '''
                    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default, estado)
                    values ($1, $2, $3, 'activo')
                    on conflict (rol_codigo, permiso_codigo) do nothing
                    ''',
                    rol_codigo, permiso_codigo, alcance_default,
                )
                if status.endswith(' 1'):
                    rows_inserted += 1
    return rows_inserted


async def _list_tenant_owners(
    conn: asyncpg.Connection,
    tenant_id: str,
) -> list[asyncpg.Record]:
    """Lista usuarios del tenant con rol producto owner|admin."""
    return await conn.fetch(
        '''
        select distinct u.id as user_id, u.email, u.display_name
        from app.user_tenant_roles utr
        join app.users u on u.id = utr.user_id
        where utr.tenant_id = $1
          and utr.role = any($2)
        ''',
        tenant_id,
        list(_TENANT_ROLES_FOR_AUTO_BOOTSTRAP),
    )


async def _ensure_perfil_usuario(
    conn: asyncpg.Connection,
    tenant_id: str,
    user_id: str,
    created_by_user_id: str | None,
) -> bool:
    """Crea perfil_usuario (estado_gd=activo) o reactiva si existía suspendido.

    Devuelve True si creó nuevo, False si solo actualizó.
    """
    # tipo_vinculacion='planta' como default — el admin_sistema puede
    # cambiarlo después desde el UI de AdminUsuarios.
    row = await conn.fetchrow(
        '''
        insert into gd.perfil_usuario (
          tenant_id, user_id,
          tipo_vinculacion, estado_gd,
          fecha_inicio_vinculacion,
          created_by_user_id
        )
        values ($1, $2, 'planta', 'activo', current_date, $3)
        on conflict (tenant_id, user_id) do update
          set estado_gd = case
                when gd.perfil_usuario.estado_gd = 'retirado' then 'retirado'
                else 'activo'
              end,
              updated_at = now()
        returning (xmax = 0) as created
        ''',
        tenant_id, user_id, created_by_user_id,
    )
    return bool(row and row['created'])


async def _ensure_admin_sistema_assignment(
    conn: asyncpg.Connection,
    tenant_id: str,
    user_id: str,
    asignado_por_user_id: str | None,
) -> bool:
    """Asegura que el usuario tenga gd.admin_sistema activo con alcance global.

    Devuelve True si insertó nueva asignación, False si ya existía activa.
    """
    # Verifica si ya hay una asignación activa de este rol para este user.
    existing = await conn.fetchrow(
        '''
        select id from gd.asignacion_alcance
        where tenant_id = $1 and user_id = $2
          and rol_codigo = 'gd.admin_sistema'
          and estado = 'activa'
          and alcance = 'global'
        limit 1
        ''',
        tenant_id, user_id,
    )
    if existing is not None:
        return False

    await conn.execute(
        '''
        insert into gd.asignacion_alcance (
          tenant_id, user_id, rol_codigo,
          alcance, fecha_inicio, estado, motivo,
          asignado_por_user_id
        )
        values (
          $1, $2, 'gd.admin_sistema',
          'global', current_date, 'activa',
          'Bootstrap automático al activar módulo Gestión Documental',
          $3
        )
        ''',
        tenant_id, user_id, asignado_por_user_id,
    )
    return True


async def bootstrap_gd_for_tenant(
    conn: asyncpg.Connection,
    tenant_id: str,
    actor_user_id: str | None,
) -> dict[str, int | list[str]]:
    """Ejecuta el bootstrap completo del módulo GD para un tenant.

    DEBE invocarse DENTRO de una transacción que ya tenga
    ``app.support_mode='true'`` activo (lo hace el PATCH handler).

    Args:
        conn: conexión asyncpg dentro de una transacción.
        tenant_id: UUID del tenant que activó el módulo.
        actor_user_id: UUID del platform_owner que ejecutó el PATCH
            (queda en ``created_by_user_id`` / ``asignado_por_user_id``
            como traza). Puede ser ``None`` si la activación viene de
            un proceso sistema (ej. seed).

    Returns:
        Dict con métricas para incluir en el audit log:
        ``{roles_seeded, perfiles_creados, asignaciones_creadas,
        users_boostrapped: [user_id, ...]}``
    """
    # 1. Catálogo de roles (19 filas en gd.rol)
    roles_seeded = await _seed_system_roles(conn)
    # 2. Catálogo de permisos (98 filas en gd.permiso)
    permisos_seeded = await _seed_permisos_catalogo(conn)
    # 3. Matriz rol×permiso (~500 filas en gd.rol_permiso) — el chequeo
    #    `require_gd_permission` la consulta para decidir 200 vs 403.
    matriz_seeded = await _seed_matriz_rol_permiso(conn)

    owners = await _list_tenant_owners(conn, tenant_id)
    target_user_ids: list[str] = [str(o['user_id']) for o in owners]

    # CRITICAL — incluir al actor del PATCH (platform_owner haciendo
    # support_mode). Sin esto, cuando un platform_owner activa GD para
    # un tenant en el que NO es miembro (caso normal de support_mode),
    # el bootstrap no le crea perfil y al entrar al módulo ve "SIN ROL".
    # Idempotente: si ya estaba en `owners` (raro), el ensure_* no
    # duplica. Solo agrego si actor_user_id NO está vacío y NO está ya
    # en la lista.
    if actor_user_id and actor_user_id not in target_user_ids:
        # Verifica que el actor exista en app.users (defensa contra UUIDs
        # bogus). Si no existe, lo omito sin fallar el bootstrap.
        actor_exists = await conn.fetchrow(
            'select 1 from app.users where id = $1', actor_user_id,
        )
        if actor_exists is not None:
            target_user_ids.append(actor_user_id)

    perfiles_creados = 0
    asignaciones_creadas = 0
    users_boostrapped: list[str] = []

    for user_id in target_user_ids:
        created_perfil = await _ensure_perfil_usuario(
            conn, tenant_id, user_id, actor_user_id,
        )
        if created_perfil:
            perfiles_creados += 1
        created_asig = await _ensure_admin_sistema_assignment(
            conn, tenant_id, user_id, actor_user_id,
        )
        if created_asig:
            asignaciones_creadas += 1
        users_boostrapped.append(user_id)

    return {
        'roles_seeded': roles_seeded,
        'permisos_seeded': permisos_seeded,
        'matriz_seeded': matriz_seeded,
        'perfiles_creados': perfiles_creados,
        'asignaciones_creadas': asignaciones_creadas,
        'users_boostrapped': users_boostrapped,
    }


__all__ = [
    'bootstrap_gd_for_tenant',
]
