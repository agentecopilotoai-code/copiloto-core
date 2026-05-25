"""Tests de handlers HTTP del bloque 2 vía FastAPI TestClient.

Estrategia:
- Crear una FastAPI app local que monta solo `app.gd.routes.router`.
- Override de `require_gd_perfil` para devolver un perfil fake activo.
- Override de `get_permisos_efectivos` para que devuelva permisos con alcance
  global (todo permitido) — el camino feliz de los handlers.
- Mock de `get_db` para devolver un asyncpg.Connection mockeado.

Para tests de error de autorización (403) hacemos sub-suite con override
distinto de `get_permisos_efectivos` que devuelve {}.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import router as gd_router
from app.gd.security import (
    GdPerfilContext,
    require_gd_perfil,
)


# Identificadores de prueba estables (no se regeneran entre tests para que
# los asserts sean reproducibles).
TENANT_ID = uuid4()
ACTOR_USER_ID = uuid4()
ACTOR_PERFIL_ID = uuid4()
TARGET_USER_ID = uuid4()


def _fake_perfil_activo() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR_USER_ID, tenant_id=TENANT_ID, perfil_id=ACTOR_PERFIL_ID,
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


# Lista completa de permisos que usan los handlers del bloque 2.
PERMISOS_ALL_GLOBAL = {
    'PERM-USR-001': 'global', 'PERM-USR-002': 'global', 'PERM-USR-004': 'global',
    'PERM-USR-009': 'global', 'PERM-USR-010': 'global', 'PERM-USR-011': 'global',
    'PERM-USR-012': 'global',
    'PERM-ROL-001': 'global', 'PERM-ROL-002': 'global', 'PERM-ROL-003': 'global',
    'PERM-ROL-004': 'global', 'PERM-ROL-005': 'global', 'PERM-ROL-006': 'global',
}


async def _fake_get_permisos_all(conn, *, user_id, tenant_id):
    return PERMISOS_ALL_GLOBAL


async def _fake_get_permisos_empty(conn, *, user_id, tenant_id):
    return {}


def build_app_for(conn_mock, *, permisos: str = 'all') -> FastAPI:
    app = FastAPI()
    app.include_router(gd_router)

    @asynccontextmanager
    async def _fake_get_db():
        yield conn_mock

    async def _override_get_db():
        yield conn_mock

    async def _override_perfil() -> GdPerfilContext:
        return _fake_perfil_activo()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_gd_perfil] = _override_perfil
    # Sobreescribir get_permisos_efectivos requiere monkeypatch porque NO es
    # una dependency directa de FastAPI. Se hace en cada test con monkeypatch.

    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client_all_perms(conn, monkeypatch):
    """Cliente con todos los permisos en alcance global."""
    monkeypatch.setattr(
        'app.gd.security.get_permisos_efectivos', _fake_get_permisos_all
    )
    app = build_app_for(conn)
    return TestClient(app)


@pytest.fixture
def client_no_perms(conn, monkeypatch):
    """Cliente sin permisos — para tests de 403."""
    monkeypatch.setattr(
        'app.gd.security.get_permisos_efectivos', _fake_get_permisos_empty
    )
    app = build_app_for(conn)
    return TestClient(app)


# =============================================================================
# /perfil-usuario
# =============================================================================
class TestPerfilUsuarioHandlers:
    def test_post_crea_perfil(self, conn, client_all_perms):
        conn.fetchval.return_value = 1  # user existe en app.users
        conn.fetchrow.side_effect = [
            # crear_perfil RETURNING
            {
                'perfil_id': uuid4(), 'tenant_id': TENANT_ID, 'user_id': TARGET_USER_ID,
                'tipo_vinculacion': 'planta', 'estado_gd': 'activo',
                'fecha_inicio_vinculacion': date(2026, 1, 1),
                'fecha_fin_vinculacion': None,
                'dependencia_actual_id': uuid4(), 'cargo_actual_id': None,
                'ultimo_acceso': None, 'created_at': datetime.now(),
                'created_by_user_id': ACTOR_USER_ID,
            },
            # core.emit_evento_auditoria RETURNING
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            '/v1/gd/perfil-usuario',
            json={
                'user_id': str(TARGET_USER_ID),
                'tipo_vinculacion': 'planta',
                'fecha_inicio_vinculacion': '2026-01-01',
                'dependencia_actual_id': str(uuid4()),
            },
        )
        assert r.status_code == 201, r.text

    def test_post_user_inexistente_404(self, conn, client_all_perms):
        conn.fetchval.return_value = None
        r = client_all_perms.post(
            '/v1/gd/perfil-usuario',
            json={
                'user_id': str(TARGET_USER_ID),
                'tipo_vinculacion': 'planta',
                'fecha_inicio_vinculacion': '2026-01-01',
                'dependencia_actual_id': str(uuid4()),
            },
        )
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'user_not_in_tenant'

    def test_post_ops_sin_fecha_fin_422(self, conn, client_all_perms):
        conn.fetchval.return_value = 1
        r = client_all_perms.post(
            '/v1/gd/perfil-usuario',
            json={
                'user_id': str(TARGET_USER_ID),
                'tipo_vinculacion': 'ops',
                'fecha_inicio_vinculacion': '2026-01-01',
                'dependencia_actual_id': str(uuid4()),
            },
        )
        assert r.status_code == 422
        assert r.json()['detail']['code'] == 'fecha_fin_requerida'

    def test_post_perfil_duplicado_409(self, conn, client_all_perms):
        import asyncpg
        conn.fetchval.return_value = 1
        # asyncpg excepciones se instancian sin args; el handler las pesca por tipo.
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client_all_perms.post(
            '/v1/gd/perfil-usuario',
            json={
                'user_id': str(TARGET_USER_ID),
                'tipo_vinculacion': 'planta',
                'fecha_inicio_vinculacion': '2026-01-01',
                'dependencia_actual_id': str(uuid4()),
            },
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'perfil_ya_existe'

    def test_patch_actualiza_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            # actualizar_perfil RETURNING
            {
                'perfil_id': uuid4(), 'tenant_id': TENANT_ID, 'user_id': TARGET_USER_ID,
                'tipo_vinculacion': 'ops', 'estado_gd': 'activo',
                'fecha_inicio_vinculacion': date(2026, 1, 1),
                'fecha_fin_vinculacion': date(2026, 12, 31),
                'dependencia_actual_id': None, 'cargo_actual_id': None,
                'ultimo_acceso': None, 'created_at': datetime.now(),
                'created_by_user_id': None,
            },
            {'id': uuid4()},  # audit
        ]
        r = client_all_perms.patch(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}',
            json={'tipo_vinculacion': 'ops', 'fecha_fin_vinculacion': '2026-12-31'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['tipo_vinculacion'] == 'ops'

    def test_patch_inexistente_404(self, conn, client_all_perms):
        conn.fetchrow.return_value = None
        r = client_all_perms.patch(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}',
            json={'tipo_vinculacion': 'ops'},
        )
        assert r.status_code == 404

    def test_post_accion_inactivar_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'estado_anterior': 'activo', 'estado_nuevo': 'inactivo'},
            {'id': uuid4()},  # audit
        ]
        r = client_all_perms.post(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/inactivar',
            json={'motivo': 'Cambio de proyecto reasignado'},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['estado_gd_anterior'] == 'activo'
        assert body['estado_gd_nuevo'] == 'inactivo'

    def test_post_accion_desbloquear_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'estado_anterior': 'bloqueado', 'estado_nuevo': 'activo'},
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/desbloquear',
            json={'motivo': 'Usuario verificado por soporte'},
        )
        assert r.status_code == 200

    def test_post_accion_perfil_inexistente_404(self, conn, client_all_perms):
        conn.fetchrow.return_value = None
        r = client_all_perms.post(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/inactivar',
            json={'motivo': 'Razón válida que tiene al menos 10 chars'},
        )
        assert r.status_code == 404

    def test_get_listar(self, conn, client_all_perms):
        conn.fetch.return_value = [
            {
                'user_id': TARGET_USER_ID, 'email': 'juan@x.com',
                'display_name': 'Juan Pérez García',
                'tipo_vinculacion': 'planta', 'estado_gd': 'activo',
                'dependencia_actual_id': None, 'cargo_actual_id': None,
                'roles_gd_count': 2, 'ultimo_acceso': None,
            }
        ]
        conn.fetchrow.return_value = {'c': 1}
        r = client_all_perms.get('/v1/gd/perfil-usuario')
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body['items']) == 1
        assert body['pagina']['total_estimado'] == 1

    def test_get_listar_con_filtros(self, conn, client_all_perms):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'c': 0}
        r = client_all_perms.get(
            '/v1/gd/perfil-usuario'
            '?dependencia_id=' + str(uuid4())
            + '&estado_gd=activo,suspendido'
            + '&tipo_vinculacion=planta,ops'
            + '&q=juan&limit=10'
        )
        assert r.status_code == 200

    def test_get_historial(self, conn, client_all_perms):
        conn.fetch.return_value = [
            {
                'evento_auditoria_id': uuid4(), 'tipo_evento': 'gd.perfil_usuario.creado',
                'accion': 'crear', 'valor_anterior': None, 'valor_nuevo': {'x': 1},
                'ejecutado_por_user_id': ACTOR_USER_ID, 'ejecutado_por_nombre': 'Admin',
                'motivo': None, 'fecha': datetime.now(),
            }
        ]
        r = client_all_perms.get(f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/historial')
        assert r.status_code == 200
        assert len(r.json()['eventos']) == 1


# =============================================================================
# /roles
# =============================================================================
class TestRolesHandlers:
    def test_get_roles(self, conn, client_all_perms):
        conn.fetch.return_value = [
            {'codigo': 'gd.profesional', 'nombre': 'Profesional', 'descripcion': None,
             'es_sistema': True, 'estado': 'activo', 'permisos_count': 23},
        ]
        r = client_all_perms.get('/v1/gd/roles')
        assert r.status_code == 200
        assert len(r.json()['items']) == 1

    def test_get_roles_con_filtro(self, conn, client_all_perms):
        conn.fetch.return_value = []
        r = client_all_perms.get('/v1/gd/roles?estado=activo')
        assert r.status_code == 200

    def test_post_rol_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
             'es_sistema': False, 'estado': 'activo'},
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            '/v1/gd/roles',
            json={'codigo': 'gd.x', 'nombre': 'Custom'},
        )
        assert r.status_code == 201, r.text

    def test_post_rol_conflicto(self, conn, client_all_perms):
        conn.fetchrow.return_value = None  # ya existe
        r = client_all_perms.post(
            '/v1/gd/roles',
            json={'codigo': 'gd.profesional', 'nombre': 'Profesional'},
        )
        assert r.status_code == 409

    def test_patch_rol(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'codigo': 'gd.x', 'nombre': 'X-nuevo', 'descripcion': None,
             'es_sistema': False, 'estado': 'activo'},
            {'c': 5},  # permisos_count re-lookup
            {'id': uuid4()},  # audit
        ]
        r = client_all_perms.patch(
            '/v1/gd/roles/gd.x',
            json={'nombre': 'X-nuevo'},
        )
        assert r.status_code == 200

    def test_patch_rol_404(self, conn, client_all_perms):
        conn.fetchrow.return_value = None
        r = client_all_perms.patch(
            '/v1/gd/roles/gd.inexistente',
            json={'nombre': 'Nombre nuevo válido'},
        )
        assert r.status_code == 404

    def test_inactivar_rol_en_uso(self, conn, client_all_perms):
        conn.fetchrow.return_value = {'c': 5}  # asignaciones activas
        r = client_all_perms.post(
            '/v1/gd/roles/gd.x/inactivar',
            json={'motivo': 'Razón válida suficientemente larga'},
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'role_in_use'

    def test_inactivar_rol_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'c': 0},  # sin asignaciones
            {'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
             'es_sistema': False, 'estado': 'inactivo'},
            {'id': uuid4()},  # audit
        ]
        r = client_all_perms.post(
            '/v1/gd/roles/gd.x/inactivar',
            json={'motivo': 'Reorganización institucional'},
        )
        assert r.status_code == 200

    def test_inactivar_rol_no_existe(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'c': 0},
            None,  # inactivar_rol devuelve None
        ]
        r = client_all_perms.post(
            '/v1/gd/roles/gd.x/inactivar',
            json={'motivo': 'Razón válida suficientemente larga'},
        )
        assert r.status_code == 404

    def test_agregar_permiso_ok(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            {'rol_codigo': 'gd.x', 'permiso_codigo': 'PERM-A',
             'alcance_default': 'dependencia', 'agregado_en': datetime.now()},
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            '/v1/gd/roles/gd.x/permisos',
            json={'permiso_codigo': 'PERM-A', 'alcance_default': 'dependencia'},
        )
        assert r.status_code == 201

    def test_agregar_permiso_ya_existe(self, conn, client_all_perms):
        conn.fetchrow.return_value = None
        r = client_all_perms.post(
            '/v1/gd/roles/gd.x/permisos',
            json={'permiso_codigo': 'PERM-A', 'alcance_default': 'dependencia'},
        )
        assert r.status_code == 409

    def test_agregar_permiso_fk_violation(self, conn, client_all_perms):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client_all_perms.post(
            '/v1/gd/roles/gd.inexistente/permisos',
            json={'permiso_codigo': 'PERM-A', 'alcance_default': 'dependencia'},
        )
        assert r.status_code == 404

    def test_quitar_permiso_ok(self, conn, client_all_perms):
        conn.execute.return_value = 'DELETE 1'
        conn.fetchrow.return_value = {'id': uuid4()}  # audit
        r = client_all_perms.delete('/v1/gd/roles/gd.x/permisos/PERM-A')
        assert r.status_code == 204

    def test_quitar_permiso_no_existe(self, conn, client_all_perms):
        conn.execute.return_value = 'DELETE 0'
        r = client_all_perms.delete('/v1/gd/roles/gd.x/permisos/PERM-A')
        assert r.status_code == 404

    def test_get_permisos(self, conn, client_all_perms):
        conn.fetch.return_value = [
            {'codigo': 'PERM-A', 'nombre': 'A', 'modulo': 'pqrsd',
             'descripcion': None, 'es_critico': False, 'estado': 'activo'},
        ]
        r = client_all_perms.get('/v1/gd/permisos')
        assert r.status_code == 200

    def test_get_permisos_con_filtros(self, conn, client_all_perms):
        conn.fetch.return_value = []
        r = client_all_perms.get('/v1/gd/permisos?modulo=pqrsd&estado=activo')
        assert r.status_code == 200


# =============================================================================
# /usuarios/{user_id}/roles
# =============================================================================
class TestAsignacionesHandlers:
    def test_post_asignar_rol_ok(self, conn, client_all_perms):
        conn.fetchval.return_value = 'activo'  # estado_destino
        conn.fetchrow.side_effect = [
            {
                'asignacion_alcance_id': uuid4(), 'user_id': TARGET_USER_ID,
                'rol_codigo': 'gd.profesional', 'dependencia_id': uuid4(),
                'alcance': 'dependencia', 'fecha_inicio': date(2026, 1, 1),
                'fecha_fin': None, 'estado': 'activa',
                'asignado_por_user_id': ACTOR_USER_ID, 'motivo': 'Acto admin 1234',
            },
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles',
            json={
                'rol_codigo': 'gd.profesional',
                'dependencia_id': str(uuid4()),
                'alcance': 'dependencia',
                'fecha_inicio': '2026-01-01',
                'motivo': 'Acto administrativo 1234',
            },
        )
        assert r.status_code == 201, r.text

    def test_post_destino_sin_perfil_404(self, conn, client_all_perms):
        conn.fetchval.return_value = None
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles',
            json={
                'rol_codigo': 'gd.profesional',
                'alcance': 'institucional',
                'fecha_inicio': '2026-01-01',
                'motivo': 'Acto administrativo 1234',
            },
        )
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'perfil_destino_no_existe'

    def test_post_destino_inactivo_409(self, conn, client_all_perms):
        conn.fetchval.return_value = 'inactivo'
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles',
            json={
                'rol_codigo': 'gd.profesional',
                'alcance': 'institucional',
                'fecha_inicio': '2026-01-01',
                'motivo': 'Acto administrativo 1234',
            },
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'usuario_inactivo'

    def test_post_fk_violation_404(self, conn, client_all_perms):
        import asyncpg
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles',
            json={
                'rol_codigo': 'gd.inexistente',
                'alcance': 'institucional',
                'fecha_inicio': '2026-01-01',
                'motivo': 'Acto administrativo 1234',
            },
        )
        assert r.status_code == 404

    def test_cerrar_asignacion_ok(self, conn, client_all_perms):
        asign_id = uuid4()
        conn.fetchrow.side_effect = [
            {'asignacion_alcance_id': asign_id, 'fecha_fin': datetime.now(), 'estado': 'cerrada'},
            {'id': uuid4()},
        ]
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles/{asign_id}/cerrar',
            json={'motivo': 'Traslado a otra dependencia'},
        )
        assert r.status_code == 200

    def test_cerrar_asignacion_no_existe(self, conn, client_all_perms):
        conn.fetchrow.return_value = None
        r = client_all_perms.post(
            f'/v1/gd/usuarios/{TARGET_USER_ID}/roles/{uuid4()}/cerrar',
            json={'motivo': 'Razón válida suficientemente larga'},
        )
        assert r.status_code == 404

    def test_get_roles_propio_ok(self, conn, client_all_perms):
        conn.fetch.return_value = []
        r = client_all_perms.get(f'/v1/gd/usuarios/{ACTOR_USER_ID}/roles')
        assert r.status_code == 200

    def test_get_roles_otro_con_permiso_ok(self, conn, client_all_perms):
        conn.fetch.side_effect = [
            # get_permisos_efectivos call (override hace fetch list)
            [],
            # listar_roles_usuario fetch
            [],
        ]
        # nota: get_permisos_efectivos está overrideado a _fake_get_permisos_all
        # así que devuelve PERM-USR-010=global y pasa el check.
        r = client_all_perms.get(f'/v1/gd/usuarios/{TARGET_USER_ID}/roles')
        assert r.status_code == 200

    def test_get_roles_otro_sin_permiso_403(self, conn, monkeypatch):
        # require_gd_perfil pasa (override por build_app_for); pero
        # require_gd_permission depende de get_permisos_efectivos que
        # devuelve {} → 403 antes incluso de entrar al handler.
        async def _solo_basicos(conn, *, user_id, tenant_id):
            return {}
        monkeypatch.setattr(
            'app.gd.security.get_permisos_efectivos', _solo_basicos
        )
        # El handler de listar_roles_usuario hace `from app.gd.security import`
        # local — el monkeypatch del módulo origen lo cubre.
        app = build_app_for(conn)
        client = TestClient(app)
        r = client.get(f'/v1/gd/usuarios/{TARGET_USER_ID}/roles')
        assert r.status_code == 403


# =============================================================================
# /seguridad/politica
# =============================================================================
class TestPoliticaHandlers:
    def test_get_politica(self, conn, client_all_perms):
        conn.fetchrow.return_value = {
            'longitud_minima': 14, 'complejidad_regex': '.*',
            'historial_no_reuso': 5, 'vigencia_dias': 60,
            'intentos_fallidos_max': 3, 'cooldown_segundos': 60,
            'vigente_desde': datetime.now(), 'tenant_id': TENANT_ID,
        }
        r = client_all_perms.get('/v1/gd/seguridad/politica')
        assert r.status_code == 200
        assert r.json()['longitud_minima'] == 14

    def test_patch_politica(self, conn, client_all_perms):
        conn.fetchrow.side_effect = [
            # obtener_politica_vigente
            {
                'longitud_minima': 12, 'complejidad_regex': '.*',
                'historial_no_reuso': 12, 'vigencia_dias': 90,
                'intentos_fallidos_max': 5, 'cooldown_segundos': 300,
                'vigente_desde': datetime.now(), 'tenant_id': TENANT_ID,
            },
            # actualizar_politica INSERT RETURNING
            {
                'longitud_minima': 20, 'complejidad_regex': '.*',
                'historial_no_reuso': 12, 'vigencia_dias': 90,
                'intentos_fallidos_max': 5, 'cooldown_segundos': 300,
                'vigente_desde': datetime.now(),
            },
            # audit
            {'id': uuid4()},
        ]
        r = client_all_perms.patch(
            '/v1/gd/seguridad/politica',
            json={'longitud_minima': 20},
        )
        assert r.status_code == 200
        assert r.json()['longitud_minima'] == 20


# =============================================================================
# /perfil-usuario/{id}/tareas-*
# =============================================================================
class TestTareasHandlers:
    def test_tareas_pendientes_stub_vacio(self, conn, client_all_perms):
        r = client_all_perms.get(f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/tareas-pendientes')
        assert r.status_code == 200
        body = r.json()
        assert body['total_pendientes'] == 0

    def test_reasignar_ok_stub(self, conn, client_all_perms):
        conn.fetchval.return_value = 'activo'
        conn.fetchrow.return_value = {'id': uuid4()}
        r = client_all_perms.post(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/tareas/reasignar',
            json={
                'tareas': [str(uuid4()), str(uuid4())],
                'user_destino_id': str(uuid4()),
                'motivo': 'Reasignación por inactivación',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body['fallidas'] == 2  # stub no implementa aún

    def test_reasignar_destino_inactivo_422(self, conn, client_all_perms):
        conn.fetchval.return_value = 'inactivo'
        r = client_all_perms.post(
            f'/v1/gd/perfil-usuario/{TARGET_USER_ID}/tareas/reasignar',
            json={
                'tareas': [str(uuid4())],
                'user_destino_id': str(uuid4()),
                'motivo': 'Reasignación válida razón',
            },
        )
        assert r.status_code == 422
