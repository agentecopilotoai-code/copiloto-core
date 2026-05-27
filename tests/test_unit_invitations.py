"""Tests para `app.services.invitations` — token gen + rate limit + flow E2E
con FakeConn (sin DB real)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.invitations import (
    InvitationRateLimitError, _reset_invitation_rate_buckets,
    create_and_send_invitation, generate_invitation_token,
    hash_invitation_token,
)


# ─── Helpers ────────────────────────────────────────────────────────────


class FakeConn:
    """Minimal fake asyncpg connection — captura calls, devuelve rows
    pre-cargadas. Espeja la API del FakeConn de
    test_unit_v1_handlers_harness.py."""

    def __init__(self, fetchrow_returns=None, fetch_returns=None,
                 execute_returns=None):
        self.fetchrow_queue = list(fetchrow_returns or [])
        self.fetch_queue = list(fetch_returns or [])
        self.execute_queue = list(execute_returns or [])
        self.calls: list[tuple[str, str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append(('fetchrow', sql, args))
        return self.fetchrow_queue.pop(0) if self.fetchrow_queue else None

    async def execute(self, sql, *args):
        self.calls.append(('execute', sql, args))
        return self.execute_queue.pop(0) if self.execute_queue else 'OK'

    async def fetch(self, sql, *args):
        self.calls.append(('fetch', sql, args))
        return self.fetch_queue.pop(0) if self.fetch_queue else []


def _stub_settings(monkeypatch, **overrides):
    """Reemplaza `app.services.invitations.get_settings` con un stub."""
    from app.services import invitations
    defaults = {
        'app_public_url': 'http://localhost:3000',
        'invitation_token_ttl_seconds': 7 * 24 * 3600,
        'invitation_send_rate_per_hour': 20,
        'email_from_address': 'invites@test.copilotoia.com',
        'email_from_name': 'CopilotoIA',
    }
    defaults.update(overrides)
    monkeypatch.setattr(
        invitations, 'get_settings', lambda: SimpleNamespace(**defaults),
    )


def _stub_provider(monkeypatch, *, real=True, status='queued',
                    message_id='msg-fake-1', raise_send=None):
    """Reemplaza `get_email_provider` con un stub controlado."""
    from app.services import invitations

    class _StubProvider:
        name = 'stub-resend' if real else 'stub-noop'

        def is_real(self):
            return real

        async def send(self, message):
            if raise_send:
                raise raise_send
            from app.services.email import EmailSendResult
            return EmailSendResult(
                message_id=message_id,
                provider=self.name,
                delivered_at_provider=(status == 'queued'),
            )

    provider = _StubProvider()
    monkeypatch.setattr(invitations, 'get_email_provider', lambda: provider)
    return provider


# ─── Token generation ────────────────────────────────────────────────────


def test_generate_invitation_token_uniqueness():
    t1, h1 = generate_invitation_token()
    t2, h2 = generate_invitation_token()
    assert t1 != t2
    assert h1 != h2
    # clear token = 64 chars hex (32 bytes).
    assert len(t1) == 64
    assert len(h1) == 64  # sha256


def test_hash_invitation_token_deterministic():
    t = 'a' * 64
    assert hash_invitation_token(t) == hash_invitation_token(t)
    # Pero el hash NO es igual al clear.
    assert hash_invitation_token(t) != t


def test_generate_invitation_token_hash_matches_recompute():
    clear, h = generate_invitation_token()
    assert hash_invitation_token(clear) == h


# ─── Rate limiting ──────────────────────────────────────────────────────


def test_invitation_rate_limit_blocks_actor_after_max(monkeypatch):
    _stub_settings(monkeypatch, invitation_send_rate_per_hour=3)
    _stub_provider(monkeypatch)
    _reset_invitation_rate_buckets()

    actor = uuid4()
    # 3 ok.
    for _ in range(3):
        conn = FakeConn(
            execute_returns=['UPDATE', 'OK'],
            fetchrow_returns=[{'id': uuid4(),
                                'expires_at': datetime.now(UTC)}],
        )
        asyncio.run(create_and_send_invitation(
            conn=conn, tenant_id=uuid4(),
            tenant_name='T', email='x@y.co', role='admin',
            inviter_user_id=actor,
        ))
    # 4to debe levantar.
    conn = FakeConn()
    with pytest.raises(InvitationRateLimitError):
        asyncio.run(create_and_send_invitation(
            conn=conn, tenant_id=uuid4(),
            tenant_name='T', email='x@y.co', role='admin',
            inviter_user_id=actor,
        ))
    _reset_invitation_rate_buckets()


def test_invitation_rate_limit_per_actor_isolated(monkeypatch):
    _stub_settings(monkeypatch, invitation_send_rate_per_hour=2)
    _stub_provider(monkeypatch)
    _reset_invitation_rate_buckets()

    actor_a = uuid4()
    actor_b = uuid4()
    for _ in range(2):
        conn = FakeConn(
            execute_returns=['UPDATE', 'OK'],
            fetchrow_returns=[{'id': uuid4(),
                                'expires_at': datetime.now(UTC)}],
        )
        asyncio.run(create_and_send_invitation(
            conn=conn, tenant_id=uuid4(),
            tenant_name='T', email='x@y.co', role='admin',
            inviter_user_id=actor_a,
        ))
    # actor_a saturado.
    conn = FakeConn()
    with pytest.raises(InvitationRateLimitError):
        asyncio.run(create_and_send_invitation(
            conn=conn, tenant_id=uuid4(),
            tenant_name='T', email='x@y.co', role='admin',
            inviter_user_id=actor_a,
        ))
    # actor_b puede operar.
    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],
        fetchrow_returns=[{'id': uuid4(),
                            'expires_at': datetime.now(UTC)}],
    )
    asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='T', email='y@y.co', role='admin',
        inviter_user_id=actor_b,
    ))
    _reset_invitation_rate_buckets()


def test_invitation_rate_limit_no_actor_id_skips(monkeypatch):
    """Sin actor_id (e.g. interno), no rate-limit."""
    _stub_settings(monkeypatch, invitation_send_rate_per_hour=1)
    _stub_provider(monkeypatch)
    _reset_invitation_rate_buckets()

    for _ in range(5):
        conn = FakeConn(
            execute_returns=['UPDATE', 'OK'],
            fetchrow_returns=[{'id': uuid4(),
                                'expires_at': datetime.now(UTC)}],
        )
        # No raise — porque inviter_user_id is None.
        asyncio.run(create_and_send_invitation(
            conn=conn, tenant_id=uuid4(),
            tenant_name='T', email='x@y.co', role='admin',
            inviter_user_id=None,
        ))


# ─── E2E flow del create_and_send_invitation ────────────────────────────


def test_create_and_send_invitation_happy_path(monkeypatch):
    _stub_settings(monkeypatch)
    _stub_provider(monkeypatch, status='queued', message_id='msg-real-99')
    _reset_invitation_rate_buckets()

    inv_id = uuid4()
    expires = datetime.now(UTC)
    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],  # supersede + post-send UPDATE
        fetchrow_returns=[{'id': inv_id, 'expires_at': expires}],
    )
    result = asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='Clínica Norte', email='ana@x.co', role='admin',
        inviter_user_id=uuid4(),
        inviter_name='Carlos', inviter_email='carlos@x.co',
    ))
    assert result.invitation_id == inv_id
    assert result.email_message_id == 'msg-real-99'
    assert result.email_status == 'queued'
    assert result.email_provider == 'stub-resend'
    assert result.accept_url.startswith('http://localhost:3000/i/')
    assert len(result.accept_url.rsplit('/', 1)[1]) == 64  # token len

    # Verifica que se hicieron 3 calls: supersede UPDATE + INSERT + UPDATE post-send.
    sqls = [c[1].strip().split()[0].lower() for c in conn.calls]
    assert 'update' in sqls
    assert 'insert' in sqls


def test_create_and_send_invitation_supersedes_existing_pending(monkeypatch):
    """Re-invitar al mismo email del mismo tenant marca el viejo como
    redeemed (superseded) y crea uno nuevo."""
    _stub_settings(monkeypatch)
    _stub_provider(monkeypatch)
    _reset_invitation_rate_buckets()

    conn = FakeConn(
        execute_returns=['UPDATE 1', 'OK'],
        fetchrow_returns=[{'id': uuid4(),
                            'expires_at': datetime.now(UTC)}],
    )
    asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='T', email='x@y.co', role='admin',
        inviter_user_id=None,
    ))
    # El primer UPDATE es el supersede — el SQL contiene 'superseded'.
    first_update = next(c for c in conn.calls if c[0] == 'execute'
                         and 'redeemed_at = now()' in c[1])
    assert 'superseded_at' in first_update[1]


def test_create_and_send_invitation_email_failure_persists_invitation(monkeypatch):
    """Si el provider falla, la invitación queda persistida con status
    'failed' — el caller puede reintentar via resend endpoint."""
    from app.services.email import EmailSendError
    _stub_settings(monkeypatch)
    _stub_provider(
        monkeypatch,
        raise_send=EmailSendError('resend_down', status_code=503),
    )
    _reset_invitation_rate_buckets()

    inv_id = uuid4()
    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],
        fetchrow_returns=[{'id': inv_id, 'expires_at': datetime.now(UTC)}],
    )
    result = asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='T', email='x@y.co', role='admin',
        inviter_user_id=None,
    ))
    assert result.invitation_id == inv_id
    assert result.email_status == 'failed'
    assert result.email_message_id == ''
    # La row queda creada (INSERT happened) y se updateó con status failed.
    update_call = next(c for c in conn.calls if c[0] == 'execute'
                       and 'last_send_status = $2' in c[1])
    assert update_call[2][1] == 'failed'


def test_create_and_send_invitation_noop_status(monkeypatch):
    """Con NoopProvider (sin API key), status='noop' y delivered=false."""
    _stub_settings(monkeypatch)
    _stub_provider(monkeypatch, real=False, status='noop')
    _reset_invitation_rate_buckets()

    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],
        fetchrow_returns=[{'id': uuid4(),
                            'expires_at': datetime.now(UTC)}],
    )
    result = asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='T', email='x@y.co', role='admin',
        inviter_user_id=None,
    ))
    assert result.email_status == 'noop'
    assert result.email_provider == 'stub-noop'


def test_create_and_send_invitation_accept_url_uses_app_public_url(monkeypatch):
    _stub_settings(monkeypatch, app_public_url='https://app.copilotoia.com/')
    _stub_provider(monkeypatch)
    _reset_invitation_rate_buckets()

    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],
        fetchrow_returns=[{'id': uuid4(),
                            'expires_at': datetime.now(UTC)}],
    )
    result = asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=uuid4(),
        tenant_name='T', email='x@y.co', role='admin',
        inviter_user_id=None,
    ))
    # Trailing slash strip + /i/<token>.
    assert result.accept_url.startswith('https://app.copilotoia.com/i/')
    assert not result.accept_url.startswith('https://app.copilotoia.com//')


def test_create_and_send_invitation_renders_template_with_tenant_name(monkeypatch):
    """Verifica integración con template — el mensaje pasado al provider
    contiene el tenant_name."""
    _stub_settings(monkeypatch)
    captured: dict = {}

    class _CapturingProvider:
        name = 'capture'

        def is_real(self):
            return True

        async def send(self, message):
            captured['subject'] = message.subject
            captured['html'] = message.html
            captured['text'] = message.text
            captured['tags'] = message.tags
            from app.services.email import EmailSendResult
            return EmailSendResult(
                message_id='m-1', provider=self.name,
                delivered_at_provider=True,
            )

    from app.services import invitations
    monkeypatch.setattr(invitations, 'get_email_provider',
                        lambda: _CapturingProvider())
    _reset_invitation_rate_buckets()

    tid = uuid4()
    inv_id = uuid4()
    conn = FakeConn(
        execute_returns=['UPDATE', 'OK'],
        fetchrow_returns=[{'id': inv_id, 'expires_at': datetime.now(UTC)}],
    )
    asyncio.run(create_and_send_invitation(
        conn=conn, tenant_id=tid,
        tenant_name='Clínica Sur', email='x@y.co', role='manager',
        inviter_user_id=None,
    ))
    assert 'Clínica Sur' in captured['subject']
    assert 'Clínica Sur' in captured['html']
    assert 'Gerente' in captured['html']  # role 'manager' → 'Gerente'
    assert captured['tags']['type'] == 'invitation'
    assert captured['tags']['tenant_id'] == str(tid)
    assert captured['tags']['invitation_id'] == str(inv_id)
