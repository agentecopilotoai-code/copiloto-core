"""Tests mocks para services del bloque 11 (plantillas EP-010)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import plantillas as svc


# Helper rows.
def _pl_row(estado='borrador', codigo='COD', tipo='oficio_respuesta', **extra):
    base = {
        'id': uuid4(), 'codigo': codigo, 'nombre': 'Plantilla',
        'descripcion': None, 'tipo_plantilla': tipo,
        'estado': estado, 'version_vigente_id': None,
        'numero_version_vigente': 0,
        'dependencia_propietaria_id': None,
        'es_institucional': False,
        'created_by_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _ver_row(numero=1, estado='borrador', schema=None, **extra):
    base = {
        'id': uuid4(), 'plantilla_id': uuid4(),
        'numero_version': numero,
        'contenido_template': 'Hola {{nombre}}',
        'archivo_digital_id': None, 'mime_type': 'text/plain',
        'json_schema_campos': schema or {'type': 'object', 'properties': {}},
        'estado': estado, 'notas': None,
        'created_by_user_id': uuid4(), 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# render_template
# =============================================================================
class TestRender:
    def test_render_simple(self):
        r = svc.render_template('Hola {{nombre}}', {'nombre': 'Ana'})
        assert r == 'Hola Ana'

    def test_render_nested(self):
        r = svc.render_template(
            'Org: {{org.nombre}}', {'org': {'nombre': 'Ravit'}},
        )
        assert r == 'Org: Ravit'

    def test_render_var_no_existe(self):
        r = svc.render_template('Hola {{nombre}}', {})
        assert r == 'Hola '

    def test_render_none_value(self):
        r = svc.render_template('Hola {{nombre}}', {'nombre': None})
        assert r == 'Hola '

    def test_render_path_no_existe_intermedio(self):
        r = svc.render_template('{{a.b.c}}', {'a': {'x': 1}})
        assert r == ''


# =============================================================================
# CRUD plantilla
# =============================================================================
class TestPlantillaCRUD:
    @pytest.mark.asyncio
    async def test_crear_sin_version(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _pl_row()
        r = await svc.crear_plantilla(
            conn, tenant_id=uuid4(), codigo='OFI',
            nombre='Oficio', descripcion=None,
            tipo_plantilla='oficio_respuesta',
            dependencia_propietaria_id=None, es_institucional=False,
            contenido_template=None, json_schema_campos=None,
            mime_type='text/plain', created_by_user_id=uuid4(),
        )
        assert r['estado'] == 'borrador'
        assert r['versiones'] == []

    @pytest.mark.asyncio
    async def test_crear_con_version_inicial(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _pl_row(),
            _ver_row(numero=1),
        ]
        conn.fetchval.return_value = 0  # max_num
        r = await svc.crear_plantilla(
            conn, tenant_id=uuid4(), codigo='OFI',
            nombre='Oficio', descripcion=None,
            tipo_plantilla='oficio_respuesta',
            dependencia_propietaria_id=None, es_institucional=False,
            contenido_template='Hola {{nombre}}',
            json_schema_campos={'type': 'object'},
            mime_type='text/plain', created_by_user_id=uuid4(),
        )
        assert len(r['versiones']) == 1

    @pytest.mark.asyncio
    async def test_crear_codigo_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='codigo_ya_existe'):
            await svc.crear_plantilla(
                conn, tenant_id=uuid4(), codigo='DUP',
                nombre='X', descripcion=None,
                tipo_plantilla='otra',
                dependencia_propietaria_id=None, es_institucional=False,
                contenido_template=None, json_schema_campos=None,
                mime_type='text/plain', created_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _pl_row(estado='activa')
        conn.fetch.return_value = [_ver_row()]
        r = await svc.obtener_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
        )
        assert r is not None
        assert len(r['versiones']) == 1

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_version_jsonschema_str(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _pl_row()
        # Postgres returns JSONB as str sometimes
        ver = _ver_row()
        ver['json_schema_campos'] = '{"type": "object"}'
        conn.fetch.return_value = [ver]
        r = await svc.obtener_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
        )
        assert r['versiones'][0]['json_schema_campos'] == {'type': 'object'}

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_plantillas(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_plantillas(
            conn, tenant_id=uuid4(),
            estado=['activa'], tipo_plantilla='oficio_respuesta',
            dependencia_id=uuid4(), es_institucional=True, limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 7
        assert await svc.contar_plantillas(conn, tenant_id=uuid4()) == 7

    @pytest.mark.asyncio
    async def test_patch_ok(self):
        conn = AsyncMock()
        # Una vez para chequeo existencia + dos veces para get inicial y final
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = [
            _pl_row(nombre='Nuevo'),
        ]
        conn.fetch.return_value = []
        r = await svc.patch_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            nombre='Nuevo', descripcion='desc',
            dependencia_propietaria_id=uuid4(),
        )
        assert r['nombre'] == 'Nuevo'

    @pytest.mark.asyncio
    async def test_patch_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.patch_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            nombre='X', descripcion=None, dependencia_propietaria_id=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_sin_cambios(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _pl_row()
        conn.fetch.return_value = []
        r = await svc.patch_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            nombre=None, descripcion=None, dependencia_propietaria_id=None,
        )
        # No cambios — debería retornar plantilla actual.
        assert r is not None


# =============================================================================
# Versiones
# =============================================================================
class TestVersiones:
    @pytest.mark.asyncio
    async def test_crear_version_primera(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetchrow.return_value = _ver_row(numero=1)
        r = await svc.crear_version_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            contenido_template='X', json_schema_campos=None,
            archivo_digital_id=None, mime_type='text/plain',
            notas='v1', created_by_user_id=uuid4(),
        )
        assert r['numero_version'] == 1

    @pytest.mark.asyncio
    async def test_crear_version_segunda(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 2
        conn.fetchrow.return_value = _ver_row(numero=3)
        r = await svc.crear_version_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            contenido_template='X', json_schema_campos={'type': 'object'},
            archivo_digital_id=uuid4(), mime_type='application/pdf',
            notas=None, created_by_user_id=uuid4(),
        )
        assert r['numero_version'] == 3

    @pytest.mark.asyncio
    async def test_crear_version_jsonschema_str(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        # PG returns JSONB as str sometimes
        ver = _ver_row(numero=1)
        ver['json_schema_campos'] = '{"type": "object"}'
        conn.fetchrow.return_value = ver
        r = await svc.crear_version_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            contenido_template='X', json_schema_campos=None,
            archivo_digital_id=None, mime_type='text/plain',
            notas=None, created_by_user_id=uuid4(),
        )
        assert r['json_schema_campos'] == {'type': 'object'}


# =============================================================================
# Activar / inactivar
# =============================================================================
class TestActivarInactivar:
    @pytest.mark.asyncio
    async def test_activar_version_borrador_explicita(self):
        conn = AsyncMock()
        ver_id = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador', 'version_vigente_id': None},  # plantilla
            {'id': ver_id, 'numero_version': 1, 'estado': 'borrador'},  # version target
            _pl_row(estado='activa', version_vigente_id=ver_id,
                     numero_version_vigente=1),  # obtener_plantilla
        ]
        conn.fetch.return_value = []
        r = await svc.activar_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            version_id=ver_id, usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'activa'

    @pytest.mark.asyncio
    async def test_activar_ultima_borrador(self):
        conn = AsyncMock()
        ver_id = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'activa', 'version_vigente_id': uuid4()},  # ya activa, vamos a cambiar versión
            {'id': ver_id, 'numero_version': 2},  # ultima borrador
            _pl_row(estado='activa', numero_version_vigente=2),
        ]
        conn.fetch.return_value = []
        r = await svc.activar_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            version_id=None, usuario_actor_id=uuid4(),
        )
        assert r['numero_version_vigente'] == 2

    @pytest.mark.asyncio
    async def test_activar_plantilla_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.activar_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            version_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_activar_sin_version_borrador(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador', 'version_vigente_id': None},
            None,  # sin versión borrador
        ]
        with pytest.raises(ValueError, match='sin_version_borrador'):
            await svc.activar_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                version_id=None, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_activar_version_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'borrador', 'version_vigente_id': None},
            None,  # version no existe
        ]
        with pytest.raises(ValueError, match='version_no_existe'):
            await svc.activar_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                version_id=uuid4(), usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_activar_version_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'activa', 'version_vigente_id': uuid4()},
            {'id': uuid4(), 'numero_version': 1, 'estado': 'reemplazada'},
        ]
        with pytest.raises(ValueError, match='version_estado_invalido'):
            await svc.activar_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                version_id=uuid4(), usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_inactivar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'activa'},
            _pl_row(estado='inactiva'),
        ]
        conn.fetch.return_value = []
        r = await svc.inactivar_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'inactiva'

    @pytest.mark.asyncio
    async def test_inactivar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.inactivar_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_inactivar_ya_inactiva(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'inactiva'}
        with pytest.raises(ValueError, match='ya_inactiva'):
            await svc.inactivar_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                usuario_actor_id=uuid4(),
            )


# =============================================================================
# Generar documento
# =============================================================================
class TestGenerar:
    @pytest.mark.asyncio
    async def test_generar_plantilla_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.generar_documento_desde_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            titulo=None, clasificacion_informacion='interna',
            radicado_id=None, pqrsd_id=None, correspondencia_id=None,
            datos_adicionales={}, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_generar_plantilla_no_activa(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'codigo': 'C', 'nombre': 'P',
            'estado': 'borrador', 'version_vigente_id': uuid4(),
        }
        with pytest.raises(ValueError, match='plantilla_estado_invalido'):
            await svc.generar_documento_desde_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                titulo=None, clasificacion_informacion='interna',
                radicado_id=None, pqrsd_id=None, correspondencia_id=None,
                datos_adicionales={}, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_generar_sin_version_vigente(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'codigo': 'C', 'nombre': 'P',
            'estado': 'activa', 'version_vigente_id': None,
        }
        with pytest.raises(ValueError, match='plantilla_sin_version_vigente'):
            await svc.generar_documento_desde_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                titulo=None, clasificacion_informacion='interna',
                radicado_id=None, pqrsd_id=None, correspondencia_id=None,
                datos_adicionales={}, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_generar_version_no_encontrada(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'codigo': 'C', 'nombre': 'P',
             'estado': 'activa', 'version_vigente_id': uuid4()},
            None,  # version vigente no encontrada
        ]
        with pytest.raises(ValueError, match='version_vigente_no_encontrada'):
            await svc.generar_documento_desde_plantilla(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                titulo=None, clasificacion_informacion='interna',
                radicado_id=None, pqrsd_id=None, correspondencia_id=None,
                datos_adicionales={}, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_generar_ok_completo(self, monkeypatch):
        # Mock svc_documentos.crear_documento
        doc_id = uuid4()
        ver_doc_id = uuid4()

        async def fake_crear_doc(conn, **kwargs):
            return {
                'id': doc_id,
                'versiones': [{'id': ver_doc_id, 'numero_version': 1}],
            }
        monkeypatch.setattr(
            'app.gd.services.documentos.crear_documento', fake_crear_doc,
        )

        conn = AsyncMock()
        # 1. plantilla
        # 2. version vigente
        # 3. org (perfil_organizacion)
        # 4. user (snapshot)
        # 5. radicado
        # 6. pqrsd
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'codigo': 'RESP_PQRSD', 'nombre': 'Respuesta',
             'estado': 'activa', 'version_vigente_id': uuid4()},
            {'id': uuid4(),
             'contenido_template': 'Hola {{solicitante.nombre}}',
             'mime_type': 'text/plain',
             'json_schema_campos': {}},
            {'nombre': 'Org S.A.', 'nit': '111', 'direccion': 'X', 'ciudad': 'Y'},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'dependencia_actual_id': uuid4(), 'cargo_actual_id': uuid4(),
             'cargo_nombre': 'Director', 'dep_nombre': 'Talento'},
            {'numero': '2026-E-1', 'asunto': 'A',
             'fecha_radicacion': datetime.now(),
             'tipo_radicado': 'entrada'},
            {'id': uuid4(), 'asunto': 'A',
             'fecha_recepcion': datetime.now(),
             'tipo_pqrsd_id': uuid4(), 'tipo_nombre': 'Petición',
             'solicitante_nombre': 'Juan Pérez',
             'solicitante_direccion': 'Calle 1'},
        ]
        r = await svc.generar_documento_desde_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            titulo=None, clasificacion_informacion='datos_personales',
            radicado_id=uuid4(), pqrsd_id=uuid4(),
            correspondencia_id=None,
            datos_adicionales={'cuerpo_respuesta': 'Su solicitud...'},
            usuario_actor_id=uuid4(),
        )
        assert r['documento_id'] == doc_id
        assert 'Juan Pérez' in r['contenido_renderizado']

    @pytest.mark.asyncio
    async def test_generar_ok_mime_no_whitelist(self, monkeypatch):
        # Si version.mime_type no está en whitelist documento, se fuerza text/plain
        doc_id = uuid4()

        captured = {}
        async def fake_crear_doc(conn, **kwargs):
            captured.update(kwargs)
            return {'id': doc_id,
                    'versiones': [{'id': uuid4(), 'numero_version': 1}]}
        monkeypatch.setattr(
            'app.gd.services.documentos.crear_documento', fake_crear_doc,
        )

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'codigo': 'X', 'nombre': 'X',
             'estado': 'activa', 'version_vigente_id': uuid4()},
            {'id': uuid4(), 'contenido_template': 'hi',
             'mime_type': 'application/octet-stream',
             'json_schema_campos': {}},
            None,  # org
            None,  # user
        ]
        await svc.generar_documento_desde_plantilla(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            titulo='T', clasificacion_informacion='interna',
            radicado_id=None, pqrsd_id=None, correspondencia_id=None,
            datos_adicionales={}, usuario_actor_id=uuid4(),
        )
        assert captured['mime_type'] == 'text/plain'


# =============================================================================
# Asociaciones
# =============================================================================
class TestAsociaciones:
    @pytest.mark.asyncio
    async def test_asociar_dep_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'plantilla_id': uuid4(),
            'asociacion_tipo': 'dependencia',
            'asociacion_id': uuid4(), 'asociacion_codigo': None,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = await svc.asociar_dependencia(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            dependencia_id=uuid4(), creado_por_user_id=uuid4(),
        )
        assert r['asociacion_tipo'] == 'dependencia'

    @pytest.mark.asyncio
    async def test_asociar_dep_plantilla_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.asociar_dependencia(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            dependencia_id=uuid4(), creado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_asociar_dep_duplicada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='asociacion_ya_existe'):
            await svc.asociar_dependencia(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                dependencia_id=uuid4(), creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_asociar_tt_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = {
            'id': uuid4(), 'plantilla_id': uuid4(),
            'asociacion_tipo': 'tipo_tramite',
            'asociacion_id': None, 'asociacion_codigo': 'PQRSD',
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = await svc.asociar_tipo_tramite(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            tipo_tramite='PQRSD', creado_por_user_id=uuid4(),
        )
        assert r['asociacion_codigo'] == 'PQRSD'

    @pytest.mark.asyncio
    async def test_asociar_tt_plantilla_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.asociar_tipo_tramite(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
            tipo_tramite='X', creado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_asociar_tt_duplicado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='asociacion_ya_existe'):
            await svc.asociar_tipo_tramite(
                conn, tenant_id=uuid4(), plantilla_id=uuid4(),
                tipo_tramite='X', creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_asociaciones(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_asociaciones(
            conn, tenant_id=uuid4(), plantilla_id=uuid4(),
        )
        assert r == []


# =============================================================================
# Seed institucional
# =============================================================================
class TestSeed:
    @pytest.mark.asyncio
    async def test_seed_todas_nuevas(self):
        conn = AsyncMock()
        # Por cada plantilla: insert pl + insert version
        # 7 plantillas × 2 fetchrows
        rows: list = []
        for i in range(7):
            rows.append(_pl_row())  # plantilla insert
            rows.append(_ver_row(numero=1))  # version insert
        conn.fetchrow.side_effect = rows
        conn.fetchval.return_value = 0  # max_num
        r = await svc.seed_plantillas_institucionales(
            conn, tenant_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r['total'] == 7
        assert r['plantillas_existentes'] == []

    @pytest.mark.asyncio
    async def test_seed_parcial_ya_existen(self):
        conn = AsyncMock()
        # Primera plantilla: duplicada; segunda en adelante: nuevas
        rows: list = [asyncpg.UniqueViolationError]
        for _ in range(6):
            rows.append(_pl_row())
            rows.append(_ver_row(numero=1))
        conn.fetchrow.side_effect = rows
        conn.fetchval.return_value = 0
        r = await svc.seed_plantillas_institucionales(
            conn, tenant_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r['total'] == 6
        assert len(r['plantillas_existentes']) == 1
        assert r['plantillas_existentes'][0] == 'OFICIO_RESPUESTA'

    @pytest.mark.asyncio
    async def test_seed_estructura(self):
        # Verificar que SEED_PLANTILLAS tiene 7 elementos con campos requeridos
        assert len(svc.SEED_PLANTILLAS) == 7
        for s in svc.SEED_PLANTILLAS:
            assert 'codigo' in s
            assert 'nombre' in s
            assert 'tipo_plantilla' in s
            assert 'contenido_template' in s
            assert 'json_schema_campos' in s
