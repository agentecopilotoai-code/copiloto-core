"""Tests TestClient para los handlers HTTP del bloque 4."""
from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import router as gd_router
from app.gd.security import GdPerfilContext, require_gd_perfil


TENANT_ID = uuid4()
ACTOR_USER_ID = uuid4()


def _fake_perfil() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR_USER_ID, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {
        'PERM-USR-001': 'global',
        'PERM-VU-001': 'global',
    }


def build_app(conn_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(gd_router)

    async def _override_get_db():
        yield conn_mock

    async def _override_perfil() -> GdPerfilContext:
        return _fake_perfil()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_gd_perfil] = _override_perfil
    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    return TestClient(build_app(conn))


# =============================================================================
# /cargos
# =============================================================================
class TestCargosHandlers:
    def test_post_cargo(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'nombre': 'Profesional',
                'dependencia_id': None, 'estado': 'activo',
                'fecha_inicio_vigencia': date(2026, 1, 1), 'fecha_fin_vigencia': None,
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/api/v1/gd/cargos',
            json={'nombre': 'Profesional Especializado'},
        )
        assert r.status_code == 201, r.text

    def test_post_cargo_fk_violation(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client.post(
            '/api/v1/gd/cargos',
            json={'nombre': 'Profesional Test', 'dependencia_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_get_cargos(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/cargos')
        assert r.status_code == 200

    def test_get_cargos_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/cargos?dependencia_id={uuid4()}&estado=activo'
        )
        assert r.status_code == 200

    def test_patch_cargo_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'nombre': 'Nuevo nombre',
                'dependencia_id': None, 'estado': 'activo',
                'fecha_inicio_vigencia': date(2026, 1, 1), 'fecha_fin_vigencia': None,
            },
            {'id': uuid4()},
        ]
        r = client.patch(
            f'/api/v1/gd/cargos/{uuid4()}',
            json={'nombre': 'Nuevo nombre'},
        )
        assert r.status_code == 200

    def test_patch_cargo_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.patch(
            f'/api/v1/gd/cargos/{uuid4()}',
            json={'nombre': 'Nuevo nombre'},
        )
        assert r.status_code == 404


# =============================================================================
# /canales
# =============================================================================
class TestCanalesHandlers:
    def test_post_canal(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'codigo': 'pres',
                'nombre': 'Presencial', 'descripcion': None,
                'requiere_punto_atencion': True, 'requiere_digitalizacion': False,
                'permite_acuse': True, 'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            '/api/v1/gd/canales',
            json={'codigo': 'pres', 'nombre': 'Presencial', 'requiere_punto_atencion': True},
        )
        assert r.status_code == 201, r.text

    def test_post_canal_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/canales',
            json={'codigo': 'pres', 'nombre': 'Presencial'},
        )
        assert r.status_code == 409

    def test_get_canales(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/canales')
        assert r.status_code == 200


# =============================================================================
# /calendarios
# =============================================================================
class TestCalendariosHandlers:
    def test_post_calendario(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'nombre': 'Hábil CO 2026',
                'vigencia_anual': 2026, 'festivos': json.dumps(['2026-01-01']),
                'dias_no_laborales': [0, 6], 'es_default': True, 'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            '/api/v1/gd/calendarios',
            json={
                'nombre': 'Hábil CO 2026',
                'vigencia_anual': 2026,
                'festivos': ['2026-01-01'],
                'es_default': True,
            },
        )
        assert r.status_code == 201, r.text

    def test_post_calendario_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/calendarios',
            json={'nombre': 'Calendario 2026', 'vigencia_anual': 2026},
        )
        assert r.status_code == 409

    def test_get_calendarios(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = None  # sin default
        r = client.get('/api/v1/gd/calendarios')
        assert r.status_code == 200

    def test_calcular_fecha_limite(self, conn, client):
        fecha_esperada = datetime(2026, 6, 15, 10, 0)
        conn.fetchrow.return_value = {'fecha_limite': fecha_esperada}
        r = client.post(
            '/api/v1/gd/calendarios/calcular-fecha-limite',
            json={
                'fecha_base': '2026-06-01T10:00:00',
                'termino_dias': 10,
                'tipo_dias': 'habiles',
            },
        )
        assert r.status_code == 200


# =============================================================================
# /tipos-pqrsd y /tipos-correspondencia
# =============================================================================
class TestTiposHandlers:
    def test_post_tipo_pqrsd(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'codigo': 'pet',
                'nombre': 'Petición', 'descripcion': None,
                'termino_dias': 15, 'tipo_dias': 'habiles',
                'requiere_respuesta': True, 'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            '/api/v1/gd/tipos-pqrsd',
            json={
                'codigo': 'pet', 'nombre': 'Petición',
                'termino_dias': 15, 'tipo_dias': 'habiles',
            },
        )
        assert r.status_code == 201

    def test_post_tipo_pqrsd_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/tipos-pqrsd',
            json={'codigo': 'pet', 'nombre': 'Petición',
                  'termino_dias': 15, 'tipo_dias': 'habiles'},
        )
        assert r.status_code == 409

    def test_get_tipos_pqrsd(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/tipos-pqrsd')
        assert r.status_code == 200

    def test_post_tipo_correspondencia(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'codigo': 'ofi',
                'nombre': 'Oficio', 'descripcion': None,
                'ambito': 'externa_enviada', 'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            '/api/v1/gd/tipos-correspondencia',
            json={'codigo': 'ofi', 'nombre': 'Oficio', 'ambito': 'externa_enviada'},
        )
        assert r.status_code == 201

    def test_post_tipo_correspondencia_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/tipos-correspondencia',
            json={'codigo': 'ofi', 'nombre': 'Oficio', 'ambito': 'interna'},
        )
        assert r.status_code == 409

    def test_get_tipos_correspondencia(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/tipos-correspondencia?ambito=interna')
        assert r.status_code == 200


# =============================================================================
# /reglas/comunicacion
# =============================================================================
class TestReglasHandlers:
    def test_post_regla_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'dependencia_origen_id': uuid4(),
                'dependencia_destino_id': uuid4(),
                'permitido': True, 'requiere_aprobacion_jefe': False,
                'motivo_restriccion': None, 'estado': 'activa',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/api/v1/gd/reglas/comunicacion',
            json={
                'dependencia_origen_id': str(uuid4()),
                'dependencia_destino_id': str(uuid4()),
                'permitido': True,
            },
        )
        assert r.status_code == 201

    def test_post_regla_mismo_origen_destino(self, conn, client):
        dep = uuid4()
        r = client.post(
            '/api/v1/gd/reglas/comunicacion',
            json={
                'dependencia_origen_id': str(dep),
                'dependencia_destino_id': str(dep),
            },
        )
        assert r.status_code == 422

    def test_post_regla_duplicada(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/reglas/comunicacion',
            json={
                'dependencia_origen_id': str(uuid4()),
                'dependencia_destino_id': str(uuid4()),
            },
        )
        assert r.status_code == 409

    def test_post_regla_fk_violation(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client.post(
            '/api/v1/gd/reglas/comunicacion',
            json={
                'dependencia_origen_id': str(uuid4()),
                'dependencia_destino_id': str(uuid4()),
            },
        )
        assert r.status_code == 404

    def test_get_reglas(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/reglas/comunicacion')
        assert r.status_code == 200

    def test_get_reglas_con_filtro(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/reglas/comunicacion?dependencia_origen_id={uuid4()}'
        )
        assert r.status_code == 200

    def test_validar_comunicacion(self, conn, client):
        conn.fetchrow.return_value = None  # sin regla
        r = client.get(
            f'/api/v1/gd/reglas/comunicacion/validar?origen={uuid4()}&destino={uuid4()}'
        )
        assert r.status_code == 200
        body = r.json()
        assert body['permitido'] is True


# =============================================================================
# /parametros
# =============================================================================
class TestParametrosHandlers:
    def test_get_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/parametros')
        assert r.status_code == 200

    def test_get_clave_existe(self, conn, client):
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'clave': 'gd.x', 'valor': 'v1',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            }
        ]
        r = client.get('/api/v1/gd/parametros/gd.x')
        assert r.status_code == 200

    def test_get_clave_no_existe(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/parametros/inexistente')
        assert r.status_code == 404

    def test_patch_parametros(self, conn, client):
        conn.fetchrow.side_effect = [
            # buscar activo actual
            None,
            # INSERT nueva fila
            {
                'id': uuid4(), 'clave': 'gd.x', 'valor': 'v1',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            },
            # audit
            {'id': uuid4()},
        ]
        r = client.patch(
            '/api/v1/gd/parametros',
            json={
                'parametros': [
                    {'clave': 'gd.x', 'valor': 'v1', 'tipo': 'string',
                     'motivo': 'Primera vez'},
                ],
            },
        )
        assert r.status_code == 200, r.text


# =============================================================================
# /consecutivos
# =============================================================================
class TestConsecutivosHandlers:
    def test_get_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/consecutivos')
        assert r.status_code == 200

    def test_get_listar_con_vigencia(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/consecutivos?vigencia=2026')
        assert r.status_code == 200

    def test_post_siguiente(self, conn, client):
        conn.fetchrow.side_effect = [
            {'numero_radicado': 'RAD-2026-000001'},
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/api/v1/gd/consecutivos/siguiente',
            json={'vigencia': 2026, 'tipo_radicado': 'entrada'},
        )
        assert r.status_code == 200
        assert r.json()['numero_radicado'] == 'RAD-2026-000001'

    def test_post_siguiente_agotado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.RaiseError('agotado')
        r = client.post(
            '/api/v1/gd/consecutivos/siguiente',
            json={'vigencia': 2026, 'tipo_radicado': 'entrada'},
        )
        assert r.status_code == 409
