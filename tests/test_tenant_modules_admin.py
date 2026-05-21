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
    TestProviderRequest,
    list_platform_ai_providers,
    list_tenant_modules,
    smoke_test_platform_ai_provider,
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


def test_list_platform_ai_providers_runs_inside_transaction():
    """BUGFIX-AI-PROVIDERS-RLS — el SELECT necesita ``app.support_mode='on'``
    persistente porque las policies de `platform_ai_providers` y
    `platform_secrets` condicionan sobre ese GUC. Sin transacción explícita
    el setting se descarta y el response viene vacío (la UI pinta
    placeholders "sin configurar").
    """
    conn = _async_conn()
    conn.fetch = AsyncMock(return_value=[])

    txn_calls = []
    original_transaction = conn.transaction
    def _spy(*a, **kw):
        txn_calls.append((a, kw))
        return original_transaction(*a, **kw)
    conn.transaction = _spy

    asyncio.run(list_platform_ai_providers(conn=conn))
    assert len(txn_calls) == 1


def test_update_platform_ai_provider_runs_inside_transaction():
    """Mismo contrato para el PATCH — sin la transacción, RLS rechaza el
    UPDATE y `row is None` dispara un 404 "modality not found" engañoso.
    """
    conn = _async_conn()
    # `_request()` no setea `state.actor_id`, así que el actor lookup queda
    # short-circuited (no `conn.fetchrow` para users). La única fetchrow es
    # el UPDATE ... RETURNING.
    conn.fetchrow = AsyncMock(return_value={
        'modality': 'llm', 'provider': 'unset', 'model': 'grok-4.3',
        'params': {}, 'secret_ref': None,
        'updated_at': datetime.now(timezone.utc),
    })

    txn_calls = []
    original_transaction = conn.transaction
    def _spy(*a, **kw):
        txn_calls.append((a, kw))
        return original_transaction(*a, **kw)
    conn.transaction = _spy

    asyncio.run(update_platform_ai_provider(
        modality='llm',
        payload=PlatformAIProviderUpdate(provider='unset', model='grok-4.3'),
        request=_request(),
        conn=conn,
    ))
    assert len(txn_calls) == 1


# ─── reuse_from_modality (reusar key cross-modality) ─────────────────────────


def test_update_platform_ai_provider_rejects_secret_value_and_reuse_together():
    """`secret_value` y `reuse_from_modality` son mutuamente excluyentes —
    pasar las dos es ambiguo y casi seguro un bug en el cliente.
    """
    conn = _async_conn()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(
                secret_value='xai-12345678',
                reuse_from_modality='image',
            ),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'mutually exclusive' in exc.value.detail


def test_update_platform_ai_provider_rejects_reuse_from_self():
    """reuse_from_modality == target_modality es siempre un no-op caro."""
    conn = _async_conn()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(reuse_from_modality='llm'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'cannot equal the target modality' in exc.value.detail


def test_update_platform_ai_provider_reuse_400_when_source_has_no_secret():
    """Si la modalidad fuente no tiene `secret_ref`, no hay key que reusar."""
    conn = _async_conn()
    # 1ra fetchrow: source modality lookup → existe pero secret_ref=None.
    conn.fetchrow = AsyncMock(return_value={'provider': 'grok', 'secret_ref': None})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(reuse_from_modality='image'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'has no secret configured' in exc.value.detail


def test_update_platform_ai_provider_reuse_400_on_provider_mismatch():
    """No se permite reusar la key de un provider distinto al target —
    aunque pegue técnicamente, en runtime fallaría 401 con el otro vendor.
    """
    conn = _async_conn()
    # source (image) tiene provider=openai, target (llm) trae provider=grok.
    conn.fetchrow = AsyncMock(side_effect=[
        # 1) source lookup
        {'provider': 'openai', 'secret_ref': 'ai:env:image:abc123'},
    ])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(
                provider='grok',
                reuse_from_modality='image',
            ),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'provider mismatch' in exc.value.detail


def test_update_platform_ai_provider_reuse_happy_path_copies_secret_ref():
    """Camino feliz: fuente con secret_ref, mismo provider → UPDATE copia
    el secret_ref de la fuente al target. Audit con secret_rotated=True
    y reused_from = fuente.
    """
    conn = _async_conn()
    # Sin `request.state.actor_id`, el actor lookup queda short-circuited.
    # Las fetchrow del handler en orden:
    #   1) source modality (image) → tiene secret_ref + provider=grok
    #   2) target current provider lookup (porque payload.provider es None)
    #   3) UPDATE ... RETURNING
    conn.fetchrow = AsyncMock(side_effect=[
        # source
        {'provider': 'grok', 'secret_ref': 'ai:env:image:abc123'},
        # current target provider (para validar match)
        {'provider': 'grok'},
        # UPDATE returning
        {
            'modality': 'llm', 'provider': 'grok', 'model': 'grok-4.3',
            'params': {}, 'secret_ref': 'ai:env:image:abc123',
            'updated_at': datetime.now(timezone.utc),
        },
        # hint lookup (secret_ref != None → handler busca el hint)
        {'hint': 'AB12'},
    ])

    with patch('app.influencer.admin_routes._provider_cache_invalidate'):
        result = asyncio.run(update_platform_ai_provider(
            modality='llm',
            payload=PlatformAIProviderUpdate(reuse_from_modality='image'),
            request=_request(),
            conn=conn,
        ))

    assert result.modality == 'llm'
    assert result.hint == 'AB12'


def test_audit_metadata_includes_reused_from_field():
    """AST: la metadata de audit incluye `reused_from` para distinguir
    rotaciones con key nueva (None) vs reuse cross-modality (modality
    fuente). Útil para el operador en el log.
    """
    from pathlib import Path
    src = Path('app/influencer/admin_routes.py').read_text(encoding='utf-8')
    # Hay UN único bloque metadata en el audit del provider — buscamos la key.
    assert "'reused_from': reused_from" in src


# ─── smoke_test_platform_ai_provider — smoke test endpoint ────────────────────────


def test_smoke_test_platform_ai_provider_rejects_unknown_modality():
    """Modalidad fuera de MODALITIES → 400."""
    conn = _async_conn()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(smoke_test_platform_ai_provider(
            modality='nonexistent',
            body=TestProviderRequest(prompt='hi'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'modality must be one of' in exc.value.detail


def test_smoke_test_platform_ai_provider_404_when_modality_row_missing():
    """Si la fila de la modalidad no existe (no debería pasar por el seed,
    pero el handler defensivo lo cubre), responde 404.
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(prompt='hi'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 404


def _provider_row(*, provider='grok', model='grok-4.3', hint='AB12', ciphertext=b'fake-ciphertext'):
    """Helper: fila típica del SELECT en `smoke_test_platform_ai_provider`.
    `ciphertext` defaultea a bytes opacos — el test que ejerce la cadena
    real mockea `_decrypt_secret` para no exigir un blob Fernet válido.
    """
    return {
        'provider': provider,
        'model': model,
        'params': {},
        'hint': hint,
        'ciphertext': ciphertext,
    }


def test_smoke_test_platform_ai_provider_400_when_unconfigured():
    """Si provider='unset' o hint=None o ciphertext=None, no hay nada
    que probar — 400 con mensaje accionable para el operador.
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value={
        'provider': 'unset', 'model': None, 'params': {},
        'hint': None, 'ciphertext': None,
    })
    with pytest.raises(HTTPException) as exc:
        asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(prompt='hi'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'not fully configured' in exc.value.detail


def test_smoke_test_platform_ai_provider_400_when_ciphertext_missing():
    """Si hay provider+hint pero el ciphertext está null (caso de DB
    corrupta o rotación interrumpida), 400 con el mismo mensaje
    'not fully configured' — el operador debe rotar la key.
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=_provider_row(ciphertext=None))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(prompt='hi'),
            request=_request(),
            conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'not fully configured' in exc.value.detail


def test_smoke_test_platform_ai_provider_501_for_unsupported_provider():
    """Hoy solo grok está cableado — providers no implementados responden
    501 explícito (no 500 opaco).
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=_provider_row(
        provider='anthropic', model='claude-sonnet-4-6',
    ))
    with patch('app.influencer.admin_routes._decrypt_secret', return_value='sk-fake'):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(smoke_test_platform_ai_provider(
                modality='llm',
                body=TestProviderRequest(prompt='hi'),
                request=_request(),
                conn=conn,
            ))
    assert exc.value.status_code == 501
    assert 'anthropic' in exc.value.detail


def test_smoke_test_platform_ai_provider_400_when_required_body_field_missing():
    """LLM exige `prompt`; sin él, el adapter ni se llama — devolvemos un
    response con ok=false y error claro (no 5xx).
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=_provider_row())
    # `prompt` ausente — el `_run_smoke_call` levanta ValueError que el
    # handler captura y mapea a ok=false (200 con error embebido).
    with patch('app.influencer.admin_routes._decrypt_secret', return_value='xai-fake'):
        result = asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(),
            request=_request(),
            conn=conn,
        ))
    assert result.ok is False
    assert 'prompt' in (result.error or '')
    assert result.error_class == 'ValueError'


def test_smoke_test_platform_ai_provider_happy_path_grok_llm():
    """Camino feliz: provider=grok configurado, ciphertext descifra a la
    key real, adapter devuelve un TextResult. ok=true + output.kind='text'.
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=_provider_row())

    class _FakeProvider:
        provider_name = 'grok'
        _models: dict = {}
        async def generate_text(self, *, prompt, system=None, max_tokens=512, temperature=0.7):
            from app.ai.providers.base import TextResult
            return TextResult(
                text=f'echo: {prompt}', finish_reason='stop',
                provider_meta={'tokens_used': 7}, cost_units=7.0,
                elapsed_ms=12.3,
            )

    with patch('app.influencer.admin_routes._decrypt_secret', return_value='xai-fake-key'), \
         patch('app.influencer.admin_routes._build_test_provider', return_value=_FakeProvider()) as build:
        result = asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(prompt='hola grok'),
            request=_request(),
            conn=conn,
        ))
        # Verificamos que el handler pasó la key DESCIFRADA al factory
        # (no el ciphertext crudo) — defensa contra regresiones que
        # rompan la cadena encrypt → store → fetch → decrypt → use.
        assert build.call_args.kwargs['api_key'] == 'xai-fake-key'

    assert result.ok is True
    assert result.modality == 'llm'
    assert result.provider == 'grok'
    assert result.output['kind'] == 'text'
    assert result.output['text'] == 'echo: hola grok'
    assert result.output['tokens_used'] == 7


def test_smoke_test_platform_ai_provider_translates_provider_error_to_ok_false():
    """ProviderRateLimited / ProviderContentRejected / etc → ok=false con
    `error_class` poblado. Nunca 5xx — la UI quiere mostrar el motivo
    granular sin un toast opaco.
    """
    conn = _async_conn()
    conn.fetchrow = AsyncMock(return_value=_provider_row())

    from app.ai.providers.base import ProviderRateLimited

    class _FakeProvider:
        _models: dict = {}
        async def generate_text(self, **kwargs):
            raise ProviderRateLimited('grok rate-limited (retry-after=30)')

    with patch('app.influencer.admin_routes._decrypt_secret', return_value='xai-fake'), \
         patch('app.influencer.admin_routes._build_test_provider', return_value=_FakeProvider()):
        result = asyncio.run(smoke_test_platform_ai_provider(
            modality='llm',
            body=TestProviderRequest(prompt='hi'),
            request=_request(),
            conn=conn,
        ))

    assert result.ok is False
    assert result.error_class == 'ProviderRateLimited'
    assert 'rate-limited' in (result.error or '')


def test_encrypt_decrypt_roundtrip():
    """Encryption/decryption round-trip — la fixture `AI_PROVIDER_MASTER_KEY`
    set en conftest provee una Fernet key válida. El test garantiza que
    cifrar+descifrar devuelve el plaintext exacto. Defensa contra cambios
    en el formato del cipher (e.g. switching a AES-GCM vs Fernet).
    """
    from app.influencer.admin_routes import _encrypt_secret, _decrypt_secret
    original = 'xai-this-is-a-real-looking-grok-key-1234567890'
    ct = _encrypt_secret(original)
    assert isinstance(ct, bytes)
    assert original.encode() not in ct  # no debe aparecer en claro
    assert _decrypt_secret(ct) == original


def test_decrypt_with_wrong_key_raises_500(monkeypatch):
    """Si AI_PROVIDER_MASTER_KEY cambia entre encrypt y decrypt (rotación
    de master key mal hecha), el handler responde 500 con mensaje claro
    en lugar de un crash opaco. Esto es CRÍTICO para que el operador
    detecte el problema sin ver ``InvalidToken`` en logs.
    """
    from cryptography.fernet import Fernet
    from app.influencer.admin_routes import _encrypt_secret, _decrypt_secret

    # Cifrar con la key actual del conftest…
    ct = _encrypt_secret('xai-key-1')

    # …y descifrar con OTRA key (rotación mal hecha).
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv('AI_PROVIDER_MASTER_KEY', new_key)
    # `get_settings` está cacheado con @lru_cache; invalidamos.
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc:
        _decrypt_secret(ct)
    assert exc.value.status_code == 500
    assert 'master key' in exc.value.detail.lower()

    # Restaurar para no contaminar otros tests.
    get_settings.cache_clear()
