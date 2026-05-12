"""Reusable customer segments for retention and reactivation.

A segment is a saved query over ``app.contacts`` (plus derived metrics from
``app.appointments``) that the tenant can name and reuse — e.g. "Sin visita en
60+ días", "VIP > $500k". Two kinds:

* ``dynamic``: defined by ``rules`` JSON, evaluated on every refresh.  The
  scheduler periodically recomputes ``contact_count`` and snapshots the
  member list into ``app.contact_segment_members``.
* ``static``: snapshot maintained manually by the operator (e.g. attendees
  of an in-person event).  ``rules`` is empty; membership is written
  directly into ``app.contact_segment_members``.

The SQL builder accepts a whitelist of fields and operators only.  Anything
else is silently dropped — the goal is to keep the surface predictable and
inject-proof while remaining flexible enough for campaign segmentation.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


SEGMENT_KINDS = ('dynamic', 'static')


# Whitelisted fields. Each entry maps to a SQL expression that yields one
# value per ``app.contacts`` row.  Sub-queries reference the ``c.id`` /
# ``c.tenant_id`` alias used by the outer ``select``.
FIELD_EXPRESSIONS: dict[str, str] = {
    'last_appointment_at': (
        "(select max(a.starts_at) from app.appointments a "
        "where a.tenant_id=c.tenant_id and a.contact_id=c.id "
        "  and a.status in ('completed','confirmed','scheduled'))"
    ),
    'total_appointments_completed': (
        "(select count(*)::int from app.appointments a "
        "where a.tenant_id=c.tenant_id and a.contact_id=c.id "
        "  and a.status='completed')"
    ),
    'total_appointments_no_show': (
        "(select count(*)::int from app.appointments a "
        "where a.tenant_id=c.tenant_id and a.contact_id=c.id "
        "  and a.status='no_show')"
    ),
    'total_spent': (
        "coalesce((select sum(coalesce(a.payment_amount, s.price_amount, 0)) "
        " from app.appointments a "
        " left join app.service_catalog s on s.tenant_id=a.tenant_id and s.id=a.service_id "
        " where a.tenant_id=c.tenant_id and a.contact_id=c.id "
        "   and a.status='completed'), 0)"
    ),
    'tags': "c.tags",
    'lead_source.channel': "c.lead_source->>'channel'",
    'created_at': "c.created_at",
}


# Operators allowed per (field, op). Operators map to a SQL fragment using
# ``$N`` placeholders that the builder allocates.
NUMERIC_OPS = {'eq', 'in', 'lt', 'lte', 'gt', 'gte', 'between'}
DATE_OPS = {'lt_days_ago', 'gte_days_ago', 'is_null', 'is_not_null'}
ARRAY_OPS = {'contains_any', 'contains_all', 'is_empty', 'is_not_empty'}
TEXT_OPS = {'eq', 'in', 'is_null', 'is_not_null'}

FIELD_OPERATORS: dict[str, set[str]] = {
    'last_appointment_at': DATE_OPS,
    'total_appointments_completed': NUMERIC_OPS,
    'total_appointments_no_show': NUMERIC_OPS | {'in_window_days'},
    'total_spent': NUMERIC_OPS,
    'tags': ARRAY_OPS,
    'lead_source.channel': TEXT_OPS,
    'created_at': DATE_OPS,
}


class _ParamBuilder:
    def __init__(self) -> None:
        self.args: list[Any] = []

    def add(self, value: Any) -> str:
        self.args.append(value)
        return f'${len(self.args)}'


def _qualification_expression(key: str) -> str:
    # Allow alphanumerics + underscore only.  Anything else is ignored by the
    # caller; this helper assumes the key already passed validation.
    return f"c.qualification->>'{key}'"


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            return None
    return None


def _valid_qualification_key(key: str) -> bool:
    return bool(key) and all(c.isalnum() or c == '_' for c in key) and len(key) <= 60


def _emit_condition(condition: dict[str, Any], pb: _ParamBuilder) -> str | None:
    if not isinstance(condition, dict):
        return None
    field = condition.get('field')
    op = condition.get('op')
    value = condition.get('value')
    if not isinstance(field, str) or not isinstance(op, str):
        return None

    # Qualification keys are a separate namespace because they live in JSONB.
    if field.startswith('qualification.'):
        key = field.split('.', 1)[1]
        if not _valid_qualification_key(key):
            return None
        if op in ('eq', 'in'):
            expr = _qualification_expression(key)
            if op == 'eq':
                ph = pb.add(str(value))
                return f"{expr} = {ph}"
            if op == 'in' and isinstance(value, list) and value:
                ph = pb.add([str(v) for v in value])
                return f"{expr} = any({ph}::text[])"
        if op == 'is_null':
            return f"{_qualification_expression(key)} is null"
        if op == 'is_not_null':
            return f"{_qualification_expression(key)} is not null"
        return None

    if field not in FIELD_EXPRESSIONS:
        return None
    if op not in FIELD_OPERATORS.get(field, set()):
        return None
    expr = FIELD_EXPRESSIONS[field]

    if op == 'eq':
        ph = pb.add(value)
        return f"{expr} = {ph}"
    if op == 'in':
        if not isinstance(value, list) or not value:
            return None
        if field == 'lead_source.channel':
            ph = pb.add([str(v) for v in value])
            return f"{expr} = any({ph}::text[])"
        # numeric in()
        nums = [_coerce_number(v) for v in value]
        nums = [n for n in nums if n is not None]
        if not nums:
            return None
        ph = pb.add(nums)
        return f"{expr} = any({ph}::numeric[])"
    if op in ('lt', 'lte', 'gt', 'gte'):
        num = _coerce_number(value)
        if num is None:
            return None
        ph = pb.add(num)
        sql_op = {'lt': '<', 'lte': '<=', 'gt': '>', 'gte': '>='}[op]
        return f"{expr} {sql_op} {ph}"
    if op == 'between':
        if not isinstance(value, list) or len(value) != 2:
            return None
        lo = _coerce_number(value[0])
        hi = _coerce_number(value[1])
        if lo is None or hi is None:
            return None
        lo_ph = pb.add(lo)
        hi_ph = pb.add(hi)
        return f"{expr} between {lo_ph} and {hi_ph}"
    if op == 'lt_days_ago':
        days = _coerce_number(value)
        if days is None or days < 0:
            return None
        ph = pb.add(int(days))
        return f"{expr} < now() - ({ph} * interval '1 day')"
    if op == 'gte_days_ago':
        days = _coerce_number(value)
        if days is None or days < 0:
            return None
        ph = pb.add(int(days))
        return f"{expr} >= now() - ({ph} * interval '1 day')"
    if op == 'is_null':
        return f"{expr} is null"
    if op == 'is_not_null':
        return f"{expr} is not null"
    if op == 'contains_any':
        if not isinstance(value, list) or not value:
            return None
        ph = pb.add([str(v) for v in value])
        return f"{expr} && {ph}::text[]"
    if op == 'contains_all':
        if not isinstance(value, list) or not value:
            return None
        ph = pb.add([str(v) for v in value])
        return f"{expr} @> {ph}::text[]"
    if op == 'is_empty':
        return f"coalesce(array_length({expr}, 1), 0) = 0"
    if op == 'is_not_empty':
        return f"coalesce(array_length({expr}, 1), 0) > 0"
    if op == 'in_window_days':
        days = _coerce_number(value)
        if days is None or days < 0:
            return None
        ph = pb.add(int(days))
        # Override: total appointments no-show within window
        return (
            "(select count(*) from app.appointments a "
            "where a.tenant_id=c.tenant_id and a.contact_id=c.id "
            f"  and a.status='no_show' and a.starts_at >= now() - ({ph} * interval '1 day')) > 0"
        )
    return None


def _emit_group(group: list[Any], pb: _ParamBuilder, joiner: str) -> str | None:
    fragments: list[str] = []
    for item in group:
        frag = _emit_node(item, pb)
        if frag:
            fragments.append(f"({frag})")
    if not fragments:
        return None
    return f' {joiner} '.join(fragments)


def _emit_node(node: Any, pb: _ParamBuilder) -> str | None:
    if not isinstance(node, dict):
        return None
    if isinstance(node.get('all_of'), list):
        return _emit_group(node['all_of'], pb, 'and')
    if isinstance(node.get('any_of'), list):
        return _emit_group(node['any_of'], pb, 'or')
    return _emit_condition(node, pb)


def normalize_rules(rules: Any) -> dict[str, Any]:
    """Return rules JSON sanitized to a small whitelist.

    A normalized rules object is always wrapped in either ``all_of`` or
    ``any_of`` at the top level so callers don't need to special-case a
    single condition.
    """
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(rules, dict):
        return {}

    def _normalize_condition(cond: Any) -> dict[str, Any] | None:
        if not isinstance(cond, dict):
            return None
        # Allow nested groups inside groups (one level deep is enough).
        if isinstance(cond.get('all_of'), list):
            children = [c for c in (_normalize_condition(x) for x in cond['all_of']) if c]
            return {'all_of': children} if children else None
        if isinstance(cond.get('any_of'), list):
            children = [c for c in (_normalize_condition(x) for x in cond['any_of']) if c]
            return {'any_of': children} if children else None
        field = cond.get('field')
        op = cond.get('op')
        if not isinstance(field, str) or not isinstance(op, str):
            return None
        if field.startswith('qualification.'):
            key = field.split('.', 1)[1]
            if not _valid_qualification_key(key):
                return None
        elif field not in FIELD_EXPRESSIONS:
            return None
        elif op not in FIELD_OPERATORS.get(field, set()):
            return None
        result: dict[str, Any] = {'field': field, 'op': op}
        if 'value' in cond:
            result['value'] = cond['value']
        return result

    if isinstance(rules.get('all_of'), list):
        children = [c for c in (_normalize_condition(x) for x in rules['all_of']) if c]
        return {'all_of': children}
    if isinstance(rules.get('any_of'), list):
        children = [c for c in (_normalize_condition(x) for x in rules['any_of']) if c]
        return {'any_of': children}
    # Bare condition → wrap in all_of for uniformity.
    cond = _normalize_condition(rules)
    return {'all_of': [cond]} if cond else {}


def build_segment_query(rules: Any) -> tuple[str, list[Any]]:
    """Return ``(sql, args)`` selecting ``contact_id`` for a segment.

    ``args[0]`` is reserved for the tenant id (filled by the caller).  The
    query restricts to reachable contacts (``opt_in_status`` not in
    ``revoked``/``suppressed`` and ``phone_e164`` not null) so segments are
    always usable as campaign recipients.
    """
    normalized = normalize_rules(rules)
    pb = _ParamBuilder()
    tenant_ph = pb.add(None)  # tenant_id placeholder
    where = [
        f'c.tenant_id = {tenant_ph}',
        "c.opt_in_status not in ('revoked','suppressed')",
        'c.phone_e164 is not null',
    ]
    condition_sql = _emit_node(normalized, pb)
    if condition_sql:
        where.append(condition_sql)
    sql = (
        'select c.id as contact_id, c.display_name, c.phone_e164, c.opt_in_status '
        'from app.contacts c where ' + ' and '.join(where) + ' order by c.created_at'
    )
    return sql, pb.args


def _bind_tenant(args: list[Any], tenant_id: UUID) -> list[Any]:
    bound = list(args)
    if bound:
        bound[0] = tenant_id
    return bound


async def evaluate_segment_rules(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    rules: Any,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql, args = build_segment_query(rules)
    if limit is not None:
        sql = f'{sql} limit {int(limit)}'
    rows = await conn.fetch(sql, *_bind_tenant(args, tenant_id))
    return [dict(row) for row in rows]


async def count_segment_contacts(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    rules: Any,
) -> int:
    sql, args = build_segment_query(rules)
    wrapped = f'select count(*) from ({sql}) sub'
    return int(await conn.fetchval(wrapped, *_bind_tenant(args, tenant_id)) or 0)


async def snapshot_segment_members(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    segment_id: UUID,
    rules: Any,
) -> tuple[int, str]:
    """Materialise the current evaluation of ``rules`` into the members table.

    Returns ``(count, snapshot_at_iso)``.  Members are written with a single
    ``snapshot_at`` timestamp so callers (campaign launches, hourly refresh)
    can reference an exact point-in-time set without ambiguity.
    """
    rows = await evaluate_segment_rules(conn, tenant_id, rules)
    snapshot_at = await conn.fetchval('select now()')
    if rows:
        # Insert with ON CONFLICT DO NOTHING so the unique key (segment_id,
        # contact_id, snapshot_at) protects against accidental duplicates if
        # the same refresh runs twice in the same instant.
        await conn.executemany(
            """
            insert into app.contact_segment_members (tenant_id, segment_id, contact_id, snapshot_at)
            values ($1, $2, $3, $4)
            on conflict (segment_id, contact_id, snapshot_at) do nothing
            """,
            [(tenant_id, segment_id, row['contact_id'], snapshot_at) for row in rows],
        )
    await conn.execute(
        """
        update app.contact_segments
        set contact_count=$3, last_refreshed_at=$4, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        segment_id,
        len(rows),
        snapshot_at,
    )
    return len(rows), snapshot_at


async def refresh_due_segments(
    conn: 'asyncpg.Connection',
    *,
    interval: timedelta = timedelta(hours=1),
    limit: int = 25,
) -> int:
    """Recompute dynamic segments whose snapshot is older than ``interval``.

    Returns the number of segments refreshed in this iteration.
    """
    cutoff = await conn.fetchval(
        "select now() - $1::interval", interval
    )
    rows = await conn.fetch(
        """
        select id, tenant_id, rules
        from app.contact_segments
        where kind='dynamic'
          and (last_refreshed_at is null or last_refreshed_at < $1)
        order by coalesce(last_refreshed_at, '-infinity'::timestamptz)
        limit $2
        """,
        cutoff,
        limit,
    )
    refreshed = 0
    for row in rows:
        await conn.execute(
            "select set_config('app.tenant_id', $1, true)", str(row['tenant_id'])
        )
        try:
            await snapshot_segment_members(
                conn, row['tenant_id'], row['id'], row['rules']
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.exception(
                'segment.refresh_failed',
                tenant_id=str(row['tenant_id']),
                segment_id=str(row['id']),
                error=str(exc),
            )
            continue
        refreshed += 1
    return refreshed


PRECONSTRUCTED_SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        'name': 'Sin visita en 60+ días',
        'description': 'Contactos cuya última cita fue hace más de 60 días.',
        'rules': {
            'all_of': [
                {'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': 60},
            ],
        },
    },
    {
        'name': 'Clientes recurrentes (3+ citas)',
        'description': 'Han completado 3 o más citas.',
        'rules': {
            'all_of': [
                {'field': 'total_appointments_completed', 'op': 'gte', 'value': 3},
            ],
        },
    },
    {
        'name': 'VIP (gasto > $500.000)',
        'description': 'Han gastado más de $500.000 en servicios completados.',
        'rules': {
            'all_of': [
                {'field': 'total_spent', 'op': 'gt', 'value': 500000},
            ],
        },
    },
    {
        'name': 'Primer contacto sin agendar',
        'description': 'No registran citas completadas todavía.',
        'rules': {
            'all_of': [
                {'field': 'total_appointments_completed', 'op': 'eq', 'value': 0},
                {'field': 'last_appointment_at', 'op': 'is_null'},
            ],
        },
    },
    {
        'name': 'No-show reciente (30 días)',
        'description': 'Tuvieron al menos un no-show en los últimos 30 días.',
        'rules': {
            'all_of': [
                {'field': 'total_appointments_no_show', 'op': 'in_window_days', 'value': 30},
            ],
        },
    },
)


async def seed_preconstructed_segments(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    *,
    created_by: UUID | None = None,
) -> int:
    """Insert the default 5 segments for a new tenant.

    Idempotent through ``ON CONFLICT (tenant_id, name) DO NOTHING`` so calling
    it twice during onboarding doesn't fail.
    """
    inserted = 0
    for definition in PRECONSTRUCTED_SEGMENTS:
        row = await conn.fetchrow(
            """
            insert into app.contact_segments (
              tenant_id, name, description, kind, rules, is_system, created_by
            )
            values ($1, $2, $3, 'dynamic', $4::jsonb, true, $5)
            on conflict (tenant_id, name) do nothing
            returning id
            """,
            tenant_id,
            definition['name'],
            definition.get('description'),
            json.dumps(normalize_rules(definition['rules'])),
            created_by,
        )
        if row is not None:
            inserted += 1
    return inserted
