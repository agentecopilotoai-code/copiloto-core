"""Tests edge cases para cubrir líneas defensivas de radicados_handlers."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.handlers.radicados_handlers import _enmascarar_documento
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


async def _all_perms(conn, *, user_id, tenant_id):
    return {'PERM-VU-001': 'global', 'PERM-VU-002': 'global'}


@pytest.fixture
def conn():
    return AsyncMock()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr('app.gd.security.get_permisos_efectivos', _all_perms)
    app = FastAPI()
    app.include_router(gd_router)

    async def _ovr_db():
        yield conn

    async def _ovr_perfil() -> GdPerfilContext:
        return _fake_perfil()

    app.dependency_overrides[get_db] = _ovr_db
    app.dependency_overrides[require_gd_perfil] = _ovr_perfil
    return TestClient(app)


# =============================================================================
# Helper enmascarar
# =============================================================================
class TestEnmascararDocumento:
    def test_documento_largo(self) -> None:
        assert _enmascarar_documento('12345678') == '***45678'

    def test_documento_corto_no_se_enmascara(self) -> None:
        # length < 4 → devuelve tal cual
        assert _enmascarar_documento('123') == '123'

    def test_none(self) -> None:
        assert _enmascarar_documento(None) is None

    def test_string_vacio(self) -> None:
        assert _enmascarar_documento('') == ''


# =============================================================================
# POST entrada — cobertura del fallback de snapshot
# =============================================================================
class TestSnapshotFallback:
    def test_post_entrada_snapshot_vacio_usa_fallback(self, conn, client):
        """Si capturar_snapshot lanza ValueError, usa fallback con solo user_id."""
        canal_id = uuid4()
        rid = uuid4()
        # capturar_snapshot lanza si fetchrow devuelve None.
        conn.fetchrow.side_effect = [
            # canal ok
            {'id': canal_id, 'codigo': 'web', 'nombre': 'Web',
             'requiere_punto_atencion': False},
            # capturar_snapshot devuelve None → lanza ValueError → fallback
            {'snapshot': None},
            # consecutivo
            {'numero_radicado': 'RAD-2026-000001'},
            # INSERT
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'XYZ123',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
            {'id': uuid4()},  # audit
        ]
        conn.fetchval.return_value = None
        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={'canal_id': str(canal_id), 'asunto': 'Solicitud test'},
        )
        assert r.status_code == 201, r.text


# =============================================================================
# POST entrada — con clasificación sugerida inline
# =============================================================================
class TestClasificacionInline:
    def test_post_entrada_con_clasificacion_sugerida(self, conn, client):
        canal_id = uuid4()
        rid = uuid4()
        conn.fetchrow.side_effect = [
            # canal
            {'id': canal_id, 'codigo': 'web', 'nombre': 'Web',
             'requiere_punto_atencion': False},
            # snapshot ok
            {'snapshot': {'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'X'}},
            # consecutivo
            {'numero_radicado': 'RAD-2026-000001'},
            # INSERT radicado
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-000001', 'tipo_radicado': 'entrada',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'X', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': None,
                'dependencia_origen_id': None, 'dependencia_destino_id': None,
                'documento_principal_id': None,
                'usuario_radicador_id': ACTOR_USER_ID, 'estado': 'registrado',
                'radicado_relacionado_id': None,
                'codigo_verificacion': 'XYZ123',
                'es_radicacion_contingencia': False,
                'actor_snapshot': '{}', 'created_at': datetime.now(),
            },
            # clasificar_radicado RETURNING
            {
                'id': uuid4(), 'radicado_id': rid,
                'tipo_clasificacion': 'pqrsd', 'sub_tipo': 'peticion',
                'dependencia_destino_id': None, 'tipo_pqrsd_id': None,
                'fuente': 'manual', 'clasificado_por_user_id': ACTOR_USER_ID,
                'fecha_clasificacion': datetime.now(), 'estado': 'vigente',
            },
            # audit
            {'id': uuid4()},
        ]
        # fetchval: sin colisión código + sin clasificación previa
        conn.fetchval.side_effect = [None, None]

        r = client.post(
            '/v1/gd/ventanilla/radicados/entrada',
            json={
                'canal_id': str(canal_id),
                'asunto': 'Solicitud con clasificación',
                'clasificacion_sugerida': {
                    'tipo_clasificacion': 'pqrsd',
                    'sub_tipo': 'peticion',
                },
            },
        )
        assert r.status_code == 201, r.text


# =============================================================================
# POST salida — con destinatario nuevo inline
# =============================================================================
class TestSalidaConDestinatarioNuevo:
    def test_post_salida_con_destinatario_nuevo(self, conn, client):
        canal_id = uuid4()
        dep_origen = uuid4()
        tid = uuid4()
        rid = uuid4()
        conn.fetchrow.side_effect = [
            # canal
            {'id': canal_id, 'codigo': 'correo', 'nombre': 'Correo',
             'requiere_punto_atencion': False},
            # crear tercero destinatario
            {
                'id': tid, 'tenant_id': TENANT_ID,
                'tipo_tercero': 'persona_natural', 'tipo_documento': 'CC',
                'numero_documento': '99999999',
                'nombres_razon_social': 'Destinatario Test',
                'correo': None, 'telefono': None, 'direccion': None,
                'municipio': None, 'departamento': None, 'pais': 'CO',
                'estado': 'activo',
            },
            # snapshot
            {'snapshot': {'usuario_id': str(ACTOR_USER_ID), 'nombre_completo': 'X'}},
            # consecutivo
            {'numero_radicado': 'RAD-2026-S00001'},
            # INSERT radicado
            {
                'id': rid, 'tenant_id': TENANT_ID,
                'numero_radicado': 'RAD-2026-S00001', 'tipo_radicado': 'salida',
                'fecha_radicacion': datetime.now(),
                'canal_id': canal_id, 'punto_atencion_id': None,
                'asunto': 'Respuesta', 'descripcion': None,
                'tercero_id': None, 'tercero_destinatario_id': tid,
                'dependencia_origen_id': dep_origen, 'dependencia_destino_id': None,
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
                'asunto': 'Respuesta a solicitud',
                'dependencia_origen_id': str(dep_origen),
                'canal_envio_id': str(canal_id),
                'tercero_destinatario_nuevo': {
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': '99999999',
                    'nombres_razon_social': 'Destinatario Test',
                },
            },
        )
        assert r.status_code == 201, r.text

    def test_post_salida_con_destinatario_nuevo_duplicado(self, conn, client):
        import asyncpg
        canal_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': canal_id, 'codigo': 'correo', 'nombre': 'X',
             'requiere_punto_atencion': False},
            asyncpg.UniqueViolationError,
        ]
        r = client.post(
            '/v1/gd/ventanilla/radicados/salida',
            json={
                'asunto': 'Respuesta',
                'dependencia_origen_id': str(uuid4()),
                'canal_envio_id': str(canal_id),
                'tercero_destinatario_nuevo': {
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': '99999999',
                    'nombres_razon_social': 'Test Duplicado',
                },
            },
        )
        assert r.status_code == 409

    def test_post_salida_relacionado_no_existe(self, conn, client):
        canal_id = uuid4()
        conn.fetchrow.side_effect = [
            {'id': canal_id, 'codigo': 'correo', 'nombre': 'X',
             'requiere_punto_atencion': False},
            None,  # relacionado no existe
        ]
        r = client.post(
            '/v1/gd/ventanilla/radicados/salida',
            json={
                'asunto': 'Respuesta',
                'dependencia_origen_id': str(uuid4()),
                'canal_envio_id': str(canal_id),
                'radicado_entrada_relacionado_id': str(uuid4()),
            },
        )
        assert r.status_code == 404
