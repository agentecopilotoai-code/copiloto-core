"""Tests funcionales para los handlers de TASK-INFLU-019 en
``app/influencer/admin_routes.py``.

Cubren ``list_tenant_modules`` (GET /platform/tenant-modules) y
``update_tenant_module`` (PATCH /platform/tenant-modules/{tenant_id}/{module})
con AsyncMock para asyncpg + audit, sin red ni DB real.

Diseño: ejercer todos los caminos del query — empty result, filtros,
toggle on/off, error 404 cuando tenant no existe, error 409 cuando faltan
proveedores IA para activar influencer, y la rama que solo actualiza
plan/notes sin tocar `enabled`. El objetivo es subir cobertura backend
≥92% (gate de CI).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.influencer.admin_routes import (
    PlatformAIProviderUpdate,
    TenantModuleUpdate,
    list_platform_ai_providers,
    list_tenant_modules,
    update_platform_ai_provider,
    update_tenant_module,
)


def _request(user_id=None):
    """Mini Starlette-like request con state.user_id (lo que audit usa)."""
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id or uuid4()))


class _NoOpTxn:
    """Async context manager no-op para mockear ``conn.transaction()``.

    Los handlers ahora abren ``async with conn.transaction():`` para anclar
    ``set_config('app.support_mode', 'on', true)`` (transaction-local) a la
    misma transacción que el resto de queries. ``AsyncMock`` no provee
    ``__aenter__``/``__aexit__`` por defecto en métodos sync (que es como
    asyncpg expone ``.transaction()``), entonces el test plumbea este stub.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _async_conn(**kwargs):
    """AsyncMock con ``conn.transaction()`` simulado como CM no-op.

    El handler real corre todo dentro de ``async with conn.transaction()``
    para que ``set_config(..., true)`` persista; los tests no necesitan
    semántica transaccional real, solo que el CM no rompa.
    """
    conn = AsyncMock(**kwargs)
    conn.transaction = lambda *a, **kw: _NoOpTxn()
    return conn


def _module_row(*, tenant_id, slug, name, module, enabled, when=None):
    """Una fila típica del JOIN en list_tenant_modules."""
    return {
        'tenant_id': tenant_id,
        'tenant_slug': slug,
        'tenant_name': name,
        'module': module,
        'enabled': enabled,
        'plan': None,
        'activated_at': when or datetime.now(timezone.utc),
        'activated_by': uuid4(),
        'notes': None,
    }


@pytest.fixture(autouse=True)
def _patch_audit():
    """Audit dispara escrituras async — mock para no requerir DB."""
    with patch('app.influencer.admin_routes.audit', new=AsyncMock(return_value=None)):
        yield


@pytest.fixture(autouse=True)
def _patch_set_support_mode():
    """`_set_support_mode` setea config session-local — mock para no
    tocar la conexión.
    """
    with patch(
        'app.influencer.admin_routes._set_support_mode',
        new=AsyncMock(return_value=None),
    ):
        yield


# ─── list_tenant_modules ─────────────────────────────────────────────────────


def test_list_tenant_modules_empty():
    """Lista sin filtros y DB vacía retorna response con items=[]."""
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    result = asyncio.run(list_tenant_modules(_request(), conn=conn))
    assert result.items == []
    assert conn.fetch.called


def test_list_tenant_modules_returns_rows_with_display_name():
    """BUGFIX-PLATFORM-ROUTES — el query usa `t.display_name as tenant_name`
    (antes era `t.name` que no existe en `app.tenants`). Verificamos que
    `tenant_name` viene del SELECT con la columna correcta.
    """
    tenant_id = uuid4()
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[
        _module_row(
            tenant_id=tenant_id, slug='clinica-x', name='Clínica X',
            module='influencer', enabled=True,
        ),
        _module_row(
            tenant_id=tenant_id, slug='clinica-x', name='Clínica X',
            module='chatbot', enabled=False,
        ),
    ])

    result = asyncio.run(list_tenant_modules(_request(), conn=conn))
    assert len(result.items) == 2
    assert result.items[0].tenant_name == 'Clínica X'
    assert result.items[0].module == 'influencer'
    assert result.items[0].enabled is True
    assert result.items[1].module == 'chatbot'
    assert result.items[1].enabled is False


def test_list_tenant_modules_filters_by_module():
    """Pasar `module='influencer'` añade un WHERE."""
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    asyncio.run(list_tenant_modules(_request(), module='influencer', conn=conn))
    call_args = conn.fetch.call_args
    sql = call_args.args[0]
    params = call_args.args[1:]
    assert 'tm.module = $' in sql
    assert 'influencer' in params


def test_list_tenant_modules_filters_by_enabled_bool():
    """`enabled=True` se traduce a `tm.enabled = $N`."""
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    asyncio.run(list_tenant_modules(_request(), enabled=True, conn=conn))
    call_args = conn.fetch.call_args
    sql = call_args.args[0]
    params = call_args.args[1:]
    assert 'tm.enabled = $' in sql
    assert True in params


def test_list_tenant_modules_filters_by_tenant_search_uses_display_name():
    """BUGFIX-PLATFORM-ROUTES — el WHERE de búsqueda usa
    `lower(t.display_name)` (antes era `t.name`). Verificamos el SQL.
    """
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    asyncio.run(list_tenant_modules(_request(), tenant_search='Clinica', conn=conn))
    sql = conn.fetch.call_args.args[0]
    assert 'lower(t.display_name)' in sql, (
        f'tenant_search debe filtrar por display_name. SQL actual: {sql}'
    )
    assert 'lower(t.slug)' in sql
    # No queda referencia a la columna inexistente.
    assert 't.name' not in sql


# ─── update_tenant_module ────────────────────────────────────────────────────


def test_update_tenant_module_404_when_tenant_not_found():
    """Si `app.tenants` no tiene el id, devuelve 404 con detail explícito."""
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # tenant lookup retorna None

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_tenant_module(
            tenant_id=str(uuid4()),
            module='chatbot',
            body=TenantModuleUpdate(enabled=True),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 404
    assert 'tenant not found' in exc.value.detail


def test_update_tenant_module_activates_new_module():
    """Camino feliz: tenant existe, no había fila → INSERT con
    activated_at=now(), enabled=true.
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    # 1ra llamada: SELECT del tenant. 2da: SELECT existing (None → activated_changed=True).
    # 3ra: INSERT ... ON CONFLICT ... RETURNING * → row final.
    conn.fetchrow = AsyncMock(side_effect=[
        tenant_row,
        None,  # no existía fila previa
        {
            'tenant_id': tenant_id,
            'module': 'chatbot',
            'enabled': True,
            'plan': None,
            'activated_at': datetime.now(timezone.utc),
            'activated_by': uuid4(),
            'notes': None,
        },
    ])

    result = asyncio.run(update_tenant_module(
        tenant_id=str(tenant_id),
        module='chatbot',
        body=TenantModuleUpdate(enabled=True, notes='activación inicial'),
        request=_request(),
        conn=conn,
    ))
    assert result.enabled is True
    assert result.module == 'chatbot'
    assert result.tenant_slug == 'demo'
    # BUGFIX — tenant_name viene de display_name (no de t['name']).
    assert result.tenant_name == 'Demo Org'


def test_update_tenant_module_deactivates_module():
    """Toggle OFF: existía con enabled=True → INSERT ... ON CONFLICT UPDATE
    con enabled=False y activated_at refrescado.
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    conn.fetchrow = AsyncMock(side_effect=[
        tenant_row,
        {'enabled': True},  # existía enabled=true, vamos a desactivar
        {
            'tenant_id': tenant_id,
            'module': 'chatbot',
            'enabled': False,
            'plan': None,
            'activated_at': datetime.now(timezone.utc),
            'activated_by': uuid4(),
            'notes': None,
        },
    ])

    result = asyncio.run(update_tenant_module(
        tenant_id=str(tenant_id),
        module='chatbot',
        body=TenantModuleUpdate(enabled=False),
        request=_request(),
        conn=conn,
    ))
    assert result.enabled is False


def test_update_tenant_module_only_metadata_no_state_change():
    """Si existía con `enabled=True` y se vuelve a pedir `enabled=True`,
    solo se hace UPDATE de plan/notes (no INSERT, no audit, no
    invalidación de cache).
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    conn.fetchrow = AsyncMock(side_effect=[
        tenant_row,
        {'enabled': True},  # existía igual
        {
            'tenant_id': tenant_id,
            'module': 'chatbot',
            'enabled': True,
            'plan': 'pro',  # nuevo valor
            'activated_at': datetime.now(timezone.utc),
            'activated_by': uuid4(),
            'notes': 'plan upgrade',
        },
    ])

    result = asyncio.run(update_tenant_module(
        tenant_id=str(tenant_id),
        module='chatbot',
        body=TenantModuleUpdate(enabled=True, plan='pro', notes='plan upgrade'),
        request=_request(),
        conn=conn,
    ))
    assert result.plan == 'pro'
    assert result.notes == 'plan upgrade'


def test_update_tenant_module_influencer_requires_ai_providers():
    """Pre-flight check: activar 'influencer' exige que `app.platform_ai_providers`
    tenga las modalidades `llm` e `image` configuradas. Si faltan, 409.
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=tenant_row)
    conn.fetch = AsyncMock(return_value=[])  # ninguna modalidad configurada

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_tenant_module(
            tenant_id=str(tenant_id),
            module='influencer',
            body=TenantModuleUpdate(enabled=True),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 409
    assert 'ai_providers_not_configured' in exc.value.detail


def test_update_tenant_module_influencer_ok_when_providers_present():
    """Si los proveedores IA están configurados, activar influencer pasa
    el pre-flight check y continúa al INSERT normal.
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    conn.fetchrow = AsyncMock(side_effect=[
        tenant_row,
        None,  # no existía fila previa
        {
            'tenant_id': tenant_id,
            'module': 'influencer',
            'enabled': True,
            'plan': None,
            'activated_at': datetime.now(timezone.utc),
            'activated_by': uuid4(),
            'notes': None,
        },
    ])
    conn.fetch = AsyncMock(return_value=[
        {'modality': 'llm'},
        {'modality': 'image'},
    ])

    with patch('app.influencer.admin_routes._module_gate_cache_invalidate') as inv:
        result = asyncio.run(update_tenant_module(
            tenant_id=str(tenant_id),
            module='influencer',
            body=TenantModuleUpdate(enabled=True),
            request=_request(),
            conn=conn,
        ))
        assert result.enabled is True
        # Cache invalidation se llama cuando hay cambio de estado.
        assert inv.called


# ─── list_platform_ai_providers (TASK-INFLU-002) ─────────────────────────────


def test_list_platform_ai_providers_empty():
    """Sin filas en la DB el response trae rows=[]."""
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    result = asyncio.run(list_platform_ai_providers(conn=conn))
    assert result.rows == []


def test_list_platform_ai_providers_returns_rows_without_secrets():
    """El response solo expone `hint` (últimos 4 chars), nunca `secret_value`
    ni `ciphertext`. Confirmación de la defensa contra leak via API.
    """
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[
        {
            'modality': 'llm',
            'provider': 'openai',
            'model': 'gpt-4o-mini',
            'params': {'temperature': 0.7},
            'hint': 'sk-…AB12',
            'updated_at': datetime.now(timezone.utc),
        },
        {
            'modality': 'image',
            'provider': 'unset',
            'model': None,
            'params': None,
            'hint': None,
            'updated_at': None,
        },
    ])

    result = asyncio.run(list_platform_ai_providers(conn=conn))
    assert len(result.rows) == 2
    # Primer row: openai con params dict y hint.
    assert result.rows[0].modality == 'llm'
    assert result.rows[0].provider == 'openai'
    assert result.rows[0].params == {'temperature': 0.7}
    assert result.rows[0].hint == 'sk-…AB12'
    # Segundo row: unset con params=None se traduce a dict vacío.
    assert result.rows[1].modality == 'image'
    assert result.rows[1].provider == 'unset'
    assert result.rows[1].params == {}
    assert result.rows[1].hint is None
    assert result.rows[1].updated_at is None


# ─── update_platform_ai_provider — paths de validación ──────────────────────


def test_update_platform_ai_provider_rejects_unknown_modality():
    """Si la modalidad no está en MODALITIES, 400 con mensaje claro."""
    conn = _async_conn()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='nonexistent_modality',
            payload=PlatformAIProviderUpdate(provider='openai'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'modality must be one of' in exc.value.detail


def test_update_platform_ai_provider_rejects_empty_payload():
    """Si NO se pasa ningún campo, 400 con 'at least one field must be
    provided'.
    """
    conn = _async_conn()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'at least one field must be provided' in exc.value.detail


def test_update_platform_ai_provider_404_when_row_missing():
    """Caso defensivo — si el UPDATE no encuentra fila (no debería pasar
    porque la migración seedea 5 modalidades, pero el handler maneja el
    caso), responde 404.
    """
    conn = _async_conn()
    # actor lookup → None (no resolvemos UUID), UPDATE → None.
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(provider='openai'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 404
    assert 'llm' in exc.value.detail


# ─── BUGFIX-RLS-TXN: `update_tenant_module` debe correr todo dentro de un
#     `async with conn.transaction():`. Sin esa transacción explícita,
#     `set_config('app.support_mode', 'on', true)` es transaction-local y se
#     descarta antes del INSERT → RLS rechaza el INSERT con
#     `InsufficientPrivilegeError: new row violates row-level security
#     policy for table "tenant_modules"`. Estos tests son defensivos para
#     que un refactor futuro no rompa ese contrato sin que falle CI.


def test_update_tenant_module_runs_inside_transaction():
    """``conn.transaction()`` se invoca exactamente una vez al activar un
    módulo. Garantiza que el handler abre la transacción explícita —
    requerida para que ``set_config('app.support_mode', 'on', true)``
    persista a lo largo del SELECT/INSERT.
    """
    tenant_id = uuid4()
    tenant_row = {'id': tenant_id, 'slug': 'demo', 'display_name': 'Demo Org'}

    conn = _async_conn()
    conn.fetchrow = AsyncMock(side_effect=[
        tenant_row,
        None,
        {
            'tenant_id': tenant_id, 'module': 'chatbot', 'enabled': True,
            'plan': None, 'activated_at': datetime.now(timezone.utc),
            'activated_by': uuid4(), 'notes': None,
        },
    ])

    txn_calls = []
    original_transaction = conn.transaction
    def _spy(*a, **kw):
        txn_calls.append((a, kw))
        return original_transaction(*a, **kw)
    conn.transaction = _spy

    asyncio.run(update_tenant_module(
        tenant_id=str(tenant_id),
        module='chatbot',
        body=TenantModuleUpdate(enabled=True),
        request=_request(),
        conn=conn,
    ))
    assert len(txn_calls) == 1, (
        'update_tenant_module debe abrir exactamente un `async with '
        'conn.transaction():` que envuelve `set_config` + INSERT/UPDATE.'
    )


def test_list_tenant_modules_runs_inside_transaction():
    """Mismo contrato para ``list_tenant_modules`` — aunque el SELECT no
    dispare RLS de escritura, mantener el patrón consistente facilita razonar
    sobre el lifecycle del config session-local.
    """
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    txn_calls = []
    original_transaction = conn.transaction
    def _spy(*a, **kw):
        txn_calls.append((a, kw))
        return original_transaction(*a, **kw)
    conn.transaction = _spy

    asyncio.run(list_tenant_modules(_request(), conn=conn))
    assert len(txn_calls) == 1
