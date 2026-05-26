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
from uuid import uuid4

import pytest
from fastapi import HTTPException


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
    """Si JWT NO trae email y x-admin-user-email también vacío → fallback
    `{actor_id}@auth.local`."""
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid = uuid4()
    req = _fake_request(email=None)
    # M57: 3 fetchrow ahora — auth_subject miss → pending miss → insert.
    conn = FakeConn(fetchrow=[None, None, {'id': uid}])
    asyncio.run(current_user_id_from_request(req, conn))
    # Buscar el INSERT por SQL (no por índice) para no depender del orden.
    insert_call = next(c for c in conn.calls if 'insert into app.users' in c[1])
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


def test_patch_role_happy():
    from app.api.v1.handlers.platform_roles_handlers import (
        patch_role, RolePatchRequest,
    )
    conn = FakeConn(
        fetchrow=[
            {'code': 'analyst', 'name': 'Analyst X', 'description': 'updated',
             'is_system': False, 'is_active': True},
        ],
        fetchval=[3],     # capability_count
        execute=['OK'],   # audit
    )
    req = _fake_request(roles=['platform_owner'])
    body = RolePatchRequest(name='Analyst X', description='updated', is_active=True)
    result = asyncio.run(patch_role('analyst', body, req, conn))
    assert result.capability_count == 3


def test_patch_role_400_empty():
    from app.api.v1.handlers.platform_roles_handlers import (
        patch_role, RolePatchRequest,
    )
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_role('analyst', RolePatchRequest(), req, conn))
    assert exc.value.status_code == 400


def test_patch_role_404():
    from app.api.v1.handlers.platform_roles_handlers import (
        patch_role, RolePatchRequest,
    )
    from fastapi import HTTPException
    conn = FakeConn(fetchrow=[None])
    req = _fake_request(roles=['platform_owner'])
    body = RolePatchRequest(name='New Name')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_role('missing', body, req, conn))
    assert exc.value.status_code == 404


def test_delete_role_happy():
    from app.api.v1.handlers.platform_roles_handlers import delete_role
    conn = FakeConn(
        fetchrow=[{'code': 'analyst', 'is_system': False}],
        execute=['DELETE 1', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(delete_role('analyst', req, conn))


def test_delete_role_404():
    from app.api.v1.handlers.platform_roles_handlers import delete_role
    from fastapi import HTTPException
    conn = FakeConn(fetchrow=[None])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_role('missing', req, conn))
    assert exc.value.status_code == 404


def test_delete_role_409_system():
    from app.api.v1.handlers.platform_roles_handlers import delete_role
    from fastapi import HTTPException
    conn = FakeConn(fetchrow=[{'code': 'owner', 'is_system': True}])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_role('owner', req, conn))
    assert exc.value.status_code == 409


def test_assign_capability_happy():
    from app.api.v1.handlers.platform_roles_handlers import (
        assign_capability_to_role, RoleCapabilityAssignRequest,
    )
    conn = FakeConn(
        fetchval=[True, True],   # role exists, capability exists
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = RoleCapabilityAssignRequest(access_level='RW')
    result = asyncio.run(
        assign_capability_to_role('admin', 'foo.bar', body, req, conn)
    )
    assert result.access_level == 'RW'


def test_assign_capability_404_role_missing():
    from app.api.v1.handlers.platform_roles_handlers import (
        assign_capability_to_role, RoleCapabilityAssignRequest,
    )
    from fastapi import HTTPException
    conn = FakeConn(fetchval=[False])  # role missing
    req = _fake_request(roles=['platform_owner'])
    body = RoleCapabilityAssignRequest(access_level='R')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            assign_capability_to_role('missing', 'foo.bar', body, req, conn)
        )
    assert exc.value.status_code == 404


def test_assign_capability_404_cap_missing():
    from app.api.v1.handlers.platform_roles_handlers import (
        assign_capability_to_role, RoleCapabilityAssignRequest,
    )
    from fastapi import HTTPException
    conn = FakeConn(fetchval=[True, False])
    req = _fake_request(roles=['platform_owner'])
    body = RoleCapabilityAssignRequest(access_level='R')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            assign_capability_to_role('admin', 'missing.cap', body, req, conn)
        )
    assert exc.value.status_code == 404


def test_revoke_capability_happy():
    from app.api.v1.handlers.platform_roles_handlers import revoke_capability_from_role
    conn = FakeConn(execute=['DELETE 1', 'OK'])
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(revoke_capability_from_role('admin', 'foo.bar', req, conn))


def test_revoke_capability_404():
    from app.api.v1.handlers.platform_roles_handlers import revoke_capability_from_role
    from fastapi import HTTPException
    conn = FakeConn(execute=['DELETE 0'])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(revoke_capability_from_role('admin', 'foo.bar', req, conn))
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# platform_admin_handlers — members + observability + feature flags
# ═══════════════════════════════════════════════════════════════════════════


def test_patch_tenant_status_happy():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_status, TenantStatusUpdate
    tid = uuid4()
    conn = FakeConn(
        fetchrow=[{'id': tid, 'status': 'suspended'}],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantStatusUpdate(status='suspended')
    result = asyncio.run(patch_tenant_status(tid, body, req, conn))
    assert result['status'] == 'suspended'


def test_patch_tenant_status_404():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_status, TenantStatusUpdate
    from fastapi import HTTPException
    tid = uuid4()
    conn = FakeConn(fetchrow=[None])
    req = _fake_request(roles=['platform_owner'])
    body = TenantStatusUpdate(status='active')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_tenant_status(tid, body, req, conn))
    assert exc.value.status_code == 404


def test_list_tenant_members_happy():
    from app.api.v1.handlers.platform_admin_handlers import list_tenant_members
    from datetime import datetime, UTC
    tid = uuid4()
    uid = uuid4()
    now = datetime.now(UTC)
    rows = [{
        'user_id': uid, 'email': 'u@x.co', 'display_name': 'U',
        'user_status': 'active', 'mfa_enabled': True, 'last_login_at': now,
        'roles': ['owner', 'admin'], 'is_default': True, 'joined_at': now,
    }]
    conn = FakeConn(fetch=[rows])
    result = asyncio.run(list_tenant_members(tid, _acl=None, conn=conn))
    assert len(result['items']) == 1
    assert result['items'][0]['roles'] == ['owner', 'admin']
    assert result['tenant_id'] == str(tid)


def test_add_tenant_member_existing_user():
    from app.api.v1.handlers.platform_admin_handlers import add_tenant_member, TenantMemberAdd
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(
        fetchval=[1],   # tenant exists
        fetchrow=[{'id': uid, 'email': 'x@y.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='x@y.co', role='admin', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['email'] == 'x@y.co'


def test_add_tenant_member_pending_user():
    """Si el email no existe, se crea pending."""
    from app.api.v1.handlers.platform_admin_handlers import add_tenant_member, TenantMemberAdd
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(
        fetchval=[1],
        fetchrow=[None, {'id': uid, 'email': 'new@x.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='new@x.co', role='agent', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['user_id'] == str(uid)


def test_add_tenant_member_404_tenant_missing():
    from app.api.v1.handlers.platform_admin_handlers import add_tenant_member, TenantMemberAdd
    from fastapi import HTTPException
    tid = uuid4()
    conn = FakeConn(fetchval=[None])
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='x@y.co', role='admin', is_default=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert exc.value.status_code == 404


def test_patch_tenant_member_change_role():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_member, TenantMemberPatch
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(
        fetch=[[{'role': 'agent', 'is_default': True}]],
        execute=['DELETE 1', 'INSERT 1', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberPatch(role='admin')
    result = asyncio.run(patch_tenant_member(tid, uid, body, req, _acl=None, conn=conn))
    assert result['role'] == 'admin'


def test_patch_tenant_member_change_is_default_only():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_member, TenantMemberPatch
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(
        fetch=[[{'role': 'admin', 'is_default': False}]],
        execute=['UPDATE 1', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberPatch(is_default=True)
    result = asyncio.run(patch_tenant_member(tid, uid, body, req, _acl=None, conn=conn))
    assert result['is_default'] is True


def test_patch_tenant_member_404_no_membership():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_member, TenantMemberPatch
    from fastapi import HTTPException
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(fetch=[[]])
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberPatch(role='admin')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_tenant_member(tid, uid, body, req, _acl=None, conn=conn))
    assert exc.value.status_code == 404


def test_patch_tenant_member_400_empty():
    from app.api.v1.handlers.platform_admin_handlers import patch_tenant_member, TenantMemberPatch
    from fastapi import HTTPException
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(fetch=[[{'role': 'admin', 'is_default': True}]])
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberPatch()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_tenant_member(tid, uid, body, req, _acl=None, conn=conn))
    assert exc.value.status_code == 400


def test_remove_tenant_member_happy():
    from app.api.v1.handlers.platform_admin_handlers import remove_tenant_member
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(execute=['DELETE 1', 'OK'])
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(remove_tenant_member(tid, uid, req, _acl=None, conn=conn))


def test_remove_tenant_member_404():
    from app.api.v1.handlers.platform_admin_handlers import remove_tenant_member
    from fastapi import HTTPException
    tid = uuid4()
    uid = uuid4()
    conn = FakeConn(execute=['DELETE 0'])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(remove_tenant_member(tid, uid, req, _acl=None, conn=conn))
    assert exc.value.status_code == 404


# ─── observability ────────────────────────────────────────────────────────


def test_get_platform_health_happy():
    """M54 — shape DEBE matchear lo que `SystemHealth.jsx` consume:
    generated_at, snapshot, alerts (array), services (array de
    {key, label, status, detail}), note. El bug original era
    `services` como dict → frontend `services.map()` rompía."""
    from app.api.v1.handlers.platform_admin_handlers import get_platform_health
    conn = FakeConn(fetchval=[1])
    result = asyncio.run(get_platform_health(conn))
    assert 'generated_at' in result
    assert 'snapshot' in result
    assert isinstance(result['alerts'], list)
    assert isinstance(result['services'], list)  # ← era dict antes
    assert len(result['services']) == 2  # api + postgres
    api_svc = next(s for s in result['services'] if s['key'] == 'api')
    pg_svc = next(s for s in result['services'] if s['key'] == 'postgres')
    assert api_svc['status'] == 'ok'
    assert pg_svc['status'] == 'ok'
    assert 'ms' in (pg_svc['detail'] or '')
    assert isinstance(result['note'], str)


def test_get_platform_health_db_down():
    """Si el DB probe falla, postgres.status='down' + detail con el error."""
    from app.api.v1.handlers.platform_admin_handlers import get_platform_health

    class FailingConn(FakeConn):
        async def fetchval(self, sql, *args):
            raise RuntimeError('connection refused')

    result = asyncio.run(get_platform_health(FailingConn()))
    pg_svc = next(s for s in result['services'] if s['key'] == 'postgres')
    assert pg_svc['status'] == 'down'
    assert 'connection refused' in pg_svc['detail']


def test_get_platform_health_db_timeout():
    """Si el probe tarda más de 2s, status='down' con TimeoutError."""
    import asyncio as _asyncio
    from app.api.v1.handlers.platform_admin_handlers import get_platform_health

    class SlowConn(FakeConn):
        async def fetchval(self, sql, *args):
            await _asyncio.sleep(5)  # más de 2s → timeout
            return 1

    result = asyncio.run(get_platform_health(SlowConn()))
    pg_svc = next(s for s in result['services'] if s['key'] == 'postgres')
    assert pg_svc['status'] == 'down'


def test_get_billing_mrr():
    from app.api.v1.handlers.platform_admin_handlers import get_billing_mrr
    result = asyncio.run(get_billing_mrr())
    assert result['mrr_total_usd'] == 0


def test_list_platform_incidents_no_filter():
    from app.api.v1.handlers.platform_admin_handlers import list_platform_incidents
    conn = FakeConn(fetch=[[]])
    result = asyncio.run(
        list_platform_incidents(status_filter=None, limit=50, conn=conn)
    )
    assert result == {'items': []}


def test_list_platform_incidents_with_filter():
    from app.api.v1.handlers.platform_admin_handlers import list_platform_incidents
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    rows = [{
        'id': uuid4(), 'tenant_id': uuid4(), 'tenant_slug': 'acme',
        'tenant_name': 'ACME', 'kind': 'backup_failure', 'payload': '{}',
        'status': 'open', 'attempts': 0, 'last_error': None,
        'scheduled_for': now, 'created_at': now, 'sent_at': None,
    }]
    conn = FakeConn(fetch=[rows])
    result = asyncio.run(
        list_platform_incidents(status_filter='open', limit=10, conn=conn)
    )
    assert len(result['items']) == 1


def test_list_outbound_dlq():
    from app.api.v1.handlers.platform_admin_handlers import list_outbound_dlq
    result = asyncio.run(list_outbound_dlq())
    assert result['total'] == 0


# ─── feature flags ────────────────────────────────────────────────────────


def test_list_feature_flags():
    from app.api.v1.handlers.platform_admin_handlers import list_feature_flags
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    rows = [{
        'key': 'beta', 'description': None, 'enabled': True, 'rollout_pct': 50,
        'metadata': '{}', 'created_at': now, 'updated_at': now,
    }]
    conn = FakeConn(fetch=[rows])
    result = asyncio.run(list_feature_flags(conn))
    assert result['items'][0]['key'] == 'beta'


def test_create_feature_flag_happy():
    from app.api.v1.handlers.platform_admin_handlers import create_feature_flag, FeatureFlagCreate
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    conn = FakeConn(
        fetchrow=[{
            'key': 'new', 'description': None, 'enabled': False,
            'rollout_pct': 0, 'metadata': '{}',
            'created_at': now, 'updated_at': now,
        }],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = FeatureFlagCreate(key='new')
    result = asyncio.run(create_feature_flag(body, req, conn))
    assert result['key'] == 'new'


def test_create_feature_flag_409():
    import asyncpg
    from app.api.v1.handlers.platform_admin_handlers import create_feature_flag, FeatureFlagCreate
    from fastapi import HTTPException

    class ConflictConn(FakeConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.UniqueViolationError('key taken')

    conn = ConflictConn()
    req = _fake_request(roles=['platform_owner'])
    body = FeatureFlagCreate(key='taken')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_feature_flag(body, req, conn))
    assert exc.value.status_code == 409


def test_patch_feature_flag_happy():
    from app.api.v1.handlers.platform_admin_handlers import patch_feature_flag, FeatureFlagPatch
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    conn = FakeConn(
        fetchrow=[{
            'key': 'beta', 'description': 'updated', 'enabled': True,
            'rollout_pct': 75, 'metadata': '{}',
            'created_at': now, 'updated_at': now,
        }],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = FeatureFlagPatch(enabled=True, rollout_pct=75, description='updated', metadata={'a': 1})
    result = asyncio.run(patch_feature_flag('beta', body, req, conn))
    assert result['enabled'] is True


def test_patch_feature_flag_400_empty():
    from app.api.v1.handlers.platform_admin_handlers import patch_feature_flag, FeatureFlagPatch
    from fastapi import HTTPException
    conn = FakeConn()
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_feature_flag('beta', FeatureFlagPatch(), req, conn))
    assert exc.value.status_code == 400


def test_patch_feature_flag_404():
    from app.api.v1.handlers.platform_admin_handlers import patch_feature_flag, FeatureFlagPatch
    from fastapi import HTTPException
    conn = FakeConn(fetchrow=[None])
    req = _fake_request(roles=['platform_owner'])
    body = FeatureFlagPatch(enabled=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_feature_flag('missing', body, req, conn))
    assert exc.value.status_code == 404


def test_delete_feature_flag_happy():
    from app.api.v1.handlers.platform_admin_handlers import delete_feature_flag
    conn = FakeConn(execute=['DELETE 1', 'OK'])
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(delete_feature_flag('beta', req, conn))


def test_delete_feature_flag_404():
    from app.api.v1.handlers.platform_admin_handlers import delete_feature_flag
    from fastapi import HTTPException
    conn = FakeConn(execute=['DELETE 0'])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_feature_flag('missing', req, conn))
    assert exc.value.status_code == 404


# ─── health endpoint (public) ─────────────────────────────────────────────


def test_public_health_calls_db():
    from app.api.v1.handlers.public_handlers import health
    conn = FakeConn(fetchval=[1])
    result = asyncio.run(health(conn))
    assert result == {'status': 'ok'}


# ─── schemas — TENANT_SLUG_PATTERN + timezone validator ───────────────────


def test_tenant_create_invalid_slug():
    import pydantic
    from app.api.v1.schemas import TenantCreate
    with pytest.raises(pydantic.ValidationError):
        TenantCreate(
            slug='Bad Slug!', legal_name='X', display_name='X',
            vertical_code='tech', country_code='CO',
        )


def test_tenant_create_invalid_timezone():
    import pydantic
    from app.api.v1.schemas import TenantCreate
    with pytest.raises(pydantic.ValidationError):
        TenantCreate(
            slug='acme', legal_name='X', display_name='X',
            vertical_code='tech', country_code='CO',
            timezone='Not/A/Zone',
        )


def test_tenant_create_valid_timezone():
    from app.api.v1.schemas import TenantCreate
    t = TenantCreate(
        slug='acme', legal_name='X', display_name='X',
        vertical_code='tech', country_code='CO',
        timezone='America/Mexico_City',
    )
    assert t.timezone == 'America/Mexico_City'


def test_tenant_create_empty_timezone():
    from app.api.v1.schemas import TenantCreate
    t = TenantCreate(
        slug='acme', legal_name='X', display_name='X',
        vertical_code='tech', country_code='CO',
        timezone=None,
    )
    assert t.timezone is None


def test_tenant_create_extra_field_rejected():
    import pydantic
    from app.api.v1.schemas import TenantCreate
    with pytest.raises(pydantic.ValidationError):
        TenantCreate(
            slug='acme', legal_name='X', display_name='X',
            vertical_code='tech', country_code='CO',
            unknown_field='foo',
        )


def test_tenant_update_accepts_partial():
    from app.api.v1.schemas import TenantUpdate
    t = TenantUpdate(display_name='New name')
    assert t.display_name == 'New name'
    assert t.slug is None


def test_platform_tenant_update_status():
    from app.api.v1.schemas import PlatformTenantUpdate
    t = PlatformTenantUpdate(status='suspended')
    assert t.status == 'suspended'


def test_platform_tenant_update_invalid_status():
    import pydantic
    from app.api.v1.schemas import PlatformTenantUpdate
    with pytest.raises(pydantic.ValidationError):
        PlatformTenantUpdate(status='nuclear')


# ─── M55 — require_tenant_management ACL helper ────────────────────────────


def test_require_tenant_management_platform_owner_bypasses():
    """platform_owner pasa sin lookup en DB y setea support_mode=True."""
    from app.core.security import require_tenant_management
    tid = uuid4()
    req = _fake_request(roles=['platform_owner'])
    # No need to mock db.pool — platform_owner short-circuits before lookup
    asyncio.run(require_tenant_management(tid, req))
    assert req.state.support_mode is True


def test_require_tenant_management_401_no_actor():
    from app.core.security import require_tenant_management
    from fastapi import HTTPException
    tid = uuid4()
    req = _fake_request(actor_id=None, roles=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_tenant_management(tid, req))
    assert exc.value.status_code == 401


def test_require_tenant_management_owner_of_this_tenant(monkeypatch):
    """Owner del tenant del path → pasa + setea state.tenant_id."""
    from app.core.security import require_tenant_management
    from app.db import pool as pool_mod
    tid = uuid4()

    # Mock db.pool.acquire context manager
    class FakeConnLookup:
        async def fetchrow(self, sql, *args):
            return {'role': 'owner'}

    class FakeAcquireCtx:
        async def __aenter__(self_inner): return FakeConnLookup()
        async def __aexit__(self_inner, *e): return False

    class FakePool:
        def acquire(self_inner): return FakeAcquireCtx()

    monkeypatch.setattr(pool_mod.db, 'pool', FakePool())
    req = _fake_request(actor_id='auth0|u1', roles=[])
    asyncio.run(require_tenant_management(tid, req))
    assert req.state.tenant_id == tid


def test_require_tenant_management_admin_of_this_tenant(monkeypatch):
    """Admin del tenant del path también pasa."""
    from app.core.security import require_tenant_management
    from app.db import pool as pool_mod
    tid = uuid4()

    class FakeConnLookup:
        async def fetchrow(self, sql, *args):
            return {'role': 'admin'}

    class FakeAcquireCtx:
        async def __aenter__(self_inner): return FakeConnLookup()
        async def __aexit__(self_inner, *e): return False

    class FakePool:
        def acquire(self_inner): return FakeAcquireCtx()

    monkeypatch.setattr(pool_mod.db, 'pool', FakePool())
    req = _fake_request(actor_id='auth0|u1', roles=[])
    asyncio.run(require_tenant_management(tid, req))


def test_require_tenant_management_403_wrong_role(monkeypatch):
    """Viewer/agent/manager del tenant → 403 (solo owner/admin)."""
    from app.core.security import require_tenant_management
    from app.db import pool as pool_mod
    from fastapi import HTTPException
    tid = uuid4()

    class FakeConnLookup:
        async def fetchrow(self, sql, *args):
            return {'role': 'viewer'}

    class FakeAcquireCtx:
        async def __aenter__(self_inner): return FakeConnLookup()
        async def __aexit__(self_inner, *e): return False

    class FakePool:
        def acquire(self_inner): return FakeAcquireCtx()

    monkeypatch.setattr(pool_mod.db, 'pool', FakePool())
    req = _fake_request(actor_id='auth0|u1', roles=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_tenant_management(tid, req))
    assert exc.value.status_code == 403


def test_require_tenant_management_403_not_member(monkeypatch):
    """User no es miembro del tenant → 403."""
    from app.core.security import require_tenant_management
    from app.db import pool as pool_mod
    from fastapi import HTTPException
    tid = uuid4()

    class FakeConnLookup:
        async def fetchrow(self, sql, *args):
            return None  # no membership

    class FakeAcquireCtx:
        async def __aenter__(self_inner): return FakeConnLookup()
        async def __aexit__(self_inner, *e): return False

    class FakePool:
        def acquire(self_inner): return FakeAcquireCtx()

    monkeypatch.setattr(pool_mod.db, 'pool', FakePool())
    req = _fake_request(actor_id='auth0|u1', roles=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_tenant_management(tid, req))
    assert exc.value.status_code == 403


def test_require_tenant_management_503_no_pool(monkeypatch):
    """Si db.pool no está inicializada (boot race) → 503."""
    from app.core.security import require_tenant_management
    from app.db import pool as pool_mod
    from fastapi import HTTPException
    tid = uuid4()
    monkeypatch.setattr(pool_mod.db, 'pool', None)
    req = _fake_request(actor_id='auth0|u1', roles=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_tenant_management(tid, req))
    assert exc.value.status_code == 503


# ─── M57 — reconciliación de invitación pending ───────────────────────────


def test_current_user_id_reconciles_pending_invite():
    """M57 — si el user no existe por auth_subject pero SÍ existe un
    pending con su email, se UPDATEa el auth_subject del pending en
    lugar de crear un user nuevo (que dejaba el pending huérfano)."""
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid_pending = uuid4()
    req = _fake_request(actor_id='google-oauth2|123', email='nuevo@empresa.com')
    conn = FakeConn(
        fetchrow=[
            None,                  # 1: lookup by auth_subject → miss
            {'id': uid_pending},   # 2: lookup pending by email → hit
        ],
        execute=['OK'],            # update auth_subject del pending
    )
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == uid_pending
    # El UPDATE debe ser el primer execute, con args (actor_id, display, id)
    update_call = next(c for c in conn.calls if c[0] == 'execute')
    assert 'update app.users' in update_call[1]
    assert update_call[2][0] == 'google-oauth2|123'  # nuevo auth_subject
    assert update_call[2][2] == uid_pending          # id del pending


def test_current_user_id_creates_new_when_no_pending_match():
    """Si no hay pending con ese email, crea user nuevo (comportamiento previo)."""
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid_new = uuid4()
    req = _fake_request(actor_id='google-oauth2|456', email='nadie@empresa.com')
    conn = FakeConn(
        fetchrow=[
            None,            # lookup by auth_subject → miss
            None,            # lookup pending by email → miss
            {'id': uid_new}, # insert returning id
        ],
    )
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == uid_new


def test_current_user_id_existing_user_skips_pending_lookup():
    """Si el auth_subject ya está registrado, NO se hace lookup de pending
    (path normal, sin overhead extra para usuarios ya logueados antes)."""
    from app.api.v1._helpers.me_utils import current_user_id_from_request
    uid_existing = uuid4()
    req = _fake_request(actor_id='google-oauth2|789')
    conn = FakeConn(fetchrow=[{'id': uid_existing}])
    result = asyncio.run(current_user_id_from_request(req, conn))
    assert result == uid_existing
    # Solo UNA query: el lookup por auth_subject. NO se hizo el pending lookup.
    fetchrow_calls = [c for c in conn.calls if c[0] == 'fetchrow']
    assert len(fetchrow_calls) == 1
    assert 'auth_subject=$1' in fetchrow_calls[0][1]


# ─── M59 — add_tenant_member con Auth0 wired ─────────────────────────────


def test_add_tenant_member_auth0_invited(monkeypatch):
    """Auth0 configured + user nuevo → invita + crea user con auth_subject real."""
    from app.api.v1.handlers.platform_admin_handlers import (
        add_tenant_member, TenantMemberAdd,
    )
    from app.services import auth0_admin
    tid = uuid4()
    uid = uuid4()
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_invite(**kw):
        return {
            'user': {'user_id': 'auth0|new-real-id', 'email': kw['email']},
            'reused_existing': False,
            'invitation_ticket_url': 'https://test.auth0.com/u/reset?abc',
        }
    monkeypatch.setattr(auth0_admin, 'invite_user', fake_invite)

    conn = FakeConn(
        fetchval=[1],
        fetchrow=[None, {'id': uid, 'email': 'new@x.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='new@x.co', role='admin', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['auth0']['status'] == 'invited'
    assert result['auth0']['user_id'] == 'auth0|new-real-id'
    assert result['auth0']['invitation_ticket_url'].startswith('https://')
    # El INSERT en app.users debe usar el auth_subject REAL (no pending|).
    insert_call = next(c for c in conn.calls if 'insert into app.users' in c[1])
    assert insert_call[2][0] == 'auth0|new-real-id'
    # status='active' porque ya está en Auth0 (no 'invited' que es para pending).
    assert insert_call[2][3] == 'active'


def test_add_tenant_member_auth0_reused_existing(monkeypatch):
    """Email ya estaba en Auth0 → reusa el user. status='reused_existing'."""
    from app.api.v1.handlers.platform_admin_handlers import (
        add_tenant_member, TenantMemberAdd,
    )
    from app.services import auth0_admin
    tid = uuid4()
    uid = uuid4()
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_invite(**kw):
        return {
            'user': {'user_id': 'auth0|existing-id', 'email': kw['email']},
            'reused_existing': True,
            'invitation_ticket_url': None,
        }
    monkeypatch.setattr(auth0_admin, 'invite_user', fake_invite)

    conn = FakeConn(
        fetchval=[1],
        fetchrow=[None, {'id': uid, 'email': 'existing@x.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='existing@x.co', role='admin', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['auth0']['status'] == 'reused_existing'


def test_add_tenant_member_auth0_skipped_when_not_configured(monkeypatch):
    """Sin Auth0 configurado → modo LOCAL ONLY, status='skipped', pending|hash."""
    from app.api.v1.handlers.platform_admin_handlers import (
        add_tenant_member, TenantMemberAdd,
    )
    from app.services import auth0_admin
    tid = uuid4()
    uid = uuid4()
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: False)

    conn = FakeConn(
        fetchval=[1],
        fetchrow=[None, {'id': uid, 'email': 'local@x.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='local@x.co', role='admin', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['auth0']['status'] == 'skipped'
    assert result['auth0']['user_id'] is None
    # auth_subject = pending|hash → M57 lo reconcilia después.
    insert_call = next(c for c in conn.calls if 'insert into app.users' in c[1])
    assert insert_call[2][0].startswith('pending|')


def test_add_tenant_member_auth0_error_falls_back_to_local(monkeypatch):
    """Auth0 API error → flow sigue en modo LOCAL (no aborta), status='error'."""
    from app.api.v1.handlers.platform_admin_handlers import (
        add_tenant_member, TenantMemberAdd,
    )
    from app.services import auth0_admin
    tid = uuid4()
    uid = uuid4()
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def boom(**kw):
        raise auth0_admin.Auth0ApiError(500, '{"error":"oops"}')
    monkeypatch.setattr(auth0_admin, 'invite_user', boom)

    conn = FakeConn(
        fetchval=[1],
        fetchrow=[None, {'id': uid, 'email': 'down@x.co'}],
        execute=['OK', 'OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    body = TenantMemberAdd(email='down@x.co', role='admin', is_default=False)
    result = asyncio.run(add_tenant_member(tid, body, req, _acl=None, conn=conn))
    assert result['auth0']['status'] == 'error'
    assert 'oops' in result['auth0']['error']
    # Pero la membresía local SÍ se creó (no aborta).
    assert result['user_id'] == str(uid)


# ═══════════════════════════════════════════════════════════════════════════
# M59 — Auth0 admin HTTP endpoints (block / unblock / reset_mfa / delete)
# ═══════════════════════════════════════════════════════════════════════════


# M60/M-004 — helper payloads para los tests post-hardening.
def _auth0_action_payload(justification='Motivo legítimo de operación.'):
    from app.api.v1.handlers.platform_admin_handlers import (
        Auth0AdminActionPayload,
    )
    return Auth0AdminActionPayload(justification=justification)


def _auth0_delete_payload(confirm=True, justification='GDPR request del titular.'):
    from app.api.v1.handlers.platform_admin_handlers import (
        Auth0AdminDeletePayload,
    )
    return Auth0AdminDeletePayload(confirm=confirm, justification=justification)


def _reset_auth0_rate_limit():
    from app.api.v1.handlers.platform_admin_handlers import (
        _auth0_rl_reset_all,
    )
    _auth0_rl_reset_all()


def test_auth0_admin_404_when_user_not_found(monkeypatch):
    """Si no existe el `app.users.id`, todos los endpoints devuelven 404."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        block_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    monkeypatch.setattr(auth0_admin, 'block_user',
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('should not call')))
    conn = FakeConn(fetchrow=[None])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(block_user_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 404
    assert 'user_not_found' in exc.value.detail


def test_auth0_admin_409_when_user_pending(monkeypatch):
    """Si `auth_subject = 'pending|...'` (invitee sin login real), 409."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        reset_mfa_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    conn = FakeConn(fetchrow=[
        {'auth_subject': 'pending|abc123', 'email': 'pend@x.co'},
    ])
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(reset_mfa_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 409
    assert 'pending' in exc.value.detail.lower()


def test_auth0_admin_501_when_not_configured(monkeypatch):
    """Si Auth0 Management API no está configurado → 501."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        unblock_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: False)
    conn = FakeConn()
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(unblock_user_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 501
    assert 'auth0_management_not_configured' in exc.value.detail


def test_auth0_admin_block_ok(monkeypatch):
    """Happy path: block resuelve auth_subject + llama auth0_admin.block_user + audita."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        block_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    called = {}

    async def fake_block(user_id):
        called['user_id'] = user_id
    monkeypatch.setattr(auth0_admin, 'block_user', fake_block)

    uid = uuid4()
    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|abc', 'email': 'u@x.co'}],
        execute=['OK'],  # audit insert
    )
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(block_user_in_auth0(
        uid, _auth0_action_payload('Investigación de incidente #123.'),
        req, conn=conn,
    ))
    assert called == {'user_id': 'auth0|abc'}
    # El audit insert debe haber ocurrido y traer la justificación.
    audit_call = next((c for c in conn.calls if 'audit' in c[1].lower()), None)
    assert audit_call is not None
    # last arg de audit() es metadata as JSON (stringified) — buscamos
    # la palabra clave del justificativo.
    args_repr = repr(audit_call[2])
    assert 'incidente' in args_repr or 'justification' in args_repr


def test_auth0_admin_unblock_ok(monkeypatch):
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        unblock_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    called = {}

    async def fake_unblock(user_id):
        called['user_id'] = user_id
    monkeypatch.setattr(auth0_admin, 'unblock_user', fake_unblock)

    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|xyz', 'email': 'u@x.co'}],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(unblock_user_in_auth0(
        uuid4(), _auth0_action_payload(), req, conn=conn,
    ))
    assert called == {'user_id': 'auth0|xyz'}


def test_auth0_admin_reset_mfa_ok(monkeypatch):
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        reset_mfa_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    called = {}

    async def fake_reset(user_id):
        called['user_id'] = user_id
    monkeypatch.setattr(auth0_admin, 'reset_mfa', fake_reset)

    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|mfa-user', 'email': 'm@x.co'}],
        execute=['OK'],
    )
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(reset_mfa_in_auth0(
        uuid4(), _auth0_action_payload('User perdió su teléfono.'),
        req, conn=conn,
    ))
    assert called == {'user_id': 'auth0|mfa-user'}


def test_auth0_admin_delete_ok_marks_user_pending(monkeypatch):
    """DELETE en Auth0 + marca local user como pending|<hex> + audita."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        delete_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_delete(user_id):
        return None
    monkeypatch.setattr(auth0_admin, 'delete_user', fake_delete)

    uid = uuid4()
    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|del-me', 'email': 'd@x.co'}],
        execute=['OK', 'OK'],  # update pending + audit
    )
    req = _fake_request(roles=['platform_owner'])
    asyncio.run(delete_user_in_auth0(
        uid, _auth0_delete_payload(), req, conn=conn,
    ))
    update_call = next(c for c in conn.calls
                       if 'update app.users' in c[1] and 'auth_subject' in c[1])
    # Primer arg del UPDATE debe ser `pending|<uid.hex>`.
    assert update_call[2][0] == f'pending|{uid.hex}'


def test_auth0_admin_block_502_on_auth0_error(monkeypatch):
    """Si auth0_admin levanta Auth0ApiError → 502."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        block_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def boom(_user_id):
        raise auth0_admin.Auth0ApiError(500, '{"error":"upstream"}')
    monkeypatch.setattr(auth0_admin, 'block_user', boom)

    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|err', 'email': 'e@x.co'}],
    )
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(block_user_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 502
    assert 'auth0_block_failed' in exc.value.detail


def test_auth0_admin_delete_502_on_auth0_error(monkeypatch):
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        delete_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def boom(_user_id):
        raise auth0_admin.Auth0ApiError(404, '{"error":"not found"}')
    monkeypatch.setattr(auth0_admin, 'delete_user', boom)

    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|gone', 'email': 'g@x.co'}],
    )
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_user_in_auth0(
            uuid4(), _auth0_delete_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 502
    assert 'auth0_delete_failed' in exc.value.detail


# ═══════════════════════════════════════════════════════════════════════════
# M60/M-004 — payload validation + rate-limit per actor + confirmation
# ═══════════════════════════════════════════════════════════════════════════


def test_auth0_admin_payload_justification_too_short_rejected():
    """M-004: justification < 10 chars → pydantic ValidationError."""
    import pydantic  # noqa: PLC0415
    from app.api.v1.handlers.platform_admin_handlers import (
        Auth0AdminActionPayload,
    )
    with pytest.raises(pydantic.ValidationError):
        Auth0AdminActionPayload(justification='short')


def test_auth0_admin_delete_requires_confirm_true(monkeypatch):
    """M-004: DELETE con confirm=False explícito → 400."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        delete_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)
    monkeypatch.setattr(auth0_admin, 'delete_user',
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('should not call')))

    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|x', 'email': 'x@y.co'}],
    )
    req = _fake_request(roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_user_in_auth0(
            uuid4(), _auth0_delete_payload(confirm=False), req, conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'confirm' in exc.value.detail.lower()


def test_auth0_admin_mutate_rate_limit_enforced(monkeypatch):
    """M-004: 11º block del MISMO actor en <5min → 429."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        block_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_block(user_id): pass
    monkeypatch.setattr(auth0_admin, 'block_user', fake_block)

    req = _fake_request(
        roles=['platform_owner'], actor_id='auth0|attacker',
    )
    # 10 calls OK, 11º levanta 429.
    for i in range(10):
        conn = FakeConn(
            fetchrow=[{'auth_subject': f'auth0|t{i}', 'email': f't{i}@x.co'}],
            execute=['OK'],
        )
        asyncio.run(block_user_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    # 11º
    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|tx', 'email': 'tx@x.co'}],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(block_user_in_auth0(
            uuid4(), _auth0_action_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 429
    assert 'rate_limit' in exc.value.detail
    _reset_auth0_rate_limit()


def test_auth0_admin_destroy_rate_limit_stricter(monkeypatch):
    """M-004: delete tiene rate-limit propio más estricto: max 3/30min."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        delete_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_delete(user_id): pass
    monkeypatch.setattr(auth0_admin, 'delete_user', fake_delete)

    req = _fake_request(
        roles=['platform_owner'], actor_id='auth0|admin1',
    )
    # 3 deletes OK.
    for i in range(3):
        conn = FakeConn(
            fetchrow=[{'auth_subject': f'auth0|d{i}', 'email': f'd{i}@x.co'}],
            execute=['OK', 'OK'],
        )
        asyncio.run(delete_user_in_auth0(
            uuid4(), _auth0_delete_payload(), req, conn=conn,
        ))
    # 4º levanta.
    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|d4', 'email': 'd4@x.co'}],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_user_in_auth0(
            uuid4(), _auth0_delete_payload(), req, conn=conn,
        ))
    assert exc.value.status_code == 429
    _reset_auth0_rate_limit()


def test_auth0_admin_rate_limit_per_actor_isolated(monkeypatch):
    """M-004: el bucket es POR ACTOR — un actor saturado no afecta a otro."""
    _reset_auth0_rate_limit()
    from app.api.v1.handlers.platform_admin_handlers import (
        block_user_in_auth0,
    )
    from app.services import auth0_admin
    monkeypatch.setattr(auth0_admin, 'is_configured', lambda: True)

    async def fake_block(_uid): pass
    monkeypatch.setattr(auth0_admin, 'block_user', fake_block)

    # actor A satura su bucket (10/10).
    req_a = _fake_request(roles=['platform_owner'], actor_id='auth0|a')
    for _ in range(10):
        conn = FakeConn(
            fetchrow=[{'auth_subject': 'auth0|t', 'email': 't@x.co'}],
            execute=['OK'],
        )
        asyncio.run(block_user_in_auth0(
            uuid4(), _auth0_action_payload(), req_a, conn=conn,
        ))
    # actor B aún puede operar sin restricción.
    req_b = _fake_request(roles=['platform_owner'], actor_id='auth0|b')
    conn = FakeConn(
        fetchrow=[{'auth_subject': 'auth0|t', 'email': 't@x.co'}],
        execute=['OK'],
    )
    # Si esto no levanta, isolation funciona.
    asyncio.run(block_user_in_auth0(
        uuid4(), _auth0_action_payload(), req_b, conn=conn,
    ))
    _reset_auth0_rate_limit()
