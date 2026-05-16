"""Static tests for TASK-0085 / BUG06: Auth0 invitations go through a
``POST /api/v2/users`` step keyed by ``user_id`` and the password-change
ticket URL is never returned to the inviter.

The bug let an admin invite the email of an unrelated Auth0 account (e.g. a
platform support tenant) and receive a password-reset ticket valid for that
account — a complete account-takeover primitive. The fix:

  1. ``auth0_admin.invite_user`` first calls ``POST /users``. If Auth0
     responds with 409, raise ``Auth0UserAlreadyExists`` and refuse to issue
     a ticket against the pre-existing account.
  2. The ticket is generated keyed by the **new** ``user_id`` (not the
     email).
  3. ``invite_user`` returns ``{auth0_user_id, invited}`` — no ``ticket_url``.
     The URL is logged server-side only.
  4. ``audit_logs(action='tenant_member.invited')`` records ``auth0_user_id``
     and a SHA256 fingerprint of the email, not the plaintext address.
  5. The route maps ``Auth0UserAlreadyExists`` to ``HTTPException(409, ...)``.
  6. The Admin Panel removes the "copy ticket URL" banner — Auth0's own
     email template delivers the invitation to the new user.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app.services.auth0_admin import (
    Auth0UserAlreadyExists,
    _random_initial_password,
    invite_user,
)

ROUTES = Path('app/api/v1/routes.py')
AUTH0 = Path('app/services/auth0_admin.py')
# UI-007.13: the TeamModule was redesigned into a feature directory.
TEAM_FEATURE = Path('admin-panel/src/features/owner-admin/team')


def _team_feature_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TEAM_FEATURE.rglob('*.js*')))


# ── Source-level invariants on invite_user ─────────────────────────────────


def test_invite_user_calls_post_users_before_password_change_ticket():
    source = AUTH0.read_text()
    start = source.index('async def invite_user(')
    end = source.index('\ndef _random_initial_password(', start)
    block = source[start:end]
    # Order matters: /users MUST come first.
    users_idx = block.index("'POST', '/users'")
    ticket_idx = block.index("'POST', '/tickets/password-change'")
    assert users_idx < ticket_idx
    # And the ticket payload is keyed by user_id, not email. The body is
    # built just above the request call.
    ticket_body_idx = block.index('ticket_body = {')
    body_block = block[ticket_body_idx:ticket_idx]
    assert "'user_id': auth0_user_id" in body_block
    assert "'email': email" not in body_block


def test_invite_user_returns_auth0_user_id_not_ticket_url():
    source = AUTH0.read_text()
    start = source.index('async def invite_user(')
    end = source.index('\ndef _random_initial_password(', start)
    block = source[start:end]
    # Successful return must include auth0_user_id + invited flag and must
    # NOT propagate ``ticket`` / ``ticket_url`` in the dict.
    success_return = block[block.rindex('return {'):]
    assert "'auth0_user_id'" in success_return
    assert "'invited'" in success_return
    assert 'ticket_url' not in success_return
    assert "'ticket'" not in success_return


def test_invite_user_raises_typed_conflict_for_existing_auth0_user():
    source = AUTH0.read_text()
    # The helper raises Auth0UserAlreadyExists on Auth0 409 responses.
    assert 'class Auth0UserAlreadyExists' in source
    assert 'raise Auth0UserAlreadyExists' in source


def test_random_initial_password_is_high_entropy_and_complex():
    pw = _random_initial_password()
    # Length covers Auth0's strictest tier.
    assert len(pw) >= 16
    # Includes upper, lower, digit/symbol mix expected by Auth0 policies.
    assert any(c.isupper() for c in pw)
    assert any(c.islower() or c.isdigit() for c in pw)
    assert any(not c.isalnum() for c in pw)


# ── invite_user behaviour with a mocked _mgmt_request ──────────────────────


def _build_invite_with_mock(monkeypatch, mgmt_responses):
    """Patch settings + _mgmt_request so invite_user runs end-to-end without
    touching Auth0."""
    from app.core.config import get_settings
    from app.services import auth0_admin

    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    monkeypatch.setenv('AUTH0_ADMIN_CLIENT_ID', 'cid')
    monkeypatch.setenv('AUTH0_ADMIN_CLIENT_SECRET', 'csecret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()

    calls: list[tuple[str, str, dict | None]] = []

    async def fake_mgmt_request(method, path, *, json_body=None):
        calls.append((method, path, json_body))
        action = mgmt_responses.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    monkeypatch.setattr(auth0_admin, '_mgmt_request', fake_mgmt_request)
    return calls


def test_invite_user_returns_user_id_and_no_ticket_url(monkeypatch):
    # BUG-009 actualizó este flow para propagar tenant_id + asignar role Auth0
    # antes del ticket. La secuencia ahora es: POST /users → PATCH /users/{id}
    # (app_metadata) → GET /roles (cache role_id) → POST /users/{id}/roles
    # (assign) → POST /tickets/password-change. El test cubre todos los calls
    # y verifica la order semántica.
    from app.services.auth0_admin import clear_auth0_role_cache
    clear_auth0_role_cache()  # tests previos pueden haber poblado el cache

    calls = _build_invite_with_mock(
        monkeypatch,
        mgmt_responses=[
            {'user_id': 'auth0|new-user-123'},  # POST /users
            {},  # PATCH /users/{id} (set app_metadata)
            [  # GET /roles?per_page=100
                {'id': 'rol_admin_xyz', 'name': 'admin'},
                {'id': 'rol_owner_abc', 'name': 'owner'},
            ],
            {},  # POST /users/{id}/roles
            {'ticket': 'https://example.auth0.com/lo/reset?ticket=abc'},  # POST /tickets/password-change
        ],
    )

    result = asyncio.run(
        invite_user(
            email='nuevo@empresa.com',
            role='admin',
            tenant_id='00000000-0000-0000-0000-000000000001',
            display_name='Nuevo',
        )
    )

    assert result['disabled'] is False
    assert result['invited'] is True
    assert result['auth0_user_id'] == 'auth0|new-user-123'
    assert 'ticket' not in result
    assert 'ticket_url' not in result
    # No hubo errores de propagación — el dict no debe incluir la key.
    assert 'propagation_errors' not in result

    # /users called first with the right email + connection.
    assert calls[0][0] == 'POST'
    assert calls[0][1] == '/users'
    assert calls[0][2]['email'] == 'nuevo@empresa.com'
    assert calls[0][2]['email_verified'] is False
    assert 'connection' in calls[0][2]
    # BUG-009: PATCH /users/{id} con app_metadata.
    assert calls[1][0] == 'PATCH'
    assert calls[1][1] == '/users/auth0|new-user-123'
    assert calls[1][2]['app_metadata']['tenant_id'] == '00000000-0000-0000-0000-000000000001'
    assert calls[1][2]['app_metadata']['default_tenant_id'] == '00000000-0000-0000-0000-000000000001'
    # BUG-009: GET /roles?per_page=100 para resolver role_id por nombre.
    assert calls[2][0] == 'GET'
    assert calls[2][1] == '/roles?per_page=100'
    # BUG-009: POST /users/{id}/roles con el role_id resuelto.
    assert calls[3][0] == 'POST'
    assert calls[3][1] == '/users/auth0|new-user-123/roles'
    assert calls[3][2]['roles'] == ['rol_admin_xyz']
    # /tickets/password-change called last, keyed by user_id.
    assert calls[4][0] == 'POST'
    assert calls[4][1] == '/tickets/password-change'
    assert calls[4][2]['user_id'] == 'auth0|new-user-123'
    assert 'email' not in calls[4][2]


def test_invite_user_propagates_conflict_for_preexisting_auth0_user(monkeypatch):
    _build_invite_with_mock(
        monkeypatch,
        mgmt_responses=[Auth0UserAlreadyExists('email already taken')],
    )

    with pytest.raises(Auth0UserAlreadyExists):
        asyncio.run(
            invite_user(
                email='soporte@plataforma.com',
                role='admin',
                tenant_id='00000000-0000-0000-0000-000000000001',
            )
        )


def test_invite_user_does_not_issue_ticket_if_users_call_lacks_user_id(monkeypatch):
    """Defense: if Auth0 returns 2xx but no user_id, abort with error and
    NEVER issue a ticket against an unknown identity."""
    calls = _build_invite_with_mock(
        monkeypatch,
        mgmt_responses=[
            {},  # /users returns nothing
            # /tickets/password-change must NOT be called — extra response
            # left here to fail loudly if it is.
            {'ticket': 'https://example.auth0.com/lo/reset?ticket=xyz'},
        ],
    )

    result = asyncio.run(
        invite_user(
            email='nuevo@empresa.com',
            role='admin',
            tenant_id='00000000-0000-0000-0000-000000000001',
        )
    )

    assert result['disabled'] is False
    assert 'error' in result
    # Only the /users call should have happened.
    assert len(calls) == 1


def test_invite_user_disabled_when_management_creds_missing(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()

    result = asyncio.run(
        invite_user(
            email='nuevo@empresa.com',
            role='admin',
            tenant_id='00000000-0000-0000-0000-000000000001',
        )
    )
    assert result == {'disabled': True}


# ── Route-level wiring: 409 mapping, audit shape, no ticket in response ───


def test_route_maps_auth0_user_already_exists_to_409():
    source = ROUTES.read_text()
    # The invite handler imports the exception type and converts it to 409.
    assert 'Auth0UserAlreadyExists' in source
    pattern = re.compile(
        r'except Auth0UserAlreadyExists.*?raise HTTPException\(\s*status_code=409',
        re.DOTALL,
    )
    assert pattern.search(source) is not None


def test_route_does_not_include_ticket_url_in_response():
    source = ROUTES.read_text()
    # Look at the invite_member handler block.
    start = source.index('auth0_result = await auth0_invite_user(')
    # Take a wide window and confirm no ticket_url is propagated into member.
    end = source.index("return member", start) + 50
    block = source[start:end]
    assert 'ticket_url' not in block
    # The response only contains a curated dict.
    assert "'auth0_user_id'" in block
    assert 'invited' in block


def test_audit_logs_auth0_user_id_and_email_fingerprint_not_plain_email():
    source = ROUTES.read_text()
    audit_block = source[source.index("action='tenant_member.invited'") - 600:
                         source.index("action='tenant_member.invited'") + 800]
    assert 'auth0_user_id' in audit_block
    assert 'email_fingerprint' in audit_block
    # The metadata must not push the raw email through.
    assert "metadata={'email': email" not in source


def test_route_binds_auth_subject_when_invite_returns_user_id():
    source = ROUTES.read_text()
    block = source[source.index('Auth0UserAlreadyExists'):source.index('return member')]
    assert 'set auth_subject=$2' in block
    assert "auth0_result.get('auth0_user_id')" in block


# ── UI: no ticket banner, success copy mentions Auth0 email delivery ───────


def test_team_ui_removes_ticket_url_banner():
    source = _team_feature_source()
    assert 'ticket_url' not in source
    assert 'pendingTicket' not in source
    assert 'Copiar' not in source or 'ticket' not in source.lower().split('copiar')[0][-200:]


def test_team_ui_success_message_mentions_auth0_email_flow():
    source = _team_feature_source()
    assert 'recibirá un email de Auth0' in source
