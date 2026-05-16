"""Static tests for UI-016.7-FU — backend `/v1/me/*` endpoints (user prefs).

Coverage:
- Schema: `app.user_preferences` table with the required columns + the
  `theme_override` check constraint + the `touch_updated_at` trigger.
- Router: `me_router` defined with `authenticate_request` at the router
  level and registered on the main `/v1` router.
- Endpoints: 6 expected routes (`/me/profile`, `/me/preferences`,
  `/me/notifications` GET/PATCH) + 2 stubs (`/me/sessions` GET, DELETE).
- Security: every handler resolves the user_id via
  `current_user_id_from_request(request, conn)` — no path-parameter subject
  is accepted, so a caller cannot mutate another user via `/me/*`.
- Audit: every PATCH path emits `audit(action='user.preferences_updated', ...)`.
- Frontend: `coreApi.js` exposes the 8 helpers needed by `AccountProfile`,
  `AccountNotifications`, `AccountSessions`.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import Depends

from app.api.v1 import routes as routes_module

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ACCOUNT_PROFILE = Path('admin-panel/src/features/account/AccountProfile.jsx')
ACCOUNT_NOTIFICATIONS = Path('admin-panel/src/features/account/AccountNotifications.jsx')
ACCOUNT_SESSIONS = Path('admin-panel/src/features/account/AccountSessions.jsx')


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_user_preferences_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.user_preferences (' in schema
    for column in (
        'user_id uuid primary key references app.users(id) on delete cascade',
        'display_name text null',
        'phone text null',
        "locale text null default 'es-CO'",
        "timezone text null default 'America/Bogota'",
        "theme_override text null check (theme_override is null or theme_override in ('auto','light','dark'))",
        "notification_matrix jsonb not null default '{}'::jsonb",
        'auth0_synced_at timestamptz null',
        'created_at timestamptz not null default now()',
        'updated_at timestamptz not null default now()',
    ):
        assert column in schema, f'missing in user_preferences schema: {column}'


def test_schema_registers_touch_trigger_for_user_preferences():
    schema = SCHEMA.read_text()
    assert (
        'create trigger trg_user_preferences_touch before update on app.user_preferences'
        in schema
    )


def test_schema_declares_task_marker_for_migration_hint():
    # Existing deployments need a `create table if not exists` migration step
    # — the inline comment block is the runbook hint operators look for.
    schema = SCHEMA.read_text()
    assert 'TASK-UI-016.7-FU' in schema


# ───── Router definition ───────────────────────────────────────────────────


def test_me_router_defined_with_authenticate_dependency():
    me_router = routes_module.me_router
    assert me_router is not None
    # router-level dependencies are FastAPI `Depends(...)` instances; the
    # underlying function must be `authenticate_request`.
    dep_targets = [
        d.dependency for d in me_router.dependencies if isinstance(d, type(Depends(lambda: None)))
    ]
    assert routes_module.authenticate_request in dep_targets, (
        'me_router must enforce authenticate_request at the router level'
    )


def test_me_router_registered_on_main_router():
    main_router = routes_module.router
    paths = {getattr(r, 'path', '') for r in main_router.routes if hasattr(r, 'path')}
    # /v1 prefix is on `router`; the sub-router contributes /me/* paths.
    assert '/v1/me/profile' in paths
    assert '/v1/me/preferences' in paths
    assert '/v1/me/notifications' in paths
    assert '/v1/me/sessions' in paths


# ───── Endpoint coverage ───────────────────────────────────────────────────


def test_me_router_exposes_expected_endpoints():
    paths_with_methods = {
        (getattr(r, 'path', ''), tuple(sorted(getattr(r, 'methods', []) or [])))
        for r in routes_module.me_router.routes
        if hasattr(r, 'path')
    }
    expected = {
        ('/me/profile', ('GET',)),
        ('/me/profile', ('PATCH',)),
        ('/me/preferences', ('GET',)),
        ('/me/preferences', ('PATCH',)),
        ('/me/notifications', ('GET',)),
        ('/me/notifications', ('PATCH',)),
        ('/me/sessions', ('GET',)),
        ('/me/sessions/{session_id}', ('DELETE',)),
    }
    assert expected.issubset(paths_with_methods), (
        f'missing endpoints: {expected - paths_with_methods}'
    )


# ───── Security: every handler resolves user_id from the JWT ────────────────


def test_every_me_handler_uses_current_user_id_from_request():
    # The whole point of this router is that the subject NEVER comes from
    # a path parameter — it always comes from the validated JWT via
    # `current_user_id_from_request`. Verifying this in source ensures no
    # one regresses to a `/me/{user_id}/...` shape that would let admins
    # mutate someone else's row.
    handlers = (
        routes_module.get_my_profile,
        routes_module.patch_my_profile,
        routes_module.get_my_preferences,
        routes_module.patch_my_preferences,
        routes_module.get_my_notifications,
        routes_module.patch_my_notifications,
        routes_module.list_my_sessions,
        routes_module.revoke_my_session,
    )
    for handler in handlers:
        source = inspect.getsource(handler)
        assert '_require_current_user' in source or 'current_user_id_from_request' in source, (
            f'{handler.__name__} must resolve the user from the JWT, not a path param'
        )


def test_no_me_endpoint_accepts_a_user_id_path_parameter():
    # Regression gate: a /me/{user_id}/... shape would mean a caller could
    # claim to be another user. Verify every path is "/me/..." with no
    # user-id segment.
    for r in routes_module.me_router.routes:
        path = getattr(r, 'path', '') or ''
        if not path:
            continue
        assert not path.startswith('/me/{user_id}'), (
            f'{path} would allow cross-user mutation; remove the user_id path param'
        )
        # `{session_id}` on DELETE is fine — it identifies the session
        # being revoked, not the subject (the subject still comes from the JWT).


# ───── Audit emission on every PATCH path ──────────────────────────────────


def test_patch_my_profile_emits_user_preferences_updated_audit():
    source = inspect.getsource(routes_module.patch_my_profile)
    assert "action='user.preferences_updated'" in source
    assert "entity_type='user_preferences'" in source
    assert 'tenant_id=None' in source  # per-user, not per-tenant


def test_patch_my_preferences_emits_user_preferences_updated_audit():
    source = inspect.getsource(routes_module.patch_my_preferences)
    assert "action='user.preferences_updated'" in source
    assert "entity_type='user_preferences'" in source
    assert 'tenant_id=None' in source


def test_patch_my_notifications_emits_user_preferences_updated_audit():
    source = inspect.getsource(routes_module.patch_my_notifications)
    assert "action='user.preferences_updated'" in source
    assert "entity_type='user_preferences'" in source
    assert 'tenant_id=None' in source


def test_revoke_my_session_emits_audit_log():
    # DELETE /me/sessions/{sid} logs `user.session_revoked` (action renamed
    # from the stub-era `user.preferences_updated` once UI-016.7-FU-SESSIONS
    # shipped — the operation is no longer a placeholder).
    source = inspect.getsource(routes_module.revoke_my_session)
    assert "action='user.session_revoked'" in source
    assert "entity_type='user_session'" in source


# ───── Validation rules ────────────────────────────────────────────────────


def test_patch_my_profile_validates_timezone_via_zoneinfo():
    # SEC-010 hardening — timezone validation must catch ZoneInfoNotFoundError
    # AND ValueError so a malformed input does not 500. codex P2 (UI-016.7-FU
    # follow-up) — also catch TypeError + reject non-string up front so a JSON
    # value like {"timezone": 123} returns 422 instead of leaking 500.
    helper_src = inspect.getsource(routes_module._validate_timezone)
    assert 'ZoneInfo' in helper_src
    assert 'ZoneInfoNotFoundError' in helper_src
    assert 'ValueError' in helper_src
    assert 'TypeError' in helper_src  # codex P2: catch the non-string path
    assert 'isinstance(tz, str)' in helper_src  # explicit string check up front


def test_patch_my_profile_locale_validation_uses_helper_not_values_call():
    """codex P1 (UI-016.7-FU follow-up): SUPPORTED_COUNTRIES is a tuple, not a
    dict. The original code did `SUPPORTED_COUNTRIES.values()` which
    AttributeError'd and turned every locale-bearing PATCH into a 500. The fix
    iterates the tuple and calls `default_locale(code)` for each entry."""
    source = inspect.getsource(routes_module.patch_my_profile)
    # The buggy pattern MUST be gone.
    assert 'SUPPORTED_COUNTRIES.values()' not in source
    # The correct pattern uses default_locale + tuple iteration.
    assert 'default_locale' in source
    assert 'for code in SUPPORTED_COUNTRIES' in source


def test_patch_my_profile_validates_string_length_bounds():
    source = inspect.getsource(routes_module.patch_my_profile)
    # display_name and phone have explicit length caps so a malicious payload
    # cannot blow up the column or the audit log.
    assert '200' in source  # display_name length cap
    assert '32' in source  # phone length cap


def test_patch_my_preferences_validates_theme_override_enum():
    source = inspect.getsource(routes_module.patch_my_preferences)
    # Schema check enforces this too; the 422 path returns a clean message
    # before the DB layer rejects it.
    assert "'auto'" in source
    assert "'light'" in source
    assert "'dark'" in source


def test_patch_my_notifications_validates_channel_ids():
    helper_src = inspect.getsource(routes_module._validate_notification_matrix)
    # Channel ids are constrained to the catalog the frontend ships.
    assert "NOTIFICATION_CHANNEL_IDS" in helper_src
    catalog = routes_module.NOTIFICATION_CHANNEL_IDS
    assert catalog == ('email', 'wa', 'inapp')


# ───── /sessions handlers (UI-016.7-FU-SESSIONS shipped — no longer stubs) ─


def test_sessions_endpoints_reference_followup_ticket():
    # Both handlers cite UI-016.7-FU-SESSIONS in their docstring so a reader
    # walking the source can trace the design back to the ticket. (After
    # UI-016.7-FU-SESSIONS shipped, these are no longer stubs — see
    # `tests/test_auth_sessions_static.py` for full coverage.)
    list_src = inspect.getsource(routes_module.list_my_sessions)
    revoke_src = inspect.getsource(routes_module.revoke_my_session)
    assert 'UI-016.7-FU-SESSIONS' in list_src
    assert 'UI-016.7-FU-SESSIONS' in revoke_src


def test_revoke_my_session_rejects_unknown_session_id():
    # After UI-016.7-FU-SESSIONS the revoke handler queries `app.auth_sessions`
    # by id+user_id; an unknown id (not owned by this user / already revoked)
    # surfaces as 404 via the explicit ` 0` check on the asyncpg result string.
    source = inspect.getsource(routes_module.revoke_my_session)
    assert "result.endswith(' 0')" in source
    assert 'status_code=404' in source


# ───── Frontend wiring ─────────────────────────────────────────────────────


def test_core_api_exposes_me_endpoint_helpers():
    source = CORE_API.read_text()
    for helper in (
        'export function getMyProfile',
        'export function patchMyProfile',
        'export function getMyPreferences',
        'export function patchMyPreferences',
        'export function getMyNotifications',
        'export function patchMyNotifications',
        'export function listMySessions',
        'export function revokeMySession',
    ):
        assert helper in source, f'coreApi.js missing: {helper}'


def test_core_api_helpers_target_correct_paths_and_methods():
    source = CORE_API.read_text()
    # Path correctness — GET vs PATCH boundary.
    assert "request('/me/profile', { session })" in source
    assert "request('/me/profile', { method: 'PATCH', session, body: payload })" in source
    assert "request('/me/preferences', { session })" in source
    assert "request('/me/preferences', { method: 'PATCH', session, body: payload })" in source
    assert "request('/me/notifications', { session })" in source
    # The notifications helper wraps the matrix in `notification_matrix` per
    # the backend contract.
    assert 'notification_matrix: notificationMatrix' in source
    assert "request('/me/sessions', { session })" in source
    assert "method: 'DELETE'" in source


def test_account_profile_calls_patch_my_profile():
    source = ACCOUNT_PROFILE.read_text()
    assert 'patchMyProfile' in source
    assert 'getMyProfile' in source
    # Toast pattern of UI-016.5.
    assert 'useToast' in source
    assert 'toast.success' in source


def test_account_notifications_calls_patch_my_notifications():
    source = ACCOUNT_NOTIFICATIONS.read_text()
    assert 'patchMyNotifications' in source
    assert 'getMyNotifications' in source
    assert 'useToast' in source
    assert 'toast.success' in source


def test_account_sessions_calls_revoke_session_helper():
    source = ACCOUNT_SESSIONS.read_text()
    # GET wired (informative call) + DELETE wired only for `current` while
    # UI-016.7-FU-SESSIONS is pending.
    assert 'listMySessions' in source
    assert 'revokeMySession' in source
    assert 'UI-016.7-FU-SESSIONS' in source
