"""Tests con mocks para los services SQL del bloque 2.

Cubre:
- app/gd/services/perfil_usuario.py
- app/gd/services/roles.py
- app/gd/services/asignaciones.py
- app/gd/services/politica_contrasena.py

Sin DB real — todos los queries asyncpg están mockeados.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import asignaciones as svc_asig
from app.gd.services import perfil_usuario as svc_perfil
from app.gd.services import politica_contrasena as svc_pol
from app.gd.services import roles as svc_roles


# =============================================================================
# perfil_usuario
# =============================================================================
class TestPerfilUsuarioServices:
    @pytest.mark.asyncio
    async def test_crear_perfil_devuelve_dict(self) -> None:
        conn = AsyncMock()
        perfil_id = uuid4()
        tenant_id = uuid4()
        user_id = uuid4()
        conn.fetchrow.return_value = {
            'perfil_id': perfil_id, 'tenant_id': tenant_id, 'user_id': user_id,
            'tipo_vinculacion': 'planta', 'estado_gd': 'activo',
            'fecha_inicio_vinculacion': date(2026, 1, 1), 'fecha_fin_vinculacion': None,
            'dependencia_actual_id': None, 'cargo_actual_id': None, 'ultimo_acceso': None,
            'created_at': datetime.now(), 'created_by_user_id': None,
        }
        result = await svc_perfil.crear_perfil(
            conn, tenant_id=tenant_id, user_id=user_id,
            tipo_vinculacion='planta', fecha_inicio_vinculacion=date(2026, 1, 1),
            fecha_fin_vinculacion=None, dependencia_actual_id=uuid4(),
            cargo_actual_id=None, created_by_user_id=None,
        )
        assert result['perfil_id'] == perfil_id
        conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_actualizar_perfil_sin_cambios_solo_lee(self) -> None:
        conn = AsyncMock()
        # Cuando cambios={}, hace SELECT.
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': uuid4(), 'user_id': uuid4(),
            'tipo_vinculacion': 'planta', 'estado_gd': 'activo',
            'fecha_inicio_vinculacion': date(2026, 1, 1), 'fecha_fin_vinculacion': None,
            'dependencia_actual_id': None, 'cargo_actual_id': None, 'ultimo_acceso': None,
            'created_at': datetime.now(), 'created_by_user_id': None,
        }
        result = await svc_perfil.actualizar_perfil(
            conn, tenant_id=uuid4(), user_id=uuid4(), cambios={}
        )
        assert result is not None
        assert result['tipo_vinculacion'] == 'planta'

    @pytest.mark.asyncio
    async def test_actualizar_perfil_sin_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_perfil.actualizar_perfil(
            conn, tenant_id=uuid4(), user_id=uuid4(), cambios={}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_actualizar_perfil_con_cambios_hace_update(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'perfil_id': uuid4(), 'tenant_id': uuid4(), 'user_id': uuid4(),
            'tipo_vinculacion': 'ops', 'estado_gd': 'activo',
            'fecha_inicio_vinculacion': date(2026, 1, 1), 'fecha_fin_vinculacion': date(2026, 12, 31),
            'dependencia_actual_id': None, 'cargo_actual_id': None, 'ultimo_acceso': None,
            'created_at': datetime.now(), 'created_by_user_id': None,
        }
        result = await svc_perfil.actualizar_perfil(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            cambios={'tipo_vinculacion': 'ops', 'fecha_fin_vinculacion': date(2026, 12, 31)},
        )
        assert result['tipo_vinculacion'] == 'ops'
        # Verifica que se llamó con UPDATE.
        sql = conn.fetchrow.call_args.args[0]
        assert 'update gd.perfil_usuario' in sql.lower()

    @pytest.mark.asyncio
    async def test_actualizar_perfil_con_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_perfil.actualizar_perfil(
            conn, tenant_id=uuid4(), user_id=uuid4(), cambios={'tipo_vinculacion': 'ops'}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_cambiar_estado_accion_invalida(self) -> None:
        conn = AsyncMock()
        with pytest.raises(ValueError, match='accion inválida'):
            await svc_perfil.cambiar_estado(
                conn, tenant_id=uuid4(), user_id=uuid4(), accion='comer'
            )

    @pytest.mark.asyncio
    async def test_cambiar_estado_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado_anterior': 'activo', 'estado_nuevo': 'inactivo'}
        result = await svc_perfil.cambiar_estado(
            conn, tenant_id=uuid4(), user_id=uuid4(), accion='inactivar'
        )
        assert result == ('activo', 'inactivo')

    @pytest.mark.asyncio
    async def test_cambiar_estado_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_perfil.cambiar_estado(
            conn, tenant_id=uuid4(), user_id=uuid4(), accion='inactivar'
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_listar_perfiles_con_todos_los_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'user_id': uuid4(), 'email': 'x@y.com', 'display_name': 'Juan Pérez',
                'tipo_vinculacion': 'planta', 'estado_gd': 'activo',
                'dependencia_actual_id': uuid4(), 'cargo_actual_id': None,
                'roles_gd_count': 2, 'ultimo_acceso': None,
            }
        ]
        result = await svc_perfil.listar_perfiles(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
            estado_gd=['activo'], tipo_vinculacion=['planta'], q='Juan', limit=10,
        )
        assert len(result) == 1
        assert result[0]['email'] == 'x@y.com'

    @pytest.mark.asyncio
    async def test_listar_perfiles_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await svc_perfil.listar_perfiles(conn, tenant_id=uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_contar_perfiles(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 42}
        result = await svc_perfil.contar_perfiles(conn, tenant_id=uuid4())
        assert result == 42

    @pytest.mark.asyncio
    async def test_contar_perfiles_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_perfil.contar_perfiles(conn, tenant_id=uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_obtener_historial(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'evento_auditoria_id': uuid4(), 'tipo_evento': 'gd.perfil_usuario.creado',
                'accion': 'crear', 'valor_anterior': None, 'valor_nuevo': {'x': 1},
                'ejecutado_por_user_id': uuid4(), 'ejecutado_por_nombre': 'Ana',
                'motivo': None, 'fecha': datetime.now(),
            }
        ]
        result = await svc_perfil.obtener_historial(
            conn, tenant_id=uuid4(), user_id=uuid4()
        )
        assert len(result) == 1
        assert result[0]['tipo_evento'] == 'gd.perfil_usuario.creado'


# =============================================================================
# roles
# =============================================================================
class TestRolesServices:
    @pytest.mark.asyncio
    async def test_crear_rol_devuelve_dict(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'codigo': 'gd.custom', 'nombre': 'Custom', 'descripcion': 'x',
            'es_sistema': False, 'estado': 'activo',
        }
        result = await svc_roles.crear_rol(
            conn, codigo='gd.custom', nombre='Custom', descripcion='x'
        )
        assert result is not None
        assert result['permisos_count'] == 0

    @pytest.mark.asyncio
    async def test_crear_rol_ya_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.crear_rol(
            conn, codigo='gd.profesional', nombre='X', descripcion=None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_listar_roles_con_filtro_estado(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
             'es_sistema': True, 'estado': 'activo', 'permisos_count': 5},
        ]
        result = await svc_roles.listar_roles(conn, estado='activo')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_listar_roles_sin_filtro(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await svc_roles.listar_roles(conn)
        assert result == []

    @pytest.mark.asyncio
    async def test_obtener_rol_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
            'es_sistema': True, 'estado': 'activo', 'permisos_count': 3,
        }
        result = await svc_roles.obtener_rol(conn, codigo='gd.x')
        assert result is not None

    @pytest.mark.asyncio
    async def test_obtener_rol_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.obtener_rol(conn, codigo='gd.inexistente')
        assert result is None

    @pytest.mark.asyncio
    async def test_actualizar_rol_sin_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
            'es_sistema': True, 'estado': 'activo', 'permisos_count': 0,
        }
        result = await svc_roles.actualizar_rol(conn, codigo='gd.x', cambios={})
        assert result is not None

    @pytest.mark.asyncio
    async def test_actualizar_rol_con_cambios(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'codigo': 'gd.x', 'nombre': 'X-nuevo', 'descripcion': None,
             'es_sistema': True, 'estado': 'activo'},
            {'c': 7},
        ]
        result = await svc_roles.actualizar_rol(
            conn, codigo='gd.x', cambios={'nombre': 'X-nuevo'}
        )
        assert result['nombre'] == 'X-nuevo'
        assert result['permisos_count'] == 7

    @pytest.mark.asyncio
    async def test_actualizar_rol_con_cambios_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.actualizar_rol(
            conn, codigo='gd.x', cambios={'nombre': 'Y'}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_contar_asignaciones_activas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'c': 5}
        result = await svc_roles.contar_asignaciones_activas(conn, rol_codigo='gd.x')
        assert result == 5

    @pytest.mark.asyncio
    async def test_contar_asignaciones_activas_sin_filas(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.contar_asignaciones_activas(conn, rol_codigo='gd.x')
        assert result == 0

    @pytest.mark.asyncio
    async def test_inactivar_rol_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'codigo': 'gd.x', 'nombre': 'X', 'descripcion': None,
            'es_sistema': False, 'estado': 'inactivo',
        }
        result = await svc_roles.inactivar_rol(conn, codigo='gd.x')
        assert result is not None
        assert result['estado'] == 'inactivo'

    @pytest.mark.asyncio
    async def test_inactivar_rol_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.inactivar_rol(conn, codigo='gd.x')
        assert result is None

    @pytest.mark.asyncio
    async def test_agregar_permiso_a_rol_ok(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'rol_codigo': 'gd.x', 'permiso_codigo': 'PERM-A',
            'alcance_default': 'dependencia', 'agregado_en': datetime.now(),
        }
        result = await svc_roles.agregar_permiso_a_rol(
            conn, rol_codigo='gd.x', permiso_codigo='PERM-A', alcance_default='dependencia'
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_agregar_permiso_ya_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_roles.agregar_permiso_a_rol(
            conn, rol_codigo='gd.x', permiso_codigo='PERM-A', alcance_default='dependencia'
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_quitar_permiso_devuelve_true(self) -> None:
        conn = AsyncMock()
        conn.execute.return_value = 'DELETE 1'
        result = await svc_roles.quitar_permiso_de_rol(
            conn, rol_codigo='gd.x', permiso_codigo='PERM-A'
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_quitar_permiso_devuelve_false_si_nada(self) -> None:
        conn = AsyncMock()
        conn.execute.return_value = 'DELETE 0'
        result = await svc_roles.quitar_permiso_de_rol(
            conn, rol_codigo='gd.x', permiso_codigo='PERM-A'
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_listar_permisos_con_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'codigo': 'PERM-A', 'nombre': 'A', 'modulo': 'pqrsd',
             'descripcion': None, 'es_critico': False, 'estado': 'activo'},
        ]
        result = await svc_roles.listar_permisos(conn, modulo='pqrsd', estado='activo')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_listar_permisos_sin_filtros(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await svc_roles.listar_permisos(conn)
        assert result == []


# =============================================================================
# asignaciones
# =============================================================================
class TestAsignacionesServices:
    @pytest.mark.asyncio
    async def test_asignar_rol(self) -> None:
        conn = AsyncMock()
        asign_id = uuid4()
        conn.fetchrow.return_value = {
            'asignacion_alcance_id': asign_id, 'user_id': uuid4(),
            'rol_codigo': 'gd.x', 'dependencia_id': uuid4(),
            'alcance': 'dependencia', 'fecha_inicio': date(2026, 1, 1),
            'fecha_fin': None, 'estado': 'activa',
            'asignado_por_user_id': uuid4(), 'motivo': 'X',
        }
        result = await svc_asig.asignar_rol(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            rol_codigo='gd.x', dependencia_id=uuid4(), alcance='dependencia',
            fecha_inicio=date(2026, 1, 1), fecha_fin=None, motivo='X',
            asignado_por_user_id=uuid4(),
        )
        assert result['asignacion_alcance_id'] == asign_id

    @pytest.mark.asyncio
    async def test_cerrar_asignacion_ok(self) -> None:
        conn = AsyncMock()
        asign_id = uuid4()
        conn.fetchrow.return_value = {
            'asignacion_alcance_id': asign_id, 'fecha_fin': datetime.now(), 'estado': 'cerrada',
        }
        result = await svc_asig.cerrar_asignacion(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            asignacion_alcance_id=asign_id, motivo='X', cerrado_por_user_id=uuid4(),
        )
        assert result is not None
        assert result['estado'] == 'cerrada'

    @pytest.mark.asyncio
    async def test_cerrar_asignacion_no_existe(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_asig.cerrar_asignacion(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            asignacion_alcance_id=uuid4(), motivo='X', cerrado_por_user_id=uuid4(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_listar_roles_usuario_separa_vigentes_e_historicas(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'asignacion_alcance_id': uuid4(), 'user_id': uuid4(),
                'rol_codigo': 'gd.x', 'rol_nombre': 'X',
                'dependencia_id': None, 'alcance': 'institucional',
                'fecha_inicio': date(2026, 1, 1), 'fecha_fin': None, 'estado': 'activa',
                'asignado_por_user_id': uuid4(), 'motivo': 'X', 'vigente': True,
            },
            {
                'asignacion_alcance_id': uuid4(), 'user_id': uuid4(),
                'rol_codigo': 'gd.y', 'rol_nombre': 'Y',
                'dependencia_id': None, 'alcance': 'propio',
                'fecha_inicio': date(2025, 1, 1), 'fecha_fin': date(2025, 12, 31),
                'estado': 'cerrada', 'asignado_por_user_id': uuid4(), 'motivo': 'X',
                'vigente': False,
            },
        ]
        result = await svc_asig.listar_roles_usuario(
            conn, tenant_id=uuid4(), user_id=uuid4(), incluir_historicas=True
        )
        assert len(result['vigentes']) == 1
        assert len(result['historicas']) == 1

    @pytest.mark.asyncio
    async def test_listar_roles_usuario_excluye_historicas_por_default(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                'asignacion_alcance_id': uuid4(), 'user_id': uuid4(),
                'rol_codigo': 'gd.y', 'rol_nombre': 'Y',
                'dependencia_id': None, 'alcance': 'propio',
                'fecha_inicio': date(2025, 1, 1), 'fecha_fin': date(2025, 12, 31),
                'estado': 'cerrada', 'asignado_por_user_id': uuid4(), 'motivo': 'X',
                'vigente': False,
            },
        ]
        result = await svc_asig.listar_roles_usuario(
            conn, tenant_id=uuid4(), user_id=uuid4(), incluir_historicas=False
        )
        assert result['vigentes'] == []
        assert result['historicas'] == []


# =============================================================================
# politica_contrasena
# =============================================================================
class TestPoliticaContrasenaServices:
    @pytest.mark.asyncio
    async def test_obtener_politica_devuelve_fila_tenant(self) -> None:
        conn = AsyncMock()
        tenant_id = uuid4()
        conn.fetchrow.return_value = {
            'longitud_minima': 14, 'complejidad_regex': '.*',
            'historial_no_reuso': 5, 'vigencia_dias': 60,
            'intentos_fallidos_max': 3, 'cooldown_segundos': 60,
            'vigente_desde': datetime.now(), 'tenant_id': tenant_id,
        }
        result = await svc_pol.obtener_politica_vigente(conn, tenant_id=tenant_id)
        assert result['longitud_minima'] == 14
        assert result['es_global'] is False

    @pytest.mark.asyncio
    async def test_obtener_politica_devuelve_global_default_si_vacio(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await svc_pol.obtener_politica_vigente(conn, tenant_id=uuid4())
        assert result['es_global'] is True
        assert result['longitud_minima'] == 12  # default

    @pytest.mark.asyncio
    async def test_obtener_politica_marca_global_correctamente(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'longitud_minima': 12, 'complejidad_regex': '.*',
            'historial_no_reuso': 12, 'vigencia_dias': 90,
            'intentos_fallidos_max': 5, 'cooldown_segundos': 300,
            'vigente_desde': datetime.now(), 'tenant_id': None,
        }
        result = await svc_pol.obtener_politica_vigente(conn, tenant_id=uuid4())
        assert result['es_global'] is True

    @pytest.mark.asyncio
    async def test_actualizar_politica_crea_fila_nueva(self) -> None:
        conn = AsyncMock()
        tenant_id = uuid4()
        # obtener_politica_vigente call inicial:
        conn.fetchrow.side_effect = [
            {
                'longitud_minima': 12, 'complejidad_regex': '.*',
                'historial_no_reuso': 12, 'vigencia_dias': 90,
                'intentos_fallidos_max': 5, 'cooldown_segundos': 300,
                'vigente_desde': datetime.now(), 'tenant_id': tenant_id,
            },
            # INSERT RETURNING
            {
                'longitud_minima': 16, 'complejidad_regex': '.*',
                'historial_no_reuso': 12, 'vigencia_dias': 90,
                'intentos_fallidos_max': 5, 'cooldown_segundos': 300,
                'vigente_desde': datetime.now(),
            },
        ]
        result = await svc_pol.actualizar_politica(
            conn, tenant_id=tenant_id, cambios={'longitud_minima': 16},
            actualizado_por_user_id=uuid4(),
        )
        assert result['longitud_minima'] == 16
        assert result['es_global'] is False

    def test_validar_contrasena_corta(self) -> None:
        errores = svc_pol.validar_contrasena_contra_politica(
            contrasena='abc', longitud_minima=8, complejidad_regex='.*'
        )
        assert any('longitud' in e for e in errores)

    def test_validar_contrasena_ok(self) -> None:
        errores = svc_pol.validar_contrasena_contra_politica(
            contrasena='AbCdEf123!', longitud_minima=8,
            complejidad_regex=r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w]).+$',
        )
        assert errores == []

    def test_validar_contrasena_incumple_complejidad(self) -> None:
        errores = svc_pol.validar_contrasena_contra_politica(
            contrasena='abcdefghij', longitud_minima=5,
            complejidad_regex=r'^(?=.*[A-Z]).+$',
        )
        assert any('complejidad' in e for e in errores)

    def test_validar_regex_invalida(self) -> None:
        errores = svc_pol.validar_contrasena_contra_politica(
            contrasena='abc', longitud_minima=1, complejidad_regex='[invalid',
        )
        assert 'regex_politica_invalida' in errores

    @pytest.mark.asyncio
    async def test_registrar_hash_historico(self) -> None:
        conn = AsyncMock()
        await svc_pol.registrar_hash_historico(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            hash_nuevo='$2b$12$xxx', algoritmo='bcrypt',
        )
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_listar_hashes_recientes_con_cantidad_cero(self) -> None:
        conn = AsyncMock()
        result = await svc_pol.listar_hashes_recientes(
            conn, tenant_id=uuid4(), user_id=uuid4(), cantidad=0
        )
        assert result == []
        conn.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_listar_hashes_recientes_devuelve_strings(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = [{'hash': 'h1'}, {'hash': 'h2'}]
        result = await svc_pol.listar_hashes_recientes(
            conn, tenant_id=uuid4(), user_id=uuid4(), cantidad=2
        )
        assert result == ['h1', 'h2']
