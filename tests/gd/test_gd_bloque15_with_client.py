"""Tests TestClient para handlers del bloque 15 (reportes EP-014)."""
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
        'app.gd.handlers.reportes_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _reporte_gen_dict(**extra):
    base = {
        'id': uuid4(), 'tipo_reporte': 'radicados',
        'parametros': {}, 'formato': 'csv',
        'archivo_digital_id': None, 'resumen_inline': {'x': 1},
        'numero_filas': 1, 'contiene_datos_sensibles': False,
        'estado': 'completed', 'error_texto': None,
        'generado_por_user_id': uuid4(),
        'inicio_en': datetime.now(), 'fin_en': datetime.now(),
        'duracion_ms': 5, 'expira_en': None,
    }
    base.update(extra)
    return base


# =============================================================================
# GET reportes
# =============================================================================
class TestGets:
    def test_radicados_basico(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/v1/gd/reportes/radicados')
        assert r.status_code == 200

    def test_radicados_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            '/v1/gd/reportes/radicados'
            f'?desde=2026-01-01T00:00:00&hasta=2026-12-31T23:59:59'
            f'&canal_id={uuid4()}&dependencia_id={uuid4()}'
            '&tipo_radicado=entrada&estado=radicado',
        )
        assert r.status_code == 200

    def test_pqrsd_basico(self, conn, client):
        conn.fetchrow.return_value = {
            'total_global': 5, 'total_vencidas': 1,
            'total_proximas_vencer': 0, 'total_cerradas': 2,
        }
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/pqrsd')
        assert r.status_code == 200

    def test_pqrsd_con_filtros(self, conn, client):
        conn.fetchrow.return_value = {
            'total_global': 0, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/reportes/pqrsd?dependencia_id={uuid4()}'
            '&solo_vencidas=true&solo_proximas_vencer=true&estado=asignada',
        )
        assert r.status_code == 200

    def test_correspondencia(self, conn, client):
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/correspondencia')
        assert r.status_code == 200

    def test_correspondencia_con_filtros(self, conn, client):
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/reportes/correspondencia?tipo=interna'
            f'&dependencia_id={uuid4()}&estado=enviada',
        )
        assert r.status_code == 200

    def test_cargas(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/cargas')
        assert r.status_code == 200

    def test_cargas_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/reportes/cargas?dependencia_id={uuid4()}'
            f'&user_id={uuid4()}',
        )
        assert r.status_code == 200

    def test_uso_ia(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/uso-ia')
        assert r.status_code == 200

    def test_uso_ia_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/reportes/uso-ia?tipo_asistencia=clasificacion',
        )
        assert r.status_code == 200

    def test_anulaciones(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/anulaciones')
        assert r.status_code == 200

    def test_anulaciones_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/reportes/anulaciones'
            '?tipo_entidad=radicado&decision=aprobada',
        )
        assert r.status_code == 200

    def test_auditoria(self, conn, client):
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/auditoria')
        assert r.status_code == 200

    def test_auditoria_con_filtros(self, conn, client):
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/reportes/auditoria?usuario_id={uuid4()}'
            '&entidad_tipo=documento',
        )
        assert r.status_code == 200


# =============================================================================
# Exportar
# =============================================================================
class TestExportar:
    def _setup_export_mocks(self, conn, tipo='radicados', sensible=False):
        # fetch (datos), fetchval (totales si aplica), fetchrow (registrar)
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        conn.fetchrow.return_value = _reporte_gen_dict(
            tipo_reporte=tipo, contiene_datos_sensibles=sensible,
        )

    def test_radicados(self, conn, client):
        self._setup_export_mocks(conn, 'radicados')
        r = client.post(
            '/v1/gd/reportes/radicados/exportar',
            json={'formato': 'csv', 'filtros': {}},
        )
        assert r.status_code == 201, r.text

    def test_radicados_pdf(self, conn, client):
        self._setup_export_mocks(conn, 'radicados')
        r = client.post(
            '/v1/gd/reportes/radicados/exportar',
            json={'formato': 'pdf', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_radicados_formato_invalido(self, conn, client):
        r = client.post(
            '/v1/gd/reportes/radicados/exportar',
            json={'formato': 'xml', 'filtros': {}},
        )
        # Pydantic Literal rechaza 'xml' → 422
        assert r.status_code == 422

    def test_pqrsd(self, conn, client):
        # 2 fetchrows: totales + registrar
        conn.fetchrow.side_effect = [
            {'total_global': 0, 'total_vencidas': 0,
             'total_proximas_vencer': 0, 'total_cerradas': 0},
            _reporte_gen_dict(tipo_reporte='pqrsd', formato='json'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            '/v1/gd/reportes/pqrsd/exportar',
            json={'formato': 'json', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_correspondencia(self, conn, client):
        self._setup_export_mocks(conn, 'correspondencia')
        r = client.post(
            '/v1/gd/reportes/correspondencia/exportar',
            json={'formato': 'csv', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_cargas(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = _reporte_gen_dict(
            tipo_reporte='cargas_trabajo',
        )
        r = client.post(
            '/v1/gd/reportes/cargas/exportar',
            json={'formato': 'csv', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_uso_ia(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = _reporte_gen_dict(tipo_reporte='uso_ia')
        r = client.post(
            '/v1/gd/reportes/uso-ia/exportar',
            json={'formato': 'excel', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_anulaciones(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = _reporte_gen_dict(
            tipo_reporte='anulaciones_reasignaciones',
        )
        r = client.post(
            '/v1/gd/reportes/anulaciones/exportar',
            json={'formato': 'csv', 'filtros': {}},
        )
        assert r.status_code == 201

    def test_auditoria_marca_sensible(self, conn, client):
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        conn.fetchrow.return_value = _reporte_gen_dict(
            tipo_reporte='auditoria_consultas_sensibles',
            contiene_datos_sensibles=True,
        )
        r = client.post(
            '/v1/gd/reportes/auditoria/exportar',
            json={'formato': 'csv', 'filtros': {}},
        )
        assert r.status_code == 201
        assert r.json()['contiene_datos_sensibles'] is True


# =============================================================================
# Lectura registros
# =============================================================================
class TestLectura:
    def test_listar_generados(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/reportes/generados')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/reportes/generados?tipo_reporte=radicados'
            f'&generado_por_user_id={uuid4()}&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _reporte_gen_dict()
        r = client.get(f'/v1/gd/reportes/generados/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/reportes/generados/{uuid4()}')
        assert r.status_code == 404
