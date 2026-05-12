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


# ── TASK-0054: in-memory rule evaluator over an arbitrary facts dict ─────────
#
# Reused by ``service_catalog.applies_when`` to filter the services shown
# during booking based on the conversation's qualification answers. The shape
# is a small subset of the SQL rule language above ({all_of/any_of, with
# {key, op, value} predicates) but runs purely on a Python dict so callers
# don't need a DB roundtrip.

APPLIES_WHEN_OPS = frozenset({
    'eq',
    'ne',
    'in',
    'not_in',
    'lt',
    'lte',
    'gt',
    'gte',
    'is_null',
    'is_not_null',
    'contains_any',
    'contains_all',
})


def _valid_fact_key(key: Any) -> bool:
    return (
        isinstance(key, str)
        and bool(key)
        and len(key) <= 80
        and all(c.isalnum() or c == '_' for c in key)
        and not key[0].isdigit()
    )


def normalize_applies_when(rules: Any) -> dict[str, Any]:
    """Return an ``applies_when`` rule sanitized to the allowed shape.

    Always wraps in ``all_of`` for uniformity. Returns ``{}`` (always
    applies) when the input is empty or fully invalid — that way a service
    with a corrupted rule still shows up instead of disappearing silently.
    """
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(rules, dict) or not rules:
        return {}

    def _normalize_predicate(node: Any) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        if isinstance(node.get('all_of'), list):
            children = [
                child for child in (_normalize_predicate(c) for c in node['all_of']) if child
            ]
            return {'all_of': children} if children else None
        if isinstance(node.get('any_of'), list):
            children = [
                child for child in (_normalize_predicate(c) for c in node['any_of']) if child
            ]
            return {'any_of': children} if children else None
        key = node.get('key')
        op = node.get('op')
        if not _valid_fact_key(key) or op not in APPLIES_WHEN_OPS:
            return None
        result: dict[str, Any] = {'key': key, 'op': op}
        if 'value' in node:
            result['value'] = node['value']
        return result

    if isinstance(rules.get('all_of'), list):
        children = [
            child for child in (_normalize_predicate(c) for c in rules['all_of']) if child
        ]
        return {'all_of': children} if children else {}
    if isinstance(rules.get('any_of'), list):
        children = [
            child for child in (_normalize_predicate(c) for c in rules['any_of']) if child
        ]
        return {'any_of': children} if children else {}
    pred = _normalize_predicate(rules)
    return {'all_of': [pred]} if pred else {}


def _coerce_for_compare(value: Any) -> Any:
    """Best-effort cast so ``"true"`` matches ``True`` and ``"3"`` matches ``3``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', 'yes', 'sí', 'si'):
            return True
        if lowered in ('false', 'no'):
            return False
        try:
            if '.' in lowered:
                return float(lowered)
            return int(lowered)
        except ValueError:
            return value
    return value


def _equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    ca, cb = _coerce_for_compare(a), _coerce_for_compare(b)
    # Only compare as booleans when *both* sides actually normalized to a
    # bool. Falling back to ``bool(...)`` here would treat any non-empty
    # string like 'consultation' as True and match an ``eq true`` rule —
    # silently making services eligible/ineligible for the wrong answers.
    if isinstance(ca, bool) and isinstance(cb, bool):
        return ca == cb
    if isinstance(ca, bool) or isinstance(cb, bool):
        return False
    if isinstance(ca, (int, float)) and isinstance(cb, (int, float)):
        return float(ca) == float(cb)
    return str(ca).lower() == str(cb).lower()


def _evaluate_predicate(pred: dict[str, Any], facts: dict[str, Any]) -> bool:
    op = pred.get('op')
    key = pred.get('key')
    if not isinstance(key, str) or op not in APPLIES_WHEN_OPS:
        return False
    actual = facts.get(key)
    value = pred.get('value')

    if op == 'is_null':
        return actual is None
    if op == 'is_not_null':
        return actual is not None

    if actual is None:
        # All other operators require a present fact.
        return False

    if op == 'eq':
        return _equal(actual, value)
    if op == 'ne':
        return not _equal(actual, value)
    if op == 'in':
        if not isinstance(value, list):
            return False
        return any(_equal(actual, v) for v in value)
    if op == 'not_in':
        if not isinstance(value, list):
            return False
        return not any(_equal(actual, v) for v in value)
    if op in ('lt', 'lte', 'gt', 'gte'):
        ca = _coerce_for_compare(actual)
        cb = _coerce_for_compare(value)
        if not isinstance(ca, (int, float)) or not isinstance(cb, (int, float)):
            return False
        if op == 'lt':
            return float(ca) < float(cb)
        if op == 'lte':
            return float(ca) <= float(cb)
        if op == 'gt':
            return float(ca) > float(cb)
        return float(ca) >= float(cb)
    if op == 'contains_any':
        if not isinstance(value, list) or not isinstance(actual, (list, tuple)):
            return False
        return any(any(_equal(item, v) for item in actual) for v in value)
    if op == 'contains_all':
        if not isinstance(value, list) or not isinstance(actual, (list, tuple)):
            return False
        return all(any(_equal(item, v) for item in actual) for v in value)
    return False


def _evaluate_node(node: Any, facts: dict[str, Any]) -> bool:
    if not isinstance(node, dict) or not node:
        return True  # empty rule → always matches
    if isinstance(node.get('all_of'), list):
        children = node['all_of']
        if not children:
            return True
        return all(_evaluate_node(child, facts) for child in children)
    if isinstance(node.get('any_of'), list):
        children = node['any_of']
        if not children:
            return True
        return any(_evaluate_node(child, facts) for child in children)
    return _evaluate_predicate(node, facts)


def evaluate_rules(rules: Any, facts: Any) -> bool:
    """Evaluate an ``applies_when``-shaped rule against a facts dict.

    Returns ``True`` when the rule is empty/invalid so callers default to
    "applies always" rather than dropping the row.
    """
    if not isinstance(facts, dict):
        facts = {}
    normalized = normalize_applies_when(rules)
    if not normalized:
        return True
    return _evaluate_node(normalized, facts)


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
