"""TASK-0065 — Dead-letter queue de mensajes outbound.

Cuando ``event_worker`` agota el envío de un mensaje a Meta y lo deja con
``messages.status='failed'`` y ``error_code/error_message`` poblados, ese
mensaje queda invisible para el operador. Este módulo expone tres operaciones
puras (sin FastAPI) que las rutas y el scheduler reutilizan:

1.  ``list_dlq``: lista paginada con preview por ``error_code``.
2.  ``count_recent_failures``: conteo agrupado por ``error_code`` en la
    ventana móvil para alimentar la alerta automática.
3.  ``requeue_message``: resetea el mensaje a ``status='queued'`` y vuelve a
    encolar el evento ``message.queued`` para que el worker lo procese.

La alerta ``operator_alerts(kind='outbound_dlq_threshold')`` se enfila desde
el scheduler cuando el total en la ventana excede ``dlq_alert_threshold``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import UUID

import structlog

log = structlog.get_logger()


PREVIEW_PER_GROUP = 3


def normalize_error_code(value: Any) -> str:
    """Convierte ``error_code`` a un slug estable para agrupar/contar.

    Vacío o ``None`` se mapea a ``'transport_error'``: mismo bucket que usa
    el ``event_worker`` cuando el fallo es de red y no hay respuesta HTTP de
    Meta. Esto evita que un puñado de timeouts queden invisibles bajo un
    grupo NULL.
    """
    if value is None:
        return 'transport_error'
    text = str(value).strip()
    return text or 'transport_error'


def _row_to_item(row: Any) -> dict[str, Any]:
    payload = row['payload'] if 'payload' in row.keys() else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        'id': str(row['id']),
        'conversation_id': str(row['conversation_id']) if row.get('conversation_id') else None,
        'contact_phone_last4': (row.get('contact_phone') or '')[-4:],
        'message_type': row.get('message_type'),
        'body_preview': (row.get('body_text') or '')[:160],
        'error_code': normalize_error_code(row.get('error_code')),
        'error_message': row.get('error_message'),
        'failed_at': row['failed_at'].isoformat() if row.get('failed_at') else None,
        'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
        'payload': payload,
    }


async def list_dlq(
    conn: Any,
    *,
    tenant_id: UUID,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Devuelve ``{items, totals_by_error_code}``.

    ``items`` son los últimos ``limit`` mensajes ``status='failed'`` dentro
    de la ventana, opcionalmente filtrados por ``error_code``.
    ``totals_by_error_code`` es el conteo total por código en la ventana
    (sin aplicar el filtro), para que el panel pueda mostrar los buckets
    completos.
    """
    bounded_limit = max(1, min(int(limit), 500))
    where_parts = ['m.tenant_id = $1', "m.status = 'failed'"]
    params: list[Any] = [tenant_id]
    if since is not None:
        params.append(since)
        where_parts.append(f'coalesce(m.failed_at, m.created_at) >= ${len(params)}')
    if until is not None:
        params.append(until)
        where_parts.append(f'coalesce(m.failed_at, m.created_at) <= ${len(params)}')
    base_where = ' and '.join(where_parts)

    totals_rows = await conn.fetch(
        f"""
        select coalesce(nullif(m.error_code, ''), 'transport_error') as error_code,
               count(*) as count
        from app.messages m
        where {base_where}
          and m.direction='outbound'
        group by 1
        order by 2 desc
        """,
        *params,
    )
    totals = [
        {'error_code': normalize_error_code(row['error_code']), 'count': int(row['count'])}
        for row in totals_rows
    ]

    if error_code:
        params.append(error_code)
        items_where = (
            base_where
            + f" and coalesce(nullif(m.error_code, ''), 'transport_error') = ${len(params)}"
        )
    else:
        items_where = base_where

    params.append(bounded_limit)
    items_rows = await conn.fetch(
        f"""
        select m.id, m.conversation_id, m.message_type, m.body_text,
               m.error_code, m.error_message, m.failed_at, m.created_at,
               m.payload, ct.phone_e164 as contact_phone
        from app.messages m
        left join app.conversations cv on cv.id = m.conversation_id and cv.tenant_id = m.tenant_id
        left join app.contacts ct on ct.id = cv.contact_id and ct.tenant_id = m.tenant_id
        where {items_where}
          and m.direction='outbound'
        order by coalesce(m.failed_at, m.created_at) desc
        limit ${len(params)}
        """,
        *params,
    )
    items = [_row_to_item(row) for row in items_rows]
    return {'items': items, 'totals_by_error_code': totals}


async def count_recent_failures(
    conn: Any,
    *,
    tenant_id: UUID,
    window_minutes: int,
) -> dict[str, Any]:
    """Devuelve ``{total, by_error_code, preview}`` para la alerta automática.

    ``preview`` contiene hasta 5 fallos recientes (id, error_code,
    error_message, failed_at) que se inyectan en el payload de la alerta
    para que el operador entienda de un vistazo qué está fallando.
    """
    since = datetime.now(UTC) - timedelta(minutes=max(1, int(window_minutes)))
    rows = await conn.fetch(
        """
        select coalesce(nullif(m.error_code, ''), 'transport_error') as error_code,
               count(*) as count
        from app.messages m
        where m.tenant_id = $1
          and m.status = 'failed'
          and m.direction = 'outbound'
          and coalesce(m.failed_at, m.created_at) >= $2
        group by 1
        order by 2 desc
        """,
        tenant_id,
        since,
    )
    by_error_code = [
        {'error_code': normalize_error_code(row['error_code']), 'count': int(row['count'])}
        for row in rows
    ]
    total = sum(item['count'] for item in by_error_code)

    preview_rows = await conn.fetch(
        """
        select m.id, m.error_code, m.error_message,
               coalesce(m.failed_at, m.created_at) as at
        from app.messages m
        where m.tenant_id = $1
          and m.status = 'failed'
          and m.direction = 'outbound'
          and coalesce(m.failed_at, m.created_at) >= $2
        order by coalesce(m.failed_at, m.created_at) desc
        limit 5
        """,
        tenant_id,
        since,
    )
    preview = [
        {
            'id': str(row['id']),
            'error_code': normalize_error_code(row['error_code']),
            'error_message': (row['error_message'] or '')[:300],
            'at': row['at'].isoformat() if row['at'] else None,
        }
        for row in preview_rows
    ]
    return {
        'total': total,
        'window_minutes': int(window_minutes),
        'by_error_code': by_error_code,
        'preview': preview,
        'since': since.isoformat(),
    }


async def requeue_message(
    conn: Any,
    *,
    tenant_id: UUID,
    message_id: UUID,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Resetea un mensaje ``status='failed'`` a ``queued`` y lo re-encola.

    SEC-010 (DLQ retry idempotency): la transición ``failed → queued`` se hace
    en UN solo ``UPDATE ... WHERE status='failed' RETURNING retry_count`` que
    incrementa atomicamente ``retry_count``. Dos requeues concurrentes del
    MISMO mensaje (operator dobleclickea, bulk-requeue + manual race, etc.)
    no pueden ambos ganar el UPDATE — el segundo no matchea ``status='failed'``
    (porque el primero ya movió a ``queued``) y se reporta como
    ``already_queued`` sin emitir un segundo domain event. El ``idempotency_key``
    del domain event se deriva de ``(message_id, retry_count)`` — estable por
    intento, así que un retry posterior del MISMO ``retry_count`` (escenario
    teorico de retry de la operación administrativa entera) hace short-circuit
    en ``on conflict do nothing`` en lugar de emitir un duplicate.

    Operación idempotente desde el punto de vista del operador: si ya está
    en ``queued`` (re-clic accidental o race) la función devuelve
    ``{'requeued': False, 'reason': 'already_queued'}`` sin lanzar.
    Devuelve ``{'requeued': False, 'reason': 'not_found'}`` si el mensaje no
    existe en este tenant.

    El ``retry_count`` se incrementa SOLO en transiciones reales — operadores
    pueden inspeccionar la columna para entender cuántas veces se intentó
    rescatar un mensaje. La lógica del worker no lo lee (el TASK-0065 dice
    que el retry manual es decisión del operador y no afecta el bot).
    """
    row = await conn.fetchrow(
        """
        select id, status, direction, retry_count
        from app.messages
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        message_id,
    )
    if row is None:
        return {'requeued': False, 'reason': 'not_found'}
    if row['direction'] != 'outbound':
        return {'requeued': False, 'reason': 'not_outbound'}
    if row['status'] == 'queued':
        return {'requeued': False, 'reason': 'already_queued'}
    if row['status'] not in ('failed',):
        return {'requeued': False, 'reason': f'invalid_status:{row["status"]}'}

    # Atomic transition: only succeed if status is STILL 'failed' (defensive
    # against the race between the pre-check above and this UPDATE). The
    # RETURNING gives us the post-increment retry_count, which is the stable
    # half of the idempotency_key. If WHERE doesn't match (lost the race),
    # updated is None and we report 'already_queued' without emitting an event.
    updated = await conn.fetchrow(
        """
        update app.messages
        set status='queued',
            failed_at=null,
            error_code=null,
            error_message=null,
            retry_count = retry_count + 1
        where tenant_id=$1 and id=$2 and status='failed'
        returning retry_count
        """,
        tenant_id,
        message_id,
    )
    if updated is None:
        # Lost the race vs. a concurrent requeue (or the row's status changed
        # between fetchrow and update). Idempotent: report no-op.
        return {'requeued': False, 'reason': 'already_queued'}

    retry_count = int(updated['retry_count'])
    # Stable idempotency_key: derived from (message_id, retry_count). Two
    # concurrent retries can't both reach here because the atomic UPDATE
    # filters on status='failed'; if a future replay of THIS administrative
    # call happens with the same retry_count (e.g. application-level retry
    # of the bulk handler), on conflict do nothing makes it a true no-op.
    idem = f'message-retry:{message_id}:{retry_count}'
    inserted = await conn.fetchval(
        """
        insert into app.domain_events
          (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload)
        values ($1,'message',$2,'message.queued',$3,$4::jsonb)
        on conflict do nothing
        returning id
        """,
        tenant_id,
        message_id,
        idem,
        json.dumps({
            'retry': True,
            'retry_count': retry_count,
            'requested_by': requested_by or 'operator',
        }),
    )
    if inserted is None:
        # The (message_id, retry_count) tuple was already present — a previous
        # invocation of the same administrative retry attempt already emitted
        # the event. Idempotent: report success without re-emitting, otherwise
        # the operator UI would treat the second call as failure.
        log.info(
            'outbound_dlq.requeue_event_already_emitted',
            tenant_id=str(tenant_id),
            message_id=str(message_id),
            retry_count=retry_count,
            idempotency_key=idem,
        )
        return {
            'requeued': True,
            'message_id': str(message_id),
            'idempotency_key': idem,
            'retry_count': retry_count,
            'event_replayed': True,
        }
    log.info(
        'outbound_dlq.requeued',
        tenant_id=str(tenant_id),
        message_id=str(message_id),
        retry_count=retry_count,
        requested_by=requested_by,
    )
    return {
        'requeued': True,
        'message_id': str(message_id),
        'idempotency_key': idem,
        'retry_count': retry_count,
    }


async def requeue_tenant_dlq(
    conn: Any,
    *,
    tenant_id: UUID,
    error_code: str | None = None,
    since: datetime | None = None,
    limit: int = 500,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Bulk-requeue the failed outbound messages of a single tenant.

    Drives the platform-owner "retry masivo" action (UI-006.5). Selects up to
    ``limit`` matching ``status='failed'`` outbound messages — optionally
    narrowed by ``error_code`` and a ``since`` window — and requeues each one
    through :func:`requeue_message`, so the idempotency-key / domain-event
    guarantees are identical to a single manual retry.

    Returns ``{matched, requeued, message_ids, capped}``: ``matched`` is how
    many rows were selected, ``requeued`` how many actually transitioned, and
    ``capped`` is True when the selection hit ``limit`` (more may remain).
    """
    bounded_limit = max(1, min(int(limit), 1000))
    where_parts = ['tenant_id = $1', "status = 'failed'", "direction = 'outbound'"]
    params: list[Any] = [tenant_id]
    if error_code:
        params.append(error_code)
        where_parts.append(
            f"coalesce(nullif(error_code, ''), 'transport_error') = ${len(params)}"
        )
    if since is not None:
        params.append(since)
        where_parts.append(f'coalesce(failed_at, created_at) >= ${len(params)}')
    params.append(bounded_limit)
    rows = await conn.fetch(
        f"""
        select id
        from app.messages
        where {' and '.join(where_parts)}
        order by coalesce(failed_at, created_at) desc
        limit ${len(params)}
        """,
        *params,
    )
    message_ids = [row['id'] for row in rows]
    requeued: list[str] = []
    for message_id in message_ids:
        result = await requeue_message(
            conn,
            tenant_id=tenant_id,
            message_id=message_id,
            requested_by=requested_by,
        )
        if result.get('requeued'):
            requeued.append(str(message_id))
    log.info(
        'outbound_dlq.bulk_requeued',
        tenant_id=str(tenant_id),
        matched=len(message_ids),
        requeued=len(requeued),
        error_code=error_code,
        requested_by=requested_by,
    )
    return {
        'matched': len(message_ids),
        'requeued': len(requeued),
        'message_ids': requeued,
        'capped': len(message_ids) >= bounded_limit,
    }


async def maybe_emit_dlq_threshold_alerts(
    conn: Any,
    *,
    threshold: int,
    window_minutes: int,
    enqueue_alert: Any,
) -> int:
    """Recorre tenants y emite alertas cuando el conteo supera el umbral.

    ``enqueue_alert`` es ``app.services.operator_alerts.enqueue_operator_alert``
    inyectado para que los tests puedan ejercitar la rama sin tocar redes ni
    SMTP. Devuelve la cantidad de alertas encoladas en este tick.

    Para evitar duplicados ruidosos, se descarta el tick si ya hay una alerta
    ``outbound_dlq_threshold`` ``pending`` o ``sent`` en la ventana corriente
    para el mismo tenant.
    """
    tenants: Iterable[Any] = await conn.fetch(
        """
        select distinct m.tenant_id
        from app.messages m
        where m.status='failed'
          and m.direction='outbound'
          and coalesce(m.failed_at, m.created_at) >= now() - ($1 * interval '1 minute')
        """,
        int(window_minutes),
    )
    emitted = 0
    for tenant_row in tenants:
        tenant_id = tenant_row['tenant_id']
        stats = await count_recent_failures(
            conn,
            tenant_id=tenant_id,
            window_minutes=window_minutes,
        )
        if stats['total'] < threshold:
            continue
        existing = await conn.fetchval(
            """
            select 1 from app.operator_alerts
            where tenant_id=$1
              and kind='outbound_dlq_threshold'
              and status in ('pending','sent')
              and created_at >= now() - ($2 * interval '1 minute')
            limit 1
            """,
            tenant_id,
            int(window_minutes),
        )
        if existing:
            continue
        await enqueue_alert(
            conn,
            tenant_id=tenant_id,
            kind='outbound_dlq_threshold',
            payload={
                'threshold': int(threshold),
                'window_minutes': int(window_minutes),
                'total': stats['total'],
                'by_error_code': stats['by_error_code'],
                'preview': stats['preview'],
            },
        )
        emitted += 1
    return emitted


__all__ = [
    'count_recent_failures',
    'list_dlq',
    'maybe_emit_dlq_threshold_alerts',
    'normalize_error_code',
    'requeue_message',
    'requeue_tenant_dlq',
]
