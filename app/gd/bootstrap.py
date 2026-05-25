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
    roles_seeded = await _seed_system_roles(conn)

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
        'perfiles_creados': perfiles_creados,
        'asignaciones_creadas': asignaciones_creadas,
        'users_boostrapped': users_boostrapped,
    }


__all__ = [
    'bootstrap_gd_for_tenant',
]
