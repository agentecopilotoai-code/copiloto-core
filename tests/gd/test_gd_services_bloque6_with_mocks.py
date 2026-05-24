"""Tests con mocks para services bloque 6 (contactos + tareas + notificaciones)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import contactos as svc_con
from app.gd.services import notificaciones as svc_not
from app.gd.services import tareas as svc_tar


# =============================================================================
# Contactos
# =============================================================================
class TestContactosServices:
    @pytest.mark.asyncio
    async def test_crear_contacto_principal_desmarca_otros(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'tercero_id': uuid4(),
            'tipo_contacto': 'correo', 'valor': 'x@y.com',
            'es_principal': True, 'estado': 'activo',
        }
        r = await svc_con.crear_contacto(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
            tipo_contacto='correo', valor='x@y.com', es_principal=True,
        )
        assert r['es_principal'] is True
        # execute() del desmarcado debe haberse llamado
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crear_contacto_no_principal_no_desmarca(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'tercero_id': uuid4(),
            'tipo_contacto': 'telefono', 'valor': '300',
            'es_principal': False, 'estado': 'activo',
        }
        await svc_con.crear_contacto(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
            tipo_contacto='telefono', valor='300', es_principal=False,
        )
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_listar_contactos(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_con.listar_contactos(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_inactivar_contacto_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'tercero_id': uuid4(),
            'tipo_contacto': 'correo', 'valor': 'x',
            'es_principal': False, 'estado': 'inactivo',
        }
        r = await svc_con.inactivar_contacto(
            conn, tenant_id=uuid4(), contacto_id=uuid4(),
        )
        assert r is not None
        assert r['estado'] == 'inactivo'

    @pytest.mark.asyncio
    async def test_inactivar_contacto_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_con.inactivar_contacto(
            conn, tenant_id=uuid4(), contacto_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_historial(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'numero_radicado': 'RAD-2026-001',
                'fecha_radicacion': datetime.now(),
                'asunto': 'X', 'estado': 'registrado',
            }
        ]
        r = await svc_con.obtener_historial_tercero(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
        )
        assert len(r['items']) == 1
        assert r['totales']['radicados'] == 1
        assert r['totales']['pqrsd'] == 0

    @pytest.mark.asyncio
    async def test_obtener_historial_vacio(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_con.obtener_historial_tercero(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
        )
        assert r['items'] == []


# =============================================================================
# Tareas
# =============================================================================
class TestTareasServices:
    @pytest.mark.asyncio
    async def test_crear_tarea(self) -> None:
        conn = AsyncMock()
        tid = uuid4()
        conn.fetchrow.return_value = {
            'id': tid, 'tenant_id': uuid4(),
            'tipo_tarea': 'revisar', 'titulo': 'Test', 'descripcion': None,
            'entidad_origen_tipo': None, 'entidad_origen_id': None,
            'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
            'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
            'fecha_limite': None, 'prioridad': 'normal', 'estado': 'pendiente',
        }
        r = await svc_tar.crear_tarea(
            conn, tenant_id=uuid4(),
            datos={
                'tipo_tarea': 'revisar', 'titulo': 'Test',
                'asignado_a_user_id': uuid4(),
            },
            asignado_por_user_id=uuid4(),
        )
        assert r['id'] == tid
        # historial 'creada' inserted
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_listar_tareas_con_todos_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_tar.listar_tareas(
            conn, tenant_id=uuid4(),
            asignado_a_user_id=uuid4(), asignado_a_dependencia_id=uuid4(),
            estado=['pendiente'], fecha_limite_antes=datetime.now(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_tareas_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_tar.listar_tareas(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_por_estado_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'estado': 'pendiente', 'c': 5},
            {'estado': 'en_proceso', 'c': 2},
        ]
        r = await svc_tar.contar_tareas_por_estado(
            conn, tenant_id=uuid4(),
            asignado_a_user_id=uuid4(), asignado_a_dependencia_id=uuid4(),
        )
        assert r == {'pendiente': 5, 'en_proceso': 2}

    @pytest.mark.asyncio
    async def test_contar_por_estado_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_tar.contar_tareas_por_estado(conn, tenant_id=uuid4())
        assert r == {}

    @pytest.mark.asyncio
    async def test_aplicar_accion_invalida(self) -> None:
        conn = AsyncMock()
        with pytest.raises(ValueError, match='accion inválida'):
            await svc_tar.aplicar_accion(
                conn, tenant_id=uuid4(), tarea_id=uuid4(),
                accion='inexistente', ejecutado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_aplicar_accion_tarea_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='iniciar', ejecutado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_aplicar_accion_iniciar_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},  # actual
            {  # update returning
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'en_proceso',
            },
        ]
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='iniciar', ejecutado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'en_proceso'

    @pytest.mark.asyncio
    async def test_aplicar_accion_devolver_con_observacion(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'en_proceso'},
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'devuelta',
            },
        ]
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='devolver', ejecutado_por_user_id=uuid4(),
            observacion='Faltan datos',
        )
        assert r['estado'] == 'devuelta'

    @pytest.mark.asyncio
    async def test_aplicar_accion_finalizar_setea_finalizada_en(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'en_proceso'},
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'finalizada',
            },
        ]
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='finalizar', ejecutado_por_user_id=uuid4(),
            observacion='Listo',
        )
        assert r['estado'] == 'finalizada'

    @pytest.mark.asyncio
    async def test_aplicar_accion_anular_con_motivo(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'anulada',
            },
        ]
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='anular', ejecutado_por_user_id=uuid4(),
            observacion='Ya no aplica',
        )
        assert r['estado'] == 'anulada'

    @pytest.mark.asyncio
    async def test_aplicar_accion_escalar(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': uuid4(), 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'alta', 'estado': 'pendiente',
            },
        ]
        r = await svc_tar.aplicar_accion(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            accion='escalar', ejecutado_por_user_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_reasignar_tarea_ok(self) -> None:
        conn = AsyncMock()
        old_user = uuid4()
        new_user = uuid4()
        conn.fetchrow.side_effect = [
            {'asignado_a_user_id': old_user, 'asignado_a_dependencia_id': None,
             'estado': 'pendiente'},
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'tipo_tarea': 'revisar', 'titulo': 'X', 'descripcion': None,
                'entidad_origen_tipo': None, 'entidad_origen_id': None,
                'asignado_a_user_id': new_user, 'asignado_a_dependencia_id': None,
                'asignado_por_user_id': uuid4(), 'fecha_asignacion': datetime.now(),
                'fecha_limite': None, 'prioridad': 'normal', 'estado': 'pendiente',
            },
        ]
        r = await svc_tar.reasignar_tarea(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            usuario_destino_id=new_user, dependencia_destino_id=None,
            motivo='Cambio operativo', ejecutado_por_user_id=uuid4(),
        )
        assert r['asignado_a_user_id'] == new_user

    @pytest.mark.asyncio
    async def test_reasignar_tarea_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_tar.reasignar_tarea(
            conn, tenant_id=uuid4(), tarea_id=uuid4(),
            usuario_destino_id=uuid4(), dependencia_destino_id=None,
            motivo='X', ejecutado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_carga_por_usuario_dependencia(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'user_id': uuid4(), 'pendientes': 3, 'en_proceso': 1, 'vencidas': 0},
        ]
        r = await svc_tar.carga_por_usuario_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
        )
        assert len(r) == 1
        assert r[0]['pendientes'] == 3


# =============================================================================
# Notificaciones
# =============================================================================
class TestNotificacionesServices:
    @pytest.mark.asyncio
    async def test_crear_notificacion(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'destinatario_user_id': uuid4(),
            'tipo_notificacion': 'tarea_asignada', 'titulo': 'X',
            'mensaje': 'Y', 'entidad_origen_tipo': None,
            'entidad_origen_id': None, 'enviada_por_canal': ['in_app'],
            'leida': False, 'fecha_lectura': None, 'created_at': datetime.now(),
        }
        r = await svc_not.crear_notificacion(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
            tipo_notificacion='tarea_asignada', titulo='X', mensaje='Y',
        )
        assert r['tipo_notificacion'] == 'tarea_asignada'

    @pytest.mark.asyncio
    async def test_listar_solo_no_leidas(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_not.listar_notificaciones(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
            solo_no_leidas=True,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_todas(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_not.listar_notificaciones(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_no_leidas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 5}
        r = await svc_not.contar_no_leidas(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == 5

    @pytest.mark.asyncio
    async def test_contar_no_leidas_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_not.contar_no_leidas(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == 0

    @pytest.mark.asyncio
    async def test_contar_total(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 10}
        r = await svc_not.contar_total(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == 10

    @pytest.mark.asyncio
    async def test_contar_total_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_not.contar_total(
            conn, tenant_id=uuid4(), destinatario_user_id=uuid4(),
        )
        assert r == 0

    @pytest.mark.asyncio
    async def test_marcar_leida_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'leida': True, 'fecha_lectura': datetime.now(),
        }
        r = await svc_not.marcar_leida(
            conn, tenant_id=uuid4(), notificacion_id=uuid4(),
            destinatario_user_id=uuid4(),
        )
        assert r['leida'] is True

    @pytest.mark.asyncio
    async def test_marcar_leida_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_not.marcar_leida(
            conn, tenant_id=uuid4(), notificacion_id=uuid4(),
            destinatario_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_preferencias(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_not.obtener_preferencias_usuario(
            conn, tenant_id=uuid4(), user_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_upsert_preferencias(self) -> None:
        conn = AsyncMock()
        r = await svc_not.upsert_preferencias(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            preferencias=[
                {'tipo_notificacion': 'tarea_asignada',
                 'in_app_habilitado': True, 'correo_habilitado': False},
            ],
        )
        assert r == 1
        conn.execute.assert_awaited_once()
