"""Tests TestClient para handlers del bloque 17 (expedientes EP-016)."""
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
        'app.gd.handlers.expedientes_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _exp_dict(estado='abierto', **extra):
    base = {
        'id': uuid4(), 'codigo': 'EXP-001',
        'titulo': 'Exp', 'descripcion': None,
        'dependencia_responsable_id': None,
        'serie_id': None, 'subserie_id': None,
        'estado': estado, 'fecha_apertura': datetime.now(),
        'fecha_cierre': None, 'fecha_reapertura': None,
        'fecha_transferencia': None,
        'motivo_cierre': None, 'motivo_reapertura': None,
        'motivo_transferencia': None, 'destino_transferencia': None,
        'abierto_por_user_id': uuid4(),
        'cerrado_por_user_id': None, 'reabierto_por_user_id': None,
        'metadata': {}, 'created_at': datetime.now(),
        'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _item_dict(estado='vinculado', **extra):
    base = {
        'id': uuid4(), 'expediente_id': uuid4(),
        'item_tipo': 'documento', 'item_id': uuid4(),
        'orden': 0, 'estado': estado,
        'vinculado_por_user_id': uuid4(),
        'fecha_vinculacion': datetime.now(),
        'retirado_por_user_id': None,
        'fecha_retiro': None, 'motivo_retiro': None,
    }
    base.update(extra)
    return base


# =============================================================================
# CRUD
# =============================================================================
class TestCRUDHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.return_value = _exp_dict()
        r = client.post(
            '/v1/gd/expedientes',
            json={'codigo': 'EXP-001', 'titulo': 'Mi expediente'},
        )
        assert r.status_code == 201, r.text

    def test_crear_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/v1/gd/expedientes',
            json={'codigo': 'DUP', 'titulo': 'Duplicado'},
        )
        assert r.status_code == 409

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/v1/gd/expedientes')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            '/v1/gd/expedientes?estado=abierto'
            f'&dependencia_id={uuid4()}&serie_id={uuid4()}'
            f'&subserie_id={uuid4()}&codigo=2026&q=proyecto&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _exp_dict()
        r = client.get(f'/v1/gd/expedientes/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/expedientes/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchval.return_value = 'abierto'
        conn.fetchrow.return_value = _exp_dict(titulo='Renombrado')
        r = client.patch(
            f'/v1/gd/expedientes/{uuid4()}',
            json={'titulo': 'Renombrado'},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.patch(
            f'/v1/gd/expedientes/{uuid4()}',
            json={'titulo': 'Nuevo'},
        )
        assert r.status_code == 404

    def test_patch_cerrado_solo_metadata(self, conn, client):
        conn.fetchval.return_value = 'cerrado'
        conn.fetchrow.return_value = _exp_dict(estado='cerrado')
        r = client.patch(
            f'/v1/gd/expedientes/{uuid4()}',
            json={'metadata': {'k': 'v'}},
        )
        assert r.status_code == 200

    def test_patch_cerrado_titulo_falla(self, conn, client):
        conn.fetchval.return_value = 'cerrado'
        r = client.patch(
            f'/v1/gd/expedientes/{uuid4()}',
            json={'titulo': 'Nuevo Título'},
        )
        assert r.status_code == 409


# =============================================================================
# Lifecycle
# =============================================================================
class TestLifecycleHandlers:
    def test_cerrar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            _exp_dict(estado='cerrado'),
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/cerrar',
            json={'motivo': 'trámite completo'},
        )
        assert r.status_code == 200

    def test_cerrar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/cerrar',
            json={'motivo': 'X' * 6},
        )
        assert r.status_code == 404

    def test_cerrar_ya_cerrado(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'cerrado'}
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/cerrar',
            json={'motivo': 'X' * 6},
        )
        assert r.status_code == 409

    def test_reabrir_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'cerrado', 'fecha_reapertura': None},
            _exp_dict(estado='reabierto'),
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/reabrir',
            json={'motivo': 'apareció nueva información'},
        )
        assert r.status_code == 200

    def test_reabrir_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/reabrir',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_reabrir_no_cerrado(self, conn, client):
        conn.fetchrow.return_value = {
            'estado': 'abierto', 'fecha_reapertura': None,
        }
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/reabrir',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_reabrir_ya_reabierto(self, conn, client):
        conn.fetchrow.return_value = {
            'estado': 'cerrado', 'fecha_reapertura': datetime.now(),
        }
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/reabrir',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_transferir_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'cerrado'},
            _exp_dict(estado='transferido'),
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/transferir',
            json={'destino': 'Archivo Central',
                  'motivo': 'transferencia documental'},
        )
        assert r.status_code == 200

    def test_transferir_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/transferir',
            json={'destino': 'Destino', 'motivo': 'X' * 11},
        )
        assert r.status_code == 404


# =============================================================================
# Items
# =============================================================================
class TestItemsHandlers:
    def test_asociar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            _item_dict(),
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items',
            json={'item_tipo': 'documento',
                  'item_id': str(uuid4()), 'orden': 1},
        )
        assert r.status_code == 201

    def test_asociar_expediente_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items',
            json={'item_tipo': 'documento', 'item_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_asociar_expediente_cerrado(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'cerrado'}
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items',
            json={'item_tipo': 'radicado', 'item_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_asociar_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            asyncpg.UniqueViolationError,
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items',
            json={'item_tipo': 'documento', 'item_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_retirar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4()},
            _item_dict(estado='retirado', motivo_retiro='error'),
        ]
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items/documento/{uuid4()}/retirar',
            json={'motivo': 'error de asociación'},
        )
        assert r.status_code == 200

    def test_retirar_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items/documento/{uuid4()}/retirar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_retirar_tipo_invalido(self, conn, client):
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/items/invalido/{uuid4()}/retirar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 422


# =============================================================================
# Contenido
# =============================================================================
class TestContenidoHandler:
    def test_ok(self, conn, client):
        conn.fetchrow.return_value = _exp_dict()
        conn.fetch.return_value = [
            _item_dict(item_tipo='documento'),
            _item_dict(item_tipo='radicado'),
        ]
        r = client.get(f'/v1/gd/expedientes/{uuid4()}/contenido')
        assert r.status_code == 200, r.text
        body = r.json()
        assert 'totales_por_tipo' in body

    def test_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/expedientes/{uuid4()}/contenido')
        assert r.status_code == 404
