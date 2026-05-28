"""M45 — cobertura de `copiloto_core.platform_admin.admin_routes` (antes 31%).

Cubre helpers + endpoints via invocación directa. Los endpoints usan
`async with conn.transaction()` para que el `set_config('app.support_mode',
'true', true)` sobreviva al SELECT/UPDATE, así que el FakeConn debe
exponer un `transaction()` que devuelva un async context manager no-op.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from copiloto_core.platform_admin import admin_routes as ar


# ─── FakeConn con transaction support ─────────────────────────────────────


class _NullCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, *, fetchrow=None, fetch=None, fetchval=None, execute=None,
                 raise_on_fetchrow=None):
        self.fetchrow_q = list(fetchrow or [])
        self.fetch_q = list(fetch or [])
        self.fetchval_q = list(fetchval or [])
        self.execute_q = list(execute or [])
        self.raise_on_fetchrow = raise_on_fetchrow
        self.calls: list[tuple[str, str, tuple]] = []

    def transaction(self):
        return _NullCtx()

    async def fetchrow(self, sql, *args):
        self.calls.append(('fetchrow', sql, args))
        if self.raise_on_fetchrow:
            raise self.raise_on_fetchrow
        return self.fetchrow_q.pop(0) if self.fetchrow_q else None

    async def fetch(self, sql, *args):
        self.calls.append(('fetch', sql, args))
        return self.fetch_q.pop(0) if self.fetch_q else []

    async def fetchval(self, sql, *args):
        self.calls.append(('fetchval', sql, args))
        return self.fetchval_q.pop(0) if self.fetchval_q else None

    async def execute(self, sql, *args):
        self.calls.append(('execute', sql, args))
        return self.execute_q.pop(0) if self.execute_q else 'OK'


def _fake_request(actor_id='auth0|u1', roles=('platform_owner',)):
    return SimpleNamespace(state=SimpleNamespace(actor_id=actor_id, roles=list(roles)))


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def test_hint_of_returns_last_4():
    assert ar._hint_of('sk-test-1234') == '1234'
    assert ar._hint_of('abcdef') == 'cdef'


def test_generate_secret_ref_format():
    ref = ar._generate_secret_ref('llm', 'env')
    assert ref.startswith('ai:env:llm:')
    # token random 12 hex chars
    assert len(ref.split(':')[-1]) == 12


def test_generate_secret_ref_unique():
    ref1 = ar._generate_secret_ref('llm', 'env')
    ref2 = ar._generate_secret_ref('llm', 'env')
    assert ref1 != ref2


def test_get_secret_cipher_ok():
    """Conftest setea AI_PROVIDER_MASTER_KEY → Fernet válido."""
    cipher = ar._get_secret_cipher()
    assert cipher is not None


def test_get_secret_cipher_missing(monkeypatch):
    import copiloto_core.core.config as cfg
    from fastapi import HTTPException

    real = cfg.get_settings()
    fake = SimpleNamespace(**{**real.model_dump(), 'ai_provider_master_key': None})
    monkeypatch.setattr(ar, 'get_settings', lambda: fake)
    with pytest.raises(HTTPException) as exc:
        ar._get_secret_cipher()
    assert exc.value.status_code == 500


def test_encrypt_decrypt_roundtrip():
    secret = 'my-api-key-123'
    ct = ar._encrypt_secret(secret)
    pt = ar._decrypt_secret(ct)
    assert pt == secret


def test_decrypt_invalid_token():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        ar._decrypt_secret(b'not-a-valid-fernet-blob')
    assert exc.value.status_code == 500


def test_set_support_mode_executes_set_config():
    conn = FakeConn(execute=['OK'])
    asyncio.run(ar._set_support_mode(conn, True))
    assert conn.calls[0][2] == ('app.support_mode', 'true')


def test_set_support_mode_false():
    conn = FakeConn(execute=['OK'])
    asyncio.run(ar._set_support_mode(conn, False))
    assert conn.calls[0][2] == ('app.support_mode', 'false')


def test_module_gate_cache_invalidate_noop():
    # No-op en core; verifica que no levante.
    assert ar._module_gate_cache_invalidate() is None


def test_persona_for_test_returns_anchor():
    p = ar._persona_for_test()
    assert p.persona_id == '__platform_smoke_test__'


def test_build_test_provider_grok():
    p = ar._build_test_provider('grok', api_key='sk-x', model='grok-4.3')
    from copiloto_core.ai.providers.grok import GrokProvider
    assert isinstance(p, GrokProvider)


def test_build_test_provider_not_implemented():
    with pytest.raises(NotImplementedError):
        ar._build_test_provider('openai', api_key='sk-x', model='gpt-4')


# ═══════════════════════════════════════════════════════════════════════════
# list_platform_ai_providers
# ═══════════════════════════════════════════════════════════════════════════


def test_list_platform_ai_providers_happy():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    rows = [{
        'modality': 'llm', 'provider': 'grok', 'model': 'grok-4.3',
        'params': {'timeout': 30}, 'hint': '1234', 'updated_at': now,
    }]
    conn = FakeConn(execute=['OK'], fetch=[rows])
    result = asyncio.run(ar.list_platform_ai_providers(conn))
    assert len(result.rows) == 1
    assert result.rows[0].modality == 'llm'


def test_list_platform_ai_providers_with_non_dict_params():
    """Si `params` viene como string desde JSONB (asyncpg quirk),
    el handler debe normalizarlo a {}."""
    rows = [{
        'modality': 'llm', 'provider': 'grok', 'model': None,
        'params': 'not-a-dict', 'hint': None, 'updated_at': None,
    }]
    conn = FakeConn(execute=['OK'], fetch=[rows])
    result = asyncio.run(ar.list_platform_ai_providers(conn))
    assert result.rows[0].params == {}


# ═══════════════════════════════════════════════════════════════════════════
# update_platform_ai_provider — branches
# ═══════════════════════════════════════════════════════════════════════════


def test_update_invalid_modality():
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(provider='grok')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('nope', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_empty_payload():
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_secret_value_and_reuse_mutually_exclusive():
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(secret_value='12345678', reuse_from_modality='image')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_reuse_self_modality_rejected():
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(reuse_from_modality='llm')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_with_secret_value_persists():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    conn = FakeConn(
        execute=['OK', 'OK', 'OK'],   # set_config, insert secret, audit
        fetchrow=[
            # actor_id lookup
            {'id': uuid4()},
            # UPDATE returning *
            {'modality': 'llm', 'provider': 'grok', 'model': 'grok-4.3',
             'params': {}, 'secret_ref': 'ai:env:llm:abcdef123456',
             'updated_at': now},
            # hint lookup
            {'hint': 'wxyz'},
        ],
    )
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(secret_value='new-secret-1234',
                                          provider='grok', model='grok-4.3',
                                          params={'timeout': 30})
    result = asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert result.modality == 'llm'
    assert result.hint == 'wxyz'


def test_update_with_reuse_from_modality_happy():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    conn = FakeConn(
        execute=['OK', 'OK'],
        fetchrow=[
            # actor_id
            {'id': uuid4()},
            # source modality lookup
            {'provider': 'grok', 'secret_ref': 'ai:env:image:xyz'},
            # current modality provider lookup (since payload.provider is None)
            {'provider': 'grok'},
            # UPDATE returning *
            {'modality': 'llm', 'provider': 'grok', 'model': None,
             'params': {}, 'secret_ref': 'ai:env:image:xyz',
             'updated_at': now},
            # hint
            {'hint': 'reus'},
        ],
    )
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(reuse_from_modality='image')
    result = asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert result.hint == 'reus'


def test_update_reuse_when_source_has_no_secret():
    from fastapi import HTTPException
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[
            {'id': uuid4()},          # actor_id
            {'provider': 'grok', 'secret_ref': None},  # source has no secret
        ],
    )
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(reuse_from_modality='image')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_reuse_provider_mismatch():
    from fastapi import HTTPException
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[
            {'id': uuid4()},
            {'provider': 'openai', 'secret_ref': 'ai:env:image:abc'},
        ],
    )
    req = _fake_request()
    # Cliente fuerza target=grok pero la fuente es openai → mismatch.
    payload = ar.PlatformAIProviderUpdate(reuse_from_modality='image', provider='grok')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 400


def test_update_returns_404_when_row_missing():
    from fastapi import HTTPException
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[
            {'id': uuid4()},
            None,    # UPDATE returning * → row vacío
        ],
    )
    req = _fake_request()
    payload = ar.PlatformAIProviderUpdate(provider='grok')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert exc.value.status_code == 404


def test_update_with_no_actor_id():
    """actor_id_raw None → no se llama users lookup."""
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    conn = FakeConn(
        execute=['OK', 'OK'],
        fetchrow=[
            # UPDATE returning *
            {'modality': 'llm', 'provider': 'grok', 'model': None,
             'params': {}, 'secret_ref': None, 'updated_at': now},
        ],
    )
    req = _fake_request(actor_id=None)
    payload = ar.PlatformAIProviderUpdate(provider='grok')
    result = asyncio.run(ar.update_platform_ai_provider('llm', payload, req, conn))
    assert result.provider == 'grok'


# ═══════════════════════════════════════════════════════════════════════════
# smoke_test_platform_ai_provider — branches
# ═══════════════════════════════════════════════════════════════════════════


def test_smoke_test_invalid_modality():
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request()
    body = ar.TestProviderRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.smoke_test_platform_ai_provider('nope', body, req, conn))
    assert exc.value.status_code == 400


def test_smoke_test_404_when_modality_not_in_db():
    from fastapi import HTTPException
    conn = FakeConn(execute=['OK'], fetchrow=[None])
    req = _fake_request()
    body = ar.TestProviderRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.smoke_test_platform_ai_provider('llm', body, req, conn))
    assert exc.value.status_code == 404


def test_smoke_test_400_when_unconfigured():
    from fastapi import HTTPException
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[{'provider': 'unset', 'model': None, 'params': {},
                   'hint': None, 'ciphertext': None}],
    )
    req = _fake_request()
    body = ar.TestProviderRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.smoke_test_platform_ai_provider('llm', body, req, conn))
    assert exc.value.status_code == 400


def test_smoke_test_501_for_non_grok():
    from fastapi import HTTPException
    # Encriptamos una key real con la master key de conftest.
    ct = ar._encrypt_secret('sk-fake-openai')
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[{'provider': 'openai', 'model': 'gpt-4o',
                   'params': {}, 'hint': 'xxxx', 'ciphertext': ct}],
    )
    req = _fake_request()
    body = ar.TestProviderRequest(prompt='hi')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.smoke_test_platform_ai_provider('llm', body, req, conn))
    assert exc.value.status_code == 501


# ═══════════════════════════════════════════════════════════════════════════
# list_tenant_modules
# ═══════════════════════════════════════════════════════════════════════════


def test_list_tenant_modules_no_filters():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    tid = uuid4()
    uid = uuid4()
    rows = [{
        'tenant_id': tid, 'tenant_slug': 'acme', 'tenant_name': 'ACME',
        'module': 'gd', 'enabled': True, 'plan': 'pro',
        'activated_at': now, 'activated_by': uid, 'notes': None,
    }]
    conn = FakeConn(execute=['OK'], fetch=[rows])
    req = _fake_request()
    result = asyncio.run(ar.list_tenant_modules(req, None, None, None, conn))
    assert len(result.items) == 1
    assert result.items[0].module == 'gd'


def test_list_tenant_modules_with_filters():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    rows = [{
        'tenant_id': uuid4(), 'tenant_slug': 'acme', 'tenant_name': 'ACME',
        'module': 'gd', 'enabled': True, 'plan': None,
        'activated_at': now, 'activated_by': None, 'notes': 'note',
    }]
    conn = FakeConn(execute=['OK'], fetch=[rows])
    req = _fake_request()
    result = asyncio.run(
        ar.list_tenant_modules(req, 'gd', True, 'acme', conn)
    )
    assert len(result.items) == 1


def test_list_tenant_modules_returns_empty():
    conn = FakeConn(execute=['OK'], fetch=[[]])
    req = _fake_request()
    result = asyncio.run(ar.list_tenant_modules(req, None, None, None, conn))
    assert result.items == []


def test_list_tenant_modules_handles_null_module():
    """Si un tenant no tiene ninguna fila en tenant_modules, el LEFT JOIN
    devuelve module=None, enabled=None. Handler debe traducirlos."""
    tid = uuid4()
    rows = [{
        'tenant_id': tid, 'tenant_slug': 'acme', 'tenant_name': 'ACME',
        'module': None, 'enabled': None, 'plan': None,
        'activated_at': None, 'activated_by': None, 'notes': None,
    }]
    conn = FakeConn(execute=['OK'], fetch=[rows])
    req = _fake_request()
    result = asyncio.run(ar.list_tenant_modules(req, None, None, None, conn))
    assert result.items[0].module == ''
    assert result.items[0].enabled is False


# ═══════════════════════════════════════════════════════════════════════════
# update_tenant_module
# ═══════════════════════════════════════════════════════════════════════════


def test_update_tenant_module_tenant_404():
    from fastapi import HTTPException
    tid = str(uuid4())
    conn = FakeConn(execute=['OK'], fetchrow=[None])
    req = _fake_request()
    body = ar.TenantModuleUpdate(enabled=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_tenant_module(tid, 'gd', body, req, conn))
    assert exc.value.status_code == 404


def test_update_tenant_module_activate_first_time():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    tid = str(uuid4())
    uid = uuid4()
    new_row = {
        'tenant_id': UUID(tid), 'module': 'gd', 'enabled': True, 'plan': 'pro',
        'activated_at': now, 'activated_by': uid, 'notes': None,
    }
    conn = FakeConn(
        execute=['OK', 'OK'],
        fetchrow=[
            {'id': tid, 'slug': 'acme', 'display_name': 'ACME'},   # tenant exists
            None,                                                    # no existing row
            new_row,                                                 # INSERT returning *
        ],
    )
    req = _fake_request()
    body = ar.TenantModuleUpdate(enabled=True, plan='pro')
    result = asyncio.run(ar.update_tenant_module(tid, 'gd', body, req, conn))
    assert result.enabled is True


def test_update_tenant_module_toggle_change():
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    tid = str(uuid4())
    uid = uuid4()
    updated_row = {
        'tenant_id': UUID(tid), 'module': 'gd', 'enabled': False, 'plan': None,
        'activated_at': now, 'activated_by': uid, 'notes': None,
    }
    conn = FakeConn(
        execute=['OK', 'OK'],
        fetchrow=[
            {'id': tid, 'slug': 'acme', 'display_name': 'ACME'},
            {'enabled': True},          # existing
            updated_row,
        ],
    )
    req = _fake_request()
    body = ar.TenantModuleUpdate(enabled=False)
    result = asyncio.run(ar.update_tenant_module(tid, 'gd', body, req, conn))
    assert result.enabled is False


def test_update_tenant_module_no_toggle_change_uses_update_path():
    """Si enabled == existing.enabled, va por el UPDATE simple (no INSERT)."""
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    tid = str(uuid4())
    uid = uuid4()
    updated_row = {
        'tenant_id': UUID(tid), 'module': 'gd', 'enabled': True, 'plan': 'enterprise',
        'activated_at': now, 'activated_by': uid, 'notes': 'updated',
    }
    conn = FakeConn(
        execute=['OK'],
        fetchrow=[
            {'id': tid, 'slug': 'acme', 'display_name': 'ACME'},
            {'enabled': True},     # ya estaba enabled
            updated_row,
        ],
    )
    req = _fake_request()
    body = ar.TenantModuleUpdate(enabled=True, plan='enterprise', notes='updated')
    result = asyncio.run(ar.update_tenant_module(tid, 'gd', body, req, conn))
    assert result.plan == 'enterprise'


def test_update_tenant_module_check_violation_translates_to_400():
    import asyncpg
    from fastapi import HTTPException
    tid = str(uuid4())

    class CheckConn(FakeConn):
        def __init__(self):
            super().__init__(
                execute=['OK'],
                fetchrow=[
                    {'id': tid, 'slug': 'acme', 'display_name': 'ACME'},
                    None,
                ],
            )
            self._fail_next_fetchrow = False

        async def fetchrow(self, sql, *args):
            self.calls.append(('fetchrow', sql, args))
            if 'insert into app.tenant_modules' in sql or 'returning *' in sql:
                raise asyncpg.CheckViolationError('module not in check')
            return self.fetchrow_q.pop(0) if self.fetchrow_q else None

    conn = CheckConn()
    req = _fake_request()
    body = ar.TenantModuleUpdate(enabled=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ar.update_tenant_module(tid, 'unknown_mod', body, req, conn))
    assert exc.value.status_code == 400
