"""Tests mocks para services del bloque 21b (EP-021 periféricos parte 2)."""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import perifericos2 as svc


# =============================================================================
# Lote
# =============================================================================
class TestLote:
    def _perif(self, **extra):
        base = {'id': uuid4(), 'estado': 'activo'}
        base.update(extra)
        return base

    def _lote(self, **extra):
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

    @pytest.mark.asyncio
    async def test_iniciar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [self._perif(), self._lote()]
        r = await svc.iniciar_lote_digitalizacion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            usuario_id=uuid4(), modo_separacion='por_pagina',
            radicado_id_default=None, calidad_dpi=300,
            observacion='lote test', timeout_min=30,
        )
        assert r['estado'] == 'abierto'

    @pytest.mark.asyncio
    async def test_iniciar_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.iniciar_lote_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                usuario_id=uuid4(), modo_separacion='por_pagina',
                radicado_id_default=None, calidad_dpi=300,
                observacion=None, timeout_min=30,
            )

    @pytest.mark.asyncio
    async def test_iniciar_perif_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._perif(estado='inactivo')
        with pytest.raises(ValueError):
            await svc.iniciar_lote_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                usuario_id=uuid4(), modo_separacion='por_pagina',
                radicado_id_default=None, calidad_dpi=300,
                observacion=None, timeout_min=30,
            )

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._lote()
        r = await svc.obtener_lote(
            conn, tenant_id=uuid4(), lote_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_none(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_lote(
            conn, tenant_id=uuid4(), lote_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_progreso_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._lote()
        conn.fetch.return_value = [
            {'id': uuid4(), 'radicado_id': uuid4(),
             'archivo_digital_id': None, 'numero_paginas': 5,
             'estado': 'correcta', 'mensaje_error': None,
             'fecha_digitalizacion': datetime.now()},
        ]
        r = await svc.progreso_lote(
            conn, tenant_id=uuid4(), lote_id=uuid4(),
        )
        assert len(r['digitalizaciones']) == 1

    @pytest.mark.asyncio
    async def test_progreso_lote_none(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.progreso_lote(
            conn, tenant_id=uuid4(), lote_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_finalizar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._lote(),
            self._lote(estado='finalizado',
                       finalizado_en=datetime.now()),
        ]
        r = await svc.finalizar_lote(
            conn, tenant_id=uuid4(), lote_id=uuid4(),
            observacion_final='completado correctamente',
        )
        assert r['estado'] == 'finalizado'

    @pytest.mark.asyncio
    async def test_finalizar_lote_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.finalizar_lote(
                conn, tenant_id=uuid4(), lote_id=uuid4(),
                observacion_final=None,
            )

    @pytest.mark.asyncio
    async def test_finalizar_lote_no_actualizable(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._lote(estado='finalizado')
        with pytest.raises(ValueError, match='lote_no_actualizable'):
            await svc.finalizar_lote(
                conn, tenant_id=uuid4(), lote_id=uuid4(),
                observacion_final=None,
            )


# =============================================================================
# Contexto activo
# =============================================================================
class TestContexto:
    @pytest.mark.asyncio
    async def test_upsert(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'user_id': uuid4(),
            'periferico_id': uuid4(), 'radicado_activo_id': uuid4(),
            'expira_en': datetime.now(), 'created_at': datetime.now(),
        }
        r = await svc.upsert_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(), radicado_activo_id=uuid4(),
            expira_en_segundos=300,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_eliminar_ok(self):
        conn = AsyncMock()
        conn.execute.return_value = 'DELETE 1'
        r = await svc.eliminar_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(),
        )
        assert r is True

    @pytest.mark.asyncio
    async def test_eliminar_nada(self):
        conn = AsyncMock()
        conn.execute.return_value = 'DELETE 0'
        r = await svc.eliminar_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(),
        )
        assert r is False

    @pytest.mark.asyncio
    async def test_eliminar_string_raro(self):
        conn = AsyncMock()
        conn.execute.return_value = 'algo'  # no parseable
        r = await svc.eliminar_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(),
        )
        assert r is False

    @pytest.mark.asyncio
    async def test_obtener_vigente(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'user_id': uuid4(),
            'periferico_id': uuid4(), 'radicado_activo_id': uuid4(),
            'expira_en': datetime.now() + timedelta(minutes=5),
            'created_at': datetime.now(),
        }
        r = await svc.obtener_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_expirado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_contexto_activo(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            periferico_id=uuid4(),
        )
        assert r is None


# =============================================================================
# Eventos + dashboard salud
# =============================================================================
class TestEventos:
    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_eventos_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_todos_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'id': uuid4(), 'periferico_id': uuid4(),
            'usuario_id': uuid4(), 'tipo_evento': 'conexion_perdida',
            'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
            'resultado': 'fallo', 'mensaje_error': 'timeout',
            'latencia_ms': 5000, 'fecha_hora': datetime.now(),
        }]
        r = await svc.listar_eventos_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
            resultado='fallo', limit=50,
        )
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_agregado_fallos(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'periferico_id': uuid4(),
            'periferico_nombre': 'Zebra',
            'total_fallos': 3, 'ultimo_fallo': datetime.now(),
        }]
        r = await svc.agregado_fallos(
            conn, tenant_id=uuid4(),
            desde=datetime.now() - timedelta(hours=1),
        )
        assert r[0]['total_fallos'] == 3


# =============================================================================
# Auto-protección
# =============================================================================
class TestAutoProteccion:
    @pytest.mark.asyncio
    async def test_no_aplica(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 3
        r = await svc.chequear_auto_proteccion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_se_dispara(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 6
        conn.fetchrow.return_value = {
            'id': uuid4(), 'periferico_id': uuid4(),
            'tipo': 'auto_proteccion',
            'descripcion': 'Auto-protección: 6 fallos en 1h.',
            'fecha_estimada_fin': None,
            'iniciado_por_user_id': uuid4(),
            'iniciado_en': datetime.now(),
            'finalizado_en': None,
            'observacion_final': None, 'costo': None, 'repuestos': None,
            'finalizado_por_user_id': None, 'estado': 'en_curso',
        }
        r = await svc.chequear_auto_proteccion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is not None
        assert r['tipo'] == 'auto_proteccion'


# =============================================================================
# Mantenimiento
# =============================================================================
class TestMantenimiento:
    def _mant(self, **extra):
        base = {
            'id': uuid4(), 'periferico_id': uuid4(),
            'tipo': 'preventivo',
            'descripcion': 'Calibración mensual',
            'fecha_estimada_fin': None,
            'iniciado_por_user_id': uuid4(),
            'iniciado_en': datetime.now(),
            'finalizado_en': None,
            'observacion_final': None, 'costo': None, 'repuestos': None,
            'finalizado_por_user_id': None, 'estado': 'en_curso',
        }
        base.update(extra)
        return base

    @pytest.mark.asyncio
    async def test_iniciar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'estado': 'activo'},
            self._mant(),
        ]
        r = await svc.iniciar_mantenimiento(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            tipo='preventivo', descripcion='Calibración mensual',
            fecha_estimada_fin=date.today(),
            iniciado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'en_curso'

    @pytest.mark.asyncio
    async def test_iniciar_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.iniciar_mantenimiento(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                tipo='preventivo', descripcion='X',
                fecha_estimada_fin=None,
                iniciado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_finalizar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'estado': 'en_curso'},
            self._mant(estado='finalizado',
                       finalizado_en=datetime.now(),
                       observacion_final='OK', costo=100.0,
                       repuestos=[{'parte': 'rodillo', 'qty': 1}]),
        ]
        r = await svc.finalizar_mantenimiento(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            mantenimiento_id=uuid4(),
            observacion_final='OK', costo=100.0,
            repuestos=[{'parte': 'rodillo', 'qty': 1}],
            finalizado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'finalizado'

    @pytest.mark.asyncio
    async def test_finalizar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.finalizar_mantenimiento(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                mantenimiento_id=uuid4(),
                observacion_final='X', costo=None,
                repuestos=None, finalizado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_finalizar_ya_finalizado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4(), 'estado': 'finalizado'}
        with pytest.raises(ValueError, match='no_actualizable'):
            await svc.finalizar_mantenimiento(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                mantenimiento_id=uuid4(),
                observacion_final='X', costo=None,
                repuestos=None, finalizado_por_user_id=uuid4(),
            )

    def test_norm_mant_repuestos_str(self):
        d = svc._norm_mant({'repuestos': '[{"x":1}]'})
        assert d['repuestos'] == [{'x': 1}]

    def test_norm_mant_none(self):
        assert svc._norm_mant(None) is None

    def test_norm_mant_repuestos_dict(self):
        d = svc._norm_mant({'repuestos': [{'a': 1}]})
        assert d['repuestos'] == [{'a': 1}]


# =============================================================================
# Agente local
# =============================================================================
class TestAgente:
    @pytest.mark.asyncio
    async def test_emparejar_ok(self):
        conn = AsyncMock()
        # 1) count periféricos, 2) insert agente
        conn.fetchval.return_value = 2
        conn.fetchrow.return_value = {
            'id': uuid4(), 'nombre_equipo': 'Counter-1',
            'version_agente': '0.1.0', 'periferico_ids': [uuid4(), uuid4()],
            'fingerprint_publico': b'\x01\x02',
            'estado': 'pendiente', 'motivo_revocacion': None,
            'ultimo_handshake_en': None,
            'registrado_por_user_id': uuid4(),
            'fecha_registro': datetime.now(),
            'token_emparejamiento_expira':
                datetime.now() + timedelta(minutes=10),
        }
        r = await svc.emparejar_agente_local(
            conn, tenant_id=uuid4(), nombre_equipo='Counter-1',
            version_agente='0.1.0',
            perifericos=[uuid4(), uuid4()],
            fingerprint_publico_b64=base64.b64encode(
                b'fake_pubkey').decode(),
            registrado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'pendiente'
        assert 'token_emparejamiento' in r
        assert len(r['token_emparejamiento']) >= 30

    @pytest.mark.asyncio
    async def test_emparejar_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # solo 1 de 2 existe
        with pytest.raises(LookupError):
            await svc.emparejar_agente_local(
                conn, tenant_id=uuid4(), nombre_equipo='X',
                version_agente=None,
                perifericos=[uuid4(), uuid4()],
                fingerprint_publico_b64=base64.b64encode(b'k').decode(),
                registrado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_emparejar_fingerprint_invalido(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        with pytest.raises(ValueError, match='fingerprint_invalido'):
            await svc.emparejar_agente_local(
                conn, tenant_id=uuid4(), nombre_equipo='X',
                version_agente=None,
                perifericos=[uuid4()],
                fingerprint_publico_b64='!!! no es base64 válido !!!',
                registrado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_revocar_ok(self):
        conn = AsyncMock()
        aid = uuid4()
        conn.fetchrow.side_effect = [
            {'id': aid, 'estado': 'activo'},
            {'id': aid, 'nombre_equipo': 'Counter-1',
             'version_agente': '0.1.0', 'periferico_ids': [uuid4()],
             'estado': 'revocado',
             'motivo_revocacion': 'equipo perdido',
             'ultimo_handshake_en': None,
             'registrado_por_user_id': uuid4(),
             'fecha_registro': datetime.now()},
        ]
        r = await svc.revocar_agente_local(
            conn, tenant_id=uuid4(), agente_id=aid,
            motivo='equipo perdido y comprometido',
        )
        assert r['estado'] == 'revocado'

    @pytest.mark.asyncio
    async def test_revocar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.revocar_agente_local(
                conn, tenant_id=uuid4(), agente_id=uuid4(),
                motivo='X' * 20,
            )

    @pytest.mark.asyncio
    async def test_revocar_ya_revocado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4(), 'estado': 'revocado'}
        with pytest.raises(ValueError, match='agente_ya_revocado'):
            await svc.revocar_agente_local(
                conn, tenant_id=uuid4(), agente_id=uuid4(),
                motivo='X' * 20,
            )

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'nombre_equipo': 'X',
            'version_agente': None, 'periferico_ids': [],
            'estado': 'activo', 'motivo_revocacion': None,
            'ultimo_handshake_en': None,
            'registrado_por_user_id': uuid4(),
            'fecha_registro': datetime.now(),
        }
        r = await svc.obtener_agente_local(
            conn, tenant_id=uuid4(), agente_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_none(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_agente_local(
            conn, tenant_id=uuid4(), agente_id=uuid4(),
        )
        assert r is None

    def test_generar_token_y_hash(self):
        t = svc._generar_token_emparejamiento()
        h = svc._hash_token(t)
        # SHA-256 hex = 64 chars
        assert len(h) == 64
        assert h != t
        # Mismo token → mismo hash
        assert svc._hash_token(t) == h


# =============================================================================
# Historial
# =============================================================================
class TestHistorial:
    @pytest.mark.asyncio
    async def test_periferico_todos_tipos(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.historial_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_periferico_solo_impresion(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'id': uuid4(), 'tipo_operacion': 'impresion',
            'subtipo': 'etiqueta_qr', 'estado': 'generada',
            'fecha': datetime.now(), 'usuario_id': uuid4(),
            'radicado_id': uuid4(), 'mensaje_error': None,
        }]
        r = await svc.historial_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            tipo_operacion='impresion',
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
        )
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_periferico_digit_con_rango(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        await svc.historial_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            tipo_operacion='digitalizacion',
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
        )

    @pytest.mark.asyncio
    async def test_periferico_eventos_con_rango(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        await svc.historial_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            tipo_operacion='evento_periferico',
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
        )

    @pytest.mark.asyncio
    async def test_periferico_filtro_invalido(self):
        conn = AsyncMock()
        # tipo_operacion='xxx' no matchea ninguna parte → no fetch.
        r = await svc.historial_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            tipo_operacion='xxx',
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_global_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.historial_uso_global(
            conn, tenant_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_global_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.historial_uso_global(
            conn, tenant_id=uuid4(),
            usuario_id=uuid4(), periferico_id=uuid4(),
            desde=datetime(2026, 1, 1), limit=100,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_export(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 42
        r = await svc.export_historial(
            conn, tenant_id=uuid4(), formato='csv',
            desde=datetime(2026, 1, 1), hasta=None,
            periferico_id=uuid4(), usuario_id=uuid4(),
            solicitado_por_user_id=uuid4(),
        )
        assert r['total_filas'] == 42
        assert r['formato'] == 'csv'
        assert r['archivo_digital_id'] is None  # worker async lo llenará

    @pytest.mark.asyncio
    async def test_export_sin_filtros(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        r = await svc.export_historial(
            conn, tenant_id=uuid4(), formato='excel',
            desde=None, hasta=None,
            periferico_id=None, usuario_id=None,
            solicitado_por_user_id=uuid4(),
        )
        assert r['total_filas'] == 0


# =============================================================================
# Reemplazo digitalización
# =============================================================================
class TestReemplazoDigit:
    @pytest.mark.asyncio
    async def test_ok(self):
        conn = AsyncMock()
        did = uuid4()
        nuevo_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': did, 'radicado_id': uuid4(),
             'periferico_id': uuid4(),
             'tipo_digitalizacion': 'individual',
             'calidad_dpi': 200, 'estado': 'correcta'},
            {'id': nuevo_id, 'fecha_digitalizacion': datetime.now()},
        ]
        r = await svc.reemplazar_digitalizacion(
            conn, tenant_id=uuid4(), digitalizacion_id=did,
            motivo='Calidad baja: 100 DPI insuficiente',
            archivo_digital_id_nuevo=uuid4(), usuario_id=uuid4(),
        )
        assert r['digitalizacion_nueva_id'] == nuevo_id
        assert r['digitalizacion_original_id'] == did

    @pytest.mark.asyncio
    async def test_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.reemplazar_digitalizacion(
                conn, tenant_id=uuid4(), digitalizacion_id=uuid4(),
                motivo='X' * 20, archivo_digital_id_nuevo=uuid4(),
                usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_ya_reemplazada(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_id': uuid4(),
            'periferico_id': uuid4(),
            'tipo_digitalizacion': 'individual',
            'calidad_dpi': 200, 'estado': 'reemplazada',
        }
        with pytest.raises(ValueError, match='ya_reemplazada'):
            await svc.reemplazar_digitalizacion(
                conn, tenant_id=uuid4(), digitalizacion_id=uuid4(),
                motivo='X' * 20, archivo_digital_id_nuevo=uuid4(),
                usuario_id=uuid4(),
            )
