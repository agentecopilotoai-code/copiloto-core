"""TASK-0067 — Resumen periódico (digest) por email y WhatsApp al manager.

El worker (`app/workers/digest_worker.py`) corre cada 10 minutos, consulta las
filas de ``app.digest_subscriptions`` cuya zona horaria del tenant marca las
08:00 locales y arma:

- **daily**: citas confirmadas hoy, citas para mañana, no-shows de ayer, top 3
  quejas abiertas (mensajes 1–2★ recientes), mensajes recibidos en 24h y
  conversión del funnel del día.
- **weekly** (lunes 08:00): lo del daily más ingreso semanal, top campañas,
  top servicios, retención 90d y comparación contra la semana anterior.

El builder devuelve ``{'subject', 'text', 'html', 'whatsapp_components'}``
para poder enviar el mismo payload por SMTP (vía ``operator_alerts
._send_email_channel``) y por la plantilla aprobada
``digest_daily_v1`` / ``digest_weekly_v1`` en WhatsApp Cloud API.

La idempotencia se ancla en ``digest_subscriptions.last_sent_at`` comparado
contra ``now() at time zone tenants.timezone`` — si la última corrida tiene
la misma fecha local (daily) o lunes-local de la misma semana ISO (weekly),
el worker la salta.
"""
from __future__ import annotations

import html
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


CADENCE_DAILY = 'daily'
CADENCE_WEEKLY = 'weekly'
VALID_CADENCES: frozenset[str] = frozenset({CADENCE_DAILY, CADENCE_WEEKLY})

WHATSAPP_DIGEST_DAILY_TEMPLATE = 'digest_daily_v1'
WHATSAPP_DIGEST_WEEKLY_TEMPLATE = 'digest_weekly_v1'
WHATSAPP_DIGEST_TEMPLATE_LOCALE = 'es'

# Cuando se ejecuta el worker apuntamos a las 08:00 hora local; le damos una
# ventana de 60 minutos por si el tick cae entre las 08:00 y las 08:59 para no
# perder un día por arranques diferidos. La idempotencia (``last_sent_at``)
# evita doble envío.
DELIVERY_HOUR_LOCAL = 8
DELIVERY_WINDOW_MINUTES = 60


def safe_zone(tz_name: str | None) -> ZoneInfo:
    """Resolve ``tenants.timezone`` to a ZoneInfo with safe fallback.

    Tenants nuevos siempre vienen con un timezone IANA válido, pero un valor
    truncado o un alias deprecado no debería tumbar el worker — caemos a UTC
    y emitimos un log para investigar.
    """
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            log.warning('digest.unknown_timezone', tz=tz_name)
    return ZoneInfo('UTC')


def is_due(
    *,
    cadence: str,
    now_utc: datetime,
    tz_name: str | None,
    last_sent_at: datetime | None,
) -> bool:
    """Return True si esta corrida puede despachar la suscripción.

    Reglas:
    - La hora local debe estar en la ventana ``08:00..08:59``.
    - ``weekly`` solo dispara los lunes (``weekday()==0``).
    - ``last_sent_at`` con misma fecha local (daily) o misma semana ISO
      (weekly) bloquea — evita doble envío si el worker tickea dos veces
      dentro de la ventana.
    """
    if cadence not in VALID_CADENCES:
        return False
    zone = safe_zone(tz_name)
    local_now = now_utc.astimezone(zone)
    if local_now.hour < DELIVERY_HOUR_LOCAL:
        return False
    if local_now.hour >= DELIVERY_HOUR_LOCAL + 1:
        return False
    if cadence == CADENCE_WEEKLY and local_now.weekday() != 0:
        return False
    if last_sent_at is None:
        return True
    last_local = last_sent_at.astimezone(zone)
    if cadence == CADENCE_DAILY:
        return last_local.date() < local_now.date()
    # weekly: comparamos por (año ISO, semana ISO) para que un envío del lunes
    # pasado no bloquee el lunes de esta semana.
    last_iso = last_local.isocalendar()
    now_iso = local_now.isocalendar()
    return (last_iso.year, last_iso.week) < (now_iso.year, now_iso.week)


def _format_money(value: float | int | None, currency: str = 'COP') -> str:
    amount = float(value or 0.0)
    return f'{currency} {amount:,.0f}'.replace(',', '.')


def _range_for_day(local_day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(local_day, time.min, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _range_for_week(monday_local: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(monday_local, time.min, tzinfo=zone)
    end_local = start_local + timedelta(days=7)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


async def _appointments_for_day(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    starts_in_utc: tuple[datetime, datetime],
    statuses: tuple[str, ...],
) -> int:
    row = await conn.fetchrow(
        """
        select count(*)::int as count
        from app.appointments
        where tenant_id = $1
          and starts_at >= $2 and starts_at < $3
          and status = any($4::text[])
        """,
        tenant_id, starts_in_utc[0], starts_in_utc[1], list(statuses),
    )
    return int(row['count'] or 0) if row else 0


async def _messages_received(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
) -> int:
    row = await conn.fetchrow(
        """
        select count(*)::int as count
        from app.messages
        where tenant_id = $1
          and direction = 'inbound'
          and created_at >= $2 and created_at < $3
        """,
        tenant_id, window_utc[0], window_utc[1],
    )
    return int(row['count'] or 0) if row else 0


async def _funnel_for_day(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
) -> dict[str, int]:
    """Conversión simple del día: leads → engaged → scheduled → completed.

    Igual filosofía que ``/v1/analytics/funnel`` pero limitada al rango
    diario para no inflar el email. Se omite ``repeat_customers`` porque la
    ventana de 90d no aplica al digest del día.
    """
    row = await conn.fetchrow(
        """
        with leads as (
          select id as contact_id
          from app.contacts
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ),
        engaged as (
          select distinct conv.contact_id
          from app.conversations conv
          join app.messages m on m.tenant_id = conv.tenant_id
                              and m.conversation_id = conv.id
          where conv.tenant_id = $1
            and m.direction = 'outbound'
            and m.sender_actor_type in ('bot','agent')
            and m.created_at >= $2 and m.created_at < $3
        ),
        scheduled as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ),
        completed as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1 and status = 'completed'
            and starts_at >= $2 and starts_at < $3
        )
        select
          (select count(*) from leads)::int as leads,
          (select count(*) from engaged)::int as engaged,
          (select count(*) from scheduled)::int as scheduled,
          (select count(*) from completed)::int as completed
        """,
        tenant_id, window_utc[0], window_utc[1],
    )
    if row is None:
        return {'leads': 0, 'engaged': 0, 'scheduled': 0, 'completed': 0}
    return {k: int(row[k] or 0) for k in ('leads', 'engaged', 'scheduled', 'completed')}


async def _top_complaints(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Top quejas abiertas: feedback 1–2★ con comentario en la ventana."""
    rows = await conn.fetch(
        """
        select coalesce(c.display_name, c.phone_e164, 'cliente') as contact_name,
               f.rating,
               coalesce(f.comment, '') as comment,
               f.created_at
        from app.appointment_feedback f
        left join app.contacts c
          on c.tenant_id = f.tenant_id and c.id = f.contact_id
        where f.tenant_id = $1
          and f.rating <= 2
          and f.created_at >= $2 and f.created_at < $3
        order by f.created_at desc
        limit $4
        """,
        tenant_id, window_utc[0], window_utc[1], limit,
    )
    return [
        {
            'contact_name': row['contact_name'],
            'rating': int(row['rating'] or 0),
            'comment': (row['comment'] or '').strip(),
        }
        for row in rows
    ]


async def _revenue_completed(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
) -> float:
    row = await conn.fetchrow(
        """
        select coalesce(sum(s.price_amount), 0)::float as revenue
        from app.appointments a
        left join app.service_catalog s
          on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1
          and a.status = 'completed'
          and a.starts_at >= $2 and a.starts_at < $3
        """,
        tenant_id, window_utc[0], window_utc[1],
    )
    return float(row['revenue'] or 0.0) if row else 0.0


async def _top_services(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select coalesce(s.name, a.service_code) as name,
               count(*)::int as count
        from app.appointments a
        left join app.service_catalog s
          on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1
          and a.created_at >= $2 and a.created_at < $3
        group by 1
        order by count desc nulls last
        limit $4
        """,
        tenant_id, window_utc[0], window_utc[1], limit,
    )
    return [
        {'name': row['name'] or '—', 'count': int(row['count'] or 0)}
        for row in rows
    ]


async def _top_campaigns(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    window_utc: tuple[datetime, datetime],
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select coalesce(camp.name, ca.campaign_id::text) as name,
               count(*)::int as conversions
        from app.campaign_attributions ca
        left join app.campaigns camp
          on camp.tenant_id = ca.tenant_id and camp.id = ca.campaign_id
        where ca.tenant_id = $1
          and ca.attributed_at >= $2 and ca.attributed_at < $3
        group by 1
        order by conversions desc
        limit $4
        """,
        tenant_id, window_utc[0], window_utc[1], limit,
    )
    return [
        {'name': row['name'] or '—', 'conversions': int(row['conversions'] or 0)}
        for row in rows
    ]


async def _retention_rate(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    end_utc: datetime,
) -> float:
    """% de contactos con ≥ 2 citas completadas en los últimos 90 días."""
    start = end_utc - timedelta(days=90)
    row = await conn.fetchrow(
        """
        with completed as (
          select contact_id, count(*) as ct
          from app.appointments
          where tenant_id = $1 and status = 'completed'
            and starts_at >= $2 and starts_at < $3
          group by contact_id
        )
        select
          count(*) filter (where ct >= 2)::int as recurring,
          count(*)::int as total
        from completed
        """,
        tenant_id, start, end_utc,
    )
    if row is None or not row['total']:
        return 0.0
    return float(row['recurring']) / float(row['total']) * 100.0


async def build_daily_digest(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    tz_name: str | None,
    today_local: date | None = None,
) -> dict[str, Any]:
    """Arma el digest diario para el ``today_local`` (default: hoy).

    Devuelve ``subject``, ``text``, ``html`` y ``whatsapp_components`` listos
    para ``operator_alerts._send_email_channel`` / la cola de WhatsApp.
    """
    zone = safe_zone(tz_name)
    if today_local is None:
        today_local = datetime.now(zone).date()
    yesterday_local = today_local - timedelta(days=1)
    tomorrow_local = today_local + timedelta(days=1)

    today_range = _range_for_day(today_local, zone)
    yesterday_range = _range_for_day(yesterday_local, zone)
    tomorrow_range = _range_for_day(tomorrow_local, zone)

    confirmed_today = await _appointments_for_day(
        conn,
        tenant_id=tenant_id,
        starts_in_utc=today_range,
        statuses=('confirmed', 'completed'),
    )
    appts_tomorrow = await _appointments_for_day(
        conn,
        tenant_id=tenant_id,
        starts_in_utc=tomorrow_range,
        statuses=('confirmed', 'pending', 'rescheduled'),
    )
    no_shows_yesterday = await _appointments_for_day(
        conn,
        tenant_id=tenant_id,
        starts_in_utc=yesterday_range,
        statuses=('no_show',),
    )
    messages_24h = await _messages_received(
        conn, tenant_id=tenant_id, window_utc=yesterday_range,
    )
    complaints = await _top_complaints(
        conn, tenant_id=tenant_id, window_utc=yesterday_range,
    )
    funnel = await _funnel_for_day(
        conn, tenant_id=tenant_id, window_utc=today_range,
    )

    kpis = {
        'cadence': CADENCE_DAILY,
        'date_local': today_local.isoformat(),
        'confirmed_today': confirmed_today,
        'appointments_tomorrow': appts_tomorrow,
        'no_shows_yesterday': no_shows_yesterday,
        'messages_received_24h': messages_24h,
        'funnel': funnel,
        'complaints': complaints,
    }
    subject, text, html_body = _render_daily(kpis)
    return {
        'subject': subject,
        'text': text,
        'html': html_body,
        'whatsapp_components': _whatsapp_components_daily(kpis),
        'kpis': kpis,
    }


async def build_weekly_digest(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    tz_name: str | None,
    monday_local: date | None = None,
    currency: str = 'COP',
) -> dict[str, Any]:
    zone = safe_zone(tz_name)
    if monday_local is None:
        today = datetime.now(zone).date()
        monday_local = today - timedelta(days=today.weekday())
    prev_monday = monday_local - timedelta(days=7)
    this_week = _range_for_week(monday_local, zone)
    last_week = _range_for_week(prev_monday, zone)

    daily = await build_daily_digest(
        conn, tenant_id=tenant_id, tz_name=tz_name, today_local=monday_local,
    )
    revenue_week = await _revenue_completed(
        conn, tenant_id=tenant_id, window_utc=this_week,
    )
    revenue_last_week = await _revenue_completed(
        conn, tenant_id=tenant_id, window_utc=last_week,
    )
    top_campaigns = await _top_campaigns(
        conn, tenant_id=tenant_id, window_utc=this_week,
    )
    top_services = await _top_services(
        conn, tenant_id=tenant_id, window_utc=this_week,
    )
    retention_pct = await _retention_rate(
        conn, tenant_id=tenant_id, end_utc=this_week[1],
    )

    if revenue_last_week > 0:
        delta_pct = (revenue_week - revenue_last_week) / revenue_last_week * 100.0
    else:
        delta_pct = 0.0 if revenue_week == 0 else 100.0

    kpis = {
        'cadence': CADENCE_WEEKLY,
        'week_start_local': monday_local.isoformat(),
        'currency': currency,
        'daily': daily['kpis'],
        'revenue_week': round(revenue_week, 2),
        'revenue_last_week': round(revenue_last_week, 2),
        'revenue_delta_pct': round(delta_pct, 1),
        'top_campaigns': top_campaigns,
        'top_services': top_services,
        'retention_pct_90d': round(retention_pct, 1),
    }
    subject, text, html_body = _render_weekly(kpis)
    return {
        'subject': subject,
        'text': text,
        'html': html_body,
        'whatsapp_components': _whatsapp_components_weekly(kpis),
        'kpis': kpis,
    }


def _render_daily(kpis: dict[str, Any]) -> tuple[str, str, str]:
    subject = f"[CopilotoIA] Resumen diario — {kpis['date_local']}"
    f = kpis['funnel']
    lines = [
        f"Resumen diario del {kpis['date_local']}",
        '',
        f"• Citas confirmadas hoy: {kpis['confirmed_today']}",
        f"• Citas para mañana: {kpis['appointments_tomorrow']}",
        f"• No-shows de ayer: {kpis['no_shows_yesterday']}",
        f"• Mensajes recibidos (24h): {kpis['messages_received_24h']}",
        (
            f"• Funnel del día: {f['leads']} leads → "
            f"{f['engaged']} engaged → {f['scheduled']} agendadas → "
            f"{f['completed']} completadas"
        ),
    ]
    if kpis['complaints']:
        lines += ['', 'Top quejas abiertas (1–2★):']
        for c in kpis['complaints']:
            preview = (c.get('comment') or '').replace('\n', ' ').strip()
            if len(preview) > 120:
                preview = preview[:119] + '…'
            lines.append(
                f"  • {c['contact_name']} ({c['rating']}★): {preview or '—'}"
            )
    lines += ['', 'Abre el Admin Panel para ver el desglose completo.']
    text = '\n'.join(lines)
    html_body = (
        '<h2>Resumen diario — '
        f"{html.escape(kpis['date_local'])}</h2>"
        '<ul>'
        f"<li>Citas confirmadas hoy: <strong>{kpis['confirmed_today']}</strong></li>"
        f"<li>Citas para mañana: <strong>{kpis['appointments_tomorrow']}</strong></li>"
        f"<li>No-shows de ayer: <strong>{kpis['no_shows_yesterday']}</strong></li>"
        f"<li>Mensajes recibidos (24h): <strong>{kpis['messages_received_24h']}</strong></li>"
        f"<li>Funnel: {f['leads']}/{f['engaged']}/{f['scheduled']}/{f['completed']}</li>"
        '</ul>'
    )
    return subject, text, html_body


def _render_weekly(kpis: dict[str, Any]) -> tuple[str, str, str]:
    subject = f"[CopilotoIA] Resumen semanal — semana del {kpis['week_start_local']}"
    daily = kpis['daily']
    f = daily['funnel']
    currency = kpis['currency']
    sign = '+' if kpis['revenue_delta_pct'] >= 0 else ''
    lines = [
        f"Resumen semanal (semana del {kpis['week_start_local']})",
        '',
        f"Ingreso semanal: {_format_money(kpis['revenue_week'], currency)} "
        f"({sign}{kpis['revenue_delta_pct']}% vs semana anterior)",
        f"Retención 90d: {kpis['retention_pct_90d']}%",
        '',
        'Daily de hoy:',
        f"• Citas confirmadas hoy: {daily['confirmed_today']}",
        f"• Citas para mañana: {daily['appointments_tomorrow']}",
        f"• No-shows de ayer: {daily['no_shows_yesterday']}",
        f"• Mensajes recibidos (24h): {daily['messages_received_24h']}",
        (
            f"• Funnel: {f['leads']} → {f['engaged']} → "
            f"{f['scheduled']} → {f['completed']}"
        ),
    ]
    if kpis['top_services']:
        lines += ['', 'Top servicios de la semana:']
        for svc in kpis['top_services']:
            lines.append(f"  • {svc['name']}: {svc['count']}")
    if kpis['top_campaigns']:
        lines += ['', 'Top campañas:']
        for camp in kpis['top_campaigns']:
            lines.append(f"  • {camp['name']}: {camp['conversions']}")
    if daily['complaints']:
        lines += ['', 'Quejas abiertas (1–2★) del último día:']
        for c in daily['complaints']:
            preview = (c.get('comment') or '').replace('\n', ' ').strip()
            if len(preview) > 120:
                preview = preview[:119] + '…'
            lines.append(
                f"  • {c['contact_name']} ({c['rating']}★): {preview or '—'}"
            )
    text = '\n'.join(lines)
    html_body = (
        '<h2>Resumen semanal — semana del '
        f"{html.escape(kpis['week_start_local'])}</h2>"
        f"<p>Ingreso: <strong>{html.escape(_format_money(kpis['revenue_week'], currency))}</strong> "
        f"({sign}{kpis['revenue_delta_pct']}% vs semana anterior)</p>"
        f"<p>Retención 90d: <strong>{kpis['retention_pct_90d']}%</strong></p>"
    )
    return subject, text, html_body


def _whatsapp_components_daily(kpis: dict[str, Any]) -> list[dict[str, Any]]:
    """Variables 1..5 para ``digest_daily_v1``.

    {{1}} fecha local, {{2}} confirmadas hoy, {{3}} para mañana,
    {{4}} no-shows ayer, {{5}} mensajes 24h.
    """
    return [
        {
            'type': 'body',
            'parameters': [
                {'type': 'text', 'text': str(kpis['date_local'])},
                {'type': 'text', 'text': str(kpis['confirmed_today'])},
                {'type': 'text', 'text': str(kpis['appointments_tomorrow'])},
                {'type': 'text', 'text': str(kpis['no_shows_yesterday'])},
                {'type': 'text', 'text': str(kpis['messages_received_24h'])},
            ],
        }
    ]


def _whatsapp_components_weekly(kpis: dict[str, Any]) -> list[dict[str, Any]]:
    """Variables 1..5 para ``digest_weekly_v1``.

    {{1}} semana, {{2}} ingreso formateado, {{3}} delta %, {{4}} retención %,
    {{5}} top servicio "name (count)".
    """
    daily = kpis['daily']
    top_services = kpis['top_services']
    if top_services:
        top = top_services[0]
        top_label = f"{top['name']} ({top['count']})"
    else:
        top_label = '—'
    sign = '+' if kpis['revenue_delta_pct'] >= 0 else ''
    return [
        {
            'type': 'body',
            'parameters': [
                {'type': 'text', 'text': str(kpis['week_start_local'])},
                {'type': 'text', 'text': _format_money(kpis['revenue_week'], kpis['currency'])},
                {'type': 'text', 'text': f"{sign}{kpis['revenue_delta_pct']}%"},
                {'type': 'text', 'text': f"{kpis['retention_pct_90d']}%"},
                {'type': 'text', 'text': top_label},
            ],
        }
    ]


def whatsapp_template_for_cadence(cadence: str) -> str:
    if cadence == CADENCE_WEEKLY:
        return WHATSAPP_DIGEST_WEEKLY_TEMPLATE
    return WHATSAPP_DIGEST_DAILY_TEMPLATE


__all__ = [
    'CADENCE_DAILY',
    'CADENCE_WEEKLY',
    'DELIVERY_HOUR_LOCAL',
    'DELIVERY_WINDOW_MINUTES',
    'VALID_CADENCES',
    'WHATSAPP_DIGEST_DAILY_TEMPLATE',
    'WHATSAPP_DIGEST_WEEKLY_TEMPLATE',
    'WHATSAPP_DIGEST_TEMPLATE_LOCALE',
    'build_daily_digest',
    'build_weekly_digest',
    'is_due',
    'safe_zone',
    'whatsapp_template_for_cadence',
]
