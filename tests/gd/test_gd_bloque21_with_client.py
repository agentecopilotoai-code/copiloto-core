"""Tests TestClient para handlers del bloque 21a (EP-021 periféricos parte 1)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.pool import get_db
from app.gd.handlers.perifericos_handlers import (
    router_codigos, router_perif, router_puntos,
)
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
    return {'PERM-PER-001': 'global'}


async def _noop_emit(*a, **k):
    return uuid4()


def build_app(conn_mock):
    app = FastAPI()
    # Prefijo /v1/gd similar al routes.py global.
    from fastapi import APIRouter
    root = APIRouter(prefix='/v1/gd')
    root.include_router(router_puntos)
    root.include_router(router_perif)
    root.include_router(router_codigos)
    app.include_router(root)

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
        'app.gd.handlers.perifericos_handlers.emit_gd_event', _noop_emit,
    )
    return TestClient(build_app(conn))


def _modulo_activo(conn):
    """Stub para gate de módulo activo: ya viene cargado."""
    conn.fetchrow.return_value = {'activado': True}


def _punto(**extra):
    base = {
        'id': uuid4(), 'nombre': 'Sede Sur', 'direccion': 'Cl 1',
        'dependencia_responsable_id': None, 'estado': 'activo',
        'motivo_cierre': None, 'metadata': {},
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _perif(**extra):
    base = {
        'id': uuid4(), 'tipo_periferico': 'impresora_etiquetas',
        'nombre': 'Zebra', 'marca': 'Zebra', 'modelo': 'GK420t',
        'serial': 'ZB-1', 'dependencia_id': None,
        'punto_atencion_id': None, 'estado': 'activo',
        'motivo_cambio_estado': None, 'configuracion': {},
        'ultimo_handshake_en': None,
        'fecha_registro': datetime.now(),
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _impr(**extra):
    base = {
        'id': uuid4(), 'radicado_id': uuid4(), 'documento_id': None,
        'periferico_id': uuid4(), 'usuario_id': uuid4(),
        'tipo_impresion': 'etiqueta_qr', 'formato': 'estandar',
        'estado': 'encolada', 'mensaje_error': None,
        'latencia_ms': None, 'motivo_reimpresion': None,
        'intentos_reimpresion': 0, 'impresion_original_id': None,
        'archivo_digital_id': None, 'contenido_impreso': {},
        'fecha_impresion': datetime.now(),
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _digit(**extra):
    base = {
        'id': uuid4(), 'radicado_id': uuid4(), 'documento_id': None,
        'archivo_digital_id': None, 'periferico_id': uuid4(),
        'usuario_id': uuid4(), 'tipo_digitalizacion': 'individual',
        'numero_paginas': None, 'calidad_dpi': 300,
        'estado': 'encolada', 'mensaje_error': None,
        'observacion': None, 'lote_id': None,
        'fecha_digitalizacion': datetime.now(),
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _codigo(**extra):
    base = {
        'id': uuid4(), 'tipo_codigo': 'qr',
        'radicado_id': uuid4(), 'documento_id': None,
        'expediente_id': None,
        'valor_codigo': '/gd/verificar/x', 'token_opaco': 'x',
        'estado': 'activo', 'reemplazado_por_id': None,
        'motivo_anulacion': None,
        'fecha_generacion': datetime.now(),
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Gate de módulo
# =============================================================================
class TestGateModulo:
    def test_modulo_inactivo_404(self, conn, client):
        conn.fetchrow.return_value = None  # módulo no activado
        r = client.get('/v1/gd/puntos-atencion')
        assert r.status_code == 404
        body = r.json()
        assert body['detail']['code'] == 'modulo_perifericos_no_activo'

    def test_modulo_desactivado_404(self, conn, client):
        conn.fetchrow.return_value = {'activado': False}
        r = client.get('/v1/gd/perifericos')
        assert r.status_code == 404


# =============================================================================
# Puntos de atención
# =============================================================================
class TestPuntos:
    def test_crear(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _punto(),
        ]
        r = client.post(
            '/v1/gd/puntos-atencion',
            json={'nombre': 'Sede Centro', 'direccion': 'Cra 7'},
        )
        assert r.status_code == 201

    def test_listar(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get('/v1/gd/puntos-atencion')
        assert r.status_code == 200
        assert r.json() == []

    def test_listar_con_estado(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get('/v1/gd/puntos-atencion?estado=activo')
        assert r.status_code == 200

    def test_obtener_ok(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _punto()]
        r = client.get(f'/v1/gd/puntos-atencion/{uuid4()}')
        assert r.status_code == 200

    def test_obtener_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.get(f'/v1/gd/puntos-atencion/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _punto(nombre='Nuevo'),
        ]
        r = client.patch(
            f'/v1/gd/puntos-atencion/{uuid4()}',
            json={'nombre': 'Nuevo'},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.patch(
            f'/v1/gd/puntos-atencion/{uuid4()}',
            json={'nombre': 'Nuevo'},
        )
        assert r.status_code == 404

    def test_activar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _punto(),
            _punto(estado='activo'),
        ]
        r = client.post(
            f'/v1/gd/puntos-atencion/{uuid4()}/activar',
            json={'motivo': 'reapertura programada'},
        )
        assert r.status_code == 200

    def test_inactivar_con_huerfanos_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _punto(),
        ]
        conn.fetchval.return_value = 2
        r = client.post(
            f'/v1/gd/puntos-atencion/{uuid4()}/inactivar',
            json={'motivo': 'cierre temporal'},
        )
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'perifericos_huerfanos'

    def test_cerrar_404_no_existe(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/puntos-atencion/{uuid4()}/cerrar',
            json={'motivo': 'cierre definitivo'},
        )
        assert r.status_code == 404

    def test_listar_perif_punto(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(
            f'/v1/gd/puntos-atencion/{uuid4()}/perifericos',
        )
        assert r.status_code == 200


# =============================================================================
# Periféricos
# =============================================================================
class TestPerifericosCRUD:
    def test_crear_ok(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _perif()]
        r = client.post(
            '/v1/gd/perifericos',
            json={
                'tipo_periferico': 'impresora_etiquetas',
                'nombre': 'Zebra GK420t',
                'marca': 'Zebra', 'modelo': 'GK420t',
                'serial': 'ZB-12345',
            },
        )
        assert r.status_code == 201

    def test_crear_serial_duplicado_409(self, conn, client):
        import asyncpg
        conn.fetchrow.side_effect = [
            {'activado': True},
            asyncpg.UniqueViolationError('dup'),
        ]
        r = client.post(
            '/v1/gd/perifericos',
            json={
                'tipo_periferico': 'impresora_etiquetas',
                'nombre': 'Otra Zebra', 'serial': 'ZB-1',
            },
        )
        assert r.status_code == 409

    def test_listar(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get('/v1/gd/perifericos')
        assert r.status_code == 200
        assert r.json()['total'] == 0

    def test_listar_con_filtros(self, conn, client):
        conn.fetchrow.return_value = {'activado': True}
        conn.fetch.return_value = []
        r = client.get(
            '/v1/gd/perifericos'
            f'?dependencia_id={uuid4()}&punto_atencion_id={uuid4()}'
            '&estado=activo&tipo_periferico=escaner_plano',
        )
        assert r.status_code == 200

    def test_detalle_ok(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _perif()]
        conn.fetch.side_effect = [[], []]
        r = client.get(f'/v1/gd/perifericos/{uuid4()}')
        assert r.status_code == 200

    def test_detalle_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.get(f'/v1/gd/perifericos/{uuid4()}')
        assert r.status_code == 404

    def test_patch_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(nombre='Nuevo'),
        ]
        r = client.patch(
            f'/v1/gd/perifericos/{uuid4()}',
            json={'nombre': 'Nuevo'},
        )
        assert r.status_code == 200

    def test_patch_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.patch(
            f'/v1/gd/perifericos/{uuid4()}',
            json={'nombre': 'Nuevo'},
        )
        assert r.status_code == 404

    def test_activar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(estado='inactivo'),
            _perif(estado='activo'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/activar',
            json={'motivo': 'vuelve a operación'},
        )
        assert r.status_code == 200

    def test_inactivar_en_uso_409(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _perif()]
        conn.fetchval.return_value = 3
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/inactivar',
            json={'motivo': 'mantenimiento programado'},
        )
        assert r.status_code == 409

    def test_inactivar_forzado(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(), _perif(estado='inactivo'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/inactivar',
            json={'motivo': 'mantenimiento programado', 'forzar': True},
        )
        assert r.status_code == 200

    def test_poner_mantenimiento(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(), _perif(estado='mantenimiento'),
        ]
        conn.fetchval.return_value = 0
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/poner-mantenimiento',
            json={'motivo': 'calibración periódica'},
        )
        assert r.status_code == 200

    def test_retirar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(), _perif(estado='retirado'),
        ]
        conn.fetchval.return_value = 0
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/retirar',
            json={'motivo': 'equipo dado de baja'},
        )
        assert r.status_code == 200

    def test_estado_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/activar',
            json={'motivo': 'X' * 20},
        )
        assert r.status_code == 404


# =============================================================================
# Códigos
# =============================================================================
class TestCodigos:
    def test_generar(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'numero_radicado': 'RAD-001'},
            _codigo(),
        ]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}/codigo-barras',
            json={'tipo_codigo': 'qr'},
        )
        assert r.status_code == 201

    def test_generar_radicado_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}/codigo-barras',
            json={'tipo_codigo': 'qr'},
        )
        assert r.status_code == 404

    def test_obtener_vigente(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, _codigo()]
        r = client.get(f'/v1/gd/radicados/{uuid4()}/codigo-barras')
        assert r.status_code == 200

    def test_obtener_vigente_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.get(f'/v1/gd/radicados/{uuid4()}/codigo-barras')
        assert r.status_code == 404

    def test_anular_sin_reemplazo(self, conn, client):
        cid = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': cid, 'estado': 'activo'},
            _codigo(id=cid, estado='anulado',
                    motivo_anulacion='roto al pegar'),
        ]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}'
            f'/codigo-barras/{cid}/anular',
            json={'motivo': 'roto al pegar'},
        )
        assert r.status_code == 200
        assert r.json()['estado'] == 'anulado'

    def test_anular_con_reemplazo(self, conn, client):
        cid = uuid4()
        nuevo = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': cid, 'estado': 'activo'},
            {'numero_radicado': 'RAD-001'},
            _codigo(id=nuevo),
            _codigo(id=cid, estado='reemplazado',
                    reemplazado_por_id=nuevo),
        ]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}'
            f'/codigo-barras/{cid}/anular',
            json={
                'motivo': 'cambio de formato',
                'generar_reemplazo': True,
                'tipo_codigo_reemplazo': 'codigo_barras',
            },
        )
        assert r.status_code == 200
        assert r.json()['estado'] == 'reemplazado'

    def test_anular_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}'
            f'/codigo-barras/{uuid4()}/anular',
            json={'motivo': 'X' * 20},
        )
        assert r.status_code == 404

    def test_anular_409_ya_anulado(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'anulado'},
        ]
        r = client.post(
            f'/v1/gd/radicados/{uuid4()}'
            f'/codigo-barras/{uuid4()}/anular',
            json={'motivo': 'X' * 20},
        )
        assert r.status_code == 409


# =============================================================================
# Impresión
# =============================================================================
class TestImpresion:
    def test_imprimir_etiqueta_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
            _impr(),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/imprimir-etiqueta',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_imprimir_etiqueta_perif_inactivo_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(estado='inactivo'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/imprimir-etiqueta',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_imprimir_etiqueta_radicado_404(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(), None,
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/imprimir-etiqueta',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_reimprimir_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
            _impr(intentos_reimpresion=1),
        ]
        conn.fetchval.return_value = 0
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/reimprimir-etiqueta',
            json={
                'radicado_id': str(uuid4()),
                'motivo': 'etiqueta original se dañó al pegarla',
            },
        )
        assert r.status_code == 201

    def test_reimprimir_motivo_corto_422(self, conn, client):
        # motivo < 10 chars → schema 422 (no llega al gate).
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/reimprimir-etiqueta',
            json={'radicado_id': str(uuid4()), 'motivo': 'corto'},
        )
        assert r.status_code == 422

    def test_reimprimir_excede_intentos_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
        ]
        conn.fetchval.return_value = 3
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/reimprimir-etiqueta',
            json={
                'radicado_id': str(uuid4()),
                'motivo': 'cuarto intento por papel',
            },
        )
        assert r.status_code == 409
        assert 'aprobacion' in r.json()['detail']['code']

    def test_imprimir_constancia_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(),
            {'numero_radicado': 'RAD-001'},
            _impr(tipo_impresion='constancia_radicacion'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/imprimir-constancia',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_imprimir_constancia_perif_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/imprimir-constancia',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 404

    def test_reportar_resultado_generada(self, conn, client):
        iid = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': iid, 'estado': 'encolada'},
            _impr(id=iid, estado='generada', latencia_ms=850),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/impresiones/{iid}/resultado',
            json={'estado': 'generada', 'latencia_ms': 850},
        )
        assert r.status_code == 200

    def test_reportar_resultado_fallida(self, conn, client):
        iid = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': iid, 'estado': 'encolada'},
            _impr(id=iid, estado='fallida',
                  mensaje_error='papel atascado'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/impresiones/{iid}/resultado',
            json={'estado': 'fallida',
                  'mensaje_error': 'papel atascado'},
        )
        assert r.status_code == 200

    def test_reportar_resultado_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/impresiones/{uuid4()}/resultado',
            json={'estado': 'generada', 'latencia_ms': 100},
        )
        assert r.status_code == 404

    def test_reportar_resultado_ya_actualizada_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'generada'},
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/impresiones/{uuid4()}/resultado',
            json={'estado': 'generada', 'latencia_ms': 100},
        )
        assert r.status_code == 409


# =============================================================================
# Digitalización
# =============================================================================
class TestDigit:
    def test_encolar_ok(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(),
            {'id': uuid4(), 'estado': 'radicado'},
            _digit(),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/digitalizar',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 201

    def test_encolar_perif_inactivo_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(estado='retirado'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/digitalizar',
            json={'radicado_id': str(uuid4())},
        )
        assert r.status_code == 409

    def test_encolar_radicado_404(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True}, _perif(), None,
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}/digitalizar',
            json={'radicado_id': str(uuid4()),
                  'calidad_dpi': 300, 'observacion': 'oficio'},
        )
        assert r.status_code == 404

    def test_reportar_correcta(self, conn, client):
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': did, 'estado': 'encolada'},
            _digit(id=did, estado='correcta', numero_paginas=5,
                   archivo_digital_id=uuid4()),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/digitalizaciones/{did}/resultado',
            json={'estado': 'correcta',
                  'archivo_digital_id': str(uuid4()),
                  'numero_paginas': 5},
        )
        assert r.status_code == 200

    def test_reportar_fallida(self, conn, client):
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': did, 'estado': 'encolada'},
            _digit(id=did, estado='fallida', mensaje_error='atasco'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/digitalizaciones/{did}/resultado',
            json={'estado': 'fallida', 'mensaje_error': 'atasco'},
        )
        assert r.status_code == 200

    def test_reportar_incompleta(self, conn, client):
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': did, 'estado': 'encolada'},
            _digit(id=did, estado='incompleta'),
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/digitalizaciones/{did}/resultado',
            json={'estado': 'incompleta', 'observacion': 'reintentar'},
        )
        assert r.status_code == 200

    def test_reportar_no_existe_404(self, conn, client):
        conn.fetchrow.side_effect = [{'activado': True}, None]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/digitalizaciones/{uuid4()}/resultado',
            json={'estado': 'correcta',
                  'archivo_digital_id': str(uuid4()),
                  'numero_paginas': 1},
        )
        assert r.status_code == 404

    def test_reportar_ya_actualizada_409(self, conn, client):
        conn.fetchrow.side_effect = [
            {'activado': True},
            {'id': uuid4(), 'estado': 'correcta'},
        ]
        r = client.post(
            f'/v1/gd/perifericos/{uuid4()}'
            f'/digitalizaciones/{uuid4()}/resultado',
            json={'estado': 'correcta',
                  'archivo_digital_id': str(uuid4()),
                  'numero_paginas': 1},
        )
        assert r.status_code == 409
