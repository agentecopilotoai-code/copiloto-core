"""Tests TestClient para handlers del bloque 5 (terceros + radicados Ventanilla)."""
from __future__ import annotations

from datetime import datetime
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
OTRO_USER_ID = uuid4()


def _fake_perfil() -> GdPerfilContext:
    return GdPerfilContext(
        user_id=ACTOR_USER_ID, tenant_id=TENANT_ID, perfil_id=uuid4(),
        tipo_vinculacion='planta', estado_gd='activo',
        dependencia_actual_id=None, cargo_actual_id=None,
    )


async def _all_perms(conn, *, user_id, tenant_id):
    return {
        'PERM-VU-001': 'global', 'PERM-VU-002': 'global',
        'PERM-VU-005': 'global', 'PERM-VU-006': 'global',
        'PERM-VU-015': 'global', 'PERM-VU-016': 'global',
    }


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
# /terceros
# =============================================================================
class TestTercerosHandlers:
    def test_post_tercero(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan Pérez García',
                'correo': None, 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            '/v1/gd/terceros',
            json={
                'tipo_tercero': 'persona_natural',
                'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan Pérez García',
            },
        )
        assert r.status_code == 201, r.text

    def test_post_tercero_duplicado(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        r = client.post(
            '/v1/gd/terceros',
            json={
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan Pérez',
            },
        )
        assert r.status_code == 409

    def test_post_tercero_anonimo_sin_documento_ok(self, conn, client):
        """Anónimo NO exige documento."""
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'tipo_tercero': 'anonimo', 'tipo_documento': None,
                'numero_documento': None,
                'nombres_razon_social': 'Ciudadano Anónimo',
                'correo': None, 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.post(
            '/v1/gd/terceros',
            json={
                'tipo_tercero': 'anonimo',
                'nombres_razon_social': 'Ciudadano Anónimo',
            },
        )
        assert r.status_code == 201, r.text

    def test_post_tercero_persona_natural_sin_documento_falla(self, conn, client):
        """Persona natural exige tipo_documento + numero_documento."""
        r = client.post(
            '/v1/gd/terceros',
            json={
                'tipo_tercero': 'persona_natural',
                'nombres_razon_social': 'Juan',
            },
        )
        assert r.status_code == 422

    def test_get_buscar_por_documento(self, conn, client):
        conn.fetch.return_value = []
        r = client.get('/v1/gd/terceros/buscar?documento=12345')
        assert r.status_code == 200

    def test_get_tercero_existe(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tenant_id': TENANT_ID,
            'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
            'numero_documento': '12345678',
            'nombres_razon_social': 'Juan',
            'correo': None, 'telefono': None, 'direccion': None,
            'municipio': None, 'departamento': None, 'pais': 'CO',
            'estado': 'activo',
        }
        r = client.get(f'/v1/gd/terceros/{uuid4()}')
        assert r.status_code == 200

    def test_get_tercero_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/terceros/{uuid4()}')
        assert r.status_code == 404

    def test_patch_tercero(self, conn, client):
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'tenant_id': TENANT_ID,
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan',
                'correo': 'nuevo@x.com', 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
            {'id': uuid4()},
        ]
        r = client.patch(
            f'/v1/gd/terceros/{uuid4()}',
            json={'correo': 'nuevo@x.com'},
        )
        assert r.status_code == 200

    def test_patch_tercero_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.patch(
            f'/v1/gd/terceros/{uuid4()}',
            json={'correo': 'x@y.com'},
        )
        assert r.status_code == 404


# =============================================================================
# /ventanilla/radicados — POST entrada
# =============================================================================
class TestRadicadoEntrada:
    def _setup_canal_ok(self, conn, requiere_punto=False):
        return {
            'id': uuid4(), 'codigo': 'pres', 'nombre': 'Presencial',
            'requiere_punto_atencion': requiere_punto,
        }

    def test_post_entrada_basico(self, conn, client):
        canal_id = uuid4()
        rid = uuid4()
        conn.fetchrow.side_effect = [
            # 1. validar canal
            {'id': canal_id, 'codigo': 'web', 'nombre': 'Web',
             'requiere_punto_atencion': False},
            # 2. capturar_snapshot (SQL function)
            {'snapshot': {
                'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'Test User',
                'rol_codigo': 'gd.radicador', 'dependencia_codigo': 'VU',
                'cargo_nombre': 'Auxiliar',
            }},
            # 3. siguiente_radicado (SQL function)
            {'numero_radicado': 'RAD-2026-000001'},
            # 4. INSERT radicado
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'Solicitud', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'XYZ123',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
            # 5. emit audit
            {'id': uuid4()},
        ]
        conn.fetchval.return_value = None  # sin colisión codigo_verificacion

        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(canal_id),
                'asunto': 'Solicitud copia documento',
                'descripcion': 'Texto de prueba',
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body['numero_radicado'] == 'RAD-2026-000001'
        assert body['constancia']['codigo_verificacion'] == 'XYZ123'

    def test_post_entrada_canal_inexistente(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(uuid4()),
                'asunto': 'Solicitud',
            },
        )
        assert r.status_code == 404

    def test_post_entrada_canal_requiere_punto_pero_no_se_envia(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'codigo': 'pres', 'nombre': 'Presencial',
            'requiere_punto_atencion': True,
        }
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={'canal_id': str(uuid4()), 'asunto': 'Solicitud'},
        )
        assert r.status_code == 422
        assert r.json()['detail']['code'] == 'punto_atencion_requerido'

    def test_post_entrada_tercero_y_tercero_nuevo_excluyentes(self, conn, client):
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(uuid4()),
                'asunto': 'Asunto válido',
                'tercero_id': str(uuid4()),
                'tercero_nuevo': {
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': '12345678',
                    'nombres_razon_social': 'Juan Pérez',
                },
            },
        )
        assert r.status_code == 422

    def test_post_entrada_con_tercero_nuevo_inline(self, conn, client):
        canal_id = uuid4()
        rid = uuid4()
        tercero_id = uuid4()
        conn.fetchrow.side_effect = [
            # validar canal
            {'id': canal_id, 'codigo': 'pres', 'nombre': 'Presencial',
             'requiere_punto_atencion': False},
            # crear tercero
            {
                'id': tercero_id, 'tenant_id': TENANT_ID,
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan',
                'correo': None, 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
            # capturar_snapshot
            {'snapshot': {'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'X'}},
            # siguiente_radicado
            {'numero_radicado': 'RAD-2026-000001'},
            # INSERT radicado
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': tercero_id, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'ABC234',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
            # emit audit
            {'id': uuid4()},
        ]
        conn.fetchval.return_value = None
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(canal_id),
                'asunto': 'Test tercero inline',
                'tercero_nuevo': {
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': '12345678',
                    'nombres_razon_social': 'Juan Pérez',
                },
            },
        )
        assert r.status_code == 201, r.text

    def test_post_entrada_tercero_nuevo_duplicado(self, conn, client):
        import asyncpg
        canal_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': canal_id, 'codigo': 'pres', 'nombre': 'Presencial',
             'requiere_punto_atencion': False},
            asyncpg.UniqueViolationError,
        ]
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(canal_id),
                'asunto': 'Solicitud test',
                'tercero_nuevo': {
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': '12345678',
                    'nombres_razon_social': 'Juan Pérez',
                },
            },
        )
        assert r.status_code == 409

    def test_post_entrada_tercero_id_inexistente(self, conn, client):
        canal_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': canal_id, 'codigo': 'pres', 'nombre': 'Presencial',
             'requiere_punto_atencion': False},
            None,  # tercero_id no existe
        ]
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(canal_id),
                'asunto': 'Solicitud',
                'tercero_id': str(uuid4()),
            },
        )
        assert r.status_code == 404


# =============================================================================
# POST radicado salida
# =============================================================================
class TestRadicadoSalida:
    def test_post_salida_basico(self, conn, client):
        canal_id = uuid4()
        rid = uuid4()
        conn.fetchrow.side_effect = [
            # validar canal
            {'id': canal_id, 'codigo': 'correo', 'nombre': 'Correo postal',
             'requiere_punto_atencion': False},
            # snapshot
            {'snapshot': {'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'X'}},
            # siguiente_radicado
            {'numero_radicado': 'RAD-2026-S00001'},
            # INSERT radicado
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-S00001', 'tipo_radicado': 'salida',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'Respuesta', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': uuid4(), 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'OUT123',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
            # audit
            {'id': uuid4()},
        ]
        conn.fetchval.return_value = None
        r = client.post(
            '/v1/gd/ventanilla/radicados/salida',
            json={
                'asunto': 'Respuesta a oficio',
                'dependencia_origen_id': str(uuid4()),
                'canal_envio_id': str(canal_id),
            },
        )
        assert r.status_code == 201, r.text

    def test_post_salida_relacionado_anulado(self, conn, client):
        canal_id = uuid4()
        rel_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': canal_id, 'codigo': 'correo', 'nombre': 'X',
             'requiere_punto_atencion': False},
            {'estado': 'anulado', 'tipo_radicado': 'entrada'},
        ]
        r = client.post(
            '/v1/gd/ventanilla/radicados/salida',
            json={
                'asunto': 'Respuesta',
                'dependencia_origen_id': str(uuid4()),
                'canal_envio_id': str(canal_id),
                'radicado_entrada_relacionado_id': str(rel_id),
            },
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'radicado_entrada_anulado'


# =============================================================================
# GET búsqueda + detalle
# =============================================================================
class TestRadicadoConsulta:
    def test_get_buscar(self, conn, client):
        conn.fetch.return_value = [
            {
                'id': uuid4(), 'numero_radicado': 'RAD-2026-000001',
                'tipo_radicado': 'entrada', 'fecha_radicacion': datetime.now(),
                'asunto': 'X', 'estado': 'registrado',
                'canal_id': uuid4(), 'canal_codigo': 'web', 'canal_nombre': 'Web',
                'tercero_id': None, 'dependencia_destino_id': None,
                'anexos_count': 0, 'clasificacion_tipo': None,
            }
        ]
        conn.fetchrow.return_value = {'c': 1}
        r = client.get('/v1/gd/ventanilla/radicados')
        assert r.status_code == 200
        assert len(r.json()['items']) == 1

    def test_get_buscar_con_filtros(self, conn, client):
        conn.fetch.return_value = []
        conn.fetchrow.return_value = {'c': 0}
        r = client.get(
            '/v1/gd/ventanilla/radicados'
            '?numero_radicado=RAD-2026-000001'
            '&q=oficio'
            '&tipo_radicado=entrada,salida'
            '&estado=registrado'
            f'&canal_id={uuid4()}'
            f'&dependencia_destino_id={uuid4()}'
            f'&tercero_id={uuid4()}'
            '&fecha_radicacion_desde=2026-01-01T00:00:00'
            '&limit=10'
        )
        assert r.status_code == 200

    def test_get_detalle_existe(self, conn, client):
        rid = uuid4()
        canal_id = uuid4()
        conn.fetchrow.return_value = {
            'id': rid, 'tenant_id': TENANT_ID,
            'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
            'fecha_radicacion': datetime.now(),
            'canal_id': canal_id, 'canal_codigo': 'web', 'canal_nombre': 'Web',
            'punto_atencion_id': None,
            'asunto': 'X', 'descripcion': None,
            'tercero_id': None, 'tercero_destinatario_id': None,
            'dependencia_origen_id': None, 'dependencia_destino_id': None,
            'documento_principal_id': None,
            'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
            'radicado_relacionado_id': None,
            'codigo_verificacion': 'XYZ123',
            'es_radicacion_contingencia': False,
            'actor_snapshot': {'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'X'},
        }
        r = client.get(f'/v1/gd/ventanilla/radicados/{rid}')
        assert r.status_code == 200

    def test_get_detalle_con_tercero(self, conn, client):
        rid = uuid4()
        canal_id = uuid4()
        tid = uuid4()
        # primer fetchrow: radicado. segundo: tercero (string jsonb).
        conn.fetchrow.side_effect = [
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'canal_codigo': 'web', 'canal_nombre': 'Web',
                'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': tid, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'XYZ123',
                'es_radicacion_contingencia': False,
                # actor_snapshot como string (caso driver viejo)
                'actor_snapshot': '{"usuario_id": "' + str(ACTOR_USER_ID) + '"}',
            },
            {
                'id': tid, 'tenant_id': TENANT_ID,
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '12345678',
                'nombres_razon_social': 'Juan Pérez',
                'correo': None, 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
        ]
        r = client.get(f'/v1/gd/ventanilla/radicados/{rid}')
        assert r.status_code == 200
        body = r.json()
        assert body['tercero'] is not None
        # Documento enmascarado
        assert body['tercero']['numero_documento_enmascarado'] == '***45678'

    def test_get_detalle_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.get(f'/v1/gd/ventanilla/radicados/{uuid4()}')
        assert r.status_code == 404


# =============================================================================
# Clasificación + Reclasificación
# =============================================================================
class TestClasificarHandlers:
    def test_clasificar_ok(self, conn, client):
        # Usamos 'tramite' en lugar de 'pqrsd' para evitar disparar el hook
        # reactivo (GD-API-0043) que crea gd.pqrsd. El hook se cubre en
        # tests específicos del bloque 7.
        conn.fetchval.return_value = None  # no clasificación previa
        conn.fetchrow.side_effect = [
            {
                'id': uuid4(), 'radicado_id': uuid4(),
                'tipo_clasificacion': 'tramite', 'sub_tipo': None,
                'dependencia_destino_id': None, 'tipo_pqrsd_id': None,
                'fuente': 'manual', 'clasificado_por_user_id': ACTOR_USER_ID,
                'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/clasificar',
            json={'tipo_clasificacion': 'tramite'},
        )
        assert r.status_code == 200, r.text

    def test_clasificar_pqrsd_requiere_tipo_pqrsd_id(self, conn, client):
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/clasificar',
            json={'tipo_clasificacion': 'pqrsd'},
        )
        assert r.status_code == 422

    def test_clasificar_ya_existe_409(self, conn, client):
        conn.fetchval.return_value = 1  # ya vigente
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/clasificar',
            json={
                'tipo_clasificacion': 'tramite',
            },
        )
        assert r.status_code == 409

    def test_reclasificar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'id': uuid4()},  # vigente anterior
            {
                'id': uuid4(), 'radicado_id': uuid4(),
                'tipo_clasificacion': 'expediente', 'sub_tipo': None,
                'dependencia_destino_id': None, 'tipo_pqrsd_id': None,
                'fuente': 'manual', 'clasificado_por_user_id': ACTOR_USER_ID,
                'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/reclasificar',
            json={
                'tipo_clasificacion': 'expediente',
                'motivo': 'Cambio por solicitud del jefe de área',
            },
        )
        assert r.status_code == 200, r.text

    def test_reclasificar_sin_previa_404(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/reclasificar',
            json={
                'tipo_clasificacion': 'tramite',
                'motivo': 'Razón suficientemente larga',
            },
        )
        assert r.status_code == 404


# =============================================================================
# Anulación
# =============================================================================
class TestAnulacionHandlers:
    def test_solicitar_anulacion_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'estado': 'registrado'},  # radicado existe + no anulado
            {
                'id': uuid4(), 'tipo_entidad': 'radicado',
                'entidad_afectada_id': uuid4(),
                'solicitante_user_id': ACTOR_USER_ID,
                'motivo': 'Error grave en datos del solicitante',
                'decision': 'pendiente', 'fecha_solicitud': datetime.now(),
            },
            {'id': uuid4()},  # audit
        ]
        conn.fetchval.return_value = None  # sin pendiente previa
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/solicitar-anulacion',
            json={'motivo': 'Error grave en datos del solicitante'},
        )
        assert r.status_code == 201, r.text

    def test_solicitar_anulacion_radicado_inexistente(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/solicitar-anulacion',
            json={'motivo': 'Motivo lo suficientemente largo para pasar'},
        )
        assert r.status_code == 404

    def test_solicitar_anulacion_radicado_ya_anulado(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'anulado'}
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/solicitar-anulacion',
            json={'motivo': 'Motivo lo suficientemente largo para pasar'},
        )
        assert r.status_code == 409

    def test_solicitar_anulacion_duplicada_422(self, conn, client):
        conn.fetchrow.return_value = {'estado': 'registrado'}
        conn.fetchval.return_value = 1  # ya hay pendiente
        # crear_solicitud_anulacion devuelve None cuando ya hay pendiente
        # → mock devuelve None solo si fetchval indica conflicto
        # → necesitamos hacer la segunda fetchrow (la del INSERT) devolver None
        conn.fetchrow.side_effect = [
            {'estado': 'registrado'},  # radicado check
        ]
        r = client.post(
            f'/v1/gd/ventanilla/radicados/{uuid4()}/solicitar-anulacion',
            json={'motivo': 'Motivo lo suficientemente largo'},
        )
        assert r.status_code == 422

    def test_aprobar_anulacion_separacion_funciones(self, conn, client):
        """Solicitante NO puede aprobar (RNF-008)."""
        sid = uuid4()
        conn.fetchrow.return_value = {
            'id': sid, 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'solicitante_user_id': ACTOR_USER_ID,  # ACTOR es el solicitante
            'motivo': 'X', 'decision': 'pendiente',
            'aprobador_user_id': None, 'observacion_decision': None,
            'fecha_solicitud': datetime.now(), 'fecha_decision': None,
        }
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{sid}/aprobar',
            json={'observacion_decision': 'Aprobado por mí mismo'},
        )
        assert r.status_code == 403
        assert r.json()['detail']['code'] == 'solicitante_no_puede_aprobar'

    def test_aprobar_anulacion_ok(self, conn, client):
        sid = uuid4()
        rid = uuid4()
        # Orden real de fetchrows en handler:
        # 1. obtener_solicitud
        # 2. svc.aprobar_solicitud (UPDATE solicitud RETURNING)
        # 3. emit_gd_event (INSERT audit RETURNING)
        # 4. SELECT radicado para response
        conn.fetchrow.side_effect = [
            {
                'id': sid, 'tipo_entidad': 'radicado',
                'entidad_afectada_id': rid,
                'solicitante_user_id': OTRO_USER_ID,
                'motivo': 'X', 'decision': 'pendiente',
                'aprobador_user_id': None, 'observacion_decision': None,
                'fecha_solicitud': datetime.now(), 'fecha_decision': None,
            },
            {
                'id': sid, 'tipo_entidad': 'radicado',
                'entidad_afectada_id': rid,
                'aprobador_user_id': ACTOR_USER_ID,
                'fecha_decision': datetime.now(),
            },
            {'id': uuid4()},  # audit
            {
                'id': rid, 'numero_radicado': 'RAD-2026-000001',
                'estado': 'anulado', 'anulado_en': datetime.now(),
            },
        ]
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{sid}/aprobar',
            json={'observacion_decision': 'Aprobada por validación'},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['decision'] == 'aprobada'
        assert body['radicado']['estado'] == 'anulado'

    def test_aprobar_anulacion_solicitud_no_existe(self, conn, client):
        conn.fetchrow.return_value = None
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{uuid4()}/aprobar',
            json={'observacion_decision': None},
        )
        assert r.status_code == 404

    def test_aprobar_anulacion_ya_decidida(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'solicitante_user_id': OTRO_USER_ID,
            'motivo': 'X', 'decision': 'rechazada',
            'aprobador_user_id': uuid4(), 'observacion_decision': 'X',
            'fecha_solicitud': datetime.now(), 'fecha_decision': datetime.now(),
        }
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{uuid4()}/aprobar',
            json={'observacion_decision': None},
        )
        assert r.status_code == 409

    def test_rechazar_anulacion_ok(self, conn, client):
        sid = uuid4()
        conn.fetchrow.side_effect = [
            {
                'id': sid, 'tipo_entidad': 'radicado',
                'entidad_afectada_id': uuid4(),
                'solicitante_user_id': OTRO_USER_ID,
                'motivo': 'X', 'decision': 'pendiente',
                'aprobador_user_id': None, 'observacion_decision': None,
                'fecha_solicitud': datetime.now(), 'fecha_decision': None,
            },
            {
                'id': sid, 'tipo_entidad': 'radicado',
                'entidad_afectada_id': uuid4(),
                'aprobador_user_id': ACTOR_USER_ID,
                'fecha_decision': datetime.now(),
            },
            {'id': uuid4()},  # audit
        ]
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{sid}/rechazar',
            json={'observacion_decision': 'No procede según política'},
        )
        assert r.status_code == 200

    def test_rechazar_sin_observacion(self, conn, client):
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{uuid4()}/rechazar',
            json={'observacion_decision': 'corta'},
        )
        assert r.status_code == 422

    def test_rechazar_solicitante_no_puede(self, conn, client):
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'radicado',
            'entidad_afectada_id': uuid4(),
            'solicitante_user_id': ACTOR_USER_ID,  # ACTOR es solicitante
            'motivo': 'X', 'decision': 'pendiente',
            'aprobador_user_id': None, 'observacion_decision': None,
            'fecha_solicitud': datetime.now(), 'fecha_decision': None,
        }
        r = client.post(
            f'/v1/gd/ventanilla/anulaciones/{uuid4()}/rechazar',
            json={'observacion_decision': 'No procede por política institucional'},
        )
        assert r.status_code == 403
