"""Tests mocks para services del bloque 18 (RPA EP-017)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import rpa as svc


def _ident_row(estado='activa', **extra):
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


def _tarea_row(estado='pending', **extra):
    base = {
        'id': uuid4(), 'identidad_tecnica_id': None,
        'tipo': 'radicar_pdf', 'payload': {'k': 'v'},
        'prioridad': 'normal', 'estado': estado,
        'resultado': None, 'error_texto': None, 'error_codigo': None,
        'claim_token': None, 'claim_expira_en': None,
        'created_by_user_id': uuid4(),
        'started_at': None, 'completed_at': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _sub_row(estado='activa', **extra):
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
# Helpers
# =============================================================================
class TestHelpers:
    def test_generar_api_key(self):
        k = svc.generar_api_key()
        assert k.startswith('gdat_')
        assert len(k) >= 30

    def test_hash_api_key_deterministico(self):
        k = 'gdat_test'
        assert svc.hash_api_key(k) == svc.hash_api_key(k)

    def test_hash_distintos_keys_distintos(self):
        assert svc.hash_api_key('a') != svc.hash_api_key('b')

    def test_generar_webhook_secret(self):
        s = svc.generar_webhook_secret()
        assert s.startswith('whsec_')

    def test_hash_webhook_secret(self):
        s = 'whsec_test'
        assert svc.hash_webhook_secret(s) == svc.hash_webhook_secret(s)

    def test_calcular_next_retry_intento_1(self):
        r = svc.calcular_next_retry(
            intento=1, backoff_inicial_segundos=30,
            backoff_max_segundos=3600,
        )
        diff = (r - datetime.now(timezone.utc)).total_seconds()
        assert 25 < diff < 35

    def test_calcular_next_retry_exponencial(self):
        r1 = svc.calcular_next_retry(
            intento=1, backoff_inicial_segundos=10,
            backoff_max_segundos=600,
        )
        r3 = svc.calcular_next_retry(
            intento=3, backoff_inicial_segundos=10,
            backoff_max_segundos=600,
        )
        # 3er intento >= primer intento + delay
        assert (r3 - r1).total_seconds() > 20

    def test_calcular_next_retry_cap(self):
        r = svc.calcular_next_retry(
            intento=20, backoff_inicial_segundos=30,
            backoff_max_segundos=60,
        )
        diff = (r - datetime.now(timezone.utc)).total_seconds()
        # Limita por backoff_max=60
        assert diff <= 65


# =============================================================================
# Identidades técnicas
# =============================================================================
class TestIdentidades:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _ident_row()
        row, key = await svc.crear_identidad_tecnica(
            conn, tenant_id=uuid4(),
            codigo='BOT_X', nombre='Bot X',
            descripcion=None, tipo='robot_rpa',
            scopes=['PERM-*'], rate_limit_rpm=100,
            dependencia_alcance_id=None,
            created_by_user_id=uuid4(),
        )
        assert key.startswith('gdat_')
        assert row['estado'] == 'activa'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='codigo_ya_existe'):
            await svc.crear_identidad_tecnica(
                conn, tenant_id=uuid4(),
                codigo='DUP', nombre='X', descripcion=None,
                tipo='agente_ia', scopes=[], rate_limit_rpm=None,
                dependencia_alcance_id=None,
                created_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_crear_scopes_str_jsonb(self):
        conn = AsyncMock()
        row = _ident_row()
        row['scopes'] = '["x"]'
        conn.fetchrow.return_value = row
        d, _ = await svc.crear_identidad_tecnica(
            conn, tenant_id=uuid4(),
            codigo='X', nombre='X', descripcion=None,
            tipo='integrador', scopes=['x'], rate_limit_rpm=None,
            dependencia_alcance_id=None,
            created_by_user_id=uuid4(),
        )
        assert d['scopes'] == ['x']

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _ident_row()
        r = await svc.obtener_identidad(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_identidad(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_identidades(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_identidades(
            conn, tenant_id=uuid4(),
            tipo='robot_rpa', estado='activa', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_revocar_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _ident_row(estado='revocada')
        r = await svc.revocar_identidad(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
            motivo='comprometida', revocada_por_user_id=uuid4(),
        )
        assert r['estado'] == 'revocada'

    @pytest.mark.asyncio
    async def test_revocar_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.revocar_identidad(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
            motivo='X' * 11, revocada_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_revocar_ya_revocada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'revocada'
        with pytest.raises(ValueError, match='ya_revocada'):
            await svc.revocar_identidad(
                conn, tenant_id=uuid4(), identidad_id=uuid4(),
                motivo='X' * 11, revocada_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_rotar_key_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _ident_row()
        res = await svc.rotar_api_key(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
        )
        assert res is not None
        row, key = res
        assert key.startswith('gdat_')

    @pytest.mark.asyncio
    async def test_rotar_key_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.rotar_api_key(
            conn, tenant_id=uuid4(), identidad_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_rotar_key_revocada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'revocada'
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.rotar_api_key(
                conn, tenant_id=uuid4(), identidad_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_autenticar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo': 'X', 'tipo': 'robot_rpa',
            'scopes': '[]', 'estado': 'activa',
            'rate_limit_rpm': None,
            'dependencia_alcance_id': None,
        }
        r = await svc.autenticar_por_api_key(conn, api_key='gdat_test')
        assert r is not None
        assert r['scopes'] == []

    @pytest.mark.asyncio
    async def test_autenticar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.autenticar_por_api_key(conn, api_key='gdat_fake')
        assert r is None


# =============================================================================
# Tareas RPA
# =============================================================================
class TestTareasRPA:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _tarea_row()
        r = await svc.crear_tarea_rpa(
            conn, tenant_id=uuid4(),
            tipo='radicar_pdf', payload={'k': 'v'},
            prioridad='alta', identidad_tecnica_id=None,
            created_by_user_id=uuid4(),
        )
        assert r['estado'] == 'pending'

    @pytest.mark.asyncio
    async def test_crear_payload_jsonb_str(self):
        conn = AsyncMock()
        row = _tarea_row()
        row['payload'] = '{"x":1}'
        conn.fetchrow.return_value = row
        r = await svc.crear_tarea_rpa(
            conn, tenant_id=uuid4(),
            tipo='X', payload={'x': 1}, prioridad='normal',
            identidad_tecnica_id=None,
            created_by_user_id=uuid4(),
        )
        assert r['payload'] == {'x': 1}

    @pytest.mark.asyncio
    async def test_reclamar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _tarea_row(estado='in_progress')
        r = await svc.reclamar_tarea(
            conn, tenant_id=uuid4(), identidad_tecnica_id=uuid4(),
            tipo=None, ttl_segundos=300,
        )
        assert r['estado'] == 'in_progress'

    @pytest.mark.asyncio
    async def test_reclamar_con_tipo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _tarea_row(estado='in_progress')
        r = await svc.reclamar_tarea(
            conn, tenant_id=uuid4(), identidad_tecnica_id=uuid4(),
            tipo='radicar_pdf', ttl_segundos=600,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_reclamar_sin_tareas(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.reclamar_tarea(
            conn, tenant_id=uuid4(), identidad_tecnica_id=uuid4(),
            tipo=None, ttl_segundos=300,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reportar_done(self):
        conn = AsyncMock()
        token = uuid4()
        conn.fetchrow.side_effect = [
            {'claim_token': token,
             'claim_expira_en': datetime.now(timezone.utc) + timedelta(minutes=5),
             'estado': 'in_progress'},
            _tarea_row(estado='done',
                        resultado={'ok': True}),
        ]
        r = await svc.reportar_resultado(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            claim_token=token, estado='done',
            resultado={'ok': True},
            error_texto=None, error_codigo=None,
        )
        assert r['estado'] == 'done'

    @pytest.mark.asyncio
    async def test_reportar_failed(self):
        conn = AsyncMock()
        token = uuid4()
        conn.fetchrow.side_effect = [
            {'claim_token': token, 'claim_expira_en': datetime.now(timezone.utc),
             'estado': 'in_progress'},
            _tarea_row(estado='failed', error_texto='X'),
        ]
        r = await svc.reportar_resultado(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            claim_token=token, estado='failed',
            resultado=None, error_texto='download failed',
            error_codigo='HTTP_500',
        )
        assert r['estado'] == 'failed'

    @pytest.mark.asyncio
    async def test_reportar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.reportar_resultado(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            claim_token=uuid4(), estado='done',
            resultado=None, error_texto=None, error_codigo=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reportar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'claim_token': uuid4(),
            'claim_expira_en': datetime.now(),
            'estado': 'done',
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.reportar_resultado(
                conn, tenant_id=uuid4(), tarea_id=uuid4(),
                claim_token=uuid4(), estado='done',
                resultado=None, error_texto=None, error_codigo=None,
            )

    @pytest.mark.asyncio
    async def test_reportar_claim_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'claim_token': uuid4(),  # otro token
            'claim_expira_en': datetime.now(),
            'estado': 'in_progress',
        }
        with pytest.raises(ValueError, match='claim_token_invalido'):
            await svc.reportar_resultado(
                conn, tenant_id=uuid4(), tarea_id=uuid4(),
                claim_token=uuid4(),  # mismatch
                estado='done', resultado=None,
                error_texto=None, error_codigo=None,
            )

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_tareas_rpa(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_tareas_rpa(
            conn, tenant_id=uuid4(),
            estado='pending', tipo='X',
            identidad_tecnica_id=uuid4(), limit=10,
        )
        assert r == []


# =============================================================================
# Webhooks
# =============================================================================
class TestWebhooks:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _sub_row()
        row, secret = await svc.crear_webhook_sub(
            conn, tenant_id=uuid4(),
            identidad_tecnica_id=uuid4(),
            url='https://x.com/hook',
            eventos_suscritos=['PQRSDCreada'],
            descripcion=None,
            max_intentos=5,
            backoff_inicial_segundos=30,
            backoff_max_segundos=3600,
        )
        assert secret.startswith('whsec_')

    @pytest.mark.asyncio
    async def test_crear_identidad_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='identidad_no_existe'):
            await svc.crear_webhook_sub(
                conn, tenant_id=uuid4(),
                identidad_tecnica_id=uuid4(),
                url='https://x.com', eventos_suscritos=['*'],
                descripcion=None, max_intentos=3,
                backoff_inicial_segundos=10,
                backoff_max_segundos=600,
            )

    @pytest.mark.asyncio
    async def test_crear_identidad_revocada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'revocada'
        with pytest.raises(ValueError, match='identidad_estado'):
            await svc.crear_webhook_sub(
                conn, tenant_id=uuid4(),
                identidad_tecnica_id=uuid4(),
                url='https://x.com', eventos_suscritos=['*'],
                descripcion=None, max_intentos=3,
                backoff_inicial_segundos=10,
                backoff_max_segundos=600,
            )

    @pytest.mark.asyncio
    async def test_listar(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_webhook_subs(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_webhook_subs(
            conn, tenant_id=uuid4(),
            identidad_tecnica_id=uuid4(), estado='activa', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _sub_row()
        r = await svc.obtener_webhook_sub(
            conn, tenant_id=uuid4(), sub_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_webhook_sub(
            conn, tenant_id=uuid4(), sub_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _sub_row(estado='pausada')
        r = await svc.patch_webhook_sub(
            conn, tenant_id=uuid4(), sub_id=uuid4(),
            cambios={'estado': 'pausada', 'descripcion': 'x'},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_sin_cambios(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _sub_row()
        r = await svc.patch_webhook_sub(
            conn, tenant_id=uuid4(), sub_id=uuid4(), cambios={},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.patch_webhook_sub(
            conn, tenant_id=uuid4(), sub_id=uuid4(),
            cambios={'estado': 'pausada'},
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_encolar_delivery(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'suscripcion_id': uuid4(),
            'evento_id': uuid4(), 'tipo_evento': 'PQRSDCreada',
            'estado': 'pending', 'intentos': 0, 'http_status': None,
            'ultimo_intento_en': None, 'next_retry_at': datetime.now(),
            'delivered_at': None, 'error_texto': None,
            'created_at': datetime.now(),
        }
        r = await svc.encolar_delivery(
            conn, tenant_id=uuid4(), suscripcion_id=uuid4(),
            evento_id=uuid4(), tipo_evento='PQRSDCreada',
            payload={'x': 1},
        )
        assert r['estado'] == 'pending'

    @pytest.mark.asyncio
    async def test_listar_deliveries(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_deliveries(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_deliveries_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_deliveries(
            conn, tenant_id=uuid4(),
            suscripcion_id=uuid4(), estado='failed', limit=10,
        )
        assert r == []


# =============================================================================
# Rate limit
# =============================================================================
class TestRateLimit:
    @pytest.mark.asyncio
    async def test_sin_limite(self):
        conn = AsyncMock()
        r = await svc.rate_limit_decision(
            conn, tenant_id=uuid4(),
            identidad_tecnica_id=uuid4(), rate_limit_rpm=None,
        )
        assert r['permitido'] is True
        assert r['rate_limit_rpm'] is None

    @pytest.mark.asyncio
    async def test_dentro_del_limite(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'contador': 5}
        r = await svc.rate_limit_decision(
            conn, tenant_id=uuid4(),
            identidad_tecnica_id=uuid4(), rate_limit_rpm=100,
        )
        assert r['permitido'] is True
        assert r['contador_actual'] == 5
        assert r['retry_after_segundos'] is None

    @pytest.mark.asyncio
    async def test_excede_limite(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'contador': 101}
        r = await svc.rate_limit_decision(
            conn, tenant_id=uuid4(),
            identidad_tecnica_id=uuid4(), rate_limit_rpm=100,
        )
        assert r['permitido'] is False
        assert r['retry_after_segundos'] is not None
        assert r['retry_after_segundos'] >= 1
