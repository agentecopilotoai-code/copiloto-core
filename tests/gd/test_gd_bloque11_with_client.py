"""Tests TestClient para handlers del bloque 11 (plantillas EP-010)."""
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
        'app.gd.handlers.plantillas_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _pl_dict(estado='borrador', **extra):
    base = {
        'id': uuid4(), 'codigo': 'COD', 'nombre': 'P',
        'descripcion': None, 'tipo_plantilla': 'oficio_respuesta',
        'estado': estado, 'version_vigente_id': None,
        'numero_version_vigente': 0,
        'dependencia_propietaria_id': None,
        'es_institucional': False,
        'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _ver_dict(numero=1, **extra):
    base = {
        'id': uuid4(), 'plantilla_id': uuid4(),
        'numero_version': numero,
        'contenido_template': 'Hola {{nombre}}',
        'archivo_digital_id': None, 'mime_type': 'text/plain',
        'json_schema_campos': {'type': 'object'},
        'estado': 'borrador', 'notas': None,
        'created_by_user_id': uuid4(), 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# CRUD
# =============================================================================
class TestCRUDHandlers:
    def test_crear_sin_version_ok(self, conn, client):
        conn.fetchrow.return_value = _pl_dict()
        r = client.post(
            '/v1/gd/plantillas',
            json={'codigo': 'OFI', 'nombre': 'Oficio',
                  'tipo_plantilla': 'oficio_respuesta'},
        )
        assert r.status_code == 201, r.text

    def test_crear_con_version_ok(self, conn, client):
        conn.fetchrow.side_effect = [_pl_dict(), _ver_dict()]
        conn.fetchval.return_value = 0
        r = client.post(
            '/v1/gd/plantillas',
            json={'codigo': 'OFI', 'nombre': 'Oficio',
                  'tipo_plantilla': 'oficio_respuesta',
                  'contenido_template': 'X'},
        )
        assert r.status_code == 201

    def test_crear_codigo_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/v1/gd/plantillas',
            json={'codigo': 'DUP', 'nombre': 'Plantilla Duplicada',
                  'tipo_plantilla': 'otra'},
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'codigo_ya_existe'

    def test_crear_codigo_invalido(self, conn, client):
        # Pattern ^[A-Z0-9_]+$
        r = client.post(
            '/v1/gd/plantillas',
            json={'codigo': 'with-dash', 'nombre': 'X',
                  'tipo_plantilla': 'otra'},
        )
        assert r.status_code == 422

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/v1/gd/plantillas')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            '/v1/gd/plantillas?estado=activa&tipo=respuesta_pqrsd'
            f'&dependencia_id={uuid4()}&es_institucional=true&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _pl_dict()
        conn.fetch.return_value = []
        r = client.get(f'/v1/gd/plantillas/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/plantillas/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _pl_dict(nombre='Nuevo')
        conn.fetch.return_value = []
        r = client.patch(
            f'/v1/gd/plantillas/{uuid4()}',
            json={'nombre': 'Nuevo Nombre'},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.patch(
            f'/v1/gd/plantillas/{uuid4()}', json={'nombre': 'Nuevo'},
        )
        assert r.status_code == 404


# =============================================================================
# Versiones
# =============================================================================
class TestVersionesHandlers:
    def test_nueva_version_ok(self, conn, client):
        # 1. fetchval(plantilla existe)
        # 2. fetchval(max_num)
        # 3. fetchrow(insert version)
        conn.fetchval.side_effect = [1, 0]
        conn.fetchrow.return_value = _ver_dict(numero=1)
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/versiones',
            json={'contenido_template': 'Nueva v {{x}}'},
        )
        assert r.status_code == 201

    def test_nueva_version_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/versiones',
            json={'contenido_template': 'X'},
        )
        assert r.status_code == 404


# =============================================================================
# Activar / inactivar
# =============================================================================
class TestActivarHandlers:
    def test_activar_ok_con_version_explicita(self, conn, client):
        ver_id = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador', 'version_vigente_id': None},
            {'id': ver_id, 'numero_version': 1, 'estado': 'borrador'},
            _pl_dict(estado='activa', numero_version_vigente=1),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/activar',
            json={'version_id': str(ver_id)},
        )
        assert r.status_code == 200

    def test_activar_sin_version_borrador(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'borrador', 'version_vigente_id': None},
            None,
        ]
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/activar', json={},
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'sin_version_borrador'

    def test_activar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/activar', json={},
        )
        assert r.status_code == 404

    def test_inactivar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'activa'},
            _pl_dict(estado='inactiva'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/inactivar',
        )
        assert r.status_code == 200

    def test_inactivar_409(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'inactiva'}
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/inactivar',
        )
        assert r.status_code == 409

    def test_inactivar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/inactivar',
        )
        assert r.status_code == 404


# =============================================================================
# Generar documento
# =============================================================================
class TestGenerarHandler:
    def test_generar_ok(self, conn, client, monkeypatch):
        doc_id = uuid4()
        async def fake_crear_doc(conn, **kwargs):
            return {'id': doc_id,
                    'versiones': [{'id': uuid4(), 'numero_version': 1}]}
        monkeypatch.setattr(
            'app.gd.services.documentos.crear_documento', fake_crear_doc,
        )
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'codigo': 'C', 'nombre': 'P',
             'estado': 'activa', 'version_vigente_id': uuid4()},
            {'id': uuid4(), 'contenido_template': 'X',
             'mime_type': 'text/plain', 'json_schema_campos': {}},
            None,  # org
            None,  # user
        ]
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/generar-documento',
            json={'titulo': 'Documento generado',
                  'datos_adicionales': {'k': 'v'}},
        )
        assert r.status_code == 201

    def test_generar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/generar-documento',
            json={},
        )
        assert r.status_code == 404

    def test_generar_plantilla_no_activa(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'codigo': 'X', 'nombre': 'X',
            'estado': 'borrador', 'version_vigente_id': uuid4(),
        }
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/generar-documento',
            json={},
        )
        assert r.status_code == 409


# =============================================================================
# Asociaciones
# =============================================================================
class TestAsociacionesHandlers:
    def test_asociar_dep_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'plantilla_id': uuid4(),
            'asociacion_tipo': 'dependencia',
            'asociacion_id': uuid4(), 'asociacion_codigo': None,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/asociar-dependencia/{uuid4()}',
        )
        assert r.status_code == 201

    def test_asociar_dep_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/asociar-dependencia/{uuid4()}',
        )
        assert r.status_code == 404

    def test_asociar_dep_duplicada(self, conn, client):
        import asyncpg
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/asociar-dependencia/{uuid4()}',
        )
        assert r.status_code == 409

    def test_asociar_tt_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'plantilla_id': uuid4(),
            'asociacion_tipo': 'tipo_tramite',
            'asociacion_id': None, 'asociacion_codigo': 'PQRSD',
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/asociar-tipo-tramite/PQRSD',
        )
        assert r.status_code == 201

    def test_asociar_tt_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/plantillas/{uuid4()}/asociar-tipo-tramite/PQRSD',
        )
        assert r.status_code == 404

    def test_listar_asociaciones(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/plantillas/{uuid4()}/asociaciones',
        )
        assert r.status_code == 200


# =============================================================================
# Seed institucional
# =============================================================================
class TestSeedHandler:
    def test_seed_todas_nuevas(self, conn, client):
        # 7 plantillas seed × 2 (insert pl + insert version)
        rows: list = []
        for _ in range(7):
            rows.append(_pl_dict(es_institucional=True))
            rows.append(_ver_dict(numero=1))
        conn.fetchrow.side_effect = rows
        conn.fetchval.return_value = 0
        r = client.post('/v1/gd/plantillas/_seed-institucionales')
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['total'] == 7

    def test_seed_idempotente(self, conn, client):
        # Todas duplicadas
        import asyncpg
        rows: list = [asyncpg.UniqueViolationError for _ in range(7)]
        conn.fetchrow.side_effect = rows
        r = client.post('/v1/gd/plantillas/_seed-institucionales')
        assert r.status_code == 200
        body = r.json()
        assert body['total'] == 0
        assert len(body['plantillas_existentes']) == 7
