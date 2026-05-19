"""Handlers extracted from routes.py for web_router (public web widget).

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import json
import secrets
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from fastapi import Depends, Header, HTTPException, Request

from app.api.v1._helpers.notifications_db import notify_operations_change
from app.api.v1._helpers.projections import WEB_CHANNEL_PROJECTION
from app.api.v1._helpers.web_chat_db import _persist_bot_reply_sync
from app.api.v1.routes import web_router
from app.api.v1.schemas import WebChatMessage, WebChatStart
from app.core.config import get_settings
from app.db.pool import get_db
from app.services.audit import audit
from app.services.rag_orchestrator import orchestrate_inbound_message
from app.services.web_widget import (
    build_lead_source,
    constant_time_equals,
    decode_session_token,
    hash_phone,
    issue_session_token,
    origin_is_allowed,
    synthesize_web_identity,
)
from app.services.whatsapp import resolve_secret_ref

log = structlog.get_logger()


def _resolve_web_session(
    request: Request,
    authorization: str | None,
) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail='Session token required')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(status_code=401, detail='Invalid session token header')
    settings = get_settings()
    try:
        return decode_session_token(
            token,
            secret_key=settings.jwt_secret,
            issuer=settings.jwt_issuer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@web_router.post('/chat/start', status_code=201)
async def web_chat_start(
    payload: WebChatStart,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    tenant_row = await conn.fetchrow(
        'select id, slug from app.tenants where slug=$1 and deleted_at is null',
        payload.tenant_slug,
    )
    if not tenant_row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    tenant_id: UUID = tenant_row['id']

    channel = await conn.fetchrow(
        f"select {WEB_CHANNEL_PROJECTION} from app.tenant_channels where tenant_id=$1 and provider='web'",
        tenant_id,
    )
    if not channel or channel['status'] != 'active':
        raise HTTPException(status_code=404, detail='Web channel is not active for this tenant')

    expected_token = resolve_secret_ref(channel['token_ref'])
    if not constant_time_equals(payload.widget_token, expected_token):
        raise HTTPException(status_code=401, detail='Invalid widget token')

    origin = request.headers.get('origin') or request.headers.get('referer')
    allowed = list(channel['allowed_origins'] or [])
    if allowed and not origin_is_allowed(origin, allowed):
        raise HTTPException(status_code=403, detail='Origin not allowed for this widget')

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    lead_source = build_lead_source(
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        referrer=payload.referrer,
    )

    # SECURITY: Anonymous web widget sessions cannot prove ownership of the
    # phone/email they submit. Reusing an existing contact based on an
    # unverified phone enables customer impersonation (an attacker who knows a
    # victim's phone can submit a message like "no" and mutate the victim's
    # appointment confirmation state via the orchestrator). Always synthesize
    # a fresh web-only identity and store the user-supplied phone/email as
    # unverified metadata. Operations can later verify and merge contacts
    # through an authenticated flow.
    seed = f'{tenant_id}:{payload.phone or ""}:{payload.email or ""}:{secrets.token_hex(16)}'
    wa_id, phone_e164 = synthesize_web_identity(seed)
    contact_metadata: dict[str, Any] = {'phone_verified': False, 'email_verified': False}
    if payload.phone:
        contact_metadata['unverified_phone'] = payload.phone.strip()
    if payload.email:
        contact_metadata['unverified_email'] = payload.email.strip()
    # TASK-0055: link the new lead to the referring contact when the widget
    # received a ?ref=<contact_uuid> or data-ref=<contact_uuid> hint. We only
    # honour it if the referrer is a real contact of the same tenant.
    referrer_id: UUID | None = None
    if payload.referrer_contact_id:
        if await conn.fetchval(
            'select 1 from app.contacts where tenant_id=$1 and id=$2',
            tenant_id,
            payload.referrer_contact_id,
        ):
            referrer_id = payload.referrer_contact_id

    contact = await conn.fetchrow(
        """
        insert into app.contacts (
          tenant_id, wa_id, phone_e164, phone_hash, display_name, source,
          metadata, lead_source, referrer_contact_id
        )
        values ($1, $2, $3, $4, $5, 'web_widget', $6::jsonb, $7::jsonb, $8)
        returning *
        """,
        tenant_id,
        wa_id,
        phone_e164,
        hash_phone(phone_e164),
        payload.name.strip(),
        json.dumps(contact_metadata),
        json.dumps(lead_source),
        referrer_id,
    )

    conversation = await conn.fetchrow(
        """
        insert into app.conversations (tenant_id, contact_id, channel_id, status, opened_by, handoff_required)
        values ($1, $2, $3, 'open', 'user', false)
        returning *
        """,
        tenant_id,
        contact['id'],
        channel['id'],
    )

    inbound_message = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, received_at, payload
        )
        values ($1, $2, 'inbound', 'contact', $3, 'text', 'received', now(), $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation['id'],
        payload.message.strip(),
        json.dumps({
            'channel': 'web',
            'origin': origin,
            'lead_source': lead_source,
        }),
    )

    await notify_operations_change(
        conn,
        tenant_id,
        'conversation.changed',
        conversation_id=conversation['id'],
        message_id=inbound_message['id'],
    )

    try:
        await orchestrate_inbound_message(
            conn,
            tenant_id=tenant_id,
            channel_id=channel['id'],
            channel_account_mode=channel['account_mode'] or 'live',
            conversation=conversation,
            contact=contact,
            inbound_message=inbound_message,
        )
    except Exception:
        log.exception(
            'web_widget.orchestrator_error',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation['id']),
        )

    bot_reply = await _persist_bot_reply_sync(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
    )

    settings = get_settings()
    session_token, expires_at = issue_session_token(
        secret_key=settings.jwt_secret,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        contact_id=contact['id'],
        issuer=settings.jwt_issuer,
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='anonymous',
        actor_id=str(contact['id']),
        action='web_widget.chat_started',
        entity_type='conversation',
        entity_id=str(conversation['id']),
        metadata={'lead_source': lead_source},
    )

    return {
        'conversation_id': str(conversation['id']),
        'contact_id': str(contact['id']),
        'session_token': session_token,
        'session_expires_at': expires_at.isoformat(),
        'inbound_message_id': str(inbound_message['id']),
        'bot_reply': bot_reply,
        'lead_source': lead_source,
    }


@web_router.post('/chat/{conversation_id}/messages', status_code=201)
async def web_chat_send_message(
    conversation_id: UUID,
    payload: WebChatMessage,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    session = _resolve_web_session(request, authorization)
    if session.get('conversation_id') != str(conversation_id):
        raise HTTPException(status_code=403, detail='Session token does not match conversation')

    tenant_id = UUID(session['tenant_id'])
    contact_id = UUID(session['contact_id'])
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    conversation = await conn.fetchrow(
        'select * from app.conversations where tenant_id=$1 and id=$2',
        tenant_id,
        conversation_id,
    )
    if not conversation or conversation['contact_id'] != contact_id:
        raise HTTPException(status_code=404, detail='Conversation not found')

    channel = await conn.fetchrow(
        'select * from app.tenant_channels where tenant_id=$1 and id=$2',
        tenant_id,
        conversation['channel_id'],
    )
    if not channel or channel['provider'] != 'web':
        raise HTTPException(status_code=400, detail='Conversation is not on the web channel')

    contact = await conn.fetchrow(
        'select * from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')

    inbound_message = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, received_at, payload
        )
        values ($1, $2, 'inbound', 'contact', $3, 'text', 'received', now(), $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation_id,
        payload.body.strip(),
        json.dumps({'channel': 'web'}),
    )

    await notify_operations_change(
        conn,
        tenant_id,
        'conversation.changed',
        conversation_id=conversation_id,
        message_id=inbound_message['id'],
    )

    try:
        await orchestrate_inbound_message(
            conn,
            tenant_id=tenant_id,
            channel_id=channel['id'],
            channel_account_mode=channel['account_mode'] or 'live',
            conversation=conversation,
            contact=contact,
            inbound_message=inbound_message,
        )
    except Exception:
        log.exception(
            'web_widget.orchestrator_error',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation_id),
        )

    bot_reply = await _persist_bot_reply_sync(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
    )

    return {
        'inbound_message_id': str(inbound_message['id']),
        'bot_reply': bot_reply,
    }


@web_router.get('/chat/{conversation_id}/messages')
async def web_chat_history(
    conversation_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    session = _resolve_web_session(request, authorization)
    if session.get('conversation_id') != str(conversation_id):
        raise HTTPException(status_code=403, detail='Session token does not match conversation')
    tenant_id = UUID(session['tenant_id'])
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select id, direction, sender_actor_type, body_text, message_type, created_at
        from app.messages
        where tenant_id=$1 and conversation_id=$2
        order by created_at asc
        """,
        tenant_id,
        conversation_id,
    )
    return {
        'conversation_id': str(conversation_id),
        'messages': [
            {
                'id': str(row['id']),
                'direction': row['direction'],
                'sender_actor_type': row['sender_actor_type'],
                'body_text': row['body_text'] or '',
                'message_type': row['message_type'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            }
            for row in rows
        ],
    }
