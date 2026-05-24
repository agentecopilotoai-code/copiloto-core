"""Tests mocks para services del bloque 15 (reportes EP-014)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import reportes as svc


# =============================================================================
# CSV builder
# =============================================================================
class TestCsv:
    def test_vacio(self):
        assert svc.filas_to_csv([]) == ''

    def test_simple(self):
        out = svc.filas_to_csv([
            {'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'},
        ])
        assert 'a,b' in out
        assert '1,x' in out

    def test_con_none(self):
        out = svc.filas_to_csv([{'a': None, 'b': 'x'}])
        assert ',x' in out

    def test_normalize_uuid_datetime(self):
        uid = uuid4()
        dt = datetime.now()
        out = svc._normalize_for_csv({'id': uid, 'fecha': dt, 'n': 5})
        assert out['id'] == str(uid)
        assert out['fecha'] == dt.isoformat()
        assert out['n'] == 5


# =============================================================================
# Reporte radicados
# =============================================================================
class TestReporteRadicados:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'fecha': '2026-05-01', 'canal_id': uuid4(),
             'dependencia_id': None, 'tipo_radicado': 'entrada',
             'estado': 'radicado', 'total': 3},
        ]
        conn.fetchval.return_value = 3
        r = await svc.reporte_radicados(conn, tenant_id=uuid4())
        assert r['total_radicados'] == 3
        assert len(r['filas']) == 1

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0
        r = await svc.reporte_radicados(
            conn, tenant_id=uuid4(),
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
            canal_id=uuid4(), dependencia_id=uuid4(),
            tipo_radicado='salida', estado='radicado',
        )
        assert r['total_radicados'] == 0


# =============================================================================
# Reporte PQRSD
# =============================================================================
class TestReportePqrsd:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 10, 'total_vencidas': 2,
            'total_proximas_vencer': 1, 'total_cerradas': 5,
        }
        conn.fetch.return_value = [
            {'tipo_pqrsd_id': uuid4(), 'dependencia_id': uuid4(),
             'estado': 'asignada', 'total': 5, 'vencidas': 1,
             'proximas_vencer': 0, 'dias_promedio_resolucion': 3.2},
        ]
        r = await svc.reporte_pqrsd(conn, tenant_id=uuid4())
        assert r['total_global'] == 10
        assert r['filas'][0]['dias_promedio_resolucion'] == 3.2

    @pytest.mark.asyncio
    async def test_filtros_vencidas(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 0, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = []
        r = await svc.reporte_pqrsd(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            dependencia_id=uuid4(), tipo_pqrsd_id=uuid4(),
            estado='asignada',
            solo_vencidas=True, solo_proximas_vencer=True,
        )
        assert r['total_global'] == 0

    @pytest.mark.asyncio
    async def test_totales_none_safe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # edge case
        conn.fetch.return_value = []
        r = await svc.reporte_pqrsd(conn, tenant_id=uuid4())
        assert r['total_global'] == 0

    @pytest.mark.asyncio
    async def test_dias_promedio_null(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'total_global': 1, 'total_vencidas': 0,
            'total_proximas_vencer': 0, 'total_cerradas': 0,
        }
        conn.fetch.return_value = [{
            'tipo_pqrsd_id': None, 'dependencia_id': None,
            'estado': 'nueva', 'total': 1, 'vencidas': 0,
            'proximas_vencer': 0, 'dias_promedio_resolucion': None,
        }]
        r = await svc.reporte_pqrsd(conn, tenant_id=uuid4())
        assert r['filas'][0]['dias_promedio_resolucion'] is None


# =============================================================================
# Reporte correspondencia
# =============================================================================
class TestReporteCorrespondencia:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 5
        conn.fetch.return_value = [
            {'tipo': 'interna', 'estado': 'enviada',
             'dependencia_id': uuid4(), 'total': 3},
        ]
        r = await svc.reporte_correspondencia(conn, tenant_id=uuid4())
        assert r['total'] == 5

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = await svc.reporte_correspondencia(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            tipo='externa_enviada', dependencia_id=uuid4(),
            estado='enviada',
        )
        assert r['total'] == 0


# =============================================================================
# Reporte cargas
# =============================================================================
class TestReporteCargas:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'user_id': uuid4(), 'dependencia_id': uuid4(),
             'tareas_pendientes': 5, 'tareas_completadas_periodo': 10,
             'radicados_clasificados_periodo': 0},
        ]
        r = await svc.reporte_cargas(conn, tenant_id=uuid4())
        assert r['filas'][0]['tareas_pendientes'] == 5

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.reporte_cargas(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            dependencia_id=uuid4(), user_id=uuid4(),
        )
        assert r['filas'] == []


# =============================================================================
# Reporte uso IA
# =============================================================================
class TestReporteUsoIA:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'tipo_asistencia': 'clasificacion',
             'total_solicitudes': 10, 'completadas': 9, 'failed': 1,
             'aceptadas': 5, 'modificadas': 2, 'rechazadas': 1,
             'sin_decision': 1},
            {'tipo_asistencia': 'resumen',
             'total_solicitudes': 3, 'completadas': 3, 'failed': 0,
             'aceptadas': 3, 'modificadas': 0, 'rechazadas': 0,
             'sin_decision': 0},
        ]
        r = await svc.reporte_uso_ia(conn, tenant_id=uuid4())
        assert r['total_solicitudes'] == 13
        assert len(r['filas']) == 2

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.reporte_uso_ia(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            tipo_asistencia='clasificacion',
        )
        assert r['total_solicitudes'] == 0


# =============================================================================
# Reporte anulaciones
# =============================================================================
class TestReporteAnulaciones:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'tipo_entidad': 'radicado', 'decision': 'aprobada', 'total': 5},
            {'tipo_entidad': 'pqrsd', 'decision': 'rechazada', 'total': 1},
        ]
        r = await svc.reporte_anulaciones(conn, tenant_id=uuid4())
        assert len(r['filas']) == 2

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.reporte_anulaciones(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            tipo_entidad='documento', decision='pendiente',
        )
        assert r['filas'] == []


# =============================================================================
# Reporte auditoría
# =============================================================================
class TestReporteAuditoria:
    @pytest.mark.asyncio
    async def test_basico(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 3
        conn.fetch.return_value = [
            {'fecha': '2026-05-23', 'usuario_id': uuid4(),
             'accion': 'descargar', 'entidad_tipo': 'documento',
             'clasificacion': 'reservada', 'total': 2},
        ]
        r = await svc.reporte_auditoria(conn, tenant_id=uuid4())
        assert r['total'] == 3

    @pytest.mark.asyncio
    async def test_con_filtros(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        r = await svc.reporte_auditoria(
            conn, tenant_id=uuid4(),
            desde=datetime.now(), hasta=datetime.now(),
            usuario_id=uuid4(), entidad_tipo='documento',
        )
        assert r['total'] == 0


# =============================================================================
# Registro + exportar
# =============================================================================
class TestExportar:
    @pytest.mark.asyncio
    async def test_registrar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'radicados',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': {'x': 1},
            'numero_filas': 3, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 50, 'expira_en': None,
        }
        r = await svc.registrar_reporte_generado(
            conn, tenant_id=uuid4(), tipo_reporte='radicados',
            parametros={'desde': None}, formato='csv',
            resumen_inline={'x': 1}, archivo_digital_id=None,
            numero_filas=3, contiene_datos_sensibles=False,
            generado_por_user_id=uuid4(),
            ip='1.2.3.4', user_agent='ua', duracion_ms=50,
        )
        assert r['estado'] == 'completed'

    @pytest.mark.asyncio
    async def test_registrar_jsonb_str(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'pqrsd',
            'parametros': '{}', 'formato': 'json',
            'archivo_digital_id': None, 'resumen_inline': '{"x":1}',
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 10, 'expira_en': None,
        }
        r = await svc.registrar_reporte_generado(
            conn, tenant_id=uuid4(), tipo_reporte='pqrsd',
            parametros={}, formato='json',
            resumen_inline={'x': 1}, archivo_digital_id=None,
            numero_filas=0, contiene_datos_sensibles=False,
            generado_por_user_id=uuid4(),
            ip=None, user_agent=None, duracion_ms=10,
        )
        assert r['parametros'] == {}
        assert r['resumen_inline'] == {'x': 1}

    @pytest.mark.asyncio
    async def test_exportar_formato_invalido(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='formato_invalido'):
            await svc.exportar_reporte(
                conn, tenant_id=uuid4(), tipo_reporte='radicados',
                formato='docx', filtros={},
                incluir_datos_sensibles=False,
                generado_por_user_id=uuid4(),
                ip=None, user_agent=None,
            )

    @pytest.mark.asyncio
    async def test_exportar_tipo_invalido(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='tipo_reporte_invalido'):
            await svc.exportar_reporte(
                conn, tenant_id=uuid4(), tipo_reporte='inexistente',
                formato='csv', filtros={},
                incluir_datos_sensibles=False,
                generado_por_user_id=uuid4(),
                ip=None, user_agent=None,
            )

    @pytest.mark.asyncio
    async def test_exportar_radicados_csv(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'fecha': '2026-05-01', 'canal_id': None,
             'dependencia_id': None, 'tipo_radicado': 'entrada',
             'estado': 'radicado', 'total': 1},
        ]
        conn.fetchval.return_value = 1
        # registrar_reporte_generado fetchrow
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'radicados',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': {'csv_content': 'x'},
            'numero_filas': 1, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(), tipo_reporte='radicados',
            formato='csv', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r['formato'] == 'csv'

    @pytest.mark.asyncio
    async def test_exportar_pqrsd_json(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'total_global': 0, 'total_vencidas': 0,
             'total_proximas_vencer': 0, 'total_cerradas': 0},
            # registrar
            {'id': uuid4(), 'tipo_reporte': 'pqrsd',
             'parametros': {}, 'formato': 'json',
             'archivo_digital_id': None, 'resumen_inline': {},
             'numero_filas': 0, 'contiene_datos_sensibles': False,
             'estado': 'completed', 'error_texto': None,
             'generado_por_user_id': uuid4(),
             'inicio_en': datetime.now(), 'fin_en': datetime.now(),
             'duracion_ms': 5, 'expira_en': None},
        ]
        conn.fetch.return_value = []
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(), tipo_reporte='pqrsd',
            formato='json', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r['formato'] == 'json'

    @pytest.mark.asyncio
    async def test_exportar_correspondencia_excel(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'correspondencia',
            'parametros': {}, 'formato': 'excel',
            'archivo_digital_id': None, 'resumen_inline': {'placeholder': True},
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(), tipo_reporte='correspondencia',
            formato='excel', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r['formato'] == 'excel'

    @pytest.mark.asyncio
    async def test_exportar_cargas_pdf(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'cargas_trabajo',
            'parametros': {}, 'formato': 'pdf',
            'archivo_digital_id': None, 'resumen_inline': {'placeholder': True},
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(), tipo_reporte='cargas_trabajo',
            formato='pdf', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r['formato'] == 'pdf'

    @pytest.mark.asyncio
    async def test_exportar_uso_ia(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'uso_ia',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': {},
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(), tipo_reporte='uso_ia',
            formato='csv', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_exportar_anulaciones(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'anulaciones_reasignaciones',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': {},
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(),
            tipo_reporte='anulaciones_reasignaciones',
            formato='csv', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_exportar_auditoria_sensible(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'auditoria_consultas_sensibles',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': {},
            'numero_filas': 0, 'contiene_datos_sensibles': True,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 5, 'expira_en': None,
        }
        r = await svc.exportar_reporte(
            conn, tenant_id=uuid4(),
            tipo_reporte='auditoria_consultas_sensibles',
            formato='csv', filtros={}, incluir_datos_sensibles=False,
            generado_por_user_id=uuid4(), ip=None, user_agent=None,
        )
        assert r['contiene_datos_sensibles'] is True


# =============================================================================
# Listar / obtener
# =============================================================================
class TestListarObtener:
    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_reportes_generados(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_reportes_generados(
            conn, tenant_id=uuid4(),
            tipo_reporte='radicados',
            generado_por_user_id=uuid4(), limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_jsonb_str(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'id': uuid4(), 'tipo_reporte': 'radicados',
            'parametros': '{}', 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': '{}',
            'numero_filas': 0, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': None,
            'duracion_ms': 0, 'expira_en': None,
        }]
        r = await svc.listar_reportes_generados(conn, tenant_id=uuid4())
        assert r[0]['parametros'] == {}

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_reporte': 'radicados',
            'parametros': {}, 'formato': 'csv',
            'archivo_digital_id': None, 'resumen_inline': None,
            'numero_filas': 5, 'contiene_datos_sensibles': False,
            'estado': 'completed', 'error_texto': None,
            'generado_por_user_id': uuid4(),
            'inicio_en': datetime.now(), 'fin_en': datetime.now(),
            'duracion_ms': 100, 'expira_en': None,
        }
        r = await svc.obtener_reporte_generado(
            conn, tenant_id=uuid4(), reporte_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_reporte_generado(
            conn, tenant_id=uuid4(), reporte_id=uuid4(),
        )
        assert r is None
