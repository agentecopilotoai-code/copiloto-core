"""TASK-0061: per-tenant retention policies and the purge cycle.

Each (tenant, entity) row in ``app.data_retention_policies`` defines how long
to keep historical rows of that entity. The ``retention_worker`` calls
``run_retention_cycle`` once per day; for each policy it either DELETEs rows
older than ``retention_days`` or anonymizes them in place (only valid for
``messages`` and ``conversations``).

``audit_logs`` are never anonymized — that would break compliance — so the
``anonymize_instead_of_delete`` flag is rejected for that entity both at the
DB level (CHECK constraint) and here.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.core.config import get_settings

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


RETENTION_ENTITIES: tuple[str, ...] = (
    'messages',
    'conversations',
    'audit_logs',
    'domain_events',
    'webhook_events_raw',
    'reminder_jobs',
)

# Entities that may carry PII — eligible for anonymization instead of DELETE.
ANONYMIZABLE_ENTITIES: frozenset[str] = frozenset({'messages', 'conversations'})

# BUG-003 fix: each retention entity exposes its own "age" column. Most use
# `created_at` (default in `touch_updated_at` triggers), but two predate it:
#   - `domain_events.occurred_at` is the canonical event timestamp.
#   - `webhook_events_raw.received_at` is when we first persisted the payload.
# Hard-code the mapping so `preview_retention` + `run_retention_cycle` query
# the correct column. Before this fix, those two entities raised
# UndefinedColumnError on column "created_at" and `/v1/tenants/{id}/retention/preview`
# returned 500 for every Owner that landed on Tenant Setup.
ENTITY_AGE_COLUMN: dict[str, str] = {
    'messages': 'created_at',
    'conversations': 'created_at',
    'audit_logs': 'created_at',
    'domain_events': 'occurred_at',
    'webhook_events_raw': 'received_at',
    'reminder_jobs': 'created_at',
}

# Default retention windows seeded for every new tenant. Audit logs default to
# 5 years (1825 days) for legal compliance; everything else is shorter.
DEFAULT_RETENTION_DAYS: dict[str, int] = {
    'messages': 365,
    'conversations': 365,
    'audit_logs': 1825,
    'domain_events': 90,
    'webhook_events_raw': 30,
    'reminder_jobs': 30,
}

# Anonymization tokens for fields that must keep their NOT NULL contract.
ANONYMIZED_TOKEN = '[redacted]'
ANONYMIZED_PHONE_PREFIX = '+anon:'


def hash_token(*, tenant_id: UUID, table: str, row_id: Any) -> str:
    """Stable per-tenant hash used to replace PII while keeping uniqueness."""
    digest = hashlib.sha256(
        f'{tenant_id}:{table}:{row_id}'.encode('utf-8')
    ).hexdigest()
    return digest[:16]


def default_policy_rows(tenant_id: UUID) -> list[dict[str, Any]]:
    """Return the seed rows for ``data_retention_policies`` for a new tenant."""
    return [
        {
            'tenant_id': tenant_id,
            'entity': entity,
            'retention_days': days,
            'anonymize_instead_of_delete': entity in ANONYMIZABLE_ENTITIES,
        }
        for entity, days in DEFAULT_RETENTION_DAYS.items()
    ]


async def seed_default_retention_policies(
    conn: 'asyncpg.Connection', tenant_id: UUID
) -> None:
    """Idempotent insert of default policies; called from ``create_tenant``."""
    for row in default_policy_rows(tenant_id):
        await conn.execute(
            """
            insert into app.data_retention_policies
              (tenant_id, entity, retention_days, anonymize_instead_of_delete)
            values ($1, $2, $3, $4)
            on conflict (tenant_id, entity) do nothing
            """,
            row['tenant_id'],
            row['entity'],
            row['retention_days'],
            row['anonymize_instead_of_delete'],
        )


def validate_policy(entity: str, retention_days: int, anonymize: bool) -> None:
    """Mirror the DB CHECK constraints in Python so the API returns 4xx
    instead of leaking a DB error to the caller.
    """
    if entity not in RETENTION_ENTITIES:
        raise ValueError(f'unknown_entity:{entity}')
    if retention_days < 30:
        raise ValueError('retention_days_below_minimum')
    if anonymize and entity == 'audit_logs':
        raise ValueError('audit_logs_cannot_be_anonymized')
    if anonymize and entity not in ANONYMIZABLE_ENTITIES:
        raise ValueError(f'entity_not_anonymizable:{entity}')


async def preview_retention(
    conn: 'asyncpg.Connection', tenant_id: UUID
) -> list[dict[str, Any]]:
    """Return how many rows would be purged tomorrow per entity.

    "Tomorrow" means "after the next 24h tick of the worker", so we count rows
    whose ``created_at`` is older than ``now() + interval '1 day' -
    retention_days * interval '1 day'``. That keeps the preview honest for
    operators planning a policy change.
    """
    policies = await conn.fetch(
        """
        select entity, retention_days, anonymize_instead_of_delete
        from app.data_retention_policies
        where tenant_id = $1
        order by entity
        """,
        tenant_id,
    )
    out: list[dict[str, Any]] = []
    for row in policies:
        entity = row['entity']
        age_col = ENTITY_AGE_COLUMN.get(entity, 'created_at')
        candidate = await conn.fetchval(
            f"""
            select count(*) from app.{entity}
            where tenant_id = $1
              and {age_col} < (now() + interval '1 day')
                              - ($2::int * interval '1 day')
            """,
            tenant_id,
            int(row['retention_days']),
        )
        total = await conn.fetchval(
            f'select count(*) from app.{entity} where tenant_id = $1',
            tenant_id,
        )
        out.append({
            'entity': entity,
            'retention_days': int(row['retention_days']),
            'anonymize_instead_of_delete': bool(row['anonymize_instead_of_delete']),
            'candidates': int(candidate or 0),
            'total': int(total or 0),
        })
    return out


async def _delete_paginated(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    entity: str,
    retention_days: int,
    page_size: int,
) -> int:
    """DELETE rows older than the retention window, paginated.

    The query uses ``ctid`` to limit the batch — works for every table since
    ``ctid`` is a Postgres system column. Returns the total rows deleted.
    """
    total = 0
    age_col = ENTITY_AGE_COLUMN.get(entity, 'created_at')
    while True:
        result = await conn.execute(
            f"""
            with batch as (
              select ctid from app.{entity}
              where tenant_id = $1
                and {age_col} < now() - ($2::int * interval '1 day')
              limit $3
            )
            delete from app.{entity} t
            using batch
            where t.ctid = batch.ctid
            """,
            tenant_id,
            retention_days,
            page_size,
        )
        # asyncpg returns e.g. "DELETE 5000"
        try:
            n = int(result.split()[-1])
        except (ValueError, IndexError):
            n = 0
        total += n
        if n < page_size:
            break
    return total


async def _anonymize_messages(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    retention_days: int,
    page_size: int,
) -> int:
    total = 0
    while True:
        rows = await conn.fetch(
            """
            with batch as (
              select id from app.messages
              where tenant_id = $1
                and created_at < now() - ($2::int * interval '1 day')
                and body_text is distinct from $3
                and body_text is not null
              limit $4
            )
            update app.messages m
            set body_text = $3,
                payload = '{}'::jsonb
            from batch
            where m.id = batch.id and m.tenant_id = $1
            returning m.id
            """,
            tenant_id,
            retention_days,
            ANONYMIZED_TOKEN,
            page_size,
        )
        n = len(rows)
        total += n
        if n < page_size:
            break
    return total


async def _anonymize_conversations(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    retention_days: int,
    page_size: int,
) -> int:
    total = 0
    while True:
        rows = await conn.fetch(
            """
            with batch as (
              select id from app.conversations
              where tenant_id = $1
                and created_at < now() - ($2::int * interval '1 day')
                and summary is distinct from $3
              limit $4
            )
            update app.conversations c
            set summary = $3,
                metadata = '{}'::jsonb
            from batch
            where c.id = batch.id and c.tenant_id = $1
            returning c.id
            """,
            tenant_id,
            retention_days,
            ANONYMIZED_TOKEN,
            page_size,
        )
        n = len(rows)
        total += n
        if n < page_size:
            break
    # After messages/conversations are anonymized, the contact's phone is
    # still in ``app.contacts``. We only touch contacts whose latest activity
    # falls outside the retention window — that keeps the active book intact.
    # BUG-156: antes este bloque corría UNA sola vez con `limit 100`, así
    # que tenants con más de 100 contactos viejos quedaban semi-anonimizados.
    # Igualamos el patrón de los messages: loop hasta que la batch devuelva
    # menos filas que el page_size (señal de que ya no hay más).
    while True:
        rows = await conn.fetch(
            """
            with batch as (
              select c.id from app.contacts c
              where c.tenant_id = $1
                and c.updated_at < now() - ($2::int * interval '1 day')
                and c.phone_e164 not like $3 || '%'
              limit $4
            )
            update app.contacts ct
            set phone_e164 = $3 || encode(digest(ct.id::text || $5::text, 'sha256'), 'hex'),
                display_name = $6
            from batch
            where ct.id = batch.id and ct.tenant_id = $1
            returning ct.id
            """,
            tenant_id,
            retention_days,
            ANONYMIZED_PHONE_PREFIX,
            page_size,
            str(tenant_id),
            ANONYMIZED_TOKEN,
        )
        n = len(rows)
        total += n
        if n < page_size:
            break
    return total


async def run_retention_cycle_for_tenant(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    page_size: int | None = None,
) -> dict[str, dict[str, int]]:
    """Apply every policy for ``tenant_id`` and return per-entity counts."""
    settings = get_settings()
    page = page_size or settings.retention_page_size
    policies = await conn.fetch(
        """
        select entity, retention_days, anonymize_instead_of_delete
        from app.data_retention_policies
        where tenant_id = $1
        order by entity
        """,
        tenant_id,
    )
    summary: dict[str, dict[str, int]] = {}
    for row in policies:
        entity = row['entity']
        retention_days = int(row['retention_days'])
        anonymize = bool(row['anonymize_instead_of_delete'])
        total_before = int(await conn.fetchval(
            f'select count(*) from app.{entity} where tenant_id = $1',
            tenant_id,
        ) or 0)
        deleted = anonymized = 0
        if anonymize and entity == 'messages':
            anonymized = await _anonymize_messages(
                conn,
                tenant_id=tenant_id,
                retention_days=retention_days,
                page_size=page,
            )
        elif anonymize and entity == 'conversations':
            anonymized = await _anonymize_conversations(
                conn,
                tenant_id=tenant_id,
                retention_days=retention_days,
                page_size=page,
            )
        else:
            deleted = await _delete_paginated(
                conn,
                tenant_id=tenant_id,
                entity=entity,
                retention_days=retention_days,
                page_size=page,
            )
        summary[entity] = {
            'deleted': deleted,
            'anonymized': anonymized,
            'total_before': total_before,
        }
        await conn.execute(
            """
            insert into app.audit_logs
              (tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)
            values ($1, 'system', 'retention_worker', 'retention.purged', $2, $1::text, $3::jsonb)
            """,
            tenant_id,
            entity,
            _audit_metadata(entity, deleted, anonymized, total_before, retention_days),
        )
    return summary


def _audit_metadata(
    entity: str, deleted: int, anonymized: int, total_before: int, days: int
) -> str:
    import json

    threshold_pct = get_settings().retention_anomaly_threshold_pct
    removed = deleted + anonymized
    pct = (removed / total_before * 100.0) if total_before > 0 else 0.0
    return json.dumps({
        'entity': entity,
        'deleted_count': deleted,
        'anonymized_count': anonymized,
        'total_before': total_before,
        'retention_days': days,
        'removed_pct': round(pct, 2),
        'anomaly': pct > threshold_pct,
    })


async def run_retention_cycle(conn: 'asyncpg.Connection') -> dict[UUID, dict[str, dict[str, int]]]:
    """Run the cycle for every active tenant. Returns ``{tenant_id: summary}``."""
    tenant_rows = await conn.fetch(
        "select id from app.tenants where deleted_at is null and status='active'"
    )
    out: dict[UUID, dict[str, dict[str, int]]] = {}
    for row in tenant_rows:
        tenant_id = row['id']
        await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
        try:
            summary = await run_retention_cycle_for_tenant(conn, tenant_id=tenant_id)
        except Exception:
            log.exception('retention.cycle_failed', tenant_id=str(tenant_id))
            continue
        out[tenant_id] = summary
        await conn.execute(
            """
            insert into app.domain_events
              (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload)
            values ($1, 'tenant', $1, 'retention.cycle_completed', $2, $3::jsonb)
            on conflict (tenant_id, idempotency_key) do nothing
            """,
            tenant_id,
            f'retention:{tenant_id}:{datetime.now(UTC).date().isoformat()}',
            _cycle_event_payload(summary),
        )
        log.info('retention.cycle_completed', tenant_id=str(tenant_id), summary=summary)
    return out


def _cycle_event_payload(summary: dict[str, dict[str, int]]) -> str:
    import json

    return json.dumps({
        'entities': {
            entity: {
                'deleted': data['deleted'],
                'anonymized': data['anonymized'],
                'total_before': data['total_before'],
            }
            for entity, data in summary.items()
        },
        'completed_at': datetime.now(UTC).isoformat(),
    })
