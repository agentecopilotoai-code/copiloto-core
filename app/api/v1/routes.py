import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.schemas import (
    PlatformTenantUpdate,
    TenantUpdate,
)
from app.core.config import get_settings
from app.core.security import (
    authenticate_request,
    has_jwt_role,
    require_mfa_for_privileged,
    require_min_role,
    require_platform_owner,
    require_service,
)
from app.core.signed_cookies import unpack_signed_payload
from app.db.pool import record_to_dict
from app.services.audit import audit
from app.services.rag_retrieval import (
    END_USER_VISIBILITY,
    build_grounded_answer,
    rank_chunks,
)
from app.services.whatsapp import (
    secret_ref_is_configured,
    token_ref_is_configured,
)
from app.services.legal import (  # noqa: F401 — LEGAL_KINDS re-exported for legal-document tests/handlers
    LEGAL_KIND_LABELS_ES,
    LEGAL_KINDS,
    render_markdown_to_safe_html,
)
from app.services.subscriptions import (  # noqa: F401 — re-exported for webhook handler + static tests
    INVOICE_FAILED_PURPOSE,
    INVOICE_FAILED_TEMPLATE,
    extract_subscription_event,
)

log = structlog.get_logger()


# Extracted to app/api/v1/_helpers/parsing.py
from app.api.v1._helpers.parsing import (  # noqa: E402,F401 — re-exported for backward compat
    _coerce_jsonb,
    metadata_extracted_text,
    parse_json_object,
)

# Extracted to app/api/v1/_helpers/secrets.py
from app.api.v1._helpers.secrets import (  # noqa: E402,F401 — re-exported for backward compat
    tenant_knowledge_s3_secret_ref,
    tenant_secret_ref,
    write_tenant_secret,
)

# Extracted to app/api/v1/_helpers/widget_proxy.py
from app.api.v1._helpers.widget_proxy import (  # noqa: E402,F401 — re-exported for backward compat
    tenant_brand_logo_proxy_url,
)

# Extracted to app/api/v1/_helpers/legal.py
from app.api.v1._helpers.legal import html_escape_attr  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/whatsapp_pure.py
from app.api.v1._helpers.whatsapp_pure import (  # noqa: E402,F401 — re-exported for backward compat
    MEDIA_MESSAGE_TYPES,
    SUPPORTED_AGENT_MESSAGE_TYPES,
    WHATSAPP_TEMPLATE_COLUMNS,
    WHATSAPP_TEMPLATE_PROJECTION,
    WHATSAPP_TEMPLATE_REQUIRED_PURPOSES,
    _WHATSAPP_WEBHOOK_DUMMY_SECRET,
    media_url_from_payload,
    normalize_whatsapp_template,
    validate_outbound_message_content,
    verify_token_hash,
    whatsapp_phone_number_id_from_payload,
)

# Extracted to app/api/v1/_helpers/knowledge_storage_config.py
from app.api.v1._helpers.knowledge_storage_config import (  # noqa: E402,F401 — re-exported for backward compat
    default_knowledge_storage_config,
    normalize_knowledge_storage_config,
    public_knowledge_storage_config,
)

# Extracted to app/api/v1/_helpers/knowledge_documents.py
from app.api.v1._helpers.knowledge_documents import (  # noqa: E402,F401 — re-exported for backward compat
    KNOWLEDGE_DOCUMENT_PROJECTION,
    KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS,
    KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS,
    normalize_knowledge_document,
    normalize_knowledge_documents,
)

# Extracted to app/api/v1/_helpers/slots.py
from app.api.v1._helpers.slots import (  # noqa: E402,F401 — re-exported for backward compat
    WEEKDAY_KEYS,
    compute_free_slots,
    minutes_to_hhmm,
    parse_iso_date,
    slot_start_minutes,
    working_hours_for_date,
)

# Extracted to app/api/v1/_helpers/onboarding.py
from app.api.v1._helpers.onboarding import (  # noqa: E402,F401 — re-exported for backward compat
    ONBOARDING_CONSENT_TEMPLATE_NAME,
    ONBOARDING_STEP_METADATA,
    ONBOARDING_STEPS,
    ONBOARDING_TOTAL_STEPS,
    _step_metadata,
    normalize_onboarding_progress,
)

# Extracted to app/api/v1/_helpers/readiness.py
from app.api.v1._helpers.readiness import (  # noqa: E402,F401 — re-exported for backward compat
    readiness_check,
    readiness_positive_int,
    readiness_response,
    readiness_truthy_object,
)

# Extracted to app/api/v1/_helpers/health.py
from app.api.v1._helpers.health import _derive_health_services  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/analytics.py
from app.api.v1._helpers.analytics import (  # noqa: E402,F401 — re-exported for backward compat
    _funnel_step,
    _range_bounds,
    _resolve_analytics_range,
)

# Extracted to app/api/v1/_helpers/validators.py
from app.api.v1._helpers.validators import (  # noqa: E402,F401 — re-exported for backward compat
    NOTIFICATION_CHANNEL_IDS,
    _validate_digest_recipients,
    _validate_notification_matrix,
    _validate_timezone,
)

# Extracted to app/api/v1/_helpers/auth_misc.py
from app.api.v1._helpers.auth_misc import (  # noqa: E402,F401 — re-exported for backward compat
    _TENANT_ROLE_LEVELS,
    _tenant_db_role_meets,
)

# Extracted to app/api/v1/_helpers/sessions.py
from app.api.v1._helpers.sessions import AUTH_SESSION_ACTIVE_HOURS  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/support_mode.py
from app.api.v1._helpers.support_mode import (  # noqa: E402,F401 — re-exported for backward compat
    SUPPORT_MODE_MIN_JUSTIFICATION_LEN,
    SUPPORT_MODE_TTL_SECONDS,
)

# Extracted to app/api/v1/_helpers/platform_filters.py
from app.api.v1._helpers.platform_filters import (  # noqa: E402,F401 — re-exported for backward compat
    _CONTACT_EXPORT_ALLOWED_KINDS,
    _FLEET_LIST_STATUS_PATTERN,
    _INCIDENT_KIND_PATTERN,
    _INCIDENT_STATUS_PATTERN,
)

# Extracted to app/api/v1/_helpers/widget.py
from app.api.v1._helpers.widget import _build_widget_snippet  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/payments_pure.py
from app.api.v1._helpers.payments_pure import (  # noqa: E402,F401 — re-exported for backward compat
    _appointment_payment_external_ref,
    _appointment_payment_summary,
    _normalize_payment_settings,
    _parse_appointment_external_ref,
    _public_payment_settings,
)

# Extracted to app/api/v1/_helpers/quotes.py
from app.api.v1._helpers.quotes import (  # noqa: E402,F401 — re-exported for backward compat
    _build_quote_summary_text,
    _compute_quote_subtotal,
)

# Extracted to app/api/v1/_helpers/projections.py
from app.api.v1._helpers.projections import (  # noqa: E402,F401 — re-exported for backward compat
    CAMPAIGN_PROJECTION,
    MEDIA_ASSET_COLUMNS,
    MESSENGER_CHANNEL_PROJECTION,
    PROMOTION_COLUMNS,
    QUALIFICATION_PROJECTION,
    SEGMENT_PROJECTION,
    SERVICE_CATALOG_COLUMNS,
    SERVICE_CATALOG_PROJECTION,
    WEB_CHANNEL_PROJECTION,
)

# Extracted to app/api/v1/_helpers/normalizers.py
from app.api.v1._helpers.normalizers import (  # noqa: E402,F401 — re-exported for backward compat
    _digest_subscription_to_dict,
    _legal_row_to_dict,
    _normalize_messenger_channel,
    _normalize_web_channel,
    _serialize_profile,
    normalize_campaign,
    normalize_media_asset,
    normalize_promotion,
    normalize_qualification_question,
    normalize_segment_row,
    normalize_service_catalog_row,
)

# Extracted to app/api/v1/_helpers/notifications_db.py
from app.api.v1._helpers.notifications_db import notify_operations_change  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/whatsapp_db.py
from app.api.v1._helpers.whatsapp_db import (  # noqa: E402,F401 — re-exported for backward compat
    _fetch_template_or_404,
    _resolve_channel_for_template,
    upsert_whatsapp_contact,
)

# Extracted to app/api/v1/_helpers/booking_db.py
from app.api.v1._helpers.booking_db import (  # noqa: E402,F401 — re-exported for backward compat
    appointment_detail,
    ensure_resource_available,
    fetch_fallback_duration,
    fetch_service_duration,
)

# Extracted to app/api/v1/_helpers/knowledge_storage_db.py
from app.api.v1._helpers.knowledge_storage_db import fetch_tenant_knowledge_storage_config  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/onboarding_db.py
from app.api.v1._helpers.onboarding_db import (  # noqa: E402,F401 — re-exported for backward compat
    ONBOARDING_VERIFIERS,
    _load_onboarding_progress,
    _verify_onboarding_business_details,
    _verify_onboarding_business_hours,
    _verify_onboarding_consent_template,
    _verify_onboarding_end_to_end_test,
    _verify_onboarding_locale_currency,
    _verify_onboarding_service_catalog,
    _verify_onboarding_whatsapp_channel,
)

# Extracted to app/api/v1/_helpers/payments_db.py
from app.api.v1._helpers.payments_db import _fetch_tenant_payment_settings  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/campaigns_db.py
from app.api.v1._helpers.campaigns_db import (  # noqa: E402,F401 — re-exported for backward compat
    _campaign_segment_filter_dict,
    _ensure_template_approved,
    _fetch_campaign_or_404,
)

# Extracted to app/api/v1/_helpers/segments_db.py
from app.api.v1._helpers.segments_db import _fetch_segment_or_404  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/messenger_db.py
from app.api.v1._helpers.messenger_db import _upsert_messenger_contact  # noqa: E402,F401 — re-exported for backward compat

# Extracted to app/api/v1/_helpers/auth_db.py
from app.api.v1._helpers.auth_db import (  # noqa: E402,F401 — re-exported for backward compat
    _TENANT_MEMBER_ROLES,
    _tenant_member_payload,
    _tenant_owner_count,
)

# Extracted to app/api/v1/_helpers/web_chat_db.py
from app.api.v1._helpers.web_chat_db import _persist_bot_reply_sync  # noqa: E402,F401 — re-exported for backward compat


router = APIRouter(prefix='/v1')
public_router = APIRouter(tags=['public'])
webhook_router = APIRouter(prefix='/webhooks', tags=['public-webhooks'])
platform_admin_router = APIRouter(
    tags=['platform-admin'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_platform_owner),
        Depends(require_mfa_for_privileged),
    ],
)
tenant_admin_router = APIRouter(
    tags=['tenant-admin'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_min_role('admin')),
        Depends(require_mfa_for_privileged),
    ],
)
tenant_catalog_router = APIRouter(
    tags=['tenant-catalog'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_min_role('admin', allow_service=True)),
        Depends(require_mfa_for_privileged),
    ],
)
tenant_ops_router = APIRouter(
    tags=['tenant-operations'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('agent', allow_service=True))],
)
tenant_analytics_router = APIRouter(
    tags=['tenant-analytics'],
    # BUG-037: bajado de `manager` a `viewer` — la matriz de permisos
    # (`admin-panel/src/permissions/matrix.js`) asigna
    # `analytics.tenant.read` al rol `viewer` (UI-010.2 monta
    # `ViewerAnalytics` sobre `AnalyticsPanel`). Antes los viewers veían
    # el componente pero los GET de analytics respondían 403. Todos los
    # endpoints aquí son GETs read-only.
    dependencies=[Depends(authenticate_request), Depends(require_min_role('viewer'))],
)
# BUG-036: nuevo router para endpoints que la UI expone a managers
# (digest-reports, etc.) pero que no requieren admin completo. Antes los
# digest CRUD vivían en `tenant_admin_router` (admin+) mientras la UI los
# exponía con capability `digest.write` (manager+) → 403 silencioso a todos
# los managers que intentaban gestionar suscripciones.
tenant_manager_router = APIRouter(
    tags=['tenant-manager'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_min_role('manager')),
        Depends(require_mfa_for_privileged),
    ],
)
tenant_signup_router = APIRouter(
    tags=['tenant-signup'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_min_role('admin')),
        Depends(require_mfa_for_privileged),
    ],
)
# Endpoints that any authenticated user must be able to call regardless of the
# role they currently hold inside their default tenant.  Used for the Slack-style
# tenant switcher (listing tenants the user belongs to).
tenant_user_router = APIRouter(
    tags=['tenant-user'],
    dependencies=[Depends(authenticate_request)],
)
system_router = APIRouter(
    tags=['system'],
    dependencies=[Depends(authenticate_request), Depends(require_service)],
)
# UI-016.7-FU: user-scoped router for `/me/profile`, `/me/preferences`,
# `/me/notifications` and `/me/sessions`. Auth is required at the router
# level; each handler additionally enforces that the actor on the JWT
# matches the user_id being mutated (no cross-user edits — `current_user_id_from_request`
# only ever resolves to the authenticated subject, never to a path parameter).
me_router = APIRouter(
    tags=['me'],
    dependencies=[Depends(authenticate_request)],
)
# UI-005: public web widget endpoints. Defined here (instead of next to the
# handlers in app/api/v1/handlers/web_handlers.py) so the router exists by
# the time the handler module imports it from app.api.v1.routes.
web_router = APIRouter(prefix='/web', tags=['public-web-widget'])


def is_service_or_support(request: Request) -> bool:
    return getattr(request.state, 'actor_type', None) == 'service' or getattr(
        request.state, 'support_mode', False
    )


# TASK-0077: per-tenant role ranking.  ``platform_owner`` is intentionally not
# part of this table because that role is never stored in
# ``app.user_tenant_roles``; it lives in the JWT only.  The JWT half of the
# double-check uses ``has_jwt_role`` from ``app.core.security`` which *does*
# include ``platform_owner`` in its ranking.
async def get_user_tenant_role(
    conn: asyncpg.Connection, request: Request, tenant_id: UUID
) -> str | None:
    """Return the highest-ranked role the actor holds *in this tenant*, or ``None``.

    Replaces the legacy ``has_user_tenant_role`` (existence-only) check.  Pure
    existence is insufficient for authorization decisions because the schema
    permits low-privilege roles (viewer/agent) — see BUG25.
    """
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        return None
    rows = await conn.fetch(
        """
        select utr.role
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject=$1 and utr.tenant_id=$2
        """,
        actor_id,
        tenant_id,
    )
    if not rows:
        return None
    return max(
        (row['role'] for row in rows),
        key=lambda role: _TENANT_ROLE_LEVELS.get(role, 0),
    )


async def user_tenant_roles_for(
    conn: asyncpg.Connection, request: Request, tenant_id: UUID
) -> list[str]:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        return []
    rows = await conn.fetch(
        """
        select utr.role
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject=$1 and utr.tenant_id=$2
        """,
        actor_id,
        tenant_id,
    )
    return [row['role'] for row in rows]


async def _audit_authz_denied(
    request: Request,
    conn: asyncpg.Connection | None,
    *,
    tenant_id: UUID | None,
    reason: str,
) -> None:
    """Best-effort audit log for authorization denials.

    Failures here must never mask the 403 raised by the caller, so we swallow
    any exception (eg. fake test connections lacking ``execute``).
    """
    if conn is None:
        return
    try:
        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type=getattr(request.state, 'actor_type', 'anonymous'),
            actor_id=getattr(request.state, 'actor_id', None),
            action='authz.denied',
            entity_type='tenant',
            entity_id=str(tenant_id) if tenant_id else None,
            metadata={'reason': reason, 'path': getattr(request.scope, 'get', lambda *_: None)('path') or request.scope.get('path')},
        )
    except Exception:  # pragma: no cover - defensive
        pass


async def ensure_tenant_access(
    request: Request, tenant_id: UUID, conn: asyncpg.Connection | None = None
) -> None:
    """Confirm the caller may operate as the actor for ``tenant_id``.

    TASK-0077 hardens this helper relative to the prior contract:

    * The DB membership check is no longer existence-only.  When the router
      installed a JWT-level ``require_min_role`` dependency it leaves the
      expected minimum on ``request.state.required_tenant_role``; we use that
      to gate ``user_tenant_roles`` so JWT-admin + DB-viewer combinations are
      rejected (BUG16/BUG25).
    * ``platform_owner`` JWTs on unscoped tokens (platform staff are not
      tracked in ``user_tenant_roles``) are recognized as a global bypass.
    * Same-token-scope still implies access for read-only routers that did
      *not* install a ``require_min_role`` dependency.  Routers that *did*
      (``tenant_admin_router``, ``tenant_ops_router``, ``tenant_catalog_router``)
      always go through the DB role gate.
    """
    if is_service_or_support(request):
        return
    roles = getattr(request.state, 'roles', []) or []
    if 'platform_owner' in roles and not getattr(request.state, 'tenant_id', None):
        return

    required_tenant_role = getattr(request.state, 'required_tenant_role', None)
    request_tenant_id = getattr(request.state, 'tenant_id', None)

    if required_tenant_role is None:
        # Router did not declare a minimum tenant role (eg. ``tenant_user_router``
        # endpoints that any authenticated user may call).  Fall back to the
        # legacy semantics: token tenant scope or any DB membership row.
        if request_tenant_id == tenant_id:
            return
        if conn is not None and await get_user_tenant_role(conn, request, tenant_id) is not None:
            return
        if not request_tenant_id:
            await _audit_authz_denied(
                request, conn, tenant_id=tenant_id, reason='no_tenant_scope'
            )
            raise HTTPException(
                status_code=400, detail='X-Tenant-Id header or tenant_id claim is required'
            )
        await _audit_authz_denied(
            request, conn, tenant_id=tenant_id, reason='tenant_scope_mismatch'
        )
        raise HTTPException(status_code=403, detail='Tenant scope does not match request')

    # A required tenant role is in effect → always consult the DB for that
    # tenant, regardless of whether the token nominally scopes to it.
    db_role = await get_user_tenant_role(conn, request, tenant_id) if conn is not None else None
    if _tenant_db_role_meets(db_role, required_tenant_role):
        return

    if db_role is None and not request_tenant_id and conn is None:
        await _audit_authz_denied(
            request, conn, tenant_id=tenant_id, reason='no_tenant_scope'
        )
        raise HTTPException(
            status_code=400, detail='X-Tenant-Id header or tenant_id claim is required'
        )
    await _audit_authz_denied(
        request, conn, tenant_id=tenant_id, reason='insufficient_tenant_role'
    )
    raise HTTPException(
        status_code=403,
        detail=f'{required_tenant_role} role or higher is required for this tenant',
    )


async def ensure_tenant_role(
    request: Request,
    conn: asyncpg.Connection,
    tenant_id: UUID,
    minimum_role: str,
) -> None:
    """Double-check that the actor holds ``minimum_role`` in **both** the JWT
    and the per-tenant DB role table.

    TASK-0077 elevates this from a DB-only check to a defense-in-depth gate
    that preserves the JWT invariant (the token must carry the role the
    endpoint demands) while also requiring the DB row for the *target* tenant
    to confirm it.  Either half failing → 403 with a distinct ``reason`` in
    the audit log.

    Bypasses:
      * service tokens and explicit Postgres support_mode sessions
      * ``platform_owner`` JWTs on unscoped tokens (platform staff are not
        tracked in ``app.user_tenant_roles``)
    """
    if is_service_or_support(request):
        return
    roles = getattr(request.state, 'roles', []) or []
    if 'platform_owner' in roles and not getattr(request.state, 'tenant_id', None):
        return

    if not has_jwt_role(roles, minimum_role):
        await _audit_authz_denied(
            request, conn, tenant_id=tenant_id, reason='insufficient_token_role'
        )
        raise HTTPException(
            status_code=403,
            detail=f'{minimum_role} token role or higher is required',
        )

    db_role = await get_user_tenant_role(conn, request, tenant_id)
    if _tenant_db_role_meets(db_role, minimum_role):
        return

    await _audit_authz_denied(
        request, conn, tenant_id=tenant_id, reason='insufficient_tenant_role'
    )
    raise HTTPException(
        status_code=403,
        detail=f'{minimum_role} role or higher is required for this tenant',
    )


async def require_tenant(request: Request) -> UUID:
    if not getattr(request.state, 'tenant_id', None):
        raise HTTPException(status_code=400, detail='X-Tenant-Id header or tenant_id claim is required')
    return request.state.tenant_id


async def tenant_id_from_request(request: Request, conn: asyncpg.Connection) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None) or getattr(
        request.state, 'requested_tenant_id', None
    )
    if not tenant_id:
        raise HTTPException(status_code=400, detail='X-Tenant-Id header or tenant_id claim is required')
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    return tenant_id


def user_email_from_request(request: Request) -> str:
    """Return the email for `app.users` upsert — JWT claim or signed BFF header.

    BUG-195 (codex HIGH): el header `X-Admin-User-Email` lo emite el admin BFF
    desde el ID token de Auth0, pero el Core API también puede recibir
    llamadas DIRECTAS con bearer token. Si un caller cualquiera puede mandar
    `X-Admin-User-Email: victim@example.com` cuando su JWT no incluye claim
    `email`, podemos terminar UPSERTeando `app.users` con (auth_subject de
    ATACANTE, email de VÍCTIMA). Después, cuando un admin invita
    `victim@example.com` via `invite_tenant_member`, encontramos la fila
    por email y reusamos el `auth_subject` del atacante → el atacante
    hereda la membresía de la víctima.

    BUG-228 (codex P1 follow-up sobre BUG-195): el fix original dropeó el
    header completamente, pero el Auth0 PostLogin Action NO agrega claim
    `email` al access token (solo a id_token). Para requests normales del
    panel `request.state.email` queda vacío → el fallback escribía
    `<hash>@auth.local` → al invitar a un email real, el lookup por email
    fallaba y los pending-invite no se reclamaban. ROMPIA el flow normal
    del admin panel.

    Fix: aceptar el header CUANDO viene acompañado de un payload firmado
    (`X-Admin-Identity`) que el BFF produce con `pack_signed_payload`. El
    payload incluye `{sub, email, exp}` firmado con `jwt_secret` — el Core
    valida que (a) la firma matchea, (b) `sub == request.state.actor_id`,
    (c) `exp > now`. Un caller con bearer token directo NO puede producir
    el payload firmado (no tiene `jwt_secret`).

    Si no hay header firmado válido, mantenemos el fallback sintético.
    """
    email = getattr(request.state, 'email', None)
    if email:
        return email
    # BUG-228: intentar header firmado del BFF.
    trusted_email = _email_from_signed_bff_header(request)
    if trusted_email:
        return trusted_email
    actor_id = getattr(request.state, 'actor_id', 'unknown-user')
    stable_id = uuid5(NAMESPACE_URL, actor_id).hex
    return f'{stable_id}@auth.local'


def _email_from_signed_bff_header(request: Request) -> str | None:
    """BUG-228: validar el header `X-Admin-Identity` que el BFF firma con
    `pack_signed_payload(jwt_secret, {sub, email, exp})`.

    Retorna el `email` solo cuando:
      - la firma matchea (`unpack_signed_payload` no retorna None),
      - `sub` del payload == `request.state.actor_id` (JWT del request),
      - `exp` > now (cookie/header no expirado),
      - `email` está presente y no vacío.

    Cualquier otra cosa retorna None (caller cae al sintético).
    """
    raw = request.headers.get('X-Admin-Identity')
    if not raw:
        return None
    settings = get_settings()
    payload = unpack_signed_payload(settings.jwt_secret, raw)
    if not isinstance(payload, dict):
        return None
    sub = payload.get('sub')
    email = payload.get('email')
    exp = payload.get('exp')
    if not isinstance(sub, str) or not isinstance(email, str) or not email:
        return None
    if sub != getattr(request.state, 'actor_id', None):
        return None
    if not isinstance(exp, int):
        return None
    now_ts = int(datetime.now(UTC).timestamp())
    if exp <= now_ts:
        return None
    return email


def user_display_name_from_request(request: Request) -> str:
    """Return display name for audit/UI — display-only, NOT for identity.

    A diferencia de `user_email_from_request`, este sí puede usar el header
    `X-Admin-User-Name` porque el display name NO es identifier (no participa
    en lookups por email ni en UPSERT keyed por email). El peor caso de un
    header spoofeado acá es un audit log con un nombre incorrecto.
    """
    return (
        getattr(request.state, 'name', None)
        or request.headers.get('X-Admin-User-Name')
        or getattr(request.state, 'email', None)
        or getattr(request.state, 'actor_id', None)
        or 'Tenant admin'
    )


async def current_user_id_from_request(request: Request, conn: asyncpg.Connection) -> UUID | None:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id or getattr(request.state, 'actor_type', None) != 'user':
        return None
    user_display = user_display_name_from_request(request)

    # BUG-022: si el usuario fue invitado vía `POST /v1/tenants/{id}/members`
    # antes de tener cuenta Auth0, su fila en `app.users` quedó con
    # `auth_subject = 'pending|<uuid5(email).hex>'` (ver `invite_tenant_member`
    # más abajo). El link de la membresía en `user_tenant_roles` está creado
    # contra esa fila. Cuando el usuario finalmente loguea con Auth0, el `sub`
    # del JWT es `auth0|...` y NO matchea el `auth_subject` pendiente — la
    # membresía existe pero queda "huérfana".
    #
    # Multi-tenant: un mismo email puede tener invitaciones a varios tenants
    # con roles distintos. invite_tenant_member sólo crea UNA fila en
    # `app.users` por email (las invitaciones subsecuentes reutilizan la fila
    # y agregan filas en `user_tenant_roles`). Cuando este reclamo dispara,
    # TODAS las memberships pendientes de ese user se iluminan a la vez
    # porque comparten el mismo `user_id`.
    #
    # Históricamente, el path feliz de `invite_tenant_member` también hacía
    # `UPDATE app.users SET auth_subject=<sub real>` justo después de Auth0
    # crear la cuenta, pero ese update vive dentro del `else:` del try/except
    # y se salta si algún paso post-creación (set_user_tenant_metadata,
    # assign_auth0_role_by_name, o el ticket de password-change) lanza una
    # excepción — el invitado se queda con la fila pendiente y al loguear
    # aterriza en `/admin/no-tenant`.
    #
    # **Seguridad** (Codex P1 en PR #17): el reclamo SÓLO usa el claim
    # `email` del JWT (`request.state.email`), NUNCA el header
    # `X-Admin-User-Email` ni el email sintético `<hash>@auth.local`. Sin
    # esta restricción, un atacante autenticado con su propia cuenta Auth0
    # podría mandar `X-Admin-User-Email: <email-de-la-víctima>` y reclamar
    # la membresía pendiente de otro tenant. El JWT está firmado por Auth0
    # — el `email` claim es la única fuente confiable.
    #
    # El reclamo es idempotente (sólo afecta filas pendientes) y respeta
    # UNIQUE de `auth_subject` con un `not exists` defensivo — si por alguna
    # razón ya hay otra fila con ese `sub`, el reclamo no se ejecuta.
    trusted_email = getattr(request.state, 'email', None)
    if trusted_email:
        claimed = await conn.fetchrow(
            """
            update app.users
            set auth_subject = $1,
                display_name = case
                  when coalesce(display_name, '') = '' then $3
                  else display_name
                end,
                status = 'active',
                last_login_at = now(),
                updated_at = now()
            where email = $2
              and auth_subject like 'pending|%'
              and not exists (
                select 1 from app.users u2
                where u2.auth_subject = $1 and u2.id <> app.users.id
              )
            returning id
            """,
            actor_id,
            trusted_email,
            user_display,
        )
        if claimed:
            return claimed['id']

    row = await conn.fetchrow(
        """
        insert into app.users (auth_subject, email, display_name, last_login_at)
        values ($1, $2, $3, now())
        on conflict (auth_subject) do update set
          email=excluded.email,
          display_name=excluded.display_name,
          last_login_at=now(),
          updated_at=now()
        returning id
        """,
        actor_id,
        user_email_from_request(request),
        user_display,
    )
    return row['id']


# UI-006.1: Fleet · Tenants list endpoint.
#
# Drives the platform-owner "Fleet · Tenants" view. The router-level
# `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`
# dependencies already enforce that ONLY a platform_owner with verified MFA can
# read across tenants — never relaxed at the handler level.


# UI-006.2: Platform System Health snapshot.
#
# Drives the platform-owner "System Health" view. Same router-level security as
# the rest of `platform_admin_router` (`authenticate_request` +


# UI-006.3: Platform-level Billing / MRR snapshot.
#
# Drives the platform-owner "Billing & MRR" view. Same router-level security as
# the rest of `platform_admin_router` (`authenticate_request` +
# `require_platform_owner` + `require_mfa_for_privileged`) — never relaxed.
#
# The "MRR" here is the recurring revenue flowing through the fleet, aggregated
# from the per-tenant subscription model of TASK-0075 across every tenant. The
# cross-tenant read goes through `app.support_mode` — the codebase's intended
# RLS bypass for authorized platform operations (TASK-0077) — set
# transaction-locally so it never leaks past this request.


# UI-006.4: Platform incidents feed.
#
# Drives the platform-owner "Incidentes" view. Same router-level security as the
# rest of `platform_admin_router` (`authenticate_request` +
# `require_platform_owner` + `require_mfa_for_privileged`) — never relaxed.
#
# The "incidents" feed is the cross-tenant view of `app.operator_alerts`
# (TASK-0057 / TASK-0064 / TASK-0065). The cross-tenant read goes through
# `app.support_mode` — operator_alerts has RLS and a nullable `tenant_id` for
# system-level alerts; the schema comment notes that surfacing NULL-tenant rows
# under `app.support_mode()` is the expected operator path (TASK-0064).


# UI-006.5: Platform-wide Outbound DLQ.
#
# Drives the platform-owner "Outbound DLQ · fleet" view. Same router-level
# security as the rest of `platform_admin_router` (`authenticate_request` +
# `require_platform_owner` + `require_mfa_for_privileged`) — never relaxed.
#
# The fleet DLQ is the cross-tenant aggregate of `app.messages` rows that ended
# `status='failed'` / `direction='outbound'` (TASK-0065). `app.messages` has
# RLS, so the cross-tenant read goes through `app.support_mode`, set
# transaction-locally. The aggregate query never selects message bodies or
# contact identifiers — only counts grouped by tenant and error_code.


# UI-006.6: Platform runbooks catalogue.
#
# Drives the platform-owner "Runbooks" view. Same router-level security as the
# rest of `platform_admin_router` (`authenticate_request` +
# `require_platform_owner` + `require_mfa_for_privileged`) — never relaxed.
#
# The runbooks are static Markdown files under `docs/runbooks/`. The detail
# endpoint renders them through `render_markdown_to_safe_html` (TASK-0076) —
# the same fully-escaped Markdown subset used for public legal pages — so the
# returned HTML carries no script/style/raw-HTML. Slugs are validated against a
# strict pattern and the resolved path is verified to live inside the runbooks
# directory (path-traversal defense lives in `platform_runbooks`).


# UI-006.8: Platform feature-flags catalogue (read-only).
#
# Same router-level security as the rest of `platform_admin_router`
# (`authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`).
#
# This is a READ-ONLY catalogue of the product's feature flags — a static
# registry (`app.services.feature_flags`), no DB, no writes. Live toggling,
# gradual rollout and per-tenant overrides are deferred to a separate backend
# ticket (the UI backlog flags UI-006.8 as "confirmar con el equipo antes de
# cablear" precisely because the writable system does not exist yet).


async def update_tenant_record(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    payload: TenantUpdate | PlatformTenantUpdate,
    *,
    actor_is_platform_owner: bool = False,
) -> asyncpg.Record:
    """Persist tenant profile fields.

    TASK-0077/BUG11: ``status`` may only be written when the caller is
    ``platform_owner`` (``actor_is_platform_owner=True``).  ``TenantUpdate``
    no longer carries a ``status`` field, so tenant admins can never set it;
    if a ``PlatformTenantUpdate`` arrives without that flag we refuse to
    persist the ``status`` change defensively.
    """
    allowed = payload.model_dump(exclude_unset=True, exclude_none=True)
    if 'status' in allowed and not actor_is_platform_owner:
        # Defense in depth: even if a future caller passes a PlatformTenantUpdate
        # without the platform-owner flag, never let ``status`` leak through.
        raise HTTPException(
            status_code=403, detail='Only platform_owner may change tenant status'
        )
    current = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail='Tenant not found')
    merged = dict(current)
    merged.update(allowed)
    row = await conn.fetchrow(
        """
        update app.tenants
        set slug=$2,
            legal_name=$3,
            display_name=$4,
            vertical_code=$5,
            business_type_label=$6,
            country_code=$7,
            timezone=$8,
            status=$9,
            updated_at=now()
        where id=$1 and deleted_at is null
        returning *
        """,
        tenant_id,
        merged['slug'],
        merged['legal_name'],
        merged['display_name'],
        merged['vertical_code'],
        merged.get('business_type_label'),
        merged['country_code'],
        merged['timezone'],
        merged['status'],
    )
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return row


_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    'trial': {'active', 'suspended', 'churned'},
    'active': {'suspended', 'churned'},
    'suspended': {'active', 'churned'},
    'churned': set(),
}


async def _ensure_caller_can_target_role(
    request: Request, conn: asyncpg.Connection, tenant_id: UUID, target_role: str
) -> None:
    """Only an existing owner of the tenant may assign or modify the owner role."""
    if target_role != 'owner':
        return
    if is_service_or_support(request):
        return
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=403, detail='Only an owner can manage the owner role')
    caller_is_owner = await conn.fetchval(
        """
        select exists(
          select 1
          from app.users u
          join app.user_tenant_roles utr on utr.user_id = u.id
          where u.auth_subject=$1 and utr.tenant_id=$2 and utr.role='owner'
        )
        """,
        actor_id,
        tenant_id,
    )
    if not caller_is_owner:
        raise HTTPException(status_code=403, detail='Only an owner can manage the owner role')


# BUG-036: digest endpoints viven en tenant_manager_router (manager+) para
# matchear la capability `digest.write` que la UI expone a managers.


# BUG-036: en tenant_manager_router (manager+).


# BUG-036: en tenant_manager_router (manager+).


# BUG-036: en tenant_manager_router (manager+).


# ───── Branches (TASK-0050) ────────────────────────────────────────────────


# ───── Treatment packages (TASK-0051) ──────────────────────────────────────


# TASK-0084 / BUG02: package mutation endpoints live on the admin router
# (admin+ role) because they encode financial state. Agents keep read access
# via list_contact_packages above.


# ───── Subscription plans (TASK-0075) ──────────────────────────────────────


# SEC-008: subscription mutations require `admin` role (was `agent` via
# tenant_ops_router). Sibling fix to TASK-0077, which already moved the
# `/packages` CRUD to tenant_admin_router. Path is preserved so the admin
# panel (`coreApi.cancelContactSubscription`, etc.) keeps working without a
# breaking change; the auth boundary tightens via the router-level
# `require_min_role('admin')` + `require_mfa_for_privileged` dependencies.


# ─────────────────────────────────────────────────────────────────────────────
# TASK-0069 — Wizard de onboarding self-service con verificación paso-a-paso
# ─────────────────────────────────────────────────────────────────────────────


async def build_tenant_readiness_report(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    *,
    smoke_question: str = 'horarios políticas servicios garantías precios contacto',
    retrieval_min_score: float = 0.12,
) -> dict[str, Any]:
    tenant = await conn.fetchrow(
        'select id, slug, display_name, status, deleted_at from app.tenants where id=$1',
        tenant_id,
    )
    checks: list[dict[str, Any]] = []

    tenant_ready = bool(tenant and tenant['status'] == 'active' and tenant['deleted_at'] is None)
    checks.append(
        readiness_check(
            'tenant_active',
            'Tenant activo',
            tenant_ready,
            'Tenant activo y disponible.' if tenant_ready else 'El tenant no existe, no está activo o fue eliminado.',
            record_to_dict(tenant) if tenant else {},
        )
    )

    settings = await conn.fetchrow(
        'select locale, business_hours, escalation_policy, pii_policy, no_train, onboarding_progress from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    settings_dict = record_to_dict(settings) if settings else {}
    onboarding_progress = normalize_onboarding_progress(_coerce_jsonb(settings_dict.get('onboarding_progress')))
    settings_ready = bool(
        settings
        and readiness_truthy_object(settings['locale'])
        and readiness_truthy_object(settings['business_hours'])
        and readiness_truthy_object(settings['pii_policy'])
    )
    checks.append(
        readiness_check(
            'tenant_settings',
            'Settings operativos',
            settings_ready,
            'Settings mínimos configurados.' if settings_ready else 'Faltan settings mínimos: locale, horarios o PII policy.',
            settings_dict,
        )
    )

    channel = await conn.fetchrow(
        """
        select id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref,
               verify_token_hash is not null as verify_token_hash_configured, account_mode, status
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    channel_dict = record_to_dict(channel) if channel else {}
    whatsapp_token_ready = token_ref_is_configured(channel['token_ref']) if channel else False
    whatsapp_secret_ready = secret_ref_is_configured(channel['app_secret_ref']) if channel else False
    whatsapp_verify_ready = secret_ref_is_configured(tenant_secret_ref(tenant_id, 'whatsapp_verify_token')) if channel else False
    whatsapp_ready = bool(
        channel
        and channel['status'] == 'active'
        and channel['business_id']
        and channel['waba_id']
        and channel['phone_number_id']
        and channel['account_mode'] == 'live'
        and whatsapp_token_ready
        and whatsapp_secret_ready
        and whatsapp_verify_ready
    )
    checks.append(
        readiness_check(
            'whatsapp_channel',
            'Canal WhatsApp',
            whatsapp_ready,
            (
                'Canal WhatsApp activo en modo live con secretos resueltos.'
                if whatsapp_ready
                else 'El canal WhatsApp no está activo, no está en modo live o faltan IDs/secretos reales.'
            ),
            {
                **channel_dict,
                'meta_access_token_configured': whatsapp_token_ready,
                'app_secret_configured': whatsapp_secret_ready,
                'verify_token_configured': whatsapp_verify_ready,
                'delivery_mode_live': channel['account_mode'] == 'live' if channel else False,
            },
        )
    )

    knowledge_counts = await conn.fetchrow(
        """
        select
          count(distinct kd.id) as active_documents,
          count(kc.id) as active_chunks
        from app.knowledge_documents kd
        left join app.knowledge_chunks kc on kc.tenant_id=kd.tenant_id and kc.document_id=kd.id
        where kd.tenant_id=$1 and kd.status='active'
        """,
        tenant_id,
    )
    retrieval_rows = await conn.fetch(
        """
        select kc.id, kc.document_id, kd.title as document_title, kd.source_uri, kd.source_type,
               kd.document_type, kd.visibility, kc.chunk_index, kc.section_path, kc.chunk_text,
               kc.token_count, kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id=kc.document_id and kd.tenant_id=kc.tenant_id
        where kc.tenant_id=$1 and kd.status='active'
          and kd.visibility = ANY($2::text[])
        order by kd.updated_at desc, kc.chunk_index asc
        limit 500
        """,
        tenant_id,
        list(END_USER_VISIBILITY),
    )
    matches = rank_chunks(smoke_question, [record_to_dict(row) for row in retrieval_rows], max_chunks=3)
    retrieval_answer = build_grounded_answer(smoke_question, matches, min_score=retrieval_min_score)
    knowledge_ready = bool(
        knowledge_counts
        and knowledge_counts['active_documents'] > 0
        and knowledge_counts['active_chunks'] > 0
        and retrieval_answer['sufficient_context']
    )
    checks.append(
        readiness_check(
            'knowledge_retrieval',
            'Documentos activos y retrieval smoke test',
            knowledge_ready,
            'Knowledge base activa y retrieval smoke test con contexto suficiente.' if knowledge_ready else 'No hay documentos/chunks activos o el retrieval smoke test no recuperó contexto suficiente.',
            {
                'active_documents': knowledge_counts['active_documents'] if knowledge_counts else 0,
                'active_chunks': knowledge_counts['active_chunks'] if knowledge_counts else 0,
                'returned_chunk_count': len(matches),
                'top_score': matches[0].score if matches else None,
                'sufficient_context': retrieval_answer['sufficient_context'],
            },
        )
    )

    escalation_policy = _coerce_jsonb(settings_dict.get('escalation_policy') or {}) or {}
    if not isinstance(escalation_policy, dict):
        escalation_policy = {}
    ep_triggers = escalation_policy.get('triggers') or {}

    _ep_has_triggers = bool(
        ep_triggers.get('keywords')
        or ep_triggers.get('after_bot_turns')
        or ep_triggers.get('confidence_below')
    )
    _ep_has_message = bool(escalation_policy.get('handoff_message'))

    if not settings or not escalation_policy:
        handoff_ready = False
        handoff_reason = 'Política de escalamiento ausente. Configura la política en la pestaña Escalamiento del Tenant Setup.'
    elif escalation_policy.get('enabled') is False:
        handoff_ready = False
        handoff_reason = 'Política de escalamiento deshabilitada (enabled=false). Actívala en la pestaña Escalamiento del Tenant Setup.'
    elif not escalation_policy.get('queue'):
        handoff_ready = False
        handoff_reason = 'Sin cola de escalamiento (queue vacía). Configura la cola en la pestaña Escalamiento del Tenant Setup.'
    elif not _ep_has_triggers and not _ep_has_message:
        handoff_ready = False
        handoff_reason = 'Sin triggers ni mensaje de handoff. Configura keywords, after_bot_turns, confidence_below o handoff_message en la pestaña Escalamiento.'
    else:
        handoff_ready = True
        handoff_reason = 'Política de handoff configurada.'

    checks.append(
        readiness_check(
            'handoff',
            'Handoff humano',
            handoff_ready,
            handoff_reason,
            {'escalation_policy': escalation_policy},
        )
    )

    # Policy engine check: at least after_bot_turns > 0 and one trigger defined.
    pe_after_bot_turns = readiness_positive_int(ep_triggers.get('after_bot_turns'))
    pe_has_triggers = bool(ep_triggers.get('keywords') or ep_triggers.get('after_bot_turns'))
    policy_engine_ready = bool(pe_after_bot_turns and pe_has_triggers)
    if not settings:
        policy_engine_reason = 'Sin configuración de tenant settings. Configura el policy engine en la pestaña Escalamiento.'
    elif not pe_after_bot_turns:
        policy_engine_reason = 'triggers.after_bot_turns debe ser mayor que cero. Configura el límite en la pestaña Escalamiento.'
    elif not pe_has_triggers:
        policy_engine_reason = 'Sin triggers de escalamiento. Configura keywords o after_bot_turns en la pestaña Escalamiento.'
    else:
        policy_engine_reason = 'Policy engine configurado con triggers válidos.'
    checks.append(
        readiness_check(
            'policy_engine',
            'Policy engine configurado',
            policy_engine_ready,
            policy_engine_reason,
            {
                'after_bot_turns': ep_triggers.get('after_bot_turns'),
                'has_trigger_keywords': bool(ep_triggers.get('keywords')),
                'consecutive_no_context_limit': escalation_policy.get('consecutive_no_context_limit'),
            },
        )
    )

    template_rows = await conn.fetch(
        """
        select purpose, status
        from app.whatsapp_templates
        where tenant_id=$1 and purpose = any($2::text[])
        """,
        tenant_id,
        list(WHATSAPP_TEMPLATE_REQUIRED_PURPOSES),
    )
    approved_purposes = {
        row['purpose'] for row in template_rows if row['status'] == 'approved'
    }
    missing_purposes = [
        purpose for purpose in WHATSAPP_TEMPLATE_REQUIRED_PURPOSES
        if purpose not in approved_purposes
    ]
    templates_ready = not missing_purposes
    template_reason = (
        'Plantillas mínimas aprobadas para confirmación y recordatorio 24 h.'
        if templates_ready
        else f'Faltan plantillas aprobadas: {", ".join(missing_purposes)}. '
             'Crea y sincroniza con Meta desde la pestaña Plantillas de WhatsApp.'
    )
    checks.append(
        readiness_check(
            'whatsapp_templates',
            'Plantillas mínimas aprobadas',
            templates_ready,
            template_reason,
            {
                'required_purposes': list(WHATSAPP_TEMPLATE_REQUIRED_PURPOSES),
                'approved_purposes': sorted(approved_purposes),
                'missing_purposes': missing_purposes,
            },
        )
    )

    audit_count = await conn.fetchval('select count(*) from app.audit_logs where tenant_id=$1', tenant_id)
    audit_count = audit_count or 0
    audit_ready = audit_count > 0
    checks.append(
        readiness_check(
            'audit',
            'Auditoría',
            audit_ready,
            'Auditoría con eventos registrados.' if audit_ready else 'No hay eventos de auditoría para evidenciar cambios del tenant.',
            {'audit_log_entries': audit_count},
        )
    )

    response = readiness_response(tenant_id, checks, smoke_question)
    response['onboarding_progress'] = onboarding_progress
    # TASK-UI-016.1-FU: surface go_live_at so the frontend can render
    # "Tenant en producción desde X" once the owner marks live. Defensive
    # read via `dict(...).get(...)` so older fake connections (legacy tests
    # that mock `from app.tenant_settings` without including this new
    # column) don't blow up with KeyError; in production asyncpg returns
    # the column whenever the SELECT lists it.
    go_live_row = await conn.fetchrow(
        'select go_live_at from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    go_live_at = dict(go_live_row).get('go_live_at') if go_live_row else None
    response['tenant_status'] = {
        'go_live_at': go_live_at.isoformat() if go_live_at is not None else None,
    }
    return response


# ─────────────────────────────────────────────────────────────────────────────
# SEC-010-EXPORT-FU — contact-scoped data export for consent-violation claims.
# ─────────────────────────────────────────────────────────────────────────────
#
# The tenant-wide `data-export` above is the wrong tool for derecho de acceso
# claims that target a SINGLE contact: it dumps every contact's data and the
# operator was building extracts by `grep`-ing the JSON manually, with a high
# risk of leaking cross-contact PII to the claimant. The runbook
# `docs/runbooks/consent-violation-claim.md` (SEC-010 sub-finding 6317cdc8)
# prohibited that path and asked the operator to compose the extract via SQL.
# This endpoint replaces the manual SQL with a tested server-side handler.
#
# Surface:
#   GET /v1/tenants/{tenant_id}/contacts/{contact_id}/export?kinds=consent_ledger,messages
#
# Auth:
#   - Mounted on `tenant_admin_router` → `require_min_role('admin')` already
#     gates this; manager/agent/viewer get 403 before the handler runs.
#   - `ensure_tenant_access` re-verifies the caller has access to THIS tenant
#     (defense in depth against cross-tenant token reuse).
#   - The contact row is fetched WITH `tenant_id=$1` in the WHERE — a contact
#     id from another tenant returns 404 (RLS also enforces this; the explicit
#     check is the audit-trail signal).
#
# Output:
#   - JSON object `{data: {...}, signature: '<hex>', signature_algorithm: ...}`.
#   - `data` includes `exported_at` (ISO-8601 UTC), `tenant_id`, `contact`,
#     `kinds` (echoed) and one key per kind requested.
#   - `signature` is HMAC-SHA256 of the canonical JSON of `data` under the
#     server's `jwt_secret`. Operators sharing the export with a claimant or
#     court can prove integrity via the audit log entry (which records the
#     same signature) — if anyone tampers with the file, the signature won't
#     match. The audit log is the source of truth.
#
# Audit:
#   `contact.exported_for_consent_claim` with `{kinds, signature, exported_at}`.
#   Tenant-scoped so it appears in the tenant's audit_logs feed.
#
# Why the tenant-wide export is NOT enough: a Ley 1581 / GDPR access request
# requires the data of the ONE complainant. Sending the full dump exposes
# every OTHER contact's PII and creates a worse violation than the one the
# claimant was reporting. The runbook now points here.


# ─────────────────────────────────────────────────────────────────────────────
# UI-016.7-FU — `/v1/me/*` endpoints (user preferences)
# ─────────────────────────────────────────────────────────────────────────────
#
# These endpoints persist the per-user settings that UI-016.7 wired into the
# `/account/*` screens. The data model lives in `app.user_preferences`
# (one row per user, PK = `app.users.id`). Auth0 is the source of truth for
# `email`/`display_name`/`phone` — we only cache them in this table to avoid
# round-tripping Auth0 on every read; `auth0_synced_at` marks when the cache
# was last refreshed.
#
# Security primitives (non-negotiable, mirror UI-012-FU / UI-016.1-FU):
#   1. `authenticate_request` at the router level (so unauthenticated callers
#      get 401 before any handler runs).
#   2. Each handler resolves the user_id via `current_user_id_from_request(...)`
#      — that helper reads `request.state.actor_id` (the Auth0 `sub` from the
#      validated JWT) and looks up / upserts the matching `app.users` row.
#      There is NO path parameter for the subject, so a caller cannot edit
#      another user even with a forged URL.
#   3. Every PATCH emits `audit(action='user.preferences_updated', ...)` with
#      `tenant_id=None` (this is per-user, not per-tenant) and metadata
#      listing the fields touched.

async def _load_user_preferences_row(
    conn: asyncpg.Connection, user_id: UUID
) -> asyncpg.Record:
    """Fetch the `user_preferences` row, creating it lazily on first access.

    First-time callers (whose `app.users` row exists from
    `current_user_id_from_request` but who have never hit `/me/*`) get an
    auto-provisioned row with the schema defaults so GET handlers can return
    a stable shape without a 404.
    """
    row = await conn.fetchrow(
        'select * from app.user_preferences where user_id=$1', user_id
    )
    if row is None:
        await conn.execute(
            'insert into app.user_preferences (user_id) values ($1) on conflict do nothing',
            user_id,
        )
        row = await conn.fetchrow(
            'select * from app.user_preferences where user_id=$1', user_id
        )
    return row


async def _require_current_user(request: Request, conn: asyncpg.Connection) -> UUID:
    user_id = await current_user_id_from_request(request, conn)
    if user_id is None:
        raise HTTPException(status_code=401, detail='Authentication required')
    return user_id


def _session_id_from_request(request: Request) -> str | None:
    """UI-016.7-FU-SESSIONS: derive a stable per-session id from the JWT.

    Auth0 emits `jti` for every access token by default; we prefer that.
    Fallback when `jti` is absent: a deterministic SHA-256 hash of
    `sub + iat` so the same logical session resolves to the same id across
    requests until the token expires. Returns `None` only when the request
    is unauthenticated (anonymous/service) — handlers must guard with
    `_require_current_user` first, so reaching here without a user means
    the caller built the JWT without `sub`, which is a misconfig.
    """
    jti = getattr(request.state, 'session_jti', None)
    if jti:
        return str(jti)
    actor_id = getattr(request.state, 'actor_id', None)
    iat = getattr(request.state, 'token_iat', None)
    if not actor_id or iat is None:
        return None
    digest = hashlib.sha256(f'{actor_id}|{iat}'.encode()).hexdigest()
    # Prefix marks fallback ids so audit/logs can tell them apart from real jti.
    return f'iat-{digest[:32]}'


async def record_auth_session(
    request: Request, conn: asyncpg.Connection, user_id: UUID
) -> str | None:
    """UI-016.7-FU-SESSIONS: upsertea `app.auth_sessions` para la request actual.

    Devuelve el `session_id` que queda registrado (para que el handler pueda
    marcar la entrada como `current` en el GET list). Si la request no es de
    usuario autenticado, devuelve `None` sin tocar la DB.

    No re-activa una sesión previamente revocada (la cláusula `where
    revoked_at is null` en el update lo previene); si la sesión está
    revocada, el upsert deja de actualizar `last_seen_at` — lo correcto, ya
    que el usuario debe re-loguear para obtener un nuevo JWT con jti distinto.

    Best-effort sobre IP/user_agent: si no están disponibles (test client,
    headers strippados por un proxy), se persisten como NULL.
    """
    session_id = _session_id_from_request(request)
    if not session_id:
        return None
    user_agent = request.headers.get('user-agent') or None
    client = getattr(request, 'client', None)
    client_ip = client.host if client and client.host else None
    await conn.execute(
        """
        insert into app.auth_sessions (id, user_id, user_agent, ip, last_seen_at)
        values ($1, $2, $3, $4::inet, now())
        on conflict (id) do update set
            user_agent = coalesce(excluded.user_agent, app.auth_sessions.user_agent),
            ip = coalesce(excluded.ip, app.auth_sessions.ip),
            last_seen_at = now()
        where app.auth_sessions.revoked_at is null
        """,
        session_id,
        user_id,
        user_agent,
        client_ip,
    )
    return session_id


# ─── BUG-008 — Support mode opt-in temporal por sesión ──────────────────────
# Reemplaza el workaround actual de setear `app_metadata.support_mode=true`
# permanente en Auth0 (ver `BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE` en
# `scripts/configure-auth0.sh`). Ahora el `platform_owner` activa el modo
# explícitamente para UN tenant a la vez; el cookie tiene TTL (1h default)
# y `authenticate_request` solo lo aplica si matchea el `X-Tenant-Id` del
# request. Esto respeta TASK-0077 — opt-in deliberado, audit trail, blast
# radius acotado a un tenant.


# BUG-171 (codex P1 sobre BUG-037): cuando el router `tenant_analytics_router`
# se bajó a `viewer` para que viewers vieran sus métricas básicas, este
# endpoint específico quedó expuesto. Devuelve email + handoffs + feedback +
# revenue de TODOS los agentes — `analytics.agent_performance.read` en la
# matriz (`matrix.js:53`) es manager+ (agentes ven `own_only`, no la lista
# global). Re-restringimos con `require_min_role('manager')` per-route, sin
# tocar el router (que sigue siendo viewer-readable para los otros endpoints
# de analytics como overview/funnel/campaigns).


# ─── TASK-0065: DLQ de mensajes outbound ────────────────────────────────────


# ─── TASK-0076: páginas legales por tenant ───────────────────────────────


# ── Extracted handlers (registered by module side-effect) ────────────────
# Importing these modules wires their @<router>.<verb>(...) decorators onto
# the router objects defined above. Must happen AFTER the routers exist but
# BEFORE the router.include_router(...) calls below.
from app.api.v1.handlers import (  # noqa: F401, E402
    me_handlers,
    platform_admin_handlers,
    public_handlers,
    system_handlers,
    tenant_admin_handlers,
    tenant_analytics_handlers,
    tenant_catalog_handlers,
    tenant_manager_handlers,
    tenant_ops_handlers,
    tenant_signup_handlers,
    tenant_user_handlers,
    web_handlers,
    webhook_handlers,
)

# Re-export handler functions for back-compat with tests + tooling that
# imports them directly from `app.api.v1.routes`. The handler modules
# themselves remain the source of truth; this block keeps the public
# surface of routes.py stable across the refactor.
from app.api.v1.handlers.me_handlers import (  # noqa: F401, E402
    activate_support_mode,
    deactivate_support_mode,
    get_my_notifications,
    get_my_preferences,
    get_my_profile,
    list_my_sessions,
    patch_my_notifications,
    patch_my_preferences,
    patch_my_profile,
    revoke_my_session,
)
from app.api.v1.handlers.platform_admin_handlers import (  # noqa: F401, E402
    create_tenant,
    list_tenants_fleet,
    patch_tenant_status,
    platform_billing_mrr,
    platform_feature_flags,
    platform_incidents_feed,
    platform_outbound_dlq,
    platform_outbound_dlq_retry,
    platform_runbook_detail,
    platform_runbooks_list,
    platform_system_health,
)
from app.api.v1.handlers.public_handlers import (  # noqa: F401, E402
    get_public_legal_document,
    health,
    list_public_resources,
)
from app.api.v1.handlers.system_handlers import (  # noqa: F401, E402
    create_conversation,
    upsert_contact,
)
from app.api.v1.handlers.tenant_admin_handlers import (  # noqa: F401, E402
    archive_subscription_plan,
    assign_contact_package,
    cancel_campaign,
    cancel_contact_subscription,
    channel_health,
    complete_tenant_onboarding_step,
    create_branch,
    create_campaign,
    create_channel,
    create_contact_segment,
    create_contact_subscription,
    create_contact_tag,
    create_knowledge_document,
    create_legal_document_draft,
    create_promotion,
    create_prompt,
    create_qualification_question,
    create_service,
    create_subscription_plan,
    create_treatment_package,
    create_whatsapp_template,
    deactivate_branch,
    deactivate_service,
    deactivate_treatment_package,
    delete_contact_segment,
    delete_contact_tag,
    delete_knowledge_document,
    delete_media_asset,
    delete_promotion,
    delete_qualification_question,
    delete_whatsapp_template,
    evaluate_intent_retrieval,
    export_audit_logs,
    export_contact_data,
    export_tenant_data,
    get_campaign,
    get_contact_segment,
    get_knowledge_document,
    get_knowledge_storage_settings,
    get_retention_preview,
    get_tenant_onboarding,
    get_tenant_payment_settings,
    get_tenant_readiness,
    get_tenant_settings,
    get_web_channel,
    get_whatsapp_template,
    index_knowledge_document,
    invite_tenant_member,
    launch_campaign,
    list_audit_logs,
    list_campaigns,
    list_contact_segments,
    list_knowledge_documents,
    list_legal_documents,
    list_media_assets,
    list_messenger_channels,
    list_promotions,
    list_retention_policies,
    list_tenant_members,
    list_whatsapp_templates,
    mark_tenant_go_live,
    patch_campaign,
    patch_channel_mode,
    patch_contact_segment,
    patch_knowledge_document,
    patch_knowledge_storage_settings,
    patch_settings,
    patch_tenant,
    preview_campaign,
    preview_contact_segment,
    publish_legal_document,
    put_retention_policies,
    record_onboarding_test_message_sent,
    refresh_contact_segment,
    refund_contact_package,
    reindex_all_knowledge_documents,
    remove_tenant_member,
    reorder_qualification_questions,
    reorder_services,
    set_static_segment_members,
    suppress_contact,
    sync_whatsapp_templates,
    update_branch,
    update_contact_package,
    update_contact_subscription,
    update_contact_tag,
    update_media_asset,
    update_promotion,
    update_qualification_question,
    update_service,
    update_subscription_plan,
    update_tenant_member_role,
    update_tenant_payment_settings,
    update_treatment_package,
    update_whatsapp_template,
    upload_knowledge_document,
    upload_media_asset,
    upload_tenant_brand_logo,
    upsert_messenger_channel,
    upsert_web_channel,
    verify_tenant_onboarding_step,
)
from app.api.v1.handlers.tenant_analytics_handlers import (  # noqa: F401, E402
    analytics_agents,
    analytics_appointments,
    analytics_campaigns,
    analytics_contacts,
    analytics_conversations,
    analytics_funnel,
    analytics_overview,
    analytics_referrals,
)
from app.api.v1.handlers.tenant_catalog_handlers import (  # noqa: F401, E402
    list_qualification_questions,
    list_services,
    resource_availability,
    tenant_availability,
)
from app.api.v1.handlers.tenant_manager_handlers import (  # noqa: F401, E402
    create_digest_subscription,
    delete_digest_subscription,
    list_digest_subscriptions,
    update_digest_subscription,
)
from app.api.v1.handlers.tenant_ops_handlers import (  # noqa: F401, E402
    accept_handoff,
    assign_contact_tags,
    cancel_appointment,
    create_appointment,
    create_appointment_feedback,
    create_appointment_payment_link,
    create_contact_note,
    create_handoff,
    create_message,
    create_quote,
    create_resource,
    create_service_request,
    deactivate_resource,
    get_contact,
    get_contact_profile,
    get_conversation,
    get_conversation_message_media,
    get_quote_for_service_request,
    get_service_request,
    get_tenant,
    get_tenant_media_content,
    list_appointment_feedback,
    list_appointments,
    list_branches,
    list_complaint_conversations,
    list_contact_consent,
    list_contact_notes,
    list_contact_packages,
    list_contact_subscriptions,
    list_contact_tags,
    list_contacts,
    list_conversations,
    list_outbound_dlq,
    list_resources,
    list_service_requests,
    list_subscription_plans,
    list_treatment_packages,
    patch_appointment_payment_status,
    patch_contact_phone,
    patch_quote,
    patch_service_request,
    release_conversation,
    retry_outbound_dlq_message,
    send_appointment_payment_link,
    send_quote,
    start_conversation,
    unassign_contact_tag,
    update_appointment,
    update_resource,
)
from app.api.v1.handlers.tenant_signup_handlers import (  # noqa: F401, E402
    create_own_tenant,
)
from app.api.v1.handlers.tenant_user_handlers import (  # noqa: F401, E402
    list_my_tenants,
)
from app.api.v1.handlers.web_handlers import (  # noqa: F401, E402
    web_chat_history,
    web_chat_send_message,
    web_chat_start,
)
from app.api.v1.handlers.webhook_handlers import (  # noqa: F401, E402
    receive_messenger_webhook,
    receive_payment_webhook,
    receive_subscription_webhook,
    receive_whatsapp_webhook,
    verify_messenger_webhook,
    verify_whatsapp_webhook,
)


# Cargar los módulos que registran endpoints en `platform_admin_router` y
# `tenant_admin_router` ANTES de incluir esos sub-routers en `router`.
#
# FastAPI `include_router(child)` copia `child.routes` en el momento de la
# llamada, no por referencia. Si un módulo externo usa decoradores
# `@platform_admin_router.X` para registrar endpoints, esos decoradores
# deben haber corrido ANTES de `router.include_router(platform_admin_router)`.
#
# Branch `core`: `app/platform_admin/admin_routes.py` declara los endpoints
# transversales del platform admin (`/platform/ai-providers/*`,
# `/platform/tenant-modules/*`). Antes vivían en `app.influencer.admin_routes`
# por razón histórica; al separar el core se promueven al paquete neutral.
from app.platform_admin import admin_routes as _platform_admin_routes  # noqa: F401, E402
# Fase 2 — CRUD de roles/capabilities. Mismo patrón side-effect: el módulo
# usa decoradores `@platform_admin_router.X` para registrar endpoints
# `/platform/roles/*` y `/platform/capabilities/*`. Debe importarse ANTES
# de `router.include_router(platform_admin_router)`.
from app.api.v1.handlers import platform_roles_handlers as _platform_roles_handlers  # noqa: F401, E402

router.include_router(public_router)
router.include_router(web_router)
router.include_router(webhook_router)
router.include_router(platform_admin_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_user_router)
router.include_router(tenant_admin_router)
router.include_router(tenant_catalog_router)
router.include_router(tenant_ops_router)
router.include_router(tenant_analytics_router)
# BUG-036: manager-level router (digest CRUD y demás endpoints que la UI
# expone a managers pero que no requieren admin).
router.include_router(tenant_manager_router)
router.include_router(system_router)
# UI-016.7-FU
router.include_router(me_router)
