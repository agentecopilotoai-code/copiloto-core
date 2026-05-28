"""Tests para I-2 / QUAL (audit#3/#4) — advisory-lock race en
`create_invitation_record`.

Los tests existentes en `test_unit_invitations.py` mockean
`add_tenant_member` completo y NO ejercitan el orden real de
`pg_advisory_xact_lock` → `update supersede` → `insert new`. Esos
mocks confirman que `add_tenant_member` se llama, pero un refactor
podría romper el orden de las queries SIN hacer fallar a esos tests.

Este módulo captura la SECUENCIA de queries que `create_invitation_record`
emite a `conn.execute` para garantizar:

 1. `pg_advisory_xact_lock` se llama PRIMERO (antes del supersede).
 2. El `lock_key` es determinístico para mismo (tenant_id, email).
 3. Diferentes (tenant_id, email) → diferentes lock_keys.
 4. Email case-insensitive — `'Foo@x.com'` y `'foo@x.com'` mismo lock.

Verificación de concurrency REAL contra Postgres requiere fixture
de integración con asyncpg+DB; queda como TODO para CI de integración.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest


_T_ID_A = UUID('11111111-1111-1111-1111-111111111111')
_T_ID_B = UUID('22222222-2222-2222-2222-222222222222')


class _ExecCapture:
    """Adapter: registra cada `conn.execute(sql, *args)` en `.calls`."""

    def __init__(self, fetchrow_results: list | None = None,
                 fetchval_results: list | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._fetchrow_iter = iter(fetchrow_results or [])
        self._fetchval_iter = iter(fetchval_results or [])

    async def execute(self, sql: str, *args) -> None:
        self.calls.append((sql, args))

    async def fetchrow(self, sql: str, *args):
        self.calls.append((sql, args))
        try:
            return next(self._fetchrow_iter)
        except StopIteration:
            return None

    async def fetchval(self, sql: str, *args):
        self.calls.append((sql, args))
        try:
            return next(self._fetchval_iter)
        except StopIteration:
            return None


@pytest.mark.asyncio
async def test_advisory_lock_called_before_supersede_and_insert(monkeypatch):
    """Orden requerido: lock → supersede previo → insert nuevo."""
    from copiloto_core.services import invitations

    invitations._reset_invitation_rate_buckets()
    # Mock generate_invitation_token para determinismo.
    monkeypatch.setattr(
        invitations, 'generate_invitation_token',
        lambda: ('clear-token-xxx', 'hash-xxx'),
    )
    conn = _ExecCapture(
        fetchrow_results=[
            {'id': uuid4(), 'invitation_id': uuid4(),
             'expires_at': datetime(2026, 12, 31)},
        ],
    )
    await invitations.create_invitation_record(
        conn=conn,  # type: ignore[arg-type]
        tenant_id=_T_ID_A,
        email='alice@x.com',
        tenant_name='Demo',
        role='member',
        inviter_user_id=uuid4(),
        inviter_name='Bob',
        inviter_email='bob@x.com',
    )
    # Las 3 primeras queries deben ser, en orden: lock, supersede, insert.
    sqls = [c[0] for c in conn.calls]
    assert 'pg_advisory_xact_lock' in sqls[0], (
        f'first query should be advisory lock, got: {sqls[0]!r}'
    )
    # Después: el UPDATE supersede.
    assert any('update app.tenant_invitations' in s.lower() for s in sqls[1:3])
    # Después: el INSERT.
    assert any('insert into app.tenant_invitations' in s.lower() for s in sqls)


@pytest.mark.asyncio
async def test_advisory_lock_key_deterministic_for_same_tenant_and_email(
    monkeypatch,
):
    """Same (tenant, email) → same lock_key entre invocaciones."""
    from copiloto_core.services import invitations

    invitations._reset_invitation_rate_buckets()
    monkeypatch.setattr(
        invitations, 'generate_invitation_token',
        lambda: ('t', 'h'),
    )

    async def _run(email: str, tid: UUID) -> int:
        conn = _ExecCapture(fetchrow_results=[
            {'id': uuid4(), 'invitation_id': uuid4(),
             'expires_at': datetime(2026, 12, 31)},
        ])
        await invitations.create_invitation_record(
            conn=conn,  # type: ignore[arg-type]
            tenant_id=tid, email=email,
            tenant_name='X', role='member',
            inviter_user_id=uuid4(),
            inviter_name=None, inviter_email=None,
        )
        # Buscar la llamada al advisory_lock — extraer el arg.
        for sql, args in conn.calls:
            if 'pg_advisory_xact_lock' in sql:
                return args[0]
        raise AssertionError('advisory_lock query no encontrada')

    k1 = await _run('alice@x.com', _T_ID_A)
    k2 = await _run('alice@x.com', _T_ID_A)
    assert k1 == k2


@pytest.mark.asyncio
async def test_advisory_lock_key_email_case_insensitive(monkeypatch):
    """`Foo@x.com` y `foo@x.com` deben generar mismo lock_key."""
    from copiloto_core.services import invitations

    invitations._reset_invitation_rate_buckets()
    monkeypatch.setattr(
        invitations, 'generate_invitation_token', lambda: ('t', 'h'),
    )

    async def _key_for(email: str) -> int:
        conn = _ExecCapture(fetchrow_results=[
            {'id': uuid4(), 'invitation_id': uuid4(),
             'expires_at': datetime(2026, 12, 31)},
        ])
        await invitations.create_invitation_record(
            conn=conn,  # type: ignore[arg-type]
            tenant_id=_T_ID_A, email=email,
            tenant_name='X', role='member',
            inviter_user_id=uuid4(),
            inviter_name=None, inviter_email=None,
        )
        for sql, args in conn.calls:
            if 'pg_advisory_xact_lock' in sql:
                return args[0]
        raise AssertionError('no lock query')

    k_upper = await _key_for('Foo@X.com')
    k_lower = await _key_for('foo@x.com')
    assert k_upper == k_lower, (
        f'email case sensitivity en lock_key: {k_upper} != {k_lower}'
    )


@pytest.mark.asyncio
async def test_advisory_lock_key_differs_across_tenants(monkeypatch):
    """Diferentes tenants para mismo email → diferentes lock_keys (no
    bloqueo cruzado entre tenants)."""
    from copiloto_core.services import invitations

    invitations._reset_invitation_rate_buckets()
    monkeypatch.setattr(
        invitations, 'generate_invitation_token', lambda: ('t', 'h'),
    )

    async def _key_for(tid: UUID) -> int:
        conn = _ExecCapture(fetchrow_results=[
            {'id': uuid4(), 'invitation_id': uuid4(),
             'expires_at': datetime(2026, 12, 31)},
        ])
        await invitations.create_invitation_record(
            conn=conn,  # type: ignore[arg-type]
            tenant_id=tid, email='alice@x.com',
            tenant_name='X', role='member',
            inviter_user_id=uuid4(),
            inviter_name=None, inviter_email=None,
        )
        for sql, args in conn.calls:
            if 'pg_advisory_xact_lock' in sql:
                return args[0]
        raise AssertionError('no lock')

    k_a = await _key_for(_T_ID_A)
    k_b = await _key_for(_T_ID_B)
    assert k_a != k_b


@pytest.mark.asyncio
async def test_advisory_lock_key_within_postgres_bigint_range(monkeypatch):
    """pg_advisory_xact_lock acepta un BIGINT (signed, ±2^63)."""
    from copiloto_core.services import invitations

    invitations._reset_invitation_rate_buckets()
    monkeypatch.setattr(
        invitations, 'generate_invitation_token', lambda: ('t', 'h'),
    )
    conn = _ExecCapture(fetchrow_results=[
        {'id': uuid4(), 'invitation_id': uuid4(),
         'expires_at': datetime(2026, 12, 31)},
    ])
    await invitations.create_invitation_record(
        conn=conn,  # type: ignore[arg-type]
        tenant_id=_T_ID_A, email='alice@x.com',
        tenant_name='X', role='member',
        inviter_user_id=uuid4(),
        inviter_name=None, inviter_email=None,
    )
    for sql, args in conn.calls:
        if 'pg_advisory_xact_lock' in sql:
            key = args[0]
            assert isinstance(key, int)
            assert -(2**63) <= key < 2**63
            assert key >= 0  # usamos abs() en el código fuente.
            return
    raise AssertionError('advisory_lock no encontrada')
