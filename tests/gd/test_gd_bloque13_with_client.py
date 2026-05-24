"""Tests TestClient para handlers del bloque 13 (correo institucional EP-012)."""
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
        'app.gd.handlers.correo_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _bz_dict(estado='activa', **extra):
    base = {
        'id': uuid4(), 'nombre': 'Buzón',
        'direccion_correo': 'inbox@org.gov.co',
        'proveedor': 'imap_generico', 'dependencia_id': None,
        'host': 'imap.org', 'port': 993, 'usar_tls': True,
        'usuario_smtp': 'u', 'config': {}, 'secret_vault_ref': 'vault/b',
        'ultima_lectura_en': None,
        'envio_acuse_recibido': False, 'plantilla_acuse_id': None,
        'estado': estado, 'ultimo_error_texto': None, 'ultimo_error_en': None,
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _correo_dict(estado='pendiente', **extra):
    base = {
        'id': uuid4(), 'buzon_id': uuid4(),
        'message_id': 'm1', 'remitente_email': 'a@x.com',
        'remitente_nombre': 'Alice',
        'destinatarios_to': ['inbox@org.gov.co'],
        'destinatarios_cc': [], 'destinatarios_bcc': [],
        'asunto': 'Hi', 'cuerpo_texto': 'body', 'cuerpo_html': None,
        'fecha_envio_original': datetime.now(),
        'importado_en': datetime.now(),
        'anexos_archivo_ids': [],
        'estado': estado, 'radicado_id': None,
        'convertido_por_user_id': None, 'fecha_decision': None,
        'motivo_descarte': None, 'observaciones': None,
        'acuse_enviado_en': None, 'acuse_estado': None,
    }
    base.update(extra)
    return base


# =============================================================================
# Buzones
# =============================================================================
class TestBuzonHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.return_value = _bz_dict()
        r = client.post(
            '/api/v1/gd/correo/buzones',
            json={
                'nombre': 'Mi Buzón',
                'direccion_correo': 'inbox@org.gov.co',
                'proveedor': 'imap_generico',
                'secret_vault_ref': 'vault/buzon-1',
            },
        )
        assert r.status_code == 201, r.text

    def test_crear_email_invalido(self, conn, client):
        r = client.post(
            '/api/v1/gd/correo/buzones',
            json={
                'nombre': 'X',
                'direccion_correo': 'sinarroba',
                'proveedor': 'imap_generico',
                'secret_vault_ref': 'v',
            },
        )
        assert r.status_code == 422

    def test_crear_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/correo/buzones',
            json={
                'nombre': 'Mi Buzón',
                'direccion_correo': 'dup@org.gov.co',
                'proveedor': 'imap_generico',
                'secret_vault_ref': 'vault/x',
            },
        )
        assert r.status_code == 409

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/correo/buzones')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/correo/buzones?estado=activa'
            f'&dependencia_id={uuid4()}&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _bz_dict()
        r = client.get(f'/api/v1/gd/correo/buzones/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/gd/correo/buzones/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _bz_dict(nombre='Renamed')
        r = client.patch(
            f'/api/v1/gd/correo/buzones/{uuid4()}',
            json={'nombre': 'Renamed', 'config': {'k': 'v'}},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.patch(
            f'/api/v1/gd/correo/buzones/{uuid4()}',
            json={'nombre': 'Renamed Plus'},
        )
        assert r.status_code == 404

    def test_probar_conexion_ok(self, conn, client):
        conn.fetchrow.return_value = _bz_dict()
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/probar-conexion',
            json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()['exitoso'] is True

    def test_probar_conexion_falla(self, conn, client):
        conn.fetchrow.return_value = _bz_dict(secret_vault_ref='invalid')
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/probar-conexion',
            json={},
        )
        assert r.status_code == 200
        assert r.json()['exitoso'] is False

    def test_probar_conexion_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/probar-conexion',
            json={},
        )
        assert r.status_code == 404

    def test_ejecutar_worker_ok(self, conn, client):
        bz = _bz_dict(config={'seed_correos': [
            {'message_id': 'm1', 'remitente_email': 'a@x.com'},
        ]})
        conn.fetchrow.side_effect = [bz, {'id': uuid4()}]
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/ejecutar-worker',
            json={'max_correos': 10},
        )
        assert r.status_code == 200, r.text
        assert r.json()['correos_nuevos'] == 1

    def test_ejecutar_worker_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/ejecutar-worker',
            json={},
        )
        assert r.status_code == 404

    def test_ejecutar_worker_buzon_inactivo(self, conn, client):
        conn.fetchrow.return_value = _bz_dict(estado='inactiva')
        r = client.post(
            f'/api/v1/gd/correo/buzones/{uuid4()}/ejecutar-worker',
            json={},
        )
        assert r.status_code == 409


# =============================================================================
# Correos importados
# =============================================================================
class TestCorreoHandlers:
    def test_listar_sin_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/api/v1/gd/correo/correos')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            f'/api/v1/gd/correo/correos?buzon_id={uuid4()}'
            '&estado=pendiente&remitente_email=a@x.com&limit=20',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _correo_dict()
        r = client.get(f'/api/v1/gd/correo/correos/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/gd/correo/correos/{uuid4()}')
        assert r.status_code == 404

    def test_asociar_radicado_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            _correo_dict(estado='asociado_radicado'),
        ]
        conn.fetchval.return_value = 1
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/asociar-radicado/{uuid4()}',
            json={'observaciones': 'ok'},
        )
        assert r.status_code == 200

    def test_asociar_radicado_no_existe(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'pendiente'}
        conn.fetchval.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/asociar-radicado/{uuid4()}',
            json={},
        )
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'radicado_no_existe'

    def test_asociar_correo_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/asociar-radicado/{uuid4()}',
            json={},
        )
        assert r.status_code == 404

    def test_asociar_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'descartado'}
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/asociar-radicado/{uuid4()}',
            json={},
        )
        assert r.status_code == 409

    def test_descartar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            _correo_dict(estado='descartado', motivo_descarte='spam'),
        ]
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/descartar',
            json={'motivo': 'es spam evidente del proveedor'},
        )
        assert r.status_code == 200

    def test_descartar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/descartar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_descartar_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'convertido_radicado'}
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/descartar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_convertir_ok(self, conn, client, monkeypatch):
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-9'}
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'a@x.com', 'remitente_nombre': None,
             'asunto': 'Sub', 'cuerpo_texto': 'body',
             'envio_acuse_recibido': False, 'host': None, 'port': None,
             'usar_tls': True, 'usuario_smtp': None,
             'secret_vault_ref': 'v', 'config': {}},
            _correo_dict(estado='convertido_radicado', radicado_id=rad_id),
        ]
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/convertir-a-radicado',
            json={'canal_id': str(uuid4())},
        )
        assert r.status_code == 201, r.text

    def test_convertir_correo_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/convertir-a-radicado',
            json={'canal_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_convertir_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {
            'estado': 'convertido_radicado', 'buzon_id': uuid4(),
            'remitente_email': 'a@x.com', 'remitente_nombre': None,
            'asunto': None, 'cuerpo_texto': None,
            'envio_acuse_recibido': False, 'host': None, 'port': None,
            'usar_tls': True, 'usuario_smtp': None,
            'secret_vault_ref': 'v', 'config': {},
        }
        r = client.post(
            f'/api/v1/gd/correo/correos/{uuid4()}/convertir-a-radicado',
            json={'canal_id': str(uuid4())},
        )
        assert r.status_code == 409
