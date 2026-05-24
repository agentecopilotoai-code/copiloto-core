"""Tests mocks para services del bloque 17 (expedientes EP-016)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import expedientes as svc


def _exp_row(estado='abierto', **extra):
    base = {
        'id': uuid4(), 'codigo': 'EXP-2026-001',
        'titulo': 'Expediente', 'descripcion': None,
        'dependencia_responsable_id': None,
        'serie_id': None, 'subserie_id': None,
        'estado': estado, 'fecha_apertura': datetime.now(),
        'fecha_cierre': None, 'fecha_reapertura': None,
        'fecha_transferencia': None,
        'motivo_cierre': None, 'motivo_reapertura': None,
        'motivo_transferencia': None, 'destino_transferencia': None,
        'abierto_por_user_id': uuid4(),
        'cerrado_por_user_id': None, 'reabierto_por_user_id': None,
        'metadata': {}, 'created_at': datetime.now(),
        'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _item_row(estado='vinculado', **extra):
    base = {
        'id': uuid4(), 'expediente_id': uuid4(),
        'item_tipo': 'documento', 'item_id': uuid4(),
        'orden': 0, 'estado': estado,
        'vinculado_por_user_id': uuid4(),
        'fecha_vinculacion': datetime.now(),
        'retirado_por_user_id': None,
        'fecha_retiro': None, 'motivo_retiro': None,
    }
    base.update(extra)
    return base


# =============================================================================
# CRUD
# =============================================================================
class TestExpedienteCRUD:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _exp_row()
        r = await svc.crear_expediente(
            conn, tenant_id=uuid4(), codigo='EXP-001',
            titulo='Test', descripcion=None,
            dependencia_responsable_id=None,
            serie_id=None, subserie_id=None,
            metadata={'k': 'v'}, abierto_por_user_id=uuid4(),
        )
        assert r['estado'] == 'abierto'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='codigo_ya_existe'):
            await svc.crear_expediente(
                conn, tenant_id=uuid4(), codigo='DUP',
                titulo='X', descripcion=None,
                dependencia_responsable_id=None,
                serie_id=None, subserie_id=None,
                metadata={}, abierto_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_crear_metadata_jsonb_str(self):
        conn = AsyncMock()
        row = _exp_row()
        row['metadata'] = '{}'
        conn.fetchrow.return_value = row
        r = await svc.crear_expediente(
            conn, tenant_id=uuid4(), codigo='X',
            titulo='Y', descripcion=None,
            dependencia_responsable_id=None,
            serie_id=None, subserie_id=None,
            metadata={}, abierto_por_user_id=uuid4(),
        )
        assert r['metadata'] == {}

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _exp_row()
        r = await svc.obtener_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_metadata_str(self):
        conn = AsyncMock()
        row = _exp_row()
        row['metadata'] = '{"a":1}'
        conn.fetchrow.return_value = row
        r = await svc.obtener_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r['metadata'] == {'a': 1}

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_expedientes(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_expedientes(
            conn, tenant_id=uuid4(),
            estado='abierto', dependencia_id=uuid4(),
            serie_id=uuid4(), subserie_id=uuid4(),
            codigo_like='2026', titulo_like='proyecto', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 5
        assert await svc.contar_expedientes(conn, tenant_id=uuid4()) == 5

    @pytest.mark.asyncio
    async def test_patch_abierto_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'abierto'
        conn.fetchrow.return_value = _exp_row(titulo='Nuevo')
        r = await svc.patch_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            cambios={'titulo': 'Nuevo', 'metadata': {'x': 1}},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.patch_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            cambios={'titulo': 'X'},
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_cerrado_solo_metadata(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'cerrado'
        conn.fetchrow.return_value = _exp_row(estado='cerrado')
        # Solo metadata permitido
        r = await svc.patch_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            cambios={'metadata': {'nuevo': 'valor'}},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_patch_cerrado_titulo_falla(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'cerrado'
        with pytest.raises(ValueError, match='estado_invalido_para_edicion'):
            await svc.patch_expediente(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                cambios={'titulo': 'Nuevo'},
            )

    @pytest.mark.asyncio
    async def test_patch_sin_cambios(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'abierto'
        conn.fetchrow.return_value = _exp_row()
        r = await svc.patch_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            cambios={},
        )
        assert r is not None


# =============================================================================
# Lifecycle
# =============================================================================
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_cerrar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            _exp_row(estado='cerrado'),
        ]
        r = await svc.cerrar_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            motivo='trámite completo', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'cerrado'

    @pytest.mark.asyncio
    async def test_cerrar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.cerrar_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            motivo='X' * 6, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_cerrar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'cerrado'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.cerrar_expediente(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                motivo='X' * 6, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reabrir_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'cerrado', 'fecha_reapertura': None},
            _exp_row(estado='reabierto'),
        ]
        r = await svc.reabrir_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            motivo='nueva información', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'reabierto'

    @pytest.mark.asyncio
    async def test_reabrir_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.reabrir_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reabrir_no_cerrado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'estado': 'abierto', 'fecha_reapertura': None,
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.reabrir_expediente(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                motivo='X' * 11, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reabrir_ya_reabierto(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'estado': 'cerrado', 'fecha_reapertura': datetime.now(),
        }
        with pytest.raises(ValueError, match='ya_reabierto_previamente'):
            await svc.reabrir_expediente(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                motivo='X' * 11, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_transferir_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'cerrado'},
            _exp_row(estado='transferido'),
        ]
        r = await svc.transferir_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            destino='Archivo Central', motivo='transferencia trd',
            usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'transferido'

    @pytest.mark.asyncio
    async def test_transferir_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.transferir_expediente(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            destino='X', motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_transferir_no_cerrado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'abierto'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.transferir_expediente(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                destino='X', motivo='X' * 11, usuario_actor_id=uuid4(),
            )


# =============================================================================
# Items
# =============================================================================
class TestItems:
    @pytest.mark.asyncio
    async def test_asociar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            _item_row(),
        ]
        r = await svc.asociar_item(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            item_tipo='documento', item_id=uuid4(),
            orden=1, vinculado_por_user_id=uuid4(),
        )
        assert r['estado'] == 'vinculado'

    @pytest.mark.asyncio
    async def test_asociar_expediente_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.asociar_item(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            item_tipo='documento', item_id=uuid4(),
            orden=0, vinculado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_asociar_expediente_cerrado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'cerrado'}
        with pytest.raises(ValueError, match='expediente_estado_invalido'):
            await svc.asociar_item(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                item_tipo='radicado', item_id=uuid4(),
                orden=0, vinculado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_asociar_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'abierto'},
            asyncpg.UniqueViolationError,
        ]
        with pytest.raises(ValueError, match='vinculo_duplicado'):
            await svc.asociar_item(
                conn, tenant_id=uuid4(), expediente_id=uuid4(),
                item_tipo='documento', item_id=uuid4(),
                orden=0, vinculado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_retirar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4()},  # vínculo existente
            _item_row(estado='retirado',
                       motivo_retiro='error al asociar'),
        ]
        r = await svc.retirar_item(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            item_tipo='documento', item_id=uuid4(),
            motivo='error al asociar', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'retirado'

    @pytest.mark.asyncio
    async def test_retirar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.retirar_item(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            item_tipo='documento', item_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_items(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_estado(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_items(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            estado='vinculado',
        )
        assert r == []


# =============================================================================
# Contenido
# =============================================================================
class TestContenido:
    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_contenido(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_ok_con_items(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _exp_row()
        conn.fetch.return_value = [
            _item_row(item_tipo='documento'),
            _item_row(item_tipo='radicado'),
            _item_row(item_tipo='documento', estado='retirado'),
        ]
        r = await svc.obtener_contenido(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r['totales_por_tipo'] == {'documento': 1, 'radicado': 1}
        assert len(r['items_vinculados']) == 2
        assert len(r['items_retirados']) == 1

    @pytest.mark.asyncio
    async def test_ok_vacio(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _exp_row()
        conn.fetch.return_value = []
        r = await svc.obtener_contenido(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r['totales_por_tipo'] == {}
        assert r['items_vinculados'] == []
