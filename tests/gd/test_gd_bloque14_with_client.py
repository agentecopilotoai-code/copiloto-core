"""Tests TestClient para handlers del bloque 14 (IA EP-013)."""
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
        'app.gd.handlers.ia_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _sol_dict(tipo='clasificacion', estado='completed', **extra):
    base = {
        'id': uuid4(), 'tipo_asistencia': tipo,
        'entidad_origen_tipo': 'radicado',
        'entidad_origen_id': uuid4(),
        'estado': estado, 'payload_original': {},
        'datos_redactados': {}, 'redacciones_aplicadas': [],
        'proveedor': 'StubIAProvider',
        'error_texto': None, 'error_codigo': None,
        'solicitante_user_id': uuid4(),
        'inicio_procesamiento_en': None, 'fin_procesamiento_en': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _res_dict(**extra):
    base = {
        'id': uuid4(), 'solicitud_id': uuid4(),
        'contenido': {'tipo_clasificacion_sugerido': 'tramite'},
        'confianza': 0.5, 'explicacion': 'stub',
        'modelo': 'stub-v1',
        'tokens_input': 5, 'tokens_output': 3, 'timing_ms': 2,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _decision_dict(**extra):
    base = {
        'id': uuid4(), 'resultado_id': uuid4(),
        'decision': 'aceptar', 'contenido_modificado': None,
        'observaciones': None, 'decided_by_user_id': uuid4(),
        'decided_at': datetime.now(),
        'materializado_endpoint': None, 'materializado_entidad_id': None,
    }
    base.update(extra)
    return base


# Helper: prepara los 4 fetchrows comunes para orquestar.
# 1. encolar insert
# 2. ejecutar select solicitud
# 3. ejecutar insert resultado
# 4. obtener_solicitud al final
def _mocks_orquesta(conn, tipo='clasificacion'):
    conn.fetchrow.side_effect = [
        _sol_dict(tipo=tipo, estado='pending'),      # encolar
        {'tipo_asistencia': tipo, 'estado': 'pending',
         'datos_redactados': {'texto': 'tengo una queja'}},  # ejecutar SELECT
        _res_dict(),                                  # ejecutar INSERT resultado
        _sol_dict(tipo=tipo, estado='completed'),    # obtener_solicitud final
    ]


# =============================================================================
# Endpoints por tipo
# =============================================================================
class TestEndpointsTipos:
    def test_clasificar(self, conn, client):
        _mocks_orquesta(conn, tipo='clasificacion')
        r = client.post(
            '/v1/gd/ia/clasificar',
            json={'entidad_origen_tipo': 'radicado',
                  'entidad_origen_id': str(uuid4())},
        )
        assert r.status_code == 201, r.text
        assert r.json()['resultado']['confianza'] == 0.5

    def test_extraer(self, conn, client):
        _mocks_orquesta(conn, tipo='extraccion')
        r = client.post(
            '/v1/gd/ia/extraer',
            json={'entidad_origen_tipo': 'pqrsd',
                  'entidad_origen_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_resumir(self, conn, client):
        _mocks_orquesta(conn, tipo='resumen')
        r = client.post(
            '/v1/gd/ia/resumir',
            json={'entidad_origen_tipo': 'pqrsd',
                  'entidad_origen_id': str(uuid4()),
                  'max_caracteres': 300},
        )
        assert r.status_code == 201

    def test_sugerir_dependencia(self, conn, client):
        _mocks_orquesta(conn, tipo='sugerencia_dependencia')
        r = client.post(
            '/v1/gd/ia/sugerir-dependencia',
            json={'entidad_origen_tipo': 'radicado',
                  'entidad_origen_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_detectar_duplicados(self, conn, client):
        _mocks_orquesta(conn, tipo='deteccion_duplicados')
        r = client.post(
            '/v1/gd/ia/detectar-duplicados',
            json={'entidad_origen_tipo': 'radicado',
                  'entidad_origen_id': str(uuid4()),
                  'top_k': 3},
        )
        assert r.status_code == 201

    def test_borrador_respuesta(self, conn, client):
        _mocks_orquesta(conn, tipo='borrador_respuesta')
        r = client.post(
            '/v1/gd/ia/borrador-respuesta',
            json={'entidad_origen_tipo': 'pqrsd',
                  'entidad_origen_id': str(uuid4()),
                  'plantilla_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_sugerir_termino(self, conn, client):
        _mocks_orquesta(conn, tipo='sugerencia_termino')
        r = client.post(
            '/v1/gd/ia/sugerir-termino',
            json={'entidad_origen_tipo': 'pqrsd',
                  'entidad_origen_id': str(uuid4())},
        )
        assert r.status_code == 201


# =============================================================================
# Lectura
# =============================================================================
class TestLectura:
    def test_detalle_solicitud_ok(self, conn, client):
        conn.fetchrow.return_value = _sol_dict()
        r = client.get(f'/v1/gd/ia/solicitudes/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_solicitud_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/ia/solicitudes/{uuid4()}')
        assert r.status_code == 404

    def test_detalle_resultado_ok(self, conn, client):
        conn.fetchrow.return_value = _res_dict()
        r = client.get(f'/v1/gd/ia/resultados/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_resultado_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/ia/resultados/{uuid4()}')
        assert r.status_code == 404


# =============================================================================
# Decisión humana
# =============================================================================
class TestDecidir:
    def test_aceptar(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _decision_dict(decision='aceptar')
        r = client.post(
            f'/v1/gd/ia/sugerencias/{uuid4()}/decidir',
            json={'decision': 'aceptar'},
        )
        assert r.status_code == 201

    def test_modificar_con_contenido(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _decision_dict(
            decision='modificar', contenido_modificado={'x': 1},
        )
        r = client.post(
            f'/v1/gd/ia/sugerencias/{uuid4()}/decidir',
            json={'decision': 'modificar',
                  'contenido_modificado': {'x': 1},
                  'observaciones': 'cambié'},
        )
        assert r.status_code == 201

    def test_rechazar(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _decision_dict(decision='rechazar')
        r = client.post(
            f'/v1/gd/ia/sugerencias/{uuid4()}/decidir',
            json={'decision': 'rechazar', 'observaciones': 'no útil'},
        )
        assert r.status_code == 201

    def test_resultado_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/ia/sugerencias/{uuid4()}/decidir',
            json={'decision': 'aceptar'},
        )
        assert r.status_code == 404

    def test_duplicada(self, conn, client):
        import asyncpg
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            f'/v1/gd/ia/sugerencias/{uuid4()}/decidir',
            json={'decision': 'aceptar'},
        )
        assert r.status_code == 409


# =============================================================================
# Trazabilidad
# =============================================================================
class TestTrazabilidad:
    def test_vacia(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/ia/trazabilidad?entidad_tipo=radicado'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 200
        assert r.json()['total'] == 0

    def test_con_solicitud_sin_resultado(self, conn, client):
        conn.fetch.return_value = [_sol_dict()]
        conn.fetchrow.return_value = None
        r = client.get(
            f'/v1/gd/ia/trazabilidad?entidad_tipo=pqrsd'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 200
        assert r.json()['total'] == 1

    def test_completa(self, conn, client):
        conn.fetch.return_value = [_sol_dict()]
        conn.fetchrow.side_effect = [_res_dict(), _decision_dict()]
        r = client.get(
            f'/v1/gd/ia/trazabilidad?entidad_tipo=pqrsd'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 200
        body = r.json()
        assert body['total'] == 1
        assert body['historial'][0]['decision'] is not None

    def test_entidad_tipo_invalido(self, conn, client):
        r = client.get(
            f'/v1/gd/ia/trazabilidad?entidad_tipo=invalido'
            f'&entidad_id={uuid4()}',
        )
        assert r.status_code == 422
