"""Tests TestClient para handlers del bloque 8 (PQRSD cierre EP-007).

Cubre handlers de:
- workflow respuesta (GD-API-0047)
- cerrar / reabrir (GD-API-0048)
- trasladar competencia (GD-API-0049)
- solicitar info adicional (GD-API-0050)
- dashboard (GD-API-0051)
"""
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
        'PERM-USR-001': 'global', 'PERM-VU-001': 'global',
        'PERM-VU-005': 'global', 'PERM-PQRSD-019': 'global',
        'PERM-PQRSD-020': 'global', 'PERM-PQRSD-021': 'global',
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


async def _noop_emit(*args, **kwargs):
    """Stub que evita tener que mockear conn.fetchrow para auditoría."""
    return uuid4()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    # Importante: parchear en el módulo handler (que lo importa), no solo en
    # el módulo donde está definido.
    monkeypatch.setattr(
        'app.gd.handlers.pqrsd_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _resp_row_dict(estado: str, **extra):
    base = {
        'id': uuid4(), 'pqrsd_id': uuid4(),
        'documento_id': None, 'plantilla_id': None,
        'contenido_borrador': 'x', 'usuario_proyecta_id': uuid4(),
        'usuario_revisa_id': None, 'usuario_aprueba_id': None,
        'usuario_firma_id': None, 'radicado_salida_id': None,
        'estado': estado,
        'fecha_proyeccion': datetime.now(), 'fecha_revision': None,
        'fecha_aprobacion': None, 'fecha_firma': None,
        'fecha_radicacion': None, 'fecha_envio': None,
        'observaciones_devolucion': None,
    }
    base.update(extra)
    return base


def _pqrsd_dict(estado='asignada'):
    return {
        'id': uuid4(), 'radicado_entrada_id': uuid4(),
        'tipo_pqrsd_id': uuid4(), 'tercero_id': None,
        'asunto': 'A', 'descripcion': 'D',
        'dependencia_responsable_id': None, 'usuario_responsable_id': None,
        'fecha_recepcion': datetime.now(), 'fecha_limite_respuesta': datetime.now(),
        'estado': estado, 'prioridad': 'normal', 'reserva': False,
    }


# =============================================================================
# Workflow respuesta (6 endpoints)
# =============================================================================
class TestWorkflowHandlers:
    def test_enviar_a_revision_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('borrador', usuario_proyecta_id=proyecta),
            _resp_row_dict('en_revision', usuario_proyecta_id=proyecta),
            None,  # audit
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/enviar-a-revision',
            json={'observaciones': 'lista'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['estado'] == 'en_revision'

    def test_enviar_a_revision_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/enviar-a-revision', json={},
        )
        assert r.status_code == 404

    def test_enviar_a_revision_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('aprobada')
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/enviar-a-revision', json={},
        )
        assert r.status_code == 409

    def test_revisar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('en_revision', usuario_proyecta_id=proyecta),
            _resp_row_dict('aprobada', usuario_proyecta_id=proyecta),
            None,  # audit
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 200
        assert r.json()['estado'] == 'aprobada'

    def test_revisar_devolver(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('en_revision', usuario_proyecta_id=proyecta),
            _resp_row_dict('devuelta', usuario_proyecta_id=proyecta,
                           observaciones_devolucion='corrige'),
            None,
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/revisar',
            json={'resultado': 'devolver', 'observaciones': 'corrige'},
        )
        assert r.status_code == 200
        assert r.json()['estado'] == 'devuelta'

    def test_revisar_separacion_funciones(self, conn, client):
        # actor == proyecta → 403
        conn.fetchrow.return_value = _resp_row_dict(
            'en_revision', usuario_proyecta_id=ACTOR_USER_ID,
        )
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 403
        assert r.json()['detail']['code'] == 'separacion_funciones'

    def test_revisar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 404

    def test_revisar_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('borrador')
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 409

    def test_aprobar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('aprobada', usuario_proyecta_id=proyecta),
            _resp_row_dict('aprobada', usuario_proyecta_id=proyecta),
            None,
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/aprobar', json={},
        )
        assert r.status_code == 200

    def test_aprobar_separacion(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict(
            'aprobada', usuario_proyecta_id=ACTOR_USER_ID,
        )
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/aprobar', json={})
        assert r.status_code == 403

    def test_aprobar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/aprobar', json={})
        assert r.status_code == 404

    def test_aprobar_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('borrador')
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/aprobar', json={})
        assert r.status_code == 409

    def test_firmar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('aprobada', usuario_proyecta_id=proyecta),
            _resp_row_dict('firmada', usuario_proyecta_id=proyecta),
            None,
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/firmar',
            json={'firma_id': str(uuid4())},
        )
        assert r.status_code == 200

    def test_firmar_separacion(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict(
            'aprobada', usuario_proyecta_id=ACTOR_USER_ID,
        )
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/firmar', json={})
        assert r.status_code == 403

    def test_firmar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/firmar', json={})
        assert r.status_code == 404

    def test_firmar_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('borrador')
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/firmar', json={})
        assert r.status_code == 409

    def test_radicar_salida_ok(self, conn, client, monkeypatch):
        async def fake_sig(c, *, tenant_id, vigencia, tipo_radicado):
            return '2026-S-00001'
        monkeypatch.setattr(
            'app.gd.services.consecutivos.siguiente_radicado', fake_sig,
        )
        proyecta = uuid4()
        pqrsd_id = uuid4()
        radicado_id = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('firmada', usuario_proyecta_id=proyecta, pqrsd_id=pqrsd_id),
            {'asunto': 'X', 'descripcion': 'Y',
             'dependencia_responsable_id': uuid4(), 'tercero_id': None,
             'radicado_entrada_id': uuid4()},
            {'id': radicado_id, 'numero_radicado': '2026-S-00001',
             'fecha_radicacion': datetime.now()},
            _resp_row_dict('radicada', usuario_proyecta_id=proyecta, pqrsd_id=pqrsd_id,
                           radicado_salida_id=radicado_id),
            None,
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/radicar-salida', json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()['estado'] == 'radicada'

    def test_radicar_salida_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/radicar-salida', json={},
        )
        assert r.status_code == 404

    def test_radicar_salida_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('borrador')
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/radicar-salida', json={},
        )
        assert r.status_code == 409

    def test_enviar_respuesta_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row_dict('radicada', usuario_proyecta_id=proyecta),
            _resp_row_dict('enviada', usuario_proyecta_id=proyecta),
            None,
        ]
        r = client.post(
            f'/v1/gd/respuestas/{uuid4()}/enviar',
            json={'canal_envio_id': str(uuid4()),
                  'constancia_envio_uri': 's3://x/y.pdf'},
        )
        assert r.status_code == 200

    def test_enviar_respuesta_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/enviar', json={})
        assert r.status_code == 404

    def test_enviar_respuesta_409(self, conn, client):
        conn.fetchrow.return_value = _resp_row_dict('borrador')
        r = client.post(f'/v1/gd/respuestas/{uuid4()}/enviar', json={})
        assert r.status_code == 409


# =============================================================================
# Cerrar / Reabrir
# =============================================================================
class TestCierreHandlers:
    def test_cerrar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'enviada'},
            _pqrsd_dict(estado='cerrada'),
            None,  # audit
        ]
        conn.fetchval.return_value = 1
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/cerrar',
            json={'motivo': 'Respondida y enviada'},
        )
        assert r.status_code == 200, r.text

    def test_cerrar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/cerrar',
            json={'motivo': 'X' * 10},
        )
        assert r.status_code == 404

    def test_cerrar_sin_respuesta_falla(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'asignada'}
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/cerrar',
            json={'motivo': 'No quiero esperar'},
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'sin_respuesta_enviada'

    def test_cerrar_forzado(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'asignada'}, _pqrsd_dict(estado='cerrada'), None,
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/cerrar',
            json={'motivo': 'Retiro de solicitante',
                   'forzar_sin_respuesta': True},
        )
        assert r.status_code == 200

    def test_cerrar_ya_cerrada(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'cerrada'}
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/cerrar',
            json={'motivo': 'X' * 10, 'forzar_sin_respuesta': True},
        )
        assert r.status_code == 409

    def test_reabrir_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'cerrada'},
            _pqrsd_dict(estado='asignada'),
            None,
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reabrir',
            json={'motivo': 'Solicitante apeló', 'dias_adicionales': 10},
        )
        assert r.status_code == 200

    def test_reabrir_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reabrir',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_reabrir_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'asignada'}
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/reabrir',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409


# =============================================================================
# Traslado por competencia
# =============================================================================
class TestTrasladoHandler:
    def test_trasladar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'asignada', 'fecha_limite_respuesta': datetime.now()},
            _pqrsd_dict(estado='trasladada'),
            None,  # audit
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/trasladar-competencia',
            json={'entidad_competente_destino': 'Alcaldía Municipal',
                  'motivo': 'No es de nuestra competencia'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['estado'] == 'trasladada'

    def test_trasladar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/trasladar-competencia',
            json={'entidad_competente_destino': 'Otra Entidad',
                  'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_trasladar_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'cerrada',
                                       'fecha_limite_respuesta': None}
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/trasladar-competencia',
            json={'entidad_competente_destino': 'Otra Entidad',
                  'motivo': 'X' * 11},
        )
        assert r.status_code == 409


# =============================================================================
# Solicitar info adicional
# =============================================================================
class TestSolicitarInfoHandler:
    def test_solicitar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'asignada', 'fecha_limite_respuesta': datetime.now()},
            {'id': uuid4(), 'pqrsd_id': uuid4(),
             'tipo_evento': 'solicitud_info_adicional',
             'fecha_evento': datetime.now(),
             'motivo': 'falta info' * 2,
             'justificacion_legal': 'Cédula completa',
             'dias_afectados': 10, 'fecha_limite_anterior': datetime.now(),
             'fecha_limite_nueva': None, 'usuario_id': uuid4()},
            None,  # audit
        ]
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/solicitar-info-adicional',
            json={'motivo': 'Falta documentación',
                  'informacion_solicitada': 'Cédula completa',
                  'dias_estimados_suspension': 10},
        )
        assert r.status_code == 200, r.text

    def test_solicitar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/solicitar-info-adicional',
            json={'motivo': 'Falta info x', 'informacion_solicitada': 'Foto cédula',
                  'dias_estimados_suspension': 5},
        )
        assert r.status_code == 404

    def test_solicitar_estado_invalido(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'cerrada',
                                       'fecha_limite_respuesta': None}
        r = client.post(
            f'/v1/gd/pqrsd/{uuid4()}/solicitar-info-adicional',
            json={'motivo': 'Falta info x', 'informacion_solicitada': 'Foto cédula',
                  'dias_estimados_suspension': 5},
        )
        assert r.status_code == 409


# =============================================================================
# Dashboard
# =============================================================================
class TestDashboardHandler:
    def test_dashboard_sin_filtros(self, conn, client):
        conn.fetchrow.return_value = {
            'total_global': 10, 'total_vencidas': 2,
            'total_proximas_vencer': 1, 'total_cerradas': 5,
        }
        conn.fetch.return_value = [
            {'dependencia_id': uuid4(), 'estado': 'asignada',
             'tipo_pqrsd_id': uuid4(), 'total': 3, 'vencidas': 1,
             'proximas_vencer': 0, 'dias_promedio_resolucion': 2.5},
        ]
        r = client.get('/v1/gd/pqrsd/dashboard')
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['total_global'] == 10
        assert len(body['buckets']) == 1

    def test_dashboard_con_filtros(self, conn, client):
        conn.fetchrow.return_value = {
            'total_global': 0, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/pqrsd/dashboard?dependencia_id={uuid4()}'
            '&desde=2026-01-01T00:00:00&hasta=2026-05-23T00:00:00',
        )
        assert r.status_code == 200
        assert r.json()['total_global'] == 0
