"""Tests con mocks para services del bloque 8 (PQRSD cierre EP-007).

Cubre: workflow respuesta (enviar_a_revision, revisar, aprobar, firmar,
radicar_salida, enviar), cerrar, reabrir, trasladar_competencia,
solicitar_info_adicional, dashboard.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import pqrsd as svc


# Helper: respuesta_pqrsd fila base.
def _resp_row(estado: str, usuario_proyecta_id):
    return {
        'id': uuid4(), 'pqrsd_id': uuid4(),
        'documento_id': None, 'plantilla_id': None,
        'contenido_borrador': 'x', 'usuario_proyecta_id': usuario_proyecta_id,
        'usuario_revisa_id': None, 'usuario_aprueba_id': None,
        'usuario_firma_id': None, 'radicado_salida_id': None,
        'estado': estado,
        'fecha_proyeccion': datetime.now(), 'fecha_revision': None,
        'fecha_aprobacion': None, 'fecha_firma': None,
        'fecha_radicacion': None, 'fecha_envio': None,
        'observaciones_devolucion': None,
    }


# =============================================================================
# Workflow respuesta (GD-API-0047)
# =============================================================================
class TestWorkflowRespuesta:
    @pytest.mark.asyncio
    async def test_enviar_a_revision_ok(self) -> None:
        conn = AsyncMock()
        actor = uuid4()
        # _obtener_respuesta → fila estado borrador
        conn.fetchrow.side_effect = [
            _resp_row('borrador', actor),
            {**_resp_row('en_revision', actor)},
        ]
        r = await svc.enviar_respuesta_a_revision(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=actor, observaciones='ok',
        )
        assert r['estado'] == 'en_revision'

    @pytest.mark.asyncio
    async def test_enviar_a_revision_estado_invalido(self) -> None:
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = _resp_row('aprobada', actor)
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.enviar_respuesta_a_revision(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_enviar_a_revision_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.enviar_respuesta_a_revision(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_revisar_ok_aprueba(self) -> None:
        conn = AsyncMock()
        proyecta = uuid4()
        revisor = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row('en_revision', proyecta),
            {**_resp_row('aprobada', proyecta), 'usuario_revisa_id': revisor},
        ]
        r = await svc.revisar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            resultado='ok', observaciones=None, usuario_actor_id=revisor,
        )
        assert r['estado'] == 'aprobada'

    @pytest.mark.asyncio
    async def test_revisar_devuelve(self) -> None:
        conn = AsyncMock()
        proyecta = uuid4()
        revisor = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row('en_revision', proyecta),
            {**_resp_row('devuelta', proyecta), 'usuario_revisa_id': revisor,
             'observaciones_devolucion': 'corrige'},
        ]
        r = await svc.revisar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            resultado='devolver', observaciones='corrige', usuario_actor_id=revisor,
        )
        assert r['estado'] == 'devuelta'

    @pytest.mark.asyncio
    async def test_revisar_separacion_funciones(self) -> None:
        conn = AsyncMock()
        actor = uuid4()  # mismo que proyectista
        conn.fetchrow.return_value = _resp_row('en_revision', actor)
        with pytest.raises(PermissionError, match='separacion_funciones'):
            await svc.revisar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                resultado='ok', observaciones=None, usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_revisar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = _resp_row('borrador', uuid4())
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.revisar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                resultado='ok', observaciones=None, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_revisar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.revisar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            resultado='ok', observaciones=None, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_aprobar_ok(self) -> None:
        conn = AsyncMock()
        proyecta = uuid4()
        aprobador = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row('aprobada', proyecta),
            {**_resp_row('aprobada', proyecta), 'usuario_aprueba_id': aprobador,
             'fecha_aprobacion': datetime.now()},
        ]
        r = await svc.aprobar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=aprobador,
        )
        assert r['usuario_aprueba_id'] == aprobador

    @pytest.mark.asyncio
    async def test_aprobar_separacion(self) -> None:
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = _resp_row('aprobada', actor)
        with pytest.raises(PermissionError):
            await svc.aprobar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_aprobar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = _resp_row('borrador', uuid4())
        with pytest.raises(ValueError):
            await svc.aprobar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_aprobar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.aprobar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_firmar_ok(self) -> None:
        conn = AsyncMock()
        proyecta = uuid4()
        firmante = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row('aprobada', proyecta),
            {**_resp_row('firmada', proyecta), 'usuario_firma_id': firmante,
             'fecha_firma': datetime.now()},
        ]
        r = await svc.firmar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=firmante, firma_id=uuid4(),
        )
        assert r['estado'] == 'firmada'

    @pytest.mark.asyncio
    async def test_firmar_separacion(self) -> None:
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = _resp_row('aprobada', actor)
        with pytest.raises(PermissionError):
            await svc.firmar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_firmar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = _resp_row('borrador', uuid4())
        with pytest.raises(ValueError):
            await svc.firmar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_firmar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.firmar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_radicar_salida_ok(self, monkeypatch) -> None:
        conn = AsyncMock()
        async def fake_sig(conn, *, tenant_id, vigencia, tipo_radicado):
            return '2026-S-00001'
        monkeypatch.setattr(
            'app.gd.services.consecutivos.siguiente_radicado', fake_sig,
        )
        proyecta = uuid4()
        radicado_id = uuid4()
        pqrsd_id = uuid4()
        # _obtener_respuesta → fila firmada
        # pqrsd_row (asunto, descripcion, dependencia, tercero, radicado_entrada_id)
        # radicado_row (id, numero_radicado, fecha_radicacion)
        # update returning fila final
        resp_firmada = {**_resp_row('firmada', proyecta), 'pqrsd_id': pqrsd_id}
        conn.fetchrow.side_effect = [
            resp_firmada,
            {'asunto': 'X', 'descripcion': 'Y',
             'dependencia_responsable_id': uuid4(), 'tercero_id': None,
             'radicado_entrada_id': uuid4()},
            {'id': radicado_id, 'numero_radicado': '2026-S-00001',
             'fecha_radicacion': datetime.now()},
            {**resp_firmada, 'estado': 'radicada',
             'radicado_salida_id': radicado_id,
             'fecha_radicacion': datetime.now()},
        ]
        r = await svc.radicar_salida_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(), canal_envio_id=uuid4(),
        )
        assert r['estado'] == 'radicada'
        assert r['radicado_salida_id'] == radicado_id

    @pytest.mark.asyncio
    async def test_radicar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = _resp_row('borrador', uuid4())
        with pytest.raises(ValueError):
            await svc.radicar_salida_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_radicar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.radicar_salida_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_radicar_pqrsd_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _resp_row('firmada', uuid4()),
            None,  # pqrsd_row none
        ]
        r = await svc.radicar_salida_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_enviar_respuesta_ok(self) -> None:
        conn = AsyncMock()
        proyecta = uuid4()
        conn.fetchrow.side_effect = [
            _resp_row('radicada', proyecta),
            {**_resp_row('enviada', proyecta),
             'fecha_envio': datetime.now()},
        ]
        r = await svc.enviar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(), canal_envio_id=uuid4(),
            constancia_envio_uri='s3://bucket/x.pdf',
        )
        assert r['estado'] == 'enviada'

    @pytest.mark.asyncio
    async def test_enviar_respuesta_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = _resp_row('borrador', uuid4())
        with pytest.raises(ValueError):
            await svc.enviar_respuesta(
                conn, tenant_id=uuid4(), respuesta_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_enviar_respuesta_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.enviar_respuesta(
            conn, tenant_id=uuid4(), respuesta_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None


# =============================================================================
# Cerrar / Reabrir (GD-API-0048)
# =============================================================================
def _pqrsd_row(estado='asignada'):
    return {
        'id': uuid4(), 'radicado_entrada_id': uuid4(),
        'tipo_pqrsd_id': uuid4(), 'tercero_id': None,
        'asunto': 'A', 'descripcion': 'D',
        'dependencia_responsable_id': None, 'usuario_responsable_id': None,
        'fecha_recepcion': datetime.now(), 'fecha_limite_respuesta': datetime.now(),
        'estado': estado, 'prioridad': 'normal', 'reserva': False,
    }


class TestCerrarReabrir:
    @pytest.mark.asyncio
    async def test_cerrar_ok_con_respuesta(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'enviada'},  # SELECT estado
            _pqrsd_row(estado='cerrada'),  # UPDATE returning
        ]
        conn.fetchval.return_value = 1  # respuesta enviada existe
        r = await svc.cerrar_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='Respondida y enviada', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'cerrada'

    @pytest.mark.asyncio
    async def test_cerrar_sin_respuesta_forzado(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'asignada'},
            _pqrsd_row(estado='cerrada'),
        ]
        r = await svc.cerrar_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='Solicitante retiró', usuario_actor_id=uuid4(),
            forzar_sin_respuesta=True,
        )
        assert r['estado'] == 'cerrada'

    @pytest.mark.asyncio
    async def test_cerrar_sin_respuesta_falla(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'asignada'}
        conn.fetchval.return_value = None
        with pytest.raises(ValueError, match='sin_respuesta_enviada'):
            await svc.cerrar_pqrsd(
                conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
                motivo='Quiero cerrar', usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_cerrar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'cerrada'}
        with pytest.raises(ValueError):
            await svc.cerrar_pqrsd(
                conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
                motivo='X', usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_cerrar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.cerrar_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='X', usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_reabrir_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'cerrada'},
            _pqrsd_row(estado='asignada'),
        ]
        r = await svc.reabrir_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='solicitante apeló', dias_adicionales=10,
            usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'asignada'

    @pytest.mark.asyncio
    async def test_reabrir_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'asignada'}
        with pytest.raises(ValueError):
            await svc.reabrir_pqrsd(
                conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
                motivo='x' * 11, dias_adicionales=5,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reabrir_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.reabrir_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='x' * 11, dias_adicionales=5,
            usuario_actor_id=uuid4(),
        ) is None


# =============================================================================
# Traslado por competencia (GD-API-0049)
# =============================================================================
class TestTraslado:
    @pytest.mark.asyncio
    async def test_trasladar_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'asignada', 'fecha_limite_respuesta': datetime.now()},
            _pqrsd_row(estado='trasladada'),
        ]
        r = await svc.trasladar_competencia(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            entidad_competente_destino='Alcaldía Municipal',
            motivo='No es de competencia', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'trasladada'

    @pytest.mark.asyncio
    async def test_trasladar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'cerrada',
                                       'fecha_limite_respuesta': None}
        with pytest.raises(ValueError):
            await svc.trasladar_competencia(
                conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
                entidad_competente_destino='X', motivo='y' * 11,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_trasladar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.trasladar_competencia(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            entidad_competente_destino='X', motivo='y' * 11,
            usuario_actor_id=uuid4(),
        ) is None


# =============================================================================
# Solicitar info adicional (GD-API-0050)
# =============================================================================
class TestSolicitarInfo:
    @pytest.mark.asyncio
    async def test_solicitar_ok(self) -> None:
        conn = AsyncMock()
        ev_id = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'asignada', 'fecha_limite_respuesta': datetime.now()},
            {'id': ev_id, 'pqrsd_id': uuid4(),
             'tipo_evento': 'solicitud_info_adicional',
             'fecha_evento': datetime.now(),
             'motivo': 'falta info', 'justificacion_legal': 'documentos',
             'dias_afectados': 10, 'fecha_limite_anterior': datetime.now(),
             'fecha_limite_nueva': None, 'usuario_id': uuid4()},
        ]
        r = await svc.solicitar_info_adicional(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='falta info', informacion_solicitada='Cédula',
            dias_estimados_suspension=10, usuario_actor_id=uuid4(),
        )
        assert r['tipo_evento'] == 'solicitud_info_adicional'

    @pytest.mark.asyncio
    async def test_solicitar_estado_invalido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'cerrada',
                                       'fecha_limite_respuesta': None}
        with pytest.raises(ValueError):
            await svc.solicitar_info_adicional(
                conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
                motivo='m' * 11, informacion_solicitada='Cédula completa',
                dias_estimados_suspension=10, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_solicitar_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.solicitar_info_adicional(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='m' * 11, informacion_solicitada='C' * 11,
            dias_estimados_suspension=10, usuario_actor_id=uuid4(),
        ) is None


# =============================================================================
# Dashboard (GD-API-0051)
# =============================================================================
class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 10, 'total_vencidas': 2,
            'total_proximas_vencer': 1, 'total_cerradas': 5,
        }
        conn.fetch.return_value = [
            {'dependencia_id': uuid4(), 'estado': 'asignada',
             'tipo_pqrsd_id': uuid4(), 'total': 3, 'vencidas': 1,
             'proximas_vencer': 0, 'dias_promedio_resolucion': 2.5},
            {'dependencia_id': None, 'estado': 'cerrada',
             'tipo_pqrsd_id': None, 'total': 5, 'vencidas': 0,
             'proximas_vencer': 0, 'dias_promedio_resolucion': None},
        ]
        r = await svc.dashboard_pqrsd(conn, tenant_id=uuid4())
        assert r['total_global'] == 10
        assert r['total_vencidas'] == 2
        assert len(r['buckets']) == 2
        assert r['buckets'][0]['dias_promedio_resolucion'] == 2.5
        assert r['buckets'][1]['dias_promedio_resolucion'] is None

    @pytest.mark.asyncio
    async def test_dashboard_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 1, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 1,
        }
        conn.fetch.return_value = []
        r = await svc.dashboard_pqrsd(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 5, 23),
        )
        assert r['total_global'] == 1
        assert r['buckets'] == []

    @pytest.mark.asyncio
    async def test_dashboard_solo_desde(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 0, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = []
        r = await svc.dashboard_pqrsd(
            conn, tenant_id=uuid4(), desde=datetime(2026, 1, 1),
        )
        assert r['total_global'] == 0

    @pytest.mark.asyncio
    async def test_dashboard_solo_hasta(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 0, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = []
        r = await svc.dashboard_pqrsd(
            conn, tenant_id=uuid4(), hasta=datetime(2026, 12, 31),
        )
        assert r['total_global'] == 0

    @pytest.mark.asyncio
    async def test_dashboard_totales_null_safe(self) -> None:
        conn = AsyncMock()
        # caso edge: fetchrow retorna None (debería tratarlo defensivamente)
        conn.fetchrow.return_value = None
        conn.fetch.return_value = []
        r = await svc.dashboard_pqrsd(conn, tenant_id=uuid4())
        assert r['total_global'] == 0
