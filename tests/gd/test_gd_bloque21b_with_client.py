"""Tests TestClient para handlers del bloque 21b (EP-021 parte 2 — CIERRE)."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.handlers.perifericos2_handlers import (
    router_agentes, router_digit, router_perif_b, router_perif_literals,
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
    return {'PERM-PER-001': 'global'}


async def _noop_emit(*a, **k):
    return uuid4()


def build_app(conn_mock):
    app = FastAPI()
    from fastapi import APIRouter
    root = APIRouter(prefix='/api/v1/gd')
    # ORDEN crítico: literals primero (mismo patrón que routes.py global).
    root.include_router(router_perif_literals)
    root.include_router(router_perif_b)
    root.include_router(router_agentes)
    root.include_router(router_digit)
    app.include_router(root)

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
        'app.gd.handlers.perifericos2_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _lote(**extra):
    base = {
        'id': uuid4(), 'periferico_id': uuid4(),
        'usuario_id': uuid4(), 'modo_separacion': 'por_pagina',
        'radicado_id_default': None, 'estado': 'abierto',
        'calidad_dpi': 300, 'observacion': None,
        'total_documentos': 0,
        'iniciado_en': datetime.now(),
        'finalizado_en': None, 'timeout_en': datetime.now(),
    }
    base.update(extra)
    return base


def _mant(**extra):
    base = {
        'id': uuid4(), 'periferico_id': uuid4(),
        'tipo': 'preventivo', 'descripcion': 'Cal mensual',
        'fecha_estimada_fin': None,
        'iniciado_por_user_id': uuid4(),
        'iniciado_en': datetime.now(),
        'finalizado_en': None,
        'observacion_final': None, 'costo': None, 'repuestos': None,
        'finalizado_por_user_id': None, 'estado': 'en_curso',
    }
    base.update(extra)
    return base


# =============================================================================
# Lote
# =============================================================================
class TestLote:
    def test_iniciar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'activo'},
            _lote(),
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/digitalizar-lote',
            json={'modo_separacion': 'por_pagina', 'calidad_dpi': 300},
        )
        assert r.status_code == 201

    def test_iniciar_perif_inactivo_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'inactivo'},
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/digitalizar-lote',
            json={'modo_separacion': 'por_pagina'},
        )
        assert r.status_code == 409

    def test_iniciar_perif_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/digitalizar-lote',
            json={'modo_separacion': 'por_pagina'},
        )
        assert r.status_code == 404

    def test_obtener_progreso_ok(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _lote()]
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/perifericos/lotes/{uuid4()}')
        assert r.status_code == 200

    def test_obtener_progreso_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.get(f'/api/v1/gd/perifericos/lotes/{uuid4()}')
        assert r.status_code == 404

    def test_finalizar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _lote(),
            _lote(estado='finalizado'),
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/lotes/{uuid4()}/finalizar',
            json={'observacion_final': 'completado'},
        )
        assert r.status_code == 200

    def test_finalizar_lote_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/perifericos/lotes/{uuid4()}/finalizar',
            json={},
        )
        assert r.status_code == 404

    def test_finalizar_lote_ya_finalizado_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _lote(estado='finalizado'),
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/lotes/{uuid4()}/finalizar',
            json={},
        )
        assert r.status_code == 409


# =============================================================================
# Contexto activo
# =============================================================================
class TestContexto:
    def test_upsert(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'user_id': uuid4(),
             'periferico_id': uuid4(), 'radicado_activo_id': uuid4(),
             'expira_en': datetime.now(),
             'created_at': datetime.now()},
        ]
        r = client.post(
            '/api/v1/gd/perifericos/contexto-activo',
            json={'periferico_id': str(uuid4()),
                  'radicado_activo_id': str(uuid4())},
        )
        assert r.status_code == 200

    def test_delete(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.execute.return_value = 'DELETE 1'
        r = client.delete(
            '/api/v1/gd/perifericos/contexto-activo'
            f'?periferico_id={uuid4()}',
        )
        assert r.status_code == 200
        assert r.json()['eliminado'] is True


# =============================================================================
# Eventos + dashboard
# =============================================================================
class TestEventos:
    def test_listar(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/perifericos/{uuid4()}/eventos')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        desde = (datetime.now() - timedelta(days=1)).isoformat()
        hasta = datetime.now().isoformat()
        r = client.get(
            f'/api/v1/gd/perifericos/{uuid4()}/eventos'
            f'?desde={desde}&hasta={hasta}&resultado=fallo&limit=10',
        )
        assert r.status_code == 200

    def test_fallos(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        desde = (datetime.now() - timedelta(hours=24)).isoformat()
        r = client.get(
            f'/api/v1/gd/perifericos/eventos/fallos?desde={desde}',
        )
        assert r.status_code == 200


# =============================================================================
# Mantenimiento
# =============================================================================
class TestMantenimiento:
    def test_iniciar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'activo'},
            _mant(),
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/mantenimiento',
            json={'tipo': 'preventivo',
                  'descripcion': 'Calibración mensual'},
        )
        assert r.status_code == 201

    def test_iniciar_perif_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/mantenimiento',
            json={'descripcion': 'Calibración'},
        )
        assert r.status_code == 404

    def test_finalizar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'en_curso'},
            _mant(estado='finalizado'),
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}'
            f'/mantenimiento/{uuid4()}/finalizar',
            json={'observacion_final': 'OK calibrado',
                  'costo': 50.0,
                  'repuestos': [{'parte': 'rodillo'}]},
        )
        assert r.status_code == 200

    def test_finalizar_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}'
            f'/mantenimiento/{uuid4()}/finalizar',
            json={'observacion_final': 'X' * 20},
        )
        assert r.status_code == 404

    def test_finalizar_ya_finalizado_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'finalizado'},
        ]
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}'
            f'/mantenimiento/{uuid4()}/finalizar',
            json={'observacion_final': 'ya estaba'},
        )
        assert r.status_code == 409


# =============================================================================
# Agente local
# =============================================================================
class TestAgente:
    def test_emparejar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'nombre_equipo': 'Counter-1',
             'version_agente': '0.1.0',
             'periferico_ids': [uuid4()],
             'fingerprint_publico': b'\x01',
             'estado': 'pendiente', 'motivo_revocacion': None,
             'ultimo_handshake_en': None,
             'registrado_por_user_id': uuid4(),
             'fecha_registro': datetime.now(),
             'token_emparejamiento_expira':
                 datetime.now() + timedelta(minutes=10)},
        ]
        conn.fetchval.return_value = 1
        r = client.post(
            '/api/v1/gd/agentes-locales/emparejar',
            json={
                'nombre_equipo': 'Counter-1',
                'version_agente': '0.1.0',
                'perifericos': [str(uuid4())],
                'fingerprint_publico_b64':
                    base64.b64encode(b'fake_pubkey').decode(),
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body['estado'] == 'pendiente'
        assert len(body['token_emparejamiento']) >= 30

    def test_emparejar_perifericos_invalidos_404(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetchval.return_value = 0
        r = client.post(
            '/api/v1/gd/agentes-locales/emparejar',
            json={
                'nombre_equipo': 'Counter-2',
                'perifericos': [str(uuid4())],
                'fingerprint_publico_b64':
                    base64.b64encode(b'k' * 32).decode(),
            },
        )
        assert r.status_code == 404

    def test_emparejar_fingerprint_invalido_409(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetchval.return_value = 1
        r = client.post(
            '/api/v1/gd/agentes-locales/emparejar',
            json={
                'nombre_equipo': 'Counter-2',
                'perifericos': [str(uuid4())],
                'fingerprint_publico_b64': 'no_es_base64_!!!@@@',
            },
        )
        assert r.status_code == 409

    def test_revocar_ok(self, conn, client):
        aid = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': aid, 'estado': 'activo'},
            {'id': aid, 'nombre_equipo': 'X',
             'version_agente': None, 'periferico_ids': [],
             'estado': 'revocado', 'motivo_revocacion': 'X',
             'ultimo_handshake_en': None,
             'registrado_por_user_id': uuid4(),
             'fecha_registro': datetime.now()},
        ]
        r = client.post(
            f'/api/v1/gd/agentes-locales/{aid}/revocar',
            json={'motivo': 'equipo comprometido'},
        )
        assert r.status_code == 200

    def test_revocar_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/agentes-locales/{uuid4()}/revocar',
            json={'motivo': 'X' * 20},
        )
        assert r.status_code == 404

    def test_revocar_ya_revocado_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'revocado'},
        ]
        r = client.post(
            f'/api/v1/gd/agentes-locales/{uuid4()}/revocar',
            json={'motivo': 'X' * 20},
        )
        assert r.status_code == 409


# =============================================================================
# Historial + export
# =============================================================================
class TestHistorial:
    def test_historial_perif(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/gd/perifericos/{uuid4()}/historial')
        assert r.status_code == 200

    def test_historial_perif_con_filtros(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(
            f'/api/v1/gd/perifericos/{uuid4()}/historial'
            '?tipo_operacion=impresion&limit=50',
        )
        assert r.status_code == 200

    def test_historial_global(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(
            '/api/v1/gd/perifericos/historial-uso-global'
            f'?usuario_id={uuid4()}&periferico_id={uuid4()}',
        )
        assert r.status_code == 200

    def test_exportar(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetchval.return_value = 100
        r = client.post(
            '/api/v1/gd/perifericos/historial/exportar',
            json={'formato': 'csv'},
        )
        assert r.status_code == 202
        body = r.json()
        assert body['formato'] == 'csv'
        assert body['total_filas'] == 100


# =============================================================================
# Reemplazo digitalización
# =============================================================================
class TestReemplazo:
    def test_ok(self, conn, client):
        did = uuid4()
        nuevo = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': did, 'radicado_id': uuid4(),
             'periferico_id': uuid4(),
             'tipo_digitalizacion': 'individual',
             'calidad_dpi': 200, 'estado': 'correcta'},
            {'id': nuevo, 'fecha_digitalizacion': datetime.now()},
        ]
        r = client.post(
            f'/api/v1/gd/digitalizaciones/{did}/reemplazar',
            json={'motivo': 'Calidad baja: DPI insuficiente',
                  'archivo_digital_id_nuevo': str(uuid4())},
        )
        assert r.status_code == 201

    def test_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/api/v1/gd/digitalizaciones/{uuid4()}/reemplazar',
            json={'motivo': 'X' * 20,
                  'archivo_digital_id_nuevo': str(uuid4())},
        )
        assert r.status_code == 404

    def test_ya_reemplazada_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'radicado_id': uuid4(),
             'periferico_id': uuid4(),
             'tipo_digitalizacion': 'individual',
             'calidad_dpi': 200, 'estado': 'reemplazada'},
        ]
        r = client.post(
            f'/api/v1/gd/digitalizaciones/{uuid4()}/reemplazar',
            json={'motivo': 'X' * 20,
                  'archivo_digital_id_nuevo': str(uuid4())},
        )
        assert r.status_code == 409

    def test_motivo_corto_422(self, conn, client):
        r = client.post(
            f'/api/v1/gd/digitalizaciones/{uuid4()}/reemplazar',
            json={'motivo': 'corto',
                  'archivo_digital_id_nuevo': str(uuid4())},
        )
        assert r.status_code == 422


# =============================================================================
# Gate de módulo en handlers parte 2
# =============================================================================
class TestGate:
    def test_lote_modulo_inactivo_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/perifericos/{uuid4()}/digitalizar-lote',
            json={'modo_separacion': 'por_pagina'},
        )
        assert r.status_code == 404

    def test_agente_modulo_inactivo_404(self, conn, client):
        conn.fetchrow.return_value = {'activado': False}
        r = client.post(
            '/api/v1/gd/agentes-locales/emparejar',
            json={'nombre_equipo': 'Counter-A',
                  'perifericos': [str(uuid4())],
                  'fingerprint_publico_b64':
                      base64.b64encode(b'k' * 32).decode()},
        )
        assert r.status_code == 404

    def test_reemplazo_modulo_inactivo_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/digitalizaciones/{uuid4()}/reemplazar',
            json={'motivo': 'X' * 20,
                  'archivo_digital_id_nuevo': str(uuid4())},
        )
        assert r.status_code == 404
