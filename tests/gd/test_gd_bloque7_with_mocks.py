"""Tests con mocks para services del bloque 7 (alertas + pqrsd)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import alertas as svc_ale
from app.gd.services import pqrsd as svc_pq


# =============================================================================
# Alertas
# =============================================================================
class TestAlertasServices:
    @pytest.mark.asyncio
    async def test_crear_alerta(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'destinatario_user_id': uuid4(),
            'destinatario_dependencia_id': None,
            'tipo_alerta': 'proximo_vencimiento', 'severidad': 'alta',
            'titulo': 'X', 'mensaje': 'Y',
            'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
            'estado': 'activa', 'created_at': datetime.now(),
        }
        r = await svc_ale.crear_alerta(
            conn, tenant_id=uuid4(),
            tipo_alerta='proximo_vencimiento', severidad='alta',
            titulo='X', mensaje='Y',
            destinatario_user_id=uuid4(),
        )
        assert r['severidad'] == 'alta'

    @pytest.mark.asyncio
    async def test_listar_alertas_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_ale.listar_alertas(
            conn, tenant_id=uuid4(),
            destinatario_user_id=uuid4(), estado='activa', severidad='critica',
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_alertas_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_ale.listar_alertas(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_activas_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'total': 5, 'criticas': 2}
        r = await svc_ale.contar_activas(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == {'total': 5, 'criticas': 2}

    @pytest.mark.asyncio
    async def test_contar_activas_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_ale.contar_activas(conn, tenant_id=uuid4())
        assert r == {'total': 0, 'criticas': 0}

    @pytest.mark.asyncio
    async def test_escalar_alerta_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'destinatario_user_id': uuid4(),
            'destinatario_dependencia_id': None,
            'tipo_alerta': 'vencido', 'severidad': 'critica',
            'titulo': 'X', 'mensaje': 'Y',
            'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
            'estado': 'escalada', 'created_at': datetime.now(),
        }
        r = await svc_ale.escalar_alerta(
            conn, tenant_id=uuid4(), alerta_id=uuid4(),
            user_destino_id=uuid4(), motivo='Escalación urgente',
            ejecutado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'escalada'

    @pytest.mark.asyncio
    async def test_escalar_alerta_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_ale.escalar_alerta(
            conn, tenant_id=uuid4(), alerta_id=uuid4(),
            user_destino_id=uuid4(), motivo='X',
            ejecutado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_marcar_gestionada_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'destinatario_user_id': uuid4(),
            'destinatario_dependencia_id': None,
            'tipo_alerta': 'vencido', 'severidad': 'alta',
            'titulo': 'X', 'mensaje': 'Y',
            'entidad_relacionada_tipo': None, 'entidad_relacionada_id': None,
            'estado': 'gestionada', 'created_at': datetime.now(),
        }
        r = await svc_ale.marcar_gestionada(
            conn, tenant_id=uuid4(), alerta_id=uuid4(),
            user_id=uuid4(), observacion='Gestionada por proceso X',
        )
        assert r['estado'] == 'gestionada'

    @pytest.mark.asyncio
    async def test_marcar_gestionada_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_ale.marcar_gestionada(
            conn, tenant_id=uuid4(), alerta_id=uuid4(),
            user_id=uuid4(), observacion=None,
        )
        assert r is None


# =============================================================================
# PQRSD services
# =============================================================================
class TestPqrsdServices:
    @pytest.mark.asyncio
    async def test_crear_desde_radicado_idempotente(self) -> None:
        """Si ya existe PQRSD para el radicado, retorna None."""
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # ya existe
        r = await svc_pq.crear_desde_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_pqrsd_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_sin_radicado_lanza(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetchrow.return_value = None  # radicado no existe
        with pytest.raises(ValueError):
            await svc_pq.crear_desde_radicado(
                conn, tenant_id=uuid4(), radicado_id=uuid4(),
                tipo_pqrsd_id=None,
            )

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_ok_sin_tipo_pqrsd(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'asunto': 'X', 'descripcion': None,
                'tercero_id': uuid4(), 'fecha_radicacion': datetime.now(),
                'actor_snapshot': '{}',
            },
            {  # INSERT pqrsd RETURNING
                'id': uuid4(), 'radicado_entrada_id': uuid4(),
                'tipo_pqrsd_id': None, 'tercero_id': uuid4(),
                'asunto': 'X', 'descripcion': None,
                'dependencia_responsable_id': None,
                'usuario_responsable_id': None,
                'fecha_recepcion': datetime.now(),
                'fecha_limite_respuesta': None,
                'estado': 'clasificada', 'prioridad': 'normal', 'reserva': False,
            },
        ]
        r = await svc_pq.crear_desde_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_pqrsd_id=None,
        )
        assert r is not None
        assert r['estado'] == 'clasificada'

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_con_tipo_pqrsd_calcula_fecha(self) -> None:
        conn = AsyncMock()
        fecha_limite = datetime.now() + timedelta(days=15)
        conn.fetchval.return_value = None
        conn.fetchrow.side_effect = [
            # 1. Datos del radicado
            {
                'id': uuid4(), 'asunto': 'X', 'descripcion': None,
                'tercero_id': uuid4(), 'fecha_radicacion': datetime.now(),
                'actor_snapshot': {'usuario_id': str(uuid4())},
            },
            # 2. tipo_pqrsd
            {'termino_dias': 15, 'tipo_dias': 'habiles'},
            # 3. fecha_limite calculada
            {'fecha_limite': fecha_limite},
            # 4. INSERT pqrsd
            {
                'id': uuid4(), 'radicado_entrada_id': uuid4(),
                'tipo_pqrsd_id': uuid4(), 'tercero_id': uuid4(),
                'asunto': 'X', 'descripcion': None,
                'dependencia_responsable_id': None,
                'usuario_responsable_id': None,
                'fecha_recepcion': datetime.now(),
                'fecha_limite_respuesta': fecha_limite,
                'estado': 'clasificada', 'prioridad': 'normal', 'reserva': False,
            },
        ]
        r = await svc_pq.crear_desde_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_pqrsd_id=uuid4(),
        )
        assert r['fecha_limite_respuesta'] == fecha_limite

    @pytest.mark.asyncio
    async def test_obtener_pqrsd(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_entrada_id': uuid4(),
            'tipo_pqrsd_id': None, 'tercero_id': None,
            'asunto': 'X', 'descripcion': None,
            'dependencia_responsable_id': None,
            'usuario_responsable_id': None,
            'fecha_recepcion': datetime.now(),
            'fecha_limite_respuesta': None,
            'estado': 'clasificada', 'prioridad': 'normal', 'reserva': False,
        }
        r = await svc_pq.obtener_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_pq.obtener_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_pqrsd_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_pq.listar_pqrsd(
            conn, tenant_id=uuid4(),
            estado=['nueva', 'asignada'],
            dependencia_id=uuid4(), usuario_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_pqrsd_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_pq.listar_pqrsd(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_pqrsd(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 10}
        assert await svc_pq.contar_pqrsd(conn, tenant_id=uuid4()) == 10

    @pytest.mark.asyncio
    async def test_contar_pqrsd_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc_pq.contar_pqrsd(conn, tenant_id=uuid4()) == 0

    @pytest.mark.asyncio
    async def test_asignar_dependencia_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # pqrsd existe
        conn.fetchrow.return_value = {
            'id': uuid4(), 'pqrsd_id': uuid4(),
            'dependencia_id': uuid4(), 'usuario_asignado_id': None,
            'asignado_por_user_id': uuid4(),
            'fecha_asignacion': datetime.now(), 'fecha_fin': None,
            'motivo': None, 'estado': 'activa',
        }
        r = await svc_pq.asignar_a_dependencia(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            dependencia_id=uuid4(), asignado_por_user_id=uuid4(), motivo=None,
        )
        assert r is not None
        assert r['estado'] == 'activa'

    @pytest.mark.asyncio
    async def test_asignar_dependencia_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc_pq.asignar_a_dependencia(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            dependencia_id=uuid4(), asignado_por_user_id=uuid4(), motivo=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_asignar_funcionario_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'pqrsd_id': uuid4(),
            'dependencia_id': None, 'usuario_asignado_id': uuid4(),
            'asignado_por_user_id': uuid4(),
            'fecha_asignacion': datetime.now(), 'fecha_fin': None,
            'motivo': None, 'estado': 'activa',
        }
        r = await svc_pq.asignar_a_funcionario(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            usuario_id=uuid4(), asignado_por_user_id=uuid4(), motivo=None,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_asignar_funcionario_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc_pq.asignar_a_funcionario(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            usuario_id=uuid4(), asignado_por_user_id=uuid4(), motivo=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reasignar_pqrsd_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'pqrsd_id': uuid4(),
            'dependencia_id': uuid4(), 'usuario_asignado_id': uuid4(),
            'asignado_por_user_id': uuid4(),
            'fecha_asignacion': datetime.now(), 'fecha_fin': None,
            'motivo': 'X', 'estado': 'activa',
        }
        r = await svc_pq.reasignar_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            dependencia_id=uuid4(), usuario_id=uuid4(),
            motivo='Reasignación operativa',
            asignado_por_user_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_reasignar_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc_pq.reasignar_pqrsd(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            dependencia_id=None, usuario_id=uuid4(),
            motivo='X', asignado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_proyectar_respuesta_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'pqrsd_id': uuid4(),
            'documento_id': None, 'plantilla_id': None,
            'contenido_borrador': 'Borrador test',
            'usuario_proyecta_id': uuid4(),
            'usuario_revisa_id': None, 'usuario_aprueba_id': None,
            'usuario_firma_id': None, 'radicado_salida_id': None,
            'estado': 'borrador',
            'fecha_proyeccion': datetime.now(),
            'fecha_revision': None, 'fecha_aprobacion': None,
            'fecha_firma': None, 'fecha_radicacion': None, 'fecha_envio': None,
        }
        r = await svc_pq.proyectar_respuesta(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            documento_id=None, plantilla_id=None,
            contenido_borrador='Borrador test',
            usuario_proyecta_id=uuid4(),
        )
        assert r['estado'] == 'borrador'

    @pytest.mark.asyncio
    async def test_proyectar_respuesta_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc_pq.proyectar_respuesta(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            documento_id=None, plantilla_id=None,
            contenido_borrador='X', usuario_proyecta_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_suspender_termino_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'fecha_limite_respuesta': datetime.now(timezone.utc)},
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'tipo_evento': 'suspension', 'fecha_evento': datetime.now(),
                'motivo': 'X', 'justificacion_legal': None,
                'dias_afectados': None,
                'fecha_limite_anterior': datetime.now(),
                'fecha_limite_nueva': None, 'usuario_id': uuid4(),
            },
        ]
        r = await svc_pq.suspender_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='Solicitud info adicional',
            justificacion_legal=None, dias_estimados=None,
            usuario_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_suspender_termino_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_pq.suspender_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='X', justificacion_legal=None, dias_estimados=None,
            usuario_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reanudar_termino_recalcula(self) -> None:
        conn = AsyncMock()
        fecha_susp = datetime.now(timezone.utc) - timedelta(days=5)
        fecha_lim = datetime.now(timezone.utc) + timedelta(days=10)
        conn.fetchrow.side_effect = [
            {'fecha_limite_respuesta': fecha_lim},
            {'fecha_evento': fecha_susp},
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'tipo_evento': 'reanudacion', 'fecha_evento': datetime.now(),
                'motivo': 'X', 'justificacion_legal': None,
                'dias_afectados': 5,
                'fecha_limite_anterior': fecha_lim,
                'fecha_limite_nueva': fecha_lim + timedelta(days=5),
                'usuario_id': uuid4(),
            },
        ]
        r = await svc_pq.reanudar_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='Reanudación', usuario_id=uuid4(),
        )
        assert r is not None
        assert r['dias_afectados'] >= 0

    @pytest.mark.asyncio
    async def test_reanudar_termino_pqrsd_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_pq.reanudar_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='X', usuario_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reanudar_termino_sin_suspension_previa(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'fecha_limite_respuesta': datetime.now(timezone.utc)},
            None,  # sin suspensión previa
            {
                'id': uuid4(), 'pqrsd_id': uuid4(),
                'tipo_evento': 'reanudacion', 'fecha_evento': datetime.now(),
                'motivo': 'X', 'justificacion_legal': None,
                'dias_afectados': 0,
                'fecha_limite_anterior': datetime.now(),
                'fecha_limite_nueva': datetime.now(),
                'usuario_id': uuid4(),
            },
        ]
        r = await svc_pq.reanudar_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
            motivo='X', usuario_id=uuid4(),
        )
        assert r['dias_afectados'] == 0

    @pytest.mark.asyncio
    async def test_listar_eventos_termino(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_pq.listar_eventos_termino(
            conn, tenant_id=uuid4(), pqrsd_id=uuid4(),
        )
        assert r == []
