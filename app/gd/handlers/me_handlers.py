"""GD-API-0002 — Endpoint `GET /api/v1/gd/me`.

Extiende `GET /v1/me` del producto principal con los campos institucionales del
módulo GD: perfil, dependencia, cargo, roles vigentes (de `gd.asignacion_alcance`)
y permisos efectivos (resueltos vía `gd.security.get_permisos_efectivos`).

Documentado en docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md
sección 1.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from app.db.pool import get_db
from app.gd.schemas.identidad import (
    GdMeCargo,
    GdMeDependencia,
    GdMePerfilSection,
    GdMeResponse,
    GdMeRolVigente,
)
from app.gd.security import (
    GdPerfilContext,
    get_permisos_efectivos,
    require_gd_perfil,
)


router = APIRouter(tags=['gd:identidad'])


def _split_display_name(display_name: str) -> tuple[str, str]:
    """Separa un `display_name` ("Juan Carlos Pérez García") en (nombres, apellidos).

    Heurística simple: la última palabra es el primer apellido, todo lo demás
    son los nombres. Para nombres compuestos hispánicos típicos esto es
    razonable, pero no infalible. Casos edge (nombre de una sola palabra,
    apellidos compuestos con preposición) caen al fallback `('', display_name)`.

    Cuando EP-001 implemente captura granular en gd.perfil_usuario podremos
    leer nombres/apellidos directamente y deprecar este helper.
    """
    if not display_name or not display_name.strip():
        return ('', '')
    parts = display_name.strip().split()
    if len(parts) == 1:
        return (parts[0], '')
    # Heurística común CO: dos nombres + dos apellidos. Si hay 4+ palabras,
    # asumimos que las dos últimas son apellidos.
    if len(parts) >= 4:
        nombres = ' '.join(parts[:-2])
        apellidos = ' '.join(parts[-2:])
    else:
        nombres = ' '.join(parts[:-1])
        apellidos = parts[-1]
    return (nombres, apellidos)


@router.get(
    '/me',
    response_model=GdMeResponse,
    summary='Perfil del usuario actual en el módulo GD',
    description=(
        'Retorna el perfil institucional, roles vigentes y permisos efectivos del '
        'usuario autenticado en el tenant activo. Pre-requisito: el usuario debe '
        'tener gd.perfil_usuario.estado_gd=activo en el tenant (si no, 403 con '
        'code=gd_profile_missing_or_inactive).'
    ),
)
async def get_gd_me(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> GdMeResponse:
    """Implementación de `GET /api/v1/gd/me`."""
    # 1. Datos del usuario (de app.users)
    user_row = await conn.fetchrow(
        'select email, display_name from app.users where id = $1',
        perfil.user_id,
    )
    # user_row no puede ser None porque require_gd_perfil ya validó FK indirecta.
    email = user_row['email']
    nombres, apellidos = _split_display_name(user_row['display_name'])

    # 2. Sección perfil_gd (snapshot adicional del último_acceso desde la tabla)
    perfil_row = await conn.fetchrow(
        """
        select
            tipo_vinculacion,
            estado_gd,
            fecha_inicio_vinculacion,
            fecha_fin_vinculacion,
            ultimo_acceso
        from gd.perfil_usuario
        where id = $1
        """,
        perfil.perfil_id,
    )
    perfil_section = GdMePerfilSection(
        tipo_vinculacion=perfil_row['tipo_vinculacion'],
        estado_gd=perfil_row['estado_gd'],
        fecha_inicio_vinculacion=perfil_row['fecha_inicio_vinculacion'],
        fecha_fin_vinculacion=perfil_row['fecha_fin_vinculacion'],
        ultimo_acceso=perfil_row['ultimo_acceso'],
    )

    # 3. Dependencia y cargo actuales.
    # Desde el bloque 3 (GD-API-0012) `gd.dependencia` existe → hacemos JOIN
    # para traer código y nombre. Si el id está en perfil pero la fila no
    # existe (caso edge — FK validada pero borrada por soporte), devolvemos
    # solo el id sin enriquecer.
    dependencia_actual = None
    if perfil.dependencia_actual_id is not None:
        dep_row = await conn.fetchrow(
            'select codigo_organico, nombre from gd.dependencia where id = $1',
            perfil.dependencia_actual_id,
        )
        if dep_row is not None:
            dependencia_actual = GdMeDependencia(
                id=perfil.dependencia_actual_id,
                codigo=dep_row['codigo_organico'],
                nombre=dep_row['nombre'],
            )
        else:
            dependencia_actual = GdMeDependencia(id=perfil.dependencia_actual_id)

    cargo_actual = None
    if perfil.cargo_actual_id is not None:
        cargo_row = await conn.fetchrow(
            'select nombre from gd.cargo where id = $1', perfil.cargo_actual_id
        )
        if cargo_row is not None:
            cargo_actual = GdMeCargo(id=perfil.cargo_actual_id, nombre=cargo_row['nombre'])

    # 4. Roles GD vigentes (de gd.asignacion_alcance) + JOIN con gd.dependencia
    # para traer dependencia_nombre cuando aplique.
    rol_rows = await conn.fetch(
        """
        select
            aa.id              as asignacion_alcance_id,
            aa.rol_codigo,
            r.nombre           as rol_nombre,
            aa.dependencia_id,
            d.nombre           as dependencia_nombre,
            aa.alcance,
            aa.fecha_inicio,
            aa.fecha_fin
        from gd.asignacion_alcance aa
        join gd.rol r on r.codigo = aa.rol_codigo
        left join gd.dependencia d on d.id = aa.dependencia_id
        where aa.user_id = $1
          and aa.tenant_id = $2
          and aa.estado = 'activa'
          and (aa.fecha_fin is null or aa.fecha_fin >= current_date)
          and r.estado = 'activo'
        order by aa.fecha_inicio desc
        """,
        perfil.user_id,
        perfil.tenant_id,
    )
    roles_vigentes = [
        GdMeRolVigente(
            asignacion_alcance_id=row['asignacion_alcance_id'],
            rol_codigo=row['rol_codigo'],
            rol_nombre=row['rol_nombre'],
            dependencia_id=row['dependencia_id'],
            dependencia_nombre=row['dependencia_nombre'],
            alcance=row['alcance'],
            fecha_inicio=row['fecha_inicio'],
            fecha_fin=row['fecha_fin'],
        )
        for row in rol_rows
    ]

    # 5. Permisos efectivos (resolución de matriz rol↔permiso ∩ asignaciones).
    permisos_dict = await get_permisos_efectivos(
        conn, user_id=perfil.user_id, tenant_id=perfil.tenant_id
    )
    permisos_efectivos = sorted(permisos_dict.keys())

    # 6. Módulos activos de la organización.
    # Desde el bloque 3 (GD-API-0011.b) gd.organizacion_modulo_activacion existe.
    # Consultamos solo los activados. Si la organización no tiene fila para
    # un módulo, se asume false (no se incluye en la lista).
    modulos_rows = await conn.fetch(
        """
        select modulo_codigo
        from gd.organizacion_modulo_activacion
        where tenant_id = $1 and activado = true
        order by modulo_codigo
        """,
        perfil.tenant_id,
    )
    modulos_activos: list[str] = [r['modulo_codigo'] for r in modulos_rows]

    return GdMeResponse(
        user_id=perfil.user_id,
        email=email,
        nombres=nombres,
        apellidos=apellidos,
        perfil_gd=perfil_section,
        dependencia_actual=dependencia_actual,
        cargo_actual=cargo_actual,
        roles_gd_vigentes=roles_vigentes,
        permisos_efectivos=permisos_efectivos,
        modulos_activos_organizacion=modulos_activos,
    )


__all__ = ['router', 'get_gd_me']
