"""Tests mocks para services del bloque 10 (documentos EP-009)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import documentos as svc


def _doc_row(estado='activo', clasif='interna', **extra):
    base = {
        'id': uuid4(), 'titulo': 'Doc', 'descripcion': None,
        'clasificacion_informacion': clasif,
        'trd_serie_codigo': None, 'trd_subserie_codigo': None,
        'trd_tipo_documental': None,
        'estado': estado, 'version_vigente_id': uuid4(),
        'numero_version_vigente': 1,
        'anulado_en': None, 'motivo_anulacion': None,
        'reemplazado_por_documento_id': None,
        'creado_por_user_id': uuid4(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _ver_row(numero=1, estado='borrador', **extra):
    base = {
        'id': uuid4(), 'documento_id': uuid4(),
        'numero_version': numero, 'archivo_digital_id': uuid4(),
        'mime_type': 'application/pdf', 'tamano_bytes': 1024,
        'hash_sha256': 'abc', 'estado': estado,
        'creado_por_user_id': uuid4(),
        'aprobado_por_user_id': None, 'firmado_por_user_id': None,
        'observaciones': None, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Validación archivo
# =============================================================================
class TestValidacionArchivo:
    def test_mime_permitido_ok(self):
        svc.validar_archivo_para_documento(
            mime_type='application/pdf', tamano_bytes=1024,
        )

    def test_mime_no_permitido(self):
        with pytest.raises(ValueError, match='mime_no_permitido'):
            svc.validar_archivo_para_documento(
                mime_type='application/x-executable', tamano_bytes=100,
            )

    def test_tamano_excedido(self):
        with pytest.raises(ValueError, match='tamano_excedido'):
            svc.validar_archivo_para_documento(
                mime_type='application/pdf', tamano_bytes=200 * 1024 * 1024,
            )

    def test_mime_none_ok(self):
        svc.validar_archivo_para_documento(mime_type=None, tamano_bytes=None)


# =============================================================================
# CRUD documento + versiones
# =============================================================================
class TestDocumentos:
    @pytest.mark.asyncio
    async def test_crear_documento_ok(self):
        conn = AsyncMock()
        ver_id = uuid4()
        conn.fetchrow.side_effect = [
            _doc_row(version_vigente_id=None),  # insert documento
            _ver_row(numero=1),  # insert version
            _doc_row(version_vigente_id=ver_id),  # update version_vigente
        ]
        r = await svc.crear_documento(
            conn, tenant_id=uuid4(), titulo='Test',
            descripcion=None, clasificacion_informacion='interna',
            trd_serie_codigo=None, trd_subserie_codigo=None,
            trd_tipo_documental=None,
            archivo_digital_id=uuid4(), mime_type='application/pdf',
            tamano_bytes=1024, hash_sha256='abc',
            observaciones=None, creado_por_user_id=uuid4(),
        )
        assert r['numero_version_vigente'] == 1
        assert len(r['versiones']) == 1

    @pytest.mark.asyncio
    async def test_crear_documento_mime_invalido(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='mime_no_permitido'):
            await svc.crear_documento(
                conn, tenant_id=uuid4(), titulo='T',
                descripcion=None, clasificacion_informacion='interna',
                trd_serie_codigo=None, trd_subserie_codigo=None,
                trd_tipo_documental=None,
                archivo_digital_id=uuid4(),
                mime_type='application/x-exe', tamano_bytes=100,
                hash_sha256=None, observaciones=None,
                creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_documento_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _doc_row()
        conn.fetch.return_value = [_ver_row()]
        r = await svc.obtener_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
        )
        assert r is not None
        assert len(r['versiones']) == 1

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_documentos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_todos_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_documentos(
            conn, tenant_id=uuid4(),
            estado=['activo'], clasificacion=['interna', 'publica'],
            trd_serie='SERIE-1', titulo_like='test',
            permisos_clasificacion_permitidas=['publica', 'interna'],
            limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 5
        assert await svc.contar_documentos(conn, tenant_id=uuid4()) == 5

    @pytest.mark.asyncio
    async def test_nueva_version_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'activo', 'numero_version_vigente': 1},
            _ver_row(numero=2),
        ]
        r = await svc.nueva_version(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            archivo_digital_id=uuid4(),
            mime_type='application/pdf', tamano_bytes=2048,
            hash_sha256='def', observaciones='v2',
            creado_por_user_id=uuid4(),
        )
        assert r['numero_version'] == 2

    @pytest.mark.asyncio
    async def test_nueva_version_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.nueva_version(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            archivo_digital_id=uuid4(),
            mime_type=None, tamano_bytes=None, hash_sha256=None,
            observaciones=None, creado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_nueva_version_doc_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'anulado',
                                        'numero_version_vigente': 1}
        with pytest.raises(ValueError, match='estado_documento_invalido'):
            await svc.nueva_version(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                archivo_digital_id=uuid4(),
                mime_type=None, tamano_bytes=None, hash_sha256=None,
                observaciones=None, creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_nueva_version_mime_invalido(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='mime_no_permitido'):
            await svc.nueva_version(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                archivo_digital_id=uuid4(),
                mime_type='application/x-exe', tamano_bytes=100,
                hash_sha256=None, observaciones=None,
                creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_versiones(self):
        conn = AsyncMock()
        conn.fetch.return_value = [_ver_row(numero=2), _ver_row(numero=1)]
        r = await svc.listar_versiones(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
        )
        assert len(r) == 2


# =============================================================================
# Anulación + reemplazo
# =============================================================================
class TestAnularReemplazar:
    @pytest.mark.asyncio
    async def test_anular_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'activo'},
            _doc_row(estado='anulado'),
        ]
        conn.fetch.return_value = []
        r = await svc.anular_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'anulado'

    @pytest.mark.asyncio
    async def test_anular_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.anular_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_anular_ya_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'anulado'}
        with pytest.raises(ValueError, match='ya_anulado'):
            await svc.anular_documento(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                motivo='X' * 11, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reemplazar_ok(self):
        conn = AsyncMock()
        ver_anterior_id = uuid4()
        conn.fetchrow.side_effect = [
            {'estado': 'activo', 'version_vigente_id': ver_anterior_id,
             'numero_version_vigente': 1},
            _ver_row(numero=2),
        ]
        r = await svc.reemplazar_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            archivo_digital_id=uuid4(), motivo='reemplazo',
            mime_type='application/pdf', tamano_bytes=1000,
            hash_sha256=None, usuario_actor_id=uuid4(),
        )
        assert r['numero_version'] == 2

    @pytest.mark.asyncio
    async def test_reemplazar_sin_version_anterior(self):
        # documento.version_vigente_id es None
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'activo', 'version_vigente_id': None,
             'numero_version_vigente': 0},
            _ver_row(numero=1),
        ]
        r = await svc.reemplazar_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            archivo_digital_id=uuid4(), motivo='reemplazo',
            mime_type=None, tamano_bytes=None, hash_sha256=None,
            usuario_actor_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_reemplazar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.reemplazar_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            archivo_digital_id=uuid4(), motivo='X',
            mime_type=None, tamano_bytes=None, hash_sha256=None,
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_reemplazar_doc_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'estado': 'anulado', 'version_vigente_id': uuid4(),
            'numero_version_vigente': 3,
        }
        with pytest.raises(ValueError, match='estado_documento_invalido'):
            await svc.reemplazar_documento(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                archivo_digital_id=uuid4(), motivo='X',
                mime_type=None, tamano_bytes=None, hash_sha256=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reemplazar_mime_invalido(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='mime_no_permitido'):
            await svc.reemplazar_documento(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                archivo_digital_id=uuid4(), motivo='X',
                mime_type='application/x-exe', tamano_bytes=100,
                hash_sha256=None, usuario_actor_id=uuid4(),
            )


# =============================================================================
# Anexos
# =============================================================================
class TestAnexos:
    @pytest.mark.asyncio
    async def test_crear_anexo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'archivo_digital_id': uuid4(),
            'entidad_relacionada_tipo': 'radicado',
            'entidad_relacionada_id': uuid4(),
            'titulo': 'Anexo', 'descripcion': None,
            'mime_type': 'application/pdf', 'tamano_bytes': 1024,
            'creado_por_user_id': uuid4(), 'created_at': datetime.now(),
        }
        r = await svc.crear_anexo(
            conn, tenant_id=uuid4(), archivo_digital_id=uuid4(),
            entidad_relacionada_tipo='radicado',
            entidad_relacionada_id=uuid4(),
            titulo='Anexo', descripcion=None,
            mime_type='application/pdf', tamano_bytes=1024,
            creado_por_user_id=uuid4(),
        )
        assert r['entidad_relacionada_tipo'] == 'radicado'

    @pytest.mark.asyncio
    async def test_listar_anexos_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_anexos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_anexos_por_entidad(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_anexos(
            conn, tenant_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_anexos_sin_filtros(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 7
        assert await svc.contar_anexos(conn, tenant_id=uuid4()) == 7

    @pytest.mark.asyncio
    async def test_contar_anexos_por_entidad(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 3
        assert await svc.contar_anexos(
            conn, tenant_id=uuid4(),
            entidad_tipo='pqrsd', entidad_id=uuid4(),
        ) == 3


# =============================================================================
# Descarga + criticidad
# =============================================================================
class TestDescarga:
    @pytest.mark.asyncio
    async def test_registrar_descarga_baja(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'descargado_en': datetime.now(),
            'clasificacion_informacion': 'interna',
        }
        r = await svc.registrar_descarga(
            conn, tenant_id=uuid4(), archivo_digital_id=uuid4(),
            usuario_id=uuid4(), clasificacion_informacion='interna',
        )
        assert r['criticidad'] == 'baja'

    @pytest.mark.asyncio
    async def test_registrar_descarga_alta_reservada(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'descargado_en': datetime.now(),
            'clasificacion_informacion': 'reservada',
        }
        r = await svc.registrar_descarga(
            conn, tenant_id=uuid4(), archivo_digital_id=uuid4(),
            usuario_id=uuid4(), clasificacion_informacion='reservada',
            ip='1.2.3.4', user_agent='ua', request_id=uuid4(),
        )
        assert r['criticidad'] == 'alta'

    @pytest.mark.asyncio
    async def test_registrar_descarga_datos_personales(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'descargado_en': datetime.now(),
            'clasificacion_informacion': 'datos_personales',
        }
        r = await svc.registrar_descarga(
            conn, tenant_id=uuid4(), archivo_digital_id=uuid4(),
            usuario_id=uuid4(), clasificacion_informacion='datos_personales',
        )
        assert r['criticidad'] == 'alta'


# =============================================================================
# Relaciones polimórficas
# =============================================================================
class TestRelaciones:
    @pytest.mark.asyncio
    async def test_relacionar_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # doc existe
        conn.fetchrow.return_value = {
            'id': uuid4(), 'documento_id': uuid4(),
            'entidad_tipo': 'radicado', 'entidad_id': uuid4(),
            'rol': 'principal', 'creado_por_user_id': uuid4(),
            'created_at': datetime.now(),
        }
        r = await svc.relacionar_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
            rol='principal', creado_por_user_id=uuid4(),
        )
        assert r['entidad_tipo'] == 'radicado'

    @pytest.mark.asyncio
    async def test_relacionar_doc_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.relacionar_documento(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
            entidad_tipo='radicado', entidad_id=uuid4(),
            rol=None, creado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_relacionar_duplicado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='relacion_ya_existe'):
            await svc.relacionar_documento(
                conn, tenant_id=uuid4(), documento_id=uuid4(),
                entidad_tipo='radicado', entidad_id=uuid4(),
                rol=None, creado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_relaciones(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_relaciones(
            conn, tenant_id=uuid4(), documento_id=uuid4(),
        )
        assert r == []
