"""Tests mocks para services del bloque 19 (archivos EP-018)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import archivos as svc


def _arch_row(estado='cargado', av='limpio', **extra):
    base = {
        'id': uuid4(), 'nombre_original': 'doc.pdf',
        'extension': 'pdf', 'mime_type': 'application/pdf',
        'tamano_bytes': 1024,
        'hash_sha256': 'abc' * 21 + 'd',  # 64 chars
        'hash_md5': 'a' * 32,
        'storage_backend': 'filesystem',
        'ruta_almacenamiento': 'file:///tmp/x',
        'encriptado_at_rest': False,
        'proposito': 'general',
        'contexto_entidad_tipo': None, 'contexto_entidad_id': None,
        'estado': estado, 'analisis_antivirus': av,
        'motor_antivirus': 'stub-eicar',
        'fecha_antivirus': datetime.now(), 'detalle_antivirus': None,
        'retencion_politica': None, 'fecha_elegible_purga': None,
        'fecha_purga_bytes': None, 'motivo_purga': None,
        'cargado_por_user_id': uuid4(), 'cargado_en': datetime.now(),
        'ultimo_acceso_en': None, 'total_descargas': 0,
        'metadata': {},
    }
    base.update(extra)
    return base


# =============================================================================
# Storage providers
# =============================================================================
class TestStorageProviders:
    @pytest.mark.asyncio
    async def test_memory_provider_full_cycle(self):
        p = svc.InMemoryStorageProvider()
        await p.save(tenant_id=uuid4(), key='k1', contenido=b'data')
        assert await p.exists(key='k1')
        assert await p.get(key='k1') == b'data'
        assert await p.delete(key='k1') is True
        assert await p.delete(key='k1') is False
        url = await p.generar_url_descarga(key='k1', ttl_segundos=60)
        assert 'ttl=60' in url

    @pytest.mark.asyncio
    async def test_filesystem_provider(self, tmp_path):
        p = svc.FilesystemStorageProvider(base_dir=str(tmp_path))
        await p.save(tenant_id=uuid4(), key='sub/file.txt', contenido=b'hello')
        assert await p.exists(key='sub/file.txt')
        assert await p.get(key='sub/file.txt') == b'hello'
        url = await p.generar_url_descarga(key='sub/file.txt')
        assert url.startswith('/core/archivos/_download/')
        await p.delete(key='sub/file.txt')
        assert not await p.exists(key='sub/file.txt')

    @pytest.mark.asyncio
    async def test_filesystem_get_inexistente(self, tmp_path):
        p = svc.FilesystemStorageProvider(base_dir=str(tmp_path))
        assert await p.get(key='no_existe') is None

    @pytest.mark.asyncio
    async def test_filesystem_delete_inexistente(self, tmp_path):
        p = svc.FilesystemStorageProvider(base_dir=str(tmp_path))
        assert await p.delete(key='no_existe') is False

    def test_get_default(self):
        assert isinstance(svc.get_default_storage(), svc.InMemoryStorageProvider)

    def test_set_default_storage(self):
        original = svc.get_default_storage()
        custom = svc.InMemoryStorageProvider()
        svc.set_default_storage(custom)
        assert svc.get_default_storage() is custom
        svc.set_default_storage(original)


# =============================================================================
# Antivirus
# =============================================================================
class TestAntivirus:
    @pytest.mark.asyncio
    async def test_limpio(self):
        s = svc.StubAntivirusScanner()
        r = await s.scan(contenido=b'normal content')
        assert r['limpio'] is True

    @pytest.mark.asyncio
    async def test_eicar_bloqueado(self):
        s = svc.StubAntivirusScanner()
        r = await s.scan(contenido=svc.EICAR_SIGNATURE.encode())
        assert r['limpio'] is False
        assert 'EICAR' in r['detalle']

    def test_get_default(self):
        assert isinstance(svc.get_default_antivirus(), svc.StubAntivirusScanner)


# =============================================================================
# OCR
# =============================================================================
class TestOCR:
    @pytest.mark.asyncio
    async def test_stub_ocr(self):
        p = svc.StubOCRProvider()
        r = await p.ocr(contenido=b'data', mime_type='image/jpeg')
        assert r['motor'] == 'stub-tesseract'
        assert r['texto_completo']
        assert 0.5 <= r['confianza'] <= 0.99

    @pytest.mark.asyncio
    async def test_stub_ocr_determinista(self):
        p = svc.StubOCRProvider()
        r1 = await p.ocr(contenido=b'mismo', mime_type='image/png')
        r2 = await p.ocr(contenido=b'mismo', mime_type='image/png')
        assert r1['confianza'] == r2['confianza']

    def test_get_default(self):
        assert isinstance(svc.get_default_ocr(), svc.StubOCRProvider)


# =============================================================================
# Helpers
# =============================================================================
class TestHelpers:
    def test_sha256_determinista(self):
        assert svc.calcular_sha256(b'a') == svc.calcular_sha256(b'a')

    def test_md5_determinista(self):
        assert svc.calcular_md5(b'a') == svc.calcular_md5(b'a')

    def test_detectar_extension(self):
        assert svc.detectar_extension('foo.pdf') == 'pdf'
        assert svc.detectar_extension('FOO.PDF') == 'pdf'
        assert svc.detectar_extension('foo.tar.gz') == 'gz'
        assert svc.detectar_extension('sin_extension') is None

    def test_fecha_purga_estandar(self):
        ref = datetime(2026, 1, 1)
        r = svc.calcular_fecha_purga(
            fecha_referencia=ref, retencion_politica='estandar',
        )
        assert r is not None
        assert r.year >= 2032  # +7 años

    def test_fecha_purga_conservacion_total(self):
        r = svc.calcular_fecha_purga(
            fecha_referencia=datetime.now(),
            retencion_politica='conservacion_total',
        )
        assert r is None

    def test_fecha_purga_invalida(self):
        r = svc.calcular_fecha_purga(
            fecha_referencia=datetime.now(), retencion_politica='inexistente',
        )
        assert r is None


# =============================================================================
# Subir / obtener / listar / anular
# =============================================================================
class TestSubir:
    @pytest.mark.asyncio
    async def test_subir_limpio(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row()
        r = await svc.subir_archivo(
            conn, tenant_id=uuid4(),
            nombre_original='doc.pdf', mime_type='application/pdf',
            contenido=b'pdf-bytes', proposito='gd.documento',
            contexto_entidad_tipo=None, contexto_entidad_id=None,
            retencion_politica=None,
            storage_backend='filesystem', encriptado_at_rest=False,
            cargado_por_user_id=uuid4(),
            storage_provider=svc.InMemoryStorageProvider(),
        )
        assert r['estado'] == 'cargado'
        assert r['analisis_antivirus'] == 'limpio'

    @pytest.mark.asyncio
    async def test_subir_infectado_bloquea(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(
            estado='bloqueado', av='infectado',
            ruta_almacenamiento=None,
        )
        r = await svc.subir_archivo(
            conn, tenant_id=uuid4(),
            nombre_original='virus.txt', mime_type='text/plain',
            contenido=svc.EICAR_SIGNATURE.encode(),
            proposito='general',
            contexto_entidad_tipo=None, contexto_entidad_id=None,
            retencion_politica=None,
            storage_backend='memory', encriptado_at_rest=False,
            cargado_por_user_id=uuid4(),
            storage_provider=svc.InMemoryStorageProvider(),
        )
        assert r['estado'] == 'bloqueado'
        assert r['analisis_antivirus'] == 'infectado'

    @pytest.mark.asyncio
    async def test_subir_con_retencion(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(
            retencion_politica='eliminacion',
            fecha_elegible_purga=datetime.now() + timedelta(days=365 * 5),
        )
        r = await svc.subir_archivo(
            conn, tenant_id=uuid4(),
            nombre_original='x.txt', mime_type='text/plain',
            contenido=b'x', proposito='general',
            contexto_entidad_tipo=None, contexto_entidad_id=None,
            retencion_politica='eliminacion',
            storage_backend='memory', encriptado_at_rest=False,
            cargado_por_user_id=uuid4(),
            storage_provider=svc.InMemoryStorageProvider(),
        )
        assert r['retencion_politica'] == 'eliminacion'

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row()
        r = await svc.obtener_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_metadata_str(self):
        conn = AsyncMock()
        row = _arch_row()
        row['metadata'] = '{"a":1}'
        conn.fetchrow.return_value = row
        r = await svc.obtener_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
        )
        assert r['metadata'] == {'a': 1}

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_archivos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_archivos(
            conn, tenant_id=uuid4(),
            proposito='gd.documento', estado='cargado',
            contexto_entidad_tipo='radicado', contexto_entidad_id=uuid4(),
            limit=10,
        )
        assert r == []


# =============================================================================
# Descargar
# =============================================================================
class TestDescargar:
    @pytest.mark.asyncio
    async def test_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _arch_row(),
            {'id': uuid4(), 'descargado_en': datetime.now()},
        ]
        r = await svc.descargar_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            usuario_id=uuid4(), motivo='consulta',
            ip='1.2.3.4', user_agent='ua',
            storage_provider=svc.InMemoryStorageProvider(),
        )
        assert r['download_url']
        assert r['descarga_id']

    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.descargar_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            usuario_id=uuid4(),
            storage_provider=svc.InMemoryStorageProvider(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_estado_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(estado='anulado')
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.descargar_archivo(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
                usuario_id=uuid4(),
                storage_provider=svc.InMemoryStorageProvider(),
            )

    @pytest.mark.asyncio
    async def test_infectado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(av='infectado')
        with pytest.raises(ValueError, match='archivo_infectado'):
            await svc.descargar_archivo(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
                usuario_id=uuid4(),
                storage_provider=svc.InMemoryStorageProvider(),
            )


# =============================================================================
# Anular
# =============================================================================
class TestAnular:
    @pytest.mark.asyncio
    async def test_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'cargado'},
            _arch_row(estado='anulado'),
        ]
        r = await svc.anular_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            motivo='subido por error', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'anulado'

    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.anular_archivo(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_ya_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'anulado'}
        with pytest.raises(ValueError, match='ya_anulado'):
            await svc.anular_archivo(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
                motivo='X' * 11, usuario_actor_id=uuid4(),
            )


# =============================================================================
# Dedupe
# =============================================================================
class TestDedupe:
    @pytest.mark.asyncio
    async def test_sin_coincidencias(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.buscar_duplicados_por_hash(
            conn, tenant_id=uuid4(), hash_sha256='a' * 64,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_con_coincidencias(self):
        conn = AsyncMock()
        conn.fetch.return_value = [_arch_row(), _arch_row()]
        r = await svc.buscar_duplicados_por_hash(
            conn, tenant_id=uuid4(), hash_sha256='abc',
        )
        assert len(r) == 2


# =============================================================================
# Extracción
# =============================================================================
class TestExtraccion:
    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.extraer_texto(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(estado='anulado')
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.extraer_texto(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_extraer_pdf_idempotente(self):
        conn = AsyncMock()
        existing_id = uuid4()
        # 1. obtener_archivo, 2. fetchval idempotency check (existe),
        # 3. obtener_extraccion fetchrow
        conn.fetchrow.side_effect = [
            _arch_row(mime_type='application/pdf'),
            # obtener_extraccion returns:
            {'id': existing_id, 'archivo_digital_id': uuid4(),
             'motor': 'pypdf', 'version': None,
             'texto_completo': 'existing',
             'paginas_jsonb': [], 'confianza': None,
             'warning_baja_confianza': False, 'truncado': False,
             'motivo_truncado': None,
             'extraido_en': datetime.now(), 'duracion_ms': 0},
        ]
        conn.fetchval.return_value = existing_id
        storage = svc.InMemoryStorageProvider()
        r = await svc.extraer_texto(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            forzar=False, storage_provider=storage,
        )
        assert r['texto_completo'] == 'existing'

    @pytest.mark.asyncio
    async def test_extraer_ocr(self):
        # Pre-populate storage so .get() retorna bytes
        storage = svc.InMemoryStorageProvider()
        conn = AsyncMock()
        arch_id = uuid4()
        tenant = uuid4()
        # Construir arch_row con tenant + id consistentes para que la key
        # del storage matchee.
        arch = _arch_row(mime_type='image/jpeg')
        arch['id'] = arch_id
        arch['nombre_original'] = 'foto.jpg'
        await storage.save(
            tenant_id=tenant,
            key=f"{tenant}/{arch_id}/foto.jpg",
            contenido=b'image-bytes',
        )

        conn.fetchrow.side_effect = [
            arch,  # obtener_archivo
            # insert extraccion returning row
            {'id': uuid4(), 'archivo_digital_id': arch_id,
             'motor': 'stub-tesseract-v0.1.0-stub',
             'version': '0.1.0-stub',
             'texto_completo': '[OCR STUB]', 'paginas_jsonb': '[]',
             'confianza': 0.7, 'warning_baja_confianza': False,
             'truncado': False, 'motivo_truncado': None,
             'extraido_en': datetime.now(), 'duracion_ms': 5},
        ]
        conn.fetchval.return_value = None  # no existing extraction
        r = await svc.extraer_texto(
            conn, tenant_id=tenant, archivo_id=arch_id,
            forzar=False, storage_provider=storage,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_extraer_contenido_no_disponible(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _arch_row(mime_type='application/pdf')
        conn.fetchval.return_value = None
        storage = svc.InMemoryStorageProvider()
        with pytest.raises(LookupError, match='contenido_no_disponible'):
            await svc.extraer_texto(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
                forzar=True, storage_provider=storage,
            )

    @pytest.mark.asyncio
    async def test_obtener_extraccion_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_extraccion(
            conn, tenant_id=uuid4(), extraccion_id=uuid4(),
        )
        assert r is None


# =============================================================================
# Retención
# =============================================================================
class TestRetencion:
    @pytest.mark.asyncio
    async def test_sin_candidatos(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.aplicar_politica_retencion(
            conn, tenant_id=uuid4(), dry_run=True,
        )
        assert r['candidatos_evaluados'] == 0
        assert r['purgados'] == 0

    @pytest.mark.asyncio
    async def test_dry_run(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'id': uuid4(), 'ruta_almacenamiento': 'file:///tmp/a',
             'retencion_politica': 'eliminacion', 'nombre_original': 'a.pdf'},
        ]
        r = await svc.aplicar_politica_retencion(
            conn, tenant_id=uuid4(), dry_run=True,
        )
        assert r['dry_run'] is True
        assert r['purgados'] == 0
        assert r['detalle'][0]['accion'] == 'purgaria'

    @pytest.mark.asyncio
    async def test_purga_real(self):
        storage = svc.InMemoryStorageProvider()
        await storage.save(tenant_id=uuid4(), key='/tmp/a', contenido=b'data')
        conn = AsyncMock()
        conn.fetch.return_value = [
            {'id': uuid4(), 'ruta_almacenamiento': 'file:///tmp/a',
             'retencion_politica': 'eliminacion', 'nombre_original': 'a.pdf'},
        ]
        r = await svc.aplicar_politica_retencion(
            conn, tenant_id=uuid4(), dry_run=False,
            storage_provider=storage,
        )
        assert r['dry_run'] is False


# =============================================================================
# attach_proposito
# =============================================================================
class TestAttach:
    @pytest.mark.asyncio
    async def test_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'cargado'
        conn.fetchrow.return_value = _arch_row(proposito='gd.documento')
        r = await svc.attach_proposito(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            proposito='gd.documento',
            contexto_entidad_tipo='radicado',
            contexto_entidad_id=uuid4(),
        )
        assert r['proposito'] == 'gd.documento'

    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.attach_proposito(
            conn, tenant_id=uuid4(), archivo_id=uuid4(),
            proposito='general',
            contexto_entidad_tipo=None, contexto_entidad_id=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_estado_anulado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'anulado'
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.attach_proposito(
                conn, tenant_id=uuid4(), archivo_id=uuid4(),
                proposito='general',
                contexto_entidad_tipo=None, contexto_entidad_id=None,
            )
