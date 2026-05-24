"""Tests TestClient para handlers del bloque 19 (archivos EP-018)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import router_core as core_router
from app.gd.security import GdPerfilContext, require_gd_perfil


TENANT_ID = uuid4()
ACTOR = uuid4()


def _perfil():
    return GdPerfilContext(
        user_id=ACTOR, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {'PERM-USR-001': 'global'}


async def _noop_emit(*a, **k):
    return uuid4()


def build_app(conn_mock):
    app = FastAPI()
    app.include_router(core_router)

    async def _ovr_db():
        yield conn_mock

    async def _ovr_perfil():
        return _perfil()

    app.dependency_overrides[get_db] = _ovr_db
    app.dependency_overrides[require_gd_perfil] = _ovr_perfil
    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    monkeypatch.setattr(
        'app.gd.handlers.archivos_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _arch_dict(estado='cargado', av='limpio', **extra):
    base = {
        'id': uuid4(), 'nombre_original': 'doc.pdf',
        'extension': 'pdf', 'mime_type': 'application/pdf',
        'tamano_bytes': 1024,
        'hash_sha256': 'a' * 64, 'hash_md5': 'a' * 32,
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
# Upload
# =============================================================================
class TestUpload:
    def test_subir_ok(self, conn, client):
        conn.fetchrow.return_value = _arch_dict()
        r = client.post(
            '/api/v1/core/archivos',
            files={'archivo': ('test.pdf', BytesIO(b'pdf-data'),
                                'application/pdf')},
            data={'proposito': 'gd.documento'},
        )
        assert r.status_code == 201, r.text
        assert r.json()['estado'] == 'cargado'

    def test_subir_infectado(self, conn, client):
        from app.gd.services.archivos import EICAR_SIGNATURE
        conn.fetchrow.return_value = _arch_dict(
            estado='bloqueado', av='infectado', ruta_almacenamiento=None,
        )
        r = client.post(
            '/api/v1/core/archivos',
            files={'archivo': ('eicar.txt',
                                BytesIO(EICAR_SIGNATURE.encode()),
                                'text/plain')},
            data={'proposito': 'general'},
        )
        assert r.status_code == 201
        assert r.json()['estado'] == 'bloqueado'


# =============================================================================
# Listar / detalle / duplicados
# =============================================================================
class TestLectura:
    def test_listar(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/api/v1/core/archivos')
        assert r.status_code == 200

    def test_listar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(
            '/api/v1/core/archivos?proposito=gd.documento'
            f'&estado=cargado&contexto_entidad_tipo=radicado'
            f'&contexto_entidad_id={uuid4()}&limit=10',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.return_value = _arch_dict()
        r = client.get(f'/api/v1/core/archivos/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/core/archivos/{uuid4()}')
        assert r.status_code == 404

    def test_duplicados_vacio(self, conn, client):
        conn.fetch.return_value = []
        r = client.get(f'/api/v1/core/archivos/duplicados?hash={"a"*64}')
        assert r.status_code == 200
        assert r.json()['total'] == 0

    def test_duplicados_con_coincidencias(self, conn, client):
        conn.fetch.return_value = [_arch_dict()]
        r = client.get(f'/api/v1/core/archivos/duplicados?hash={"b"*64}')
        assert r.status_code == 200
        assert r.json()['total'] == 1

    def test_duplicados_hash_invalido(self, conn, client):
        # hash debe min_length=32
        r = client.get('/api/v1/core/archivos/duplicados?hash=short')
        assert r.status_code == 422


# =============================================================================
# attach_proposito
# =============================================================================
class TestAttach:
    def test_ok(self, conn, client):
        conn.fetchval.return_value = 'cargado'
        conn.fetchrow.return_value = _arch_dict(proposito='gd.anexo')
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/attach-proposito',
            json={'proposito': 'gd.anexo',
                  'contexto_entidad_tipo': 'pqrsd',
                  'contexto_entidad_id': str(uuid4())},
        )
        assert r.status_code == 200

    def test_404(self, conn, client):
        conn.fetchval.return_value = None
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/attach-proposito',
            json={'proposito': 'general'},
        )
        assert r.status_code == 404

    def test_anulado_409(self, conn, client):
        conn.fetchval.return_value = 'anulado'
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/attach-proposito',
            json={'proposito': 'general'},
        )
        assert r.status_code == 409


# =============================================================================
# Descargar / anular
# =============================================================================
class TestDescargarAnular:
    def test_descargar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            _arch_dict(),
            {'id': uuid4(), 'descargado_en': datetime.now()},
        ]
        r = client.post(f'/api/v1/core/archivos/{uuid4()}/descargar')
        assert r.status_code == 200, r.text
        assert 'download_url' in r.json()

    def test_descargar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(f'/api/v1/core/archivos/{uuid4()}/descargar')
        assert r.status_code == 404

    def test_descargar_anulado_409(self, conn, client):
        conn.fetchrow.return_value = _arch_dict(estado='anulado')
        r = client.post(f'/api/v1/core/archivos/{uuid4()}/descargar')
        assert r.status_code == 409

    def test_descargar_infectado_409(self, conn, client):
        conn.fetchrow.return_value = _arch_dict(av='infectado')
        r = client.post(f'/api/v1/core/archivos/{uuid4()}/descargar')
        assert r.status_code == 409

    def test_anular_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'cargado'},
            _arch_dict(estado='anulado'),
        ]
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/anular',
            json={'motivo': 'subido por error sin permisos'},
        )
        assert r.status_code == 200

    def test_anular_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 404

    def test_anular_ya_anulado(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'anulado'}
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/anular',
            json={'motivo': 'X' * 11},
        )
        assert r.status_code == 409


# =============================================================================
# Extracción / re-extraer
# =============================================================================
class TestExtraccion:
    def test_consultar_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'archivo_digital_id': uuid4(),
            'motor': 'pypdf', 'version': None,
            'texto_completo': 'extracted',
            'paginas_jsonb': [], 'confianza': None,
            'warning_baja_confianza': False, 'truncado': False,
            'motivo_truncado': None,
            'extraido_en': datetime.now(), 'duracion_ms': 5,
        }
        r = client.get(f'/api/v1/core/archivos/{uuid4()}/extraccion')
        assert r.status_code == 200

    def test_consultar_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/api/v1/core/archivos/{uuid4()}/extraccion')
        assert r.status_code == 404

    def test_reextraer_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/core/archivos/{uuid4()}/reextraer',
            json={'motor': 'auto'},
        )
        assert r.status_code == 404


# =============================================================================
# Retención
# =============================================================================
class TestRetencion:
    def test_dry_run_sin_candidatos(self, conn, client):
        conn.fetch.return_value = []
        r = client.post(
            '/api/v1/core/archivos/aplicar-retencion',
            json={'dry_run': True, 'limit': 100},
        )
        assert r.status_code == 200
        assert r.json()['candidatos_evaluados'] == 0

    def test_dry_run_con_candidatos(self, conn, client):
        conn.fetch.return_value = [
            {'id': uuid4(), 'ruta_almacenamiento': 'file:///x',
             'retencion_politica': 'eliminacion',
             'nombre_original': 'a.pdf'},
        ]
        r = client.post(
            '/api/v1/core/archivos/aplicar-retencion',
            json={'dry_run': True, 'limit': 100},
        )
        assert r.status_code == 200
        assert r.json()['candidatos_evaluados'] == 1
