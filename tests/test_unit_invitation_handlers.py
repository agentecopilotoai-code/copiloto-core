"""Tests para `app.api.v1.handlers.invitation_handlers` (M65).

Cubre los handlers públicos + autenticados sin necesidad de DB real —
monkeypatcheamos las funciones de servicio (`get_invitation_preview` y
`redeem_invitation`) que ya tienen sus tests propios en
`test_unit_invitations.py`.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import invitations as invitations_service


# ─── Fixtures ────────────────────────────────────────────────────────────


def _preview(*, redeemed: bool = False, tenant_name: str = 'Demo Tenant',
             role: str = 'admin', email: str = 'inv@example.com'):
    return invitations_service.InvitationPreview(
        invitation_id=uuid4(),
        tenant_id=uuid4(),
        tenant_name=tenant_name,
        role=role,
        email=email,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        redeemed=redeemed,
    )


def _fake_request_state(*, actor_id='auth0|abc', email='inv@example.com',
                         actor_type='user'):
    """Construye un Request con state.actor_id/email setteados como lo
    haría `authenticate_request`. Pasamos el state via objeto simple
    (no inicializamos Starlette state completo)."""
    from types import SimpleNamespace
    from starlette.requests import Request as StarletteRequest

    # Truco: usamos scope mínimo + asignamos state directamente al instance.
    scope = {
        'type': 'http', 'method': 'POST', 'path': '/',
        'headers': [], 'query_string': b'', 'app': None,
    }
    req = StarletteRequest(scope)
    state_ns = SimpleNamespace(
        actor_id=actor_id, email=email, actor_type=actor_type,
        user_id=None,  # _require_current_user lo cachea
    )
    # Starlette state es un singleton vacío — sobreescribimos.
    req._state = state_ns  # type: ignore[attr-defined]
    # Acceso state.X via property que lee _state.
    req.scope['state'] = state_ns  # type: ignore[index]
    return req


def _patch_require_current_user(monkeypatch, user_id):
    """`_require_current_user` toca la DB para resolver user_id desde
    actor_id. Lo monkeypatcheamos para que devuelva un UUID fijo."""
    from app.api.v1.handlers import invitation_handlers

    async def _stub(request, conn):
        return user_id

    monkeypatch.setattr(invitation_handlers, '_require_current_user', _stub)


# ─── GET /v1/invitations/{token} (público) ───────────────────────────────


def test_get_invitation_404_when_token_unknown(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import get_invitation

    async def _stub_preview(conn, token):
        return None

    monkeypatch.setattr(invitations_service, 'get_invitation_preview', _stub_preview)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_invitation('a' * 64, conn=object()))
    assert exc_info.value.status_code == 404


def test_get_invitation_returns_dict_when_valid(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import get_invitation
    preview = _preview()

    async def _stub_preview(conn, token):
        return preview

    monkeypatch.setattr(invitations_service, 'get_invitation_preview', _stub_preview)
    out = asyncio.run(get_invitation('a' * 64, conn=object()))
    assert out['tenant_name'] == 'Demo Tenant'
    assert out['role'] == 'admin'
    assert out['email'] == 'inv@example.com'
    assert out['redeemed'] is False
    assert 'expires_at' in out
    assert 'invitation_id' in out
    assert 'tenant_id' in out


def test_get_invitation_marks_redeemed_flag(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import get_invitation

    async def _stub_preview(conn, token):
        return _preview(redeemed=True)

    monkeypatch.setattr(invitations_service, 'get_invitation_preview', _stub_preview)
    out = asyncio.run(get_invitation('a' * 64, conn=object()))
    assert out['redeemed'] is True


# ─── POST /v1/invitations/{token}/redeem (autenticado) ───────────────────


def test_redeem_invitation_403_when_no_email_in_jwt(monkeypatch):
    """Si el JWT no incluye el claim email (A-003 — namespaced), no
    podemos validar email-match → 403 + mensaje pedir re-login."""
    from app.api.v1.handlers.invitation_handlers import redeem_invitation
    user_id = uuid4()
    _patch_require_current_user(monkeypatch, user_id)
    req = _fake_request_state(email=None)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(redeem_invitation('a' * 64, req, conn=object()))
    assert exc_info.value.status_code == 403
    assert 'email' in str(exc_info.value.detail).lower()


def test_redeem_invitation_404_when_token_unknown(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import redeem_invitation
    user_id = uuid4()
    _patch_require_current_user(monkeypatch, user_id)

    async def _stub_redeem(**kw):
        raise invitations_service.InvitationNotFoundError('not found')

    monkeypatch.setattr(invitations_service, 'redeem_invitation', _stub_redeem)
    req = _fake_request_state()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(redeem_invitation('a' * 64, req, conn=object()))
    assert exc_info.value.status_code == 404


def test_redeem_invitation_410_when_expired(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import redeem_invitation
    user_id = uuid4()
    _patch_require_current_user(monkeypatch, user_id)

    async def _stub_redeem(**kw):
        raise invitations_service.InvitationExpiredError('expired')

    monkeypatch.setattr(invitations_service, 'redeem_invitation', _stub_redeem)
    req = _fake_request_state()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(redeem_invitation('a' * 64, req, conn=object()))
    assert exc_info.value.status_code == 410


def test_redeem_invitation_403_when_email_mismatch(monkeypatch):
    """Anti-hijack: el JWT email no matchea el de la invitación → 403."""
    from app.api.v1.handlers.invitation_handlers import redeem_invitation
    user_id = uuid4()
    _patch_require_current_user(monkeypatch, user_id)

    async def _stub_redeem(**kw):
        raise invitations_service.InvitationEmailMismatchError('mismatch')

    monkeypatch.setattr(invitations_service, 'redeem_invitation', _stub_redeem)
    req = _fake_request_state(email='attacker@evil.co')
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(redeem_invitation('a' * 64, req, conn=object()))
    assert exc_info.value.status_code == 403


def test_redeem_invitation_happy_path_returns_dict(monkeypatch):
    from app.api.v1.handlers.invitation_handlers import redeem_invitation
    user_id = uuid4()
    _patch_require_current_user(monkeypatch, user_id)
    preview = _preview(redeemed=True)

    async def _stub_redeem(**kw):
        assert kw['redeemer_user_id'] == user_id
        assert kw['redeemer_email'] == 'inv@example.com'
        assert kw['clear_token'] == 'a' * 64
        return preview

    monkeypatch.setattr(invitations_service, 'redeem_invitation', _stub_redeem)
    req = _fake_request_state()
    out = asyncio.run(redeem_invitation('a' * 64, req, conn=object()))
    assert out['redeemed'] is True
    assert out['already_redeemed'] is True
    assert out['tenant_name'] == 'Demo Tenant'
