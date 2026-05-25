"""Tests TestClient para handlers del bloque 18 (RPA EP-017)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        'app.gd.handlers.rpa_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _ident_dict(estado='activa', **extra):
    base = {
        'id': uuid4(), 'codigo': 'BOT_001', 'nombre': 'Bot',
        'descripcion': None, 'tipo': 'robot_rpa',
        'api_key_prefijo': 'gdat_abc',
        'scopes': [], 'estado': estado, 'rate_limit_rpm': 100,
        'ultimo_uso_en': None, 'total_requests': 0,
        'dependencia_alcance_id': None,
        'motivo_revocacion': None, 'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _tarea_dict(estado='pending', **extra):
    base = {
        'id': uuid4(), 'identidad_tecnica_id': None,
        'tipo': 'radicar_pdf', 'payload': {},
        'prioridad': 'normal', 'estado': estado,
        'resultado': None, 'error_texto': None, 'error_codigo': None,
        'claim_token': None, 'claim_expira_en': None,
        'created_by_user_id': uuid4(),
        'started_at': None, 'completed_at': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _sub_dict(estado='activa', **extra):
    base = {
        'id': uuid4(), 'identidad_tecnica_id': uuid4(),
        'url': 'https://example.com/hook',
        'eventos_suscritos': ['PQRSDCreada'],
        'descripcion': None, 'estado': estado,
        'max_intentos': 5, 'backoff_inicial_segundos': 30,
        'backoff_max_segundos': 3600,
        'total_eventos_entregados': 0, 'total_eventos_fallidos': 0,
        'ultimo_evento_en': None,
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Identidades técnicas
# =============================================================================
class TestIdentidadesHandlers:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.return_value = _ident_dict()
        r = client.post(
            '/v1/gd/identidades-tecnicas',
            json={'codigo': 'BOT_X', 'nombre': 'Bot X',
                  'tipo': 'robot_rpa', 'scopes': ['*']},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert 'api_key' in body

    def test_crear_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/v1/gd/identidades-tecnicas',
            json={'codigo': 'DUP', 'nombre': 'Dup',
                  'tipo': 'agente_ia'},
        )
        assert r.status_code == 409

    def test_crear_codigo_invalido(self, conn, client):
        r = client.post(
            '/v1/gd/identidades-tecnicas',
            json={'codigo': 'minusculas',  # pattern ^[A-Z0-9_]+$
                  'nombre': 'X', 'tipo': 'agente_ia'},
        )
        assert r.status_code == 422

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/identidades-tecnicas')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/identidades-tecnicas?tipo=robot_rpa'
            '&estado=activa&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _ident_dict()
        r = client.get(f'/v1/gd/identidades-tecnicas/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/identidades-tecnicas/{uuid4()}')
        assert r.status_code == 404

    def test_revocar_ok(self, conn, client):
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _ident_dict(estado='revocada')
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/revocar',
            json={'motivo': 'comprometida por filtración'},
        )
        assert r.status_code == 200

    def test_revocar_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/revocar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_revocar_ya_revocada(self, conn, client):
        conn.fetchval.return_value = 'revocada'
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/revocar',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409

    def test_rotar_key_ok(self, conn, client):
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _ident_dict()
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/rotar-key',
            json={},
        )
        assert r.status_code == 200, r.text
        assert 'api_key' in r.json()

    def test_rotar_key_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/rotar-key',
            json={},
        )
        assert r.status_code == 404

    def test_rotar_key_revocada(self, conn, client):
        conn.fetchval.return_value = 'revocada'
        r = client.post(
            f'/v1/gd/identidades-tecnicas/{uuid4()}/rotar-key',
            json={},
        )
        assert r.status_code == 409


# =============================================================================
# Tareas RPA
# =============================================================================
class TestTareasHandlers:
    def test_crear_tarea(self, conn, client):
        conn.fetchrow.return_value = _tarea_dict()
        r = client.post(
            '/v1/gd/rpa/tareas',
            json={'tipo': 'radicar_pdf', 'payload': {'k': 'v'},
                  'prioridad': 'alta'},
        )
        assert r.status_code == 201

    def test_pendientes(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/rpa/tareas-pendientes?tipo=radicar_pdf')
        assert r.status_code == 200

    def test_reclamar_ok(self, conn, client):
        conn.fetchrow.return_value = _tarea_dict(estado='in_progress')
        r = client.post(
            f'/v1/gd/rpa/tareas/reclamar?identidad_tecnica_id={uuid4()}',
            json={'ttl_segundos': 300},
        )
        assert r.status_code == 200

    def test_reclamar_sin_tareas(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/rpa/tareas/reclamar?identidad_tecnica_id={uuid4()}',
            json={'ttl_segundos': 60},
        )
        assert r.status_code == 404

    def test_reportar_done(self, conn, client):
        token = uuid4()
        conn.fetchrow.side_effect = [
            {'claim_token': token,
             'claim_expira_en': datetime.now(timezone.utc) + timedelta(minutes=5),
             'estado': 'in_progress'},
            _tarea_dict(estado='done'),
        ]
        r = client.post(
            f'/v1/gd/rpa/tareas/{uuid4()}/resultado',
            json={'claim_token': str(token), 'estado': 'done',
                  'resultado': {'ok': True}},
        )
        assert r.status_code == 200

    def test_reportar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/rpa/tareas/{uuid4()}/resultado',
            json={'claim_token': str(uuid4()), 'estado': 'done'},
        )
        assert r.status_code == 404

    def test_reportar_claim_invalido(self, conn, client):
        conn.fetchrow.return_value = {
            'claim_token': uuid4(),
            'claim_expira_en': datetime.now(timezone.utc),
            'estado': 'in_progress',
        }
        r = client.post(
            f'/v1/gd/rpa/tareas/{uuid4()}/resultado',
            json={'claim_token': str(uuid4()), 'estado': 'done'},
        )
        assert r.status_code == 409

    def test_listar_tareas(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/rpa/tareas')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/rpa/tareas?estado=done&tipo=radicar_pdf'
            f'&identidad_tecnica_id={uuid4()}&limit=10',
        )
        assert r.status_code == 200


# =============================================================================
# Webhooks
# =============================================================================
class TestWebhooksHandlers:
    def test_crear_sub_ok(self, conn, client):
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _sub_dict()
        r = client.post(
            '/v1/gd/webhooks/suscripciones',
            json={'identidad_tecnica_id': str(uuid4()),
                  'url': 'https://example.com/webhook',
                  'eventos_suscritos': ['PQRSDCreada']},
        )
        assert r.status_code == 201, r.text
        assert 'secret' in r.json()

    def test_crear_sub_identidad_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            '/v1/gd/webhooks/suscripciones',
            json={'identidad_tecnica_id': str(uuid4()),
                  'url': 'https://x.com/hook',
                  'eventos_suscritos': ['*']},
        )
        assert r.status_code == 404

    def test_crear_sub_identidad_revocada(self, conn, client):
        conn.fetchval.return_value = 'revocada'
        r = client.post(
            '/v1/gd/webhooks/suscripciones',
            json={'identidad_tecnica_id': str(uuid4()),
                  'url': 'https://x.com/hook',
                  'eventos_suscritos': ['*']},
        )
        assert r.status_code == 409

    def test_crear_sub_url_invalida(self, conn, client):
        r = client.post(
            '/v1/gd/webhooks/suscripciones',
            json={'identidad_tecnica_id': str(uuid4()),
                  'url': 'ftp://invalido',
                  'eventos_suscritos': ['*']},
        )
        assert r.status_code == 422

    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/webhooks/suscripciones')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/webhooks/suscripciones?identidad_tecnica_id={uuid4()}'
            '&estado=activa&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _sub_dict()
        r = client.get(f'/v1/gd/webhooks/suscripciones/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/webhooks/suscripciones/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _sub_dict(estado='pausada')
        r = client.patch(
            f'/v1/gd/webhooks/suscripciones/{uuid4()}',
            json={'estado': 'pausada'},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.patch(
            f'/v1/gd/webhooks/suscripciones/{uuid4()}',
            json={'estado': 'pausada'},
        )
        assert r.status_code == 404

    def test_listar_deliveries(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/webhooks/deliveries')
        assert r.status_code == 200

    def test_listar_deliveries_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/webhooks/deliveries?suscripcion_id={uuid4()}'
            '&estado=failed&limit=10',
        )
        assert r.status_code == 200


# =============================================================================
# Rate limit info
# =============================================================================
class TestRateLimitHandlers:
    def test_info_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            _ident_dict(rate_limit_rpm=100),
            {'contador': 5},
        ]
        r = client.get(
            f'/v1/gd/rate-limit/identidades-tecnicas/{uuid4()}/info',
        )
        assert r.status_code == 200
        body = r.json()
        assert body['permitido'] is True
        assert body['contador_actual'] == 5

    def test_info_sin_limite(self, conn, client):
        conn.fetchrow.return_value = _ident_dict(rate_limit_rpm=None)
        r = client.get(
            f'/v1/gd/rate-limit/identidades-tecnicas/{uuid4()}/info',
        )
        assert r.status_code == 200
        assert r.json()['permitido'] is True

    def test_info_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(
            f'/v1/gd/rate-limit/identidades-tecnicas/{uuid4()}/info',
        )
        assert r.status_code == 404
