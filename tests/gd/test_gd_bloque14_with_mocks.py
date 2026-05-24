"""Tests mocks para services del bloque 14 (IA EP-013)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import ia as svc


def _sol_row(tipo='clasificacion', estado='pending', **extra):
    base = {
        'id': uuid4(), 'tipo_asistencia': tipo,
        'entidad_origen_tipo': 'radicado',
        'entidad_origen_id': uuid4(),
        'estado': estado, 'payload_original': {},
        'datos_redactados': {}, 'redacciones_aplicadas': [],
        'proveedor': 'StubIAProvider',
        'error_texto': None, 'error_codigo': None,
        'solicitante_user_id': uuid4(),
        'inicio_procesamiento_en': None, 'fin_procesamiento_en': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _res_row(**extra):
    base = {
        'id': uuid4(), 'solicitud_id': uuid4(),
        'contenido': {'k': 'v'}, 'confianza': 0.8,
        'explicacion': 'stub', 'modelo': 'stub-v1',
        'tokens_input': 10, 'tokens_output': 5, 'timing_ms': 3,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Redactor PII (GD-API-0086)
# =============================================================================
class TestRedactor:
    def test_sin_texto(self):
        out, red = svc.redactar_datos_sensibles(None)
        assert out is None and red == []

    def test_texto_vacio(self):
        out, red = svc.redactar_datos_sensibles('')
        assert out == '' and red == []

    def test_redacta_cedula_con_keyword(self):
        out, red = svc.redactar_datos_sensibles(
            'Mi cédula es 79.123.456 por favor.'
        )
        assert '[CEDULA_REDACTADA]' in out
        assert any(r['tipo'] == 'cedula' for r in red)

    def test_redacta_cedula_cc(self):
        out, red = svc.redactar_datos_sensibles('CC 1023456789')
        assert '[CEDULA_REDACTADA]' in out
        assert any(r['tipo'] == 'cedula' for r in red)

    def test_redacta_email(self):
        out, red = svc.redactar_datos_sensibles('Contacto: juan@example.com')
        assert '[EMAIL_REDACTADO]' in out
        assert any(r['tipo'] == 'email' for r in red)

    def test_redacta_telefono(self):
        out, red = svc.redactar_datos_sensibles('Llámame al 300 555 1234')
        assert '[TELEFONO_REDACTADO]' in out
        assert any(r['tipo'] == 'telefono' for r in red)

    def test_redacta_telefono_con_prefijo(self):
        out, red = svc.redactar_datos_sensibles('Cel: +57 312-987-6543')
        assert '[TELEFONO_REDACTADO]' in out

    def test_redacta_multiples(self):
        out, red = svc.redactar_datos_sensibles(
            'Cédula: 1023456789, email: a@b.com, tel: 3105551234'
        )
        # Debe redactar todos
        tipos = {r['tipo'] for r in red}
        assert 'cedula' in tipos
        assert 'email' in tipos

    def test_sin_pii(self):
        out, red = svc.redactar_datos_sensibles(
            'Texto sin información sensible.'
        )
        assert out == 'Texto sin información sensible.'
        assert red == []

    def test_redactar_payload_dict_nested(self):
        payload = {
            'asunto': 'Sobre mi cédula 79.123.456',
            'datos': {
                'email': 'a@x.com',
                'nested': {'tel': 'Cel: 300-555-1234'},
            },
            'lista': ['email: x@y.com', 'sin pii'],
        }
        red, info = svc.redactar_payload(payload)
        # No mutó el original
        assert '79.123.456' in payload['asunto']
        # Redactó
        assert '[CEDULA_REDACTADA]' in red['asunto']
        assert '[EMAIL_REDACTADO]' in red['datos']['email']
        # Consolidación
        tipos = {r['tipo'] for r in info}
        assert 'cedula' in tipos
        assert 'email' in tipos

    def test_redactar_payload_no_string(self):
        red, info = svc.redactar_payload({'numero': 42, 'flag': True,
                                            'nulo': None})
        assert red == {'numero': 42, 'flag': True, 'nulo': None}
        assert info == []


# =============================================================================
# Provider stub
# =============================================================================
class TestProvider:
    @pytest.mark.asyncio
    async def test_clasificar_pqrsd(self):
        p = svc.StubIAProvider()
        r = await p.clasificar(payload={'texto': 'Tengo una queja sobre el servicio'})
        assert r['contenido']['tipo_clasificacion_sugerido'] == 'pqrsd'

    @pytest.mark.asyncio
    async def test_clasificar_correspondencia(self):
        p = svc.StubIAProvider()
        r = await p.clasificar(payload={'texto': 'Oficio número 123'})
        assert r['contenido']['tipo_clasificacion_sugerido'] == 'correspondencia_externa'

    @pytest.mark.asyncio
    async def test_clasificar_tramite_generico(self):
        p = svc.StubIAProvider()
        r = await p.clasificar(payload={'texto': 'Solicitud sin keyword'})
        assert r['contenido']['tipo_clasificacion_sugerido'] == 'tramite'

    @pytest.mark.asyncio
    async def test_clasificar_asunto_fallback(self):
        p = svc.StubIAProvider()
        r = await p.clasificar(payload={'asunto': 'Queja formal'})
        assert r['contenido']['tipo_clasificacion_sugerido'] == 'pqrsd'

    @pytest.mark.asyncio
    async def test_extraer_datos(self):
        p = svc.StubIAProvider()
        r = await p.extraer_datos(payload={'texto': 'email: a@b.com'})
        assert 'a@b.com' in r['contenido']['emails_detectados']

    @pytest.mark.asyncio
    async def test_resumir(self):
        p = svc.StubIAProvider()
        r = await p.resumir(payload={'texto': 'Hola ' * 100},
                              max_caracteres=20)
        assert len(r['contenido']['resumen']) <= 25  # 20 + '...'

    @pytest.mark.asyncio
    async def test_resumir_corto_no_trunca(self):
        p = svc.StubIAProvider()
        r = await p.resumir(payload={'texto': 'Corto'}, max_caracteres=500)
        assert r['contenido']['resumen'] == 'Corto'

    @pytest.mark.asyncio
    async def test_sugerir_dependencia_con_hint(self):
        p = svc.StubIAProvider()
        dep_id = str(uuid4())
        r = await p.sugerir_dependencia(payload={'dependencia_hint': dep_id})
        assert r['contenido']['dependencia_sugerida_id'] == dep_id

    @pytest.mark.asyncio
    async def test_sugerir_dependencia_sin_hint(self):
        p = svc.StubIAProvider()
        r = await p.sugerir_dependencia(payload={})
        assert r['confianza'] == 0.3

    @pytest.mark.asyncio
    async def test_detectar_duplicados(self):
        p = svc.StubIAProvider()
        r = await p.detectar_duplicados(
            payload={'candidatos_recientes': [
                {'id': 'a'}, {'id': 'b'},
            ]}, top_k=2,
        )
        assert len(r['contenido']['duplicados']) == 2

    @pytest.mark.asyncio
    async def test_borrador_respuesta(self):
        p = svc.StubIAProvider()
        r = await p.borrador_respuesta(payload={'asunto': 'mi consulta'})
        assert 'mi consulta' in r['contenido']['borrador_texto']

    @pytest.mark.asyncio
    async def test_sugerir_termino_consulta(self):
        p = svc.StubIAProvider()
        r = await p.sugerir_termino(payload={'tipo_pqrsd_codigo': 'CONSULTA'})
        assert r['contenido']['dias_sugeridos'] == 30

    @pytest.mark.asyncio
    async def test_sugerir_termino_reclamo(self):
        p = svc.StubIAProvider()
        r = await p.sugerir_termino(payload={'tipo_pqrsd_codigo': 'RECLAMO'})
        assert r['contenido']['dias_sugeridos'] == 15

    def test_get_default(self):
        assert isinstance(svc.get_default_provider(), svc.StubIAProvider)


# =============================================================================
# Workflow: encolar + ejecutar + obtener
# =============================================================================
class TestWorkflow:
    @pytest.mark.asyncio
    async def test_encolar_aplica_redactor(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _sol_row()
        sol = await svc.encolar_solicitud(
            conn, tenant_id=uuid4(),
            tipo_asistencia='clasificacion',
            entidad_origen_tipo='radicado',
            entidad_origen_id=uuid4(),
            payload_original={'texto': 'Mi cédula 1023456789'},
            solicitante_user_id=uuid4(),
        )
        assert sol['estado'] == 'pending'

    @pytest.mark.asyncio
    async def test_encolar_jsonb_str(self):
        conn = AsyncMock()
        row = _sol_row()
        row['payload_original'] = '{}'
        row['datos_redactados'] = '{}'
        row['redacciones_aplicadas'] = '[]'
        conn.fetchrow.return_value = row
        sol = await svc.encolar_solicitud(
            conn, tenant_id=uuid4(), tipo_asistencia='resumen',
            entidad_origen_tipo='pqrsd', entidad_origen_id=uuid4(),
            payload_original={'x': 1}, solicitante_user_id=uuid4(),
        )
        assert sol['payload_original'] == {}

    @pytest.mark.asyncio
    async def test_ejecutar_solicitud_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'tipo_asistencia': 'clasificacion', 'estado': 'pending',
             'datos_redactados': {'texto': 'Tengo una queja'}},
            _res_row(),
        ]
        r = await svc.ejecutar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            extra_kwargs=None, provider=None,
        )
        assert r['resultado'] is not None

    @pytest.mark.asyncio
    async def test_ejecutar_solicitud_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.ejecutar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            extra_kwargs=None, provider=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_ejecutar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tipo_asistencia': 'clasificacion', 'estado': 'completed',
            'datos_redactados': {},
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.ejecutar_solicitud(
                conn, tenant_id=uuid4(), solicitud_id=uuid4(),
                extra_kwargs=None, provider=None,
            )

    @pytest.mark.asyncio
    async def test_ejecutar_datos_redactados_str(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'tipo_asistencia': 'resumen', 'estado': 'pending',
             'datos_redactados': '{"texto": "hola"}'},
            _res_row(),
        ]
        r = await svc.ejecutar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            extra_kwargs={'max_caracteres': 100}, provider=None,
        )
        assert r['resultado'] is not None

    @pytest.mark.asyncio
    async def test_ejecutar_provider_falla(self):
        class FailingProvider(svc.StubIAProvider):
            async def clasificar(self, **kwargs):
                raise RuntimeError('provider down')

        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tipo_asistencia': 'clasificacion', 'estado': 'pending',
            'datos_redactados': {},
        }
        r = await svc.ejecutar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            extra_kwargs=None, provider=FailingProvider(),
        )
        assert r['resultado'] is None
        assert 'provider down' in r['error']

    @pytest.mark.asyncio
    async def test_obtener_solicitud_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _sol_row()
        r = await svc.obtener_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_solicitud_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_solicitud_jsonb_str(self):
        conn = AsyncMock()
        row = _sol_row()
        row['payload_original'] = '{"x":1}'
        conn.fetchrow.return_value = row
        r = await svc.obtener_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
        )
        assert r['payload_original'] == {'x': 1}

    @pytest.mark.asyncio
    async def test_obtener_resultado_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _res_row()
        r = await svc.obtener_resultado(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_resultado_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_resultado(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_resultado_jsonb_str(self):
        conn = AsyncMock()
        row = _res_row()
        row['contenido'] = '{"k": "v"}'
        conn.fetchrow.return_value = row
        r = await svc.obtener_resultado(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
        )
        assert r['contenido'] == {'k': 'v'}


# =============================================================================
# Decisión humana
# =============================================================================
class TestDecision:
    @pytest.mark.asyncio
    async def test_decidir_aceptar(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # resultado existe
        conn.fetchrow.return_value = {
            'id': uuid4(), 'resultado_id': uuid4(),
            'decision': 'aceptar', 'contenido_modificado': None,
            'observaciones': None, 'decided_by_user_id': uuid4(),
            'decided_at': datetime.now(),
            'materializado_endpoint': None, 'materializado_entidad_id': None,
        }
        r = await svc.decidir_sugerencia(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
            decision='aceptar', contenido_modificado=None,
            observaciones=None, decided_by_user_id=uuid4(),
        )
        assert r['decision'] == 'aceptar'

    @pytest.mark.asyncio
    async def test_decidir_modificar_con_contenido(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'resultado_id': uuid4(),
            'decision': 'modificar',
            'contenido_modificado': {'k': 'nuevo'},
            'observaciones': 'cambié la sugerencia',
            'decided_by_user_id': uuid4(), 'decided_at': datetime.now(),
            'materializado_endpoint': None, 'materializado_entidad_id': None,
        }
        r = await svc.decidir_sugerencia(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
            decision='modificar', contenido_modificado={'k': 'nuevo'},
            observaciones='cambié', decided_by_user_id=uuid4(),
        )
        assert r['contenido_modificado'] == {'k': 'nuevo'}

    @pytest.mark.asyncio
    async def test_decidir_resultado_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.decidir_sugerencia(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
            decision='rechazar', contenido_modificado=None,
            observaciones=None, decided_by_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_decidir_duplicada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='decision_ya_registrada'):
            await svc.decidir_sugerencia(
                conn, tenant_id=uuid4(), resultado_id=uuid4(),
                decision='aceptar', contenido_modificado=None,
                observaciones=None, decided_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_decidir_contenido_modificado_str_parse(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'resultado_id': uuid4(),
            'decision': 'modificar',
            'contenido_modificado': '{"x": 1}',  # PG retornó str
            'observaciones': None,
            'decided_by_user_id': uuid4(), 'decided_at': datetime.now(),
            'materializado_endpoint': None, 'materializado_entidad_id': None,
        }
        r = await svc.decidir_sugerencia(
            conn, tenant_id=uuid4(), resultado_id=uuid4(),
            decision='modificar', contenido_modificado={'x': 1},
            observaciones=None, decided_by_user_id=uuid4(),
        )
        assert r['contenido_modificado'] == {'x': 1}


# =============================================================================
# Trazabilidad
# =============================================================================
class TestTrazabilidad:
    @pytest.mark.asyncio
    async def test_vacio(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.obtener_trazabilidad(
            conn, tenant_id=uuid4(),
            entidad_origen_tipo='radicado', entidad_origen_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_solicitudes_sin_resultado(self):
        conn = AsyncMock()
        sol = _sol_row()
        conn.fetch.return_value = [sol]
        # fetchrow para resultado retorna None
        conn.fetchrow.return_value = None
        r = await svc.obtener_trazabilidad(
            conn, tenant_id=uuid4(),
            entidad_origen_tipo='radicado', entidad_origen_id=uuid4(),
        )
        assert len(r) == 1
        assert r[0]['resultado'] is None
        assert r[0]['decision'] is None

    @pytest.mark.asyncio
    async def test_solicitudes_con_resultado_sin_decision(self):
        conn = AsyncMock()
        sol = _sol_row()
        conn.fetch.return_value = [sol]
        # fetchrow se llama 2 veces: resultado, decisión.
        # Primera devuelve resultado, segunda devuelve None.
        conn.fetchrow.side_effect = [_res_row(), None]
        r = await svc.obtener_trazabilidad(
            conn, tenant_id=uuid4(),
            entidad_origen_tipo='pqrsd', entidad_origen_id=uuid4(),
        )
        assert r[0]['resultado'] is not None
        assert r[0]['decision'] is None

    @pytest.mark.asyncio
    async def test_solicitudes_completas(self):
        conn = AsyncMock()
        sol = _sol_row()
        conn.fetch.return_value = [sol]
        res = _res_row()
        dec = {
            'id': uuid4(), 'resultado_id': res['id'],
            'decision': 'aceptar', 'contenido_modificado': None,
            'observaciones': None, 'decided_by_user_id': uuid4(),
            'decided_at': datetime.now(),
            'materializado_endpoint': None, 'materializado_entidad_id': None,
        }
        conn.fetchrow.side_effect = [res, dec]
        r = await svc.obtener_trazabilidad(
            conn, tenant_id=uuid4(),
            entidad_origen_tipo='pqrsd', entidad_origen_id=uuid4(),
        )
        assert r[0]['decision']['decision'] == 'aceptar'
