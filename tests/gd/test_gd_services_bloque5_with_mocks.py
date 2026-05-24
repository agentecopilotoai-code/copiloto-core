"""Tests con mocks para services del bloque 5 (terceros + radicados)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import radicados as svc_rad
from app.gd.services import terceros as svc_ter


# =============================================================================
# Terceros
# =============================================================================
class TestTercerosServices:
    @pytest.mark.asyncio
    async def test_crear_tercero(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
            'numero_documento': '12345678',
            'nombres_razon_social': 'Juan Pérez',
            'correo': None, 'telefono': None, 'direccion': None,
            'municipio': None, 'departamento': None, 'pais': 'CO',
            'estado': 'activo',
        }
        r = await svc_ter.crear_tercero(
            conn, tenant_id=uuid4(),
            datos={
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678', 'nombres_razon_social': 'Juan Pérez',
            },
            created_by_user_id=uuid4(),
        )
        assert r['tipo_tercero'] == 'persona_natural'

    @pytest.mark.asyncio
    async def test_obtener_tercero_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
            'numero_documento': '123', 'nombres_razon_social': 'X',
            'correo': None, 'telefono': None, 'direccion': None,
            'municipio': None, 'departamento': None, 'pais': 'CO',
            'estado': 'activo',
        }
        r = await svc_ter.obtener_tercero(conn, tenant_id=uuid4(), tercero_id=uuid4())
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_tercero_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_ter.obtener_tercero(conn, tenant_id=uuid4(), tercero_id=uuid4())
        assert r is None

    @pytest.mark.asyncio
    async def test_actualizar_tercero_sin_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
            'numero_documento': '123', 'nombres_razon_social': 'X',
            'correo': None, 'telefono': None, 'direccion': None,
            'municipio': None, 'departamento': None, 'pais': 'CO',
            'estado': 'activo',
        }
        r = await svc_ter.actualizar_tercero(
            conn, tenant_id=uuid4(), tercero_id=uuid4(), cambios={},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_actualizar_tercero_con_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
            'numero_documento': '123', 'nombres_razon_social': 'X',
            'correo': 'nuevo@x.com', 'telefono': None, 'direccion': None,
            'municipio': None, 'departamento': None, 'pais': 'CO',
            'estado': 'activo',
        }
        r = await svc_ter.actualizar_tercero(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
            cambios={'correo': 'nuevo@x.com'},
        )
        assert r['correo'] == 'nuevo@x.com'

    @pytest.mark.asyncio
    async def test_actualizar_tercero_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_ter.actualizar_tercero(
            conn, tenant_id=uuid4(), tercero_id=uuid4(),
            cambios={'correo': 'x@y.com'},
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_buscar_por_documento_exacto(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tipo_tercero': 'persona_natural',
                'tipo_documento': 'CC', 'numero_documento': '123',
                'nombres_razon_social': 'X', 'correo': None,
            }
        ]
        r = await svc_ter.buscar_tercero(conn, tenant_id=uuid4(), documento='123')
        assert len(r['items']) == 1

    @pytest.mark.asyncio
    async def test_buscar_por_email(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tipo_tercero': 'persona_natural',
                'tipo_documento': 'CC', 'numero_documento': '123',
                'nombres_razon_social': 'X', 'correo': 'x@y.com',
            }
        ]
        r = await svc_ter.buscar_tercero(conn, tenant_id=uuid4(), email='x@y.com')
        assert len(r['items']) == 1

    @pytest.mark.asyncio
    async def test_buscar_por_nombre_devuelve_duplicados(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tipo_tercero': 'persona_natural',
                'tipo_documento': 'CC', 'numero_documento': '123',
                'nombres_razon_social': 'Juan Pérez', 'correo': None,
            }
        ]
        r = await svc_ter.buscar_tercero(conn, tenant_id=uuid4(), nombre='Juan')
        assert len(r['posibles_duplicados']) == 1

    @pytest.mark.asyncio
    async def test_buscar_sin_filtros_devuelve_vacio(self) -> None:
        conn = AsyncMock()
        r = await svc_ter.buscar_tercero(conn, tenant_id=uuid4())
        assert r['items'] == []
        assert r['posibles_duplicados'] == []

    @pytest.mark.asyncio
    async def test_buscar_documento_y_email_no_duplica(self) -> None:
        """Si el mismo tercero matchea por documento y email, solo aparece una vez."""
        conn = AsyncMock()
        tid = uuid4()
        item = {
            'id': tid, 'tipo_tercero': 'persona_natural',
            'tipo_documento': 'CC', 'numero_documento': '123',
            'nombres_razon_social': 'X', 'correo': 'x@y.com',
        }
        conn.fetch.side_effect = [[item], [item]]  # mismo en ambas queries
        r = await svc_ter.buscar_tercero(
            conn, tenant_id=uuid4(), documento='123', email='x@y.com',
        )
        assert len(r['items']) == 1


# =============================================================================
# Radicados — crear / consultar / buscar
# =============================================================================
class TestRadicadosCrearConsultar:
    @pytest.mark.asyncio
    async def test_crear_radicado(self, monkeypatch) -> None:
        conn = AsyncMock()
        # siguiente_radicado (fetchrow para SQL function)
        rid = uuid4()
        conn.fetchrow.side_effect = [
            {'numero_radicado': 'RAD-2026-000001'},
            # INSERT radicado RETURNING
            {
                'id': rid, 'tenant_id': uuid4(),
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': uuid4(), 'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': uuid4(), 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'R2X9F4',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
        ]
        # fetchval para chequeo de colisión codigo_verificacion
        conn.fetchval.return_value = None  # sin colisión

        r = await svc_rad.crear_radicado(
            conn, tenant_id=uuid4(),
            tipo_radicado='entrada', canal_id=uuid4(),
            asunto='X', descripcion=None,
            tercero_id=None, tercero_destinatario_id=None,
            dependencia_origen_id=None, dependencia_destino_id=None,
            documento_principal_id=None,
            usuario_radicador_id=uuid4(),
            actor_snapshot={'nombre_completo': 'Test'},
        )
        assert r['numero_radicado'] == 'RAD-2026-000001'
        assert r['codigo_verificacion'] == 'R2X9F4'

    @pytest.mark.asyncio
    async def test_crear_radicado_codigo_colisiona_y_reintentamos(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'numero_radicado': 'RAD-2026-000001'},  # consecutivo
            {  # INSERT después de resolver colisión
                'id': uuid4(), 'tenant_id': uuid4(),
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': uuid4(), 'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': uuid4(), 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'XXYYZZ',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
        ]
        # Primera colisión, segunda sin colisión.
        conn.fetchval.side_effect = [1, None]
        r = await svc_rad.crear_radicado(
            conn, tenant_id=uuid4(),
            tipo_radicado='entrada', canal_id=uuid4(),
            asunto='X', descripcion=None,
            tercero_id=None, tercero_destinatario_id=None,
            dependencia_origen_id=None, dependencia_destino_id=None,
            documento_principal_id=None,
            usuario_radicador_id=uuid4(),
            actor_snapshot={},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_crear_radicado_codigo_agotado_lanza(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'numero_radicado': 'RAD-2026-000001'}
        # Siempre colisión.
        conn.fetchval.return_value = 1
        with pytest.raises(RuntimeError, match='No se pudo generar'):
            await svc_rad.crear_radicado(
                conn, tenant_id=uuid4(),
                tipo_radicado='entrada', canal_id=uuid4(),
                asunto='X', descripcion=None,
                tercero_id=None, tercero_destinatario_id=None,
                dependencia_origen_id=None, dependencia_destino_id=None,
                documento_principal_id=None,
                usuario_radicador_id=uuid4(),
                actor_snapshot={},
            )

    @pytest.mark.asyncio
    async def test_obtener_radicado_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
            'fecha_radicacion': datetime.now(),
            'canal_id': uuid4(), 'canal_codigo': 'pres', 'canal_nombre': 'Presencial',
            'punto_atencion_id': None,
            'asunto': 'X', 'descripcion': None,
            'tercero_id': None, 'tercero_destinatario_id': None,
            'dependencia_origen_id': None, 'dependencia_destino_id': None,
            'documento_principal_id': None,
            'usuario_radicador_id': uuid4(), 'estado': 'registrado',
            'radicado_relacionado_id': None,
            'codigo_verificacion': 'XYZ123',
            'es_radicacion_contingencia': False,
            'actor_snapshot': {},
        }
        r = await svc_rad.obtener_radicado(conn, tenant_id=uuid4(), radicado_id=uuid4())
        assert r is not None
        assert r['numero_radicado'] == 'RAD-2026-000001'

    @pytest.mark.asyncio
    async def test_obtener_radicado_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_rad.obtener_radicado(conn, tenant_id=uuid4(), radicado_id=uuid4())
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_por_codigo(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
            'fecha_radicacion': datetime.now(), 'asunto': 'X',
            'estado': 'registrado', 'codigo_verificacion': 'XYZ123',
        }
        r = await svc_rad.obtener_radicado_por_codigo(
            conn, tenant_id=uuid4(), codigo='XYZ123',
        )
        assert r is not None
        assert r['codigo_verificacion'] == 'XYZ123'

    @pytest.mark.asyncio
    async def test_buscar_radicados_con_todos_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_rad.buscar_radicados(
            conn, tenant_id=uuid4(),
            numero_radicado='RAD-2026-000001', q='oficio',
            tipo_radicado=['entrada'], estado=['registrado'],
            canal_id=uuid4(), dependencia_destino_id=uuid4(),
            tercero_id=uuid4(),
            fecha_desde=datetime(2026, 1, 1), fecha_hasta=datetime(2026, 12, 31),
            limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_buscar_radicados_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_rad.buscar_radicados(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_buscar_radicados_anexo_tabla_no_existe_fallback(self) -> None:
        """Si gd.anexo no existe (EP-009 no implementado), fallback simplifica query."""
        conn = AsyncMock()
        import asyncpg
        # Primera llamada: error UndefinedTable. Segunda llamada (fallback): ok.
        conn.fetch.side_effect = [
            asyncpg.UndefinedTableError('gd.anexo no existe'),
            [],
        ]
        r = await svc_rad.buscar_radicados(conn, tenant_id=uuid4())
        assert r == []
        assert conn.fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_contar_radicados(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 42}
        assert await svc_rad.contar_radicados(conn, tenant_id=uuid4()) == 42

    @pytest.mark.asyncio
    async def test_contar_radicados_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc_rad.contar_radicados(conn, tenant_id=uuid4()) == 0


# =============================================================================
# Clasificación
# =============================================================================
class TestClasificacion:
    @pytest.mark.asyncio
    async def test_clasificar_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None  # no hay vigente
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_id': uuid4(),
            'tipo_clasificacion': 'pqrsd', 'sub_tipo': 'peticion',
            'dependencia_destino_id': None, 'tipo_pqrsd_id': uuid4(),
            'fuente': 'manual', 'clasificado_por_user_id': uuid4(),
            'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
        }
        r = await svc_rad.clasificar_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_clasificacion='pqrsd', sub_tipo='peticion',
            dependencia_destino_id=None, tipo_pqrsd_id=uuid4(),
            justificacion=None, sugerencia_ia_id=None,
            clasificado_por_user_id=uuid4(),
        )
        assert r is not None
        assert r['tipo_clasificacion'] == 'pqrsd'

    @pytest.mark.asyncio
    async def test_clasificar_con_sugerencia_ia_fuente(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetchrow.return_value = {
            'id': uuid4(), 'radicado_id': uuid4(),
            'tipo_clasificacion': 'pqrsd', 'sub_tipo': None,
            'dependencia_destino_id': None, 'tipo_pqrsd_id': None,
            'fuente': 'ia_aceptada', 'clasificado_por_user_id': uuid4(),
            'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
        }
        r = await svc_rad.clasificar_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_clasificacion='pqrsd', sub_tipo=None,
            dependencia_destino_id=None, tipo_pqrsd_id=None,
            justificacion=None, sugerencia_ia_id=uuid4(),
            clasificado_por_user_id=uuid4(),
        )
        assert r['fuente'] == 'ia_aceptada'

    @pytest.mark.asyncio
    async def test_clasificar_ya_existe_devuelve_none(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # ya vigente
        r = await svc_rad.clasificar_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_clasificacion='pqrsd', sub_tipo=None,
            dependencia_destino_id=None, tipo_pqrsd_id=None,
            justificacion=None, sugerencia_ia_id=None,
            clasificado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reclasificar_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4()},  # vigente anterior
            {  # nueva vigente
                'id': uuid4(), 'radicado_id': uuid4(),
                'tipo_clasificacion': 'expediente', 'sub_tipo': None,
                'dependencia_destino_id': None, 'tipo_pqrsd_id': None,
                'fuente': 'manual', 'clasificado_por_user_id': uuid4(),
                'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
            },
        ]
        r = await svc_rad.reclasificar_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_clasificacion='expediente', sub_tipo=None,
            dependencia_destino_id=None, tipo_pqrsd_id=None,
            justificacion=None, sugerencia_ia_id=None,
            motivo='Cambio de criterio',
            clasificado_por_user_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_reclasificar_sin_vigente_devuelve_none(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # no hay vigente
        r = await svc_rad.reclasificar_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_clasificacion='pqrsd', sub_tipo=None,
            dependencia_destino_id=None, tipo_pqrsd_id=None,
            justificacion=None, sugerencia_ia_id=None,
            motivo='Cambio',
            clasificado_por_user_id=uuid4(),
        )
        assert r is None


# =============================================================================
# Anulación
# =============================================================================
class TestAnulacion:
    @pytest.mark.asyncio
    async def test_crear_solicitud_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = None  # sin pendiente
        sid = uuid4()
        conn.fetchrow.return_value = {
            'id': sid, 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'solicitante_user_id': uuid4(),
            'motivo': 'Error de digitación grave',
            'decision': 'pendiente', 'fecha_solicitud': datetime.now(),
        }
        r = await svc_rad.crear_solicitud_anulacion(
            conn, tenant_id=uuid4(),
            tipo_entidad='radicado', entidad_afectada_id=uuid4(),
            solicitante_user_id=uuid4(),
            motivo='Error de digitación grave',
            evidencia_archivo_digital_id=None,
        )
        assert r['id'] == sid

    @pytest.mark.asyncio
    async def test_crear_solicitud_duplicada_devuelve_none(self) -> None:
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # ya hay pendiente
        r = await svc_rad.crear_solicitud_anulacion(
            conn, tenant_id=uuid4(),
            tipo_entidad='radicado', entidad_afectada_id=uuid4(),
            solicitante_user_id=uuid4(),
            motivo='X', evidencia_archivo_digital_id=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_solicitud(self) -> None:
        conn = AsyncMock()
        sid = uuid4()
        conn.fetchrow.return_value = {
            'id': sid, 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'solicitante_user_id': uuid4(),
            'motivo': 'X', 'decision': 'pendiente',
            'aprobador_user_id': None, 'observacion_decision': None,
            'fecha_solicitud': datetime.now(), 'fecha_decision': None,
        }
        r = await svc_rad.obtener_solicitud_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=sid,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_solicitud_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_rad.obtener_solicitud_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_aprobar_solicitud_radicado_ejecuta_anulacion(self) -> None:
        conn = AsyncMock()
        rad_id = uuid4()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'radicado',
            'entidad_afectada_id': rad_id,
            'aprobador_user_id': uuid4(),
            'fecha_decision': datetime.now(),
        }
        r = await svc_rad.aprobar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(),
            observacion_decision=None,
        )
        assert r is not None
        # Verificar UPDATE radicado se llamó.
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aprobar_solicitud_no_radicado_no_ejecuta(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'documento',
            'entidad_afectada_id': uuid4(),
            'aprobador_user_id': uuid4(),
            'fecha_decision': datetime.now(),
        }
        r = await svc_rad.aprobar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(),
            observacion_decision=None,
        )
        assert r is not None
        conn.execute.assert_not_awaited()  # documento → no toca radicado

    @pytest.mark.asyncio
    async def test_aprobar_solicitud_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_rad.aprobar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(), observacion_decision=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_rechazar_solicitud(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'aprobador_user_id': uuid4(),
            'fecha_decision': datetime.now(),
        }
        r = await svc_rad.rechazar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(),
            observacion_decision='No procede según política institucional',
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_rechazar_solicitud_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_rad.rechazar_solicitud(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(),
            observacion_decision='Rechazado por motivos',
        )
        assert r is None
