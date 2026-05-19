"""Onboarding verification DB helpers extracted from app/api/v1/routes.py.

TASK-0069 — Wizard de onboarding self-service con verificación paso-a-paso.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.onboarding import (
    ONBOARDING_CONSENT_TEMPLATE_NAME,
    normalize_onboarding_progress,
)
from app.api.v1._helpers.parsing import _coerce_jsonb
from app.api.v1._helpers.secrets import tenant_secret_ref
from app.services.whatsapp import secret_ref_is_configured, token_ref_is_configured


async def _verify_onboarding_business_details(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    tenant = await conn.fetchrow(
        'select slug, legal_name, display_name, vertical_code, country_code, timezone, status, deleted_at '
        'from app.tenants where id=$1',
        tenant_id,
    )
    if not tenant:
        return False, 'Tenant no encontrado.', {}
    missing = [
        f for f in ('slug', 'legal_name', 'display_name', 'vertical_code', 'country_code', 'timezone')
        if not (tenant[f] and str(tenant[f]).strip())
    ]
    if missing:
        return False, f'Faltan campos del negocio: {", ".join(missing)}.', {'missing': missing}
    if tenant['deleted_at'] is not None:
        return False, 'Tenant eliminado.', {}
    return True, 'Datos del negocio completos.', {'slug': tenant['slug'], 'vertical_code': tenant['vertical_code']}


async def _verify_onboarding_locale_currency(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    tenant = await conn.fetchrow('select timezone from app.tenants where id=$1', tenant_id)
    settings = await conn.fetchrow(
        'select locale, payment_settings from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    if not tenant or not settings:
        return False, 'Settings o tenant ausentes.', {}
    timezone = (tenant['timezone'] or '').strip()
    locale = (settings['locale'] or '').strip()
    payment_settings = _coerce_jsonb(settings['payment_settings']) or {}
    currency = (payment_settings.get('currency') or '').strip() if isinstance(payment_settings, dict) else ''
    missing = []
    if not timezone:
        missing.append('timezone')
    if not locale:
        missing.append('locale')
    if not currency:
        missing.append('currency')
    if missing:
        return False, f'Falta configurar: {", ".join(missing)}.', {'missing': missing}
    return True, 'Timezone, locale y moneda configurados.', {'timezone': timezone, 'locale': locale, 'currency': currency}


async def _verify_onboarding_whatsapp_channel(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    channel = await conn.fetchrow(
        """
        select business_id, waba_id, phone_number_id, token_ref, app_secret_ref,
               verify_token_hash is not null as verify_token_hash_configured, status
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    if not channel:
        return False, 'Canal WhatsApp no aprovisionado. Configúralo desde el wizard.', {}
    if channel['status'] != 'active':
        return False, f"Canal WhatsApp en estado {channel['status']}.", {'status': channel['status']}
    if not (channel['business_id'] and channel['waba_id'] and channel['phone_number_id']):
        return False, 'Falta business_id, waba_id o phone_number_id de Meta.', {}
    if not token_ref_is_configured(channel['token_ref']):
        return False, 'Token Meta inválido o ausente. Vuelve a pegar el token de acceso.', {}
    if not secret_ref_is_configured(channel['app_secret_ref']):
        return False, 'App Secret ausente. Configúralo para validar firmas HMAC.', {}
    if not channel['verify_token_hash_configured']:
        return False, 'Verify Token del webhook ausente. Genera y pega el verify token.', {}
    verify_token_ref = tenant_secret_ref(tenant_id, 'whatsapp_verify_token')
    if not secret_ref_is_configured(verify_token_ref):
        return False, 'Verify Token no resuelto en el secret store. Reconfigura el canal.', {}
    return True, 'Canal WhatsApp con firma verificada contra Meta.', {
        'business_id': channel['business_id'],
        'waba_id': channel['waba_id'],
        'phone_number_id': channel['phone_number_id'],
    }


async def _verify_onboarding_consent_template(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    row = await conn.fetchrow(
        """
        select status from app.whatsapp_templates
        where tenant_id=$1 and name=$2 and purpose='consent_request'
        order by updated_at desc limit 1
        """,
        tenant_id,
        ONBOARDING_CONSENT_TEMPLATE_NAME,
    )
    if not row:
        return False, (
            f'No existe el template {ONBOARDING_CONSENT_TEMPLATE_NAME}. '
            'Crea y sincroniza el opt-in con Meta desde el wizard.'
        ), {}
    if row['status'] != 'approved':
        return False, (
            f'Template {ONBOARDING_CONSENT_TEMPLATE_NAME} en estado {row["status"]}. '
            'Espera la aprobación de Meta antes de continuar.'
        ), {'status': row['status']}
    return True, 'Template consent_request_v1 aprobado por Meta.', {'status': 'approved'}


async def _verify_onboarding_service_catalog(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    count = await conn.fetchval(
        'select count(*) from app.service_catalog where tenant_id=$1 and is_active=true',
        tenant_id,
    )
    count = int(count or 0)
    if count <= 0:
        return False, 'Crea al menos un servicio activo en el catálogo.', {'active_services': 0}
    return True, f'{count} servicio(s) activo(s) en el catálogo.', {'active_services': count}


async def _verify_onboarding_business_hours(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    row = await conn.fetchrow(
        'select business_hours from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    if not row:
        return False, 'Tenant settings ausentes.', {}
    hours = _coerce_jsonb(row['business_hours']) or {}
    if not isinstance(hours, dict) or not hours:
        return False, 'Horarios de atención vacíos.', {}
    # TenantSetupWizard persiste {timezone_strategy, weekly_schedule: {mon: [...]}}.
    # Aceptamos esa forma y también el flat {day: [...]} para tests/seeds.
    weekly = hours.get('weekly_schedule') if isinstance(hours.get('weekly_schedule'), dict) else hours
    populated = {day: ranges for day, ranges in weekly.items() if ranges}
    if not populated:
        return False, 'Ningún día tiene rangos de atención definidos.', {}
    return True, f'Horarios definidos para {len(populated)} día(s).', {'days_configured': sorted(populated.keys())}


async def _verify_onboarding_end_to_end_test(conn: asyncpg.Connection, tenant_id: UUID) -> tuple[bool, str, dict[str, Any]]:
    settings = await conn.fetchrow(
        'select onboarding_progress from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    progress = normalize_onboarding_progress(_coerce_jsonb(settings['onboarding_progress']) if settings else {})
    step7 = progress['steps'].get('7') or {}
    sent_at = step7.get('test_message_sent_at')
    if not sent_at:
        return False, 'Aún no se envió el mensaje de prueba al wa_id del admin.', {}
    target_wa_id = step7.get('target_wa_id')
    if not target_wa_id:
        return False, (
            'No se registró el wa_id del admin al que se envió la prueba. '
            'Vuelve a marcar el envío con el wa_id correcto.'
        ), {'sent_at': sent_at}
    inbound = await conn.fetchrow(
        """
        select m.id, m.created_at, c.wa_id
        from app.messages m
        join app.conversations conv on conv.id=m.conversation_id and conv.tenant_id=m.tenant_id
        join app.contacts c on c.id=conv.contact_id and c.tenant_id=m.tenant_id
        where m.tenant_id=$1
          and m.direction='inbound'
          and m.created_at >= $2::timestamptz
          and c.wa_id=$3
        order by m.created_at desc limit 1
        """,
        tenant_id,
        sent_at,
        str(target_wa_id),
    )
    if not inbound:
        return False, (
            f'No se recibió ningún mensaje inbound de {target_wa_id} '
            'después de enviar la prueba. Pide al admin que responda al mensaje.'
        ), {'sent_at': sent_at, 'target_wa_id': target_wa_id}
    return True, 'Test E2E exitoso: inbound del wa_id del admin recibido.', {
        'sent_at': sent_at,
        'target_wa_id': target_wa_id,
        'inbound_message_id': str(inbound['id']),
        'inbound_at': inbound['created_at'].isoformat() if inbound['created_at'] else None,
    }


ONBOARDING_VERIFIERS = {
    1: _verify_onboarding_business_details,
    2: _verify_onboarding_locale_currency,
    3: _verify_onboarding_whatsapp_channel,
    4: _verify_onboarding_consent_template,
    5: _verify_onboarding_service_catalog,
    6: _verify_onboarding_business_hours,
    7: _verify_onboarding_end_to_end_test,
}


async def _load_onboarding_progress(conn: asyncpg.Connection, tenant_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        'select onboarding_progress from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Tenant settings not found')
    return normalize_onboarding_progress(_coerce_jsonb(row['onboarding_progress']))
