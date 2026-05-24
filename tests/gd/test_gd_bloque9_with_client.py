"""Tests TestClient para handlers del bloque 9 (correspondencia EP-008)."""
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
        'PERM-CI-001': 'global', 'PERM-CI-002': 'global',
        'PERM-CE-001': 'global', 'PERM-CE-002': 'global',
    }


async def _noop_emit(*args, **kwargs):
    return uuid4()


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
    monkeypatch.setattr(
        'app.gd.handlers.correspondencia_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _corresp_dict(
    estado='enviada', tipo='interna', usuario_proyecta=None, **extra,
):
    base = {
        'id': uuid4(), 'tipo': tipo,
        'dependencia_origen_id': uuid4(),
        'dependencia_destino_id': None,
        'tercero_remitente_id': None,
        'radicado_entrada_id': None, 'radicado_salida_id': None,
        'documento_principal_id': None, 'plantilla_id': None,
        'asunto': 'A', 'contenido_borrador': 'X',
        'prioridad': 'normal', 'requiere_respuesta': False,
        'fecha_limite_respuesta': None, 'estado': estado,
        'usuario_proyecta_id': usuario_proyecta or uuid4(),
        'usuario_revisa_id': None, 'usuario_aprueba_id': None,
        'usuario_firma_id': None, 'usuario_envio_id': None,
        'fecha_envio': None, 'fecha_aprobacion': None,
        'fecha_firma': None, 'fecha_radicacion': None,
        'observaciones_devolucion': None,
        'canal_envio_id': None, 'soporte_envio_uri': None,
        'soporte_envio_codigo_rastreo': None, 'fecha_registro_soporte': None,
        'anulada_en': None, 'motivo_anulacion': None,
        'correspondencia_padre_id': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _dest_dict(tipo='dependencia', **extra):
    base = {
        'id': uuid4(), 'correspondencia_id': uuid4(),
        'tipo_destinatario': tipo,
        'dependencia_id': uuid4() if tipo == 'dependencia' else None,
        'tercero_id': uuid4() if tipo == 'tercero' else None,
        'tipo_copia': 'principal',
        'fecha_lectura': None, 'leida_por_user_id': None,
    }
    base.update(extra)
    return base


# =============================================================================
# Listado + detalle
# =============================================================================
class TestListadoYDetalle:
    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/api/v1/gd/correspondencia')
        assert r.status_code == 200
        assert r.json()['total'] == 0

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            '/api/v1/gd/correspondencia?tipo=interna&estado=enviada,leida'
            f'&dependencia_id={uuid4()}&tercero_id={uuid4()}&limit=10',
        )
        assert r.status_code == 200

    def test_listar_externa_recibida(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get('/api/v1/gd/correspondencia/externa/recibida')
        assert r.status_code == 200

    def test_listar_externa_recibida_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = client.get(
            f'/api/v1/gd/correspondencia/externa/recibida?dependencia={uuid4()}'
            '&estado=derivada,gestionada&limit=5',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _corresp_dict(tipo='interna', estado='enviada')
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/correspondencia/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_not_found(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/gd/correspondencia/{uuid4()}')
        assert r.status_code == 404


# =============================================================================
# Interna
# =============================================================================
class TestInternaHandlers:
    def test_crear_interna_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'permitido': True},
            _corresp_dict(tipo='interna', estado='enviada'),
            _dest_dict(),
        ]
        r = client.post(
            '/api/v1/gd/correspondencia/interna',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'Test',
                'contenido_borrador': 'mensaje',
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                    'tipo_copia': 'principal',
                }],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()['estado'] == 'enviada'

    def test_crear_interna_borrador(self, conn, client):
        conn.fetchrow.side_effect = [
            {'permitido': True},
            _corresp_dict(tipo='interna', estado='borrador'),
            _dest_dict(),
        ]
        r = client.post(
            '/api/v1/gd/correspondencia/interna',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'Test', 'enviar_inmediato': False,
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 201

    def test_crear_interna_409_regla(self, conn, client):
        conn.fetchrow.return_value = {'permitido': False}
        r = client.post(
            '/api/v1/gd/correspondencia/interna',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'Test',
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'comunicacion_no_permitida'

    def test_crear_interna_422_destinatario_tercero(self, conn, client):
        # Schema valida: interna NO admite tercero
        r = client.post(
            '/api/v1/gd/correspondencia/interna',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'Test',
                'destinatarios': [{
                    'tipo_destinatario': 'tercero',
                    'tercero_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 422

    def test_marcar_leida_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4()},
            _corresp_dict(tipo='interna', estado='leida'),
        ]
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/marcar-leida',
            json={'dependencia_id': str(uuid4())},
        )
        assert r.status_code == 200

    def test_marcar_leida_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/marcar-leida',
            json={'dependencia_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_responder_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'dependencia_origen_id': uuid4(), 'tipo': 'interna',
             'estado': 'enviada'},
            _corresp_dict(tipo='interna', estado='enviada'),
            _dest_dict(),
        ]
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/responder',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'RE: X', 'contenido_borrador': 'resp',
            },
        )
        assert r.status_code == 201

    def test_responder_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/responder',
            json={'dependencia_origen_id': str(uuid4()), 'asunto': 'RE: Asunto'},
        )
        assert r.status_code == 404

    def test_responder_409_tipo(self, conn, client):
        conn.fetchrow.return_value = {
            'dependencia_origen_id': uuid4(),
            'tipo': 'externa_recibida', 'estado': 'derivada',
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/responder',
            json={'dependencia_origen_id': str(uuid4()), 'asunto': 'RE: Asunto'},
        )
        assert r.status_code == 409

    def test_reenviar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'asunto': 'X', 'contenido_borrador': 'msg',
             'documento_principal_id': None, 'tipo': 'interna'},
            {'permitido': True},
            _corresp_dict(tipo='interna', estado='enviada'),
            _dest_dict(),
        ]
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/reenviar',
            json={
                'dependencia_origen_id': str(uuid4()),
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                }],
                'observaciones': 'FYI',
            },
        )
        assert r.status_code == 201

    def test_reenviar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/reenviar',
            json={
                'dependencia_origen_id': str(uuid4()),
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 404


# =============================================================================
# Externa recibida
# =============================================================================
class TestExternaRecibidaHandler:
    def test_gestionar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'tipo': 'externa_recibida', 'estado': 'derivada'},
            _corresp_dict(tipo='externa_recibida', estado='gestionada'),
            _corresp_dict(tipo='externa_recibida', estado='gestionada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/gestionar',
            json={'observaciones': 'gestionada por mí'},
        )
        assert r.status_code == 200

    def test_gestionar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/gestionar',
            json={'observaciones': 'gestionada'},
        )
        assert r.status_code == 404

    def test_gestionar_409_tipo(self, conn, client):
        conn.fetchrow.return_value = {'tipo': 'interna', 'estado': 'enviada'}
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/gestionar',
            json={'observaciones': 'gestionada'},
        )
        assert r.status_code == 409


# =============================================================================
# Workflow externa enviada
# =============================================================================
class TestWorkflowHandlers:
    def test_crear_externa_borrador_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            _corresp_dict(tipo='externa_enviada', estado='borrador'),
            _dest_dict(tipo='tercero'),
        ]
        r = client.post(
            '/api/v1/gd/correspondencia/externa/borrador',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'Oficio externo',
                'destinatarios': [{
                    'tipo_destinatario': 'tercero',
                    'tercero_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 201, r.text

    def test_crear_externa_borrador_422_sin_tercero(self, conn, client):
        r = client.post(
            '/api/v1/gd/correspondencia/externa/borrador',
            json={
                'dependencia_origen_id': str(uuid4()),
                'asunto': 'X',
                'destinatarios': [{
                    'tipo_destinatario': 'dependencia',
                    'dependencia_id': str(uuid4()),
                }],
            },
        )
        assert r.status_code == 422

    def test_enviar_revision_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
             'usuario_proyecta_id': uuid4()},
            _corresp_dict(tipo='externa_enviada', estado='en_revision'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar-a-revision',
            json={'observaciones': 'lista'},
        )
        assert r.status_code == 200

    def test_enviar_revision_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar-a-revision', json={},
        )
        assert r.status_code == 404

    def test_enviar_revision_409(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
            'usuario_proyecta_id': uuid4(),
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar-a-revision', json={},
        )
        assert r.status_code == 409

    def test_revisar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'en_revision',
             'usuario_proyecta_id': proyecta},
            _corresp_dict(tipo='externa_enviada', estado='aprobada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 200

    def test_revisar_separacion(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'en_revision',
            'usuario_proyecta_id': ACTOR_USER_ID,
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/revisar',
            json={'resultado': 'ok'},
        )
        assert r.status_code == 403

    def test_aprobar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
             'usuario_proyecta_id': proyecta},
            _corresp_dict(tipo='externa_enviada', estado='aprobada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/aprobar', json={},
        )
        assert r.status_code == 200

    def test_aprobar_separacion(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
            'usuario_proyecta_id': ACTOR_USER_ID,
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/aprobar', json={},
        )
        assert r.status_code == 403

    def test_firmar_ok(self, conn, client):
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
             'usuario_proyecta_id': proyecta},
            _corresp_dict(tipo='externa_enviada', estado='firmada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/firmar',
            json={'firma_id': str(uuid4())},
        )
        assert r.status_code == 200

    def test_firmar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/firmar', json={},
        )
        assert r.status_code == 404

    def test_radicar_ok(self, conn, client, monkeypatch):
        async def fake_sig(c, *, tenant_id, vigencia, tipo_radicado):
            return '2026-S-00100'
        monkeypatch.setattr(
            'app.gd.services.consecutivos.siguiente_radicado', fake_sig,
        )
        conn.fetchrow.side_effect = [
            {'tipo': 'externa_enviada', 'estado': 'firmada',
             'asunto': 'A', 'contenido_borrador': 'X',
             'dependencia_origen_id': uuid4(), 'usuario_proyecta_id': uuid4()},
            {'id': uuid4(), 'numero_radicado': '2026-S-00100',
             'fecha_radicacion': datetime.now()},
            _corresp_dict(tipo='externa_enviada', estado='radicada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/radicar-salida', json={},
        )
        assert r.status_code == 200, r.text

    def test_radicar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/radicar-salida', json={},
        )
        assert r.status_code == 404

    def test_enviar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'radicada',
             'usuario_proyecta_id': uuid4()},
            _corresp_dict(tipo='externa_enviada', estado='enviada'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar', json={},
        )
        assert r.status_code == 200

    def test_enviar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar', json={},
        )
        assert r.status_code == 404

    def test_enviar_409(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/enviar', json={},
        )
        assert r.status_code == 409

    def test_registrar_soporte_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'enviada',
             'usuario_proyecta_id': uuid4()},
            _corresp_dict(tipo='externa_enviada', estado='enviada',
                           soporte_envio_uri='s3://x/y.pdf'),
        ]
        conn.fetch.return_value = []
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/registrar-soporte-envio',
            json={'soporte_envio_uri': 's3://bucket/x.pdf',
                  'codigo_rastreo': 'ABC123'},
        )
        assert r.status_code == 200

    def test_registrar_soporte_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/registrar-soporte-envio',
            json={'soporte_envio_uri': 's3://x'},
        )
        assert r.status_code == 404


# =============================================================================
# Anulación
# =============================================================================
class TestAnulacionHandlers:
    def test_solicitar_anulacion_ok(self, conn, client):
        conn.fetchval.return_value = 'enviada'
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'correspondencia',
            'entidad_afectada_id': uuid4(), 'solicitante_user_id': uuid4(),
            'motivo': 'duplicado de envío', 'decision': 'pendiente',
            'aprobador_user_id': None, 'observacion_decision': None,
            'fecha_solicitud': datetime.now(), 'fecha_decision': None,
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/anular',
            json={'motivo': 'fue duplicado del envío anterior'},
        )
        assert r.status_code == 201, r.text

    def test_solicitar_anulacion_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_solicitar_anulacion_409(self, conn, client):
        conn.fetchval.return_value = 'anulada'
        r = client.post(
            f'/api/v1/gd/correspondencia/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_aprobar_anulacion_ok(self, conn, client):
        corresp_id = uuid4()
        conn.fetchrow.side_effect = [
            {'entidad_afectada_id': corresp_id, 'decision': 'pendiente'},
            {'id': uuid4(), 'tipo_entidad': 'correspondencia',
             'entidad_afectada_id': corresp_id, 'solicitante_user_id': uuid4(),
             'motivo': 'X', 'decision': 'aprobada',
             'aprobador_user_id': uuid4(), 'observacion_decision': 'ok',
             'fecha_solicitud': datetime.now(), 'fecha_decision': datetime.now()},
        ]
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/aprobar',
            json={'observacion': 'aprobada'},
        )
        assert r.status_code == 200

    def test_aprobar_anulacion_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/aprobar',
            json={},
        )
        assert r.status_code == 404

    def test_aprobar_anulacion_409(self, conn, client):
        conn.fetchrow.return_value = {
            'entidad_afectada_id': uuid4(), 'decision': 'aprobada',
        }
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/aprobar',
            json={},
        )
        assert r.status_code == 409

    def test_rechazar_anulacion_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'decision': 'pendiente'},
            {'id': uuid4(), 'tipo_entidad': 'correspondencia',
             'entidad_afectada_id': uuid4(), 'solicitante_user_id': uuid4(),
             'motivo': 'X', 'decision': 'rechazada',
             'aprobador_user_id': uuid4(),
             'observacion_decision': 'no procede',
             'fecha_solicitud': datetime.now(), 'fecha_decision': datetime.now()},
        ]
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/rechazar',
            json={'observacion': 'no procede'},
        )
        assert r.status_code == 200

    def test_rechazar_anulacion_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/rechazar',
            json={'observacion': 'no procede'},
        )
        assert r.status_code == 404

    def test_rechazar_anulacion_409(self, conn, client):
        conn.fetchrow.return_value = {'decision': 'aprobada'}
        r = client.post(
            f'/api/v1/gd/correspondencia/solicitudes-anulacion/{uuid4()}/rechazar',
            json={'observacion': 'no procede'},
        )
        assert r.status_code == 409
