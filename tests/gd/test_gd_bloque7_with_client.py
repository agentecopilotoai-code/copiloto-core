"""Tests TestClient para handlers del bloque 7 (alertas + pqrsd)."""
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
        'PERM-USR-001': 'global', 'PERM-USR-010': 'global',
        'PERM-VU-001': 'global', 'PERM-VU-005': 'global',
        'PERM-VU-006': 'global',
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
# Alertas
# =============================================================================
class TestAlertasHandlers:
    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'total': 0, 'criticas': 0}
        r = client.get('/v1/gd/alertas')
        assert r.status_code == 200

    def test_listar_solo_mis_false(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'total': 0, 'criticas': 0}
        r = client.get('/v1/gd/alertas?solo_mis=false&estado=activa&severidad=critica')
        assert r.status_code == 200

    def test_escalar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'destinatario_user_id': uuid4(),
                'destinatario_dependencia_id': None,
                'tipo_alerta': 'vencido', 'severidad': 'critica',
                'titulo': 'X', 'mensaje': 'Y',
                'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
                'estado': 'escalada', 'created_at': datetime.now(),
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/v1/gd/alertas/{uuid4()}/escalar',
            json={'user_destino_id': str(uuid4()), 'motivo': 'Escalación urgente'},
        )
        assert r.status_code == 200

    def test_escalar_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/alertas/{uuid4()}/escalar',
            json={'user_destino_id': str(uuid4()), 'motivo': 'Escalación urgente'},
        )
        assert r.status_code == 404

    def test_marcar_gestionada_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'destinatario_user_id': uuid4(),
                'destinatario_dependencia_id': None,
                'tipo_alerta': 'vencido', 'severidad': 'alta',
                'titulo': 'X', 'mensaje': 'Y',
                'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
                'estado': 'gestionada', 'created_at': datetime.now(),
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/alertas/{uuid4()}/marcar-gestionada',
            json={'observacion': 'OK gestionada'},
        )
        assert r.status_code == 200

    def test_marcar_gestionada_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/alertas/{uuid4()}/marcar-gestionada',
            json={},
        )
        assert r.status_code == 404


# =============================================================================
# PQRSD
# =============================================================================
class TestPqrsdHandlers:
    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'c': 0}
        r = client.get('/v1/gd/pqrsd')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'radicado_entrada_id': uuid4(),
                'numero_radicado': 'RAD-2026-001',
                'asunto': 'X', 'estado': 'nueva',
                'fecha_recepcion': datetime.now(),
                'fecha_limite_respuesta': None,
                'dependencia_responsable_id': None,
                'usuario_responsable_id': None,
            }
        ]
        conn.fetchrow.return_value = {'c': 1}
        r = client.get(
            f'/v1/gd/pqrsd?estado=nueva,asignada&dependencia_id={uuid4()}'
            f'&usuario_id={uuid4()}'
        )
        assert r.status_code == 200

    def test_obtener_pqrsd(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_entrada_id': uuid4(),
            'tipo_pqrsd_id': None, 'tercero_id': None,
            'asunto': 'X', 'descripcion': None,
            'dependencia_responsable_id': None,
            'usuario_responsable_id': None,
            'fecha_recepcion': datetime.now(),
            'fecha_limite_respuesta': None,
            'estado': 'nueva', 'prioridad': 'normal', 'reserva': False,
        }
        r = client.get(f'/v1/gd/pqrsd/{uuid4()}')
        assert r.status_code == 200

    def test_obtener_pqrsd_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/pqrsd/{uuid4()}')
        assert r.status_code == 404

    def test_asignar_dependencia_ok(self, conn, client):
        conn.fetchval.return_value = 1  # pqrsd existe
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'dependencia_id': uuid4(), 'usuario_asignado_id': None,
                'asignado_por_user_id': ACTOR_USER_ID,
                'fecha_asignacion': datetime.now(), 'fecha_fin': None,
                'motivo': None, 'estado': 'activa',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/asignar-dependencia',
            json={'dependencia_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_asignar_dependencia_pqrsd_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/asignar-dependencia',
            json={'dependencia_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_asignar_funcionario_inactivo(self, conn, client):
        conn.fetchval.return_value = 'inactivo'
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/asignar-funcionario',
            json={'usuario_id': str(uuid4())},
        )
        assert r.status_code == 422

    def test_asignar_funcionario_ok(self, conn, client):
        conn.fetchval.side_effect = ['activo', 1]  # estado, pqrsd existe
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'dependencia_id': None, 'usuario_asignado_id': uuid4(),
                'asignado_por_user_id': ACTOR_USER_ID,
                'fecha_asignacion': datetime.now(), 'fecha_fin': None,
                'motivo': None, 'estado': 'activa',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/asignar-funcionario',
            json={'usuario_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_asignar_funcionario_pqrsd_no_existe(self, conn, client):
        conn.fetchval.side_effect = ['activo', None]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/asignar-funcionario',
            json={'usuario_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_reasignar_sin_destino(self, conn, client):
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reasignar',
            json={'motivo': 'Motivo válido suficientemente largo'},
        )
        assert r.status_code == 422

    def test_reasignar_destino_inactivo(self, conn, client):
        conn.fetchval.return_value = 'inactivo'
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reasignar',
            json={
                'usuario_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 422

    def test_reasignar_ok(self, conn, client):
        conn.fetchval.side_effect = ['activo', 1]
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'dependencia_id': None, 'usuario_asignado_id': uuid4(),
                'asignado_por_user_id': ACTOR_USER_ID,
                'fecha_asignacion': datetime.now(), 'fecha_fin': None,
                'motivo': 'X', 'estado': 'activa',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reasignar',
            json={
                'usuario_id': str(uuid4()),
                'motivo': 'Reasignación operativa',
            },
        )
        assert r.status_code == 200

    def test_reasignar_pqrsd_no_existe(self, conn, client):
        # body solo tiene dependencia_id (sin usuario_id) → handler salta
        # la validación de usuario activo. Solo se llama 1 fetchval (en service)
        # que debe retornar None para indicar pqrsd no existe.
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reasignar',
            json={
                'dependencia_id': str(uuid4()),
                'motivo': 'Motivo válido suficientemente largo',
            },
        )
        assert r.status_code == 404

    def test_proyectar_respuesta_sin_contenido(self, conn, client):
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/respuestas',
            json={},
        )
        assert r.status_code == 422

    def test_proyectar_respuesta_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'documento_id': None, 'plantilla_id': None,
                'contenido_borrador': 'Borrador de respuesta test',
                'usuario_proyecta_id': ACTOR_USER_ID,
                'usuario_revisa_id': None, 'usuario_aprueba_id': None,
                'usuario_firma_id': None, 'radicado_salida_id': None,
                'estado': 'borrador',
                'fecha_proyeccion': datetime.now(),
                'fecha_revision': None, 'fecha_aprobacion': None,
                'fecha_firma': None, 'fecha_radicacion': None,
                'fecha_envio': None,
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/respuestas',
            json={'contenido_borrador': 'Borrador de respuesta test'},
        )
        assert r.status_code == 201

    def test_proyectar_respuesta_pqrsd_no_existe(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/respuestas',
            json={'contenido_borrador': 'X'},
        )
        assert r.status_code == 404

    def test_suspender_termino_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'fecha_limite_respuesta': datetime.now()},
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'tipo_evento': 'suspension', 'fecha_evento': datetime.now(),
                'motivo': 'X', 'justificacion_legal': None,
                'dias_afectados': None,
                'fecha_limite_anterior': datetime.now(),
                'fecha_limite_nueva': None, 'usuario_id': ACTOR_USER_ID,
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/suspender-termino',
            json={'motivo': 'Solicitud info adicional ciudadano'},
        )
        assert r.status_code == 200

    def test_suspender_termino_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/suspender-termino',
            json={'motivo': 'Solicitud info adicional ciudadano'},
        )
        assert r.status_code == 404

    def test_reanudar_termino_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'fecha_limite_respuesta': datetime.now()},
            None,  # sin suspensión previa
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'tipo_evento': 'reanudacion', 'fecha_evento': datetime.now(),
                'motivo': 'X', 'justificacion_legal': None,
                'dias_afectados': 0,
                'fecha_limite_anterior': datetime.now(),
                'fecha_limite_nueva': datetime.now(),
                'usuario_id': ACTOR_USER_ID,
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reanudar-termino',
            json={'motivo': 'Reanudación luego de info adicional'},
        )
        assert r.status_code == 200

    def test_reanudar_termino_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reanudar-termino',
            json={'motivo': 'Reanudación operativa'},
        )
        assert r.status_code == 404

    def test_historial_terminos(self, conn, client):
        # fetch para eventos + fetchrow para pqrsd_row
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_entrada_id': uuid4(),
            'tipo_pqrsd_id': None, 'tercero_id': None,
            'asunto': 'X', 'descripcion': None,
            'dependencia_responsable_id': None,
            'usuario_responsable_id': None,
            'fecha_recepcion': datetime.now(),
            'fecha_limite_respuesta': datetime.now(),
            'estado': 'nueva', 'prioridad': 'normal', 'reserva': False,
        }
        r = client.get(f'/v1/gd/pqrsd/{uuid4()}/historial-terminos')
        assert r.status_code == 200

    def test_historial_terminos_pqrsd_no_existe(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/pqrsd/{uuid4()}/historial-terminos')
        assert r.status_code == 404


# =============================================================================
# Hook reactivo: clasificar como pqrsd dispara creación PQRSD
# =============================================================================
class TestHookReactivoPqrsd:
    def test_clasificar_pqrsd_crea_pqrsd_automaticamente(self, conn, client):
        radicado_id = uuid4()
        pqrsd_id = uuid4()
        tipo_pqrsd_id = uuid4()
        # Mocks orden:
        # 1. fetchval: clasif previa (None)
        # 2. fetchrow: clasificar_radicado RETURNING
        # 3. fetchrow: audit RadicadoClasificado
        # 4. fetchval: idempotencia gd.pqrsd (None)
        # 5. fetchrow: datos del radicado
        # 6. fetchrow: tipo_pqrsd (termino_dias)
        # 7. fetchrow: fecha_limite calculada
        # 8. fetchrow: INSERT pqrsd RETURNING
        # 9. fetchrow: audit PQRSDCreada
        from datetime import timedelta
        conn.fetchval.side_effect = [None, None]  # clasif previa + idempot pqrsd
        conn.fetchrow.side_effect = [
            # clasificar_radicado returning
            {
                'id': uuid4(), 'radicado_id': radicado_id,
                'tipo_clasificacion': 'pqrsd', 'sub_tipo': 'peticion',
                'dependencia_destino_id': None, 'tipo_pqrsd_id': tipo_pqrsd_id,
                'fuente': 'manual', 'clasificado_por_user_id': ACTOR_USER_ID,
                'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
            },
            {'id': uuid4()},  # audit RadicadoClasificado
            # crear_desde_radicado: datos del radicado
            {
                'id': radicado_id, 'asunto': 'X', 'descripcion': None,
                'tercero_id': None, 'fecha_radicacion': datetime.now(),
                'actor_snapshot': '{}',
            },
            # tipo_pqrsd
            {'termino_dias': 15, 'tipo_dias': 'habiles'},
            # fecha_limite
            {'fecha_limite': datetime.now() + timedelta(days=15)},
            # INSERT pqrsd
            {
                'id': pqrsd_id, 'radicado_entrada_id': radicado_id,
                'tipo_pqrsd_id': tipo_pqrsd_id, 'tercero_id': None,
                'asunto': 'X', 'descripcion': None,
                'dependencia_responsable_id': None,
                'usuario_responsable_id': None,
                'fecha_recepcion': datetime.now(),
                'fecha_limite_respuesta': datetime.now() + timedelta(days=15),
                'estado': 'clasificada', 'prioridad': 'normal', 'reserva': False,
            },
            {'id': uuid4()},  # audit PQRSDCreada
        ]
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{radicado_id}/clasificar',
            json={
                'tipo_clasificacion': 'pqrsd',
                'sub_tipo': 'peticion',
                'tipo_pqrsd_id': str(tipo_pqrsd_id),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['recursos_creados']['pqrsd_id'] == str(pqrsd_id)
