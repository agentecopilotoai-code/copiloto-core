"""Tests mocks para services del bloque 16 (TRD/TVD EP-015)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import trd as svc


def _trd_row(estado='borrador', **extra):
    base = {
        'id': uuid4(), 'codigo': 'TRD-2024-v1',
        'nombre': 'TRD inicial', 'descripcion': None,
        'fecha_aprobacion': date.today(),
        'fecha_inicio_vigencia': None, 'fecha_fin_vigencia': None,
        'estado': estado, 'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _serie_row(**extra):
    base = {
        'id': uuid4(), 'version_trd_id': uuid4(),
        'codigo': '100', 'nombre': 'Acuerdos',
        'descripcion': None, 'estado': 'activa',
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _subserie_row(**extra):
    base = {
        'id': uuid4(), 'serie_id': uuid4(),
        'codigo': '100.01', 'nombre': 'Acuerdos municipales',
        'descripcion': None,
        'tiempo_archivo_gestion_anos': 2,
        'tiempo_archivo_central_anos': 10,
        'disposicion_final': 'conservacion_total',
        'estado': 'activa', 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _tipo_doc_row(**extra):
    base = {
        'id': uuid4(), 'subserie_id': uuid4(),
        'codigo': 'TD01', 'nombre': 'Resolución',
        'descripcion': None, 'estado': 'activo',
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _tvd_row(estado='borrador', **extra):
    base = {
        'id': uuid4(), 'codigo': 'TVD-2024-v1',
        'nombre': 'TVD inicial', 'descripcion': None,
        'version_trd_id': None,
        'fecha_aprobacion': None,
        'fecha_inicio_vigencia': None, 'fecha_fin_vigencia': None,
        'estado': estado, 'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _clasif_row(estado='vigente', **extra):
    base = {
        'id': uuid4(), 'entidad_tipo': 'radicado',
        'entidad_id': uuid4(), 'version_trd_id': uuid4(),
        'serie_id': uuid4(), 'subserie_id': uuid4(),
        'tipo_documental_id': None, 'justificacion': None,
        'estado': estado, 'clasificado_por_user_id': uuid4(),
        'fecha_clasificacion': datetime.now(),
        'reemplazada_por_id': None, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Version TRD
# =============================================================================
class TestVersionTRD:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _trd_row()
        r = await svc.crear_version_trd(
            conn, tenant_id=uuid4(), codigo='TRD-2024',
            nombre='TRD 2024', descripcion=None,
            created_by_user_id=uuid4(),
        )
        assert r['estado'] == 'borrador'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='codigo_ya_existe'):
            await svc.crear_version_trd(
                conn, tenant_id=uuid4(), codigo='DUP',
                nombre='X', descripcion=None,
                created_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _trd_row()
        r = await svc.obtener_version_trd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_version_trd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_versiones_trd(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_versiones_trd(
            conn, tenant_id=uuid4(), estado='vigente', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_activar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            _trd_row(estado='vigente'),
        ]
        r = await svc.activar_version_trd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r['estado'] == 'vigente'

    @pytest.mark.asyncio
    async def test_activar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.activar_version_trd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_activar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'historica'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.activar_version_trd(
                conn, tenant_id=uuid4(), version_id=uuid4(),
            )


# =============================================================================
# Series
# =============================================================================
class TestSeries:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},  # validar version_trd
            _serie_row(),
        ]
        r = await svc.crear_serie(
            conn, tenant_id=uuid4(), version_trd_id=uuid4(),
            codigo='100', nombre='Acuerdos', descripcion=None,
        )
        assert r['codigo'] == '100'

    @pytest.mark.asyncio
    async def test_crear_version_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError, match='version_trd_no_existe'):
            await svc.crear_serie(
                conn, tenant_id=uuid4(), version_trd_id=uuid4(),
                codigo='X', nombre='Y', descripcion=None,
            )

    @pytest.mark.asyncio
    async def test_crear_codigo_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            asyncpg.UniqueViolationError,
        ]
        with pytest.raises(ValueError, match='serie_codigo_duplicado'):
            await svc.crear_serie(
                conn, tenant_id=uuid4(), version_trd_id=uuid4(),
                codigo='DUP', nombre='X', descripcion=None,
            )

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_series(
            conn, tenant_id=uuid4(), version_trd_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_series(
            conn, tenant_id=uuid4(), version_trd_id=uuid4(), estado='activa',
        )
        assert r == []


# =============================================================================
# Subseries
# =============================================================================
class TestSubseries:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _subserie_row()
        r = await svc.crear_subserie(
            conn, tenant_id=uuid4(), serie_id=uuid4(),
            codigo='100.01', nombre='Acuerdos municipales',
            descripcion=None,
            tiempo_archivo_gestion_anos=2,
            tiempo_archivo_central_anos=10,
            disposicion_final='conservacion_total',
        )
        assert r['disposicion_final'] == 'conservacion_total'

    @pytest.mark.asyncio
    async def test_crear_serie_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='serie_no_existe'):
            await svc.crear_subserie(
                conn, tenant_id=uuid4(), serie_id=uuid4(),
                codigo='X', nombre='Y', descripcion=None,
                tiempo_archivo_gestion_anos=None,
                tiempo_archivo_central_anos=None,
                disposicion_final=None,
            )

    @pytest.mark.asyncio
    async def test_crear_codigo_duplicado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='subserie_codigo_duplicado'):
            await svc.crear_subserie(
                conn, tenant_id=uuid4(), serie_id=uuid4(),
                codigo='DUP', nombre='X', descripcion=None,
                tiempo_archivo_gestion_anos=None,
                tiempo_archivo_central_anos=None,
                disposicion_final=None,
            )

    @pytest.mark.asyncio
    async def test_listar(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_subseries(
            conn, tenant_id=uuid4(), serie_id=uuid4(),
        )
        assert r == []


# =============================================================================
# Tipos documentales
# =============================================================================
class TestTiposDoc:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _tipo_doc_row()
        r = await svc.crear_tipo_documental(
            conn, tenant_id=uuid4(), subserie_id=uuid4(),
            codigo='TD01', nombre='Resolución', descripcion=None,
        )
        assert r['estado'] == 'activo'

    @pytest.mark.asyncio
    async def test_crear_subserie_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='subserie_no_existe'):
            await svc.crear_tipo_documental(
                conn, tenant_id=uuid4(), subserie_id=uuid4(),
                codigo='X', nombre='Y', descripcion=None,
            )

    @pytest.mark.asyncio
    async def test_crear_codigo_duplicado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='tipo_doc_codigo_duplicado'):
            await svc.crear_tipo_documental(
                conn, tenant_id=uuid4(), subserie_id=uuid4(),
                codigo='DUP', nombre='X', descripcion=None,
            )

    @pytest.mark.asyncio
    async def test_listar(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_tipos_documentales(
            conn, tenant_id=uuid4(), subserie_id=uuid4(),
        )
        assert r == []


# =============================================================================
# Version TVD
# =============================================================================
class TestVersionTVD:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _tvd_row()
        r = await svc.crear_version_tvd(
            conn, tenant_id=uuid4(), codigo='TVD-2024',
            nombre='TVD 2024', descripcion=None,
            version_trd_id=uuid4(),
            created_by_user_id=uuid4(),
        )
        assert r['estado'] == 'borrador'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='codigo_tvd_ya_existe'):
            await svc.crear_version_tvd(
                conn, tenant_id=uuid4(), codigo='DUP',
                nombre='X', descripcion=None,
                version_trd_id=None, created_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_activar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            _tvd_row(estado='vigente'),
        ]
        r = await svc.activar_version_tvd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r['estado'] == 'vigente'

    @pytest.mark.asyncio
    async def test_activar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.activar_version_tvd(
            conn, tenant_id=uuid4(), version_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_activar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'vigente'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.activar_version_tvd(
                conn, tenant_id=uuid4(), version_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_versiones_tvd(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_versiones_tvd(
            conn, tenant_id=uuid4(), estado='vigente', limit=10,
        )
        assert r == []


# =============================================================================
# Asociación dep ↔ código
# =============================================================================
class TestAsociacion:
    @pytest.mark.asyncio
    async def test_asociar_serie_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'dependencia_id': uuid4(),
            'version_trd_id': uuid4(),
            'serie_id': uuid4(), 'subserie_id': None,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = await svc.asociar_dep_codigo(
            conn, tenant_id=uuid4(),
            dependencia_id=uuid4(), version_trd_id=uuid4(),
            serie_id=uuid4(), subserie_id=None,
            creado_por_user_id=uuid4(),
        )
        assert r['serie_id'] is not None

    @pytest.mark.asyncio
    async def test_asociar_duplicada(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='asociacion_ya_existe'):
            await svc.asociar_dep_codigo(
                conn, tenant_id=uuid4(),
                dependencia_id=uuid4(), version_trd_id=uuid4(),
                serie_id=uuid4(), subserie_id=None,
                creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_dep_codigos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_dep_codigos(
            conn, tenant_id=uuid4(),
            dependencia_id=uuid4(), version_trd_id=uuid4(),
        )
        assert r == []


# =============================================================================
# Clasificación documental
# =============================================================================
class TestClasificacion:
    @pytest.mark.asyncio
    async def test_clasificar_nueva(self):
        conn = AsyncMock()
        # version_trd valida + vigente_id null + insert nueva
        conn.fetchrow.side_effect = [
            {'estado': 'vigente'},  # version_trd
            _clasif_row(),
        ]
        conn.fetchval.return_value = None  # no vigente existente
        r = await svc.clasificar(
            conn, tenant_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
            version_trd_id=uuid4(),
            serie_id=uuid4(), subserie_id=uuid4(),
            tipo_documental_id=None, justificacion=None,
            clasificado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'vigente'

    @pytest.mark.asyncio
    async def test_clasificar_reemplaza_vigente(self):
        conn = AsyncMock()
        vigente_anterior = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'vigente'},  # version_trd valida
            _clasif_row(),  # insert nueva
        ]
        conn.fetchval.return_value = vigente_anterior  # hay vigente
        r = await svc.clasificar(
            conn, tenant_id=uuid4(),
            entidad_tipo='documento', entidad_id=uuid4(),
            version_trd_id=uuid4(),
            serie_id=uuid4(), subserie_id=None,
            tipo_documental_id=None, justificacion='cambio de serie',
            clasificado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'vigente'

    @pytest.mark.asyncio
    async def test_clasificar_version_trd_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError, match='version_trd_no_existe'):
            await svc.clasificar(
                conn, tenant_id=uuid4(),
                entidad_tipo='radicado', entidad_id=uuid4(),
                version_trd_id=uuid4(),
                serie_id=None, subserie_id=None,
                tipo_documental_id=None, justificacion=None,
                clasificado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_vigente_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _clasif_row()
        r = await svc.obtener_vigente(
            conn, tenant_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
        )
        assert r['estado'] == 'vigente'

    @pytest.mark.asyncio
    async def test_obtener_vigente_none(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_vigente(
            conn, tenant_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_historial(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            _clasif_row(estado='vigente'),
            _clasif_row(estado='reemplazada'),
        ]
        r = await svc.historial_clasificacion(
            conn, tenant_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
        )
        assert len(r) == 2
