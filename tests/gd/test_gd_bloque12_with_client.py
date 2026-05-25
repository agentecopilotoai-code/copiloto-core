"""Tests TestClient para handlers del bloque 12 (firmas EP-011)."""
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
        'app.gd.handlers.firmas_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _esc_dict(estado='pendiente_autorizacion', **extra):
    base = {
        'id': uuid4(), 'user_id': uuid4(), 'archivo_digital_id': uuid4(),
        'mime_type': 'image/png', 'tamano_bytes': 1024,
        'hash_sha256': 'abc', 'estado': estado,
        'autorizada_por_user_id': None, 'fecha_autorizacion': None,
        'motivo_revocacion': None, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _firma_doc_dict(estado='consumada', tipo='electronica', **extra):
    base = {
        'id': uuid4(),
        'documento_id': uuid4(), 'version_documento_id': uuid4(),
        'firmante_user_id': uuid4(),
        'tipo_firma': tipo, 'estado': estado,
        'firma_escaneada_id': None, 'certificado_id': None,
        'proveedor_firma_digital': None,
        'hash_archivo': 'abc123', 'hash_algoritmo': 'sha256',
        'snapshot_firmante': {'user_id': 'x', 'email': 'u@x'},
        'ip': '1.2.3.4', 'user_agent': 'ua',
        'fecha_firma': datetime.now(),
        'fecha_rechazo': None, 'fecha_revocacion': None,
        'observaciones_rechazo': None, 'motivo_revocacion': None,
        'step_up_requerido': False, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Firma escaneada handlers
# =============================================================================
class TestEscaneadaHandlers:
    def test_registrar_ok(self, conn, client):
        conn.fetchrow.return_value = _esc_dict()
        r = client.post(
            '/v1/gd/firmas/escaneadas',
            json={'archivo_digital_id': str(uuid4()),
                  'mime_type': 'image/png'},
        )
        assert r.status_code == 201, r.text

    def test_registrar_duplicada(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/v1/gd/firmas/escaneadas',
            json={'archivo_digital_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_listar_sin_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/firmas/escaneadas')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/firmas/escaneadas?user_id={uuid4()}'
            '&estado=activa&limit=10',
        )
        assert r.status_code == 200

    def test_autorizar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'user_id': uuid4(), 'estado': 'pendiente_autorizacion'},
            _esc_dict(estado='activa'),
        ]
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/autorizar', json={},
        )
        assert r.status_code == 200

    def test_autorizar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/autorizar', json={},
        )
        assert r.status_code == 404

    def test_autorizar_409(self, conn, client):
        conn.fetchrow.return_value = {
            'user_id': uuid4(), 'estado': 'activa',
        }
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/autorizar', json={},
        )
        assert r.status_code == 409

    def test_revocar_ok(self, conn, client):
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _esc_dict(estado='revocada',
                                                 motivo_revocacion='X')
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/revocar',
            json={'motivo': 'ya no se usa'},
        )
        assert r.status_code == 200

    def test_revocar_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/revocar',
            json={'motivo': 'X' * 6},
        )
        assert r.status_code == 404

    def test_revocar_409(self, conn, client):
        conn.fetchval.return_value = 'revocada'
        r = client.post(
            f'/v1/gd/firmas/escaneadas/{uuid4()}/revocar',
            json={'motivo': 'X' * 6},
        )
        assert r.status_code == 409


# =============================================================================
# Firma electrónica documento
# =============================================================================
class TestFirmarElectronicaHandler:
    def _setup_mocks_ok(self, conn, estado='consumada'):
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _firma_doc_dict(estado=estado),
        ]
        conn.fetchval.return_value = 'activo'

    def test_firmar_ok(self, conn, client):
        self._setup_mocks_ok(conn)
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-electronica',
            json={'version_documento_id': str(uuid4()),
                  'step_up_satisfecho': True},
        )
        assert r.status_code == 201, r.text

    def test_firmar_doc_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-electronica',
            json={'version_documento_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_firmar_doc_anulado(self, conn, client):
        conn.fetchrow.return_value = {
            'doc_estado': 'anulado', 'ver_estado': 'aprobada',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-electronica',
            json={'version_documento_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_firmar_version_borrador(self, conn, client):
        conn.fetchrow.return_value = {
            'doc_estado': 'activo', 'ver_estado': 'borrador',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-electronica',
            json={'version_documento_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_firmar_firmante_inactivo(self, conn, client):
        conn.fetchrow.return_value = {
            'doc_estado': 'activo', 'ver_estado': 'aprobada',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        conn.fetchval.return_value = 'suspendido'
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-electronica',
            json={'version_documento_id': str(uuid4())},
        )
        assert r.status_code == 409


# =============================================================================
# Firma digital
# =============================================================================
class TestFirmarDigitalHandler:
    def test_firmar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _firma_doc_dict(tipo='digital', certificado_id='cert1',
                             proveedor_firma_digital='stub'),
        ]
        conn.fetchval.return_value = 'activo'
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-digital',
            json={'version_documento_id': str(uuid4()),
                  'certificado_id': 'cert1', 'proveedor': 'stub'},
            headers={'X-Signing-Pin': '0000'},
        )
        assert r.status_code == 201, r.text

    def test_firmar_sin_pin(self, conn, client):
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-digital',
            json={'version_documento_id': str(uuid4()),
                  'certificado_id': 'cert1', 'proveedor': 'stub'},
        )
        assert r.status_code == 422
        assert r.json()['detail']['code'] == 'pin_requerido'

    def test_firmar_pin_invalido(self, conn, client):
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
        ]
        conn.fetchval.return_value = 'activo'
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-digital',
            json={'version_documento_id': str(uuid4()),
                  'certificado_id': 'cert1', 'proveedor': 'stub'},
            headers={'X-Signing-Pin': 'WRONG'},
        )
        assert r.status_code == 409


# =============================================================================
# Firma escaneada aplicada
# =============================================================================
class TestFirmarEscaneadaAplicada:
    def test_firmar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'user_id': ACTOR, 'estado': 'activa'},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _firma_doc_dict(tipo='escaneada'),
        ]
        conn.fetchval.return_value = 'activo'
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-escaneada'
            f'?version_documento_id={uuid4()}&firma_escaneada_id={uuid4()}',
        )
        assert r.status_code == 201, r.text

    def test_firmar_escaneada_no_existe(self, conn, client):
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            None,
        ]
        conn.fetchval.return_value = 'activo'
        r = client.post(
            f'/v1/gd/documentos/{uuid4()}/firmar-escaneada'
            f'?version_documento_id={uuid4()}&firma_escaneada_id={uuid4()}',
        )
        assert r.status_code == 404


# =============================================================================
# Rechazo / revocación / evidencia
# =============================================================================
class TestRechazoEvidenciaHandlers:
    def test_rechazar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'firmante_user_id': uuid4()},
            _firma_doc_dict(estado='rechazada'),
        ]
        r = client.post(
            f'/v1/gd/firmas/{uuid4()}/rechazar',
            json={'observacion': 'no acepto'},
        )
        assert r.status_code == 200

    def test_rechazar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/firmas/{uuid4()}/rechazar',
            json={'observacion': 'X' * 6},
        )
        assert r.status_code == 404

    def test_rechazar_409(self, conn, client):
        conn.fetchrow.return_value = {
            'estado': 'consumada', 'firmante_user_id': uuid4(),
        }
        r = client.post(
            f'/v1/gd/firmas/{uuid4()}/rechazar',
            json={'observacion': 'X' * 6},
        )
        assert r.status_code == 409

    def test_revocar_ok(self, conn, client):
        conn.fetchval.return_value = 'consumada'
        conn.fetchrow.return_value = _firma_doc_dict(estado='revocada')
        r = client.post(
            f'/v1/gd/firmas/{uuid4()}/revocar',
            json={'motivo': 'compromiso seguridad'},
        )
        assert r.status_code == 200

    def test_revocar_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/firmas/{uuid4()}/revocar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_evidencia_ok(self, conn, client):
        row = _firma_doc_dict()
        row['documento_titulo'] = 'Doc X'
        row['documento_version'] = 1
        conn.fetchrow.return_value = row
        r = client.get(
            f'/v1/gd/firmas/{uuid4()}/evidencia',
        )
        assert r.status_code == 200, r.text
        assert r.json()['documento_titulo'] == 'Doc X'

    def test_evidencia_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(
            f'/v1/gd/firmas/{uuid4()}/evidencia',
        )
        assert r.status_code == 404

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/firmas')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/firmas?documento_id={uuid4()}'
            f'&firmante_user_id={uuid4()}&estado=consumada&limit=20',
        )
        assert r.status_code == 200
