"""Tests mocks para services del bloque 21a (EP-021 periféricos parte 1)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import perifericos as svc


# =============================================================================
# Gate por módulo activo
# =============================================================================
class TestGateModulo:
    @pytest.mark.asyncio
    async def test_modulo_activo_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'activado': True}
        # No raise.
        await svc.assert_modulo_perifericos_activo(conn, tenant_id=uuid4())

    @pytest.mark.asyncio
    async def test_modulo_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(svc.ModuloNoActivoError):
            await svc.assert_modulo_perifericos_activo(
                conn, tenant_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_modulo_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'activado': False}
        with pytest.raises(svc.ModuloNoActivoError):
            await svc.assert_modulo_perifericos_activo(
                conn, tenant_id=uuid4(),
            )


# =============================================================================
# Puntos de atención
# =============================================================================
class TestPuntos:
    def _row_punto(self, **extra):
        base = {
            'id': uuid4(), 'nombre': 'Sede Sur', 'direccion': 'Cl 1',
            'dependencia_responsable_id': None, 'estado': 'activo',
            'motivo_cierre': None, 'metadata': {},
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }
        base.update(extra)
        return base

    @pytest.mark.asyncio
    async def test_crear(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_punto()
        r = await svc.crear_punto_atencion(
            conn, tenant_id=uuid4(), nombre='Sede Sur',
            direccion='Cl 1', dependencia_responsable_id=None,
            metadata={'piso': 2}, creado_por_user_id=uuid4(),
        )
        assert r['nombre'] == 'Sede Sur'

    @pytest.mark.asyncio
    async def test_listar_sin_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = [self._row_punto()]
        r = await svc.listar_puntos(conn, tenant_id=uuid4())
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_listar_con_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_puntos(
            conn, tenant_id=uuid4(), estado='activo',
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_punto()
        r = await svc.obtener_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_sin_campos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_punto()
        r = await svc.patch_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
            nombre=None, direccion=None,
            dependencia_responsable_id=None, metadata=None,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_con_todos_campos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_punto(nombre='Nueva')
        r = await svc.patch_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
            nombre='Nueva', direccion='Cra 7',
            dependencia_responsable_id=uuid4(),
            metadata={'horario': '8-5'},
        )
        assert r['nombre'] == 'Nueva'

    @pytest.mark.asyncio
    async def test_cambiar_estado_inactivar_sin_huerfanos(self):
        conn = AsyncMock()
        # 1er fetchrow: obtener_punto, 2do: update.
        conn.fetchrow.side_effect = [
            self._row_punto(),
            self._row_punto(estado='inactivo'),
        ]
        conn.fetchval.return_value = 0
        r = await svc.cambiar_estado_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
            nuevo_estado='inactivo', motivo='cierre temporal',
        )
        assert r['estado'] == 'inactivo'

    @pytest.mark.asyncio
    async def test_cambiar_estado_punto_huerfanos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_punto()
        conn.fetchval.return_value = 3
        with pytest.raises(ValueError, match='perifericos_huerfanos'):
            await svc.cambiar_estado_punto(
                conn, tenant_id=uuid4(), punto_id=uuid4(),
                nuevo_estado='cerrado', motivo='cierre',
            )

    @pytest.mark.asyncio
    async def test_cambiar_estado_punto_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.cambiar_estado_punto(
                conn, tenant_id=uuid4(), punto_id=uuid4(),
                nuevo_estado='cerrado', motivo='cierre',
            )

    @pytest.mark.asyncio
    async def test_cambiar_estado_activar_skip_check(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_punto(estado='inactivo'),
            self._row_punto(estado='activo'),
        ]
        r = await svc.cambiar_estado_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
            nuevo_estado='activo', motivo='reapertura',
        )
        assert r['estado'] == 'activo'

    @pytest.mark.asyncio
    async def test_listar_perif_de_punto(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_perifericos_de_punto(
            conn, tenant_id=uuid4(), punto_id=uuid4(),
        )
        assert r == []


# =============================================================================
# Periféricos CRUD
# =============================================================================
class TestPerifericos:
    def _row(self, **extra):
        base = {
            'id': uuid4(), 'tipo_periferico': 'impresora_etiquetas',
            'nombre': 'Zebra GK420t', 'marca': 'Zebra', 'modelo': 'GK420t',
            'serial': 'ZB-12345', 'dependencia_id': None,
            'punto_atencion_id': None, 'estado': 'activo',
            'motivo_cambio_estado': None, 'configuracion': {},
            'ultimo_handshake_en': None,
            'fecha_registro': datetime.now(),
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }
        base.update(extra)
        return base

    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row()
        r = await svc.crear_periferico(
            conn, tenant_id=uuid4(),
            tipo_periferico='impresora_etiquetas', nombre='Zebra',
            marca='Zebra', modelo='GK420t', serial='ZB-12345',
            dependencia_id=None, punto_atencion_id=None,
            configuracion={'velocidad': 4}, registrado_por_user_id=uuid4(),
        )
        assert r['serial'] == 'ZB-12345'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        import asyncpg as ap
        conn = AsyncMock()
        conn.fetchrow.side_effect = ap.UniqueViolationError('dup')
        with pytest.raises(ValueError, match='serial_duplicado'):
            await svc.crear_periferico(
                conn, tenant_id=uuid4(),
                tipo_periferico='impresora_etiquetas', nombre='X',
                marca=None, modelo=None, serial='dup',
                dependencia_id=None, punto_atencion_id=None,
                configuracion={}, registrado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_perifericos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_todos_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = [self._row()]
        r = await svc.listar_perifericos(
            conn, tenant_id=uuid4(),
            dependencia_id=uuid4(), punto_atencion_id=uuid4(),
            estado='activo', tipo_periferico='impresora_etiquetas',
        )
        assert len(r) == 1

    @pytest.mark.asyncio
    async def test_obtener(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row()
        r = await svc.obtener_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_detalle_ok(self):
        conn = AsyncMock()
        # detalle_periferico llama obtener (fetchrow) + 2 fetch.
        conn.fetchrow.return_value = self._row()
        conn.fetch.side_effect = [
            [{'id': uuid4(), 'tipo_operacion': 'impresion',
              'subtipo': 'etiqueta_qr', 'estado': 'generada',
              'fecha': datetime.now(), 'mensaje_error': None}],
            [{'id': uuid4(), 'tipo_operacion': 'digitalizacion',
              'subtipo': 'individual', 'estado': 'correcta',
              'fecha': datetime.now(), 'mensaje_error': None}],
        ]
        r = await svc.detalle_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r is not None
        assert len(r['ultimas_operaciones']) == 2

    @pytest.mark.asyncio
    async def test_detalle_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.detalle_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_sin_campos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row()
        r = await svc.patch_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            nombre=None, marca=None, modelo=None,
            dependencia_id=None, punto_atencion_id=None,
            configuracion=None,
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_todos_campos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row(nombre='Nuevo')
        r = await svc.patch_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            nombre='Nuevo', marca='HP', modelo='LJ',
            dependencia_id=uuid4(), punto_atencion_id=uuid4(),
            configuracion={'foo': 'bar'},
        )
        assert r['nombre'] == 'Nuevo'

    @pytest.mark.asyncio
    async def test_cambiar_estado_activar_sin_check(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row(estado='inactivo'),
            self._row(estado='activo'),
        ]
        r = await svc.cambiar_estado_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            nuevo_estado='activo', motivo='vuelve',
        )
        assert r['estado'] == 'activo'

    @pytest.mark.asyncio
    async def test_cambiar_estado_inactivar_con_encoladas(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row()
        conn.fetchval.return_value = 2
        with pytest.raises(ValueError, match='periferico_en_uso'):
            await svc.cambiar_estado_periferico(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                nuevo_estado='inactivo', motivo='mant.',
            )

    @pytest.mark.asyncio
    async def test_cambiar_estado_inactivar_forzado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row(),
            self._row(estado='inactivo'),
        ]
        r = await svc.cambiar_estado_periferico(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            nuevo_estado='inactivo', motivo='mant.', forzar=True,
        )
        assert r['estado'] == 'inactivo'

    @pytest.mark.asyncio
    async def test_cambiar_estado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.cambiar_estado_periferico(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                nuevo_estado='inactivo', motivo='X',
            )


# =============================================================================
# Códigos de barras / QR
# =============================================================================
class TestCodigos:
    @pytest.mark.asyncio
    async def test_generar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'numero_radicado': 'RAD-2026-001'},
            {
                'id': uuid4(), 'tipo_codigo': 'qr',
                'radicado_id': uuid4(), 'documento_id': None,
                'expediente_id': None,
                'valor_codigo': '/gd/verificar/abcd1234',
                'token_opaco': 'abcd1234', 'estado': 'activo',
                'reemplazado_por_id': None, 'motivo_anulacion': None,
                'fecha_generacion': datetime.now(),
                'created_at': datetime.now(),
            },
        ]
        r = await svc.generar_codigo_barras_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            tipo_codigo='qr', generado_por_user_id=uuid4(),
        )
        assert r['tipo_codigo'] == 'qr'
        # Regla absoluta: valor_codigo NO contiene PII.
        assert 'gd/verificar' in r['valor_codigo']
        assert 'RAD-' not in r['valor_codigo']

    @pytest.mark.asyncio
    async def test_generar_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.generar_codigo_barras_radicado(
                conn, tenant_id=uuid4(), radicado_id=uuid4(),
                tipo_codigo='qr', generado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_vigente_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_codigo': 'qr',
            'radicado_id': uuid4(), 'documento_id': None,
            'expediente_id': None, 'valor_codigo': '/gd/verificar/x',
            'token_opaco': 'x', 'estado': 'activo',
            'reemplazado_por_id': None, 'motivo_anulacion': None,
            'fecha_generacion': datetime.now(),
            'created_at': datetime.now(),
        }
        r = await svc.obtener_codigo_vigente_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_vigente_none(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_codigo_vigente_radicado(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_anular_sin_reemplazo(self):
        conn = AsyncMock()
        cid = uuid4()
        conn.fetchrow.side_effect = [
            {'id': cid, 'estado': 'activo'},
            {
                'id': cid, 'tipo_codigo': 'qr',
                'radicado_id': uuid4(), 'documento_id': None,
                'expediente_id': None,
                'valor_codigo': '/gd/verificar/x',
                'token_opaco': 'x', 'estado': 'anulado',
                'reemplazado_por_id': None,
                'motivo_anulacion': 'roto',
                'fecha_generacion': datetime.now(),
                'created_at': datetime.now(),
            },
        ]
        r = await svc.anular_codigo_barras(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            codigo_id=cid, motivo='roto al pegar',
            generar_reemplazo=False, tipo_codigo_reemplazo=None,
            user_id=uuid4(),
        )
        assert r['estado'] == 'anulado'

    @pytest.mark.asyncio
    async def test_anular_con_reemplazo(self):
        conn = AsyncMock()
        cid = uuid4()
        rid = uuid4()
        nuevo_id = uuid4()
        # Order: 1) existente, 2) numero_radicado para nuevo, 3) insert nuevo,
        # 4) update anulado.
        conn.fetchrow.side_effect = [
            {'id': cid, 'estado': 'activo'},
            {'numero_radicado': 'RAD-001'},
            {
                'id': nuevo_id, 'tipo_codigo': 'qr',
                'radicado_id': rid, 'documento_id': None,
                'expediente_id': None,
                'valor_codigo': '/gd/verificar/y',
                'token_opaco': 'y', 'estado': 'activo',
                'reemplazado_por_id': None, 'motivo_anulacion': None,
                'fecha_generacion': datetime.now(),
                'created_at': datetime.now(),
            },
            {
                'id': cid, 'tipo_codigo': 'qr',
                'radicado_id': rid, 'documento_id': None,
                'expediente_id': None,
                'valor_codigo': '/gd/verificar/x',
                'token_opaco': 'x', 'estado': 'reemplazado',
                'reemplazado_por_id': nuevo_id,
                'motivo_anulacion': 'cambio',
                'fecha_generacion': datetime.now(),
                'created_at': datetime.now(),
            },
        ]
        r = await svc.anular_codigo_barras(
            conn, tenant_id=uuid4(), radicado_id=rid,
            codigo_id=cid, motivo='cambio de formato',
            generar_reemplazo=True, tipo_codigo_reemplazo='codigo_barras',
            user_id=uuid4(),
        )
        assert r['estado'] == 'reemplazado'

    @pytest.mark.asyncio
    async def test_anular_codigo_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.anular_codigo_barras(
                conn, tenant_id=uuid4(), radicado_id=uuid4(),
                codigo_id=uuid4(), motivo='X',
                generar_reemplazo=False, tipo_codigo_reemplazo=None,
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_anular_codigo_ya_anulado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4(), 'estado': 'anulado'}
        with pytest.raises(ValueError, match='codigo_ya_no_activo'):
            await svc.anular_codigo_barras(
                conn, tenant_id=uuid4(), radicado_id=uuid4(),
                codigo_id=uuid4(), motivo='X',
                generar_reemplazo=False, tipo_codigo_reemplazo=None,
                user_id=uuid4(),
            )

    def test_norm_punto_none(self):
        assert svc._norm_punto(None) is None

    def test_norm_punto_metadata_str(self):
        d = svc._norm_punto({'metadata': '{"a":1}'})
        assert d['metadata'] == {'a': 1}

    def test_norm_punto_metadata_none(self):
        d = svc._norm_punto({'metadata': None})
        assert d['metadata'] == {}

    def test_norm_perif_none(self):
        assert svc._norm_perif(None) is None

    def test_norm_perif_config_str(self):
        d = svc._norm_perif({'configuracion': '{"k":2}'})
        assert d['configuracion'] == {'k': 2}

    def test_norm_perif_config_none(self):
        d = svc._norm_perif({'configuracion': None})
        assert d['configuracion'] == {}

    def test_norm_impresion_none(self):
        assert svc._norm_impresion(None) is None

    def test_norm_impresion_contenido_str(self):
        d = svc._norm_impresion({'contenido_impreso': '{"x":1}'})
        assert d['contenido_impreso'] == {'x': 1}

    def test_norm_impresion_contenido_none(self):
        d = svc._norm_impresion({'contenido_impreso': None})
        assert d['contenido_impreso'] == {}

    def test_token_opaco_unique(self):
        a = svc._token_opaco()
        b = svc._token_opaco()
        assert a != b
        assert len(a) >= 8

    def test_construir_valor_codigo_sin_pii(self):
        v = svc._construir_valor_codigo('RAD-2026-001', 'tok12345')
        assert 'tok12345' in v
        assert 'RAD' not in v  # PII excluida


# =============================================================================
# Impresión
# =============================================================================
class TestImpresion:
    def _row_impr(self, **extra):
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

    def _row_perif(self, **extra):
        base = {
            'id': uuid4(), 'tipo_periferico': 'impresora_etiquetas',
            'nombre': 'Zebra', 'marca': None, 'modelo': None,
            'serial': 'X', 'dependencia_id': None,
            'punto_atencion_id': None, 'estado': 'activo',
            'motivo_cambio_estado': None, 'configuracion': {},
            'ultimo_handshake_en': None,
            'fecha_registro': datetime.now(),
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }
        base.update(extra)
        return base

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_ok(self):
        conn = AsyncMock()
        # 1) validar periférico activo, 2) buscar radicado, 3) insert.
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
            self._row_impr(),
        ]
        r = await svc.imprimir_etiqueta(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), formato='estandar', incluir_qr=True,
            incluir_codigo_barras=True, usuario_id=uuid4(),
        )
        assert r['estado'] == 'encolada'

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.imprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), formato='estandar', incluir_qr=True,
                incluir_codigo_barras=True, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_perif_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_perif(estado='inactivo')
        with pytest.raises(ValueError, match='periferico_no_disponible'):
            await svc.imprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), formato='estandar', incluir_qr=True,
                incluir_codigo_barras=True, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [self._row_perif(), None]
        with pytest.raises(LookupError):
            await svc.imprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), formato='estandar', incluir_qr=True,
                incluir_codigo_barras=True, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_radicado_anulado_marca(self):
        """Doc 5 § 28.3 regla 4: imprime con marca pero permite."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'anulado'},
            self._row_impr(),
        ]
        # No raise — sigue.
        r = await svc.imprimir_etiqueta(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), formato='estandar', incluir_qr=True,
            incluir_codigo_barras=True, usuario_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_imprimir_etiqueta_sin_qr_es_codigo_barras(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
            self._row_impr(tipo_impresion='etiqueta_codigo_barras'),
        ]
        r = await svc.imprimir_etiqueta(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), formato='estandar', incluir_qr=False,
            incluir_codigo_barras=True, usuario_id=uuid4(),
        )
        assert r['tipo_impresion'] == 'etiqueta_codigo_barras'

    @pytest.mark.asyncio
    async def test_reimprimir_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
            self._row_impr(intentos_reimpresion=1, motivo_reimpresion='dañada'),
        ]
        conn.fetchval.return_value = 0  # previo intentos
        r = await svc.reimprimir_etiqueta(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), motivo='dañada al pegar',
            impresion_original_id=None, usuario_id=uuid4(),
        )
        assert r['intentos_reimpresion'] == 1

    @pytest.mark.asyncio
    async def test_reimprimir_excede_3_intentos(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001', 'estado': 'radicado'},
        ]
        conn.fetchval.return_value = 3  # ya hubo 3 intentos
        with pytest.raises(ValueError, match='requiere_aprobacion'):
            await svc.reimprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), motivo='cuarta intento',
                impresion_original_id=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reimprimir_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.reimprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), motivo='X' * 20,
                impresion_original_id=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reimprimir_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [self._row_perif(), None]
        with pytest.raises(LookupError):
            await svc.reimprimir_etiqueta(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), motivo='X' * 20,
                impresion_original_id=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_imprimir_constancia_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'numero_radicado': 'RAD-001'},
            self._row_impr(tipo_impresion='constancia_radicacion'),
        ]
        r = await svc.imprimir_constancia(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), formato='estandar', incluir_qr=True,
            usuario_id=uuid4(),
        )
        assert r['tipo_impresion'] == 'constancia_radicacion'

    @pytest.mark.asyncio
    async def test_imprimir_constancia_perif_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_perif(estado='mantenimiento')
        with pytest.raises(ValueError):
            await svc.imprimir_constancia(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), formato='compacta', incluir_qr=False,
                usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_imprimir_constancia_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [self._row_perif(), None]
        with pytest.raises(LookupError):
            await svc.imprimir_constancia(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), formato='estandar', incluir_qr=True,
                usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reportar_resultado_generada(self):
        conn = AsyncMock()
        iid = uuid4()
        conn.fetchrow.side_effect = [
            {'id': iid, 'estado': 'encolada'},
            self._row_impr(id=iid, estado='generada', latencia_ms=850),
        ]
        r = await svc.reportar_resultado_impresion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            impresion_id=iid, estado='generada',
            mensaje_error=None, latencia_ms=850,
        )
        assert r['estado'] == 'generada'

    @pytest.mark.asyncio
    async def test_reportar_resultado_fallida(self):
        conn = AsyncMock()
        iid = uuid4()
        conn.fetchrow.side_effect = [
            {'id': iid, 'estado': 'encolada'},
            self._row_impr(id=iid, estado='fallida',
                            mensaje_error='papel atascado'),
        ]
        r = await svc.reportar_resultado_impresion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            impresion_id=iid, estado='fallida',
            mensaje_error='papel atascado', latencia_ms=None,
        )
        assert r['estado'] == 'fallida'

    @pytest.mark.asyncio
    async def test_reportar_resultado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.reportar_resultado_impresion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                impresion_id=uuid4(), estado='generada',
                mensaje_error=None, latencia_ms=100,
            )

    @pytest.mark.asyncio
    async def test_reportar_resultado_ya_reportada(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4(), 'estado': 'generada'}
        with pytest.raises(ValueError, match='impresion_no_actualizable'):
            await svc.reportar_resultado_impresion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                impresion_id=uuid4(), estado='generada',
                mensaje_error=None, latencia_ms=100,
            )


# =============================================================================
# Digitalización
# =============================================================================
class TestDigitalizacion:
    def _row_perif(self, **extra):
        base = {
            'id': uuid4(), 'tipo_periferico': 'escaner_plano',
            'nombre': 'Epson DS-30000', 'marca': 'Epson',
            'modelo': 'DS-30000', 'serial': 'EP-1',
            'dependencia_id': None, 'punto_atencion_id': None,
            'estado': 'activo', 'motivo_cambio_estado': None,
            'configuracion': {}, 'ultimo_handshake_en': None,
            'fecha_registro': datetime.now(),
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }
        base.update(extra)
        return base

    def _row_dig(self, **extra):
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

    @pytest.mark.asyncio
    async def test_encolar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._row_perif(),
            {'id': uuid4(), 'estado': 'radicado'},
            self._row_dig(),
        ]
        r = await svc.encolar_digitalizacion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            radicado_id=uuid4(), tipo_digitalizacion='individual',
            calidad_dpi=300, observacion='oficio entrante',
            usuario_id=uuid4(),
        )
        assert r['estado'] == 'encolada'

    @pytest.mark.asyncio
    async def test_encolar_perif_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.encolar_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), tipo_digitalizacion='individual',
                calidad_dpi=300, observacion=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_encolar_perif_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._row_perif(estado='inactivo')
        with pytest.raises(ValueError):
            await svc.encolar_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), tipo_digitalizacion='individual',
                calidad_dpi=300, observacion=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_encolar_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [self._row_perif(), None]
        with pytest.raises(LookupError):
            await svc.encolar_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                radicado_id=uuid4(), tipo_digitalizacion='individual',
                calidad_dpi=300, observacion=None, usuario_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reportar_correcta(self):
        conn = AsyncMock()
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'id': did, 'estado': 'encolada'},
            self._row_dig(id=did, estado='correcta', numero_paginas=5,
                          archivo_digital_id=uuid4()),
        ]
        r = await svc.reportar_resultado_digitalizacion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            digitalizacion_id=did, estado='correcta',
            archivo_digital_id=uuid4(), numero_paginas=5,
            mensaje_error=None, observacion=None,
        )
        assert r['estado'] == 'correcta'

    @pytest.mark.asyncio
    async def test_reportar_incompleta(self):
        conn = AsyncMock()
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'id': did, 'estado': 'encolada'},
            self._row_dig(id=did, estado='incompleta'),
        ]
        r = await svc.reportar_resultado_digitalizacion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            digitalizacion_id=did, estado='incompleta',
            archivo_digital_id=None, numero_paginas=None,
            mensaje_error='atasco', observacion='reintentar',
        )
        assert r['estado'] == 'incompleta'

    @pytest.mark.asyncio
    async def test_reportar_fallida(self):
        conn = AsyncMock()
        did = uuid4()
        conn.fetchrow.side_effect = [
            {'id': did, 'estado': 'encolada'},
            self._row_dig(id=did, estado='fallida',
                          mensaje_error='hardware down'),
        ]
        r = await svc.reportar_resultado_digitalizacion(
            conn, tenant_id=uuid4(), periferico_id=uuid4(),
            digitalizacion_id=did, estado='fallida',
            archivo_digital_id=None, numero_paginas=None,
            mensaje_error='hardware down', observacion=None,
        )
        assert r['estado'] == 'fallida'

    @pytest.mark.asyncio
    async def test_reportar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.reportar_resultado_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                digitalizacion_id=uuid4(), estado='correcta',
                archivo_digital_id=uuid4(), numero_paginas=1,
                mensaje_error=None, observacion=None,
            )

    @pytest.mark.asyncio
    async def test_reportar_ya_actualizada(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4(), 'estado': 'correcta'}
        with pytest.raises(ValueError, match='no_actualizable'):
            await svc.reportar_resultado_digitalizacion(
                conn, tenant_id=uuid4(), periferico_id=uuid4(),
                digitalizacion_id=uuid4(), estado='correcta',
                archivo_digital_id=uuid4(), numero_paginas=1,
                mensaje_error=None, observacion=None,
            )
