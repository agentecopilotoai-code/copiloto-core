"""Tests TestClient para handlers del bloque 20 (utilidades EP-019/020)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import (
    router as gd_router,
    router_core as core_router,
    router_public as pub_router,
)
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
    app.include_router(core_router)
    app.include_router(pub_router)

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
        'app.gd.handlers.utilidades_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _evento_dict(**extra):
    base = {
        'id': uuid4(), 'tipo_evento': 'X', 'dominio': 'gd',
        'accion': 'crear', 'actor_type': 'user', 'actor_id': uuid4(),
        'entidad_tipo': 'radicado', 'entidad_id': uuid4(),
        'criticidad': 'media', 'request_id': None, 'ip': None,
        'valor_anterior': None, 'valor_nuevo': None,
        'justificacion': None, 'detalles': {},
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Auditoría
# =============================================================================
class TestAuditoriaHandlers:
    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/core/auditoria')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/core/auditoria?dominio=gd&tipo_evento=X'
            f'&actor_id={uuid4()}&entidad_tipo=radicado'
            f'&entidad_id={uuid4()}&criticidad=alta&limit=20',
        )
        assert r.status_code == 200

    def test_catalogo(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/core/auditoria/catalogo-eventos')
        assert r.status_code == 200

    def test_catalogo_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/core/auditoria/catalogo-eventos?dominio=gd&activo=true',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _evento_dict()
        r = client.get(f'/v1/core/auditoria/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_alta_emite_meta(self, conn, client):
        conn.fetchrow.return_value = _evento_dict(criticidad='alta')
        r = client.get(f'/v1/core/auditoria/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/core/auditoria/{uuid4()}')
        assert r.status_code == 404


# =============================================================================
# Constancia pública
# =============================================================================
class TestConstanciaPublica:
    def test_verificar_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'exposicion_publica': True,
            'numero_radicado': '2026-E-001',
            'fecha_radicacion': datetime.now(),
            'tipo_radicado': 'entrada', 'estado': 'radicado',
            'asunto': 'Mi solicitud',
            'dependencia_nombre': 'Talento',
        }
        conn.fetchval.return_value = True
        r = client.get('/gd/verificar/abc12345')
        assert r.status_code == 200
        assert r.json()['valida'] is True

    def test_verificar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get('/gd/verificar/inexistente')
        assert r.status_code == 404

    def test_verificar_codigo_muy_corto(self, conn, client):
        # min_length=8
        r = client.get('/gd/verificar/abc')
        assert r.status_code == 422

    def test_crear_constancia(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'codigo_verificacion': 'xyz123',
            'qr_url_publica': '/gd/verificar/xyz123',
            'fecha_generacion': datetime.now(),
            'exposicion_publica': True,
        }
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}/constancias',
        )
        assert r.status_code == 201


# =============================================================================
# Tipos doc identidad
# =============================================================================
class TestTiposDocHandlers:
    def test_catalogo_sin_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/catalogos/tipos-documento')
        assert r.status_code == 200

    def test_catalogo_con_pais(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/catalogos/tipos-documento?pais_iso=co')
        assert r.status_code == 200

    def test_org_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/organizacion/tipos-documento')
        assert r.status_code == 200

    def test_patch_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetch.return_value = []
        r = client.patch(
            '/v1/gd/organizacion/tipos-documento',
            json={'codigos_activos': ['CC', 'CE'],
                  'codigo_default': 'CC'},
        )
        assert r.status_code == 200

    def test_patch_default_invalido(self, conn, client):
        r = client.patch(
            '/v1/gd/organizacion/tipos-documento',
            json={'codigos_activos': ['CC'], 'codigo_default': 'NIT'},
        )
        assert r.status_code == 409

    def test_patch_codigo_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.patch(
            '/v1/gd/organizacion/tipos-documento',
            json={'codigos_activos': ['INEXISTENTE'],
                  'codigo_default': None},
        )
        assert r.status_code == 404


# =============================================================================
# Cambios dependencias
# =============================================================================
class TestCambiosDepHandlers:
    def test_historial(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/admin/estructura/dependencias/{uuid4()}/historial',
        )
        assert r.status_code == 200

    def test_fusionar_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = [
            {'id': uuid4()}, {'id': uuid4()}, {'id': uuid4()},
        ]
        r = client.post(
            '/v1/gd/admin/estructura/fusionar',
            json={
                'dependencias_origen': [str(uuid4()), str(uuid4())],
                'dependencia_destino_id': str(uuid4()),
                'fecha_vigencia': date.today().isoformat(),
                'motivo': 'fusión administrativa requerida' * 2,
            },
        )
        assert r.status_code == 201

    def test_fusionar_destino_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            '/v1/gd/admin/estructura/fusionar',
            json={
                'dependencias_origen': [str(uuid4())],
                'dependencia_destino_id': str(uuid4()),
                'fecha_vigencia': date.today().isoformat(),
                'motivo': 'X' * 11,
            },
        )
        assert r.status_code == 404


# =============================================================================
# Contingencia
# =============================================================================
class TestContingenciaHandler:
    def test_radicar(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'numero_radicado': 'MANUAL-001',
            'tipo_radicado': 'entrada',
            'fecha_radicacion': datetime.now(),
            'fecha_radicacion_real': datetime(2026, 5, 23, 10, 0),
            'es_radicacion_contingencia': True,
            'created_at': datetime.now(),
        }
        r = client.post(
            '/v1/gd/ventanilla/radicados/contingencia',
            json={
                'numero_radicado_manual': 'MANUAL-001',
                'fecha_radicacion_real': '2026-05-23T10:00:00',
                'justificacion': 'caída sistema 3 horas X' * 2,
                'evidencia_contingencia_archivo_id': str(uuid4()),
                'canal_id': str(uuid4()),
                'asunto': 'Petición urgente',
            },
        )
        assert r.status_code == 201
        assert r.json()['es_contingencia'] is True


# =============================================================================
# Hoja control + índice
# =============================================================================
class TestHojaControlHandlers:
    def test_get_hoja_control(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(f'/v1/gd/expedientes/{uuid4()}/hoja-control')
        assert r.status_code == 200

    def test_generar_indice_ok(self, conn, client):
        conn.fetchval.side_effect = [1, 0]
        conn.fetch.side_effect = [[], []]
        conn.fetchrow.return_value = {
            'id': uuid4(), 'expediente_id': uuid4(),
            'version_indice': 1, 'generado_en': datetime.now(),
            'generado_por_user_id': uuid4(),
            'contenido_jsonb': {}, 'hash_sha256': 'abc',
        }
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/indice-electronico',
        )
        assert r.status_code == 201

    def test_generar_indice_expediente_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/expedientes/{uuid4()}/indice-electronico',
        )
        assert r.status_code == 404
