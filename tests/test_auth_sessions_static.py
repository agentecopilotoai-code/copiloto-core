"""Static tests for UI-016.7-FU-SESSIONS — server-side session store.

UI-016.7-FU shipeó `/v1/me/sessions` + `/v1/me/sessions/{sid}` como stubs
porque no existía la tabla `app.auth_sessions`. Este FU cierra ese gap:
schema + hook en `authenticate_request` que captura el `jti` del JWT +
`record_auth_session(...)` que upsertea por request + los dos endpoints
reales (list filtrado por `revoked_at is null` y delete que marca
`revoked_at`).

Cobertura del archivo (static — inspección de schema + source code, sin DB
viva, espejando el patrón de `test_user_preferences_static.py`):

1. Schema (`app.auth_sessions`): columnas + FK + índice activo +
   trigger touch + comentario `TASK-UI-016.7-FU-SESSIONS` para deployments
   existentes.
2. `authenticate_request`: setea `request.state.session_jti` + `token_iat`
   tanto en el branch anónimo (None) como en el branch usuario autenticado
   (desde `payload.get('jti')` / `payload.get('iat')`).
3. `_session_id_from_request`: prefiere `jti`, cae a hash de `sub+iat`,
   devuelve None para anónimo.
4. `record_auth_session`: upsertea con `on conflict ... do update`, filtra
   `revoked_at is null`, captura `user-agent` y `client.host`.
5. Endpoints reales (no stubs): list filtra `revoked_at is null` + ordena
   por `last_seen_at desc` + marca `current: True` por igualdad del id;
   delete acepta alias `current` y verifica result `0` para 404.
6. Audit: `user.session_revoked` (renombrado de `user.preferences_updated`).
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.core import security as security_module

SCHEMA = Path('infra/postgres/01-schema.sql')


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_auth_sessions_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.auth_sessions (' in schema
    for column in (
        'id text primary key',
        'user_id uuid not null references app.users(id) on delete cascade',
        'device text null',
        'user_agent text null',
        'ip inet null',
        'location text null',
        'created_at timestamptz not null default now()',
        'last_seen_at timestamptz not null default now()',
        'revoked_at timestamptz null',
        'updated_at timestamptz not null default now()',
    ):
        assert column in schema, f'missing in auth_sessions schema: {column}'


def test_schema_indexes_active_sessions_by_user():
    # `where revoked_at is null` keeps the index lean (no entries for revoked
    # sessions, which we never list). `last_seen_at desc` matches the ORDER BY
    # in `list_my_sessions` so the query is index-served.
    schema = SCHEMA.read_text()
    assert (
        'create index ix_auth_sessions_user_active on app.auth_sessions'
        '(user_id, last_seen_at desc) where revoked_at is null'
    ) in schema


def test_schema_registers_touch_trigger_for_auth_sessions():
    schema = SCHEMA.read_text()
    assert (
        'create trigger trg_auth_sessions_touch before update on app.auth_sessions'
        in schema
    )


def test_schema_declares_task_marker_for_migration_hint():
    # Existing deployments need a `create table if not exists` migration step
    # — the inline comment is the runbook anchor.
    schema = SCHEMA.read_text()
    assert 'TASK-UI-016.7-FU-SESSIONS' in schema


# ───── authenticate_request: jti capture ───────────────────────────────────


def test_authenticate_request_initializes_session_state_for_anonymous():
    # The anonymous branch (no Authorization header) MUST still set
    # session_jti/token_iat to None, so handlers can rely on the attribute
    # existing on request.state without `getattr` guards.
    source = inspect.getsource(security_module.authenticate_request)
    # Initial assignments (before `if not authorization:`).
    assert 'request.state.session_jti = None' in source
    assert 'request.state.token_iat = None' in source


def test_authenticate_request_extracts_jti_and_iat_from_validated_jwt():
    # On the authenticated branch, jti+iat come straight from the decoded
    # payload (no namespace gymnastics — these are standard JWT claims).
    source = inspect.getsource(security_module.authenticate_request)
    assert "request.state.session_jti = payload.get('jti')" in source
    assert "request.state.token_iat = payload.get('iat')" in source


# ───── _session_id_from_request: jti preferred, hash fallback ──────────────


def test_session_id_helper_prefers_jti():
    source = inspect.getsource(routes_module._session_id_from_request)
    # First branch: jti from request.state.session_jti.
    assert "getattr(request.state, 'session_jti', None)" in source
    # Returns it as-is (cast to str defensively).
    assert 'return str(jti)' in source


def test_session_id_helper_falls_back_to_sub_iat_hash():
    # When jti is missing, derive a stable id from `sub|iat` so the same JWT
    # always resolves to the same session row. SHA-256, truncated to 32 hex
    # chars, prefixed with `iat-` so audit logs can tell fallback from real
    # jti at a glance.
    source = inspect.getsource(routes_module._session_id_from_request)
    assert 'hashlib.sha256' in source
    assert "f'{actor_id}|{iat}'" in source
    assert "f'iat-{digest[:32]}'" in source


def test_session_id_helper_returns_none_for_unauthenticated_requests():
    source = inspect.getsource(routes_module._session_id_from_request)
    # Both actor_id and iat must be present; otherwise we can't construct a
    # stable id, so we return None (handlers guard with _require_current_user
    # before reaching here).
    assert 'if not actor_id or iat is None:' in source
    assert 'return None' in source


# ───── record_auth_session: upsert semantics ───────────────────────────────


def test_record_auth_session_inserts_on_conflict_updates_last_seen():
    # The `on conflict do update` keeps the SAME row alive across requests
    # (last_seen_at refreshed). user_agent/ip preserved via coalesce so a
    # request from a proxy that strips headers doesn't NULL out the original
    # values we captured at login time.
    source = inspect.getsource(routes_module.record_auth_session)
    assert 'insert into app.auth_sessions' in source
    assert 'on conflict (id) do update set' in source
    assert 'last_seen_at = now()' in source
    assert 'coalesce(excluded.user_agent, app.auth_sessions.user_agent)' in source
    assert 'coalesce(excluded.ip, app.auth_sessions.ip)' in source


def test_record_auth_session_does_not_revive_revoked_sessions():
    # If a session was revoked, the UPDATE branch of the upsert MUST NOT
    # reactivate it by bumping last_seen_at. The `where revoked_at is null`
    # clause on the update path enforces this.
    source = inspect.getsource(routes_module.record_auth_session)
    assert 'where app.auth_sessions.revoked_at is null' in source


def test_record_auth_session_captures_user_agent_and_ip():
    source = inspect.getsource(routes_module.record_auth_session)
    assert "request.headers.get('user-agent')" in source
    # `getattr(request, 'client', None)` defends against test clients that
    # don't expose `.client` (Starlette TestClient does, but some custom
    # fixtures don't).
    assert "getattr(request, 'client', None)" in source


def test_record_auth_session_returns_session_id_for_current_marker():
    # The return value is what `list_my_sessions` uses to flag `current: True`
    # in the response payload. Returning None for anonymous keeps the contract
    # explicit (callers can skip the marker).
    sig = inspect.signature(routes_module.record_auth_session)
    assert 'user_id' in sig.parameters
    source = inspect.getsource(routes_module.record_auth_session)
    assert 'return session_id' in source
    assert 'return None' in source


# ───── /me/sessions (list) ─────────────────────────────────────────────────


def test_list_my_sessions_is_no_longer_stubbed():
    # Confidence check that we're not accidentally re-shipping the stub
    # response — no `follow_up` key in the payload, no hardcoded
    # `[{'id': 'current', ...}]` list.
    source = inspect.getsource(routes_module.list_my_sessions)
    assert "'follow_up'" not in source
    assert "'id': 'current'" not in source


def test_list_my_sessions_records_current_session_first():
    # The handler MUST upsert via record_auth_session BEFORE the SELECT, so
    # the current session always shows up in the list (even on the very first
    # call from a brand-new JWT).
    source = inspect.getsource(routes_module.list_my_sessions)
    record_pos = source.find('record_auth_session(')
    select_pos = source.find('conn.fetch(')
    assert record_pos > 0 and select_pos > 0
    assert record_pos < select_pos, 'record_auth_session must run before the SELECT'


def test_list_my_sessions_filters_active_sessions_only():
    source = inspect.getsource(routes_module.list_my_sessions)
    assert 'where user_id = $1 and revoked_at is null' in source
    assert 'order by last_seen_at desc' in source


def test_list_my_sessions_marks_current_by_id_equality():
    # `current: True` is computed by direct equality with the id returned
    # from record_auth_session — NOT by sorting/heuristic on last_seen_at
    # (which would flap if two tabs hit the endpoint nearly simultaneously).
    source = inspect.getsource(routes_module.list_my_sessions)
    assert "'current': row['id'] == current_sid" in source


# ───── /me/sessions/{session_id} (delete/revoke) ───────────────────────────


def test_revoke_my_session_resolves_current_alias():
    # Frontend can pass `current` instead of repeating the jti; the handler
    # resolves it to the same id record_auth_session would compute, then
    # delegates to the normal path (no duplicated UPDATE logic).
    source = inspect.getsource(routes_module.revoke_my_session)
    assert "if session_id == 'current':" in source
    assert '_session_id_from_request(request)' in source


def test_revoke_my_session_scopes_update_by_user_id():
    # CRITICAL: the WHERE clause includes `user_id = $2` so a user cannot
    # revoke another user's session even if they somehow learn the id. There
    # is no path parameter for `user_id` on any /me/* route (regression gate
    # for that already lives in test_user_preferences_static.py).
    source = inspect.getsource(routes_module.revoke_my_session)
    assert 'where id = $1 and user_id = $2 and revoked_at is null' in source


def test_revoke_my_session_returns_404_when_no_row_affected():
    # asyncpg returns the command tag (`UPDATE 0` / `UPDATE 1`); 0 means no
    # row matched the WHERE — could be wrong user, wrong id, or already
    # revoked. All three look identical to the caller (404) so we don't leak
    # whether a given id exists in another user's session list.
    source = inspect.getsource(routes_module.revoke_my_session)
    assert "result.endswith(' 0')" in source
    assert "status_code=404" in source


def test_revoke_my_session_audit_uses_session_revoked_action():
    # Action renamed from the stub-era `user.preferences_updated` — the audit
    # category for sessions deserves its own verb so consent/billing tooling
    # can filter on it.
    source = inspect.getsource(routes_module.revoke_my_session)
    assert "action='user.session_revoked'" in source
    assert "metadata={" in source
    assert "'alias_used': session_id == 'current'" in source


# ───── Cross-cutting: handler signatures preserved ─────────────────────────


def test_session_handlers_still_use_require_current_user():
    # Both handlers derive user_id via `_require_current_user`, ensuring the
    # 401 path and the same auth-pickup as the rest of `/me/*`. This is the
    # gate that prevents anonymous reads.
    list_src = inspect.getsource(routes_module.list_my_sessions)
    revoke_src = inspect.getsource(routes_module.revoke_my_session)
    assert '_require_current_user(request, conn)' in list_src
    assert '_require_current_user(request, conn)' in revoke_src
