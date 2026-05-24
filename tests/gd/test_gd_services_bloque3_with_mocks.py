"""Tests con mocks para los services del bloque 3.

Cubre:
- app/gd/services/organizacion.py
- app/gd/services/dependencias.py
- app/gd/services/snapshots.py
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import dependencias as svc_dep
from app.gd.services import organizacion as svc_org
from app.gd.services import snapshots as svc_snap


# =============================================================================
# organizacion
# =============================================================================
class TestOrganizacionServices:
    @pytest.mark.asyncio
    async def test_obtener_perfil_existe(self) -> None:
        conn = AsyncMock()
        tenant_id = uuid4()
        conn.fetchrow.return_value = {
            'tenant_id': tenant_id, 'tipo_organizacion': 'publica',
            'identificacion_fiscal': '900123456-7', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'Alcaldía X', 'nombre_corto': 'X',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': None,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        result = await svc_org.obtener_perfil_organizacion(conn, tenant_id=tenant_id)
        assert result is not None
        assert result['tipo_organizacion'] == 'publica'

    @pytest.mark.asyncio
    async def test_obtener_perfil_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_org.obtener_perfil_organizacion(conn, tenant_id=uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_crear_perfil_con_defaults(self) -> None:
        conn = AsyncMock()
        tenant_id = uuid4()
        conn.fetchrow.return_value = {
            'tenant_id': tenant_id, 'tipo_organizacion': 'privada',
            'identificacion_fiscal': '111', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'Empresa Test', 'nombre_corto': 'Test',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': None,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        result = await svc_org.crear_perfil_organizacion(
            conn,
            tenant_id=tenant_id,
            datos={
                'tipo_organizacion': 'privada',
                'identificacion_fiscal': '111',
                'razon_social_legal': 'Empresa Test',
                'nombre_corto': 'Test',
            },
            created_by_user_id=uuid4(),
        )
        assert result['tipo_organizacion'] == 'privada'

    @pytest.mark.asyncio
    async def test_actualizar_perfil_sin_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'tipo_organizacion': 'publica',
            'identificacion_fiscal': '900', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'X', 'nombre_corto': 'X',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': None,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        result = await svc_org.actualizar_perfil_organizacion(
            conn, tenant_id=uuid4(), cambios={}
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_actualizar_perfil_con_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'tipo_organizacion': 'publica',
            'identificacion_fiscal': '900', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'Nuevo Nombre', 'nombre_corto': 'X',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': None,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        result = await svc_org.actualizar_perfil_organizacion(
            conn, tenant_id=uuid4(),
            cambios={'razon_social_legal': 'Nuevo Nombre'},
        )
        assert result['razon_social_legal'] == 'Nuevo Nombre'

    @pytest.mark.asyncio
    async def test_actualizar_perfil_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_org.actualizar_perfil_organizacion(
            conn, tenant_id=uuid4(), cambios={'nombre_corto': 'Y'}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_aplicar_defaults_modulos(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'count': 5}
        result = await svc_org.aplicar_defaults_modulos(conn, tenant_id=uuid4())
        assert result == 5

    @pytest.mark.asyncio
    async def test_aplicar_defaults_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_org.aplicar_defaults_modulos(conn, tenant_id=uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_listar_modulos_combina_existentes_y_faltantes(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'modulo_codigo': 'pqrsd_legal', 'activado': True, 'configuracion': None},
            {'modulo_codigo': 'firma_electronica', 'activado': True, 'configuracion': {'x': 1}},
        ]
        result = await svc_org.listar_modulos(conn, tenant_id=uuid4())
        # Deben ser exactamente 14 (canónico).
        assert len(result) == 14
        # Los 2 existentes vienen activados, los otros 12 vienen como False.
        activados = [r for r in result if r['activado']]
        assert len(activados) == 2

    @pytest.mark.asyncio
    async def test_upsert_modulos_vacio(self) -> None:
        conn = AsyncMock()
        result = await svc_org.upsert_modulos(conn, tenant_id=uuid4(), cambios=[])
        assert result == 0
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upsert_modulos_cuenta_afectados(self) -> None:
        conn = AsyncMock()
        conn.execute.side_effect = ['INSERT 0 1', 'INSERT 0 1', 'INSERT 0 0']
        result = await svc_org.upsert_modulos(
            conn, tenant_id=uuid4(),
            cambios=[
                {'modulo_codigo': 'pqrsd_legal', 'activado': True, 'configuracion': None},
                {'modulo_codigo': 'firma_electronica', 'activado': True, 'configuracion': None},
                {'modulo_codigo': 'expedientes', 'activado': False, 'configuracion': None},
            ],
        )
        assert result == 2  # 2 afectados, 1 con 0 filas


# =============================================================================
# dependencias
# =============================================================================
class TestDependenciasServices:
    @pytest.mark.asyncio
    async def test_crear_version_sin_vigente_previa(self) -> None:
        conn = AsyncMock()
        version_id = uuid4()
        conn.fetchrow.side_effect = [
            None,  # no hay vigente
            {
                'id': version_id, 'tenant_id': uuid4(),
                'numero_version': 'v1.0', 'descripcion': None,
                'acto_administrativo': None,
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None, 'estado': 'borrador',
            },
        ]
        result = await svc_dep.crear_version_estructura(
            conn, tenant_id=uuid4(),
            numero_version='v1.0', descripcion=None, acto_administrativo=None,
            fecha_inicio_vigencia=date(2026, 1, 1), created_by_user_id=uuid4(),
        )
        assert result['id'] == version_id
        assert result['dependencias_clonadas'] == 0

    @pytest.mark.asyncio
    async def test_crear_version_clona_dependencias_vigentes(self) -> None:
        conn = AsyncMock()
        vigente_id = uuid4()
        nueva_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': vigente_id},  # vigente actual
            {
                'id': nueva_id, 'tenant_id': uuid4(),
                'numero_version': 'v2.0', 'descripcion': 'X',
                'acto_administrativo': 'Decreto 123',
                'fecha_inicio_vigencia': date(2026, 7, 1),
                'fecha_fin_vigencia': None, 'estado': 'borrador',
            },
        ]
        conn.fetch.return_value = [{'id': uuid4()}, {'id': uuid4()}, {'id': uuid4()}]
        result = await svc_dep.crear_version_estructura(
            conn, tenant_id=uuid4(),
            numero_version='v2.0', descripcion='X', acto_administrativo='Decreto 123',
            fecha_inicio_vigencia=date(2026, 7, 1), created_by_user_id=uuid4(),
        )
        assert result['dependencias_clonadas'] == 3

    @pytest.mark.asyncio
    async def test_obtener_version_vigente_existe(self) -> None:
        conn = AsyncMock()
        version_id = uuid4()
        conn.fetchrow.return_value = {
            'version_estructura_id': version_id,
            'numero_version': 'v1.0',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'dependencias_count': 47,
        }
        result = await svc_dep.obtener_version_vigente(conn, tenant_id=uuid4())
        assert result is not None
        assert result['dependencias_count'] == 47

    @pytest.mark.asyncio
    async def test_obtener_version_vigente_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_dep.obtener_version_vigente(conn, tenant_id=uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_obtener_version_en_fecha(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'version_estructura_id': uuid4(), 'numero_version': 'v0.9',
            'fecha_inicio_vigencia': date(2024, 1, 1), 'dependencias_count': 30,
        }
        result = await svc_dep.obtener_version_en_fecha(
            conn, tenant_id=uuid4(), fecha=date(2024, 6, 15)
        )
        assert result is not None
        assert result['numero_version'] == 'v0.9'

    @pytest.mark.asyncio
    async def test_obtener_version_en_fecha_sin_resultado(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_dep.obtener_version_en_fecha(
            conn, tenant_id=uuid4(), fecha=date(2020, 1, 1)
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_crear_dependencia(self) -> None:
        conn = AsyncMock()
        dep_id = uuid4()
        conn.fetchrow.return_value = {
            'id': dep_id, 'tenant_id': uuid4(),
            'codigo_organico': 'JUR-001', 'nombre': 'Oficina Jurídica',
            'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
            'estado': 'activa',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'fecha_fin_vigencia': None,
        }
        result = await svc_dep.crear_dependencia(
            conn, tenant_id=uuid4(), codigo_organico='JUR-001',
            nombre='Oficina Jurídica', dependencia_padre_id=None,
            version_estructura_id=uuid4(), fecha_inicio_vigencia=date(2026, 1, 1),
            created_by_user_id=uuid4(),
        )
        assert result['id'] == dep_id

    @pytest.mark.asyncio
    async def test_listar_dependencias_con_todos_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await svc_dep.listar_dependencias(
            conn, tenant_id=uuid4(),
            estado='activa', version_estructura_id=uuid4(), q='Jur',
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_listar_dependencias_default_vigente(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tenant_id': uuid4(),
                'codigo_organico': 'X', 'nombre': 'X',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            }
        ]
        result = await svc_dep.listar_dependencias(conn, tenant_id=uuid4())
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_patch_dependencia_sin_cambios_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo_organico': 'X', 'nombre': 'X',
            'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
            'estado': 'activa',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'fecha_fin_vigencia': None,
        }
        result = await svc_dep.patch_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(), cambios={}
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_patch_dependencia_sin_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_dep.patch_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(), cambios={}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_patch_dependencia_con_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo_organico': 'X', 'nombre': 'X Nuevo',
            'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
            'estado': 'activa',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'fecha_fin_vigencia': None,
        }
        result = await svc_dep.patch_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            cambios={'nombre': 'X Nuevo'},
        )
        assert result['nombre'] == 'X Nuevo'

    @pytest.mark.asyncio
    async def test_patch_dependencia_con_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_dep.patch_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            cambios={'nombre': 'X'},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_cerrar_vigencia_dependencia_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(),
            'codigo_organico': 'X', 'nombre': 'X',
            'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
            'estado': 'cerrada',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'fecha_fin_vigencia': date(2026, 6, 30),
        }
        result = await svc_dep.cerrar_vigencia_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            fecha_fin=date(2026, 6, 30), motivo='Reestructura',
        )
        assert result is not None
        assert result['estado'] == 'cerrada'

    @pytest.mark.asyncio
    async def test_cerrar_vigencia_dependencia_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_dep.cerrar_vigencia_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            fecha_fin=date(2026, 6, 30), motivo='X',
        )
        assert result is None

    def test_construir_jerarquia_raiz_unica(self) -> None:
        raiz_id = uuid4()
        hijo_id = uuid4()
        items = [
            {'id': raiz_id, 'codigo_organico': 'D', 'nombre': 'Despacho', 'dependencia_padre_id': None},
            {'id': hijo_id, 'codigo_organico': 'J', 'nombre': 'Jurídica', 'dependencia_padre_id': raiz_id},
        ]
        result = svc_dep.construir_jerarquia(items)
        assert len(result) == 1
        assert result[0]['codigo_organico'] == 'D'
        assert len(result[0]['hijos']) == 1
        assert result[0]['hijos'][0]['codigo_organico'] == 'J'

    def test_construir_jerarquia_huerfano_sube_a_raiz(self) -> None:
        """Si el padre no está en la lista, el item va a raíz (defensivo)."""
        items = [
            {'id': uuid4(), 'codigo_organico': 'X', 'nombre': 'X',
             'dependencia_padre_id': uuid4()},  # padre inexistente
        ]
        result = svc_dep.construir_jerarquia(items)
        assert len(result) == 1  # cae a raíz


# =============================================================================
# snapshots
# =============================================================================
class TestSnapshotsService:
    @pytest.mark.asyncio
    async def test_capturar_snapshot_devuelve_dict(self) -> None:
        conn = AsyncMock()
        snapshot = {
            'usuario_id': str(uuid4()), 'nombre_completo': 'Juan Pérez',
            'rol_codigo': None, 'dependencia_nombre': 'Jurídica',
        }
        conn.fetchrow.return_value = {'snapshot': snapshot}
        result = await svc_snap.capturar_snapshot(conn, user_id=uuid4())
        assert result['nombre_completo'] == 'Juan Pérez'

    @pytest.mark.asyncio
    async def test_capturar_snapshot_parsea_string_jsonb(self) -> None:
        """asyncpg con drivers viejos puede devolver jsonb como str."""
        conn = AsyncMock()
        import json
        snapshot_str = json.dumps({'nombre_completo': 'X'})
        conn.fetchrow.return_value = {'snapshot': snapshot_str}
        result = await svc_snap.capturar_snapshot(conn, user_id=uuid4())
        assert result['nombre_completo'] == 'X'

    @pytest.mark.asyncio
    async def test_capturar_snapshot_vacio_lanza(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(ValueError, match='snapshot vacío'):
            await svc_snap.capturar_snapshot(conn, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_capturar_snapshot_jsonb_null(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'snapshot': None}
        with pytest.raises(ValueError):
            await svc_snap.capturar_snapshot(conn, user_id=uuid4())
