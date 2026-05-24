"""Tests para `app.gd.handlers.me_handlers.get_gd_me` con mocks de asyncpg.

Cubre la lógica completa del endpoint sin requerir DB real:
- Build del response con todos los campos opcionales presentes.
- Build del response con dependencia_actual y cargo_actual = None.
- Roles vigentes vacíos.
- Permisos efectivos vacíos.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.handlers.me_handlers import get_gd_me
from app.gd.security import GdPerfilContext


# Sentinel para distinguir "no se llama fetchrow para cargo" de "devuelve None".
_OMIT = object()


def _make_perfil_ctx(
    *, dependencia_id=None, cargo_id=None
) -> GdPerfilContext:
    return GdPerfilContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        perfil_id=uuid4(),
        tipo_vinculacion='planta',
        estado_gd='activo',
        dependencia_actual_id=dependencia_id,
        cargo_actual_id=cargo_id,
    )


def _make_conn_for_me(
    *,
    user_email='juan@ejemplo.com',
    user_display_name='Juan Carlos Pérez García',
    perfil_data: dict | None = None,
    dependencia_data=_OMIT,  # _OMIT = no se pide; None = se pide y devuelve None
    cargo_data=_OMIT,
    roles_data: list[dict] | None = None,
    permisos_data: list[dict] | None = None,
    modulos_data: list[dict] | None = None,
) -> AsyncMock:
    """Construye un mock de asyncpg.Connection que devuelve los rows esperados.

    `get_gd_me` hace varios fetchrow/fetch — uso side_effect en orden:
      1. fetchrow → app.users (email + display_name)
      2. fetchrow → gd.perfil_usuario detalle
      3. fetchrow → gd.dependencia JOIN (SOLO si dependencia_actual_id != None)
      4. fetchrow → gd.cargo (SOLO si cargo_actual_id != None)
      5. fetch → gd.asignacion_alcance + gd.rol + LEFT JOIN gd.dependencia
      6. fetch → matriz permisos via get_permisos_efectivos
      7. fetch → gd.organizacion_modulo_activacion (módulos activos)
    """
    conn = AsyncMock()
    perfil_default = {
        'tipo_vinculacion': 'planta',
        'estado_gd': 'activo',
        'fecha_inicio_vinculacion': date(2025, 1, 15),
        'fecha_fin_vinculacion': None,
        'ultimo_acceso': datetime(2026, 5, 23, 8, 11, 0),
    }
    fetchrow_results: list[dict | None] = [
        {'email': user_email, 'display_name': user_display_name},
        perfil_data or perfil_default,
    ]
    if dependencia_data is not _OMIT:
        fetchrow_results.append(dependencia_data)
    if cargo_data is not _OMIT:
        fetchrow_results.append(cargo_data)
    conn.fetchrow.side_effect = fetchrow_results

    conn.fetch.side_effect = [
        roles_data or [],
        permisos_data or [],
        modulos_data or [],
    ]
    return conn


class TestGetGdMe:
    @pytest.mark.asyncio
    async def test_response_minimo_sin_dependencia_ni_cargo(self) -> None:
        perfil = _make_perfil_ctx()
        conn = _make_conn_for_me()
        response = await get_gd_me(perfil, conn)
        assert response.email == 'juan@ejemplo.com'
        assert response.nombres == 'Juan Carlos'
        assert response.apellidos == 'Pérez García'
        assert response.dependencia_actual is None
        assert response.cargo_actual is None
        assert response.roles_gd_vigentes == []
        assert response.permisos_efectivos == []
        assert response.modulos_activos_organizacion == []

    @pytest.mark.asyncio
    async def test_response_con_dependencia_pero_sin_cargo(self) -> None:
        dep_id = uuid4()
        perfil = _make_perfil_ctx(dependencia_id=dep_id)
        # Desde bloque 4: el handler hace JOIN con gd.dependencia → devolvemos
        # dependencia_data con código y nombre.
        conn = _make_conn_for_me(
            dependencia_data={'codigo_organico': 'JUR-001', 'nombre': 'Oficina Jurídica'},
        )
        response = await get_gd_me(perfil, conn)
        assert response.dependencia_actual is not None
        assert response.dependencia_actual.id == dep_id
        assert response.dependencia_actual.codigo == 'JUR-001'
        assert response.dependencia_actual.nombre == 'Oficina Jurídica'

    @pytest.mark.asyncio
    async def test_response_con_dependencia_id_pero_dep_borrada(self) -> None:
        """Edge: FK validada pero soporte borró la fila — devuelve solo id."""
        dep_id = uuid4()
        perfil = _make_perfil_ctx(dependencia_id=dep_id)
        conn = _make_conn_for_me(dependencia_data=None)
        response = await get_gd_me(perfil, conn)
        assert response.dependencia_actual is not None
        assert response.dependencia_actual.id == dep_id
        assert response.dependencia_actual.nombre is None

    @pytest.mark.asyncio
    async def test_response_con_cargo_existente(self) -> None:
        cargo_id = uuid4()
        perfil = _make_perfil_ctx(cargo_id=cargo_id)
        conn = _make_conn_for_me(cargo_data={'nombre': 'Profesional Especializado'})
        response = await get_gd_me(perfil, conn)
        assert response.cargo_actual is not None
        assert response.cargo_actual.id == cargo_id
        assert response.cargo_actual.nombre == 'Profesional Especializado'

    @pytest.mark.asyncio
    async def test_response_con_cargo_inexistente_devuelve_none(self) -> None:
        """Edge: cargo_actual_id apunta a un cargo borrado / inválido."""
        cargo_id = uuid4()
        perfil = _make_perfil_ctx(cargo_id=cargo_id)
        conn = _make_conn_for_me(cargo_data=None)  # gd.cargo.fetchrow → None
        response = await get_gd_me(perfil, conn)
        assert response.cargo_actual is None

    @pytest.mark.asyncio
    async def test_response_con_roles_vigentes(self) -> None:
        perfil = _make_perfil_ctx()
        asign_id = uuid4()
        dep_id = uuid4()
        conn = _make_conn_for_me(
            roles_data=[
                {
                    'asignacion_alcance_id': asign_id,
                    'rol_codigo': 'gd.profesional',
                    'rol_nombre': 'Profesional Responsable',
                    'dependencia_id': dep_id,
                    'dependencia_nombre': 'Oficina Jurídica',
                    'alcance': 'dependencia',
                    'fecha_inicio': date(2025, 1, 15),
                    'fecha_fin': None,
                },
            ],
            permisos_data=[
                {
                    'permiso_codigo': 'PERM-PQRSD-009',
                    'alcance_asignacion': 'dependencia',
                    'alcance_default_permiso': 'dependencia',
                },
            ],
        )
        response = await get_gd_me(perfil, conn)
        assert len(response.roles_gd_vigentes) == 1
        rol = response.roles_gd_vigentes[0]
        assert rol.rol_codigo == 'gd.profesional'
        assert rol.alcance == 'dependencia'
        # permisos_efectivos ordenado alfabéticamente
        assert response.permisos_efectivos == ['PERM-PQRSD-009']
