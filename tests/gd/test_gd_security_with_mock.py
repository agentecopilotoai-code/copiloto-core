"""Tests para `app.gd.security` con mocks de asyncpg (sin DB real).

Cubre el camino feliz y error de:
- `_load_perfil`: query a gd.perfil_usuario.
- `require_gd_perfil`: dependency que valida perfil activo.
- `get_permisos_efectivos`: agregación de matriz rol↔permiso ∩ asignaciones.
- `require_gd_permission`: factory de dependency con check de alcance.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.gd.security import (
    _load_perfil,
    get_permisos_efectivos,
    require_gd_perfil,
    require_gd_permission,
)


def _make_request_state(user_id=None, tenant_id=None) -> MagicMock:
    """Construye un mock de Request con state.user_id y state.tenant_id."""
    request = MagicMock()
    request.state.user_id = user_id
    request.state.tenant_id = tenant_id
    return request


class TestLoadPerfil:
    @pytest.mark.asyncio
    async def test_retorna_none_si_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        perfil = await _load_perfil(conn, user_id=uuid4(), tenant_id=uuid4())
        assert perfil is None

    @pytest.mark.asyncio
    async def test_retorna_contexto_completo(self) -> None:
        conn = AsyncMock()
        user_id = uuid4()
        tenant_id = uuid4()
        perfil_id = uuid4()
        dep_id = uuid4()
        cargo_id = uuid4()
        conn.fetchrow.return_value = {
            'perfil_id': perfil_id,
            'user_id': user_id,
            'tenant_id': tenant_id,
            'tipo_vinculacion': 'planta',
            'estado_gd': 'activo',
            'dependencia_actual_id': dep_id,
            'cargo_actual_id': cargo_id,
        }
        perfil = await _load_perfil(conn, user_id=user_id, tenant_id=tenant_id)
        assert perfil is not None
        assert perfil.user_id == user_id
        assert perfil.tenant_id == tenant_id
        assert perfil.perfil_id == perfil_id
        assert perfil.tipo_vinculacion == 'planta'
        assert perfil.estado_gd == 'activo'
        assert perfil.dependencia_actual_id == dep_id
        assert perfil.cargo_actual_id == cargo_id


class TestRequireGdPerfil:
    @pytest.mark.asyncio
    async def test_lanza_401_sin_user_id_o_tenant_id(self) -> None:
        request = _make_request_state(user_id=None, tenant_id=None)
        conn = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await require_gd_perfil(request, _auth=None, conn=conn)
        assert exc.value.status_code == 401
        assert exc.value.detail['error'] == 'unauthenticated'

    @pytest.mark.asyncio
    async def test_lanza_403_si_perfil_no_existe(self) -> None:
        request = _make_request_state(user_id=uuid4(), tenant_id=uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(HTTPException) as exc:
            await require_gd_perfil(request, _auth=None, conn=conn)
        assert exc.value.status_code == 403
        assert exc.value.detail['code'] == 'gd_profile_missing_or_inactive'

    @pytest.mark.asyncio
    async def test_lanza_403_si_perfil_inactivo(self) -> None:
        request = _make_request_state(user_id=uuid4(), tenant_id=uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'perfil_id': uuid4(),
            'user_id': uuid4(),
            'tenant_id': uuid4(),
            'tipo_vinculacion': 'planta',
            'estado_gd': 'inactivo',  # <-- bloqueante
            'dependencia_actual_id': None,
            'cargo_actual_id': None,
        }
        with pytest.raises(HTTPException) as exc:
            await require_gd_perfil(request, _auth=None, conn=conn)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_perfil_activo_devuelve_contexto_y_cachea(self) -> None:
        user_id = uuid4()
        tenant_id = uuid4()
        request = _make_request_state(user_id=user_id, tenant_id=tenant_id)
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'perfil_id': uuid4(),
            'user_id': user_id,
            'tenant_id': tenant_id,
            'tipo_vinculacion': 'planta',
            'estado_gd': 'activo',
            'dependencia_actual_id': None,
            'cargo_actual_id': None,
        }
        perfil = await require_gd_perfil(request, _auth=None, conn=conn)
        assert perfil.user_id == user_id
        assert perfil.estado_gd == 'activo'
        # Debe cachear en request.state para evitar relectura.
        assert request.state.gd_perfil is perfil


class TestGetPermisosEfectivos:
    @pytest.mark.asyncio
    async def test_lista_vacia_si_sin_asignaciones(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        efectivos = await get_permisos_efectivos(
            conn, user_id=uuid4(), tenant_id=uuid4()
        )
        assert efectivos == {}

    @pytest.mark.asyncio
    async def test_alcance_efectivo_es_el_mas_restrictivo(self) -> None:
        """Si asignación='institucional' pero alcance_default='dependencia', gana 'dependencia'."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'permiso_codigo': 'PERM-DOC-005',
                'alcance_asignacion': 'institucional',
                'alcance_default_permiso': 'dependencia',
            },
        ]
        efectivos = await get_permisos_efectivos(
            conn, user_id=uuid4(), tenant_id=uuid4()
        )
        assert efectivos == {'PERM-DOC-005': 'dependencia'}

    @pytest.mark.asyncio
    async def test_alcance_max_entre_asignaciones_del_mismo_permiso(self) -> None:
        """Mismo permiso en dos asignaciones — gana el MAYOR alcance."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'permiso_codigo': 'PERM-PQRSD-009',
                'alcance_asignacion': 'propio',
                'alcance_default_permiso': 'propio',
            },
            {
                'permiso_codigo': 'PERM-PQRSD-009',
                'alcance_asignacion': 'dependencia',
                'alcance_default_permiso': 'dependencia',
            },
        ]
        efectivos = await get_permisos_efectivos(
            conn, user_id=uuid4(), tenant_id=uuid4()
        )
        assert efectivos == {'PERM-PQRSD-009': 'dependencia'}

    @pytest.mark.asyncio
    async def test_permisos_distintos_son_independientes(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'permiso_codigo': 'PERM-A',
                'alcance_asignacion': 'institucional',
                'alcance_default_permiso': 'institucional',
            },
            {
                'permiso_codigo': 'PERM-B',
                'alcance_asignacion': 'propio',
                'alcance_default_permiso': 'propio',
            },
        ]
        efectivos = await get_permisos_efectivos(
            conn, user_id=uuid4(), tenant_id=uuid4()
        )
        assert efectivos == {'PERM-A': 'institucional', 'PERM-B': 'propio'}


class TestRequireGdPermission:
    """Tests del factory `require_gd_permission` con su check interno."""

    @pytest.mark.asyncio
    async def test_403_si_falta_permiso(self) -> None:
        from app.gd.security import GdPerfilContext

        check = require_gd_permission('PERM-XYZ-001', alcance='dependencia')
        perfil = GdPerfilContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            perfil_id=uuid4(),
            tipo_vinculacion='planta',
            estado_gd='activo',
            dependencia_actual_id=None,
            cargo_actual_id=None,
        )
        conn = AsyncMock()
        conn.fetch.return_value = []  # sin permisos
        request = _make_request_state()
        with pytest.raises(HTTPException) as exc:
            await check(request, perfil, conn)
        assert exc.value.status_code == 403
        assert exc.value.detail['permiso_requerido'] == 'PERM-XYZ-001'
        assert exc.value.detail['alcance_requerido'] == 'dependencia'

    @pytest.mark.asyncio
    async def test_403_si_alcance_insuficiente(self) -> None:
        from app.gd.security import GdPerfilContext

        check = require_gd_permission('PERM-PQRSD-009', alcance='institucional')
        perfil = GdPerfilContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            perfil_id=uuid4(),
            tipo_vinculacion='planta',
            estado_gd='activo',
            dependencia_actual_id=None,
            cargo_actual_id=None,
        )
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'permiso_codigo': 'PERM-PQRSD-009',
                'alcance_asignacion': 'dependencia',
                'alcance_default_permiso': 'dependencia',
            },
        ]
        request = _make_request_state()
        with pytest.raises(HTTPException) as exc:
            await check(request, perfil, conn)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_ok_si_alcance_suficiente(self) -> None:
        from app.gd.security import GdPerfilContext

        check = require_gd_permission('PERM-DOC-005', alcance='dependencia')
        perfil = GdPerfilContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            perfil_id=uuid4(),
            tipo_vinculacion='planta',
            estado_gd='activo',
            dependencia_actual_id=None,
            cargo_actual_id=None,
        )
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'permiso_codigo': 'PERM-DOC-005',
                'alcance_asignacion': 'institucional',
                'alcance_default_permiso': 'institucional',
            },
        ]
        request = _make_request_state()
        # No debe lanzar.
        result = await check(request, perfil, conn)
        assert result is None
