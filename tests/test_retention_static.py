"""Static tests for TASK-0061 — Política de retención y purgado TTL (GDPR).

Coverage (≥12 tests):
1.  Schema declares ``app.data_retention_policies`` with CHECKs on entity,
    retention_days >= 30 and audit_logs_no_anonymize.
2.  Schema enables RLS and includes the table in the policy loop.
3.  ``default_policy_rows`` returns one row per entity with the documented
    defaults (messages 365, audit_logs 1825, webhook_events_raw 30…).
4.  ``seed_default_retention_policies`` is wired into ``create_tenant``
    (and the self-service tenant flow).
5.  ``validate_policy`` rejects retention_days < 30, unknown entity, and
    anonymize=True on ``audit_logs``.
6.  ``run_retention_cycle`` uses paginated DELETEs with the configured
    ``retention_page_size``.
7.  ``run_retention_cycle`` anonymizes (not DELETE) when the policy says so,
    only for ``messages`` and ``conversations``.
8.  Anonymization replaces ``body_text``/``summary`` with a stable token —
    repeated runs are idempotent (no new rewrites).
9.  Each cycle emits an ``audit_logs`` row per entity with
    ``deleted_count`` / ``anonymized_count`` plus the anomaly flag.
10. ``run_retention_cycle`` emits a ``retention.cycle_completed`` domain
    event per tenant with the per-entity summary payload.
11. The HTTP endpoint ``GET /v1/tenants/{id}/retention/preview`` is wired
    in ``routes.py`` and forwards to ``preview_retention``.
12. The HTTP endpoints ``GET/PUT /v1/tenants/{id}/retention/policies``
    expose CRUD and call ``validate_policy`` before writing.
13. Admin Panel's Privacidad tab renders the retention table + save button
    and disables the anonymize checkbox for non-anonymizable entities.
14. ``retention_worker`` schedules the next run at the configured UTC hour.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.config import get_settings
from app.services.retention import (
    ANONYMIZABLE_ENTITIES,
    ANONYMIZED_TOKEN,
    DEFAULT_RETENTION_DAYS,
    RETENTION_ENTITIES,
    default_policy_rows,
    preview_retention,
    run_retention_cycle,
    run_retention_cycle_for_tenant,
    validate_policy,
)
from app.workers import retention_worker
from app.workers.retention_worker import _seconds_until_next_run


SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')

def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))

CORE_API = Path('admin-panel/src/services/coreApi.js')


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ─── Fake asyncpg connection ────────────────────────────────────────────────


class _FakeConn:
    """Minimal asyncpg.Connection stub for offline cycle tests.

    Stores tables as ``{table: [row_dict]}``. ``created_at`` rows are flagged
    "stale" by setting an integer age in days under ``_age_days``. The fake
    only implements the SQL shapes used by ``retention.py``.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            'messages': [],
            'conversations': [],
            'audit_logs': [],
            'domain_events': [],
            'webhook_events_raw': [],
            'reminder_jobs': [],
            'contacts': [],
            'tenants': [],
            'data_retention_policies': [],
        }
        self.audit_calls: list[dict[str, Any]] = []
        self.domain_events_emitted: list[dict[str, Any]] = []
        self.deletes: list[tuple[str, int]] = []
        self.set_config_calls: list[tuple[str, str]] = []

    async def execute(self, sql: str, *args: Any) -> str:
        sql_l = sql.lower()
        if 'set_config' in sql_l:
            self.set_config_calls.append((sql, str(args[0])))
            return 'SELECT 1'
        if 'insert into app.data_retention_policies' in sql_l:
            tenant_id, entity, days, anon = args
            existing = next(
                (r for r in self.tables['data_retention_policies']
                 if r['tenant_id'] == tenant_id and r['entity'] == entity),
                None,
            )
            if existing:
                if 'do update' in sql_l:
                    existing['retention_days'] = days
                    existing['anonymize_instead_of_delete'] = anon
                return 'INSERT 0 1'
            self.tables['data_retention_policies'].append({
                'tenant_id': tenant_id,
                'entity': entity,
                'retention_days': days,
                'anonymize_instead_of_delete': anon,
                'updated_at': None,
            })
            return 'INSERT 0 1'
        if sql_l.strip().startswith('insert into app.audit_logs'):
            self.audit_calls.append({
                'tenant_id': args[0],
                'entity': args[1],
                'metadata': json.loads(args[2]),
            })
            return 'INSERT 0 1'
        if 'insert into app.domain_events' in sql_l:
            self.domain_events_emitted.append({
                'tenant_id': args[0],
                'idempotency_key': args[1],
                'payload': json.loads(args[2]),
            })
            return 'INSERT 0 1'
        match = re.search(r'delete from app\.(\w+)\s+t', sql_l)
        if match:
            entity = match.group(1)
            tenant_id, retention_days, page = args
            rows = self.tables.get(entity, [])
            stale = [
                r for r in rows
                if r.get('tenant_id') == tenant_id and r.get('_age_days', 0) > retention_days
            ]
            n = min(len(stale), page)
            for r in stale[:n]:
                rows.remove(r)
            self.deletes.append((entity, n))
            return f'DELETE {n}'
        return 'SELECT 1'

    async def fetchval(self, sql: str, *args: Any) -> Any:
        sql_l = sql.lower()
        match = re.search(r'select count\(\*\) from app\.(\w+) where tenant_id = \$1\s*$', sql_l)
        if match:
            entity = match.group(1)
            tenant_id = args[0]
            return sum(1 for r in self.tables.get(entity, []) if r.get('tenant_id') == tenant_id)
        match = re.search(r'select count\(\*\) from app\.(\w+)\s+where tenant_id = \$1\s+and created_at', sql_l)
        if match:
            entity = match.group(1)
            tenant_id, days = args[0], args[1]
            return sum(
                1 for r in self.tables.get(entity, [])
                if r.get('tenant_id') == tenant_id and r.get('_age_days', 0) > days - 1
            )
        if 'select count(*) from (select 1) s where false' in sql_l:
            return 0
        return 0

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        sql_l = sql.lower()
        if 'from app.data_retention_policies' in sql_l:
            tenant_id = args[0]
            return [
                dict(r) for r in self.tables['data_retention_policies']
                if r['tenant_id'] == tenant_id
            ]
        if "from app.tenants" in sql_l and 'deleted_at is null' in sql_l:
            return [dict(r) for r in self.tables['tenants']]
        match = re.search(r'update app\.(messages|conversations|contacts) (\w)', sql_l)
        if match:
            entity = match.group(1)
            if entity == 'contacts':
                # Anonymization sweep — return zero rows in the fake (no extras).
                return []
            tenant_id, retention_days, token, page = args
            rows = [
                r for r in self.tables.get(entity, [])
                if r.get('tenant_id') == tenant_id
                and r.get('_age_days', 0) > retention_days
                and (r.get('body_text') or r.get('summary')) != token
            ]
            n = min(len(rows), page)
            updated_ids: list[dict[str, Any]] = []
            for r in rows[:n]:
                if entity == 'messages':
                    r['body_text'] = token
                else:
                    r['summary'] = token
                updated_ids.append({'id': r.get('id', uuid4())})
            return updated_ids
        return []

    def transaction(self):
        class _Ctx:
            async def __aenter__(self_):  # noqa: ARG002
                return None

            async def __aexit__(self_, exc_type, exc, tb):  # noqa: ARG002
                return False

        return _Ctx()


def _seed_tenant(conn: _FakeConn, tenant_id: UUID, *, active: bool = True) -> None:
    conn.tables['tenants'].append({
        'id': tenant_id, 'status': 'active' if active else 'churned', 'deleted_at': None,
    })
    for entity, days in DEFAULT_RETENTION_DAYS.items():
        conn.tables['data_retention_policies'].append({
            'tenant_id': tenant_id,
            'entity': entity,
            'retention_days': days,
            'anonymize_instead_of_delete': entity in ANONYMIZABLE_ENTITIES,
            'updated_at': None,
        })


# ─── 1. Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_data_retention_policies_table_with_checks():
    source = SCHEMA.read_text()
    assert 'create table app.data_retention_policies (' in source
    assert "check (retention_days >= 30)" in source
    assert "chk_audit_logs_no_anonymize" in source
    assert "entity <> 'audit_logs' or anonymize_instead_of_delete = false" in source
    for entity in RETENTION_ENTITIES:
        assert f"'{entity}'" in source


# ─── 2. RLS + policy loop ───────────────────────────────────────────────────


def test_schema_enables_rls_and_registers_in_policy_loop():
    source = SCHEMA.read_text()
    assert 'alter table app.data_retention_policies enable row level security' in source
    # The table name must appear inside the tenant-policy loop.
    assert "'data_retention_policies'" in source
    # Touch trigger keeps ``updated_at`` honest.
    assert 'trg_data_retention_policies_touch' in source


# ─── 3. Defaults ───────────────────────────────────────────────────────────


def test_default_policy_rows_match_documented_defaults():
    tenant_id = uuid4()
    rows = default_policy_rows(tenant_id)
    by_entity = {r['entity']: r for r in rows}
    assert set(by_entity) == set(RETENTION_ENTITIES)
    assert by_entity['messages']['retention_days'] == 365
    assert by_entity['conversations']['retention_days'] == 365
    assert by_entity['audit_logs']['retention_days'] == 1825
    assert by_entity['domain_events']['retention_days'] == 90
    assert by_entity['webhook_events_raw']['retention_days'] == 30
    assert by_entity['reminder_jobs']['retention_days'] == 30
    # Anonymization defaults: only PII-bearing entities start with it on.
    assert by_entity['messages']['anonymize_instead_of_delete'] is True
    assert by_entity['conversations']['anonymize_instead_of_delete'] is True
    assert by_entity['audit_logs']['anonymize_instead_of_delete'] is False
    assert by_entity['webhook_events_raw']['anonymize_instead_of_delete'] is False


# ─── 4. Seeding is wired ───────────────────────────────────────────────────


def test_create_tenant_calls_seed_default_retention_policies():
    source = ROUTES.read_text()
    assert 'from app.services.retention import' in source
    assert 'seed_default_retention_policies' in source
    # Both tenant creation flows (admin + self-service) seed it.
    assert source.count('seed_default_retention_policies(conn, tenant_id)') >= 2


# ─── 5. validate_policy ────────────────────────────────────────────────────


def test_validate_policy_rejects_invalid_inputs():
    # < 30 days
    with pytest.raises(ValueError, match='retention_days_below_minimum'):
        validate_policy('messages', 29, False)
    # Unknown entity
    with pytest.raises(ValueError, match='unknown_entity:bogus'):
        validate_policy('bogus', 90, False)
    # Anonymize on audit_logs is forbidden
    with pytest.raises(ValueError, match='audit_logs_cannot_be_anonymized'):
        validate_policy('audit_logs', 1825, True)
    # Anonymize on a non-anonymizable entity (e.g. webhook_events_raw)
    with pytest.raises(ValueError, match='entity_not_anonymizable'):
        validate_policy('webhook_events_raw', 90, True)
    # Happy path
    validate_policy('messages', 365, True)
    validate_policy('audit_logs', 1825, False)


# ─── 6. Paginated DELETE ───────────────────────────────────────────────────


def test_run_retention_cycle_paginates_deletes():
    """Old rows are removed; the cycle does not run a single mega-DELETE."""
    tenant_id = uuid4()
    conn = _FakeConn()
    _seed_tenant(conn, tenant_id)
    # Seed 7 stale rows in webhook_events_raw (default 30d retention).
    for _ in range(7):
        conn.tables['webhook_events_raw'].append({
            'tenant_id': tenant_id, 'id': uuid4(), '_age_days': 90,
        })
    # Plus 2 fresh ones that must NOT be deleted.
    for _ in range(2):
        conn.tables['webhook_events_raw'].append({
            'tenant_id': tenant_id, 'id': uuid4(), '_age_days': 5,
        })

    summary = asyncio.run(
        run_retention_cycle_for_tenant(conn, tenant_id=tenant_id, page_size=3)
    )

    # All 7 stale rows are gone; the 2 fresh rows survive.
    remaining = [r for r in conn.tables['webhook_events_raw'] if r['tenant_id'] == tenant_id]
    assert len(remaining) == 2
    assert all(r['_age_days'] == 5 for r in remaining)
    # At least 3 DELETE batches: 3 + 3 + 1.
    webhook_deletes = [d for d in conn.deletes if d[0] == 'webhook_events_raw']
    assert len(webhook_deletes) >= 3
    assert summary['webhook_events_raw']['deleted'] == 7


# ─── 7. Anonymization path ────────────────────────────────────────────────


def test_run_retention_cycle_anonymizes_messages_when_flag_set():
    tenant_id = uuid4()
    conn = _FakeConn()
    _seed_tenant(conn, tenant_id)
    # Stale messages with real body_text.
    for _ in range(4):
        conn.tables['messages'].append({
            'tenant_id': tenant_id, 'id': uuid4(), 'body_text': 'hola mundo', '_age_days': 400,
        })
    # Plus one recent message that must keep its body.
    conn.tables['messages'].append({
        'tenant_id': tenant_id, 'id': uuid4(), 'body_text': 'still relevant', '_age_days': 5,
    })

    summary = asyncio.run(run_retention_cycle_for_tenant(conn, tenant_id=tenant_id, page_size=2))

    stale = [m for m in conn.tables['messages'] if m['_age_days'] == 400]
    fresh = [m for m in conn.tables['messages'] if m['_age_days'] == 5]
    assert all(m['body_text'] == ANONYMIZED_TOKEN for m in stale)
    assert fresh and fresh[0]['body_text'] == 'still relevant'
    assert summary['messages']['anonymized'] == 4
    assert summary['messages']['deleted'] == 0


# ─── 8. Anonymization is idempotent ───────────────────────────────────────


def test_anonymization_is_idempotent_across_runs():
    tenant_id = uuid4()
    conn = _FakeConn()
    _seed_tenant(conn, tenant_id)
    for _ in range(3):
        conn.tables['messages'].append({
            'tenant_id': tenant_id, 'id': uuid4(), 'body_text': 'secret', '_age_days': 400,
        })
    first = asyncio.run(run_retention_cycle_for_tenant(conn, tenant_id=tenant_id))
    second = asyncio.run(run_retention_cycle_for_tenant(conn, tenant_id=tenant_id))
    assert first['messages']['anonymized'] == 3
    # Second run finds nothing left to rewrite — already redacted.
    assert second['messages']['anonymized'] == 0


# ─── 9. Audit row per entity ──────────────────────────────────────────────


def test_run_retention_cycle_writes_audit_row_per_entity():
    tenant_id = uuid4()
    conn = _FakeConn()
    _seed_tenant(conn, tenant_id)
    # One stale webhook row to trigger a non-zero deletion.
    conn.tables['webhook_events_raw'].append({
        'tenant_id': tenant_id, 'id': uuid4(), '_age_days': 99,
    })

    asyncio.run(run_retention_cycle_for_tenant(conn, tenant_id=tenant_id))

    audits_by_entity = {a['entity']: a for a in conn.audit_calls}
    assert set(audits_by_entity) == set(RETENTION_ENTITIES)
    webhook_audit = audits_by_entity['webhook_events_raw']
    assert webhook_audit['metadata']['deleted_count'] == 1
    assert webhook_audit['metadata']['anonymized_count'] == 0
    assert 'removed_pct' in webhook_audit['metadata']
    assert 'anomaly' in webhook_audit['metadata']


# ─── 10. Domain event per tenant ─────────────────────────────────────────


def test_run_retention_cycle_emits_completed_event_per_tenant():
    tenant_id = uuid4()
    conn = _FakeConn()
    _seed_tenant(conn, tenant_id)

    asyncio.run(run_retention_cycle(conn))

    events = [e for e in conn.domain_events_emitted if e['tenant_id'] == tenant_id]
    assert len(events) == 1
    payload = events[0]['payload']
    assert 'entities' in payload
    assert set(payload['entities']) == set(RETENTION_ENTITIES)
    # Idempotency key is per-day so a re-run the same day is a no-op.
    assert 'retention:' in events[0]['idempotency_key']


# ─── 11. Preview endpoint wiring ─────────────────────────────────────────


def test_preview_endpoint_is_wired_in_routes():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/retention/preview')" in source
    assert 'preview_retention(' in source
    # Returns a payload keyed by ``preview`` so the UI can iterate.
    assert "'preview': await preview_retention(" in source


def test_preview_helper_counts_candidates_against_one_extra_day():
    """``preview_retention`` looks one day into the future so the operator sees
    what the *next* cycle will purge, not just what is overdue right now.
    """
    source = inspect.getsource(preview_retention)
    assert "interval '1 day'" in source
    assert 'now() + interval' in source


def test_retention_age_column_mapping_covers_every_entity():
    """BUG-003: `domain_events` uses `occurred_at` and `webhook_events_raw`
    uses `received_at`, NOT `created_at`. Without the ENTITY_AGE_COLUMN
    mapping, `preview_retention` and `_delete_paginated` blew up with
    UndefinedColumnError on column 'created_at' for those entities.
    """
    from app.services.retention import (  # noqa: PLC0415
        ENTITY_AGE_COLUMN,
        RETENTION_ENTITIES,
    )

    # Every retention-eligible entity must appear in the map; missing entries
    # would silently fall back to 'created_at' (the bug we're guarding against).
    for entity in RETENTION_ENTITIES:
        assert entity in ENTITY_AGE_COLUMN, (
            f'Entity {entity!r} missing from ENTITY_AGE_COLUMN — would default to '
            'created_at which may not exist on that table.'
        )

    # Spot-check the two entities that DON'T have created_at in the schema.
    assert ENTITY_AGE_COLUMN['domain_events'] == 'occurred_at'
    assert ENTITY_AGE_COLUMN['webhook_events_raw'] == 'received_at'


def test_preview_retention_uses_age_column_mapping():
    """The actual SQL in `preview_retention` must read the age column from
    `ENTITY_AGE_COLUMN.get(entity, 'created_at')`, not hard-code created_at."""
    source = inspect.getsource(preview_retention)
    assert 'ENTITY_AGE_COLUMN.get(entity' in source
    assert '{age_col}' in source


# ─── 12. CRUD endpoints + validation ──────────────────────────────────────


def test_policies_crud_endpoints_validate_before_writing():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/retention/policies')" in source
    assert "@tenant_admin_router.put('/tenants/{tenant_id}/retention/policies')" in source
    # Validation is called before the INSERT/UPSERT loop.
    assert 'validate_policy(entry.entity, entry.retention_days, entry.anonymize_instead_of_delete)' in source
    assert "raise HTTPException(status_code=400" in source
    # The shared core API exposes the same surface to the Admin Panel.
    api_source = CORE_API.read_text()
    assert 'listRetentionPolicies' in api_source
    assert 'updateRetentionPolicies' in api_source
    assert 'getRetentionPreview' in api_source


# ─── 13. Admin Panel ────────────────────────────────────────────────────────


def test_wizard_renders_retention_block_and_disables_anonymize_for_non_pii():
    source = _tenant_setup_source()
    assert 'data-testid="retention-policies-table"' in source
    assert 'data-testid="retention-save"' in source
    assert 'Guardar política de retención' in source
    assert 'RETENTION_ANONYMIZABLE' in source
    # The anonymize checkbox is disabled when the entity is not in the
    # ``messages`` / ``conversations`` allowlist.
    assert "disabled={!RETENTION_ANONYMIZABLE.has(row.entity)}" in source
    # Preview column wires the per-entity candidate count.
    assert 'retention-candidates-${row.entity}' in source


# ─── 14. Worker schedule ────────────────────────────────────────────────────


def test_retention_worker_schedules_next_run_at_configured_hour(monkeypatch):
    from datetime import datetime, timezone

    # At 02:00 UTC and target 03:00 → sleep ≈ 1 hour.
    now = datetime(2026, 5, 13, 2, 0, 0, tzinfo=timezone.utc)
    seconds = _seconds_until_next_run(3, now=now)
    assert 3590 <= seconds <= 3610

    # At 03:30 UTC and target 03:00 → sleep until the next day (≈ 23.5 h).
    now2 = datetime(2026, 5, 13, 3, 30, 0, tzinfo=timezone.utc)
    seconds2 = _seconds_until_next_run(3, now=now2)
    assert 84500 <= seconds2 <= 84700

    # The worker's main loop dispatches the cycle through ``run_retention_cycle``.
    assert 'from app.services.retention import run_retention_cycle' in Path(
        retention_worker.__file__
    ).read_text()
