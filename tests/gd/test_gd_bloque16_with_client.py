"""Tests TestClient para handlers del bloque 16 (TRD/TVD EP-015)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import router as gd_router
from app.gd.security import GdPerfilContext, require_gd_perfil


TENANT_ID = uuid4()
ACTOR = uuid4()


def _perfil():
    return GdPerfilContext(
        user_id=ACTOR, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {'PERM-USR-001': 'global'}


async def _noop_emit(*a, **k):
    return uuid4()


def build_app(conn_mock):
    app = FastAPI()
    app.include_router(gd_router)

    async def _ovr_db():
        yield conn_mock

    async def _ovr_perfil():
        return _perfil()

    app.dependency_overrides[get_db] = _ovr_db
    app.dependency_overrides[require_gd_perfil] = _ovr_perfil
    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    monkeypatch.setattr(
        'app.gd.handlers.trd_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _trd_dict(estado='borrador', **extra):
    base = {
        'id': uuid4(), 'codigo': 'TRD-2024-v1', 'nombre': 'TRD',
        'descripcion': None, 'fecha_aprobacion': None,
        'fecha_inicio_vigencia': None, 'fecha_fin_vigencia': None,
        'estado': estado, 'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _serie_dict(**extra):
    base = {
        'id': uuid4(), 'version_trd_id': uuid4(),
        'codigo': '100', 'nombre': 'X',
        'descripcion': None, 'estado': 'activa',
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _subserie_dict(**extra):
    base = {
        'id': uuid4(), 'serie_id': uuid4(),
        'codigo': '100.01', 'nombre': 'X',
        'descripcion': None,
        'tiempo_archivo_gestion_anos': 2,
        'tiempo_archivo_central_anos': 10,
        'disposicion_final': 'conservacion_total',
        'estado': 'activa', 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _tipo_doc_dict(**extra):
    base = {
        'id': uuid4(), 'subserie_id': uuid4(),
        'codigo': 'TD01', 'nombre': 'Resolución',
        'descripcion': None, 'estado': 'activo',
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _tvd_dict(estado='borrador', **extra):
    base = {
        'id': uuid4(), 'codigo': 'TVD-2024-v1', 'nombre': 'TVD',
        'descripcion': None, 'version_trd_id': None,
        'fecha_aprobacion': None, 'fecha_inicio_vigencia': None,
        'fecha_fin_vigencia': None,
        'estado': estado, 'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _clasif_dict(estado='vigente', **extra):
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
# TRD
# =============================================================================
class TestTRDHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.return_value = _trd_dict()
        r = client.post(
            '/api/v1/gd/trd/versiones',
            json={'codigo': 'TRD-2024-V1', 'nombre': 'TRD 2024'},
        )
        assert r.status_code == 201, r.text

    def test_crear_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/trd/versiones',
            json={'codigo': 'DUP', 'nombre': 'Dup'},
        )
        assert r.status_code == 409

    def test_crear_codigo_invalido(self, conn, client):
        # Pattern ^[A-Z0-9\-_]+$
        r = client.post(
            '/api/v1/gd/trd/versiones',
            json={'codigo': 'minusculas', 'nombre': 'X'},
        )
        assert r.status_code == 422

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/trd/versiones')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/trd/versiones?estado=vigente&limit=10')
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _trd_dict()
        r = client.get(f'/api/v1/gd/trd/versiones/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/gd/trd/versiones/{uuid4()}')
        assert r.status_code == 404

    def test_activar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            _trd_dict(estado='vigente'),
        ]
        r = client.post(
            f'/api/v1/gd/trd/versiones/{uuid4()}/activar', json={},
        )
        assert r.status_code == 200

    def test_activar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/trd/versiones/{uuid4()}/activar', json={},
        )
        assert r.status_code == 404

    def test_activar_409(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'vigente'}
        r = client.post(
            f'/api/v1/gd/trd/versiones/{uuid4()}/activar', json={},
        )
        assert r.status_code == 409


# =============================================================================
# Series
# =============================================================================
class TestSeriesHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            _serie_dict(),
        ]
        r = client.post(
            '/api/v1/gd/trd/series',
            json={'version_trd_id': str(uuid4()),
                  'codigo': '100', 'nombre': 'Acuerdos'},
        )
        assert r.status_code == 201

    def test_crear_version_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            '/api/v1/gd/trd/series',
            json={'version_trd_id': str(uuid4()),
                  'codigo': '100', 'nombre': 'Acuerdos'},
        )
        assert r.status_code == 404

    def test_crear_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            asyncpg.UniqueViolationError,
        ]
        r = client.post(
            '/api/v1/gd/trd/series',
            json={'version_trd_id': str(uuid4()),
                  'codigo': '100', 'nombre': 'Acuerdos'},
        )
        assert r.status_code == 409

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/trd/versiones/{uuid4()}/series')
        assert r.status_code == 200

    def test_listar_con_estado(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/trd/versiones/{uuid4()}/series?estado=activa',
        )
        assert r.status_code == 200


# =============================================================================
# Subseries
# =============================================================================
class TestSubseriesHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _subserie_dict()
        r = client.post(
            '/api/v1/gd/trd/subseries',
            json={'serie_id': str(uuid4()),
                  'codigo': '100.01', 'nombre': 'Acuerdos M',
                  'tiempo_archivo_gestion_anos': 2,
                  'disposicion_final': 'conservacion_total'},
        )
        assert r.status_code == 201

    def test_crear_serie_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            '/api/v1/gd/trd/subseries',
            json={'serie_id': str(uuid4()),
                  'codigo': '100.01', 'nombre': 'Subserie X'},
        )
        assert r.status_code == 404

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/trd/series/{uuid4()}/subseries')
        assert r.status_code == 200


# =============================================================================
# Tipos documentales
# =============================================================================
class TestTiposDocHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _tipo_doc_dict()
        r = client.post(
            '/api/v1/gd/trd/tipos-documentales',
            json={'subserie_id': str(uuid4()),
                  'codigo': 'TD01', 'nombre': 'Resolución'},
        )
        assert r.status_code == 201

    def test_crear_subserie_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            '/api/v1/gd/trd/tipos-documentales',
            json={'subserie_id': str(uuid4()),
                  'codigo': 'TD01', 'nombre': 'Resolución'},
        )
        assert r.status_code == 404

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/trd/subseries/{uuid4()}/tipos-documentales',
        )
        assert r.status_code == 200


# =============================================================================
# TVD
# =============================================================================
class TestTVDHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.return_value = _tvd_dict()
        r = client.post(
            '/api/v1/gd/tvd/versiones',
            json={'codigo': 'TVD-2024-V1', 'nombre': 'TVD 2024'},
        )
        assert r.status_code == 201

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/tvd/versiones')
        assert r.status_code == 200

    def test_listar_con_estado(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/tvd/versiones?estado=vigente&limit=10')
        assert r.status_code == 200

    def test_activar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'borrador'},
            _tvd_dict(estado='vigente'),
        ]
        r = client.post(
            f'/api/v1/gd/tvd/versiones/{uuid4()}/activar',
        )
        assert r.status_code == 200

    def test_activar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/tvd/versiones/{uuid4()}/activar',
        )
        assert r.status_code == 404

    def test_activar_409(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'vigente'}
        r = client.post(
            f'/api/v1/gd/tvd/versiones/{uuid4()}/activar',
        )
        assert r.status_code == 409


# =============================================================================
# Asociación dep ↔ código
# =============================================================================
class TestAsociacionHandlers:
    def test_asociar_ok(self, conn, client):
        dep_id = uuid4()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'dependencia_id': dep_id,
            'version_trd_id': uuid4(),
            'serie_id': uuid4(), 'subserie_id': None,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = client.post(
            f'/api/v1/gd/dependencias/{dep_id}/codigos-documentales',
            json={'dependencia_id': str(dep_id),
                  'version_trd_id': str(uuid4()),
                  'serie_id': str(uuid4())},
        )
        assert r.status_code == 201, r.text

    def test_asociar_mismatch(self, conn, client):
        r = client.post(
            f'/api/v1/gd/dependencias/{uuid4()}/codigos-documentales',
            json={'dependencia_id': str(uuid4()),  # otro id
                  'version_trd_id': str(uuid4()),
                  'serie_id': str(uuid4())},
        )
        assert r.status_code == 422

    def test_asociar_duplicada(self, conn, client):
        import asyncpg
        dep_id = uuid4()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            f'/api/v1/gd/dependencias/{dep_id}/codigos-documentales',
            json={'dependencia_id': str(dep_id),
                  'version_trd_id': str(uuid4()),
                  'serie_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_asociar_sin_target(self, conn, client):
        dep_id = uuid4()
        r = client.post(
            f'/api/v1/gd/dependencias/{dep_id}/codigos-documentales',
            json={'dependencia_id': str(dep_id),
                  'version_trd_id': str(uuid4())},
        )
        assert r.status_code == 422

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/dependencias/{uuid4()}/codigos-documentales',
        )
        assert r.status_code == 200


# =============================================================================
# Clasificación
# =============================================================================
class TestClasificacionHandlers:
    def test_clasificar_nueva(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'vigente'},
            _clasif_dict(),
        ]
        conn.fetchval.return_value = None
        r = client.post(
            '/api/v1/gd/clasificacion-documental',
            json={'entidad_tipo': 'radicado',
                  'entidad_id': str(uuid4()),
                  'version_trd_id': str(uuid4()),
                  'serie_id': str(uuid4()),
                  'subserie_id': str(uuid4())},
        )
        assert r.status_code == 201, r.text

    def test_clasificar_reemplaza(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'vigente'},
            _clasif_dict(),
        ]
        conn.fetchval.return_value = uuid4()  # vigente existente
        r = client.post(
            '/api/v1/gd/clasificacion-documental',
            json={'entidad_tipo': 'documento',
                  'entidad_id': str(uuid4()),
                  'version_trd_id': str(uuid4()),
                  'subserie_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_clasificar_version_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            '/api/v1/gd/clasificacion-documental',
            json={'entidad_tipo': 'radicado',
                  'entidad_id': str(uuid4()),
                  'version_trd_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_consultar_vigente(self, conn, client):
        conn.fetchrow.return_value = _clasif_dict()
        conn.fetch.return_value = [_clasif_dict()]
        r = client.get(
            f'/api/v1/gd/clasificacion-documental?entidad_tipo=radicado'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 200, r.text
        assert r.json()['vigente'] is not None

    def test_consultar_sin_clasificacion(self, conn, client):
        conn.fetchrow.return_value = None
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/clasificacion-documental?entidad_tipo=pqrsd'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 200
        assert r.json()['vigente'] is None

    def test_consultar_entidad_invalida(self, conn, client):
        r = client.get(
            f'/api/v1/gd/clasificacion-documental?entidad_tipo=invalido'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 422
