"""Handlers extracted from routes.py for tenant_admin_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import asyncpg
import structlog
from fastapi import Depends, HTTPException, Query, Request, Response, status

from app.api.v1._helpers.knowledge_documents import (
    KNOWLEDGE_DOCUMENT_PROJECTION,
    KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS,
    normalize_knowledge_document,
    normalize_knowledge_documents,
)
from app.api.v1._helpers.knowledge_storage_config import (
    default_knowledge_storage_config,
    normalize_knowledge_storage_config,
    public_knowledge_storage_config,
)
from app.api.v1._helpers.knowledge_storage_db import fetch_tenant_knowledge_storage_config
from app.api.v1._helpers.normalizers import (
    _legal_row_to_dict,
    _normalize_messenger_channel,
    _normalize_web_channel,
    normalize_campaign,
    normalize_media_asset,
    normalize_promotion,
    normalize_qualification_question,
    normalize_segment_row,
    normalize_service_catalog_row,
)
from app.api.v1._helpers.campaigns_db import (
    _campaign_segment_filter_dict,
    _ensure_template_approved,
    _fetch_campaign_or_404,
)
from app.api.v1._helpers.auth_db import (
    _tenant_member_payload,
    _tenant_owner_count,
)
from app.api.v1._helpers.segments_db import _fetch_segment_or_404
from app.api.v1._helpers.onboarding import (
    ONBOARDING_STEP_METADATA,
    ONBOARDING_STEPS,
    _step_metadata,
)
from app.api.v1._helpers.onboarding_db import (
    ONBOARDING_VERIFIERS,
    _load_onboarding_progress,
)
from app.api.v1._helpers.parsing import (
    _coerce_jsonb,
    metadata_extracted_text,
    parse_json_object,
)
from app.api.v1._helpers.payments_db import _fetch_tenant_payment_settings
from app.api.v1._helpers.payments_pure import (
    _public_payment_settings,
)
from app.api.v1._helpers.platform_filters import _CONTACT_EXPORT_ALLOWED_KINDS
from app.api.v1._helpers.projections import (
    CAMPAIGN_PROJECTION,
    MEDIA_ASSET_COLUMNS,
    MESSENGER_CHANNEL_PROJECTION,
    PROMOTION_COLUMNS,
    QUALIFICATION_PROJECTION,
    SEGMENT_PROJECTION,
    SERVICE_CATALOG_PROJECTION,
    WEB_CHANNEL_PROJECTION,
)
from app.api.v1._helpers.secrets import (
    tenant_knowledge_s3_secret_ref,
    tenant_secret_ref,
    write_tenant_secret,
)
from app.api.v1._helpers.whatsapp_db import (
    _fetch_template_or_404,
    _resolve_channel_for_template,
)
from app.api.v1._helpers.whatsapp_pure import (
    WHATSAPP_TEMPLATE_PROJECTION,
    normalize_whatsapp_template,
    verify_token_hash,
)
from app.api.v1._helpers.widget import _build_widget_snippet
from app.api.v1._helpers.widget_proxy import tenant_brand_logo_proxy_url
from app.api.v1.routes import (
    _ensure_caller_can_target_role,
    build_tenant_readiness_report,
    current_user_id_from_request,
    ensure_tenant_access,
    ensure_tenant_role,
    tenant_admin_router,
    tenant_id_from_request,
    update_tenant_record,
)
from app.api.v1.schemas import (
    BranchCreate,
    BranchUpdate,
    CampaignCreate,
    CampaignLaunch,
    CampaignUpdate,
    ChannelCreate,
    ChannelModeUpdate,
    ContactPackageAssign,
    ContactPackagePatch,
    ContactSegmentCreate,
    ContactSegmentMembersAssign,
    ContactSegmentUpdate,
    ContactSubscriptionCreate,
    ContactSubscriptionPatch,
    ContactTagCreate,
    ContactTagUpdate,
    IntentEvaluateRequest,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeStorageUpdate,
    LegalDocumentDraftCreate,
    MediaAssetUpdate,
    MemberInvite,
    MemberRoleUpdate,
    MessengerChannelUpsert,
    PromotionCreate,
    PromotionUpdate,
    PromptCreate,
    QualificationQuestionCreate,
    QualificationQuestionUpdate,
    QualificationReorderRequest,
    RetentionPoliciesUpdate,
    ServiceCreate,
    ServiceReorderRequest,
    ServiceUpdate,
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
    TenantPaymentSettingsUpdate,
    TenantUpdate,
    TreatmentPackageCreate,
    TreatmentPackageUpdate,
    WebChannelUpsert,
    WhatsAppTemplateCreate,
    WhatsAppTemplateUpdate,
)
from app.core.config import get_settings
from app.core.export_signatures import sign_export_bundle
from app.core.security import (
    require_min_role,
)
from app.db.pool import db, get_db, record_to_dict
from app.services.audit import audit  # noqa: F811
from app.services.auth0_admin import (
    Auth0AmbiguousUserMatch,
    Auth0UserAlreadyExists,
    Auth0UserNotVerified,
    assign_roles as auth0_assign_roles,
    auth0_management_enabled,
    invite_user as auth0_invite_user,
    revoke_tenant_roles as auth0_revoke_tenant_roles,
)
from app.services.campaigns import (
    count_recipients as count_campaign_recipients,
    evaluate_segment,
    refresh_campaign_counters,
)
from app.services.maps import build_maps_url
from app.services.circuit_breaker import CircuitOpenError
from app.chatbot.intent_classifier import classify_intent
from app.services.knowledge_storage import (
    delete_knowledge_file,
    is_binary_extractable,
    normalize_object_prefix,
    store_knowledge_file,
)
from app.services.media_storage import (
    MEDIA_KINDS,
    delete_media_file,
    store_media_file,
)
from app.services.rag_indexing import build_indexing_result_async, vector_literal
from app.services.rag_retrieval import (
    ALL_VISIBILITY,
    END_USER_VISIBILITY,
    build_grounded_answer,
    rank_chunks,
    retrieval_match_to_dict,
)
from app.services.retention import (
    RETENTION_ENTITIES,
    preview_retention,
    validate_policy,
)
from app.services.segments import (
    count_segment_contacts,
    evaluate_segment_rules,
    normalize_applies_when,
    normalize_rules as normalize_segment_rules,
    snapshot_segment_members,
)
from app.services.web_widget import generate_widget_token
from app.services.whatsapp import (
    delete_template_from_meta,
    fetch_templates_from_meta,
    normalize_meta_app_secret,
    resolve_secret_ref,
    secret_ref_is_configured,
    submit_template_to_meta,
    token_ref_is_configured,
)

log = structlog.get_logger()


@tenant_admin_router.patch('/tenants/{tenant_id}')
async def patch_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await update_tenant_record(conn, tenant_id, payload)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.updated',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/members')
async def list_tenant_members(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select u.id as user_id, u.auth_subject, u.email, u.display_name,
               u.status, u.last_login_at, u.created_at,
               array_agg(utr.role order by
                   case utr.role
                       when 'owner' then 1
                       when 'admin' then 2
                       when 'manager' then 3
                       when 'agent' then 4
                       when 'viewer' then 5
                       else 6
                   end
               ) as roles,
               bool_or(utr.is_default) as is_default_role
        from app.user_tenant_roles utr
        join app.users u on u.id = utr.user_id
        where utr.tenant_id=$1
        group by u.id
        order by min(utr.created_at) asc
        """,
        tenant_id,
    )
    members = []
    for row in rows:
        record = record_to_dict(row)
        record['roles'] = list(record.get('roles') or [])
        members.append(record)
    return {
        'members': members,
        'auth0_management_enabled': auth0_management_enabled(),
    }


@tenant_admin_router.post(
    '/tenants/{tenant_id}/members', status_code=status.HTTP_201_CREATED
)
async def invite_tenant_member(
    tenant_id: UUID,
    payload: MemberInvite,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _ensure_caller_can_target_role(request, conn, tenant_id, payload.role)

    email = payload.email.strip().lower()
    if '@' not in email:
        raise HTTPException(status_code=422, detail='A valid email is required')

    existing = await conn.fetchrow(
        'select id, auth_subject from app.users where email=$1', email
    )

    if existing:
        user_id = existing['id']
        auth_subject = existing['auth_subject']
        # Refresh display_name when provided.
        if payload.display_name:
            await conn.execute(
                'update app.users set display_name=$2, updated_at=now() where id=$1',
                user_id,
                payload.display_name,
            )
    else:
        # No Auth0 subject yet — use a stable placeholder so the schema's
        # NOT NULL/UNIQUE constraints on auth_subject are satisfied.
        pending_subject = f'pending|{uuid5(NAMESPACE_URL, email).hex}'
        row = await conn.fetchrow(
            """
            insert into app.users (auth_subject, email, display_name, status)
            values ($1, $2, $3, 'invited')
            returning id, auth_subject
            """,
            pending_subject,
            email,
            payload.display_name or email.split('@', 1)[0],
        )
        user_id = row['id']
        auth_subject = row['auth_subject']

    already_member = await conn.fetchval(
        'select 1 from app.user_tenant_roles where user_id=$1 and tenant_id=$2 limit 1',
        user_id,
        tenant_id,
    )
    if already_member:
        raise HTTPException(
            status_code=409,
            detail='This user already belongs to the tenant; update their role instead.',
        )

    is_default = not bool(
        await conn.fetchval(
            'select 1 from app.user_tenant_roles where user_id=$1 limit 1', user_id
        )
    )
    await conn.execute(
        """
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, $3, $4)
        on conflict (user_id, tenant_id, role) do update set is_default=excluded.is_default
        """,
        user_id,
        tenant_id,
        payload.role,
        is_default,
    )

    auth0_result: dict[str, Any] = {'disabled': True}
    if not existing or (auth_subject and auth_subject.startswith('pending|')):
        # New user en NUESTRA DB — invite_user crea o reutiliza la cuenta
        # Auth0 (BUG-013):
        #   - Email NO existe en Auth0: crea cuenta nueva + emite ticket
        #     password-change (TASK-0085 / BUG06) → Auth0 manda email de
        #     bienvenida.
        #   - Email YA existe (caso central SaaS multi-tenant: agente que
        #     trabaja para varias empresas): lookup por email, reutiliza
        #     user_id, attachea rol al nuevo tenant. NO emite ticket — el
        #     user ya tiene credenciales. invite_user devuelve
        #     `reused_existing=True` para que el frontend muestre UX
        #     apropiada (agregado vs. invitado).
        # invite_user solo raisea Auth0UserAlreadyExists cuando incluso el
        # lookup falla (Auth0 retorna [] o 5xx) — caso operativo real.
        try:
            auth0_result = await auth0_invite_user(
                email=email,
                role=payload.role,
                tenant_id=tenant_id,
                display_name=payload.display_name,
            )
        except CircuitOpenError as exc:
            # AUDIT-49 / re-audit §1.4 (2026-05-18): Auth0 breaker está abierto
            # — devolver 503 + Retry-After en vez de degradar a 2xx con `error`
            # en body, que ocultaba el incidente. El frontend del panel debe
            # mostrar "Auth0 temporalmente indisponible, reintentar en Ns".
            raise HTTPException(
                status_code=503,
                detail='Auth0 Management API temporarily unavailable',
                headers={'Retry-After': str(max(1, int(round(exc.retry_after_seconds))))},
            ) from exc
        except Auth0UserAlreadyExists:
            raise HTTPException(
                status_code=409,
                detail='Auth0 reportó que el email ya existe pero el lookup '
                'subsecuente no pudo localizarlo. Revisar el dashboard Auth0 '
                '(posible duplicado en otra connection) o reintentar.',
            )
        except Auth0AmbiguousUserMatch as exc:
            # BUG-193 (codex HIGH): Auth0 devolvió >1 user con el mismo email
            # (multiple connections: database + Google OAuth + LinkedIn, etc.).
            # Fail-closed: el operador debe desambiguar en el dashboard antes
            # de poder invitar — sino podemos terminar bindeando el tenant role
            # a la identidad equivocada.
            raise HTTPException(
                status_code=409,
                detail=(
                    'Auth0 tiene múltiples cuentas para este email en '
                    'diferentes connections. Desambiguá en el dashboard Auth0 '
                    '(borrá duplicados o reasigná manualmente) antes de '
                    f'reintentar el invite. Detalle: {exc}'
                ),
            )
        except Auth0UserNotVerified as exc:
            # BUG-193 (codex HIGH): la cuenta Auth0 existente NO tiene
            # email_verified=true. No es seguro bindear el tenant role —
            # podría ser una cuenta que un atacante registró antes que la
            # víctima active su email. Fail-closed: el operador debe verificar
            # primero (resend verification email desde Auth0 dashboard).
            raise HTTPException(
                status_code=403,
                detail=(
                    'La cuenta Auth0 asociada a este email NO está verificada. '
                    'Por seguridad no se asigna el rol a una identidad sin '
                    'verificar — pedile a la persona que confirme el email '
                    f'antes de reintentar el invite. Detalle: {exc}'
                ),
            )
        except Exception as exc:  # noqa: BLE001 - log and continue without Auth0
            log.warning('tenant_member.auth0_invite_failed', error=str(exc))
            auth0_result = {'disabled': False, 'error': str(exc)}
        else:
            # On success, bind the real Auth0 user_id into our users row so
            # future role syncs go through assign_roles, not invite again.
            new_auth_subject = auth0_result.get('auth0_user_id') if isinstance(auth0_result, dict) else None
            if new_auth_subject:
                await conn.execute(
                    "update app.users set auth_subject=$2, updated_at=now() where id=$1",
                    user_id,
                    new_auth_subject,
                )
                auth_subject = new_auth_subject
    else:
        # Existing Auth0 user — keep their tenant_roles claim in sync.
        try:
            roles_payload = await conn.fetch(
                """
                select utr.tenant_id::text as tenant_id, utr.role
                from app.user_tenant_roles utr
                where utr.user_id=$1
                """,
                user_id,
            )
            roles_list = [
                {'tenant_id': r['tenant_id'], 'role': r['role']} for r in roles_payload
            ]
            auth0_result = await auth0_assign_roles(
                auth_subject=auth_subject, roles=roles_list
            )
        except CircuitOpenError as exc:
            # AUDIT-49: ver invite — fail-loud con 503 + Retry-After.
            raise HTTPException(
                status_code=503,
                detail='Auth0 Management API temporarily unavailable',
                headers={'Retry-After': str(max(1, int(round(exc.retry_after_seconds))))},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            log.warning('tenant_member.auth0_assign_failed', error=str(exc))
            auth0_result = {'disabled': False, 'error': str(exc)}

    # TASK-0085 / BUG06: audit captures the Auth0 user_id (when known), not
    # the raw email — the email value is sensitive PII and the user_id is the
    # canonical reference for downstream account forensics. Email is reduced
    # to the local-part hash for correlation without leaking the full address.
    import hashlib as _hashlib  # noqa: PLC0415
    audit_metadata: dict[str, Any] = {
        'role': payload.role,
        'auth0_user_id': auth_subject if auth_subject and not auth_subject.startswith('pending|') else None,
        'email_fingerprint': _hashlib.sha256(email.encode('utf-8')).hexdigest()[:16],
    }
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.invited',
        entity_type='user',
        entity_id=str(user_id),
        metadata=audit_metadata,
    )

    member = await _tenant_member_payload(conn, tenant_id, user_id)
    # TASK-0085 / BUG06: the API response carries only auth0_user_id /
    # invited / error flags; the ticket URL is never propagated to the
    # caller — the invitee receives it via Auth0's email template.
    safe_auth0 = {
        'disabled': bool(auth0_result.get('disabled')),
        'invited': bool(auth0_result.get('invited')),
        'auth0_user_id': auth0_result.get('auth0_user_id'),
        # BUG-013: flag para que el frontend muestre "Agregado al tenant"
        # (con texto explicando que el user ya tenía cuenta y NO se le mandó
        # email) en lugar de "Invitación enviada".
        'reused_existing': bool(auth0_result.get('reused_existing')),
    }
    if auth0_result.get('error'):
        safe_auth0['error'] = auth0_result['error']
    if auth0_result.get('synced'):
        safe_auth0['synced'] = True
    # BUG-069: incluir `propagation_errors` cuando `invite_user` los reporta.
    # Antes el dict los devolvía pero `safe_auth0` solo copiaba 5 keys y los
    # propagation_errors quedaban invisibles a la UI — el operador no podía
    # saber que el invite se completó pero el role assignment falló (caso
    # típico cuando el tenant Auth0 no tiene el rol creado). Ahora el frontend
    # puede mostrar un warning en el modal de invitación.
    if auth0_result.get('propagation_errors'):
        safe_auth0['propagation_errors'] = list(auth0_result['propagation_errors'])
    member['auth0'] = safe_auth0
    member['auth0_skipped'] = bool(auth0_result.get('disabled'))
    return member


@tenant_admin_router.patch('/tenants/{tenant_id}/members/{user_id}')
async def update_tenant_member_role(
    tenant_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    user_row = await conn.fetchrow(
        'select id, auth_subject from app.users where id=$1', user_id
    )
    if not user_row:
        raise HTTPException(status_code=404, detail='User not found')

    current_role_row = await conn.fetchrow(
        """
        select role
        from app.user_tenant_roles
        where user_id=$1 and tenant_id=$2
        order by case role
            when 'owner' then 1
            when 'admin' then 2
            when 'manager' then 3
            when 'agent' then 4
            when 'viewer' then 5
            else 6
        end
        limit 1
        """,
        user_id,
        tenant_id,
    )
    if not current_role_row:
        raise HTTPException(status_code=404, detail='Member not found in tenant')
    previous_role = current_role_row['role']
    if previous_role == payload.role:
        member = await _tenant_member_payload(conn, tenant_id, user_id)
        member['auth0'] = {'disabled': not auth0_management_enabled(), 'skipped': 'no_change'}
        return member

    await _ensure_caller_can_target_role(request, conn, tenant_id, payload.role)
    await _ensure_caller_can_target_role(request, conn, tenant_id, previous_role)

    if previous_role == 'owner' and payload.role != 'owner':
        owner_count = await _tenant_owner_count(conn, tenant_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=409,
                detail='Cannot demote the last owner of the tenant. Promote another user to owner first.',
            )

    async with conn.transaction():
        await conn.execute(
            'delete from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
            user_id,
            tenant_id,
        )
        await conn.execute(
            """
            insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
            values ($1, $2, $3, true)
            on conflict (user_id, tenant_id, role) do update set is_default=true
            """,
            user_id,
            tenant_id,
            payload.role,
        )

    # Sync the user's tenant_roles claim list in Auth0 user_metadata.
    auth0_result: dict[str, Any] = {'disabled': True}
    try:
        roles_payload = await conn.fetch(
            """
            select utr.tenant_id::text as tenant_id, utr.role
            from app.user_tenant_roles utr
            where utr.user_id=$1
            """,
            user_id,
        )
        roles_list = [
            {'tenant_id': r['tenant_id'], 'role': r['role']} for r in roles_payload
        ]
        auth0_result = await auth0_assign_roles(
            auth_subject=user_row['auth_subject'], roles=roles_list
        )
    except CircuitOpenError as exc:
        # AUDIT-49: ver invite — fail-loud con 503 + Retry-After.
        raise HTTPException(
            status_code=503,
            detail='Auth0 Management API temporarily unavailable',
            headers={'Retry-After': str(max(1, int(round(exc.retry_after_seconds))))},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning('tenant_member.auth0_assign_failed', error=str(exc))
        auth0_result = {'disabled': False, 'error': str(exc)}

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.role_updated',
        entity_type='user',
        entity_id=str(user_id),
        metadata={'previous_role': previous_role, 'new_role': payload.role},
    )

    member = await _tenant_member_payload(conn, tenant_id, user_id)
    member['auth0'] = auth0_result
    return member


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/members/{user_id}', status_code=status.HTTP_204_NO_CONTENT
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    user_row = await conn.fetchrow(
        'select id, auth_subject from app.users where id=$1', user_id
    )
    if not user_row:
        raise HTTPException(status_code=404, detail='User not found')

    role_rows = await conn.fetch(
        'select role from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
        user_id,
        tenant_id,
    )
    if not role_rows:
        raise HTTPException(status_code=404, detail='Member not found in tenant')
    member_roles = [row['role'] for row in role_rows]

    if 'owner' in member_roles:
        await _ensure_caller_can_target_role(request, conn, tenant_id, 'owner')
        owner_count = await _tenant_owner_count(conn, tenant_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=409,
                detail='Cannot remove the last owner of the tenant.',
            )

    await conn.execute(
        'delete from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
        user_id,
        tenant_id,
    )

    try:
        await auth0_revoke_tenant_roles(
            auth_subject=user_row['auth_subject'], tenant_id=tenant_id
        )
    except CircuitOpenError as exc:
        # AUDIT-49 / re-audit §1.4: la fila de `user_tenant_roles` ya fue
        # eliminada (línea 2680) — el JWT viejo del user sigue con `tenant_id`
        # en el claim hasta que expire, pero el DB-check (`ensure_tenant_access`)
        # ya rechazará todo request (no hay row). Surfacear 503 + Retry-After
        # para que el panel auto-reintente la sincronización Auth0; la operación
        # es idempotente (DB delete = no-op si ya está, Auth0 revoke también).
        log.error(
            'tenant_member.auth0_revoke_circuit_open',
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            retry_after=exc.retry_after_seconds,
            hint='DB-side membership revoked; Auth0 metadata sync deferred',
        )
        raise HTTPException(
            status_code=503,
            detail=(
                'Membership revoked in our database; Auth0 metadata sync '
                'temporarily unavailable. Retry to complete propagation.'
            ),
            headers={'Retry-After': str(max(1, int(round(exc.retry_after_seconds))))},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning('tenant_member.auth0_revoke_failed', error=str(exc))

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.removed',
        entity_type='user',
        entity_id=str(user_id),
        metadata={'previous_roles': member_roles},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tenant_admin_router.get('/tenants/{tenant_id}/settings')
async def get_tenant_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Settings not found')
    return record_to_dict(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/settings')
async def patch_settings(tenant_id: UUID, payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    allowed = {
        k: payload[k]
        for k in (
            'locale', 'business_hours', 'escalation_policy', 'pii_policy',
            'no_train', 'notification_settings', 'bot_personality',
            'brand_logo_url',
        )
        if k in payload
    }
    # AUDIT-51 / round-3 §1.3 (2026-05-18): validar tipo de `no_train` antes
    # de aceptar el patch. asyncpg coercione algunos truthy non-bool (1,
    # "true") en columna boolean, pero la coerción depende de driver/version
    # y queremos input estricto en el endpoint admin para trazabilidad clara
    # en el audit log de §1.2 abajo.
    if 'no_train' in allowed and not isinstance(allowed['no_train'], bool):
        raise HTTPException(
            status_code=422,
            detail='no_train must be a boolean (true/false)',
        )
    # UI-012-FU: validate brand_logo_url shape/length up front. Empty string
    # clears the logo (-> null) so the admin UI can offer a "Quitar logo"
    # action without a dedicated DELETE endpoint.
    if 'brand_logo_url' in allowed:
        raw_logo = allowed['brand_logo_url']
        if raw_logo is not None:
            if not isinstance(raw_logo, str):
                raise HTTPException(
                    status_code=422,
                    detail='brand_logo_url must be a string or null',
                )
            stripped_logo = raw_logo.strip()
            if len(stripped_logo) > 1024:
                raise HTTPException(
                    status_code=422,
                    detail='brand_logo_url must be at most 1024 chars',
                )
            allowed['brand_logo_url'] = stripped_logo or None
    current = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail='Settings not found')
    merged = dict(current)
    merged.update(allowed)

    # Normalize jsonb fields: accept both raw dicts and JSON strings from clients
    for jsonb_key in ('business_hours', 'escalation_policy', 'pii_policy', 'notification_settings', 'bot_personality'):
        merged[jsonb_key] = _coerce_jsonb(merged.get(jsonb_key)) or {}

    # TASK-0079: validate the webhook URL inside notification_settings BEFORE
    # persisting. The webhook is invoked from the alerts worker with a HMAC
    # signature; accepting an unvalidated URL allows SSRF + secret leak.
    notification_settings_value = merged.get('notification_settings') or {}
    if isinstance(notification_settings_value, dict):
        channels_value = notification_settings_value.get('complaint_alert_channels')
        if channels_value is not None:
            from app.services.operator_alerts import normalize_alert_channels  # noqa: PLC0415
            from app.services.url_guard import UnsafeOutboundURLError  # noqa: PLC0415
            try:
                normalized_channels = normalize_alert_channels(channels_value, strict=True)
            except UnsafeOutboundURLError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f'complaint_alert_channels.webhook_url rejected: {exc}',
                )
            notification_settings_value['complaint_alert_channels'] = normalized_channels
            merged['notification_settings'] = notification_settings_value

    # TASK-0071: sanea la personalidad antes de persistir (rechaza valores fuera de catálogo).
    from app.services.conversation_flow import _normalize_personality as _normalize_bot_personality  # noqa: PLC0415
    merged['bot_personality'] = _normalize_bot_personality(merged['bot_personality'])

    row = await conn.fetchrow(
        """
        update app.tenant_settings
        set locale=$2, business_hours=$3::jsonb, escalation_policy=$4::jsonb, pii_policy=$5::jsonb,
            no_train=$6, notification_settings=$7::jsonb, bot_personality=$8::jsonb,
            brand_logo_url=$9
        where tenant_id=$1 returning *
        """,
        tenant_id,
        merged['locale'],
        json.dumps(merged['business_hours']),
        json.dumps(merged['escalation_policy']),
        json.dumps(merged['pii_policy']),
        merged['no_train'],
        json.dumps(merged['notification_settings']),
        json.dumps(merged['bot_personality']),
        merged.get('brand_logo_url'),
    )
    # AUDIT-51 / round-3 §1.2 (2026-05-18): incluir metadata del diff en el
    # audit log para trazabilidad GDPR. Antes el log decía solo "settings
    # updated" sin valor anterior/nuevo — un admin podía flippear `no_train`
    # (apertura a procesamiento cloud) sin que el audit explicara qué cambió.
    # Capturamos las keys realmente modificadas + viejo/nuevo para los flags
    # privacy-sensitive. NO dumpeamos `notification_settings` completo
    # (puede contener URLs con secrets en query params) — solo bool diffs +
    # whitelist de keys de bajo riesgo.
    audit_meta: dict[str, object] = {}
    changed_keys: list[str] = []
    privacy_sensitive_keys = ('no_train', 'pii_policy', 'escalation_policy', 'locale')
    for key in allowed:
        old_val = current[key] if key in current else None
        new_val = row[key] if key in row else None
        if old_val != new_val:
            changed_keys.append(key)
            if key in privacy_sensitive_keys:
                # Solo para keys privacy-sensitive, capturar valor previo+nuevo.
                # AUDIT-51 round-3 §1.2 bugfix (HTTP E2E exposed it):
                # asyncpg returns jsonb columns as str (the JSON-encoded text),
                # not dict. The original `isinstance(old_val, str)` branch
                # therefore INLINED the raw JSON for `pii_policy` /
                # `escalation_policy` / `notification_settings` — leaking the
                # exact privacy policy + webhook URLs (which may contain
                # secrets) into the audit table.
                #
                # Fix: keys known to be jsonb ALWAYS get hashed regardless of
                # the runtime Python type. The whitelist of jsonb-known keys
                # mirrors the SET clause of the UPDATE below.
                JSONB_KEYS = {
                    'pii_policy', 'escalation_policy', 'notification_settings',
                    'business_hours', 'bot_personality',
                }
                if key in JSONB_KEYS:
                    import hashlib as _h  # noqa: PLC0415
                    old_hash = _h.sha256(
                        json.dumps(old_val, sort_keys=True, default=str).encode()
                    ).hexdigest()[:12]
                    new_hash = _h.sha256(
                        json.dumps(new_val, sort_keys=True, default=str).encode()
                    ).hexdigest()[:12]
                    audit_meta[f'{key}_previous_hash'] = old_hash
                    audit_meta[f'{key}_new_hash'] = new_hash
                elif isinstance(old_val, (bool, str, int, float, type(None))):
                    audit_meta[f'{key}_previous'] = old_val
                    audit_meta[f'{key}_new'] = new_val
                else:
                    # Fallback (defensive): hash anything unexpected.
                    import hashlib as _h  # noqa: PLC0415
                    audit_meta[f'{key}_previous_hash'] = _h.sha256(
                        json.dumps(old_val, sort_keys=True, default=str).encode()
                    ).hexdigest()[:12]
                    audit_meta[f'{key}_new_hash'] = _h.sha256(
                        json.dumps(new_val, sort_keys=True, default=str).encode()
                    ).hexdigest()[:12]
    audit_meta['changed_keys'] = changed_keys
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_settings.updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata=audit_meta,
    )
    return record_to_dict(row)


@tenant_admin_router.post('/tenants/{tenant_id}/branding/logo')
async def upload_tenant_brand_logo(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """UI-012-FU: upload a tenant brand logo.

    Reuses ``store_media_file`` (kind=``image``) so the MIME allowlist
    (``image/png``, ``image/jpeg``, ``image/webp``) and the 5 MB size cap
    apply uniformly with the rest of the media library. SVG is
    intentionally excluded from the allowlist so we do not need a
    sanitizer (``defusedxml`` or similar) — PNG/JPEG/WEBP cover the
    branding use case.

    The uploaded file lands in ``app.media_assets`` (for reuse and
    deletability) and the resulting public ``source_uri`` is written
    into ``app.tenant_settings.brand_logo_url`` so the admin shell picks
    it up on the next request without extra plumbing.
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500,
            detail='python-multipart dependency is required for file uploads',
        ) from exc

    file = form.get('file')
    if not file or not hasattr(file, 'read'):
        raise HTTPException(status_code=422, detail='file is required')

    data = await file.read()
    filename = getattr(file, 'filename', None) or 'logo.bin'
    mime_type = getattr(file, 'content_type', None)
    asset_id = uuid4()
    settings = get_settings()

    try:
        stored = store_media_file(
            data=data,
            tenant_id=str(tenant_id),
            asset_id=str(asset_id),
            kind='image',  # MEDIA_MIME_ALLOWLIST['image'] = png/jpeg/webp
            filename=filename,
            mime_type=mime_type,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploader_id = await current_user_id_from_request(request, conn)

    await conn.execute(
        """
        insert into app.media_assets (
          id, tenant_id, kind, label, description,
          storage_backend, storage_bucket, object_key, source_uri,
          mime_type, sha256, size_bytes, tags, uploaded_by_user_id
        )
        values ($1, $2, 'image', $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::text[], $13)
        """,
        asset_id,
        tenant_id,
        f'Logo del tenant ({filename})',
        'Logo de marca del tenant — UI-012-FU',
        stored.storage_backend,
        stored.bucket,
        stored.object_key,
        stored.source_uri,
        stored.mime_type,
        stored.sha256,
        stored.size_bytes,
        ['branding', 'logo'],
        uploader_id,
    )

    # BUG-096: persistir la URL del proxy HTTP (no `stored.source_uri`,
    # que es `file://`/`s3://` y el browser no puede renderizar como
    # `<img src>`). El proxy vive en `tenant_ops_router` y sirve las
    # bytes con el mime_type del asset; cualquier miembro del tenant
    # (agent+ por ahora) puede leer el logo del chrome.
    new_url = tenant_brand_logo_proxy_url(tenant_id, asset_id)
    row = await conn.fetchrow(
        'update app.tenant_settings set brand_logo_url=$1 where tenant_id=$2 returning *',
        new_url,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Settings not found')

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_settings.branding_updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={
            'asset_id': str(asset_id),
            'size_bytes': stored.size_bytes,
            'mime_type': stored.mime_type,
        },
    )

    return record_to_dict(row)


@tenant_admin_router.post('/tenants/{tenant_id}/go-live')
async def mark_tenant_go_live(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """UI-016.1-FU: mark a tenant as live in production.

    Owner-only operation that captures the moment the tenant transitions
    from trial / pre-launch into production. Validates the readiness
    checklist first (re-uses ``build_tenant_readiness_report``) and
    rejects with 409 if any check is still pending. Idempotent: if
    ``tenant_settings.go_live_at`` is already set, the timestamp is
    preserved and no new audit event is emitted, so re-clicking "Marcar
    live" cannot silently overwrite the original moment of truth.

    Security primitives:
      - ``authenticate_request`` (router level) + ``require_min_role('admin')``
        (router level) + explicit ``require_min_role('owner')`` below to
        escalate above admin/manager. The ``require_mfa_for_privileged``
        guard is also inherited from the router.
      - ``ensure_tenant_access`` confirms the JWT subject can act on
        this specific tenant.
      - ``set_config('app.tenant_id')`` so RLS scopes every subsequent
        statement.
      - ``audit('tenant.go_live_marked')`` with a snapshot of the
        readiness checks at the moment of marking, plus the optional
        free-text ``reason`` from the request body.
    """
    # BUG-200 (codex HIGH): go-live es una transición de lifecycle que solo
    # el business owner del tenant target debe poder ejecutar. La combinación
    # `require_min_role('owner')` + `ensure_tenant_access` permitía que un
    # `platform_owner` (rank > owner) o un user con cookie de support_mode
    # disparara el go-live sin ser tenant-owner — la UI explícitamente NO le
    # da la capability `go_live_readiness.mark_live` a esos roles
    # (admin-panel/src/permissions/matrix.js). Aquí cerramos el bypass
    # backend: exigimos que el actor tenga un row con role='owner' en
    # `app.user_tenant_roles` para este tenant_id puntual,
    # independientemente de support_mode o platform_owner.
    await require_min_role('owner')(request)
    await ensure_tenant_access(request, tenant_id, conn)
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    is_db_owner = await conn.fetchval(
        """
        select 1
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject = $1
          and utr.tenant_id = $2
          and utr.role = 'owner'
        limit 1
        """,
        actor_id,
        tenant_id,
    )
    if not is_db_owner:
        raise HTTPException(
            status_code=403,
            detail=(
                'go-live requires DB role `owner` for this tenant '
                '(platform_owner / support_mode bypass is not honored here).'
            ),
        )
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # Validate readiness before flipping the flag.
    report = await build_tenant_readiness_report(conn, tenant_id)
    if report.get('status') != 'ready':
        raise HTTPException(
            status_code=409,
            detail={
                'message': 'Tenant not ready for go-live',
                'reasons': report.get('reasons', []),
                'checks': report.get('checks', []),
            },
        )

    # Idempotent write — preserve the original go_live_at if already set.
    current = await conn.fetchrow(
        'select go_live_at from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    if current is None:
        raise HTTPException(status_code=404, detail='Tenant settings not found')

    # Body is optional ({reason}). Reading it manually so the endpoint
    # accepts both `{}` and a fully omitted body (the frontend confirm
    # flow does not always collect a reason).
    payload: dict | None = None
    try:
        body_bytes = await request.body()
        if body_bytes:
            payload = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail='Invalid JSON body') from exc

    reason: str | None = None
    if isinstance(payload, dict):
        raw_reason = payload.get('reason')
        if raw_reason is not None and not isinstance(raw_reason, str):
            raise HTTPException(status_code=422, detail='reason must be a string')
        reason = (raw_reason or '').strip() or None

    if current['go_live_at'] is None:
        await conn.execute(
            'update app.tenant_settings set go_live_at = now(), updated_at = now() where tenant_id=$1',
            tenant_id,
        )
        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='tenant.go_live_marked',
            entity_type='tenant',
            entity_id=str(tenant_id),
            metadata={
                'reason': reason,
                'readiness_snapshot': {
                    'status': report.get('status'),
                    'checks': report.get('checks', []),
                },
            },
        )

    # Refresh the report so the frontend re-renders with go_live_at populated.
    refreshed = await build_tenant_readiness_report(conn, tenant_id)
    return refreshed


@tenant_admin_router.get('/tenants/{tenant_id}/retention/policies')
async def list_retention_policies(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select entity, retention_days, anonymize_instead_of_delete, updated_at
        from app.data_retention_policies
        where tenant_id=$1
        order by entity
        """,
        tenant_id,
    )
    return {
        'tenant_id': str(tenant_id),
        'entities': list(RETENTION_ENTITIES),
        'policies': [record_to_dict(row) for row in rows],
    }


@tenant_admin_router.put('/tenants/{tenant_id}/retention/policies')
async def put_retention_policies(
    tenant_id: UUID,
    payload: RetentionPoliciesUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await ensure_tenant_role(request, conn, tenant_id, 'admin')
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    for entry in payload.policies:
        try:
            validate_policy(entry.entity, entry.retention_days, entry.anonymize_instead_of_delete)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    async with conn.transaction():
        for entry in payload.policies:
            await conn.execute(
                """
                insert into app.data_retention_policies
                  (tenant_id, entity, retention_days, anonymize_instead_of_delete)
                values ($1, $2, $3, $4)
                on conflict (tenant_id, entity) do update
                set retention_days = excluded.retention_days,
                    anonymize_instead_of_delete = excluded.anonymize_instead_of_delete
                """,
                tenant_id,
                entry.entity,
                entry.retention_days,
                entry.anonymize_instead_of_delete,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='retention.policies_updated',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
    return await list_retention_policies(tenant_id, request, conn)


@tenant_admin_router.get('/tenants/{tenant_id}/retention/preview')
async def get_retention_preview(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    return {
        'tenant_id': str(tenant_id),
        'preview': await preview_retention(conn, tenant_id),
    }


@tenant_admin_router.get('/tenants/{tenant_id}/knowledge/storage')
async def get_knowledge_storage_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    return public_knowledge_storage_config(tenant_id, config)


@tenant_admin_router.patch('/tenants/{tenant_id}/knowledge/storage')
async def patch_knowledge_storage_settings(
    tenant_id: UUID,
    payload: KnowledgeStorageUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    incoming = payload.model_dump(exclude_unset=True)
    secret_access_key = incoming.pop('secret_access_key', None)
    if 'prefix' in incoming and incoming['prefix'] is not None:
        try:
            incoming['prefix'] = normalize_object_prefix(incoming['prefix'], str(tenant_id))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail='Invalid knowledge storage prefix',
            )
    next_config = {**current, **incoming}
    next_config = normalize_knowledge_storage_config(tenant_id, next_config)

    if next_config['backend'] == 's3':
        if not next_config.get('bucket'):
            raise HTTPException(status_code=400, detail='S3 bucket is required for tenant knowledge storage')
        # TASK-0079 / BUG18: validate the tenant-supplied endpoint_url BEFORE
        # persisting. The validator enforces HTTPS, an AWS/MinIO allowlist, and
        # blocks loopback / RFC1918 / metadata hosts. Local dev mode (APP_ENV
        # in {'local','test'}) is the only context where MinIO HTTP is allowed.
        if next_config.get('endpoint_url'):
            from app.services.url_guard import (  # noqa: PLC0415
                S3_ENDPOINT_HOST_ALLOWLIST,
                UnsafeOutboundURLError,
                validate_outbound_url,
            )
            try:
                validate_outbound_url(
                    next_config['endpoint_url'],
                    allowed_schemes=('https',),
                    host_allowlist=S3_ENDPOINT_HOST_ALLOWLIST,
                    allow_http_for_local_dev=True,
                )
            except UnsafeOutboundURLError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f'S3 endpoint_url rejected: {exc}',
                )
            # When the tenant points to a custom endpoint, tenant credentials
            # are mandatory — we never sign against an attacker-supplied host
            # with platform-wide access keys.
            has_tenant_creds = bool(
                next_config.get('access_key_id')
                and (secret_access_key or secret_ref_is_configured(next_config.get('secret_ref')))
            )
            if not has_tenant_creds:
                raise HTTPException(
                    status_code=422,
                    detail='Tenant S3 endpoint_url requires tenant-supplied '
                           'access_key_id + secret_access_key (no fallback to '
                           'platform credentials).',
                )
        if secret_access_key and not next_config.get('access_key_id'):
            raise HTTPException(
                status_code=400,
                detail='S3 access_key_id is required when configuring a tenant secret access key',
            )
        if secret_access_key:
            secret_ref = tenant_knowledge_s3_secret_ref(tenant_id)
            write_tenant_secret(secret_ref, secret_access_key)
            next_config['secret_ref'] = secret_ref
        elif next_config.get('access_key_id') and not secret_ref_is_configured(next_config.get('secret_ref')):
            raise HTTPException(
                status_code=400,
                detail='S3 secret access key is required the first time access_key_id is configured',
            )
    else:
        next_config = default_knowledge_storage_config(tenant_id)

    row = await conn.fetchrow(
        """
        update app.tenant_settings
        set knowledge_storage=$2::jsonb
        where tenant_id=$1
        returning knowledge_storage
        """,
        tenant_id,
        json.dumps(next_config),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Settings not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_knowledge_storage.updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={
            'backend': next_config.get('backend'),
            'bucket': next_config.get('bucket'),
            'prefix': next_config.get('prefix'),
            'secret_configured': secret_ref_is_configured(next_config.get('secret_ref')),
        },
    )
    return public_knowledge_storage_config(tenant_id, next_config)


@tenant_admin_router.post('/tenants/{tenant_id}/channels/whatsapp', status_code=201)
async def create_channel(tenant_id: UUID, payload: ChannelCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # TASK-0081 / BUG21: a Meta phone_number_id can only be bound to one
    # active tenant channel at a time. If another tenant already claimed it,
    # refuse with 409 before any secret is written. The unique partial index
    # in 01-schema.sql is the final guarantee; this check produces a clean
    # business error instead of a SQL integrity violation.
    if payload.phone_number_id:
        await conn.execute("select set_config('app.support_mode', 'true', true)")
        existing = await conn.fetchrow(
            """
            select tenant_id, status
            from app.tenant_channels
            where phone_number_id=$1
              and provider='whatsapp_cloud_api'
              and status='active'
              and tenant_id <> $2
            """,
            payload.phone_number_id,
            tenant_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail='phone_number_id is already bound to another active tenant channel',
            )
        # Restore the per-tenant scope so the upsert below runs under RLS.
        await conn.execute("select set_config('app.support_mode', 'false', true)")
        await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    token_ref = tenant_secret_ref(tenant_id, 'meta_access_token')
    app_secret_ref = tenant_secret_ref(tenant_id, 'whatsapp_app_secret')
    verify_token_ref = tenant_secret_ref(tenant_id, 'whatsapp_verify_token')

    if payload.meta_access_token:
        write_tenant_secret(token_ref, payload.meta_access_token)
    elif not token_ref_is_configured(token_ref):
        raise HTTPException(
            status_code=400,
            detail='Meta access token is required for this tenant secret',
        )

    if payload.app_secret:
        write_tenant_secret(app_secret_ref, normalize_meta_app_secret(payload.app_secret) or payload.app_secret)
    elif not secret_ref_is_configured(app_secret_ref):
        raise HTTPException(
            status_code=400,
            detail='WhatsApp app secret is required for this tenant secret',
        )

    if payload.verify_token:
        write_tenant_secret(verify_token_ref, payload.verify_token)
    elif not secret_ref_is_configured(verify_token_ref):
        raise HTTPException(
            status_code=400,
            detail='WhatsApp verify token is required for this tenant secret',
        )

    verify_token = resolve_secret_ref(verify_token_ref)

    row = await conn.fetchrow(
        """
        insert into app.tenant_channels (
          tenant_id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref,
          verify_token_hash, account_mode, status
        )
        values ($1, 'whatsapp_cloud_api', $2, $3, $4, $5, $6, $7, $8, 'active')
        on conflict (tenant_id, provider) do update set
          business_id=excluded.business_id, waba_id=excluded.waba_id, phone_number_id=excluded.phone_number_id,
          token_ref=excluded.token_ref, app_secret_ref=excluded.app_secret_ref,
          verify_token_hash=excluded.verify_token_hash,
          account_mode=excluded.account_mode, status='active'
        returning *
        """,
        tenant_id,
        payload.business_id,
        payload.waba_id,
        payload.phone_number_id,
        token_ref,
        app_secret_ref,
        verify_token_hash(verify_token) if verify_token else None,
        payload.account_mode,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='channel.upserted', entity_type='tenant_channel', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/channels/whatsapp/health')
async def channel_health(tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        select id, tenant_id, provider, business_id, waba_id, phone_number_id, token_ref,
               app_secret_ref, verify_token_hash, quality_rating, messaging_limit_tier, account_mode, status,
               created_at, updated_at
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    channel = record_to_dict(row)
    delivery_mode = channel.get('account_mode') or 'mock'
    token_ready = token_ref_is_configured(channel.get('token_ref'))
    app_secret_ready = secret_ref_is_configured(channel.get('app_secret_ref'))
    verify_token_ready = secret_ref_is_configured(tenant_secret_ref(channel['tenant_id'], 'whatsapp_verify_token'))
    delivery_ready = delivery_mode != 'live' or token_ready
    checks = {
        'business_id': bool(channel.get('business_id')),
        'waba_id': bool(channel.get('waba_id')),
        'phone_number_id': bool(channel.get('phone_number_id')),
        'token_ref': bool(channel.get('token_ref')),
        'app_secret_ref': bool(channel.get('app_secret_ref')),
        'app_secret_configured': app_secret_ready,
        'verify_token_configured': verify_token_ready,
        'channel_active': channel.get('status') == 'active',
        'delivery_mode': delivery_mode,
        'meta_access_token_configured': token_ready,
        'delivery_ready': delivery_ready,
    }
    health_status = 'healthy' if all(
        value for key, value in checks.items() if key != 'delivery_mode'
    ) else 'degraded'
    return {
        'status': health_status,
        'channel': channel,
        'checks': checks,
        'upstream': 'not_checked_in_local_core',
    }


@tenant_admin_router.patch('/tenants/{tenant_id}/channels/whatsapp/mode')
async def patch_channel_mode(
    tenant_id: UUID,
    payload: ChannelModeUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        update app.tenant_channels
        set account_mode=$2, updated_at=now()
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        returning id, tenant_id, provider, account_mode, status, updated_at
        """,
        tenant_id,
        payload.account_mode,
    )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='channel.mode_changed',
        entity_type='tenant_channel',
        entity_id=str(row['id']),
        metadata={'account_mode': payload.account_mode, 'reason': payload.reason},
    )
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/channels/messenger')
async def list_messenger_channels(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return Instagram + Facebook channels for the tenant. TASK-0074."""
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {MESSENGER_CHANNEL_PROJECTION}
        from app.tenant_channels
        where tenant_id=$1 and provider in ('instagram_messenger','facebook_messenger')
        order by provider asc
        """,
        tenant_id,
    )
    return {
        'channels': [_normalize_messenger_channel(row) for row in rows],
    }


@tenant_admin_router.put('/tenants/{tenant_id}/channels/messenger')
async def upsert_messenger_channel(
    tenant_id: UUID,
    payload: MessengerChannelUpsert,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Create or update an Instagram/Facebook Messenger channel. TASK-0074.

    Secrets follow the same pattern as WhatsApp:
    ``secrets/tenants/<tenant>/<provider>_access_token`` / ``..._app_secret`` /
    ``..._verify_token``. The verify_token hash is persisted so the webhook
    GET handshake can match without exposing the secret.
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    provider = payload.provider
    token_ref = tenant_secret_ref(tenant_id, f'{provider}_access_token')
    if payload.meta_access_token:
        write_tenant_secret(token_ref, payload.meta_access_token.strip())

    app_secret_ref = tenant_secret_ref(tenant_id, f'{provider}_app_secret')
    if payload.app_secret:
        normalized_secret = normalize_meta_app_secret(payload.app_secret)
        if normalized_secret:
            write_tenant_secret(app_secret_ref, normalized_secret)

    verify_token_ref = tenant_secret_ref(tenant_id, f'{provider}_verify_token')
    if payload.verify_token:
        write_tenant_secret(verify_token_ref, payload.verify_token.strip())
    verify_token = resolve_secret_ref(verify_token_ref)

    page_id = payload.recipient_account_id if provider == 'facebook_messenger' else None
    ig_account_id = (
        payload.recipient_account_id if provider == 'instagram_messenger' else None
    )

    row = await conn.fetchrow(
        f"""
        insert into app.tenant_channels (
            tenant_id, provider, business_id, page_id, instagram_account_id,
            token_ref, app_secret_ref, verify_token_hash, account_mode,
            service_window_hours, status
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'active')
        on conflict (tenant_id, provider) do update set
            business_id=excluded.business_id,
            page_id=excluded.page_id,
            instagram_account_id=excluded.instagram_account_id,
            token_ref=excluded.token_ref,
            app_secret_ref=excluded.app_secret_ref,
            verify_token_hash=coalesce(excluded.verify_token_hash, app.tenant_channels.verify_token_hash),
            account_mode=excluded.account_mode,
            service_window_hours=excluded.service_window_hours,
            status='active'
        returning {MESSENGER_CHANNEL_PROJECTION}
        """,
        tenant_id,
        provider,
        payload.business_id,
        page_id,
        ig_account_id,
        token_ref,
        app_secret_ref,
        verify_token_hash(verify_token) if verify_token else None,
        payload.account_mode,
        payload.service_window_hours,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='channel.messenger_upserted',
        entity_type='tenant_channel',
        entity_id=str(row['id']),
        metadata={'provider': provider},
    )
    return _normalize_messenger_channel(row)


@tenant_admin_router.get('/tenants/{tenant_id}/channels/web')
async def get_web_channel(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f'select {WEB_CHANNEL_PROJECTION} from app.tenant_channels where tenant_id=$1 and provider=$2',
        tenant_id,
        'web',
    )
    if not row:
        return {'channel': None, 'snippet': None, 'has_widget_token': False}
    channel = _normalize_web_channel(row)
    token_ref = channel.get('token_ref') if channel else None
    widget_token = resolve_secret_ref(token_ref) if token_ref else None
    tenant_slug = await conn.fetchval('select slug from app.tenants where id=$1', tenant_id)
    widget_config = (channel or {}).get('widget_config', {}) or {}
    snippet = _build_widget_snippet(
        tenant_slug=tenant_slug or str(tenant_id),
        widget_token=widget_token or '<missing-widget-token>',
        color=widget_config.get('primary_color'),
        greeting=widget_config.get('greeting'),
        logo_url=widget_config.get('logo_url'),
        welcome_copy=widget_config.get('welcome_copy'),
        button_position=widget_config.get('button_position'),
    )
    return {
        'channel': channel,
        'snippet': snippet,
        'has_widget_token': bool(widget_token),
        'tenant_slug': tenant_slug,
    }


@tenant_admin_router.put('/tenants/{tenant_id}/channels/web')
async def upsert_web_channel(
    tenant_id: UUID,
    payload: WebChannelUpsert,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    token_ref = tenant_secret_ref(tenant_id, 'widget_token')
    needs_token = payload.rotate_widget_token or not secret_ref_is_configured(token_ref)
    if needs_token:
        new_token = generate_widget_token()
        write_tenant_secret(token_ref, new_token)

    widget_config = {
        'primary_color': payload.primary_color,
        'greeting': payload.greeting,
        # TASK-0070: extra per-tenant customisation for the CDN widget.
        'logo_url': payload.logo_url,
        'welcome_copy': payload.welcome_copy,
        'button_position': payload.button_position,
    }
    next_status = 'active' if payload.enabled else 'suspended'
    cleaned_origins = [origin.strip().rstrip('/') for origin in payload.allowed_origins if origin and origin.strip()]
    row = await conn.fetchrow(
        """
        insert into app.tenant_channels (
          tenant_id, provider, token_ref, account_mode, status, allowed_origins, widget_config
        )
        values ($1, 'web', $2, 'live', $3, $4, $5::jsonb)
        on conflict (tenant_id, provider) do update set
          token_ref=excluded.token_ref,
          status=excluded.status,
          allowed_origins=excluded.allowed_origins,
          widget_config=excluded.widget_config,
          updated_at=now()
        returning """ + WEB_CHANNEL_PROJECTION,
        tenant_id,
        token_ref,
        next_status,
        cleaned_origins,
        json.dumps(widget_config),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='web_channel.upserted',
        entity_type='tenant_channel',
        entity_id=str(row['id']),
        metadata={
            'enabled': payload.enabled,
            'allowed_origins_count': len(cleaned_origins),
            'widget_token_rotated': needs_token,
        },
    )
    channel = _normalize_web_channel(row)
    widget_token = resolve_secret_ref(token_ref)
    tenant_slug = await conn.fetchval('select slug from app.tenants where id=$1', tenant_id)
    snippet = _build_widget_snippet(
        tenant_slug=tenant_slug or str(tenant_id),
        widget_token=widget_token or '',
        color=widget_config.get('primary_color'),
        greeting=widget_config.get('greeting'),
        logo_url=widget_config.get('logo_url'),
        welcome_copy=widget_config.get('welcome_copy'),
        button_position=widget_config.get('button_position'),
    )
    return {
        'channel': channel,
        'snippet': snippet,
        'has_widget_token': bool(widget_token),
        'tenant_slug': tenant_slug,
    }


@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates', status_code=201)
async def create_whatsapp_template(
    tenant_id: UUID,
    payload: WhatsAppTemplateCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    channel = await _resolve_channel_for_template(conn, tenant_id, payload.channel_id)
    initial_status = 'draft'
    meta_template_id: str | None = None
    rejection_reason: str | None = None
    if (channel['account_mode'] or 'mock') == 'live' and channel['waba_id']:
        try:
            meta_response = await submit_template_to_meta(
                channel['waba_id'],
                channel['token_ref'],
                name=payload.name,
                locale=payload.locale,
                category=payload.category,
                components=payload.components,
            )
        except Exception as exc:
            rejection_reason = str(exc)[:500]
        else:
            meta_template_id = (
                meta_response.get('id') if isinstance(meta_response, dict) else None
            )
            initial_status = 'pending'
    try:
        row = await conn.fetchrow(
            f"""
            insert into app.whatsapp_templates (
              tenant_id, channel_id, name, locale, category, status,
              purpose, components, meta_template_id, rejection_reason
            )
            values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)
            returning {WHATSAPP_TEMPLATE_PROJECTION}
            """,
            tenant_id,
            channel['id'],
            payload.name,
            payload.locale,
            payload.category,
            initial_status,
            payload.purpose,
            json.dumps(payload.components),
            meta_template_id,
            rejection_reason,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409,
            detail='A template with this name and locale already exists for the tenant',
        ) from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.created',
        entity_type='whatsapp_template',
        entity_id=str(row['id']),
        metadata={
            'purpose': payload.purpose,
            'status': initial_status,
            'meta_template_id': meta_template_id,
        },
    )
    return normalize_whatsapp_template(row)


@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates')
async def list_whatsapp_templates(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    purpose: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {WHATSAPP_TEMPLATE_PROJECTION}
        from app.whatsapp_templates
        where tenant_id=$1
          and ($2::text is null or purpose=$2)
          and ($3::text is null or status=$3)
        order by purpose asc, created_at desc
        """,
        tenant_id,
        purpose,
        status_filter,
    )
    return [normalize_whatsapp_template(row) for row in rows]


@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates/{template_id}')
async def get_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_template_or_404(conn, tenant_id, template_id)
    return normalize_whatsapp_template(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/whatsapp/templates/{template_id}')
async def update_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    payload: WhatsAppTemplateUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _fetch_template_or_404(conn, tenant_id, template_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await _fetch_template_or_404(conn, tenant_id, template_id)
        return normalize_whatsapp_template(row)
    row = await conn.fetchrow(
        f"""
        update app.whatsapp_templates
        set name=coalesce($3, name),
            locale=coalesce($4, locale),
            category=coalesce($5, category),
            purpose=coalesce($6, purpose),
            components=coalesce($7::jsonb, components),
            status=coalesce($8, status),
            meta_template_id=coalesce($9, meta_template_id),
            rejection_reason=coalesce($10, rejection_reason)
        where tenant_id=$1 and id=$2
        returning {WHATSAPP_TEMPLATE_PROJECTION}
        """,
        tenant_id,
        template_id,
        update_data.get('name'),
        update_data.get('locale'),
        update_data.get('category'),
        update_data.get('purpose'),
        json.dumps(update_data['components']) if 'components' in update_data else None,
        update_data.get('status'),
        update_data.get('meta_template_id'),
        update_data.get('rejection_reason'),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.updated',
        entity_type='whatsapp_template',
        entity_id=str(template_id),
        metadata={'status': update_data.get('status')},
    )
    return normalize_whatsapp_template(row)


@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates/sync')
async def sync_whatsapp_templates(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    channel = await _resolve_channel_for_template(conn, tenant_id, None)
    if (channel['account_mode'] or 'mock') != 'live' or not channel['waba_id']:
        raise HTTPException(
            status_code=400,
            detail='Template sync requires the WhatsApp channel in live mode with a configured waba_id',
        )
    try:
        meta_templates = await fetch_templates_from_meta(channel['waba_id'], channel['token_ref'])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Meta sync failed: {exc}') from exc
    by_key = {
        (item.get('name'), (item.get('language') or '').lower()): item
        for item in meta_templates
        if isinstance(item, dict) and item.get('name')
    }
    rows = await conn.fetch(
        'select id, name, locale from app.whatsapp_templates where tenant_id=$1',
        tenant_id,
    )
    updated = 0
    for row in rows:
        key = (row['name'], (row['locale'] or '').lower())
        meta_entry = by_key.get(key)
        if not meta_entry:
            continue
        meta_status = (meta_entry.get('status') or '').upper()
        next_status_map = {
            'APPROVED': 'approved',
            'PENDING': 'pending',
            'REJECTED': 'rejected',
            'PAUSED': 'paused',
        }
        next_status = next_status_map.get(meta_status)
        if not next_status:
            continue
        rejection_reason = meta_entry.get('rejected_reason') or meta_entry.get('reason')
        await conn.execute(
            """
            update app.whatsapp_templates
            set status=$3,
                meta_template_id=coalesce($4, meta_template_id),
                rejection_reason=$5
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            row['id'],
            next_status,
            str(meta_entry.get('id')) if meta_entry.get('id') is not None else None,
            str(rejection_reason)[:500] if rejection_reason else None,
        )
        updated += 1
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.synced',
        entity_type='whatsapp_template',
        entity_id=str(tenant_id),
        metadata={'updated': updated, 'meta_total': len(meta_templates)},
    )
    return {'updated': updated, 'meta_total': len(meta_templates)}


@tenant_admin_router.delete('/tenants/{tenant_id}/whatsapp/templates/{template_id}', status_code=204)
async def delete_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    template = await _fetch_template_or_404(conn, tenant_id, template_id)
    channel = await _resolve_channel_for_template(conn, tenant_id, template['channel_id'])
    if (channel['account_mode'] or 'mock') == 'live' and channel['waba_id']:
        try:
            await delete_template_from_meta(
                channel['waba_id'],
                channel['token_ref'],
                template_name=template['name'],
            )
        except Exception as exc:
            log.warning(
                'whatsapp_template.delete_meta_failed',
                tenant_id=str(tenant_id),
                template_id=str(template_id),
                error=str(exc)[:200],
            )
    await conn.execute(
        'delete from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.deleted',
        entity_type='whatsapp_template',
        entity_id=str(template_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/contact-tags', status_code=201)
async def create_contact_tag(
    tenant_id: UUID,
    payload: ContactTagCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    try:
        row = await conn.fetchrow(
            """
            insert into app.contact_tags (tenant_id, name, color, description)
            values ($1, $2, $3, $4)
            returning *
            """,
            tenant_id,
            payload.name.strip(),
            payload.color,
            payload.description,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Tag name already exists for this tenant') from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.created',
        entity_type='contact_tag',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/contact-tags/{tag_id}')
async def update_contact_tag(
    tenant_id: UUID,
    tag_id: UUID,
    payload: ContactTagUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            'select * from app.contact_tags where tenant_id=$1 and id=$2', tenant_id, tag_id
        )
        if not row:
            raise HTTPException(status_code=404, detail='Tag not found')
        return record_to_dict(row)
    set_clauses = []
    params: list[Any] = [tenant_id, tag_id]
    for field, value in updates.items():
        params.append(value)
        set_clauses.append(f'{field}=${len(params)}')
    try:
        row = await conn.fetchrow(
            f"""
            update app.contact_tags
            set {', '.join(set_clauses)}
            where tenant_id=$1 and id=$2
            returning *
            """,
            *params,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Tag name already exists for this tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Tag not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.updated',
        entity_type='contact_tag',
        entity_id=str(tag_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/contact-tags/{tag_id}', status_code=204)
async def delete_contact_tag(
    tenant_id: UUID,
    tag_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.contact_tags where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        tag_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Tag not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.deleted',
        entity_type='contact_tag',
        entity_id=str(tag_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/branches', status_code=201)
async def create_branch(payload: BranchCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    # TASK-0058: auto-generate the Google Maps URL when the admin leaves it blank.
    maps_url_value = payload.maps_url
    if not maps_url_value:
        maps_url_value = build_maps_url(payload.lat, payload.lng, payload.address)
    try:
        row = await conn.fetchrow(
            """
            insert into app.branches (
                tenant_id, name, code, address, city, state, country,
                lat, lng, maps_url, phone_e164, timezone, opening_hours,
                is_active, sort_order
            )
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14,$15)
            returning *
            """,
            tenant_id,
            payload.name,
            payload.code,
            payload.address,
            payload.city,
            payload.state,
            payload.country,
            payload.lat,
            payload.lng,
            maps_url_value,
            payload.phone_e164,
            payload.timezone,
            json.dumps(payload.opening_hours),
            payload.is_active,
            payload.sort_order,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Branch code already exists for tenant') from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.created',
        entity_type='branch',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/branches/{branch_id}')
async def update_branch(branch_id: UUID, payload: BranchUpdate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow('select * from app.branches where tenant_id=$1 and id=$2', tenant_id, branch_id)
        if not row:
            raise HTTPException(status_code=404, detail='Branch not found')
        return record_to_dict(row)
    # TASK-0058: regenerate the maps URL when the admin clears it while editing
    # location data — keeps the link consistent with the updated address/coords.
    if 'maps_url' in update_data and not update_data.get('maps_url'):
        existing = await conn.fetchrow(
            'select lat, lng, address from app.branches where tenant_id=$1 and id=$2',
            tenant_id,
            branch_id,
        )
        final_lat = update_data['lat'] if 'lat' in update_data else (existing['lat'] if existing else None)
        final_lng = update_data['lng'] if 'lng' in update_data else (existing['lng'] if existing else None)
        final_address = (
            update_data['address']
            if 'address' in update_data
            else (existing['address'] if existing else None)
        )
        auto_url = build_maps_url(final_lat, final_lng, final_address)
        if auto_url:
            update_data['maps_url'] = auto_url
    try:
        row = await conn.fetchrow(
            """
            update app.branches
            set name=coalesce($3, name),
                code=coalesce($4, code),
                address=case when $14::boolean then $5 else address end,
                city=case when $15::boolean then $6 else city end,
                state=case when $16::boolean then $7 else state end,
                country=coalesce($8, country),
                lat=case when $17::boolean then $9 else lat end,
                lng=case when $18::boolean then $10 else lng end,
                maps_url=case when $19::boolean then $11 else maps_url end,
                phone_e164=case when $20::boolean then $12 else phone_e164 end,
                timezone=coalesce($13, timezone),
                opening_hours=coalesce($21::jsonb, opening_hours),
                is_active=coalesce($22, is_active),
                sort_order=coalesce($23, sort_order)
            where tenant_id=$1 and id=$2
            returning *
            """,
            tenant_id,
            branch_id,
            update_data.get('name'),
            update_data.get('code'),
            update_data.get('address'),
            update_data.get('city'),
            update_data.get('state'),
            update_data.get('country'),
            update_data.get('lat'),
            update_data.get('lng'),
            update_data.get('maps_url'),
            update_data.get('phone_e164'),
            update_data.get('timezone'),
            'address' in update_data,
            'city' in update_data,
            'state' in update_data,
            'lat' in update_data,
            'lng' in update_data,
            'maps_url' in update_data,
            'phone_e164' in update_data,
            json.dumps(update_data['opening_hours']) if 'opening_hours' in update_data else None,
            update_data.get('is_active'),
            update_data.get('sort_order'),
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Branch code already exists for tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Branch not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.updated',
        entity_type='branch',
        entity_id=str(branch_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/branches/{branch_id}', status_code=204)
async def deactivate_branch(branch_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.branches
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        branch_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Branch not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.deleted',
        entity_type='branch',
        entity_id=str(branch_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/packages', status_code=201)
async def create_treatment_package(
    payload: TreatmentPackageCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    if payload.renewal_template_id is not None:
        owns = await conn.fetchval(
            'select 1 from app.whatsapp_templates where tenant_id=$1 and id=$2',
            tenant_id,
            payload.renewal_template_id,
        )
        if not owns:
            raise HTTPException(status_code=400, detail='renewal_template_id not found for tenant')
    row = await conn.fetchrow(
        """
        insert into app.treatment_packages (
            tenant_id, name, description, total_sessions, validity_days,
            price_amount, price_currency, includes_service_ids,
            renewal_template_id, is_active, sort_order, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
        returning *
        """,
        tenant_id,
        payload.name,
        payload.description,
        payload.total_sessions,
        payload.validity_days,
        payload.price_amount,
        payload.price_currency,
        [str(s) for s in payload.includes_service_ids],
        payload.renewal_template_id,
        payload.is_active,
        payload.sort_order,
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.created',
        entity_type='treatment_package',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/packages/{package_id}')
async def update_treatment_package(
    package_id: UUID,
    payload: TreatmentPackageUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            'select * from app.treatment_packages where tenant_id=$1 and id=$2',
            tenant_id,
            package_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Package not found')
        return record_to_dict(row)
    if 'renewal_template_id' in update_data and update_data['renewal_template_id'] is not None:
        owns = await conn.fetchval(
            'select 1 from app.whatsapp_templates where tenant_id=$1 and id=$2',
            tenant_id,
            update_data['renewal_template_id'],
        )
        if not owns:
            raise HTTPException(status_code=400, detail='renewal_template_id not found for tenant')
    row = await conn.fetchrow(
        """
        update app.treatment_packages
        set name=coalesce($3, name),
            description=case when $13::boolean then $4 else description end,
            total_sessions=coalesce($5, total_sessions),
            validity_days=case when $14::boolean then $6 else validity_days end,
            price_amount=coalesce($7, price_amount),
            price_currency=coalesce($8, price_currency),
            includes_service_ids=coalesce($9, includes_service_ids),
            renewal_template_id=case when $15::boolean then $10 else renewal_template_id end,
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order),
            metadata=coalesce($16::jsonb, metadata)
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        package_id,
        update_data.get('name'),
        update_data.get('description'),
        update_data.get('total_sessions'),
        update_data.get('validity_days'),
        update_data.get('price_amount'),
        update_data.get('price_currency'),
        [str(s) for s in update_data['includes_service_ids']] if 'includes_service_ids' in update_data else None,
        update_data.get('renewal_template_id'),
        update_data.get('is_active'),
        update_data.get('sort_order'),
        'description' in update_data,
        'validity_days' in update_data,
        'renewal_template_id' in update_data,
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.updated',
        entity_type='treatment_package',
        entity_id=str(package_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/packages/{package_id}', status_code=204)
async def deactivate_treatment_package(
    package_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.treatment_packages
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        package_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.deleted',
        entity_type='treatment_package',
        entity_id=str(package_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/contacts/{contact_id}/packages', status_code=201)
async def assign_contact_package(
    contact_id: UUID,
    payload: ContactPackageAssign,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    pkg = await conn.fetchrow(
        """
        select id, total_sessions, validity_days, price_amount, price_currency
        from app.treatment_packages
        where tenant_id=$1 and id=$2 and is_active=true
        """,
        tenant_id,
        payload.package_id,
    )
    if not pkg:
        raise HTTPException(status_code=404, detail='Package not found or inactive')
    contact = await conn.fetchval(
        'select 1 from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')
    expires_at = payload.expires_at
    if expires_at is None and pkg['validity_days']:
        expires_at = datetime.now(UTC) + timedelta(days=int(pkg['validity_days']))
    payment_amount = payload.payment_amount if payload.payment_amount is not None else float(pkg['price_amount'])
    currency = payload.payment_currency or pkg['price_currency']
    row = await conn.fetchrow(
        """
        insert into app.contact_packages (
            tenant_id, contact_id, package_id, expires_at,
            remaining_sessions, total_sessions, payment_status,
            payment_amount, payment_currency, notes
        )
        values ($1,$2,$3,$4,$5,$5,$6,$7,$8,$9)
        returning *
        """,
        tenant_id,
        contact_id,
        payload.package_id,
        expires_at,
        pkg['total_sessions'],
        payload.payment_status,
        payment_amount,
        currency,
        payload.notes,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.assigned',
        entity_type='contact_package',
        entity_id=str(row['id']),
        metadata={'package_id': str(payload.package_id), 'contact_id': str(contact_id)},
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/contacts/{contact_id}/packages/{contact_package_id}')
async def update_contact_package(
    contact_id: UUID,
    contact_package_id: UUID,
    payload: ContactPackagePatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            'select * from app.contact_packages where tenant_id=$1 and contact_id=$2 and id=$3',
            tenant_id,
            contact_id,
            contact_package_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Contact package not found')
        return record_to_dict(row)
    row = await conn.fetchrow(
        """
        update app.contact_packages
        set payment_status=coalesce($4, payment_status),
            payment_amount=case when $9::boolean then $5 else payment_amount end,
            payment_currency=coalesce($6, payment_currency),
            expires_at=case when $10::boolean then $7 else expires_at end,
            status=coalesce($8, status),
            notes=case when $11::boolean then $12 else notes end
        where tenant_id=$1 and contact_id=$2 and id=$3
        returning *
        """,
        tenant_id,
        contact_id,
        contact_package_id,
        update_data.get('payment_status'),
        update_data.get('payment_amount'),
        update_data.get('payment_currency'),
        update_data.get('expires_at'),
        update_data.get('status'),
        'payment_amount' in update_data,
        'expires_at' in update_data,
        'notes' in update_data,
        update_data.get('notes'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Contact package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.updated',
        entity_type='contact_package',
        entity_id=str(contact_package_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/contacts/{contact_id}/packages/{contact_package_id}', status_code=204)
async def refund_contact_package(
    contact_id: UUID,
    contact_package_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Mark a contact package as refunded.

    Sets status=refunded, payment_status=refunded, and zeroes the remaining
    sessions so the booking flow no longer offers them. Existing
    appointment_package_links are preserved for audit, but the package is no
    longer 'active'.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.contact_packages
        set status='refunded',
            payment_status='refunded',
            remaining_sessions=0
        where tenant_id=$1 and contact_id=$2 and id=$3
        returning id
        """,
        tenant_id,
        contact_id,
        contact_package_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Contact package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.refunded',
        entity_type='contact_package',
        entity_id=str(contact_package_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/subscription-plans', status_code=201)
async def create_subscription_plan(
    payload: SubscriptionPlanCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        insert into app.subscription_plans (
            tenant_id, name, description, billing_period, price_amount, currency,
            included_services, status, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::jsonb)
        returning *
        """,
        tenant_id,
        payload.name,
        payload.description,
        payload.billing_period,
        payload.price_amount,
        payload.currency,
        json.dumps(payload.included_services),
        payload.status,
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='subscription_plan.created',
        entity_type='subscription_plan',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/subscription-plans/{plan_id}')
async def update_subscription_plan(
    plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            'select * from app.subscription_plans where tenant_id=$1 and id=$2',
            tenant_id,
            plan_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Plan not found')
        return record_to_dict(row)
    row = await conn.fetchrow(
        """
        update app.subscription_plans
        set name=coalesce($3, name),
            description=case when $11::boolean then $4 else description end,
            billing_period=coalesce($5, billing_period),
            price_amount=coalesce($6, price_amount),
            currency=coalesce($7, currency),
            included_services=coalesce($8::jsonb, included_services),
            status=coalesce($9, status),
            metadata=coalesce($10::jsonb, metadata)
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        plan_id,
        update_data.get('name'),
        update_data.get('description'),
        update_data.get('billing_period'),
        update_data.get('price_amount'),
        update_data.get('currency'),
        json.dumps(update_data['included_services']) if 'included_services' in update_data else None,
        update_data.get('status'),
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
        'description' in update_data,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Plan not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='subscription_plan.updated',
        entity_type='subscription_plan',
        entity_id=str(plan_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/subscription-plans/{plan_id}', status_code=204)
async def archive_subscription_plan(
    plan_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.subscription_plans
        set status='archived'
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        plan_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Plan not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='subscription_plan.archived',
        entity_type='subscription_plan',
        entity_id=str(plan_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/subscriptions', status_code=201)
async def create_contact_subscription(
    payload: ContactSubscriptionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    # BUG-112: traemos `price_amount` + `currency` del plan para snapshotearlos
    # en el subscribe (`price_locked_amount` / `price_locked_currency`). Sin el
    # snapshot, futuros price-bumps del plan inflarían retroactivamente el MRR
    # y la factura de este suscriptor.
    plan = await conn.fetchrow(
        """
        select id, price_amount, currency from app.subscription_plans
        where tenant_id=$1 and id=$2 and status=$3
        """,
        tenant_id,
        payload.plan_id,
        'active',
    )
    if not plan:
        raise HTTPException(status_code=400, detail='Plan not found or archived')
    contact = await conn.fetchval(
        'select 1 from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        payload.contact_id,
    )
    if not contact:
        raise HTTPException(status_code=400, detail='Contact not found for tenant')
    row = await conn.fetchrow(
        """
        insert into app.contact_subscriptions (
            tenant_id, contact_id, plan_id, payment_provider,
            payment_provider_subscription_id, payment_method_id,
            next_billing_at, price_locked_amount, price_locked_currency, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
        returning *
        """,
        tenant_id,
        payload.contact_id,
        payload.plan_id,
        payload.payment_provider,
        payload.payment_provider_subscription_id,
        payload.payment_method_id,
        payload.next_billing_at,
        plan['price_amount'],
        plan['currency'],
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_subscription.created',
        entity_type='contact_subscription',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/subscriptions/{subscription_id}')
async def update_contact_subscription(
    subscription_id: UUID,
    payload: ContactSubscriptionPatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    cancel_now = update_data.get('status') == 'cancelled'
    row = await conn.fetchrow(
        """
        update app.contact_subscriptions
        set status=coalesce($3, status),
            next_billing_at=coalesce($4, next_billing_at),
            payment_provider_subscription_id=coalesce($5, payment_provider_subscription_id),
            payment_method_id=coalesce($6, payment_method_id),
            retry_payment_link=coalesce($7, retry_payment_link),
            metadata=coalesce($8::jsonb, metadata),
            cancelled_at=case when $9::boolean then now() else cancelled_at end
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        subscription_id,
        update_data.get('status'),
        update_data.get('next_billing_at'),
        update_data.get('payment_provider_subscription_id'),
        update_data.get('payment_method_id'),
        update_data.get('retry_payment_link'),
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
        cancel_now,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Subscription not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_subscription.updated',
        entity_type='contact_subscription',
        entity_id=str(subscription_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/subscriptions/{subscription_id}', status_code=204)
async def cancel_contact_subscription(
    subscription_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.contact_subscriptions
        set status='cancelled', cancelled_at=now()
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        subscription_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Subscription not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_subscription.cancelled',
        entity_type='contact_subscription',
        entity_id=str(subscription_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/services', status_code=201)
async def create_service(
    tenant_id: UUID,
    payload: ServiceCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f"""
        insert into app.service_catalog (
          tenant_id, name, category, description, price_amount, price_currency,
          duration_minutes, preparation_notes, post_service_notes,
          recall_interval_days, recall_template_id, applies_when,
          is_active, sort_order, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,$15::jsonb)
        returning {SERVICE_CATALOG_PROJECTION}
        """,
        tenant_id,
        payload.name,
        payload.category,
        payload.description,
        payload.price_amount,
        payload.price_currency.upper(),
        payload.duration_minutes,
        payload.preparation_notes,
        payload.post_service_notes,
        payload.recall_interval_days,
        payload.recall_template_id,
        json.dumps(normalize_applies_when(payload.applies_when)),
        payload.is_active,
        payload.sort_order,
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.created',
        entity_type='service_catalog',
        entity_id=str(row['id']),
    )
    return normalize_service_catalog_row(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/services/{service_id}')
async def update_service(
    tenant_id: UUID,
    service_id: UUID,
    payload: ServiceUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            f'select {SERVICE_CATALOG_PROJECTION} from app.service_catalog where tenant_id=$1 and id=$2',
            tenant_id,
            service_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Service not found')
        return normalize_service_catalog_row(row)
    if 'price_currency' in update_data and update_data['price_currency']:
        update_data['price_currency'] = update_data['price_currency'].upper()
    # TASK-0052: recall_interval_days / recall_template_id can be cleared back
    # to null. We pass a "<field>_set" flag so SQL knows whether the caller
    # really sent the field (clear) vs. omitted it (keep current).
    recall_days_set = 'recall_interval_days' in update_data
    recall_template_set = 'recall_template_id' in update_data
    # TASK-0054: applies_when uses coalesce semantics — only updated when the
    # caller sends it; null in the payload means "clear to {}".
    applies_when_payload: str | None = None
    if 'applies_when' in update_data:
        rules = update_data['applies_when'] or {}
        applies_when_payload = json.dumps(normalize_applies_when(rules))
    row = await conn.fetchrow(
        f"""
        update app.service_catalog
        set name=coalesce($3, name),
            category=coalesce($4, category),
            description=coalesce($5, description),
            price_amount=coalesce($6, price_amount),
            price_currency=coalesce($7, price_currency),
            duration_minutes=coalesce($8, duration_minutes),
            preparation_notes=coalesce($9, preparation_notes),
            post_service_notes=coalesce($10, post_service_notes),
            recall_interval_days = case when $14::boolean then $15 else recall_interval_days end,
            recall_template_id   = case when $16::boolean then $17 else recall_template_id end,
            applies_when=coalesce($18::jsonb, applies_when),
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order),
            metadata=coalesce($13::jsonb, metadata)
        where tenant_id=$1 and id=$2
        returning {SERVICE_CATALOG_PROJECTION}
        """,
        tenant_id,
        service_id,
        update_data.get('name'),
        update_data.get('category'),
        update_data.get('description'),
        update_data.get('price_amount'),
        update_data.get('price_currency'),
        update_data.get('duration_minutes'),
        update_data.get('preparation_notes'),
        update_data.get('post_service_notes'),
        update_data.get('is_active'),
        update_data.get('sort_order'),
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
        recall_days_set,
        update_data.get('recall_interval_days'),
        recall_template_set,
        update_data.get('recall_template_id'),
        applies_when_payload,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.updated',
        entity_type='service_catalog',
        entity_id=str(service_id),
    )
    return normalize_service_catalog_row(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/services/{service_id}', status_code=204)
async def deactivate_service(
    tenant_id: UUID,
    service_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        update app.service_catalog
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        service_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.deactivated',
        entity_type='service_catalog',
        entity_id=str(service_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/services/reorder')
async def reorder_services(
    tenant_id: UUID,
    payload: ServiceReorderRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if not payload.order:
        return {'updated': 0}
    async with conn.transaction():
        for item in payload.order:
            await conn.execute(
                """
                update app.service_catalog
                set sort_order=$3
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                item.id,
                item.sort_order,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.reordered',
        entity_type='service_catalog',
        entity_id=str(tenant_id),
    )
    return {'updated': len(payload.order)}


@tenant_admin_router.post(
    '/tenants/{tenant_id}/qualification-questions', status_code=201
)
async def create_qualification_question(
    tenant_id: UUID,
    payload: QualificationQuestionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    options_json = json.dumps(
        [o.model_dump(mode='json', exclude_none=True) for o in payload.options]
    )
    applies = [str(sid) for sid in payload.applies_to_service_ids]
    row = await conn.fetchrow(
        f"""
        insert into app.qualification_questions (
          tenant_id, position, label, kind, options, required,
          applies_to_service_ids, preset, key
        )
        values ($1, $2, $3, $4, $5::jsonb, $6, $7::uuid[], $8, $9)
        returning {QUALIFICATION_PROJECTION}
        """,
        tenant_id,
        payload.position,
        payload.label,
        payload.kind,
        options_json,
        payload.required,
        applies,
        payload.preset,
        payload.key,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.created',
        entity_type='qualification_question',
        entity_id=str(row['id']),
        metadata={'label': payload.label, 'kind': payload.kind},
    )
    return normalize_qualification_question(row)


@tenant_admin_router.patch(
    '/tenants/{tenant_id}/qualification-questions/{question_id}'
)
async def update_qualification_question(
    tenant_id: UUID,
    question_id: UUID,
    payload: QualificationQuestionUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {QUALIFICATION_PROJECTION} from app.qualification_questions '
            'where tenant_id=$1 and id=$2',
            tenant_id,
            question_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Question not found')
        return normalize_qualification_question(row)
    options_json = (
        json.dumps([o.model_dump(mode='json', exclude_none=True) for o in payload.options])
        if payload.options is not None
        else None
    )
    applies = (
        [str(sid) for sid in payload.applies_to_service_ids]
        if payload.applies_to_service_ids is not None
        else None
    )
    preset_update = updates.get('preset') if 'preset' in updates else None
    preset_provided = 'preset' in updates
    key_update = updates.get('key') if 'key' in updates else None
    key_provided = 'key' in updates
    row = await conn.fetchrow(
        f"""
        update app.qualification_questions
        set label=coalesce($3, label),
            kind=coalesce($4, kind),
            options=coalesce($5::jsonb, options),
            required=coalesce($6, required),
            position=coalesce($7, position),
            applies_to_service_ids=coalesce($8::uuid[], applies_to_service_ids),
            preset=case when $10::boolean then $9 else preset end,
            key=case when $12::boolean then $11 else key end
        where tenant_id=$1 and id=$2
        returning {QUALIFICATION_PROJECTION}
        """,
        tenant_id,
        question_id,
        updates.get('label'),
        updates.get('kind'),
        options_json,
        updates.get('required'),
        updates.get('position'),
        applies,
        preset_update,
        preset_provided,
        key_update,
        key_provided,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Question not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.updated',
        entity_type='qualification_question',
        entity_id=str(question_id),
    )
    return normalize_qualification_question(row)


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/qualification-questions/{question_id}', status_code=204
)
async def delete_qualification_question(
    tenant_id: UUID,
    question_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.qualification_questions where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        question_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Question not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.deleted',
        entity_type='qualification_question',
        entity_id=str(question_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/qualification-questions/reorder')
async def reorder_qualification_questions(
    tenant_id: UUID,
    payload: QualificationReorderRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if not payload.order:
        return {'updated': 0}
    async with conn.transaction():
        for item in payload.order:
            await conn.execute(
                """
                update app.qualification_questions
                set position=$3
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                item.id,
                item.position,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.reordered',
        entity_type='qualification_question',
        entity_id=str(tenant_id),
    )
    return {'updated': len(payload.order)}


@tenant_admin_router.get('/tenants/{tenant_id}/media')
async def list_media_assets(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    kind: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if kind is not None and kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail='Unsupported media kind')
    rows = await conn.fetch(
        f"""
        select {MEDIA_ASSET_COLUMNS}
        from app.media_assets
        where tenant_id = $1
          and ($2::text is null or kind = $2)
          and ($3::text is null or $3 = any(tags))
        order by created_at desc
        """,
        tenant_id,
        kind,
        tag,
    )
    return [normalize_media_asset(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/media', status_code=201)
async def upload_media_asset(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # BUG-222 (codex P2 follow-up): Content-Length pre-check ANTES de
    # `request.form()` que parsea/spoolea el body multipart entero. El cap
    # tight por-kind se aplica abajo después de saber `kind`, pero acá
    # cortamos uploads obviamente abusivos (>100MB cualquier kind) sin
    # buffer en memoria. 100MB es el cap más alto del schema (video).
    _MAX_MEDIA_BYTES_HARD_CAP = 100 * 1024 * 1024
    declared_size = int(request.headers.get('content-length') or 0)
    if declared_size and declared_size > _MAX_MEDIA_BYTES_HARD_CAP * 2:
        raise HTTPException(
            status_code=413,
            detail=f'Upload exceeds the global media cap ({_MAX_MEDIA_BYTES_HARD_CAP} bytes)',
        )

    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500, detail='python-multipart dependency is required for file uploads'
        ) from exc
    kind = str(form.get('kind') or '').strip()
    label = str(form.get('label') or '').strip()
    description = form.get('description')
    description_text = str(description).strip() if description else None
    raw_tags = form.get('tags')
    tags: list[str] = []
    if raw_tags:
        tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]
    file = form.get('file')
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail='kind must be one of image|video|pdf|audio')
    if not label:
        raise HTTPException(status_code=422, detail='label is required')
    if not file or not hasattr(file, 'read'):
        raise HTTPException(status_code=422, detail='file is required')

    # BUG-222 (codex MEDIUM, 2026-05-18): chequear Content-Length contra el
    # cap por-kind ANTES de leer el body. Sin esto, un admin podía mandar
    # un file de GB pre-rejection — el worker buffereaba todo en memoria
    # antes de que `validate_media_upload` lo rechazara. El cap por-kind
    # vive en `MEDIA_SIZE_LIMITS_BYTES` (app/services/media_storage.py).
    from app.services.media_storage import MEDIA_SIZE_LIMITS_BYTES as _MEDIA_CAPS  # noqa: PLC0415

    kind_cap = _MEDIA_CAPS.get(kind, 5 * 1024 * 1024)
    declared_size = int(request.headers.get('content-length') or 0)
    if declared_size and declared_size > kind_cap * 2:
        # 2x slack para multipart overhead (boundary + headers + form fields).
        raise HTTPException(
            status_code=413,
            detail=f'Upload exceeds {kind_cap} bytes for kind={kind}',
        )

    data = await file.read()
    filename = getattr(file, 'filename', None) or 'media.bin'
    mime_type = getattr(file, 'content_type', None)
    asset_id = uuid4()
    settings = get_settings()
    try:
        stored = store_media_file(
            data=data,
            tenant_id=str(tenant_id),
            asset_id=str(asset_id),
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploader_id = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        f"""
        insert into app.media_assets (
          id, tenant_id, kind, label, description,
          storage_backend, storage_bucket, object_key, source_uri,
          mime_type, sha256, size_bytes, tags, uploaded_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::text[], $14)
        returning {MEDIA_ASSET_COLUMNS}
        """,
        asset_id,
        tenant_id,
        kind,
        label,
        description_text,
        stored.storage_backend,
        stored.bucket,
        stored.object_key,
        stored.source_uri,
        stored.mime_type,
        stored.sha256,
        stored.size_bytes,
        tags,
        uploader_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.created',
        entity_type='media_asset',
        entity_id=str(asset_id),
        metadata={'kind': kind, 'size_bytes': stored.size_bytes, 'label': label},
    )
    return normalize_media_asset(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/media/{asset_id}')
async def update_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    payload: MediaAssetUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {MEDIA_ASSET_COLUMNS} from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            asset_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Media asset not found')
        return normalize_media_asset(row)
    row = await conn.fetchrow(
        f"""
        update app.media_assets
        set label=coalesce($3, label),
            description=coalesce($4, description),
            tags=coalesce($5::text[], tags)
        where tenant_id=$1 and id=$2
        returning {MEDIA_ASSET_COLUMNS}
        """,
        tenant_id,
        asset_id,
        updates.get('label'),
        updates.get('description'),
        updates.get('tags'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Media asset not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.updated',
        entity_type='media_asset',
        entity_id=str(asset_id),
    )
    return normalize_media_asset(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/media/{asset_id}', status_code=204)
async def delete_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        select storage_backend, storage_bucket, object_key, source_uri
        from app.media_assets
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        asset_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Media asset not found')
    settings = get_settings()
    delete_media_file(
        storage_backend=row['storage_backend'],
        object_key=row['object_key'],
        source_uri=row['source_uri'],
        bucket=row['storage_bucket'],
        settings=settings,
    )
    await conn.execute(
        'delete from app.media_assets where tenant_id=$1 and id=$2',
        tenant_id,
        asset_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.deleted',
        entity_type='media_asset',
        entity_id=str(asset_id),
    )
    return Response(status_code=204)


@tenant_admin_router.get('/tenants/{tenant_id}/promotions')
async def list_promotions(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    include_inactive: bool = Query(default=True),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {PROMOTION_COLUMNS}
        from app.promotions
        where tenant_id=$1
          and ($2::boolean is true or is_active is true)
        order by sort_order asc, created_at desc
        """,
        tenant_id,
        include_inactive,
    )
    return [normalize_promotion(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/promotions', status_code=201)
async def create_promotion(
    tenant_id: UUID,
    payload: PromotionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if payload.media_asset_id:
        owns = await conn.fetchval(
            'select 1 from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            payload.media_asset_id,
        )
        if not owns:
            raise HTTPException(status_code=422, detail='media_asset_id does not belong to this tenant')
    if payload.valid_from and payload.valid_until and payload.valid_from > payload.valid_until:
        raise HTTPException(status_code=422, detail='valid_from must be <= valid_until')
    applies = [str(sid) for sid in payload.applies_to_service_ids]
    row = await conn.fetchrow(
        f"""
        insert into app.promotions (
          tenant_id, name, description, media_asset_id, valid_from, valid_until,
          applies_to_service_ids, coupon_code, discount_percent, is_active, sort_order
        )
        values ($1, $2, $3, $4, $5, $6, $7::uuid[], $8, $9, $10, $11)
        returning {PROMOTION_COLUMNS}
        """,
        tenant_id,
        payload.name,
        payload.description,
        payload.media_asset_id,
        payload.valid_from,
        payload.valid_until,
        applies,
        payload.coupon_code,
        payload.discount_percent,
        payload.is_active,
        payload.sort_order,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.created',
        entity_type='promotion',
        entity_id=str(row['id']),
        metadata={'name': payload.name},
    )
    return normalize_promotion(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/promotions/{promotion_id}')
async def update_promotion(
    tenant_id: UUID,
    promotion_id: UUID,
    payload: PromotionUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {PROMOTION_COLUMNS} from app.promotions where tenant_id=$1 and id=$2',
            tenant_id,
            promotion_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Promotion not found')
        return normalize_promotion(row)
    if 'media_asset_id' in updates and updates['media_asset_id']:
        owns = await conn.fetchval(
            'select 1 from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            updates['media_asset_id'],
        )
        if not owns:
            raise HTTPException(status_code=422, detail='media_asset_id does not belong to this tenant')
    applies = (
        [str(sid) for sid in payload.applies_to_service_ids]
        if payload.applies_to_service_ids is not None
        else None
    )
    row = await conn.fetchrow(
        f"""
        update app.promotions
        set name=coalesce($3, name),
            description=coalesce($4, description),
            media_asset_id=coalesce($5, media_asset_id),
            valid_from=coalesce($6, valid_from),
            valid_until=coalesce($7, valid_until),
            applies_to_service_ids=coalesce($8::uuid[], applies_to_service_ids),
            coupon_code=coalesce($9, coupon_code),
            discount_percent=coalesce($10, discount_percent),
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order)
        where tenant_id=$1 and id=$2
        returning {PROMOTION_COLUMNS}
        """,
        tenant_id,
        promotion_id,
        updates.get('name'),
        updates.get('description'),
        updates.get('media_asset_id'),
        updates.get('valid_from'),
        updates.get('valid_until'),
        applies,
        updates.get('coupon_code'),
        updates.get('discount_percent'),
        updates.get('is_active'),
        updates.get('sort_order'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Promotion not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.updated',
        entity_type='promotion',
        entity_id=str(promotion_id),
    )
    return normalize_promotion(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/promotions/{promotion_id}', status_code=204)
async def delete_promotion(
    tenant_id: UUID,
    promotion_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.promotions where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        promotion_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Promotion not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.deleted',
        entity_type='promotion',
        entity_id=str(promotion_id),
    )
    return Response(status_code=204)


@tenant_admin_router.get('/tenants/{tenant_id}/payments/settings')
async def get_tenant_payment_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    return _public_payment_settings(tenant_id, settings)


@tenant_admin_router.put('/tenants/{tenant_id}/payments/settings')
async def update_tenant_payment_settings(
    tenant_id: UUID,
    payload: TenantPaymentSettingsUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await _fetch_tenant_payment_settings(conn, tenant_id)
    next_settings = {
        **current,
        'provider': payload.provider,
        'currency': payload.currency.upper(),
        'default_amount': payload.default_amount,
    }
    api_key_value = (payload.api_key or '').strip()
    if api_key_value:
        ref = tenant_secret_ref(tenant_id, 'payment_api_key')
        write_tenant_secret(ref, api_key_value)
        next_settings['api_key_ref'] = ref
    elif payload.provider == 'none':
        next_settings['api_key_ref'] = None
    webhook_secret_value = (payload.webhook_secret or '').strip()
    if webhook_secret_value:
        ref = tenant_secret_ref(tenant_id, 'payment_webhook_secret')
        write_tenant_secret(ref, webhook_secret_value)
        next_settings['webhook_secret_ref'] = ref
    elif payload.provider == 'none':
        next_settings['webhook_secret_ref'] = None
    if payload.provider != 'none' and not next_settings.get('webhook_secret_ref'):
        raise HTTPException(
            status_code=422,
            detail='Webhook signing secret is required to enable a payment provider',
        )
    await conn.execute(
        """
        update app.tenant_settings
        set payment_settings=$2::jsonb, updated_at=now()
        where tenant_id=$1
        """,
        tenant_id,
        json.dumps(next_settings),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_payment_settings.updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={'provider': next_settings['provider']},
    )
    return _public_payment_settings(tenant_id, next_settings)


@tenant_admin_router.get('/knowledge/documents')
async def list_knowledge_documents(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
    visibility: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
        from app.knowledge_documents
        where tenant_id=$1
          and ($2::text is null or status=$2)
          and ($3::text is null or visibility=$3)
          and ($4::text is null or source_type=$4)
        order by updated_at desc, created_at desc
        limit 250
        """,
        tenant_id,
        status_filter,
        visibility,
        source_type,
    )
    return normalize_knowledge_documents(rows)


@tenant_admin_router.post('/intents/evaluate')
async def evaluate_intent_retrieval(
    payload: IntentEvaluateRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    # AUDIT-51 / round-3 §1.1 (2026-05-18): cargar `no_train` del tenant para
    # propagarlo al `classify_intent` callsite abajo. Antes `tenant_no_train`
    # default `None` siempre bloqueaba cloud — un tenant con `no_train=False`
    # configurado legítimamente perdía Anthropic/OpenAI en este endpoint
    # admin (inconsistente con `rag_orchestrator.classify_intent`).
    settings_row = await conn.fetchrow(
        'select no_train from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    tenant_no_train: bool | None = (
        bool(settings_row['no_train'])
        if settings_row and settings_row['no_train'] is not None
        else True
    )
    visibility_filter = list(ALL_VISIBILITY) if payload.include_agents_only else list(END_USER_VISIBILITY)
    # BUG-212 (codex MEDIUM): el SELECT antes traía TODOS los chunks activos
    # del tenant y los rankeaba en Python. Un tenant admin con catálogo
    # grande podía agotar memoria/CPU del worker. Cap a 1000 candidatos
    # (mismo cap pre-TASK-0079) — el filtro Python sigue siendo necesario
    # porque pgvector no enforce el min_score que el caller envía.
    rows = await conn.fetch(
        """
        select kc.id,
               kc.document_id,
               kd.title as document_title,
               kd.source_uri,
               kd.source_type,
               kd.document_type,
               kd.visibility,
               kc.chunk_index,
               kc.section_path,
               kc.chunk_text,
               kc.token_count,
               kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id = kc.document_id and kd.tenant_id = kc.tenant_id
        where kc.tenant_id=$1
          and kd.status='active'
          and kd.visibility = ANY($2::text[])
        order by kd.updated_at desc, kc.chunk_index asc
        limit 1000
        """,
        tenant_id,
        visibility_filter,
    )
    matches = rank_chunks(
        payload.question,
        [record_to_dict(row) for row in rows],
        max_chunks=payload.max_chunks,
    )
    answer = build_grounded_answer(
        payload.question,
        matches,
        min_score=payload.min_score,
        allow_agents_only=payload.include_agents_only,
    )

    # Intent classification — AUDIT-51 propaga `tenant_no_train` para que el
    # gate cloud aplique igual que en el orchestrator (consistencia funcional).
    intent_result = await classify_intent(
        payload.question,
        settings=get_settings(),
        tenant_no_train=tenant_no_train,
    )

    response = {
        'tenant_id': str(tenant_id),
        'question': payload.question,
        'intent': intent_result.intent,
        'confidence': round(intent_result.confidence, 4),
        'resolved_by': intent_result.resolved_by,
        **answer,
        'chunks': [retrieval_match_to_dict(match) for match in matches],
        'retrieval': {
            'candidate_chunk_count': len(rows),
            'returned_chunk_count': len(matches),
            'min_score': payload.min_score,
        },
    }
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='intent.evaluated',
        entity_type='intent_evaluation',
        entity_id=None,
        metadata={
            'intent': intent_result.intent,
            'confidence': round(intent_result.confidence, 4),
            'resolved_by': intent_result.resolved_by,
            'status': response['status'],
            'sufficient_context': response['sufficient_context'],
            'returned_chunk_count': len(matches),
            'top_score': matches[0].score if matches else None,
            'include_agents_only': payload.include_agents_only,
        },
    )
    return response


@tenant_admin_router.post('/knowledge/documents', status_code=201)
async def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    if payload.status == 'active':
        raise HTTPException(status_code=400, detail='Use the indexing endpoint to activate documents')
    payload_values = payload.model_dump()
    insert_columns = ['tenant_id', *KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS]
    values = []
    for column in insert_columns:
        if column == 'tenant_id':
            values.append(payload.tenant_id)
        elif column == 'metadata':
            values.append(json.dumps(payload_values[column]))
        else:
            values.append(payload_values[column])

    placeholders = [
        f'${index}::jsonb' if column == 'metadata' else f'${index}'
        for index, column in enumerate(insert_columns, start=1)
    ]
    row = await conn.fetchrow(
        f"""
        insert into app.knowledge_documents ({', '.join(insert_columns)})
        values ({', '.join(placeholders)})
        returning {KNOWLEDGE_DOCUMENT_PROJECTION}
        """,
        *values,
    )
    await audit(
        conn,
        tenant_id=payload.tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.created',
        entity_type='knowledge_document',
        entity_id=str(row['id']),
    )
    return normalize_knowledge_document(row)


@tenant_admin_router.post('/knowledge/documents/upload', status_code=201)
async def upload_knowledge_document(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    # BUG-223 (codex P2 follow-up): Content-Length pre-check ANTES de
    # `request.form()` que parsea/spoolea el body. Sin esto, el body grande
    # entraba en memoria/disk-spool antes de que el check de tamaño
    # funcionara. Hard cap del settings con 2x slack multipart.
    _settings_for_cap = get_settings()
    declared_size = int(request.headers.get('content-length') or 0)
    if declared_size and declared_size > _settings_for_cap.knowledge_file_max_bytes * 2:
        raise HTTPException(
            status_code=413,
            detail=f'Upload exceeds {_settings_for_cap.knowledge_file_max_bytes} bytes',
        )

    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500, detail='python-multipart dependency is required for file uploads'
        ) from exc

    raw_tenant_id = form.get('tenant_id')
    raw_title = form.get('title')
    title = str(raw_title or '').strip()
    document_type = str(form.get('document_type') or 'reference')
    visibility = str(form.get('visibility') or 'tenant')
    file = form.get('file')
    if not raw_tenant_id or not title or not file or not hasattr(file, 'read'):
        raise HTTPException(status_code=422, detail='tenant_id, title and file are required')
    try:
        tenant_id = UUID(str(raw_tenant_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Invalid tenant_id') from exc

    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if document_type not in {'faq', 'policy', 'reference'}:
        raise HTTPException(status_code=422, detail='Unsupported document_type')
    if visibility not in {'tenant', 'agents_only', 'public'}:
        raise HTTPException(status_code=422, detail='Unsupported visibility')

    # BUG-223 (codex MEDIUM, 2026-05-18): pre-check de Content-Length contra
    # `knowledge_file_max_bytes` antes de leer el body. Sin esto, un admin
    # malicioso podía buffearar GBs en memoria del worker antes de que
    # `validate_knowledge_upload` rechazara. Aplicamos 2x slack para
    # multipart overhead (boundary + headers).
    settings_for_cap = get_settings()
    declared_size = int(request.headers.get('content-length') or 0)
    if declared_size and declared_size > settings_for_cap.knowledge_file_max_bytes * 2:
        raise HTTPException(
            status_code=413,
            detail=f'Upload exceeds {settings_for_cap.knowledge_file_max_bytes} bytes',
        )

    data = await file.read()
    filename = getattr(file, 'filename', None) or 'upload.bin'
    mime_type = getattr(file, 'content_type', None)
    document_id = uuid4()
    settings = get_settings()
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    storage_secret = (
        resolve_secret_ref(storage_config.get('secret_ref'))
        if storage_config.get('backend') == 's3' and storage_config.get('secret_ref')
        else None
    )
    try:
        stored = store_knowledge_file(
            data=data,
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            filename=filename,
            mime_type=mime_type,
            settings=settings,
            backend=storage_config.get('backend'),
            bucket=storage_config.get('bucket'),
            endpoint_url=storage_config.get('endpoint_url'),
            access_key_id=storage_config.get('access_key_id'),
            secret_access_key=storage_secret,
            region_name=storage_config.get('region'),
            prefix=storage_config.get('prefix'),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    needs_async_extraction = is_binary_extractable(filename, mime_type) and not stored.extracted_text
    metadata = {
        'editor': 'admin-panel',
        'registered_source': True,
        'original_filename': filename,
        'storage_backend': stored.storage_backend,
        'storage_bucket': stored.bucket,
        'storage_key': stored.object_key,
        'size_bytes': stored.size_bytes,
    }
    if stored.extracted_text:
        metadata['extracted_text'] = stored.extracted_text
    if needs_async_extraction:
        metadata['extraction_pending'] = True

    insert_columns = [
        'id',
        'tenant_id',
        'source_type',
        'document_type',
        'title',
        'source_uri',
        'checksum',
        'mime_type',
        'content',
        'visibility',
        'status',
        'metadata',
    ]
    values_by_column = {
        'id': document_id,
        'tenant_id': tenant_id,
        'source_type': 'upload',
        'document_type': document_type,
        'title': title,
        'source_uri': stored.source_uri,
        'checksum': stored.checksum,
        'mime_type': mime_type or 'application/octet-stream',
        'content': stored.content,
        'visibility': visibility,
        'status': 'draft',
        'metadata': metadata,
    }
    values = [
        json.dumps(values_by_column[column]) if column == 'metadata' else values_by_column[column]
        for column in insert_columns
    ]
    placeholders = [
        f'${index}::jsonb' if column == 'metadata' else f'${index}'
        for index, column in enumerate(insert_columns, start=1)
    ]
    row = await conn.fetchrow(
        f"""
        insert into app.knowledge_documents ({', '.join(insert_columns)})
        values ({', '.join(placeholders)})
        returning {KNOWLEDGE_DOCUMENT_PROJECTION}
        """,
        *values,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.uploaded',
        entity_type='knowledge_document',
        entity_id=str(document_id),
        metadata={
            'storage_backend': stored.storage_backend,
            'storage_key': stored.object_key,
            'checksum': stored.checksum,
            'size_bytes': stored.size_bytes,
            'extraction_pending': needs_async_extraction,
        },
    )
    document = normalize_knowledge_document(row)
    document['_extraction_pending'] = needs_async_extraction
    return document


@tenant_admin_router.get('/knowledge/documents/{document_id}')
async def get_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
        from app.knowledge_documents
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        document_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Knowledge document not found')
    return normalize_knowledge_document(row)


@tenant_admin_router.patch('/knowledge/documents/{document_id}')
async def patch_knowledge_document(
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await conn.fetchrow(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
        from app.knowledge_documents
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        document_id,
    )
    if not current:
        raise HTTPException(status_code=404, detail='Knowledge document not found')
    current_document = normalize_knowledge_document(current)

    allowed = {
        column: value
        for column, value in payload.model_dump(exclude_unset=True).items()
        if column in KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS
    }
    if not allowed:
        return current_document

    content_changed = 'content' in allowed and allowed.get('content') != current_document.get('content')
    extracted_text_changed = (
        'metadata' in allowed
        and metadata_extracted_text(allowed.get('metadata'))
        != metadata_extracted_text(current_document.get('metadata'))
    )
    invalidates_chunks = content_changed or extracted_text_changed
    if invalidates_chunks:
        allowed['status'] = 'draft'
    elif allowed.get('status') == 'active':
        has_chunks = await conn.fetchval(
            'select exists(select 1 from app.knowledge_chunks where tenant_id=$1 and document_id=$2)',
            tenant_id,
            document_id,
        )
        if not has_chunks:
            raise HTTPException(status_code=400, detail='Use the indexing endpoint to activate documents')

    assignments = []
    values = [tenant_id, document_id]
    for column, value in allowed.items():
        values.append(json.dumps(value) if column == 'metadata' else value)
        placeholder = f'${len(values)}::jsonb' if column == 'metadata' else f'${len(values)}'
        assignments.append(f'{column}={placeholder}')

    async with conn.transaction():
        row = await conn.fetchrow(
            f"""
            update app.knowledge_documents
            set {', '.join(assignments)}
            where tenant_id=$1 and id=$2
            returning {KNOWLEDGE_DOCUMENT_PROJECTION}
            """,
            *values,
        )
        if invalidates_chunks:
            await conn.execute(
                'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
                tenant_id,
                document_id,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.updated',
        entity_type='knowledge_document',
        entity_id=str(document_id),
    )
    return normalize_knowledge_document(row)


@tenant_admin_router.post('/knowledge/documents/{document_id}/index')
async def index_knowledge_document(
    document_id: UUID,
    request: Request,
):
    """Index a knowledge document — embedding is a long-running network call.

    BUG-210 (codex HIGH): el handler antes usaba `Depends(get_db)` que
    mantiene una conn de la pool (`max_size=10`) durante toda la request,
    INCLUYENDO la llamada `build_indexing_result_async(...)` que hace 1
    request por chunk al provider de embeddings (OpenAI / Voyage / Ollama).
    Para documentos grandes esto puede tardar 30s+. Un tenant admin
    malicioso podía lanzar 10 reindexes concurrentes y agotar la pool —
    DoS efectivo para TODOS los tenants.

    Fix: acquire conn ad-hoc en 2 fases —
      1) SELECT del documento (rápido, libera conn)
      2) (sin conn) embedding network call
      3) Re-acquire conn para el UPDATE + INSERT transaccional (rápido)

    Esto bound la ocupación de pool a milisegundos por checkout en vez de
    segundos. La fase 3 sigue siendo transactional para mantener atomicidad
    (status flip + chunk insert).
    """
    settings = get_settings()

    # Phase 1: load the doc with a short-lived conn — wrapped in transaction
    # para que `set_config('app.tenant_id', ..., true)` (is_local=true) aplique
    # al SELECT siguiente (Codex P1 follow-up: sin transaction el `is_local`
    # solo cubría el statement de set_config y el SELECT corría con
    # `app.current_tenant_id()` NULL → RLS bloqueaba el row y todo admin veía
    # 404). También `ensure_tenant_access(...)` siempre se ejecuta para que la
    # DB-role check (admin actual en `user_tenant_roles`) corra incluso cuando
    # el JWT trae `tenant_id` scoped — sino, un JWT admin stale pero membresía
    # downgradeada bypasea el gate (Codex P1 follow-up).
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            tenant_id = await tenant_id_from_request(request, conn)
            await ensure_tenant_access(request, tenant_id, conn)
            await conn.execute(
                "select set_config('app.tenant_id', $1, true)",
                str(tenant_id),
            )
            document = await conn.fetchrow(
                f"""
                select {KNOWLEDGE_DOCUMENT_PROJECTION}
                from app.knowledge_documents
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                document_id,
            )
            # AUDIT-49: cargar `no_train` per-tenant para gate del embedding
            # provider cloud en Phase 2. Si la fila no existe (tenant viejo),
            # fail-closed a `True` (bloquea cloud).
            settings_row = await conn.fetchrow(
                'select no_train from app.tenant_settings where tenant_id=$1',
                tenant_id,
            )
    if not document:
        raise HTTPException(status_code=404, detail='Knowledge document not found')
    tenant_no_train: bool | None = (
        bool(settings_row['no_train'])
        if settings_row and settings_row['no_train'] is not None
        else True
    )

    # Phase 2: embedding call WITHOUT holding a conn.
    try:
        result = await build_indexing_result_async(
            normalize_knowledge_document(document),
            max_tokens=settings.rag_chunk_max_tokens,
            overlap_tokens=settings.rag_chunk_overlap_tokens,
            embedding_dimensions=settings.rag_embedding_dimensions,
            embedding_provider=settings.rag_embedding_provider,
            embedding_model=settings.rag_embedding_model,
            embedding_api_key=settings.rag_embedding_api_key,
            tenant_no_train=tenant_no_train,
        )
    except (ValueError, RuntimeError) as exc:
        # BUG-211 (codex MEDIUM): el `detail=str(exc)` exponía errores raw
        # del provider de embeddings (OpenAI/Voyage/Ollama) al tenant admin,
        # incluyendo a veces prefijos de API key, account/project ids, request
        # IDs internos, URLs de fallback, etc. Cualquiera con rol admin del
        # tenant puede triggerear este endpoint y leer el error de respuesta.
        # Fix: log full exception SERVER-side (audit metadata para forensia),
        # responder al cliente con un mensaje genérico tenant-safe. La
        # excepción ValueError sí puede sobrevivir el str porque viene del
        # módulo de RAG (no del provider) — es validation feedback.
        full_error = str(exc)
        log.warning(
            'knowledge_document.indexing_provider_failure',
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            exc_type=type(exc).__name__,
            error=full_error,
        )
        # Re-acquire conn for the failure audit + status update — wrapped in
        # transaction so RLS sees `app.tenant_id` (Codex P1 follow-up).
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "select set_config('app.tenant_id', $1, true)",
                    str(tenant_id),
                )
                await conn.execute(
                    """
                    update app.knowledge_documents
                    set status='failed', metadata=metadata || $3::jsonb
                    where tenant_id=$1 and id=$2
                    """,
                    tenant_id,
                    document_id,
                    json.dumps({'indexing_error': full_error}),
                )
                await audit(
                    conn,
                    tenant_id=tenant_id,
                    actor_type=request.state.actor_type,
                    actor_id=request.state.actor_id,
                    action='knowledge_document.index_failed',
                    entity_type='knowledge_document',
                    entity_id=str(document_id),
                    metadata={'error': full_error},
                )
        if isinstance(exc, ValueError):
            status_code = 422
            client_detail = full_error
        else:
            status_code = 502
            client_detail = (
                'Embedding provider unavailable. The error has been logged '
                'server-side; check the document indexing_error metadata or '
                'the audit log if more detail is required.'
            )
        raise HTTPException(status_code=status_code, detail=client_detail) from exc

    # Phase 3: re-acquire conn for the transactional persistence.
    # Codex P1 follow-up: set_config dentro de transaction.
    indexing_started_at = datetime.now(UTC).isoformat()
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "select set_config('app.tenant_id', $1, true)",
                str(tenant_id),
            )
            await conn.execute(
                """
                update app.knowledge_documents
                set status='indexing', metadata=metadata || $3::jsonb
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                document_id,
                json.dumps(
                    {
                        'last_indexing_started_at': indexing_started_at,
                        'embedding_provider': result.embedding_provider,
                        'embedding_model': result.embedding_model,
                        'embedding_dimensions': result.embedding_dimensions,
                    }
                ),
            )
            await conn.execute(
                'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
                tenant_id,
                document_id,
            )
            for chunk in result.chunks:
                await conn.execute(
                    """
                    insert into app.knowledge_chunks (
                      tenant_id, document_id, chunk_index, section_path, chunk_text,
                      token_count, embedding, metadata
                    )
                    values ($1,$2,$3,$4,$5,$6,$7::vector,$8::jsonb)
                    """,
                    tenant_id,
                    document_id,
                    chunk.chunk_index,
                    chunk.section_path,
                    chunk.chunk_text,
                    chunk.token_count,
                    vector_literal(chunk.embedding),
                    json.dumps(chunk.metadata),
                )
            indexing_completed_at = datetime.now(UTC).isoformat()
            row = await conn.fetchrow(
                f"""
                update app.knowledge_documents
                set status='active', metadata=metadata || $3::jsonb
                where tenant_id=$1 and id=$2
                returning {KNOWLEDGE_DOCUMENT_PROJECTION}
                """,
                tenant_id,
                document_id,
                json.dumps(
                    {
                        'chunk_count': len(result.chunks),
                        'sanitized_warning_count': result.sanitized_warning_count,
                        'last_indexing_completed_at': indexing_completed_at,
                    }
                ),
            )
        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='knowledge_document.indexed',
            entity_type='knowledge_document',
            entity_id=str(document_id),
            metadata={
                'chunk_count': len(result.chunks),
                'sanitized_warning_count': result.sanitized_warning_count,
                'embedding_provider': result.embedding_provider,
                'embedding_model': result.embedding_model,
            },
        )
    response = normalize_knowledge_document(row)
    response['indexing'] = {
        'chunk_count': len(result.chunks),
        'sanitized_warning_count': result.sanitized_warning_count,
        'embedding_provider': result.embedding_provider,
        'embedding_model': result.embedding_model,
        'embedding_dimensions': result.embedding_dimensions,
    }
    return response


@tenant_admin_router.post('/knowledge/reindex-all')
async def reindex_all_knowledge_documents(
    request: Request,
):
    """Re-index all active knowledge documents for the tenant.

    BUG-210 (codex HIGH): mismo pattern de DoS que `index_knowledge_document`
    — el handler ANTES mantenía `Depends(get_db)` durante un loop que
    podía durar MINUTOS (embedding API call por chunk * N docs). Un admin
    malicioso con catálogo grande podía agotar la pool global trivialmente.
    Fix: acquire conn ad-hoc para SELECT de docs, embedding sin conn,
    re-acquire conn por doc para la persistencia transaccional.
    """
    settings = get_settings()

    # Phase 1: load doc list — wrapped in transaction + always run
    # ensure_tenant_access (Codex P1 follow-up: sin transaction el is_local
    # del set_config no aplica al SELECT y RLS bloquea; sin ensure_tenant_access
    # un JWT admin stale con membresía downgradeada bypasea el gate).
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            tenant_id = await tenant_id_from_request(request, conn)
            await ensure_tenant_access(request, tenant_id, conn)
            await conn.execute(
                "select set_config('app.tenant_id', $1, true)",
                str(tenant_id),
            )
            docs = await conn.fetch(
                f"""
                select {KNOWLEDGE_DOCUMENT_PROJECTION}
                from app.knowledge_documents
                where tenant_id=$1 and status in ('active', 'draft')
                order by updated_at asc
                """,
                tenant_id,
            )
            # AUDIT-49: gate cloud embedding provider por tenant_no_train.
            settings_row = await conn.fetchrow(
                'select no_train from app.tenant_settings where tenant_id=$1',
                tenant_id,
            )
    tenant_no_train: bool | None = (
        bool(settings_row['no_train'])
        if settings_row and settings_row['no_train'] is not None
        else True
    )

    indexed = 0
    failed = 0
    errors: list[dict] = []
    for doc in docs:
        doc_id = doc['id']
        try:
            # Phase 2a: embedding call WITHOUT holding a conn.
            result = await build_indexing_result_async(
                normalize_knowledge_document(doc),
                max_tokens=settings.rag_chunk_max_tokens,
                overlap_tokens=settings.rag_chunk_overlap_tokens,
                embedding_dimensions=settings.rag_embedding_dimensions,
                embedding_provider=settings.rag_embedding_provider,
                embedding_model=settings.rag_embedding_model,
                embedding_api_key=settings.rag_embedding_api_key,
                tenant_no_train=tenant_no_train,
            )
        except (ValueError, RuntimeError) as exc:
            # BUG-211: ver comentario en `index_knowledge_document` — el error
            # raw del provider no debe filtrarse al cliente. Aquí mismo:
            # logueamos full server-side, devolvemos solo el tipo de error +
            # detalle SI es ValueError (validation).
            full_error = str(exc)
            log.warning(
                'knowledge_reindex_all.document_failed',
                tenant_id=str(tenant_id),
                document_id=str(doc_id),
                exc_type=type(exc).__name__,
                error=full_error,
            )
            failed += 1
            if isinstance(exc, ValueError):
                errors.append({'document_id': str(doc_id), 'error': full_error})
            else:
                errors.append({
                    'document_id': str(doc_id),
                    'error': 'embedding_provider_unavailable',
                })
            continue
        # Phase 2b: re-acquire conn for transactional persistence per-doc.
        # Codex P1 follow-up: set_config(`true`) DEBE estar dentro de la
        # transaction; afuera el is_local solo cubre el statement.
        indexing_ts = datetime.now(UTC).isoformat()
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "select set_config('app.tenant_id', $1, true)",
                    str(tenant_id),
                )
                await conn.execute(
                    """
                    update app.knowledge_documents
                    set status='indexing', metadata=metadata || $3::jsonb
                    where tenant_id=$1 and id=$2
                    """,
                    tenant_id, doc_id, json.dumps({'last_indexing_started_at': indexing_ts}),
                )
                await conn.execute(
                    'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
                    tenant_id, doc_id,
                )
                for chunk in result.chunks:
                    await conn.execute(
                        """
                        insert into app.knowledge_chunks (
                          tenant_id, document_id, chunk_index, section_path, chunk_text,
                          token_count, embedding, metadata
                        )
                        values ($1,$2,$3,$4,$5,$6,$7::vector,$8::jsonb)
                        """,
                        tenant_id, doc_id,
                        chunk.chunk_index, chunk.section_path, chunk.chunk_text,
                        chunk.token_count, vector_literal(chunk.embedding),
                        json.dumps(chunk.metadata),
                    )
                await conn.execute(
                    """
                    update app.knowledge_documents
                    set status='active', metadata=metadata || $3::jsonb
                    where tenant_id=$1 and id=$2
                    """,
                    tenant_id, doc_id,
                    json.dumps({
                        'chunk_count': len(result.chunks),
                        'last_indexing_completed_at': datetime.now(UTC).isoformat(),
                        'embedding_provider': result.embedding_provider,
                        'embedding_model': result.embedding_model,
                    }),
                )
        indexed += 1

    # Phase 3: final audit with a short-lived conn — set_config dentro de
    # transaction para que RLS vea `app.tenant_id` (Codex P1 follow-up).
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "select set_config('app.tenant_id', $1, true)",
                str(tenant_id),
            )
            await audit(
                conn,
                tenant_id=tenant_id,
                actor_type=request.state.actor_type,
                actor_id=request.state.actor_id,
                action='knowledge.reindex_all',
                entity_type='tenant',
                entity_id=str(tenant_id),
                metadata={
                    'indexed': indexed,
                    'failed': failed,
                    'embedding_provider': settings.rag_embedding_provider,
                    'embedding_model': settings.rag_embedding_model,
                },
            )
    return {
        'tenant_id': str(tenant_id),
        'indexed': indexed,
        'failed': failed,
        'errors': errors,
        'embedding_provider': settings.rag_embedding_provider,
        'embedding_model': settings.rag_embedding_model,
        'embedding_dimensions': settings.rag_embedding_dimensions,
    }


@tenant_admin_router.delete('/knowledge/documents/{document_id}', status_code=204)
async def delete_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # Fetch storage metadata before deleting so we can remove the physical file
    doc = await conn.fetchrow(
        'select source_uri, metadata from app.knowledge_documents where tenant_id=$1 and id=$2',
        tenant_id, document_id,
    )
    if not doc:
        raise HTTPException(status_code=404, detail='Knowledge document not found')

    # Delete from DB — knowledge_chunks cascade automatically via FK on delete cascade
    await conn.execute(
        'delete from app.knowledge_documents where tenant_id=$1 and id=$2', tenant_id, document_id
    )

    # Delete physical file from local disk or S3.
    # NOTE: source_uri and metadata.* are tenant-admin-writable via the
    # create/patch APIs, so they cannot be trusted to determine the deletion
    # target. The storage backend, bucket, and tenant prefix are re-derived
    # from server-controlled tenant configuration and passed to
    # delete_knowledge_file(), which enforces containment of the target path
    # under the tenant's storage region before unlinking / deleting.
    storage_meta = _coerce_jsonb(doc['metadata']) or {}
    settings = get_settings()
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    storage_secret = (
        resolve_secret_ref(storage_config.get('secret_ref'))
        if storage_config.get('backend') == 's3' and storage_config.get('secret_ref')
        else None
    )
    trusted_backend = (storage_config.get('backend') or settings.knowledge_storage_backend)
    trusted_bucket = storage_config.get('bucket') or settings.knowledge_storage_bucket
    trusted_prefix = storage_config.get('prefix') or f'tenants/{tenant_id}/knowledge'
    delete_knowledge_file(
        source_uri=doc['source_uri'] or '',
        storage_backend=trusted_backend,
        object_key=storage_meta.get('storage_key'),
        bucket=trusted_bucket,
        settings=settings,
        tenant_prefix=trusted_prefix,
        expected_bucket=trusted_bucket,
        endpoint_url=storage_config.get('endpoint_url'),
        access_key_id=storage_config.get('access_key_id'),
        secret_access_key=storage_secret,
        region_name=storage_config.get('region'),
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.deleted',
        entity_type='knowledge_document',
        entity_id=str(document_id),
        metadata={
            'storage_backend': storage_meta.get('storage_backend'),
            'storage_key': storage_meta.get('storage_key'),
        },
    )
    return Response(status_code=204)


@tenant_admin_router.post('/prompts', status_code=201)
async def create_prompt(payload: PromptCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    if payload.tenant_id:
        await ensure_tenant_access(request, payload.tenant_id, conn)
    row = await conn.fetchrow("insert into app.prompt_templates (tenant_id, vertical_code, prompt_type, name, version, content, variables, checksum) values ($1,$2,$3,$4,$5,$6,$7::jsonb, encode(sha256($6::bytea),'hex')) returning *", payload.tenant_id, payload.vertical_code, payload.prompt_type, payload.name, payload.version, payload.content, json.dumps(payload.variables))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/onboarding')
async def get_tenant_onboarding(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    progress = await _load_onboarding_progress(conn, tenant_id)
    return {
        'tenant_id': str(tenant_id),
        'progress': progress,
        'steps': [
            {'step': n, **ONBOARDING_STEP_METADATA[n]}
            for n in ONBOARDING_STEPS
        ],
    }


@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/{step}/verify')
async def verify_tenant_onboarding_step(
    tenant_id: UUID,
    step: int,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    meta = _step_metadata(step)
    progress = await _load_onboarding_progress(conn, tenant_id)
    # No-skip rule: only the current step or already-completed steps can be verified.
    if step > progress['last_completed_step'] + 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f'No se puede verificar el paso {step}: primero completa el paso '
                f'{progress["last_completed_step"] + 1}.'
            ),
        )
    verifier = ONBOARDING_VERIFIERS[step]
    ready, reason, details = await verifier(conn, tenant_id)
    return {
        'tenant_id': str(tenant_id),
        'step': step,
        'key': meta['key'],
        'label': meta['label'],
        'ready': ready,
        'reason': reason,
        'details': details,
        'progress': progress,
    }


@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/{step}/complete')
async def complete_tenant_onboarding_step(
    tenant_id: UUID,
    step: int,
    request: Request,
    payload: dict | None = None,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    meta = _step_metadata(step)
    progress = await _load_onboarding_progress(conn, tenant_id)
    if step != progress['last_completed_step'] + 1:
        if step <= progress['last_completed_step']:
            raise HTTPException(status_code=409, detail=f'El paso {step} ya está completado.')
        raise HTTPException(
            status_code=409,
            detail=f'No puedes saltar al paso {step}. El siguiente paso permitido es '
                   f'{progress["last_completed_step"] + 1}.',
        )
    verifier = ONBOARDING_VERIFIERS[step]
    ready, reason, details = await verifier(conn, tenant_id)
    if not ready:
        raise HTTPException(
            status_code=422,
            detail={'step': step, 'reason': reason, 'details': details, 'key': meta['key']},
        )
    evidence = payload.get('evidence') if isinstance(payload, dict) else None
    new_steps = dict(progress['steps'])
    new_steps[str(step)] = {
        'completed_at': datetime.now(UTC).isoformat(),
        'evidence': evidence if isinstance(evidence, dict) else {},
        'details': details,
    }
    new_progress = {
        'last_completed_step': step,
        'steps': new_steps,
    }
    await conn.execute(
        'update app.tenant_settings set onboarding_progress=$2::jsonb where tenant_id=$1',
        tenant_id,
        json.dumps(new_progress),
    )
    idem = f'onboarding/{tenant_id}/step-{step}'
    await conn.execute(
        """
        insert into app.domain_events
            (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload)
        values ($1, 'tenant_onboarding', $1, 'tenant_onboarding.step_completed', $2, $3::jsonb)
        on conflict do nothing
        """,
        tenant_id,
        idem,
        json.dumps({'step': step, 'key': meta['key'], 'details': details}),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_onboarding.step_completed',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={'step': step, 'key': meta['key'], 'details': details},
    )
    refreshed = await _load_onboarding_progress(conn, tenant_id)
    return {
        'tenant_id': str(tenant_id),
        'step': step,
        'key': meta['key'],
        'label': meta['label'],
        'progress': refreshed,
    }


@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/7/send-test')
async def record_onboarding_test_message_sent(
    tenant_id: UUID,
    request: Request,
    payload: dict | None = None,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Records that the wizard sent the E2E test message to the admin's wa_id.

    The wizard delivers the actual message through the standard outbound
    endpoint; this just stamps `onboarding_progress.steps.7.test_message_sent_at`
    so the step-7 verifier can look for inbound replies that arrive after it.
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    progress = await _load_onboarding_progress(conn, tenant_id)
    if progress['last_completed_step'] < 6:
        raise HTTPException(
            status_code=409,
            detail='Completa los pasos 1..6 antes de enviar la prueba E2E.',
        )
    raw_wa_id = payload.get('wa_id') if isinstance(payload, dict) else None
    target_wa_id = str(raw_wa_id).strip() if raw_wa_id is not None else ''
    if not target_wa_id:
        raise HTTPException(
            status_code=422,
            detail='wa_id del admin es obligatorio para registrar el envío de prueba.',
        )
    sent_at = datetime.now(UTC).isoformat()
    new_steps = dict(progress['steps'])
    step_entry = dict(new_steps.get('7') or {})
    step_entry['test_message_sent_at'] = sent_at
    step_entry['target_wa_id'] = target_wa_id
    new_steps['7'] = step_entry
    new_progress = {
        'last_completed_step': progress['last_completed_step'],
        'steps': new_steps,
    }
    await conn.execute(
        'update app.tenant_settings set onboarding_progress=$2::jsonb where tenant_id=$1',
        tenant_id,
        json.dumps(new_progress),
    )
    return {
        'tenant_id': str(tenant_id),
        'step': 7,
        'test_message_sent_at': sent_at,
        'target_wa_id': target_wa_id,
    }


@tenant_admin_router.get('/tenants/{tenant_id}/readiness')
async def get_tenant_readiness(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    smoke_question: str = Query(default='horarios políticas servicios garantías precios contacto', min_length=3, max_length=1000),
    retrieval_min_score: float = Query(default=0.12, ge=0, le=1),
):
    await require_min_role('admin')(request)
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    report = await build_tenant_readiness_report(
        conn,
        tenant_id,
        smoke_question=smoke_question,
        retrieval_min_score=retrieval_min_score,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.readiness_checked',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={
            'status': report['status'],
            'not_ready_reasons': report['reasons'],
            'smoke_question': smoke_question,
        },
    )
    return report


@tenant_admin_router.get('/audit-logs')
async def list_audit_logs(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    action: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select * from app.audit_logs
        where tenant_id=$1
          and ($2::text is null or action=$2)
          and ($3::text is null or actor_type=$3)
          and ($4::text is null or entity_type=$4)
          and ($5::timestamptz is null or created_at>=$5::timestamptz)
          and ($6::timestamptz is null or created_at<=$6::timestamptz)
        order by created_at desc
        limit $7
        """,
        tenant_id, action, actor_type, entity_type, from_date, to_date, limit,
    )
    return [record_to_dict(r) for r in rows]


@tenant_admin_router.get('/audit-logs/export')
async def export_audit_logs(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    action: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select id, created_at, actor_type, actor_id, action, entity_type, entity_id, metadata
        from app.audit_logs
        where tenant_id=$1
          and ($2::text is null or action=$2)
          and ($3::text is null or actor_type=$3)
          and ($4::text is null or entity_type=$4)
          and ($5::timestamptz is null or created_at>=$5::timestamptz)
          and ($6::timestamptz is null or created_at<=$6::timestamptz)
        order by created_at desc
        limit 10000
        """,
        tenant_id, action, actor_type, entity_type, from_date, to_date,
    )
    fieldnames = ['id', 'created_at', 'actor_type', 'actor_id', 'action', 'entity_type', 'entity_id', 'metadata']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: str(v) if v is not None else '' for k, v in record_to_dict(row).items()})
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='audit_logs.exported', entity_type='tenant', entity_id=str(tenant_id))
    return Response(
        content=buf.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="audit-logs-{tenant_id}.csv"'},
    )


@tenant_admin_router.post('/contacts/{contact_id}/suppress', status_code=200)
async def suppress_contact(
    contact_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await require_min_role('admin')(request)
    tenant_id = await tenant_id_from_request(request, conn)
    existing = await conn.fetchrow('select id from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Contact not found')
    pseudo = f'suppressed+{contact_id}'
    row = await conn.fetchrow(
        """
        update app.contacts set
          display_name = null,
          phone_e164 = $3,
          wa_id = $3,
          phone_hash = decode(encode(sha256($3::bytea), 'hex'), 'hex'),
          opt_in_status = 'suppressed',
          opt_out_at = now(),
          tags = '{}',
          metadata = '{}'::jsonb
        where tenant_id=$1 and id=$2
        returning id, tenant_id, opt_in_status, updated_at
        """,
        tenant_id, contact_id, pseudo,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='contact.suppressed', entity_type='contact', entity_id=str(contact_id))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/data-export')
async def export_tenant_data(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    # TASK-0077/BUG17: data-export must double-check owner across JWT and the
    # target tenant's DB row.  ``ensure_tenant_role`` enforces both halves and
    # rejects owner-JWT-A + viewer-DB-B (and similar cross-tenant) combos.
    await ensure_tenant_role(request, conn, tenant_id, 'owner')
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    tenant = await conn.fetchrow('select * from app.tenants where id=$1', tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail='Tenant not found')
    settings = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    channels = await conn.fetch("select id, provider, status, account_mode, created_at from app.tenant_channels where tenant_id=$1", tenant_id)
    counts = await conn.fetchrow(
        """
        select
          (select count(*) from app.contacts where tenant_id=$1) as contacts,
          (select count(*) from app.conversations where tenant_id=$1) as conversations,
          (select count(*) from app.messages where tenant_id=$1) as messages,
          (select count(*) from app.service_requests where tenant_id=$1) as service_requests,
          (select count(*) from app.quotes where tenant_id=$1) as quotes,
          (select count(*) from app.knowledge_documents where tenant_id=$1) as knowledge_documents,
          (select count(*) from app.audit_logs where tenant_id=$1) as audit_log_entries
        """,
        tenant_id,
    )
    bundle = {
        'exported_at': datetime.now(UTC).isoformat(),
        'tenant': record_to_dict(tenant),
        'settings': record_to_dict(settings) if settings else {},
        'channels': [record_to_dict(ch) for ch in channels],
        'data_counts': dict(counts),
        'privacy': {
            'no_train': (settings or {}).get('no_train', True),
            'pii_policy': record_to_dict(settings).get('pii_policy', {}) if settings else {},
            'data_retention_days': 365,
            'dpa_version': '1.0',
        },
    }
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant.data_exported', entity_type='tenant', entity_id=str(tenant_id))
    content = json.dumps(bundle, default=str, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="tenant-data-{tenant_id}.json"'},
    )


@tenant_admin_router.get('/tenants/{tenant_id}/contacts/{contact_id}/export')
async def export_contact_data(
    tenant_id: UUID,
    contact_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    kinds: str = Query(
        default='consent_ledger',
        description=(
            'Comma-separated list of data kinds to include. Allowed: '
            'consent_ledger, messages, appointments, subscriptions.'
        ),
    ),
):
    """SEC-010-EXPORT-FU — contact-scoped extract for derecho de acceso /
    consent-violation claims.

    Replaces the manual SQL workaround in the consent-violation runbook.
    Returns signed JSON with audit_logs entry; never leaks cross-contact PII.
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # Validate `kinds` BEFORE touching the DB — invalid input shouldn't even
    # generate an audit entry for a request that never produced data.
    requested_kinds = tuple(
        kind.strip() for kind in kinds.split(',') if kind.strip()
    )
    if not requested_kinds:
        raise HTTPException(
            status_code=422,
            detail='At least one kind is required.',
        )
    invalid = [k for k in requested_kinds if k not in _CONTACT_EXPORT_ALLOWED_KINDS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                f'Invalid kinds: {invalid}. '
                f'Allowed: {list(_CONTACT_EXPORT_ALLOWED_KINDS)}.'
            ),
        )

    # Validate contact belongs to tenant. Even with RLS enforcing this, the
    # explicit check produces a clean 404 (vs an opaque "row not found") and
    # ensures the audit log records the lookup attempt.
    contact_row = await conn.fetchrow(
        """
        select id, phone_e164, opt_in_status, opt_in_at, opt_out_at,
               consent_version, created_at
        from app.contacts
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        contact_id,
    )
    if contact_row is None:
        raise HTTPException(status_code=404, detail='Contact not found')

    bundle: dict[str, Any] = {
        'exported_at': datetime.now(UTC).isoformat(),
        'tenant_id': str(tenant_id),
        'contact_id': str(contact_id),
        'contact': record_to_dict(contact_row),
        'kinds': list(requested_kinds),
    }

    if 'consent_ledger' in requested_kinds:
        rows = await conn.fetch(
            """
            select id, event, channel, legal_basis, purpose, copy_shown,
                   evidence_payload, occurred_at, ip, user_agent
            from app.consent_ledger
            where tenant_id=$1 and contact_id=$2
            order by occurred_at desc, id desc
            """,
            tenant_id,
            contact_id,
        )
        bundle['consent_ledger'] = [record_to_dict(r) for r in rows]

    if 'messages' in requested_kinds:
        # Join through `conversations` to filter by contact — `messages` has
        # no direct `contact_id` column (intentional: a conversation owns the
        # contact relationship). The tenant_id guard on BOTH sides is a
        # defense-in-depth check against the (impossible-given-the-FK)
        # scenario of a conversation in a different tenant.
        rows = await conn.fetch(
            """
            select m.id, m.conversation_id, m.external_message_id, m.direction,
                   m.sender_actor_type, m.sender_actor_id, m.message_type,
                   m.body_text, m.media_id, m.mime_type, m.payload, m.status,
                   m.received_at, m.sent_at, m.delivered_at, m.read_at,
                   m.failed_at, m.error_code, m.error_message, m.created_at
            from app.messages m
            join app.conversations c on c.id = m.conversation_id
            where m.tenant_id=$1 and c.tenant_id=$1 and c.contact_id=$2
            order by m.created_at desc, m.id desc
            """,
            tenant_id,
            contact_id,
        )
        bundle['messages'] = [record_to_dict(r) for r in rows]

    if 'appointments' in requested_kinds:
        rows = await conn.fetch(
            """
            select id, service_id, resource_id, service_code, starts_at,
                   ends_at, timezone, status, location_type, confirmation_status,
                   notes, payment_status, payment_amount, payment_currency,
                   created_at
            from app.appointments
            where tenant_id=$1 and contact_id=$2
            order by starts_at desc, id desc
            """,
            tenant_id,
            contact_id,
        )
        bundle['appointments'] = [record_to_dict(r) for r in rows]

    if 'subscriptions' in requested_kinds:
        rows = await conn.fetch(
            """
            select id, plan_id, status, started_at, next_billing_at,
                   cancelled_at, payment_provider, last_invoice_status,
                   last_invoice_at, created_at, updated_at
            from app.contact_subscriptions
            where tenant_id=$1 and contact_id=$2
            order by started_at desc, id desc
            """,
            tenant_id,
            contact_id,
        )
        bundle['subscriptions'] = [record_to_dict(r) for r in rows]

    # Canonical JSON for signature — `default=str` rinde datetimes en formato
    # Python `str(dt)` (`'2026-05-18 13:46:28+00:00'`, con espacio). El cliente
    # tiene que verificar la firma contra los bytes que recibe, por lo que la
    # respuesta DEBE servirse con EXACTAMENTE el mismo canonical_json firmado
    # (no via el serializer default de FastAPI, que rinde datetimes con `T`).
    #
    # BUG-231 (codex P1 sobre PR #18 SEC-010-EXPORT-FU): la versión anterior
    # devolvía `{'data': bundle, ...}` y FastAPI serializaba `bundle` con su
    # propio JSON encoder, produciendo bytes distintos de los firmados — la
    # verificación documentada en `docs/runbooks/consent-violation-claim.md`
    # via `jq -S -c '.data' | openssl dgst -sha256 -hmac "$JWT_SECRET"` no
    # matcheaba nunca. Fix: armar el response manualmente con el bundle
    # canonical embebido como string crudo en `data_canonical` para que el
    # cliente sepa qué firmar; el operador puede ejecutar
    # `echo -n "$(jq -r .data_canonical archivo.json)" | openssl dgst ...`.
    bundle_canonical = json.dumps(
        bundle, default=str, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    )
    signature = sign_export_bundle(bundle_canonical)

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact.exported_for_consent_claim',
        entity_type='contact',
        entity_id=str(contact_id),
        metadata={
            'kinds': list(requested_kinds),
            'signature': signature,
            'exported_at': bundle['exported_at'],
        },
    )

    # BUG-231: devolver el canonical_json crudo (string) además del bundle
    # parseado. El operador firma/verifica `data_canonical` (los mismos bytes
    # que el server firmó); `data` queda como conveniencia para inspección
    # programática. Mantiene back-compat para clientes que solo leían `data`.
    return {
        'data': bundle,
        'data_canonical': bundle_canonical,
        'signature': signature,
        'signature_algorithm': 'HMAC-SHA256',
    }


@tenant_admin_router.get('/tenants/{tenant_id}/segments')
async def list_contact_segments(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    kind: str | None = Query(default=None, pattern='^(dynamic|static)$'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {SEGMENT_PROJECTION}
        from app.contact_segments
        where tenant_id=$1 and ($2::text is null or kind=$2)
        order by is_system desc, name asc
        """,
        tenant_id,
        kind,
    )
    return [normalize_segment_row(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/segments', status_code=201)
async def create_contact_segment(
    tenant_id: UUID,
    payload: ContactSegmentCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rules = normalize_segment_rules(payload.rules) if payload.kind == 'dynamic' else {}
    created_by = await current_user_id_from_request(request, conn)
    initial_count = (
        await count_segment_contacts(conn, tenant_id, rules) if payload.kind == 'dynamic' else 0
    )
    row = await conn.fetchrow(
        f"""
        insert into app.contact_segments (
          tenant_id, name, description, kind, rules, contact_count, last_refreshed_at, created_by
        )
        values ($1, $2, $3, $4, $5::jsonb, $6, case when $4='dynamic' then now() else null end, $7)
        returning {SEGMENT_PROJECTION}
        """,
        tenant_id,
        payload.name.strip(),
        payload.description,
        payload.kind,
        json.dumps(rules),
        initial_count,
        created_by,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.created',
        entity_type='contact_segment',
        entity_id=str(row['id']),
        metadata={'kind': payload.kind, 'contact_count': initial_count},
    )
    return normalize_segment_row(row)


@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}')
async def get_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    return normalize_segment_row(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/segments/{segment_id}')
async def patch_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    payload: ContactSegmentUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return normalize_segment_row(row)
    next_kind = data.get('kind') or row['kind']
    if 'rules' in data:
        rules = normalize_segment_rules(data['rules']) if next_kind == 'dynamic' else {}
    else:
        rules = None
    new_count = None
    if next_kind == 'dynamic' and rules is not None:
        new_count = await count_segment_contacts(conn, tenant_id, rules)
    updated = await conn.fetchrow(
        f"""
        update app.contact_segments
        set name=coalesce($3, name),
            description=coalesce($4, description),
            kind=coalesce($5, kind),
            rules=coalesce($6::jsonb, rules),
            contact_count=coalesce($7, contact_count),
            last_refreshed_at=case when $5='dynamic' and $6 is not null then now() else last_refreshed_at end,
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {SEGMENT_PROJECTION}
        """,
        tenant_id,
        segment_id,
        data.get('name'),
        data.get('description'),
        data.get('kind'),
        json.dumps(rules) if rules is not None else None,
        new_count,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.updated',
        entity_type='contact_segment',
        entity_id=str(segment_id),
        metadata={'fields': sorted(data.keys())},
    )
    return normalize_segment_row(updated)


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/segments/{segment_id}', status_code=204
)
async def delete_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    if row['is_system']:
        raise HTTPException(
            status_code=409,
            detail='System segments cannot be deleted; edit the rules instead.',
        )
    await conn.execute(
        'delete from app.contact_segments where tenant_id=$1 and id=$2',
        tenant_id,
        segment_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.deleted',
        entity_type='contact_segment',
        entity_id=str(segment_id),
    )


@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}/preview')
async def preview_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    rules = parse_json_object(row['rules'], default={})
    if row['kind'] == 'dynamic':
        sample = await evaluate_segment_rules(conn, tenant_id, rules, limit=limit)
        total = await count_segment_contacts(conn, tenant_id, rules)
    else:
        # Static segments: pull the most recent snapshot's members.
        members = await conn.fetch(
            """
            select m.contact_id as contact_id, c.display_name, c.phone_e164, c.opt_in_status
            from app.contact_segment_members m
            join app.contacts c on c.tenant_id=m.tenant_id and c.id=m.contact_id
            where m.tenant_id=$1 and m.segment_id=$2
              and m.snapshot_at = (
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$2
              )
            order by c.display_name nulls last
            limit $3
            """,
            tenant_id,
            segment_id,
            limit,
        )
        sample = [dict(r) for r in members]
        total = await conn.fetchval(
            """
            select count(*) from app.contact_segment_members
            where segment_id=$1
              and snapshot_at = (
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$1
              )
            """,
            segment_id,
        ) or 0
    return {
        'segment_id': str(segment_id),
        'contact_count': int(total),
        'sample': [
            {
                'contact_id': str(item['contact_id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample
        ],
    }


@tenant_admin_router.post('/tenants/{tenant_id}/segments/{segment_id}/refresh')
async def refresh_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    rules = parse_json_object(row['rules'], default={})
    count, _snapshot_at = await snapshot_segment_members(conn, tenant_id, segment_id, rules)
    refreshed = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.refreshed',
        entity_type='contact_segment',
        entity_id=str(segment_id),
        metadata={'contact_count': count},
    )
    return normalize_segment_row(refreshed)


@tenant_admin_router.post('/tenants/{tenant_id}/segments/{segment_id}/members')
async def set_static_segment_members(
    tenant_id: UUID,
    segment_id: UUID,
    payload: ContactSegmentMembersAssign,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    if row['kind'] != 'static':
        raise HTTPException(
            status_code=409,
            detail='Only static segments accept manually managed members.',
        )
    snapshot_at = await conn.fetchval('select now()')
    if payload.contact_ids:
        await conn.executemany(
            """
            insert into app.contact_segment_members (tenant_id, segment_id, contact_id, snapshot_at)
            values ($1, $2, $3, $4)
            on conflict (segment_id, contact_id, snapshot_at) do nothing
            """,
            [(tenant_id, segment_id, cid, snapshot_at) for cid in payload.contact_ids],
        )
    await conn.execute(
        """
        update app.contact_segments
        set contact_count=$3, last_refreshed_at=$4, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        segment_id,
        len(payload.contact_ids),
        snapshot_at,
    )
    return normalize_segment_row(
        await _fetch_segment_or_404(conn, tenant_id, segment_id)
    )


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns', status_code=201)
async def create_campaign(
    tenant_id: UUID,
    payload: CampaignCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _ensure_template_approved(conn, tenant_id, payload.template_id)
    segment = _campaign_segment_filter_dict(payload.segment_filter)
    segment_row = None
    if payload.segment_id is not None:
        segment_row = await _fetch_segment_or_404(conn, tenant_id, payload.segment_id)
        recipient_count = int(segment_row['contact_count'] or 0)
    else:
        recipient_count = await count_campaign_recipients(conn, tenant_id, segment)
    created_by = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        f"""
        insert into app.campaigns (
          tenant_id, name, template_id, template_variables,
          segment_filter, segment_id, scheduled_at, recipient_count,
          cost_amount, cost_currency, attribution_window_days, created_by
        )
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8,
                $9, coalesce($10, 'COP'), coalesce($11, 14), $12)
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        payload.name.strip(),
        payload.template_id,
        json.dumps(payload.template_variables or {}),
        json.dumps(segment),
        payload.segment_id,
        payload.scheduled_at,
        recipient_count,
        payload.cost_amount,
        (payload.cost_currency or '').upper() or None,
        payload.attribution_window_days,
        created_by,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.created',
        entity_type='campaign',
        entity_id=str(row['id']),
        metadata={
            'template_id': str(payload.template_id),
            'recipient_count': recipient_count,
        },
    )
    return normalize_campaign(row)


@tenant_admin_router.get('/tenants/{tenant_id}/campaigns')
async def list_campaigns(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {CAMPAIGN_PROJECTION}
        from app.campaigns
        where tenant_id=$1
          and ($2::text is null or status=$2)
        order by created_at desc
        """,
        tenant_id,
        status_filter,
    )
    return [normalize_campaign(row) for row in rows]


@tenant_admin_router.get('/tenants/{tenant_id}/campaigns/{campaign_id}')
async def get_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    # Counter refresh on read so the admin panel sees the latest metrics
    # rolled up from app.messages (sent/delivered/read/failed).
    if row['status'] in ('running', 'completed'):
        await refresh_campaign_counters(conn, tenant_id, campaign_id)
        row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    return normalize_campaign(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/campaigns/{campaign_id}')
async def patch_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: CampaignUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] != 'draft':
        raise HTTPException(
            status_code=409,
            detail='Only campaigns in draft can be edited',
        )
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return normalize_campaign(row)
    if payload.template_id is not None:
        await _ensure_template_approved(conn, tenant_id, payload.template_id)
    segment = (
        _campaign_segment_filter_dict(payload.segment_filter)
        if payload.segment_filter is not None
        else None
    )
    next_segment_id = data.get('segment_id') if 'segment_id' in data else row['segment_id']
    if next_segment_id is not None and 'segment_id' in data:
        segment_row = await _fetch_segment_or_404(conn, tenant_id, next_segment_id)
        new_recipient_count = int(segment_row['contact_count'] or 0)
    elif segment is not None:
        new_recipient_count = await count_campaign_recipients(conn, tenant_id, segment)
    else:
        new_recipient_count = None
    cost_currency_value = data.get('cost_currency')
    if isinstance(cost_currency_value, str):
        cost_currency_value = cost_currency_value.upper()
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set name=coalesce($3, name),
            template_id=coalesce($4, template_id),
            template_variables=coalesce($5::jsonb, template_variables),
            segment_filter=coalesce($6::jsonb, segment_filter),
            segment_id=case when $9 then $10 else segment_id end,
            scheduled_at=coalesce($7, scheduled_at),
            recipient_count=coalesce($8, recipient_count),
            cost_amount=case when $11 then $12 else cost_amount end,
            cost_currency=coalesce($13, cost_currency),
            attribution_window_days=coalesce($14, attribution_window_days),
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
        data.get('name'),
        data.get('template_id'),
        json.dumps(data['template_variables']) if 'template_variables' in data else None,
        json.dumps(segment) if segment is not None else None,
        data.get('scheduled_at'),
        new_recipient_count,
        'segment_id' in data,
        data.get('segment_id'),
        'cost_amount' in data,
        data.get('cost_amount'),
        cost_currency_value,
        data.get('attribution_window_days'),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.updated',
        entity_type='campaign',
        entity_id=str(campaign_id),
        metadata={'fields': sorted(data.keys())},
    )
    return normalize_campaign(updated)


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/preview')
async def preview_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['segment_id'] is not None:
        seg_row = await _fetch_segment_or_404(conn, tenant_id, row['segment_id'])
        rules = parse_json_object(seg_row['rules'], default={})
        total = await count_segment_contacts(conn, tenant_id, rules)
        sample_rows = await evaluate_segment_rules(conn, tenant_id, rules, limit=5)
        sample = [
            {
                'id': str(item['contact_id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample_rows
        ]
    else:
        segment = parse_json_object(row['segment_filter'], default={})
        total = await count_campaign_recipients(conn, tenant_id, segment)
        sample_rows = await evaluate_segment(conn, tenant_id, segment, limit=5)
        sample = [
            {
                'id': str(item['id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample_rows
        ]
    return {
        'recipient_count': total,
        'sample': sample,
    }


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/launch')
async def launch_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: CampaignLaunch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] not in ('draft', 'scheduled'):
        raise HTTPException(
            status_code=409,
            detail=f'Campaign cannot be launched from status={row["status"]}',
        )
    await _ensure_template_approved(conn, tenant_id, row['template_id'])
    next_scheduled = payload.scheduled_at or row['scheduled_at'] or datetime.now(UTC)
    launched_snapshot_at = None
    if row['segment_id'] is not None:
        seg_row = await _fetch_segment_or_404(conn, tenant_id, row['segment_id'])
        rules = parse_json_object(seg_row['rules'], default={})
        if seg_row['kind'] == 'dynamic':
            _count, launched_snapshot_at = await snapshot_segment_members(
                conn, tenant_id, row['segment_id'], rules
            )
        else:
            # Static segment: use the latest manual snapshot.
            launched_snapshot_at = await conn.fetchval(
                """
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$1
                """,
                row['segment_id'],
            )
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set status='scheduled', scheduled_at=$3,
            launched_snapshot_at=coalesce($4, launched_snapshot_at),
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
        next_scheduled,
        launched_snapshot_at,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.launched',
        entity_type='campaign',
        entity_id=str(campaign_id),
        metadata={'scheduled_at': next_scheduled.isoformat()},
    )
    return normalize_campaign(updated)


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/cancel')
async def cancel_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] in ('completed', 'cancelled'):
        raise HTTPException(
            status_code=409,
            detail=f'Campaign already in terminal status={row["status"]}',
        )
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set status='cancelled', completed_at=now(), updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.cancelled',
        entity_type='campaign',
        entity_id=str(campaign_id),
    )
    return normalize_campaign(updated)


@tenant_admin_router.get('/tenants/{tenant_id}/legal')
async def list_legal_documents(
    tenant_id: UUID,
    request: Request,
    kind: str | None = Query(default=None, pattern='^(terms|privacy|consent)$'),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if kind:
        rows = await conn.fetch(
            """
            select id, tenant_id, kind, language, version, title, content_md,
                   published_at, archived_at, created_at
            from app.tenant_legal_documents
            where tenant_id=$1 and kind=$2
            order by language asc, version desc
            """,
            tenant_id,
            kind,
        )
    else:
        rows = await conn.fetch(
            """
            select id, tenant_id, kind, language, version, title, content_md,
                   published_at, archived_at, created_at
            from app.tenant_legal_documents
            where tenant_id=$1
            order by kind asc, language asc, version desc
            """,
            tenant_id,
        )
    return {'documents': [_legal_row_to_dict(row) for row in rows]}


@tenant_admin_router.post('/tenants/{tenant_id}/legal', status_code=201)
async def create_legal_document_draft(
    tenant_id: UUID,
    payload: LegalDocumentDraftCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Create a new draft (unpublished) version.

    A subsequent ``POST /tenants/{tid}/legal/{id}/publish`` flips the
    ``published_at`` timestamp and the schema trigger archives the previous
    live version for the same (kind, language).
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    next_version = await conn.fetchval(
        """
        select coalesce(max(version), 0) + 1
        from app.tenant_legal_documents
        where tenant_id=$1 and kind=$2 and language=$3
        """,
        tenant_id,
        payload.kind,
        payload.language,
    )
    created_by = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        insert into app.tenant_legal_documents (
          tenant_id, kind, language, version, title, content_md, created_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id, tenant_id, kind, language, version, title, content_md,
                  published_at, archived_at, created_at
        """,
        tenant_id,
        payload.kind,
        payload.language,
        next_version,
        payload.title,
        payload.content_md,
        created_by,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='legal_document.drafted',
        entity_type='tenant_legal_document',
        entity_id=str(row['id']),
        metadata={'kind': payload.kind, 'language': payload.language, 'version': next_version},
    )
    return _legal_row_to_dict(row)


@tenant_admin_router.post('/tenants/{tenant_id}/legal/{document_id}/publish')
async def publish_legal_document(
    tenant_id: UUID,
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        update app.tenant_legal_documents
        set published_at = now()
        where tenant_id=$1 and id=$2 and published_at is null
        returning id, tenant_id, kind, language, version, title, content_md,
                  published_at, archived_at, created_at
        """,
        tenant_id,
        document_id,
    )
    if not row:
        existing = await conn.fetchrow(
            'select id from app.tenant_legal_documents where tenant_id=$1 and id=$2',
            tenant_id,
            document_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Legal document not found')
        raise HTTPException(status_code=409, detail='Legal document already published')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='legal_document.published',
        entity_type='tenant_legal_document',
        entity_id=str(row['id']),
        metadata={
            'kind': row['kind'],
            'language': row['language'],
            'version': row['version'],
            'published_at': row['published_at'].isoformat(),
        },
    )
    return _legal_row_to_dict(row)

