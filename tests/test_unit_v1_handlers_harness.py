"""M45 — cobertura de handlers `/v1/*` invocándolos directamente.

En lugar de pasar por TestClient + FastAPI dep injection (que pelea con
el lifespan que abre Postgres real al entrar al context), invocamos las
funciones del handler directamente con Request mockeada + FakeConn.
Es feo pero MUCHO más rápido y predecible. Cubre TODOS los code paths
de los handlers sin hidratar el dependant tree de FastAPI.

Sub-objetivo: subir total coverage del backend de ~69% a >95%.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


# ─── FakeConn — asyncpg.Connection mock con queries grabadas ──────────────


class FakeConn:
    def __init__(self, *, fetchrow=None, fetch=None, fetchval=None, execute=None,
                 raise_on=None):
        self.fetchrow_queue = list(fetchrow or [])
        self.fetch_queue = list(fetch or [])
        self.fetchval_queue = list(fetchval or [])
        self.execute_queue = list(execute or [])
        # raise_on = {'fetchrow': ExceptionInstance, ...} — levanta en lugar
        # de pop del queue (útil para simular UniqueViolationError).
        self.raise_on = raise_on or {}
        self.calls: list[tuple[str, str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append(('fetchrow', sql, args))
        if 'fetchrow' in self.raise_on:
            raise self.raise_on['fetchrow']
        return self.fetchrow_queue.pop(0) if self.fetchrow_queue else None

    async def fetch(self, sql, *args):
        self.calls.append(('fetch', sql, args))
        if 'fetch' in self.raise_on:
            raise self.raise_on['fetch']
        return self.fetch_queue.pop(0) if self.fetch_queue else []

    async def fetchval(self, sql, *args):
        self.calls.append(('fetchval', sql, args))
        if 'fetchval' in self.raise_on:
            raise self.raise_on['fetchval']
        return self.fetchval_queue.pop(0) if self.fetchval_queue else None

    async def execute(self, sql, *args):
        self.calls.append(('execute', sql, args))
        if 'execute' in self.raise_on:
            raise self.raise_on['execute']
        return self.execute_queue.pop(0) if self.execute_queue else 'OK'


def _fake_request(**state) -> SimpleNamespace:
    """SimpleNamespace que mimica Request: tiene .state + .headers + .cookies + .client."""
    defaults = {
        'actor_type': 'user',
        'actor_id': 'auth0|u1',
        'roles': [],
        'tenant_id': None,
        'support_mode': False,
        'email': 'u@x.co',
        'name': 'U',
        'session_jti': 'jti-abc',
        'token_iat': 1700000000,
    }
    defaults.update(state)
    return SimpleNamespace(
        state=SimpleNamespace(**defaults),
        headers={'user-agent': 'curl/8'},
        cookies={},
        client=SimpleNamespace(host='127.0.0.1'),
    )


# ═══════════════════════════════════════════════════════════════════════════
# me_utils
# ═══════════════════════════════════════════════════════════════════════════


def test_user_display_name_from_request_uses_name():
    from app.api.v1._helpers.me_utils import _user_display_name_from_request
    req = _fake_request(name='Alice')
    assert _user_display_name_from_request(req) == 'Alice'


def test_user_display_name_from_request_falls_to_nickname():
    from app.api.v1._helpers.me_utils import _user_display_name_from_request
    req = _fake_request(name=None, nickname='alice123')
    assert _user_display_name_from_request(req) == 'alice123'


def test_user_display_name_from_request_falls_to_email_local():
    from app.api.v1._helpers.me_utils import _user_display_name_from_request
    req = _fake_request(name=None, email='bob@x.co')
    # SimpleNamespace doesn't have `nickname` attr → getattr returns None.
    assert _user_display_name_from_request(req) == 'bob'


def test_user_display_name_from_request_falls_to_actor_id():
    from app.api.v1._helpers.me_utils import _user_display_name_from_request
    req = _fake_request(name=None, email=None, actor_id='sub-xyz')
    assert _user_display_name_from_request(req) == 'sub-xyz'


def test_user_display_name_from_request_fallback_usuario():
    from app.api.v1._helpers.me_utils import _user_display_name_from_request
    req = _fake_request(name=None, email=None, actor_id=None)
    assert _user_display_name_from_request(req) == 'usuario'


def test_current_user_id_returns_cached():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    cached_id = uuid4()
    req = _fake_request()
    req.state.user_id = cached_id
    conn = FakeConn()
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == cached_id


def test_current_user_id_returns_none_when_not_user():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    req = _fake_request(actor_type='service')
    conn = FakeConn()
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result is None


def test_current_user_id_returns_none_when_no_actor_id():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    req = _fake_request(actor_id=None)
    conn = FakeConn()
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result is None


def test_current_user_id_looks_up_existing():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid = uuid4()
    req = _fake_request()
    conn = FakeConn(fetchrow=[{'id': uid}])
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == uid
    assert req.state.user_id == uid


def test_current_user_id_creates_lazy_when_missing():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid = uuid4()
    req = _fake_request()
    conn = FakeConn(fetchrow=[None, {'id': uid}])
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == uid


def test_current_user_id_creates_lazy_falls_to_default_email():
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid = uuid4()
    req = _fake_request(email=None)
    conn = FakeConn(fetchrow=[None, {'id': uid}])
    asyncio.run(current_user_id_from_request(req, conn))
    # email argumento al insert es '{actor_id}@auth.local'
    insert_call = conn.calls[1]
    assert insert_call[2][1] == 'auth0|u1@auth.local'


def test_require_current_user_raises_401_when_none():
    from app.api.v1._helpers.me_utils import _require_current_user
    from fastapi import HTTPException
    req = _fake_request(actor_id=None)
    conn = FakeConn()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require_current_user(req, conn))
    assert exc.value.status_code == 401


def test_require_current_user_returns_id():
    from app.api.v1._helpers.me_utils import _require_current_user
    uid = uuid4()
    req = _fake_request()
    conn = FakeConn(fetchrow=[{'id': uid}])
    result = asyncio.run(_require_current_user(req, conn))
    assert result == uid


def test_load_user_preferences_lazy_creates():
    from app.api.v1._helpers.me_utils import _load_user_preferences_row
    uid = uuid4()
    prefs_row = {'user_id': uid, 'locale': 'es-CO', 'timezone': 'America/Bogota'}
    conn = FakeConn(fetchrow=[None, prefs_row], execute=['OK'])
    result = asyncio.run(_load_user_preferences_row(conn, uid))
    assert result == prefs_row
    # ejecutó INSERT lazy
    assert any('insert into app.user_preferences' in c[1] for c in conn.calls)


def test_load_user_preferences_returns_existing():
    from app.api.v1._helpers.me_utils import _load_user_preferences_row
    uid = uuid4()
    prefs_row = {'user_id': uid, 'locale': 'es-CO'}
    conn = FakeConn(fetchrow=[prefs_row])
    result = asyncio.run(_load_user_preferences_row(conn, uid))
    assert result == prefs_row


def test_session_id_from_request_uses_jti():
    from app.api.v1._helpers.me_utils import _session_id_from_request
    req = _fake_request(session_jti='jwt-jti-1')
    assert _session_id_from_request(req) == 'jwt-jti-1'


def test_session_id_from_request_fallback_hash():
    from app.api.v1._helpers.me_utils import _session_id_from_request
    req = _fake_request(session_jti=None, token_iat=1234567890)
    sid = _session_id_from_request(req)
    assert sid is not None
    assert sid.startswith('iat-')


def test_session_id_from_request_returns_none_when_no_data():
    from app.api.v1._helpers.me_utils import _session_id_from_request
    req = _fake_request(session_jti=None, actor_id=None, token_iat=None)
    assert _session_id_from_request(req) is None


def test_record_auth_session_inserts():
    from app.api.v1._helpers.me_utils import record_auth_session
    uid = uuid4()
    req = _fake_request(session_jti='sid-1')
    conn = FakeConn(execute=['OK'])
    sid = asyncio.run(record_auth_session(req, conn, uid))
    assert sid == 'sid-1'
    assert len(conn.calls) == 1
    insert_call = conn.calls[0]
    assert 'insert into app.auth_sessions' in insert_call[1]


def test_record_auth_session_no_id_returns_none():
    from app.api.v1._helpers.me_utils import record_auth_session
    uid = uuid4()
    req = _fake_request(session_jti=None, actor_id=None, token_iat=None)
    conn = FakeConn()
    sid = asyncio.run(record_auth_session(req, conn, uid))
    assert sid is None
    assert conn.calls == []


def test_record_auth_session_no_user_agent():
    from app.api.v1._helpers.me_utils import record_auth_session
    uid = uuid4()
    req = _fake_request(session_jti='sid-x')
    req.headers = {}  # sin user-agent
    conn = FakeConn(execute=['OK'])
    asyncio.run(record_auth_session(req, conn, uid))
    assert conn.calls[0][2][2] is None  # user_agent param es None


# ═══════════════════════════════════════════════════════════════════════════
# me_handlers — invocados directamente
# ═══════════════════════════════════════════════════════════════════════════


def test_get_my_profile_happy_path():
    from app.api.v1.handlers.me_handlers import get_my_profile
    uid = uuid4()
    conn = FakeConn(
        fetchrow=[
            {'id': uid},
            {'email': 'u@x.co', 'display_name': 'U', 'mfa_enabled': False,
             'last_login_at': None},
            {'user_id': uid, 'display_name': 'U', 'phone': None,
             'locale': 'es-CO', 'timezone': 'America/Bogota',
             'theme_override': None, 'notification_matrix': '{}',
             'auth0_synced_at': None},
        ],
    )
    req = _fake_request()
    result = asyncio.run(get_my_profile(req, conn))
    assert result['email'] == 'u@x.co'


def test_get_my_profile_404_when_user_row_missing():
    from app.api.v1.handlers.me_handlers import get_my_profile
    from fastapi import HTTPException
    uid = uuid4()
    conn = FakeConn(fetchrow=[{'id': uid}, None])
    req = _fake_request()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_my_profile(req, conn))
    assert exc.value.status_code == 404


def test_patch_my_profile_400_empty():
    from app.api.v1.handlers.me_handlers import patch_my_profile, ProfilePatchRequest
    from fastapi import HTTPException
    uid = uuid4()
    conn = FakeConn(fetchrow=[{'id': uid}])
    req = _fake_request()
    body = ProfilePatchRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_my_profile(body, req, conn))
    assert exc.value.status_code == 400


def test_patch_my_profile_happy():
    from app.api.v1.handlers.me_handlers import patch_my_profile, ProfilePatchRequest
    uid = uuid4()
    prefs = {'user_id': uid, 'display_name': 'X', 'phone': None,
             'locale': 'es-CO', 'timezone': 'America/Bogota',
             'theme_override': None, 'notification_matrix': '{}',
             'auth0_synced_at': None}
    user_row = {'email': 'u@x.co', 'display_name': 'U', 'mfa_enabled': False,
                'last_login_at': None}
    conn = FakeConn(
        fetchrow=[
            {'id': uid},          # _require_current_user
            prefs,                 # _load_user_preferences_row 1
            user_row,              # final user lookup
            prefs,                 # final prefs reload
        ],
        execute=['OK', 'OK'],     # update + audit
    )
    req = _fake_request()
    body = ProfilePatchRequest(display_name='X')
    result = asyncio.run(patch_my_profile(body, req, conn))
    assert result is not None


def test_get_my_preferences():
    from app.api.v1.handlers.me_handlers import get_my_preferences
    uid = uuid4()
    prefs = {'user_id': uid, 'locale': 'es-MX', 'timezone': 'America/Mexico_City',
             'theme_override': 'dark', 'notification_matrix': '{}'}
    conn = FakeConn(fetchrow=[{'id': uid}, prefs])
    req = _fake_request()
    result = asyncio.run(get_my_preferences(req, conn))
    assert result == {'locale': 'es-MX', 'timezone': 'America/Mexico_City',
                       'theme_override': 'dark'}


def test_patch_my_preferences_happy():
    from app.api.v1.handlers.me_handlers import patch_my_preferences, PreferencesPatchRequest
    uid = uuid4()
    prefs = {'user_id': uid, 'locale': 'es-CO', 'timezone': 'America/Bogota',
             'theme_override': 'light', 'notification_matrix': '{}'}
    conn = FakeConn(
        fetchrow=[{'id': uid}, prefs, prefs],
        execute=['OK', 'OK'],
    )
    req = _fake_request()
    body = PreferencesPatchRequest(theme_override='light')
    result = asyncio.run(patch_my_preferences(body, req, conn))
    assert result['theme_override'] == 'light'


def test_patch_my_preferences_422_invalid_theme():
    from app.api.v1.handlers.me_handlers import patch_my_preferences, PreferencesPatchRequest
    from fastapi import HTTPException
    uid = uuid4()
    conn = FakeConn(fetchrow=[{'id': uid}])
    req = _fake_request()
    body = PreferencesPatchRequest(theme_override='rainbow')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_my_preferences(body, req, conn))
    assert exc.value.status_code == 422


def test_patch_my_preferences_400_empty():
    from app.api.v1.handlers.me_handlers import patch_my_preferences, PreferencesPatchRequest
    from fastapi import HTTPException
    uid = uuid4()
    conn = FakeConn(fetchrow=[{'id': uid}])
    req = _fake_request()
    body = PreferencesPatchRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_my_preferences(body, req, conn))
    assert exc.value.status_code == 400


def test_get_my_notifications_str_matrix():
    from app.api.v1.handlers.me_handlers import get_my_notifications
    uid = uuid4()
    matrix = {'email': {'invites': True}}
    prefs = {'user_id': uid, 'notification_matrix': json.dumps(matrix),
             'locale': 'es-CO', 'timezone': 'America/Bogota', 'theme_override': None}
    conn = FakeConn(fetchrow=[{'id': uid}, prefs])
    req = _fake_request()
    result = asyncio.run(get_my_notifications(req, conn))
    assert result == {'notification_matrix': matrix}


def test_get_my_notifications_dict_matrix():
    from app.api.v1.handlers.me_handlers import get_my_notifications
    uid = uuid4()
    matrix = {'sms': {'invites': False}}
    prefs = {'user_id': uid, 'notification_matrix': matrix,
             'locale': 'es-CO', 'timezone': 'America/Bogota', 'theme_override': None}
    conn = FakeConn(fetchrow=[{'id': uid}, prefs])
    req = _fake_request()
    result = asyncio.run(get_my_notifications(req, conn))
    assert result == {'notification_matrix': matrix}


def test_patch_my_notifications_happy():
    from app.api.v1.handlers.me_handlers import patch_my_notifications, NotificationsPatchRequest
    uid = uuid4()
    new = {'sms': {'invites': True}}
    prefs = {'user_id': uid, 'notification_matrix': new,
             'locale': 'es-CO', 'timezone': 'America/Bogota', 'theme_override': None}
    conn = FakeConn(
        fetchrow=[{'id': uid}, prefs, prefs],
        execute=['OK', 'OK'],
    )
    req = _fake_request()
    body = NotificationsPatchRequest(notification_matrix=new)
    result = asyncio.run(patch_my_notifications(body, req, conn))
    assert 'notification_matrix' in result


def test_get_my_sessions():
    from app.api.v1.handlers.me_handlers import list_my_sessions
    from datetime import datetime, UTC
    uid = uuid4()
    sid = 'sid-current'
    now = datetime.now(UTC)
    rows = [
        {'id': sid, 'device': 'desktop', 'user_agent': 'curl', 'ip': '127.0.0.1',
         'location': 'CO', 'created_at': now, 'last_seen_at': now},
    ]
    conn = FakeConn(
        fetchrow=[{'id': uid}],
        fetch=[rows],
        execute=['OK'],
    )
    req = _fake_request(session_jti=sid)
    result = asyncio.run(list_my_sessions(req, conn))
    assert len(result.items) == 1
    assert result.items[0].current is True


def test_delete_my_session_happy():
    from app.api.v1.handlers.me_handlers import revoke_my_session
    uid = uuid4()
    sid = 'sid-other'
    # UPDATE returns 'UPDATE 1' when row matched.
    conn = FakeConn(
        fetchrow=[{'id': uid}],
        execute=['UPDATE 1', 'OK'],
    )
    req = _fake_request()
    asyncio.run(revoke_my_session(sid, req, conn))


def test_delete_my_session_404_not_owner():
    from app.api.v1.handlers.me_handlers import revoke_my_session
    from fastapi import HTTPException
    uid = uuid4()
    # UPDATE returned 0 rows — handler raises 404.
    conn = FakeConn(fetchrow=[{'id': uid}], execute=['UPDATE 0'])
    req = _fake_request()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(revoke_my_session('sid-x', req, conn))
    assert exc.value.status_code == 404


def test_delete_my_session_404_unknown():
    from app.api.v1.handlers.me_handlers import revoke_my_session
    from fastapi import HTTPException
    uid = uuid4()
    conn = FakeConn(fetchrow=[{'id': uid}], execute=['UPDATE 0'])
    req = _fake_request()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(revoke_my_session('sid-x', req, conn))
    assert exc.value.status_code == 404


# ─── support_mode endpoints ────────────────────────────────────────────────


def test_activate_support_mode_happy():
    from app.api.v1.handlers.me_handlers import (
        activate_support_mode, SupportModeActivateRequest,
    )
    from fastapi import Response
    tid = uuid4()
    conn = FakeConn(
        fetchval=[1],     # tenant exists
        execute=['OK'],    # audit
    )
    req = _fake_request(roles=['platform_owner'])
    resp = Response()
    body = SupportModeActivateRequest(justification='troubleshooting issue 123')
    result = asyncio.run(
        activate_support_mode(tid, req, resp, body, conn)
    )
    assert str(result.tenant_id) == str(tid)


def test_activate_support_mode_403_for_admin_only():
    from app.api.v1.handlers.me_handlers import (
        activate_support_mode, SupportModeActivateRequest,
    )
    from fastapi import HTTPException, Response
    tid = uuid4()
    conn = FakeConn()
    req = _fake_request(roles=['admin'])
    resp = Response()
    body = SupportModeActivateRequest(justification='need access')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            activate_support_mode(tid, req, resp, body, conn)
        )
    assert exc.value.status_code == 403


def test_activate_support_mode_404_tenant_missing():
    from app.api.v1.handlers.me_handlers import (
        activate_support_mode, SupportModeActivateRequest,
    )
    from fastapi import HTTPException, Response
    tid = uuid4()
    conn = FakeConn(fetchval=[None])
    req = _fake_request(roles=['platform_owner'])
    resp = Response()
    body = SupportModeActivateRequest(justification='need access')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            activate_support_mode(tid, req, resp, body, conn)
        )
    assert exc.value.status_code == 404


def test_activate_support_mode_401_no_actor():
    from app.api.v1.handlers.me_handlers import (
        activate_support_mode, SupportModeActivateRequest,
    )
    from fastapi import HTTPException, Response
    tid = uuid4()
    conn = FakeConn()
    req = _fake_request(actor_id=None, roles=['platform_owner'])
    resp = Response()
    body = SupportModeActivateRequest(justification='need access')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            activate_support_mode(tid, req, resp, body, conn)
        )
    assert exc.value.status_code == 401


def test_deactivate_support_mode_idempotent():
    from app.api.v1.handlers.me_handlers import deactivate_support_mode
    from fastapi import Response
    tid = uuid4()
    conn = FakeConn(execute=['OK'])
    req = _fake_request(roles=['platform_owner'])
    resp = Response()
    asyncio.run(deactivate_support_mode(tid, req, resp, conn))


# ═══════════════════════════════════════════════════════════════════════════
# tenant_user_handlers
# ═══════════════════════════════════════════════════════════════════════════


def test_list_my_tenants_happy():
    from app.api.v1.handlers.tenant_user_handlers import list_my_tenants
    uid = uuid4()
    tid = uuid4()
    rows = [{
        'id': tid, 'slug': 'acme', 'display_name': 'ACME',
        'role': 'owner', 'is_default': True,
    }]
    conn = FakeConn(fetchrow=[{'id': uid}], fetch=[rows])
    req = _fake_request()
    result = asyncio.run(list_my_tenants(req, conn))
    assert isinstance(result, list)
    assert result[0]['slug'] == 'acme'


def test_list_my_tenants_401_anonymous():
    from app.api.v1.handlers.tenant_user_handlers import list_my_tenants
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request(actor_type='anonymous', actor_id=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(list_my_tenants(req, conn))
    assert exc.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# tenant_signup_handlers
# ═══════════════════════════════════════════════════════════════════════════


def test_tenant_signup_happy():
    from app.api.v1.handlers.tenant_signup_handlers import create_own_tenant
    from app.api.v1.schemas import TenantCreate
    uid = uuid4()
    tid = uuid4()
    tenant_row = {
        'id': tid, 'slug': 'acme', 'legal_name': 'ACME', 'display_name': 'ACME',
        'vertical_code': 'tech', 'business_type_label': None,
        'country_code': 'CO', 'timezone': 'America/Bogota',
        'status': 'trial', 'created_at': None, 'updated_at': None,
    }
    conn = FakeConn(
        fetchval=[None],         # no existing membership
        fetchrow=[tenant_row, {'id': uid}],  # insert tenant, upsert user
        execute=['OK', 'OK', 'OK'],          # set_config, insert role, audit
    )
    req = _fake_request()
    payload = TenantCreate(
        slug='acme', legal_name='ACME', display_name='ACME',
        vertical_code='tech', country_code='CO',
    )
    result = asyncio.run(create_own_tenant(payload, req, conn))
    assert result['slug'] == 'acme'
    assert result['user_role'] == 'owner'


def test_tenant_signup_409_when_already_member():
    from app.api.v1.handlers.tenant_signup_handlers import create_own_tenant
    from app.api.v1.schemas import TenantCreate
    from fastapi import HTTPException
    existing_tid = uuid4()
    conn = FakeConn(fetchval=[existing_tid])
    req = _fake_request()
    payload = TenantCreate(
        slug='acme', legal_name='ACME', display_name='ACME',
        vertical_code='tech', country_code='CO',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_own_tenant(payload, req, conn))
    assert exc.value.status_code == 409


def test_tenant_signup_401_anonymous():
    from app.api.v1.handlers.tenant_signup_handlers import create_own_tenant
    from app.api.v1.schemas import TenantCreate
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request(actor_id=None)
    payload = TenantCreate(
        slug='acme', legal_name='ACME', display_name='ACME',
        vertical_code='tech', country_code='CO',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_own_tenant(payload, req, conn))
    assert exc.value.status_code == 401


def test_tenant_signup_409_on_slug_conflict():
    import asyncpg
    from app.api.v1.handlers.tenant_signup_handlers import create_own_tenant
    from app.api.v1.schemas import TenantCreate
    from fastapi import HTTPException

    class ConflictingConn(FakeConn):
        def __init__(self):
            super().__init__(fetchval=[None])

        async def fetchrow(self, sql, *args):
            self.calls.append(('fetchrow', sql, args))
            # insert into app.tenants returning * → conflict
            raise asyncpg.UniqueViolationError('slug taken')

    conn = ConflictingConn()
    req = _fake_request()
    payload = TenantCreate(
        slug='taken', legal_name='X', display_name='X',
        vertical_code='tech', country_code='CO',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_own_tenant(payload, req, conn))
    assert exc.value.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# platform_admin_handlers — fleet CRUD + members
# ═══════════════════════════════════════════════════════════════════════════


def test_list_all_tenants_happy():
    from app.api.v1.handlers.platform_admin_handlers import list_all_tenants
    tid = uuid4()
    rows = [
        {
            'id': tid, 'slug': 'acme', 'legal_name': 'ACME',
            'display_name': 'ACME', 'vertical_code': 'tech',
            'business_type_label': None, 'country_code': 'CO',
            'timezone': 'America/Bogota', 'status': 'active',
            'created_at': None, 'updated_at': None,
            'member_count': 3, 'active_modules_count': 1,
        },
    ]
    conn = FakeConn(fetch=[rows], fetchval=[1])
    result = asyncio.run(
        list_all_tenants(
            status_filter='active', country_code='CO',
            vertical_code='tech', search='ACME',
            limit=50, offset=0, conn=conn,
        )
    )
    assert result['total'] == 1
    assert result['items'][0]['slug'] == 'acme'


def test_list_all_tenants_no_filters():
    from app.api.v1.handlers.platform_admin_handlers import list_all_tenants
    conn = FakeConn(fetch=[[]], fetchval=[0])
    result = asyncio.run(
        list_all_tenants(
            status_filter=None, country_code=None, vertical_code=None,
            search=None, limit=50, offset=0, conn=conn,
        )
    )
    assert result['total'] == 0


def test_create_tenant_for_third_party_happy():
    from app.api.v1.handlers.platform_admin_handlers import create_tenant_for_third_party
    from app.api.v1.schemas import TenantCreate
    tid = uuid4()
    conn = FakeConn(
        fetchrow=[{
            'id': tid, 'slug': 'new', 'legal_name': 'New', 'display_name': 'New',
            'vertical_code': 'tech', 'business_type_label': None,
            'country_code': 'CO', 'timezone': 'America/Bogota',
            'status': 'trial', 'created_at': None, 'updated_at': None,
        }],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    payload = TenantCreate(
        slug='new', legal_name='New', display_name='New',
        vertical_code='tech', country_code='CO',
    )
    result = asyncio.run(create_tenant_for_third_party(payload, req, conn))
    assert result['slug'] == 'new'


def test_create_tenant_for_third_party_409():
    import asyncpg
    from app.api.v1.handlers.platform_admin_handlers import create_tenant_for_third_party
    from app.api.v1.schemas import TenantCreate
    from fastapi import HTTPException

    class ConflictConn(FakeConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.UniqueViolationError('slug taken')

    conn = ConflictConn()
    req = _fake_request(roles=['platform_owner'])
    payload = TenantCreate(
        slug='taken', legal_name='X', display_name='X',
        vertical_code='tech', country_code='CO',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_tenant_for_third_party(payload, req, conn))
    assert exc.value.status_code == 409


def test_get_tenant_happy():
    from app.api.v1.handlers.platform_admin_handlers import get_tenant
    tid = uuid4()
    conn = FakeConn(fetchrow=[{
        'id': tid, 'slug': 'acme', 'legal_name': 'ACME', 'display_name': 'ACME',
        'vertical_code': 'tech', 'business_type_label': None,
        'country_code': 'CO', 'timezone': 'America/Bogota',
        'status': 'active', 'created_at': None, 'updated_at': None,
    }])
    result = asyncio.run(get_tenant(tid, conn))
    assert result['slug'] == 'acme'


def test_get_tenant_404():
    from app.api.v1.handlers.platform_admin_handlers import get_tenant
    from fastapi import HTTPException
    tid = uuid4()
    conn = FakeConn(fetchrow=[None])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_tenant(tid, conn))
    assert exc.value.status_code == 404


def test_patch_tenant_happy():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant
    from app.api.v1.schemas import TenantUpdate
    tid = uuid4()
    conn = FakeConn(
        fetchrow=[{
            'id': tid, 'slug': 'acme', 'legal_name': 'ACME-new',
            'display_name': 'ACME', 'vertical_code': 'tech',
            'business_type_label': None, 'country_code': 'CO',
            'timezone': 'America/Bogota', 'status': 'active',
            'created_at': None, 'updated_at': None,
        }],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    payload = TenantUpdate(legal_name='ACME-new')
    result = asyncio.run(patch_tenant(tid, payload, req, conn))
    assert result['legal_name'] == 'ACME-new'


def test_patch_tenant_400_empty():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant
    from app.api.v1.schemas import TenantUpdate
    from fastapi import HTTPException
    tid = uuid4()
    conn = FakeConn()
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_tenant(tid, TenantUpdate(), req, conn))
    assert exc.value.status_code == 400


def test_list_runbooks():
    from app.api.v1.handlers.platform_admin_handlers import list_runbooks
    result = asyncio.run(list_runbooks())
    assert 'items' in result
    for item in result['items']:
        assert 'slug' in item


def test_get_runbook_happy():
    from app.api.v1.handlers.platform_admin_handlers import get_runbook
    result = asyncio.run(get_runbook('auth0-mfa-error'))
    assert result['slug'] == 'auth0-mfa-error'
    assert 'body_md' in result


def test_get_runbook_404():
    from app.api.v1.handlers.platform_admin_handlers import get_runbook
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_runbook('does-not-exist'))
    assert exc.value.status_code == 404


def test_retry_outbound_dlq_placeholder():
    from app.api.v1.handlers.platform_admin_handlers import retry_outbound_dlq
    result = asyncio.run(retry_outbound_dlq())
    assert 'queued' in result


# ═══════════════════════════════════════════════════════════════════════════
# platform_roles_handlers
# ═══════════════════════════════════════════════════════════════════════════


def test_list_roles_happy():
    from app.api.v1.handlers.platform_roles_handlers import list_roles
    rows = [{'code': 'owner', 'name': 'Owner', 'description': None,
             'is_system': True, 'is_active': True, 'capability_count': 5}]
    conn = FakeConn(fetch=[rows])
    result = asyncio.run(list_roles(conn))
    assert len(result.items) == 1


def test_create_role_happy():
    from app.api.v1.handlers.platform_roles_handlers import (
        create_role, RoleCreateRequest,
    )
    # Handler hace `RoleRow(**dict(row), capability_count=0)` — el row no
    # debe traer `capability_count` (sería duplicate keyword).
    conn = FakeConn(
        fetchrow=[{'code': 'analyst', 'name': 'Analyst', 'description': None,
                   'is_system': False, 'is_active': True}],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = RoleCreateRequest(code='analyst', name='Analyst')
    result = asyncio.run(create_role(body, req, conn))
    assert result.code == 'analyst'


def test_create_role_409():
    import asyncpg
    from app.api.v1.handlers.platform_roles_handlers import (
        create_role, RoleCreateRequest,
    )
    from fastapi import HTTPException

    class ConflictConn(FakeConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.UniqueViolationError('role exists')

    conn = ConflictConn()
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_role(RoleCreateRequest(code='owner', name='Dup'), req, conn))
    assert exc.value.status_code == 409


def test_list_capabilities_happy():
    from app.api.v1.handlers.platform_roles_handlers import list_capabilities
    conn = FakeConn(fetch=[[]])
    result = asyncio.run(list_capabilities(conn))
    assert result.items == []


def test_create_capability_happy():
    from app.api.v1.handlers.platform_roles_handlers import (
        create_capability, CapabilityCreateRequest,
    )
    conn = FakeConn(
        fetchrow=[{'code': 'foo.bar', 'name': 'Foo', 'description': None,
                   'group_label': 'Group', 'is_system': False, 'is_active': True}],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = CapabilityCreateRequest(code='foo.bar', name='Foo', group_label='Group')
    result = asyncio.run(create_capability(body, req, conn))
    assert result.code == 'foo.bar'


def test_list_role_capabilities_happy():
    from app.api.v1.handlers.platform_roles_handlers import list_role_capabilities
    conn = FakeConn(fetch=[[]])
    result = asyncio.run(list_role_capabilities('admin', conn))
    assert result.items == []
