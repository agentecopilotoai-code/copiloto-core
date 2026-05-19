"""Handlers extracted from routes.py for platform_admin_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import structlog
from fastapi import Depends, HTTPException, Query, Request, status

from app.api.v1._helpers.health import _derive_health_services
from app.api.v1._helpers.platform_filters import (
    _FLEET_LIST_STATUS_PATTERN,
    _INCIDENT_KIND_PATTERN,
    _INCIDENT_STATUS_PATTERN,
)
from app.api.v1.routes import (
    _VALID_STATUS_TRANSITIONS,
    platform_admin_router,
)
from app.api.v1.schemas import (
    PlatformDlqRetryRequest,
    TenantCreate,
    TenantStatusTransition,
)
from app.db.pool import get_db, record_to_dict
from app.services import (
    feature_flags as feature_flags_service,
    locale as locale_service,
    metrics,
    platform_billing,
    platform_dlq,
    platform_incidents,
    platform_runbooks,
)
from app.services.audit import audit
from app.services.legal import render_markdown_to_safe_html
from app.services.locale import SUPPORTED_COUNTRIES
from app.services.retention import seed_default_retention_policies
from app.services.segments import seed_preconstructed_segments

log = structlog.get_logger()


@platform_admin_router.post('/tenants', status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    # TASK-0073: timezone/locale/currency se derivan del country_code cuando el
    # caller no fija un override explícito.
    profile = locale_service.profile_for(payload.country_code)
    tz_value = payload.timezone or profile['timezone']
    row = await conn.fetchrow(
        """
        insert into app.tenants (slug, legal_name, display_name, vertical_code, business_type_label, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.business_type_label,
        payload.country_code,
        tz_value,
    )
    tenant_id = row['id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    default_escalation_policy = {
        'handoff_message': 'En este momento te conecto con un asesor. En breve te atienden 😊',
        'triggers': {
            'keywords': ['humano', 'asesor', 'agente', 'persona', 'queja', 'reclamo'],
            'after_bot_turns': 10,
            'confidence_below': 0.0,
        },
    }
    await conn.execute(
        """
        insert into app.tenant_settings (tenant_id, escalation_policy, locale, currency)
        values ($1, $2::jsonb, $3, $4)
        """,
        tenant_id,
        json.dumps(default_escalation_policy),
        profile['locale'],
        profile['currency'],
    )
    await seed_preconstructed_segments(conn, tenant_id)
    await seed_default_retention_policies(conn, tenant_id)
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant.created', entity_type='tenant', entity_id=str(tenant_id))
    return record_to_dict(row)


@platform_admin_router.get('/tenants')
async def list_tenants_fleet(
    status_filter: str | None = Query(default=None, alias='status', max_length=16),
    country: str | None = Query(default=None, max_length=2, min_length=2),
    vertical: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return a paginated fleet view of tenants for the platform owner.

    Supports the filters declared in `docs/UI_BACKLOG.md` UI-006.1:
    `status`, `country` (ISO-2), `vertical` and free-text `search` over slug or
    display_name. Soft-deleted tenants (`deleted_at IS NOT NULL`) are excluded.

    Each row carries the tenant profile plus aggregated metadata required by
    the UI: total member count, count of owners, the primary owner's email,
    and a `last_activity_at` timestamp (currently `tenants.updated_at` — see
    UI_BACKLOG note; a richer "last message" derivation lives in UI-006.2).
    """
    if status_filter is not None and not _FLEET_LIST_STATUS_PATTERN.match(status_filter):
        raise HTTPException(status_code=422, detail='invalid status filter')
    if country is not None and country.upper() not in set(SUPPORTED_COUNTRIES):
        raise HTTPException(status_code=422, detail='unsupported country code')

    rows = await conn.fetch(
        """
        select
            t.id,
            t.slug,
            t.legal_name,
            t.display_name,
            t.vertical_code,
            t.business_type_label,
            t.country_code,
            t.timezone,
            t.status,
            t.created_at,
            t.updated_at,
            coalesce(member_counts.total, 0) as member_count,
            coalesce(member_counts.owner_count, 0) as owner_count,
            owner_email_pick.owner_email as owner_email,
            t.updated_at as last_activity_at
        from app.tenants t
        left join (
            select
                tenant_id,
                count(distinct user_id) as total,
                count(distinct user_id) filter (where role = 'owner') as owner_count
            from app.user_tenant_roles
            group by tenant_id
        ) as member_counts on member_counts.tenant_id = t.id
        left join lateral (
            select u.email as owner_email
            from app.user_tenant_roles utr
            join app.users u on u.id = utr.user_id
            where utr.tenant_id = t.id and utr.role = 'owner'
            order by utr.created_at asc
            limit 1
        ) as owner_email_pick on true
        where t.deleted_at is null
          and ($1::text is null or t.status = $1)
          and ($2::text is null or t.country_code = $2)
          and ($3::text is null or t.vertical_code = $3)
          and (
            $4::text is null
            or t.slug ilike '%' || $4 || '%'
            or t.display_name ilike '%' || $4 || '%'
            or t.legal_name ilike '%' || $4 || '%'
          )
        order by t.created_at desc
        limit $5 offset $6
        """,
        status_filter,
        country.upper() if country else None,
        vertical,
        search,
        limit,
        offset,
    )
    total = await conn.fetchval(
        """
        select count(*) from app.tenants t
        where t.deleted_at is null
          and ($1::text is null or t.status = $1)
          and ($2::text is null or t.country_code = $2)
          and ($3::text is null or t.vertical_code = $3)
          and (
            $4::text is null
            or t.slug ilike '%' || $4 || '%'
            or t.display_name ilike '%' || $4 || '%'
            or t.legal_name ilike '%' || $4 || '%'
          )
        """,
        status_filter,
        country.upper() if country else None,
        vertical,
        search,
    )
    return {
        'items': [record_to_dict(row) for row in rows],
        'total': int(total or 0),
        'limit': limit,
        'offset': offset,
    }


@platform_admin_router.get('/platform/metrics/health')
async def platform_system_health(
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return a live System Health snapshot for the platform owner (UI-006.2).

    The payload carries the metrics snapshot (`collect_health_snapshot`),
    derived point-in-time alerts (`evaluate_health_alerts`), a synthesised
    per-service status list, and a live DB connectivity probe. No PII — only
    aggregates and provider/worker identifiers.
    """
    snapshot = metrics.collect_health_snapshot()
    alerts = metrics.evaluate_health_alerts(snapshot)

    db_ok = False
    db_latency_ms: float | None = None
    try:
        started = time.perf_counter()
        await conn.fetchval('select 1')
        db_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        db_ok = True
    except Exception:  # noqa: BLE001 — any failure means the DB probe is unhealthy
        db_ok = False

    services = _derive_health_services(snapshot, db_ok=db_ok, db_latency_ms=db_latency_ms)

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'snapshot': snapshot,
        'alerts': alerts,
        'services': services,
        'note': (
            'Snapshot vivo del registry Prometheus in-process (TASK-0060). '
            'Las series históricas 24h/7d/30d requieren la query API de '
            'Prometheus y se difieren.'
        ),
    }


@platform_admin_router.get('/platform/billing/mrr')
async def platform_billing_mrr(
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return a platform-level Billing / MRR snapshot for the platform owner.

    Aggregates `app.contact_subscriptions` + `app.subscription_plans` across all
    tenants: monthly-normalised MRR by currency / plan / tenant / country, 30-day
    churn, and a per-(tenant, provider) breakdown of failed payments. No contact
    PII is returned — only tenant identities and aggregates.
    """
    # Cross-tenant read. The router already enforces require_platform_owner +
    # require_mfa_for_privileged; `support_mode` is set transaction-locally.
    await conn.execute("select set_config('app.support_mode', 'true', true)")

    # BUG-112: MRR usa el precio "locked-in" del suscriptor cuando exists
    # (`cs.price_locked_amount`), cayendo a `sp.price_amount` para suscriptores
    # legacy (pre-fix) que no tienen snapshot. Sin esto, subir el precio del
    # plan inflaba retroactivamente el MRR de los suscriptores existentes —
    # MRR debe reflejar el cash flow real (lo que cada suscriptor paga),
    # no el precio actual del catálogo.
    tenant_rows = await conn.fetch(
        """
        select
            t.id as tenant_id,
            t.slug,
            t.display_name,
            t.legal_name,
            t.country_code,
            coalesce(cs.price_locked_currency, sp.currency) as currency,
            sp.billing_period,
            sum(coalesce(cs.price_locked_amount, sp.price_amount))
                filter (where cs.status = 'active') as price_sum,
            count(*) filter (where cs.status = 'active') as active_subscriptions,
            count(*) filter (where cs.status = 'past_due') as past_due_subscriptions,
            min(cs.next_billing_at) filter (where cs.status = 'active') as next_billing_at
        from app.tenants t
        join app.contact_subscriptions cs on cs.tenant_id = t.id
        join app.subscription_plans sp on sp.id = cs.plan_id
        where t.deleted_at is null
        group by t.id, t.slug, t.display_name, t.legal_name, t.country_code,
                 coalesce(cs.price_locked_currency, sp.currency), sp.billing_period
        """
    )
    # BUG-120: antes filtrábamos `where sp.status = 'active'`, lo que ocultaba
    # los planes archivados que todavía tenían suscriptores activos pagando —
    # `archive` es forward-only (no cancela contracts existentes), así que el
    # MRR de esos planes seguía facturándose pero no aparecía en el breakdown.
    # Mostramos todos los planes que tienen al menos 1 suscriptor activo o
    # past_due, sin importar el status del plan. El plan_status se incluye
    # para que la UI pueda decorar visualmente los archivados.
    #
    # BUG-181 (codex P2 sobre BUG-112): la columna `currency` antes era
    # `sp.currency` (current price del plan), pero la sum usa
    # `coalesce(cs.price_locked_amount, sp.price_amount)` — si el operador
    # cambia el currency del plan vía update (`currency = coalesce($7, currency)`),
    # los suscriptores conservan su `price_locked_currency` pero el reporte
    # los etiqueta con el nuevo `sp.currency` (ej. COP locked → reportado USD).
    # Las otras queries (tenant/country/failed) ya bucketean por
    # `coalesce(cs.price_locked_currency, sp.currency)`; alineamos esta también.
    plan_rows = await conn.fetch(
        """
        select
            sp.name as plan_name,
            sp.status as plan_status,
            sp.billing_period,
            coalesce(cs.price_locked_currency, sp.currency) as currency,
            count(cs.id) filter (where cs.status = 'active') as active_subscriptions,
            count(cs.id) filter (where cs.status = 'past_due') as past_due_subscriptions,
            sum(coalesce(cs.price_locked_amount, sp.price_amount))
                filter (where cs.status = 'active') as price_sum
        from app.subscription_plans sp
        left join app.contact_subscriptions cs on cs.plan_id = sp.id
        group by sp.name, sp.status, sp.billing_period,
                 coalesce(cs.price_locked_currency, sp.currency)
        having count(cs.id) filter (where cs.status in ('active', 'past_due')) > 0
        """
    )
    country_rows = await conn.fetch(
        """
        select
            t.country_code,
            coalesce(cs.price_locked_currency, sp.currency) as currency,
            sp.billing_period,
            count(*) filter (where cs.status = 'active') as active_subscriptions,
            sum(coalesce(cs.price_locked_amount, sp.price_amount))
                filter (where cs.status = 'active') as price_sum
        from app.tenants t
        join app.contact_subscriptions cs on cs.tenant_id = t.id
        join app.subscription_plans sp on sp.id = cs.plan_id
        where t.deleted_at is null
        group by t.country_code, coalesce(cs.price_locked_currency, sp.currency), sp.billing_period
        """
    )
    country_tenant_rows = await conn.fetch(
        """
        select t.country_code, count(distinct t.id) as tenant_count
        from app.tenants t
        join app.contact_subscriptions cs on cs.tenant_id = t.id
        where t.deleted_at is null
        group by t.country_code
        """
    )
    failed_rows = await conn.fetch(
        """
        select
            t.id as tenant_id,
            t.slug,
            t.display_name,
            t.legal_name,
            cs.payment_provider,
            coalesce(cs.price_locked_currency, sp.currency) as currency,
            count(*) as failed_count,
            sum(coalesce(cs.price_locked_amount, sp.price_amount)) as amount_pending
        from app.tenants t
        join app.contact_subscriptions cs on cs.tenant_id = t.id
        join app.subscription_plans sp on sp.id = cs.plan_id
        where t.deleted_at is null and cs.status = 'past_due'
        group by t.id, t.slug, t.display_name, t.legal_name, cs.payment_provider,
                 coalesce(cs.price_locked_currency, sp.currency)
        order by amount_pending desc nulls last
        """
    )
    churn_row = await conn.fetchrow(
        """
        select
            count(*) filter (where cs.status = 'active') as active_total,
            count(*) filter (where cs.status = 'past_due') as past_due_total,
            count(*) filter (
                where cs.status = 'cancelled'
                  and cs.cancelled_at >= now() - interval '30 days'
            ) as cancelled_30d
        from app.contact_subscriptions cs
        join app.tenants t on t.id = cs.tenant_id
        where t.deleted_at is null
        """
    )

    tenant_dicts = [record_to_dict(row) for row in tenant_rows]
    tenants = platform_billing.fold_tenant_rows(tenant_dicts)
    mrr_by_currency = platform_billing.summarize_mrr_by_currency(tenant_dicts)

    mrr_by_plan = []
    for row in plan_rows:
        mrr_by_plan.append({
            'plan_name': row['plan_name'],
            # BUG-120: el frontend decora visualmente los planes archivados
            # que todavía tienen subs activas (status badge).
            'plan_status': row['plan_status'],
            'billing_period': row['billing_period'],
            'currency': row['currency'],
            'active_subscriptions': int(row['active_subscriptions'] or 0),
            'past_due_subscriptions': int(row['past_due_subscriptions'] or 0),
            'mrr': platform_billing.normalize_mrr(row['billing_period'], row['price_sum']),
        })
    mrr_by_plan.sort(key=lambda item: item['mrr'], reverse=True)

    tenant_count_by_country = {
        (row['country_code'] or 'UNK'): int(row['tenant_count'] or 0)
        for row in country_tenant_rows
    }
    countries: dict[str, dict] = {}
    for row in country_rows:
        code = row['country_code'] or 'UNK'
        entry = countries.setdefault(
            code,
            {'country_code': code, 'active_subscriptions': 0, '_by_currency': {}},
        )
        entry['active_subscriptions'] += int(row['active_subscriptions'] or 0)
        currency = row['currency'] or 'UNK'
        mrr = platform_billing.normalize_mrr(row['billing_period'], row['price_sum'])
        entry['_by_currency'][currency] = round(
            entry['_by_currency'].get(currency, 0.0) + mrr, 2
        )
    by_country = [
        {
            'country_code': code,
            'tenant_count': tenant_count_by_country.get(code, 0),
            'active_subscriptions': entry['active_subscriptions'],
            'mrr_by_currency': [
                {'currency': currency, 'mrr': mrr}
                for currency, mrr in sorted(entry['_by_currency'].items())
            ],
        }
        for code, entry in countries.items()
    ]
    by_country.sort(
        key=lambda item: sum(c['mrr'] for c in item['mrr_by_currency']), reverse=True
    )

    failed_items = []
    for row in failed_rows:
        failed_items.append({
            'tenant_id': str(row['tenant_id']),
            'slug': row['slug'],
            'display_name': row['display_name'] or row['legal_name'],
            'payment_provider': row['payment_provider'],
            'currency': row['currency'],
            'failed_count': int(row['failed_count'] or 0),
            'amount_pending': float(row['amount_pending'] or 0),
        })

    active_total = int(churn_row['active_total'] or 0) if churn_row else 0
    past_due_total = int(churn_row['past_due_total'] or 0) if churn_row else 0
    cancelled_30d = int(churn_row['cancelled_30d'] or 0) if churn_row else 0
    churn_denominator = active_total + cancelled_30d
    churn_rate = (cancelled_30d / churn_denominator) if churn_denominator else 0.0

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'mrr_by_currency': mrr_by_currency,
        'mrr_by_plan': mrr_by_plan,
        'churn': {
            'window_days': 30,
            'active_subscriptions': active_total,
            'past_due_subscriptions': past_due_total,
            'cancelled': cancelled_30d,
            'churn_rate': round(churn_rate, 4),
        },
        'failed_payments': {
            'count': sum(item['failed_count'] for item in failed_items),
            'items': failed_items,
        },
        'tenants': tenants,
        'by_country': by_country,
        'note': (
            'MRR mensual-normalizada agregada desde las suscripciones '
            'tenant→contacto de TASK-0075 (app.contact_subscriptions + '
            'app.subscription_plans). Expansión y retención requieren snapshots '
            'históricos de MRR que el schema no almacena — se difieren.'
        ),
    }


@platform_admin_router.get('/platform/incidents')
async def platform_incidents_feed(
    status_filter: str | None = Query(default=None, alias='status', max_length=16),
    kind: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return the cross-tenant incidents feed for the platform owner (UI-006.4).

    Reads `app.operator_alerts` joined to `app.tenants`, deriving a severity and
    a runbook reference per alert `kind`. Supports `status` and `kind` filters.
    No contact PII — only the alert payload, tenant identity and delivery
    timeline fields the alert row already carries.
    """
    if status_filter is not None and not _INCIDENT_STATUS_PATTERN.match(status_filter):
        raise HTTPException(status_code=422, detail='invalid status filter')
    if kind is not None and not _INCIDENT_KIND_PATTERN.match(kind):
        raise HTTPException(status_code=422, detail='invalid kind filter')

    # Cross-tenant read. The router already enforces require_platform_owner +
    # require_mfa_for_privileged; `support_mode` is set transaction-locally and
    # is the documented operator path for system-level (NULL-tenant) alerts.
    await conn.execute("select set_config('app.support_mode', 'true', true)")

    rows = await conn.fetch(
        """
        select
            oa.id,
            oa.tenant_id,
            t.slug as tenant_slug,
            t.display_name as tenant_display_name,
            t.legal_name as tenant_legal_name,
            oa.kind,
            oa.status,
            oa.payload,
            oa.attempts,
            oa.last_error,
            oa.scheduled_for,
            oa.created_at,
            oa.sent_at,
            oa.updated_at
        from app.operator_alerts oa
        left join app.tenants t on t.id = oa.tenant_id
        where ($1::text is null or oa.status = $1)
          and ($2::text is null or oa.kind = $2)
        order by oa.created_at desc
        limit $3
        """,
        status_filter,
        kind,
        limit,
    )

    incidents = []
    for row in rows:
        payload = row['payload']
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        incidents.append({
            'id': str(row['id']),
            'kind': row['kind'],
            'severity': platform_incidents.severity_for_kind(row['kind']),
            'runbook': platform_incidents.runbook_for_kind(row['kind']),
            'status': row['status'],
            'is_open': platform_incidents.is_open(row['status']),
            'tenant_id': str(row['tenant_id']) if row['tenant_id'] else None,
            'tenant_name': (
                row['tenant_display_name']
                or row['tenant_legal_name']
                or row['tenant_slug']
            ),
            'tenant_slug': row['tenant_slug'],
            # BUG-119: redactar PII (contact_phone/contact_name/recipient_email,
            # canales del operador) antes de devolver al platform_owner.
            'payload': platform_incidents.redact_incident_payload(
                payload if isinstance(payload, dict) else {}
            ),
            'attempts': int(row['attempts'] or 0),
            'last_error': row['last_error'],
            'scheduled_for': row['scheduled_for'],
            'created_at': row['created_at'],
            'sent_at': row['sent_at'],
            'updated_at': row['updated_at'],
        })

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'incidents': incidents,
        'summary': platform_incidents.summarize_incidents(incidents),
        'note': (
            'Feed de incidentes derivado de app.operator_alerts (TASK-0057 / '
            'TASK-0064 / TASK-0065). Asignación, MTTR, postmortem y comentarios '
            'requieren un modelo de gestión de incidentes que el schema no '
            'tiene — se difieren a un ticket de backend.'
        ),
    }


@platform_admin_router.get('/platform/outbound-dlq')
async def platform_outbound_dlq(
    window_minutes: int = Query(default=60, ge=1, le=10080),
    tenant_id: UUID | None = Query(default=None),
    error_code: str | None = Query(default=None, max_length=64),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return the cross-tenant Outbound DLQ aggregate for the platform owner.

    Counts failed outbound messages within the `window_minutes` window grouped
    by tenant and by error_code. Optional `tenant_id` / `error_code` filters
    narrow the aggregate. No message bodies or contact PII — only counts.
    """
    # Cross-tenant read. The router already enforces require_platform_owner +
    # require_mfa_for_privileged; `support_mode` is set transaction-locally.
    await conn.execute("select set_config('app.support_mode', 'true', true)")

    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    rows = await conn.fetch(
        """
        select
            m.tenant_id,
            t.slug,
            t.display_name,
            coalesce(nullif(m.error_code, ''), 'transport_error') as error_code,
            count(*) as count
        from app.messages m
        join app.tenants t on t.id = m.tenant_id
        where m.status = 'failed'
          and m.direction = 'outbound'
          and coalesce(m.failed_at, m.created_at) >= $1
          and ($2::uuid is null or m.tenant_id = $2)
          and (
            $3::text is null
            or coalesce(nullif(m.error_code, ''), 'transport_error') = $3
          )
        group by m.tenant_id, t.slug, t.display_name,
                 coalesce(nullif(m.error_code, ''), 'transport_error')
        """,
        since,
        tenant_id,
        error_code,
    )
    row_dicts = [record_to_dict(row) for row in rows]

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'window_minutes': window_minutes,
        'since': since.isoformat(),
        'summary': platform_dlq.summarize_fleet_dlq(row_dicts),
        'by_tenant': platform_dlq.fold_dlq_by_tenant(row_dicts),
        'by_error_code': platform_dlq.summarize_by_error_code(row_dicts),
        'note': (
            'Agregado cross-tenant de app.messages (status=failed, '
            'direction=outbound) de TASK-0065. Cada tenant ve el detalle de '
            'sus propios mensajes en su panel; esta vista solo agrega conteos.'
        ),
    }


@platform_admin_router.post('/platform/outbound-dlq/retry')
async def platform_outbound_dlq_retry(
    payload: PlatformDlqRetryRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Bulk-requeue the failed outbound messages of one tenant (UI-006.5).

    The platform owner always retries a single tenant's DLQ explicitly — there
    is no fleet-wide "retry everything". Each message is requeued through the
    same `requeue_message` path as a single manual retry, so the idempotency
    and domain-event guarantees are identical. The action is audited.
    """
    await conn.execute("select set_config('app.support_mode', 'true', true)")

    tenant = await conn.fetchrow(
        'select id from app.tenants where id = $1 and deleted_at is null',
        payload.tenant_id,
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail='Tenant not found')

    since = datetime.now(UTC) - timedelta(minutes=payload.window_minutes)
    from app.services.outbound_dlq import requeue_tenant_dlq

    result = await requeue_tenant_dlq(
        conn,
        tenant_id=payload.tenant_id,
        error_code=payload.error_code,
        since=since,
        limit=payload.limit,
        requested_by=getattr(request.state, 'actor_id', None),
    )
    await audit(
        conn,
        tenant_id=payload.tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='platform.outbound_dlq.bulk_retried',
        entity_type='tenant',
        entity_id=str(payload.tenant_id),
    )
    return result


@platform_admin_router.get('/platform/runbooks')
async def platform_runbooks_list():
    """Return the runbook catalogue for the platform owner (UI-006.6)."""
    items = platform_runbooks.list_runbooks()
    categories = sorted({item['category'] for item in items})
    return {'runbooks': items, 'categories': categories}


@platform_admin_router.get('/platform/runbooks/{slug}')
async def platform_runbook_detail(slug: str):
    """Return one runbook rendered to safe HTML, or 404 when the slug is
    invalid / the file does not exist."""
    runbook = platform_runbooks.read_runbook(slug)
    if runbook is None:
        raise HTTPException(status_code=404, detail='Runbook not found')
    return {
        'slug': runbook['slug'],
        'filename': runbook['filename'],
        'title': runbook['title'],
        'category': runbook['category'],
        'html': render_markdown_to_safe_html(runbook['content_md']),
    }


@platform_admin_router.get('/platform/feature-flags')
async def platform_feature_flags():
    """Return the read-only feature-flag catalogue for the platform owner."""
    flags = feature_flags_service.list_feature_flags()
    return {
        'flags': flags,
        'flag_types': list(feature_flags_service.FLAG_TYPES),
        'summary': feature_flags_service.summarize_feature_flags(flags),
        'note': (
            'Catálogo de solo lectura del registro estático de feature flags. '
            'El toggle en vivo, el rollout gradual y los overrides por tenant '
            'requieren un sistema de feature flags persistido y auditado — un '
            'ticket de backend aparte que aún no existe.'
        ),
    }


@platform_admin_router.patch('/tenants/{tenant_id}/status')
async def patch_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusTransition,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    # TASK-0077/BUG11: tenant lifecycle transitions (active/suspended/churned)
    # are platform-owner-only.  The router-level ``require_platform_owner``
    # dependency already enforces the unscoped owner role; we still keep the
    # set_config so RLS-aware audit triggers see the right tenant.
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    current_status = row['status']
    allowed = _VALID_STATUS_TRANSITIONS.get(current_status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transición inválida: {current_status!r} → {payload.status!r}. "
                   f"Transiciones permitidas desde '{current_status}': {sorted(allowed) or 'ninguna'}.",
        )
    updated = await conn.fetchrow(
        'update app.tenants set status=$2, updated_at=now() where id=$1 and deleted_at is null returning *',
        tenant_id,
        payload.status,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.status_changed',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={'from_status': current_status, 'to_status': payload.status, 'reason': payload.reason},
    )
    return record_to_dict(updated)

