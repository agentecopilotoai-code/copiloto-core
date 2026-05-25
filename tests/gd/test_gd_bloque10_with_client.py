"""Tests TestClient para handlers del bloque 10 (documentos EP-009)."""
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


def _perfil() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {'PERM-USR-001': 'global'}


async def _noop_emit(*args, **kwargs):
    return uuid4()


def build_app(conn_mock) -> FastAPI:
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
        'app.gd.handlers.documentos_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _doc_dict(**extra):
    base = {
        'id': uuid4(), 'titulo': 'Doc',
        'descripcion': None, 'clasificacion_informacion': 'interna',
        'trd_serie_codigo': None, 'trd_subserie_codigo': None,
        'trd_tipo_documental': None,
        'estado': 'activo', 'version_vigente_id': uuid4(),
        'numero_version_vigente': 1,
        'anulado_en': None, 'motivo_anulacion': None,
        'reemplazado_por_documento_id': None,
        'creado_por_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _ver_dict(numero=1, **extra):
    base = {
        'id': uuid4(), 'documento_id': uuid4(),
        'numero_version': numero, 'archivo_digital_id': uuid4(),
        'mime_type': 'application/pdf', 'tamano_bytes': 1024,
        'hash_sha256': 'abc', 'estado': 'borrador',
        'creado_por_user_id': uuid4(),
        'aprobado_por_user_id': None, 'firmado_por_user_id': None,
        'observaciones': None, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Documentos
# =============================================================================
class TestDocumentosHandlers:
    def test_crear_ok(self, conn, client):
        ver_id = uuid4()
        conn.fetchrow.side_effect = [
            _doc_dict(version_vigente_id=None),
            _ver_dict(numero=1),
            _doc_dict(version_vigente_id=ver_id),
        ]
        r = client.post(
            '/v1/gd/documentos',
            json={
                'titulo': 'Mi documento',
                'archivo_digital_id': str(uuid4()),
                'mime_type': 'application/pdf',
                'tamano_bytes': 1024,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()['titulo'] == 'Doc'

    def test_crear_415_mime(self, conn, client):
        r = client.post(
            '/v1/gd/documentos',
            json={
                'titulo': 'Mi documento',
                'archivo_digital_id': str(uuid4()),
                'mime_type': 'application/x-executable',
                'tamano_bytes': 100,
            },
        )
        assert r.status_code == 415

    def test_crear_413_tamano(self, conn, client):
        r = client.post(
            '/v1/gd/documentos',
            json={
                'titulo': 'Mi documento',
                'archivo_digital_id': str(uuid4()),
                'mime_type': 'application/pdf',
                'tamano_bytes': 200 * 1024 * 1024,
            },
        )
        assert r.status_code == 413

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/v1/gd/documentos')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            '/v1/gd/documentos?estado=activo&clasificacion=publica,interna'
            '&trd_serie=S1&q=test&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _doc_dict()
        conn.fetch.return_value = [_ver_dict()]
        r = client.get(f'/v1/gd/documentos/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/documentos/{uuid4()}')
        assert r.status_code == 404

    def test_nueva_version_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'activo', 'numero_version_vigente': 1},
            _ver_dict(numero=2),
        ]
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/versiones',
            json={
                'archivo_digital_id': str(uuid4()),
                'mime_type': 'application/pdf',
                'tamano_bytes': 2048,
            },
        )
        assert r.status_code == 201, r.text

    def test_nueva_version_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/versiones',
            json={'archivo_digital_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_nueva_version_409(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'anulado',
                                       'numero_version_vigente': 1}
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/versiones',
            json={'archivo_digital_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_nueva_version_415(self, conn, client):
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/versiones',
            json={
                'archivo_digital_id': str(uuid4()),
                'mime_type': 'application/x-exe',
            },
        )
        assert r.status_code == 415

    def test_listar_versiones(self, conn, client):
        conn.fetch.return_value = [_ver_dict(numero=2), _ver_dict(numero=1)]
        r = client.get(f'/v1/gd/documentos/{uuid4()}/versiones')
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_anular_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'activo'},
            _doc_dict(estado='anulado'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/anular',
            json={'motivo': 'duplicado por error'},
        )
        assert r.status_code == 200

    def test_anular_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_anular_409(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'anulado'}
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_reemplazar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'activo', 'version_vigente_id': uuid4(),
             'numero_version_vigente': 1},
            _ver_dict(numero=2),
        ]
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/reemplazar',
            json={
                'archivo_digital_id': str(uuid4()),
                'motivo': 'nueva versión final',
                'mime_type': 'application/pdf',
                'tamano_bytes': 1500,
            },
        )
        assert r.status_code == 201

    def test_reemplazar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/reemplazar',
            json={'archivo_digital_id': str(uuid4()), 'motivo': 'XXXXX'},
        )
        assert r.status_code == 404

    def test_reemplazar_415(self, conn, client):
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/reemplazar',
            json={
                'archivo_digital_id': str(uuid4()),
                'motivo': 'XXXXX',
                'mime_type': 'application/x-exe',
            },
        )
        assert r.status_code == 415

    def test_relacionar_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'documento_id': uuid4(),
            'entidad_tipo': 'radicado', 'entidad_id': uuid4(),
            'rol': 'principal', 'creado_por_user_id': uuid4(),
            'created_at': datetime.now(),
        }
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/relacionar',
            json={
                'entidad_tipo': 'radicado',
                'entidad_id': str(uuid4()),
                'rol': 'principal',
            },
        )
        assert r.status_code == 201

    def test_relacionar_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/relacionar',
            json={
                'entidad_tipo': 'pqrsd',
                'entidad_id': str(uuid4()),
            },
        )
        assert r.status_code == 404


# =============================================================================
# Anexos
# =============================================================================
class TestAnexosHandlers:
    def test_crear_anexo_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'archivo_digital_id': uuid4(),
            'entidad_relacionada_tipo': 'pqrsd',
            'entidad_relacionada_id': uuid4(),
            'titulo': 'Anexo', 'descripcion': None,
            'mime_type': 'application/pdf', 'tamano_bytes': 1024,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = client.post(
            '/v1/gd/anexos',
            json={
                'archivo_digital_id': str(uuid4()),
                'entidad_relacionada_tipo': 'pqrsd',
                'entidad_relacionada_id': str(uuid4()),
                'titulo': 'Anexo',
                'mime_type': 'application/pdf',
                'tamano_bytes': 1024,
            },
        )
        assert r.status_code == 201

    def test_listar_anexos(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/v1/gd/anexos')
        assert r.status_code == 200

    def test_listar_anexos_filtrado(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            f'/v1/gd/anexos?entidad_tipo=radicado&entidad_id={uuid4()}',
        )
        assert r.status_code == 200


# =============================================================================
# Descarga
# =============================================================================
class TestDescargaHandler:
    def test_descargar_sin_documento(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'descargado_en': datetime.now(),
            'clasificacion_informacion': 'interna',
        }
        r = client.post(
            f'/v1/gd/archivos/{uuid4()}/descargar',
        )
        assert r.status_code == 200, r.text
        assert r.json()['clasificacion_informacion'] == 'interna'

    def test_descargar_con_documento_reservada(self, conn, client):
        # 1. fetchrow para clasificacion del documento
        # 2. fetchrow para insertar descarga_log
        conn.fetchrow.side_effect = [
            {'clasificacion_informacion': 'reservada'},
            {'id': uuid4(), 'descargado_en': datetime.now(),
             'clasificacion_informacion': 'reservada'},
        ]
        r = client.post(
            f'/v1/gd/archivos/{uuid4()}/descargar'
            f'?documento_id={uuid4()}',
        )
        assert r.status_code == 200
        assert r.json()['clasificacion_informacion'] == 'reservada'

    def test_descargar_documento_no_existe(self, conn, client):
        conn.fetchrow.return_value = None  # documento no existe
        r = client.post(
            f'/v1/gd/archivos/{uuid4()}/descargar'
            f'?documento_id={uuid4()}',
        )
        assert r.status_code == 404
