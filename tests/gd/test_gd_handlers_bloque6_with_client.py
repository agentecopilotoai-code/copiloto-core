"""Tests TestClient para handlers del bloque 6."""
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
ACTOR_USER_ID = uuid4()


def _fake_perfil() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR_USER_ID, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {
        'PERM-VU-001': 'global',
        'PERM-USR-001': 'global',
        'PERM-USR-009': 'global',
        'PERM-USR-010': 'global',
    }


def build_app(conn_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(gd_router)

    async def _ovr_db():
        yield conn_mock

    async def _ovr_perfil() -> GdPerfilContext:
        return _fake_perfil()

    app.dependency_overrides[get_db] = _ovr_db
    app.dependency_overrides[require_gd_perfil] = _ovr_perfil
    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    return TestClient(build_app(conn))


# =============================================================================
# Contactos
# =============================================================================
class TestContactosHandlers:
    def test_post_contacto(self, conn, client):
        tid = uuid4()
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'tercero_id': tid,
                'tipo_contacto': 'correo', 'valor': 'x@y.com',
                'es_principal': True, 'estado': 'activo',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/api/v1/gd/terceros/{tid}/contactos',
            json={'tipo_contacto': 'correo', 'valor': 'x@y.com', 'es_principal': True},
        )
        assert r.status_code == 201, r.text

    def test_post_contacto_fk_violation(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client.post(
            f'/api/v1/gd/terceros/{uuid4()}/contactos',
            json={'tipo_contacto': 'correo', 'valor': 'x@y.com'},
        )
        assert r.status_code == 404

    def test_get_contactos(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/terceros/{uuid4()}/contactos')
        assert r.status_code == 200

    def test_inactivar_contacto(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID, 'tercero_id': uuid4(),
                'tipo_contacto': 'correo', 'valor': 'x@y.com',
                'es_principal': False, 'estado': 'inactivo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/api/v1/gd/terceros/{uuid4()}/contactos/{uuid4()}/inactivar',
            json={'motivo': 'Ya no aplica'},
        )
        assert r.status_code == 200

    def test_inactivar_contacto_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/terceros/{uuid4()}/contactos/{uuid4()}/inactivar',
            json={'motivo': 'Ya no aplica'},
        )
        assert r.status_code == 404

    def test_get_historial(self, conn, client):
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'numero_radicado': 'RAD-2026-001',
                'fecha_radicacion': datetime.now(),
                'asunto': 'X', 'estado': 'registrado',
            }
        ]
        r = client.get(f'/api/v1/gd/terceros/{uuid4()}/historial')
        assert r.status_code == 200
        body = r.json()
        assert body['totales']['radicados'] == 1


# =============================================================================
# Tareas
# =============================================================================
class TestTareasHandlers:
    def test_post_tarea(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': TENANT_ID,
            'tipo_tarea': 'revisar', 'titulo': 'Test tarea', 'descripcion': None,
            'entidad_origen_tipo': None, 'entidad_origen_id': None,
            'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
            'asignado_por_user_id': ACTOR_USER_ID, 'fecha_asignacion': datetime.now(),
            'fecha_limite': None, 'prioridad': 'normal', 'estado': 'pendiente',
        }
        r = client.post(
            '/api/v1/gd/tareas',
            json={
                'tipo_tarea': 'revisar', 'titulo': 'Test tarea',
                'asignado_a_user_id': str(uuid4()),
            },
        )
        assert r.status_code == 201, r.text

    def test_post_tarea_sin_asignacion(self, conn, client):
        r = client.post(
            '/api/v1/gd/tareas',
            json={'tipo_tarea': 'revisar', 'titulo': 'Test tarea'},
        )
        assert r.status_code == 422

    def test_get_tareas(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/tareas?asignadas_a=me&estado=pendiente,en_proceso')
        assert r.status_code == 200

    def test_aplicar_accion_iniciar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'en_proceso',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/iniciar',
            json={},
        )
        assert r.status_code == 200

    def test_aplicar_accion_devolver_sin_observacion(self, conn, client):
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/devolver',
            json={},
        )
        assert r.status_code == 422

    def test_aplicar_accion_anular_sin_motivo(self, conn, client):
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/anular',
            json={},
        )
        assert r.status_code == 422

    def test_aplicar_accion_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/iniciar',
            json={},
        )
        assert r.status_code == 404

    def test_reasignar_tarea_ok(self, conn, client):
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.side_effect = [
            {'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
             'estado': 'pendiente'},
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'pendiente',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/reasignar',
            json={
                'usuario_destino_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 200

    def test_reasignar_tarea_sin_destino(self, conn, client):
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/reasignar',
            json={'motivo': 'Motivo válido suficientemente largo'},
        )
        assert r.status_code == 422

    def test_reasignar_destino_inactivo(self, conn, client):
        conn.fetchval.return_value = 'inactivo'
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/reasignar',
            json={
                'usuario_destino_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 422

    def test_reasignar_tarea_no_existe(self, conn, client):
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/tareas/{uuid4()}/reasignar',
            json={
                'usuario_destino_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 404


# =============================================================================
# Buzón
# =============================================================================
class TestBuzonHandlers:
    def test_get_buzon_usuario(self, conn, client):
        # Pattern: contar_por_estado (fetch), listar pendientes/en_proceso/
        # devueltas/próximos (4 fetchs), contar_no_leidas (fetchrow).
        conn.fetch.side_effect = [
            [{'estado': 'pendiente', 'c': 3}],  # counts
            [],  # pendientes
            [],  # en_proceso
            [],  # devueltas
            [],  # próximos
        ]
        conn.fetchrow.return_value = {'c': 2}  # no_leidas
        r = client.get('/api/v1/gd/buzon')
        assert r.status_code == 200
        body = r.json()
        assert body['tareas_pendientes']['total'] == 3
        assert body['notificaciones_no_leidas'] == 2

    def test_get_buzon_dependencia(self, conn, client):
        conn.fetch.side_effect = [
            [{'estado': 'pendiente', 'c': 5}],
            [],  # pendientes
            [],  # carga_por_usuario
        ]
        r = client.get(f'/api/v1/gd/buzon/dependencia/{uuid4()}')
        assert r.status_code == 200


# =============================================================================
# Notificaciones
# =============================================================================
class TestNotificacionesHandlers:
    def test_get_notificaciones(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'c': 0}
        r = client.get('/api/v1/gd/notificaciones')
        assert r.status_code == 200

    def test_get_notificaciones_solo_no_leidas(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'c': 0}
        r = client.get('/api/v1/gd/notificaciones?solo_no_leidas=true')
        assert r.status_code == 200

    def test_marcar_leida_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'leida': True, 'fecha_lectura': datetime.now(),
        }
        r = client.post(f'/api/v1/gd/notificaciones/{uuid4()}/marcar-leida')
        assert r.status_code == 200

    def test_marcar_leida_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(f'/api/v1/gd/notificaciones/{uuid4()}/marcar-leida')
        assert r.status_code == 404

    def test_get_preferencias(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/gd/notificaciones/preferencias')
        assert r.status_code == 200

    def test_patch_preferencias(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'id': uuid4()}  # audit
        r = client.patch(
            '/api/v1/gd/notificaciones/preferencias',
            json={
                'preferencias': [
                    {'tipo_notificacion': 'tarea_asignada',
                     'in_app_habilitado': True, 'correo_habilitado': False},
                ],
            },
        )
        assert r.status_code == 200


# =============================================================================
# GD-API-0008 reactivado — tareas-pendientes real
# =============================================================================
class TestTareasPendientesReactivado:
    def test_tareas_pendientes_con_datos_reales(self, conn, client):
        user_id = uuid4()
        # 1. Conteos por tipo
        conn.fetch.side_effect = [
            [
                {'entidad_origen_tipo': 'pqrsd', 'c': 3},
                {'entidad_origen_tipo': 'generica', 'c': 2},
            ],
            # 2. Lista de items
            [
                {
                    'id': uuid4(), 'tipo_tarea': 'responder',
                    'entidad_origen_tipo': 'pqrsd', 'entidad_origen_id': uuid4(),
                    'titulo': 'Test', 'fecha_limite': None, 'prioridad': 'normal',
                },
            ],
        ]
        r = client.get(f'/api/v1/gd/perfil-usuario/{user_id}/tareas-pendientes')
        assert r.status_code == 200
        body = r.json()
        assert body['total_pendientes'] == 5
        assert body['por_tipo']['pqrsd_asignadas'] == 3
        assert body['por_tipo']['tareas_genericas'] == 2

    def test_reasignar_tareas_real_ok(self, conn, client):
        tarea_id = uuid4()
        user_dest = uuid4()
        # 1. fetchval destino activo
        # 2. fetchrow actual de tarea
        # 3+4. execute UPDATE + INSERT historial (no fetchrow)
        # 5. audit fetchrow
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.side_effect = [
            {'asignado_a_user_id': uuid4()},  # actual
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/api/v1/gd/perfil-usuario/{uuid4()}/tareas/reasignar',
            json={
                'tareas': [str(tarea_id)],
                'user_destino_id': str(user_dest),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body['reasignadas'] == 1
        assert body['fallidas'] == 0

    def test_reasignar_tareas_tarea_no_existe(self, conn, client):
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.side_effect = [
            None,  # actual = None
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/api/v1/gd/perfil-usuario/{uuid4()}/tareas/reasignar',
            json={
                'tareas': [str(uuid4())],
                'user_destino_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body['fallidas'] == 1
        assert body['detalles'][0]['error'] == 'tarea_no_existe'
