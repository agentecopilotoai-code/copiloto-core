"""Tests unitarios para `copiloto_core.services.email` — Resend wrapper + Noop + templates.

No tocan red real: el ResendProvider se prueba con un FakeHttpClient
inyectado en `httpx.AsyncClient` via monkeypatch.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from copiloto_core.services.email import (
    EmailMessage, EmailNotConfiguredError, EmailSendError, NoopProvider,
    ResendProvider, _redact_email, _resolve_resend_api_key,
    clear_email_provider_cache, get_email_provider,
)


def _run(coro):
    return asyncio.run(coro)


# ─── _redact_email ──────────────────────────────────────────────────────


def test_redact_email_normal():
    assert _redact_email('alice@example.com') == 'a***e@example.com'


def test_redact_email_short_local():
    assert _redact_email('a@x.co') == '*@x.co'
    assert _redact_email('ab@x.co') == '**@x.co'


def test_redact_email_invalid():
    assert _redact_email('') == '[invalid]'
    assert _redact_email('noatpresent') == '[invalid]'


# ─── _resolve_resend_api_key ────────────────────────────────────────────


def test_resolve_resend_api_key_plaintext(monkeypatch):
    from copiloto_core.services import email as email_mod
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(
            resend_api_key='re_plain', resend_api_key_file=None,
        ),
    )
    assert _resolve_resend_api_key() == 're_plain'


def test_resolve_resend_api_key_file(monkeypatch, tmp_path):
    from copiloto_core.services import email as email_mod
    key_file = tmp_path / 'k'
    key_file.write_text('re_from_file\n', encoding='utf-8')
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(
            resend_api_key=None, resend_api_key_file=str(key_file),
        ),
    )
    # Debe trim el trailing newline.
    assert _resolve_resend_api_key() == 're_from_file'


def test_resolve_resend_api_key_none(monkeypatch):
    from copiloto_core.services import email as email_mod
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(resend_api_key=None, resend_api_key_file=None),
    )
    assert _resolve_resend_api_key() is None


def test_resolve_resend_api_key_file_missing(monkeypatch):
    from copiloto_core.services import email as email_mod
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(
            resend_api_key=None,
            resend_api_key_file='/non/existent/path/foo',
        ),
    )
    assert _resolve_resend_api_key() is None


# ─── NoopProvider ───────────────────────────────────────────────────────


def test_noop_provider_send_returns_fake_id():
    p = NoopProvider()
    assert p.is_real() is False
    assert p.name == 'noop'
    result = _run(p.send(EmailMessage(
        to='a@b.co', subject='hi', html='<p>x</p>', text='x',
    )))
    assert result.provider == 'noop'
    assert result.delivered_at_provider is False
    assert result.message_id.startswith('noop-')


# ─── ResendProvider ─────────────────────────────────────────────────────


def _patch_httpx_post(monkeypatch, *, status_code=200, body=None,
                       captured=None):
    """Inyecta un FakeAsyncClient que captura el POST y devuelve un
    response controlado."""
    body = body if body is not None else {'id': 'msg-fake-123'}
    captured = captured if captured is not None else {}

    class _FakeResponse:
        def __init__(self, sc, b):
            self.status_code = sc
            self._body = b
            self.text = '' if not b else str(b)[:500]
            self.content = b''.__class__()  # bytes
            import json as _json  # noqa: PLC0415
            self.content = _json.dumps(b).encode() if b else b''

        def json(self):
            return self._body

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def post(self, url, headers=None, json=None):
            captured['url'] = url
            captured['headers'] = headers
            captured['json'] = json
            return _FakeResponse(status_code, body)

    monkeypatch.setattr(httpx, 'AsyncClient', _FakeClient)
    return captured


def test_resend_provider_is_real():
    p = ResendProvider('re_x', 'from@x.co', 'X')
    assert p.is_real() is True
    assert p.name == 'resend'


def test_resend_provider_send_happy_path(monkeypatch):
    captured = _patch_httpx_post(monkeypatch, status_code=200,
                                 body={'id': 'msg-real-abc'})
    p = ResendProvider('re_test', 'invites@app.copilotoia.com', 'CopilotoIA')
    msg = EmailMessage(
        to='alice@example.com', subject='Welcome', html='<p>Hi</p>',
        text='Hi', reply_to='admin@x.co',
        headers={'List-Unsubscribe': '<mailto:x>'},
        tags={'type': 'invitation', 'tenant_id': 'abc'},
    )
    result = _run(p.send(msg))
    assert result.message_id == 'msg-real-abc'
    assert result.delivered_at_provider is True
    # Verifica payload enviado a Resend.
    body = captured['json']
    assert body['from'] == 'CopilotoIA <invites@app.copilotoia.com>'
    assert body['to'] == ['alice@example.com']
    assert body['subject'] == 'Welcome'
    assert body['reply_to'] == 'admin@x.co'
    assert body['headers'] == {'List-Unsubscribe': '<mailto:x>'}
    # Tags se transforman a lista de {name, value}.
    assert {'name': 'type', 'value': 'invitation'} in body['tags']
    assert {'name': 'tenant_id', 'value': 'abc'} in body['tags']
    # Auth header.
    assert captured['headers']['authorization'] == 'Bearer re_test'


def test_resend_provider_send_overrides_from(monkeypatch):
    captured = _patch_httpx_post(monkeypatch)
    p = ResendProvider('re_test', 'default@x.co', 'Default')
    _run(p.send(EmailMessage(
        to='x@y.co', subject='s', html='<p>h</p>', text='t',
        from_address='other@z.co', from_name='OtherName',
    )))
    assert captured['json']['from'] == 'OtherName <other@z.co>'


def test_resend_provider_send_no_name(monkeypatch):
    """Sin from_name, el field es solo el addr (no `<>`)."""
    captured = _patch_httpx_post(monkeypatch)
    p = ResendProvider('re_test', 'default@x.co', '')
    _run(p.send(EmailMessage(
        to='x@y.co', subject='s', html='<p>h</p>', text='t',
    )))
    # Cuando from_name es '', el formato es solo la addr.
    assert captured['json']['from'] == 'default@x.co'


def test_resend_provider_send_http_error_raises(monkeypatch):
    _patch_httpx_post(
        monkeypatch, status_code=422,
        body={'message': 'from_not_verified'},
    )
    p = ResendProvider('re_test', 'unverified@x.co', 'X')
    with pytest.raises(EmailSendError) as exc:
        _run(p.send(EmailMessage(
            to='x@y.co', subject='s', html='<p>h</p>', text='t',
        )))
    assert exc.value.status_code == 422
    assert 'from_not_verified' in (exc.value.body or '')


def test_resend_provider_send_transport_error_raises(monkeypatch):
    class _BrokenClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def post(self, *a, **kw):
            raise httpx.ConnectError(
                'unreachable',
                request=httpx.Request('POST', 'http://x'),
            )
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: _BrokenClient())
    p = ResendProvider('re_test', 'x@y.co', 'X')
    with pytest.raises(EmailSendError) as exc:
        _run(p.send(EmailMessage(
            to='a@b.co', subject='s', html='<p>h</p>', text='t',
        )))
    assert exc.value.status_code is None
    assert 'transport' in str(exc.value).lower()


# ─── get_email_provider singleton ───────────────────────────────────────


def test_get_email_provider_returns_noop_without_key(monkeypatch):
    from copiloto_core.services import email as email_mod
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(
            resend_api_key=None, resend_api_key_file=None,
            email_from_address='x@y.co', email_from_name='X',
        ),
    )
    clear_email_provider_cache()
    p = get_email_provider()
    assert isinstance(p, NoopProvider)


def test_get_email_provider_returns_resend_with_key(monkeypatch):
    from copiloto_core.services import email as email_mod
    monkeypatch.setattr(
        email_mod, 'get_settings',
        lambda: SimpleNamespace(
            resend_api_key='re_xxx', resend_api_key_file=None,
            email_from_address='x@y.co', email_from_name='X',
        ),
    )
    clear_email_provider_cache()
    p = get_email_provider()
    assert isinstance(p, ResendProvider)
    clear_email_provider_cache()  # cleanup


def test_clear_email_provider_cache():
    clear_email_provider_cache()  # smoke


# ─── EmailNotConfiguredError exists (smoke) ─────────────────────────────


def test_email_not_configured_error_class():
    err = EmailNotConfiguredError('foo')
    assert str(err) == 'foo'


# ─── Templates render correctly ─────────────────────────────────────────


def test_render_invitation_email_es_basic():
    from copiloto_core.services.email_templates import render_invitation_email
    rendered = render_invitation_email(
        invitee_email='ana@x.co',
        tenant_name='Clínica Norte',
        role='admin',
        inviter_name='Carlos Pérez',
        inviter_email='carlos@x.co',
        accept_url='https://app.copilotoia.com/i/abc123',
        expires_in_days=7,
    )
    assert 'Te invitaron a Clínica Norte' in rendered.subject
    # HTML contiene el rol traducido + el accept_url.
    assert 'Administrador' in rendered.html
    assert 'https://app.copilotoia.com/i/abc123' in rendered.html
    assert 'Carlos Pérez' in rendered.html
    assert 'Clínica Norte' in rendered.html
    # Plaintext con misma info.
    assert 'Administrador' in rendered.text
    assert 'Carlos Pérez' in rendered.text
    assert 'https://app.copilotoia.com/i/abc123' in rendered.text


def test_render_invitation_email_escapes_html_injection():
    """tenant_name malicioso no debe quebrar el HTML."""
    from copiloto_core.services.email_templates import render_invitation_email
    rendered = render_invitation_email(
        invitee_email='x@y.co',
        tenant_name='<script>alert(1)</script>Evil',
        role='viewer',
        inviter_name=None,
        inviter_email=None,
        accept_url='https://x/i/t',
        expires_in_days=7,
    )
    # El script tag fue escapado.
    assert '<script>alert(1)</script>' not in rendered.html
    assert '&lt;script&gt;' in rendered.html
    # Pero el plaintext sí lo lleva crudo (es text, no peligroso).
    assert '<script>alert(1)</script>' in rendered.text


def test_render_invitation_email_unknown_role_capitalizes():
    from copiloto_core.services.email_templates import render_invitation_email
    rendered = render_invitation_email(
        invitee_email='x@y.co',
        tenant_name='T',
        role='custom_role',
        inviter_name=None,
        inviter_email=None,
        accept_url='https://x/i/t',
        expires_in_days=7,
    )
    assert 'Custom_role' in rendered.html


def test_render_invitation_email_no_inviter_fallback():
    from copiloto_core.services.email_templates import render_invitation_email
    rendered = render_invitation_email(
        invitee_email='x@y.co',
        tenant_name='T',
        role='admin',
        inviter_name=None,
        inviter_email=None,
        accept_url='https://x/i/t',
        expires_in_days=7,
    )
    assert 'el administrador' in rendered.html
