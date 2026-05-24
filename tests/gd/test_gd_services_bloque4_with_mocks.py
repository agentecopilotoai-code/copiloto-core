"""Tests con mocks para los services del bloque 4 (catalogos + parametros + consecutivos)."""
from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import catalogos as svc_cat
from app.gd.services import consecutivos as svc_con
from app.gd.services import parametros as svc_par


# =============================================================================
# Cargos
# =============================================================================
class TestCargos:
    @pytest.mark.asyncio
    async def test_crear_cargo(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'Test',
            'dependencia_id': None, 'estado': 'activo',
            'fecha_inicio_vigencia': date(2026, 1, 1), 'fecha_fin_vigencia': None,
        }
        r = await svc_cat.crear_cargo(
            conn, tenant_id=uuid4(), nombre='Test',
            dependencia_id=None, fecha_inicio_vigencia=None,
        )
        assert r['nombre'] == 'Test'

    @pytest.mark.asyncio
    async def test_listar_cargos_con_todos_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_cargos(
            conn, tenant_id=uuid4(),
            dependencia_id=uuid4(), estado='activo',
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_cargos_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_cargos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_patch_cargo_sin_cambios_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'X',
            'dependencia_id': None, 'estado': 'activo',
            'fecha_inicio_vigencia': date(2026, 1, 1), 'fecha_fin_vigencia': None,
        }
        r = await svc_cat.patch_cargo(
            conn, tenant_id=uuid4(), cargo_id=uuid4(), cambios={},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_cargo_sin_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_cat.patch_cargo(
            conn, tenant_id=uuid4(), cargo_id=uuid4(), cambios={},
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_cargo_con_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'Nuevo',
            'dependencia_id': None, 'estado': 'activo',
            'fecha_inicio_vigencia': date(2026, 1, 1), 'fecha_fin_vigencia': None,
        }
        r = await svc_cat.patch_cargo(
            conn, tenant_id=uuid4(), cargo_id=uuid4(),
            cambios={'nombre': 'Nuevo'},
        )
        assert r['nombre'] == 'Nuevo'

    @pytest.mark.asyncio
    async def test_patch_cargo_con_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_cat.patch_cargo(
            conn, tenant_id=uuid4(), cargo_id=uuid4(),
            cambios={'nombre': 'Nuevo'},
        )
        assert r is None


# =============================================================================
# Canales
# =============================================================================
class TestCanales:
    @pytest.mark.asyncio
    async def test_crear_canal(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'codigo': 'P', 'nombre': 'Presencial',
            'descripcion': None, 'requiere_punto_atencion': True,
            'requiere_digitalizacion': False, 'permite_acuse': True, 'estado': 'activo',
        }
        r = await svc_cat.crear_canal(
            conn, tenant_id=uuid4(),
            datos={'codigo': 'P', 'nombre': 'Presencial', 'requiere_punto_atencion': True},
        )
        assert r['codigo'] == 'P'

    @pytest.mark.asyncio
    async def test_listar_canales_con_estado(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_canales(conn, tenant_id=uuid4(), estado='activo')
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_canales_sin_estado(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_canales(conn, tenant_id=uuid4())
        assert r == []


# =============================================================================
# Calendarios
# =============================================================================
class TestCalendarios:
    @pytest.mark.asyncio
    async def test_crear_calendario_con_festivos_date_objects(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'Cal',
            'vigencia_anual': 2026,
            'festivos': json.dumps(['2026-01-01']),
            'dias_no_laborales': [0, 6], 'es_default': True, 'estado': 'activo',
        }
        r = await svc_cat.crear_calendario(
            conn, tenant_id=uuid4(),
            datos={
                'nombre': 'Cal', 'vigencia_anual': 2026,
                'festivos': [date(2026, 1, 1)],
                'es_default': True,
            },
        )
        assert r['nombre'] == 'Cal'
        assert r['festivos'] == [date(2026, 1, 1)]

    @pytest.mark.asyncio
    async def test_crear_calendario_con_defaults(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'Cal',
            'vigencia_anual': 2026, 'festivos': None,
            'dias_no_laborales': None, 'es_default': False, 'estado': 'activo',
        }
        r = await svc_cat.crear_calendario(
            conn, tenant_id=uuid4(),
            datos={'nombre': 'Cal', 'vigencia_anual': 2026},
        )
        assert r['dias_no_laborales'] == []

    @pytest.mark.asyncio
    async def test_listar_calendarios_con_festivos_jsonb_dict(self) -> None:
        """Cuando asyncpg devuelve jsonb ya parseado como list."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tenant_id': uuid4(), 'nombre': 'Cal',
                'vigencia_anual': 2026, 'festivos': ['2026-12-25'],
                'dias_no_laborales': [0, 6], 'es_default': False, 'estado': 'activo',
            }
        ]
        r = await svc_cat.listar_calendarios(conn, tenant_id=uuid4())
        assert len(r) == 1
        assert r[0]['festivos'] == [date(2026, 12, 25)]

    @pytest.mark.asyncio
    async def test_calendario_default_id_existe(self) -> None:
        conn = AsyncMock()
        cal_id = uuid4()
        conn.fetchrow.return_value = {'id': cal_id}
        r = await svc_cat.calendario_default_id(conn, tenant_id=uuid4())
        assert r == cal_id

    @pytest.mark.asyncio
    async def test_calendario_default_id_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_cat.calendario_default_id(conn, tenant_id=uuid4())
        assert r is None

    @pytest.mark.asyncio
    async def test_calcular_fecha_limite(self) -> None:
        conn = AsyncMock()
        fecha_esperada = datetime(2026, 6, 15, 10, 0)
        conn.fetchrow.return_value = {'fecha_limite': fecha_esperada}
        r = await svc_cat.calcular_fecha_limite(
            conn, tenant_id=uuid4(),
            fecha_base=datetime(2026, 6, 1, 10, 0),
            termino_dias=10, tipo_dias='habiles',
        )
        assert r == fecha_esperada


# =============================================================================
# Tipos PQRSD + correspondencia
# =============================================================================
class TestTiposPqrsdYCorresp:
    @pytest.mark.asyncio
    async def test_crear_tipo_pqrsd(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo': 'peticion', 'nombre': 'Petición', 'descripcion': None,
            'termino_dias': 15, 'tipo_dias': 'habiles',
            'requiere_respuesta': True, 'estado': 'activo',
        }
        r = await svc_cat.crear_tipo_pqrsd(
            conn, tenant_id=uuid4(),
            datos={'codigo': 'peticion', 'nombre': 'Petición',
                   'termino_dias': 15, 'tipo_dias': 'habiles'},
        )
        assert r['codigo'] == 'peticion'

    @pytest.mark.asyncio
    async def test_listar_tipos_pqrsd_sin_filtro(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_tipos_pqrsd(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_tipos_pqrsd_con_estado(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_tipos_pqrsd(conn, tenant_id=uuid4(), estado='activo')
        assert r == []

    @pytest.mark.asyncio
    async def test_crear_tipo_correspondencia(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo': 'oficio', 'nombre': 'Oficio', 'descripcion': None,
            'ambito': 'externa_enviada', 'estado': 'activo',
        }
        r = await svc_cat.crear_tipo_correspondencia(
            conn, tenant_id=uuid4(),
            datos={'codigo': 'oficio', 'nombre': 'Oficio', 'ambito': 'externa_enviada'},
        )
        assert r['ambito'] == 'externa_enviada'

    @pytest.mark.asyncio
    async def test_listar_tipos_corresp_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_tipos_correspondencia(
            conn, tenant_id=uuid4(), ambito='interna', estado='activo',
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_tipos_corresp_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_tipos_correspondencia(conn, tenant_id=uuid4())
        assert r == []


# =============================================================================
# Reglas comunicación
# =============================================================================
class TestReglasComunicacion:
    @pytest.mark.asyncio
    async def test_crear_regla(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'dependencia_origen_id': uuid4(), 'dependencia_destino_id': uuid4(),
            'permitido': False, 'requiere_aprobacion_jefe': True,
            'motivo_restriccion': 'Conflicto de interés', 'estado': 'activa',
        }
        r = await svc_cat.crear_regla_comunicacion(
            conn, tenant_id=uuid4(),
            datos={
                'dependencia_origen_id': uuid4(),
                'dependencia_destino_id': uuid4(),
                'permitido': False, 'requiere_aprobacion_jefe': True,
                'motivo_restriccion': 'Conflicto de interés',
            },
            created_by_user_id=uuid4(),
        )
        assert r['permitido'] is False

    @pytest.mark.asyncio
    async def test_listar_reglas_con_origen(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_reglas_comunicacion(
            conn, tenant_id=uuid4(), dependencia_origen_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_reglas_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_cat.listar_reglas_comunicacion(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_validar_misma_dependencia(self) -> None:
        conn = AsyncMock()
        dep = uuid4()
        r = await svc_cat.validar_comunicacion(
            conn, tenant_id=uuid4(), origen=dep, destino=dep,
        )
        assert r['permitido'] is True
        assert r['motivo'] == 'misma dependencia'
        assert r['tiene_regla_explicita'] is False

    @pytest.mark.asyncio
    async def test_validar_sin_regla_default_permisivo(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc_cat.validar_comunicacion(
            conn, tenant_id=uuid4(), origen=uuid4(), destino=uuid4(),
        )
        assert r['permitido'] is True
        assert r['tiene_regla_explicita'] is False

    @pytest.mark.asyncio
    async def test_validar_con_regla_explicita_prohibida(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'permitido': False,
            'requiere_aprobacion_jefe': True,
            'motivo_restriccion': 'X',
        }
        r = await svc_cat.validar_comunicacion(
            conn, tenant_id=uuid4(), origen=uuid4(), destino=uuid4(),
        )
        assert r['permitido'] is False
        assert r['motivo'] == 'X'
        assert r['tiene_regla_explicita'] is True


# =============================================================================
# Parámetros
# =============================================================================
class TestParametros:
    @pytest.mark.asyncio
    async def test_listar_vigentes(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'clave': 'gd.archivo.tamano_max',
                'valor': '20971520', 'tipo': 'integer', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            }
        ]
        r = await svc_par.listar_parametros_vigentes(conn, tenant_id=uuid4())
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_obtener_parametro_existe(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'clave': 'gd.x', 'valor': 'v2',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            },
            {
                'id': uuid4(), 'clave': 'gd.x', 'valor': 'v1',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': datetime.now(),
                'estado': 'reemplazado',
            },
        ]
        r = await svc_par.obtener_parametro(conn, tenant_id=uuid4(), clave='gd.x')
        assert r is not None
        assert r['vigente']['valor'] == 'v2'
        assert len(r['historial']) == 2

    @pytest.mark.asyncio
    async def test_obtener_parametro_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_par.obtener_parametro(
            conn, tenant_id=uuid4(), clave='inexistente',
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_upsert_parametros_sin_cambios_reusa(self) -> None:
        conn = AsyncMock()
        param_id = uuid4()
        conn.fetchrow.side_effect = [
            # Buscar activo actual
            {'id': param_id, 'valor': 'v1', 'tipo': 'string', 'descripcion': None},
            # Re-leer fila completa (sin crear nueva)
            {
                'id': param_id, 'clave': 'gd.x', 'valor': 'v1',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            },
        ]
        r = await svc_par.upsert_parametros(
            conn, tenant_id=uuid4(),
            parametros=[{'clave': 'gd.x', 'valor': 'v1', 'tipo': 'string',
                         'motivo': 'Sin cambio test'}],
        )
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_upsert_parametros_cambia_versiona(self) -> None:
        conn = AsyncMock()
        param_id_viejo = uuid4()
        param_id_nuevo = uuid4()
        conn.fetchrow.side_effect = [
            # Buscar activo actual
            {'id': param_id_viejo, 'valor': 'v1', 'tipo': 'string', 'descripcion': None},
            # INSERT nueva fila
            {
                'id': param_id_nuevo, 'clave': 'gd.x', 'valor': 'v2',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            },
        ]
        conn.execute.return_value = 'UPDATE 1'
        r = await svc_par.upsert_parametros(
            conn, tenant_id=uuid4(),
            parametros=[{'clave': 'gd.x', 'valor': 'v2', 'tipo': 'string',
                         'motivo': 'Cambio test'}],
        )
        assert len(r) == 1
        assert r[0]['valor'] == 'v2'
        conn.execute.assert_awaited_once()  # marcó anterior como reemplazado

    @pytest.mark.asyncio
    async def test_upsert_primera_vez(self) -> None:
        """No existe el parámetro → crea fila nueva sin marcar nada como reemplazado."""
        conn = AsyncMock()
        param_id = uuid4()
        conn.fetchrow.side_effect = [
            None,  # no hay activo previo
            {
                'id': param_id, 'clave': 'gd.x', 'valor': 'v1',
                'tipo': 'string', 'descripcion': None,
                'vigente_desde': datetime.now(), 'vigente_hasta': None,
                'estado': 'activo',
            },
        ]
        r = await svc_par.upsert_parametros(
            conn, tenant_id=uuid4(),
            parametros=[{'clave': 'gd.x', 'valor': 'v1', 'tipo': 'string',
                         'motivo': 'Primera vez'}],
        )
        assert len(r) == 1
        conn.execute.assert_not_awaited()  # NO marca nada (no había previo)


# =============================================================================
# Consecutivos
# =============================================================================
class TestConsecutivos:
    @pytest.mark.asyncio
    async def test_listar_con_vigencia(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_con.listar_consecutivos(
            conn, tenant_id=uuid4(), vigencia=2026,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_sin_vigencia(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc_con.listar_consecutivos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_siguiente_radicado(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'numero_radicado': 'RAD-2026-000123'}
        r = await svc_con.siguiente_radicado(
            conn, tenant_id=uuid4(), vigencia=2026, tipo_radicado='entrada',
        )
        assert r == 'RAD-2026-000123'

    @pytest.mark.asyncio
    async def test_siguiente_radicado_null_lanza(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(RuntimeError):
            await svc_con.siguiente_radicado(
                conn, tenant_id=uuid4(), vigencia=2026, tipo_radicado='entrada',
            )
