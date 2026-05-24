"""Tests TestClient para los handlers HTTP del bloque 3.

Cubre:
- /api/v1/gd/organizacion (GET, POST, PATCH)
- /api/v1/gd/organizacion/modulos (GET, PATCH)
- /api/v1/gd/dependencias (GET, POST, PATCH, /cerrar-vigencia)
- /api/v1/gd/estructura/versiones (POST)
- /api/v1/gd/estructura/vigente, /api/v1/gd/estructura/historica
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.routes import router as gd_router
from app.gd.security import GdPerfilContext, require_gd_perfil


TENANT_ID = uuid4()
ACTOR_USER_ID = uuid4()


def _fake_perfil() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR_USER_ID, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


PERMISOS_GLOBAL = {
    'PERM-USR-001': 'global',
    'PERM-USR-010': 'global',
}


async def _all_perms(conn, *, user_id, tenant_id):
    return PERMISOS_GLOBAL


def build_app(conn_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(gd_router)

    async def _override_get_db():
        yield conn_mock

    async def _override_perfil() -> GdPerfilContext:
        return _fake_perfil()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_gd_perfil] = _override_perfil
    return app


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    return TestClient(build_app(conn))


# =============================================================================
# /organizacion
# =============================================================================
class TestOrganizacionHandlers:
    def test_get_perfil_existe(self, conn, client):
        conn.fetchrow.return_value = {
            'tenant_id': TENANT_ID, 'tipo_organizacion': 'publica',
            'identificacion_fiscal': '900', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'Alcaldía X', 'nombre_corto': 'AX',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': None,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        r = client.get('/api/v1/gd/organizacion')
        assert r.status_code == 200
        body = r.json()
        assert body['tipo_organizacion'] == 'publica'
        assert body['logo'] is None

    def test_get_perfil_con_logo(self, conn, client):
        logo_id = uuid4()
        conn.fetchrow.return_value = {
            'tenant_id': TENANT_ID, 'tipo_organizacion': 'privada',
            'identificacion_fiscal': '111', 'tipo_identificacion_fiscal': 'NIT',
            'razon_social_legal': 'X', 'nombre_corto': 'X',
            'direccion_oficial': None, 'telefono_oficial': None,
            'correo_oficial': None, 'sitio_web': None,
            'logo_archivo_digital_id': logo_id,
            'politica_firma_default': 'electronica',
            'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
            'dias_alerta_vencimiento_default': 3,
            'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
        }
        r = client.get('/api/v1/gd/organizacion')
        assert r.status_code == 200
        assert r.json()['logo']['archivo_digital_id'] == str(logo_id)

    def test_get_perfil_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get('/api/v1/gd/organizacion')
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'perfil_organizacion_no_existe'

    def test_post_perfil_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            # crear_perfil_organizacion
            {
                'tenant_id': TENANT_ID, 'tipo_organizacion': 'privada',
                'identificacion_fiscal': '111', 'tipo_identificacion_fiscal': 'NIT',
                'razon_social_legal': 'Empresa Test', 'nombre_corto': 'Test',
                'direccion_oficial': None, 'telefono_oficial': None,
                'correo_oficial': None, 'sitio_web': None,
                'logo_archivo_digital_id': None,
                'politica_firma_default': 'electronica',
                'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
                'dias_alerta_vencimiento_default': 3,
                'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
            },
            # aplicar_defaults_modulos
            {'count': 5},
            # audit
            {'id': uuid4()},
        ]
        r = client.post(
            '/api/v1/gd/organizacion',
            json={
                'tipo_organizacion': 'privada',
                'identificacion_fiscal': '111',
                'razon_social_legal': 'Empresa Test',
                'nombre_corto': 'Test',
            },
        )
        assert r.status_code == 201, r.text

    def test_post_perfil_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/organizacion',
            json={
                'tipo_organizacion': 'privada',
                'identificacion_fiscal': '111',
                'razon_social_legal': 'Empresa Test',
                'nombre_corto': 'Test',
            },
        )
        assert r.status_code == 409

    def test_patch_perfil_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            # actualizar_perfil_organizacion
            {
                'tenant_id': TENANT_ID, 'tipo_organizacion': 'publica',
                'identificacion_fiscal': '900', 'tipo_identificacion_fiscal': 'NIT',
                'razon_social_legal': 'Nuevo Nombre Legal', 'nombre_corto': 'X',
                'direccion_oficial': None, 'telefono_oficial': None,
                'correo_oficial': None, 'sitio_web': None,
                'logo_archivo_digital_id': None,
                'politica_firma_default': 'electronica',
                'formato_radicado': '{prefijo}-{vigencia}-{consecutivo:06d}',
                'dias_alerta_vencimiento_default': 3,
                'pais_iso': 'CO', 'zona_horaria_default': 'America/Bogota',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.patch(
            '/api/v1/gd/organizacion',
            json={'razon_social_legal': 'Nuevo Nombre Legal'},
        )
        assert r.status_code == 200
        assert r.json()['razon_social_legal'] == 'Nuevo Nombre Legal'

    def test_patch_perfil_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.patch(
            '/api/v1/gd/organizacion',
            json={'razon_social_legal': 'Nuevo Nombre Legal'},
        )
        assert r.status_code == 404


# =============================================================================
# /organizacion/modulos
# =============================================================================
class TestModulosHandlers:
    def test_get_modulos(self, conn, client):
        conn.fetch.return_value = [
            {'modulo_codigo': 'pqrsd_legal', 'activado': True, 'configuracion': None},
        ]
        r = client.get('/api/v1/gd/organizacion/modulos')
        assert r.status_code == 200
        body = r.json()
        # Lista canónica devuelve siempre 14.
        assert len(body['modulos']) == 14

    def test_patch_modulos_ok(self, conn, client):
        conn.execute.return_value = 'INSERT 0 1'
        conn.fetch.return_value = [
            {'modulo_codigo': 'pqrsd_legal', 'activado': False, 'configuracion': None},
        ]
        conn.fetchrow.return_value = {'id': uuid4()}  # audit
        r = client.patch(
            '/api/v1/gd/organizacion/modulos',
            json={
                'modulos': [
                    {'modulo_codigo': 'pqrsd_legal', 'activado': False},
                ],
            },
        )
        assert r.status_code == 200


# =============================================================================
# /dependencias
# =============================================================================
class TestDependenciasHandlers:
    def test_get_lista_plana(self, conn, client):
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'codigo_organico': 'JUR-001', 'nombre': 'Jurídica',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            }
        ]
        r = client.get('/api/v1/gd/dependencias')
        assert r.status_code == 200
        assert len(r.json()['items']) == 1

    def test_get_jerarquia(self, conn, client):
        raiz_id = uuid4()
        conn.fetch.return_value = [
            {
                'id': raiz_id, 'tenant_id': TENANT_ID,
                'codigo_organico': 'D', 'nombre': 'Despacho',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            },
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'codigo_organico': 'JUR', 'nombre': 'Jurídica',
                'dependencia_padre_id': raiz_id, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            },
        ]
        r = client.get('/api/v1/gd/dependencias?incluir_jerarquia=true')
        assert r.status_code == 200
        body = r.json()
        assert 'raiz' in body
        assert len(body['raiz']) == 1
        assert len(body['raiz'][0]['hijos']) == 1

    def test_post_dependencia_ok(self, conn, client):
        dep_id = uuid4()
        conn.fetchrow.side_effect = [
            {
                'id': dep_id, 'tenant_id': TENANT_ID,
                'codigo_organico': 'JUR-001', 'nombre': 'Jurídica',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/api/v1/gd/dependencias',
            json={
                'codigo_organico': 'JUR-001',
                'nombre': 'Oficina Jurídica',
                'fecha_inicio_vigencia': '2026-01-01',
                'version_estructura_id': str(uuid4()),
            },
        )
        assert r.status_code == 201, r.text

    def test_post_dependencia_codigo_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/api/v1/gd/dependencias',
            json={
                'codigo_organico': 'JUR-001',
                'nombre': 'Jurídica',
                'fecha_inicio_vigencia': '2026-01-01',
                'version_estructura_id': str(uuid4()),
            },
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'codigo_organico_duplicado'

    def test_post_dependencia_fk_padre_invalido(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError
        r = client.post(
            '/api/v1/gd/dependencias',
            json={
                'codigo_organico': 'JUR-001',
                'nombre': 'Jurídica',
                'fecha_inicio_vigencia': '2026-01-01',
                'version_estructura_id': str(uuid4()),
                'dependencia_padre_id': str(uuid4()),
            },
        )
        assert r.status_code == 404

    def test_patch_dependencia_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'codigo_organico': 'JUR-001', 'nombre': 'Jurídica Renombrada',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'activa',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None,
            },
            {'id': uuid4()},
        ]
        r = client.patch(
            f'/api/v1/gd/dependencias/{uuid4()}',
            json={'nombre': 'Jurídica Renombrada'},
        )
        assert r.status_code == 200

    def test_patch_dependencia_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.patch(
            f'/api/v1/gd/dependencias/{uuid4()}',
            json={'nombre': 'Jurídica Nueva Larga'},
        )
        assert r.status_code == 404

    def test_cerrar_vigencia_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'codigo_organico': 'JUR-001', 'nombre': 'Jurídica',
                'dependencia_padre_id': None, 'version_estructura_id': uuid4(),
                'estado': 'cerrada',
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': date(2026, 6, 30),
            },
            {'id': uuid4()},
        ]
        r = client.post(
            f'/api/v1/gd/dependencias/{uuid4()}/cerrar-vigencia',
            json={
                'motivo': 'Reestructura administrativa',
                'fecha_fin': '2026-06-30',
                'acto_administrativo': 'Decreto 0123/2026',
            },
        )
        assert r.status_code == 200

    def test_cerrar_vigencia_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/api/v1/gd/dependencias/{uuid4()}/cerrar-vigencia',
            json={
                'motivo': 'Razón válida suficientemente larga',
                'fecha_fin': '2026-06-30',
            },
        )
        assert r.status_code == 404


# =============================================================================
# /estructura
# =============================================================================
class TestEstructuraHandlers:
    def test_post_version_estructura_ok(self, conn, client):
        version_id = uuid4()
        conn.fetchrow.side_effect = [
            None,  # vigente actual
            {
                'id': version_id, 'tenant_id': TENANT_ID,
                'numero_version': 'v1.0', 'descripcion': None,
                'acto_administrativo': None,
                'fecha_inicio_vigencia': date(2026, 1, 1),
                'fecha_fin_vigencia': None, 'estado': 'borrador',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/api/v1/gd/estructura/versiones',
            json={
                'numero_version': 'v1.0',
                'fecha_inicio_vigencia': '2026-01-01',
            },
        )
        assert r.status_code == 201, r.text

    def test_post_version_duplicada(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = [None, asyncpg.UniqueViolationError]
        r = client.post(
            '/api/v1/gd/estructura/versiones',
            json={
                'numero_version': 'v1.0',
                'fecha_inicio_vigencia': '2026-01-01',
            },
        )
        assert r.status_code == 409

    def test_get_vigente_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'version_estructura_id': uuid4(),
            'numero_version': 'v1.0',
            'fecha_inicio_vigencia': date(2026, 1, 1),
            'dependencias_count': 12,
        }
        r = client.get('/api/v1/gd/estructura/vigente')
        assert r.status_code == 200
        assert r.json()['dependencias_count'] == 12

    def test_get_vigente_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get('/api/v1/gd/estructura/vigente')
        assert r.status_code == 404

    def test_get_historica_ok(self, conn, client):
        conn.fetchrow.return_value = {
            'version_estructura_id': uuid4(),
            'numero_version': 'v0.9',
            'fecha_inicio_vigencia': date(2024, 1, 1),
            'dependencias_count': 30,
        }
        r = client.get('/api/v1/gd/estructura/historica?fecha=2024-06-15')
        assert r.status_code == 200
        assert r.json()['numero_version'] == 'v0.9'

    def test_get_historica_sin_resultado(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get('/api/v1/gd/estructura/historica?fecha=2020-01-01')
        assert r.status_code == 404
