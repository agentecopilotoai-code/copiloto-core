"""Platform admin handlers — operaciones cross-tenant del platform_owner.

Endpoints expuestos bajo `/v1/platform/*` (todos requieren
`platform_owner` + MFA, gating ya aplicado por el router):

  ─ Tenants:
      GET    /v1/tenants                       — listado con filtros
      POST   /v1/tenants                       — crear (admin lo gestiona)
      GET    /v1/tenants/{id}                  — detalle
      PATCH  /v1/tenants/{id}                  — editar metadata
      PATCH  /v1/tenants/{id}/status           — lifecycle (trial→active→…)

  ─ Membresía de tenants (gestión cross-tenant de usuarios):
      GET    /v1/tenants/{id}/members          — listar miembros del tenant
      POST   /v1/tenants/{id}/members          — agregar miembro con rol
      PATCH  /v1/tenants/{id}/members/{uid}    — cambiar rol del miembro
      DELETE /v1/tenants/{id}/members/{uid}    — revocar membresía

  ─ Observability:
      GET    /v1/platform/metrics/health       — KPIs de salud cross-tenant
      GET    /v1/platform/billing/mrr          — MRR consolidado
      GET    /v1/platform/incidents            — alertas operativas
      GET    /v1/platform/outbound-dlq         — DLQ outbound + reintento
      POST   /v1/platform/outbound-dlq/retry
      GET    /v1/platform/runbooks             — catálogo de runbooks
      GET    /v1/platform/feature-flags        — catálogo
      PATCH  /v1/platform/feature-flags/{key}  — toggle (Fase 2 write)

El listado/admin de tenants se monta bajo `tenant_signup_router` (que ya
exige autenticación) PERO con `require_platform_owner` adicional por
handler.  Más limpio: usar el `platform_admin_router` directamente.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.routes import platform_admin_router, tenant_management_router
from app.api.v1.schemas import TenantCreate, TenantUpdate
from app.core.security import require_tenant_management
from app.db.pool import get_db, record_to_dict
from app.services import locale as locale_service
from app.services.audit import audit


# ═══════════════════════════════════════════════════════════════════════════
# Tenants CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TenantStatusUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['trial', 'active', 'suspended', 'churned']


class TenantMemberAdd(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    role: Literal['owner', 'admin', 'manager', 'agent', 'viewer'] = 'admin'
    is_default: bool = False


class TenantMemberPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['owner', 'admin', 'manager', 'agent', 'viewer'] | None = None
    is_default: bool | None = None


@platform_admin_router.get('/tenants')
async def list_all_tenants(
    status_filter: str | None = Query(default=None, alias='status'),
    country_code: str | None = Query(default=None),
    vertical_code: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Listado cross-tenant para Fleet · Tenants."""
    where = ['t.deleted_at is null']
    params: list = []
    if status_filter:
        params.append(status_filter)
        where.append(f't.status = ${len(params)}')
    if country_code:
        params.append(country_code)
        where.append(f't.country_code = ${len(params)}')
    if vertical_code:
        params.append(vertical_code)
        where.append(f't.vertical_code = ${len(params)}')
    if search:
        params.append(f'%{search.lower()}%')
        where.append(
            f'(lower(t.legal_name) like ${len(params)} '
            f'or lower(t.display_name) like ${len(params)} '
            f'or lower(t.slug::text) like ${len(params)})'
        )
    where_sql = ' and '.join(where)
    params.extend([limit, offset])
    rows = await conn.fetch(
        f'''
        select t.id, t.slug, t.legal_name, t.display_name, t.vertical_code,
               t.business_type_label, t.country_code, t.timezone, t.status,
               t.created_at, t.updated_at,
               (select count(*) from app.user_tenant_roles utr
                where utr.tenant_id = t.id) as member_count,
               (select count(*) from app.tenant_modules tm
                where tm.tenant_id = t.id and tm.enabled = true) as active_modules_count
        from app.tenants t
        where {where_sql}
        order by t.created_at desc
        limit ${len(params) - 1} offset ${len(params)}
        ''',
        *params,
    )
    total = await conn.fetchval(
        f'select count(*) from app.tenants t where {where_sql}',
        *params[:-2],
    )
    return {
        'items': [record_to_dict(r) for r in rows],
        'total': total or 0,
        'limit': limit,
        'offset': offset,
    }


@platform_admin_router.post(
    '/tenants',
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant_for_third_party(
    payload: TenantCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Crea un tenant nuevo (platform_owner administra para tercero).

    A diferencia de `POST /v1/tenant-signup` (self-service), este NO
    asigna automáticamente al caller como owner — el caller es el
    platform_owner y NO debe terminar como miembro del tenant nuevo.
    Para agregar miembros, usar `POST /v1/tenants/{id}/members`.
    """
    try:
        profile = locale_service.profile_for(payload.country_code)
        tz_value = payload.timezone or profile['timezone']
    except (KeyError, AttributeError):
        tz_value = payload.timezone or 'America/Bogota'

    try:
        row = await conn.fetchrow(
            '''
            insert into app.tenants
              (slug, legal_name, display_name, vertical_code,
               business_type_label, country_code, timezone)
            values ($1, $2, $3, $4, $5, $6, $7)
            returning *
            ''',
            payload.slug, payload.legal_name, payload.display_name,
            payload.vertical_code, payload.business_type_label,
            payload.country_code, tz_value,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={'error': 'slug_taken'})

    actor_id = getattr(request.state, 'actor_id', None)
    await audit(
        conn, tenant_id=row['id'], actor_type='user', actor_id=actor_id,
        action='tenant.created_by_platform_owner',
        entity_type='tenant', entity_id=str(row['id']),
        metadata={'slug': payload.slug},
    )
    return record_to_dict(row)


@platform_admin_router.get('/tenants/{tenant_id}')
async def get_tenant(
    tenant_id: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await conn.fetchrow(
        'select * from app.tenants where id = $1 and deleted_at is null',
        tenant_id,
    )
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    return record_to_dict(row)


@platform_admin_router.patch('/tenants/{tenant_id}')
async def patch_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    sets, params = [], []
    for field in ('slug', 'legal_name', 'display_name', 'vertical_code',
                  'business_type_label', 'country_code', 'timezone'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if not sets:
        raise HTTPException(400, 'no_valid_fields')
    sets.append('updated_at = now()')
    params.append(tenant_id)
    try:
        row = await conn.fetchrow(
            f'update app.tenants set {", ".join(sets)} '
            f'where id = ${len(params)} and deleted_at is null returning *',
            *params,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'slug_taken'})
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.updated_by_platform_owner',
        entity_type='tenant', entity_id=str(tenant_id),
        metadata={'fields': list(patch.keys())},
    )
    return record_to_dict(row)


@platform_admin_router.patch('/tenants/{tenant_id}/status')
async def patch_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await conn.fetchrow(
        '''
        update app.tenants
           set status = $1, updated_at = now()
         where id = $2 and deleted_at is null
        returning id, status
        ''',
        payload.status, tenant_id,
    )
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.status_changed',
        entity_type='tenant', entity_id=str(tenant_id),
        metadata={'new_status': payload.status},
    )
    return {'id': str(row['id']), 'status': row['status']}


# ═══════════════════════════════════════════════════════════════════════════
# Membresía del tenant — gestión de usuarios cross-tenant desde admin
# ═══════════════════════════════════════════════════════════════════════════


@tenant_management_router.get('/tenants/{tenant_id}/members')
async def list_tenant_members(
    tenant_id: UUID,
    _acl: None = Depends(require_tenant_management),  # M55 ACL: platform_owner OR owner/admin
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Listar miembros del tenant + sus roles."""
    rows = await conn.fetch(
        '''
        select u.id as user_id, u.email, u.display_name, u.status as user_status,
               u.mfa_enabled, u.last_login_at,
               array_agg(utr.role order by
                   case utr.role
                       when 'owner' then 1 when 'admin' then 2
                       when 'manager' then 3 when 'agent' then 4
                       when 'viewer' then 5 else 6
                   end
               ) as roles,
               bool_or(utr.is_default) as is_default,
               min(utr.created_at) as joined_at
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where utr.tenant_id = $1
        group by u.id
        order by min(utr.created_at) asc
        ''',
        tenant_id,
    )
    items = []
    for r in rows:
        d = record_to_dict(r)
        d['roles'] = list(d.get('roles') or [])
        items.append(d)
    return {'items': items, 'tenant_id': str(tenant_id)}


@tenant_management_router.post(
    '/tenants/{tenant_id}/members',
    status_code=status.HTTP_201_CREATED,
)
async def add_tenant_member(
    tenant_id: UUID,
    payload: TenantMemberAdd,
    request: Request,
    _acl: None = Depends(require_tenant_management),  # M55
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Agregar miembro al tenant.

    M59 — orquesta dos sistemas:

    (1) Auth0 (si está configurado vía `auth0_service_client_id` +
        `auth0_service_client_secret_file`): crea el user en Auth0
        + emite ticket de password-change (Auth0 manda email con
        magic link de welcome al invitado). Idempotente: si el
        email ya existe en Auth0, reusa esa cuenta.

    (2) DB local (`app.users` + `app.user_tenant_roles`): registra
        la membresía. Si Auth0 estaba configurado, usa el
        `user_id` real (`auth0|...`) como `auth_subject`. Si NO,
        cae al placeholder `pending|<hash>` y M57 reconcilia al
        primer login del invitado.

    Response incluye `auth0` con el resultado (`invited` /
    `reused_existing` / `skipped`) + opcional `invitation_ticket_url`
    para que la UI pueda mostrarlo si Auth0 no manda el email
    automático (tiers gratuitos sin SMTP custom).
    """
    from app.services import auth0_admin  # noqa: PLC0415

    # ¿Existe el tenant?
    tenant_exists = await conn.fetchval(
        'select 1 from app.tenants where id = $1 and deleted_at is null',
        tenant_id,
    )
    if not tenant_exists:
        raise HTTPException(404, 'tenant_not_found')

    # ─── (1) Auth0 ────────────────────────────────────────────────────
    auth0_user_id: str | None = None
    auth0_status = 'skipped'  # 'invited' | 'reused_existing' | 'skipped' | 'error'
    auth0_error: str | None = None
    invitation_ticket_url: str | None = None
    if auth0_admin.is_configured():
        try:
            display_name = payload.display_name or payload.email.split('@', 1)[0]
            result = await auth0_admin.invite_user(
                email=payload.email, name=display_name,
            )
            auth0_user_id = result['user']['user_id']
            auth0_status = 'reused_existing' if result['reused_existing'] else 'invited'
            invitation_ticket_url = result.get('invitation_ticket_url')
        except auth0_admin.Auth0NotConfiguredError:
            # Race: settings cambiaron entre is_configured() y el call.
            auth0_status = 'skipped'
        except auth0_admin.Auth0ApiError as exc:
            # No abortar el flow — el user todavía puede signuparse a mano.
            # Audit-loggeamos el error para diagnóstico.
            auth0_status = 'error'
            auth0_error = str(exc)[:200]

    # ─── (1b) Tenant lookup para el email ────────────────────────────
    # Necesitamos el tenant_name para el template del email. Si el
    # bootstrap ya validó tenant_exists con SELECT 1, podemos hacer un
    # second-trip barato.
    tenant_row = await conn.fetchrow(
        'select display_name, legal_name from app.tenants where id = $1',
        tenant_id,
    )
    tenant_name = (
        tenant_row
        and (tenant_row['display_name'] or tenant_row['legal_name'])
    ) or 'CopilotoIA'

    # ─── (2) DB local ─────────────────────────────────────────────────
    # Lookup user por email (case-insensitive — `app.users.email` es citext).
    user_row = await conn.fetchrow(
        'select id, email from app.users where email = $1', payload.email,
    )
    if user_row is None:
        # auth_subject = real de Auth0 (si lo tenemos) o pending|hash.
        # `make_pending_auth_subject` es determinístico → M57 matchea
        # cuando el user se loguea real.
        auth_subject = auth0_user_id or auth0_admin.make_pending_auth_subject(
            payload.email,
        )
        user_row = await conn.fetchrow(
            '''
            insert into app.users (auth_subject, email, display_name, status)
            values ($1, $2, $3, $4)
            returning id, email
            ''',
            auth_subject, payload.email,
            payload.display_name or payload.email.split('@', 1)[0],
            'invited' if not auth0_user_id else 'active',
        )

    await conn.execute(
        '''
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, $3, $4)
        on conflict (user_id, tenant_id, role) do update set is_default = excluded.is_default
        ''',
        user_row['id'], tenant_id, payload.role, payload.is_default,
    )

    # ─── (3) Crear invitación + enviar email (M61) ────────────────────
    # SIEMPRE — para user nuevo o `reused_existing`. Esto fixea el bug
    # que el operator reportó: los users que ya existían en Auth0
    # quedaban añadidos al tenant SIN notificación. Ahora reciben un
    # email "te invitaron a TenantX" con magic link al login.
    #
    # Lookup del inviter info para mostrar en el email (reply_to + display).
    from app.services.invitations import (  # noqa: PLC0415
        InvitationRateLimitError,
        create_and_send_invitation,
    )
    actor_id = getattr(request.state, 'actor_id', None)
    actor_email = getattr(request.state, 'email', None)
    actor_name = getattr(request.state, 'name', None)
    inviter_user_id = None
    if actor_id:
        inviter_row = await conn.fetchrow(
            'select id from app.users where auth_subject = $1', actor_id,
        )
        if inviter_row:
            inviter_user_id = inviter_row['id']

    invitation_payload: dict[str, Any] = {
        'status': 'not_sent',
        'invitation_id': None,
        'accept_url': None,
        'expires_at': None,
        'message_id': None,
        'provider': None,
    }
    try:
        sent = await create_and_send_invitation(
            conn=conn,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            email=payload.email,
            role=payload.role,
            inviter_user_id=inviter_user_id,
            inviter_name=actor_name,
            inviter_email=actor_email,
        )
        invitation_payload = {
            'status': sent.email_status,  # queued|noop|failed
            'invitation_id': str(sent.invitation_id),
            'accept_url': sent.accept_url,
            'expires_at': sent.expires_at.isoformat(),
            'message_id': sent.email_message_id or None,
            'provider': sent.email_provider,
        }
    except InvitationRateLimitError as exc:
        invitation_payload['status'] = 'rate_limited'
        invitation_payload['error'] = str(exc)

    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=actor_id,
        action='tenant.member_added',
        entity_type='user_tenant_role',
        entity_id=f'{user_row["id"]}:{tenant_id}:{payload.role}',
        metadata={
            'email': payload.email, 'role': payload.role,
            'auth0_status': auth0_status,
            'auth0_user_id': auth0_user_id,
            'auth0_error': auth0_error,
            'invitation_status': invitation_payload['status'],
            'invitation_id': invitation_payload['invitation_id'],
            'invitation_provider': invitation_payload['provider'],
        },
    )
    return {
        'user_id': str(user_row['id']),
        'tenant_id': str(tenant_id),
        'email': str(user_row['email']),
        'role': payload.role,
        'is_default': payload.is_default,
        # M59 — info del invite Auth0 para que la UI pueda mostrar
        # mensaje específico ("se mandó email", "ya existía y se
        # vinculó", "Auth0 no está configurado", etc).
        'auth0': {
            'status': auth0_status,           # invited|reused_existing|skipped|error
            'user_id': auth0_user_id,
            'invitation_ticket_url': invitation_ticket_url,  # URL para forward manual
            'error': auth0_error,
        },
        # M61 — info del email transaccional (Resend/Noop). El frontend
        # decide qué mostrar al admin: si `status='queued'` y `provider=
        # 'resend'`, mostrar "Email enviado a X". Si `status='noop'`,
        # mostrar el `accept_url` como copy-button. Si `status='failed'`
        # o `'rate_limited'`, mostrar warning + opción de reintentar.
        'invitation': invitation_payload,
    }


@tenant_management_router.patch('/tenants/{tenant_id}/members/{user_id}')
async def patch_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    payload: TenantMemberPatch,
    request: Request,
    _acl: None = Depends(require_tenant_management),  # M55
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Cambiar rol o is_default. Cambio de rol = DELETE viejo + INSERT nuevo
    (la PK incluye `role`). Esto preserva audit trail."""
    existing = await conn.fetch(
        'select role, is_default from app.user_tenant_roles '
        'where user_id = $1 and tenant_id = $2',
        user_id, tenant_id,
    )
    if not existing:
        raise HTTPException(404, 'membership_not_found')

    if payload.role is not None:
        # Replace todos los roles del user en este tenant por el nuevo único.
        await conn.execute(
            'delete from app.user_tenant_roles where user_id = $1 and tenant_id = $2',
            user_id, tenant_id,
        )
        await conn.execute(
            '''
            insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
            values ($1, $2, $3, $4)
            ''',
            user_id, tenant_id, payload.role,
            payload.is_default if payload.is_default is not None else existing[0]['is_default'],
        )
        new_role = payload.role
    elif payload.is_default is not None:
        await conn.execute(
            'update app.user_tenant_roles set is_default = $1 '
            'where user_id = $2 and tenant_id = $3',
            payload.is_default, user_id, tenant_id,
        )
        new_role = existing[0]['role']
    else:
        raise HTTPException(400, 'empty_patch')

    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.member_updated',
        entity_type='user_tenant_role',
        entity_id=f'{user_id}:{tenant_id}',
        metadata=payload.model_dump(exclude_none=True),
    )
    return {
        'user_id': str(user_id),
        'tenant_id': str(tenant_id),
        'role': new_role,
        'is_default': payload.is_default if payload.is_default is not None else existing[0]['is_default'],
    }


@tenant_management_router.delete(
    '/tenants/{tenant_id}/members/{user_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    request: Request,
    _acl: None = Depends(require_tenant_management),  # M55
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Revoca membresía del user en este tenant.

    M59 — solo borra `user_tenant_roles` (membresía LOCAL). NO bloquea
    al user en Auth0 — sigue pudiendo loguearse a sus OTROS tenants
    donde aún tiene membresía. Si el caller necesita ban total, usar
    los endpoints separados de Auth0 admin (TODO: `POST
    /v1/platform/users/{user_id}/block` — fuera del scope de M59).
    """
    result = await conn.execute(
        'delete from app.user_tenant_roles where user_id = $1 and tenant_id = $2',
        user_id, tenant_id,
    )
    if result.endswith(' 0'):
        raise HTTPException(404, 'membership_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.member_removed',
        entity_type='user_tenant_role',
        entity_id=f'{user_id}:{tenant_id}',
    )


# ═══════════════════════════════════════════════════════════════════════════
# Observability (health, billing, incidents, dlq, runbooks)
# ═══════════════════════════════════════════════════════════════════════════


@platform_admin_router.get('/platform/metrics/health')
async def get_platform_health(
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> dict:
    """Snapshot live de System Health (UI-006.2).

    M54 — el shape DEBE matchear lo que `admin-panel/.../SystemHealth.jsx`
    consume:

        {
          'generated_at': ISO timestamp,
          'snapshot': {...},            # KPIs (puede estar vacío en core)
          'alerts': [...],              # array de alertas activas
          'services': [...],            # array de {key, label, status, detail}
          'note': str,
        }

    Antes el handler devolvía `services` como dict `{api: ..., db: ...}`
    y rompía el frontend con `TypeError: t.map is not a function`.
    El core branch no tiene workers/messages/circuit_breakers (todo eso
    pertenece a módulos opt-in), pero SÍ podemos reportar el estado real
    de los servicios que SÍ corren: API y Postgres (probe `select 1`).
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    # Probe live de la DB. Si responde, status=ok; si no, status=down
    # con el error en `detail`. No bloqueamos más de 2s.
    db_status = 'ok'
    db_detail: str | None = None
    db_started = time.monotonic()
    try:
        await asyncio.wait_for(conn.fetchval('select 1'), timeout=2.0)
        elapsed_ms = (time.monotonic() - db_started) * 1000.0
        db_detail = f'select 1 · {elapsed_ms:.1f}ms'
    except (TimeoutError, Exception) as exc:  # noqa: BLE001
        db_status = 'down'
        db_detail = str(exc)[:120]

    services = [
        {
            'key': 'api',
            'label': 'API · FastAPI',
            'status': 'ok',
            'detail': 'Atendiendo requests',
        },
        {
            'key': 'postgres',
            'label': 'Postgres · primary',
            'status': db_status,
            'detail': db_detail,
        },
    ]

    # M-002 — surface contador de fail-opens del revoke check. Si >0,
    # sesiones revocadas pueden estar siendo aceptadas silentemente
    # por outages transient de DB. Alerta operator-visible.
    from app.core.security import get_session_revoke_failopen_count  # noqa: PLC0415
    failopens = get_session_revoke_failopen_count()
    alerts: list[dict] = []
    if failopens > 0:
        alerts.append({
            'severity': 'warning',
            'code': 'auth_session_revoke_failopens',
            'message': (
                f'{failopens} revoke-check fail-opens desde el último restart. '
                'Sesiones marcadas como revocadas pueden seguir aceptándose. '
                'Inspeccionar logs `auth.session_revoke_check.fail_open`.'
            ),
            'count': failopens,
        })

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        # En el core no hay KPIs propios — los módulos opt-in agregan
        # response_latency, llm_calls, circuit_breakers, workers, etc.
        # Devolvemos {} para que `snapshot?.xxx` del frontend caiga al
        # default sin romper.
        'snapshot': {
            'auth_session_revoke_failopens': failopens,
        },
        'alerts': alerts,
        'services': services,
        'note': 'Core base — sin métricas de producto. Cada módulo opt-in agrega sus KPIs (workers, breakers, mensajes, etc).',
    }


@platform_admin_router.get('/platform/billing/mrr')
async def get_billing_mrr() -> dict:
    """MRR consolidado. Placeholder — el módulo de billing agregará lógica
    real (lookup en app.subscriptions, conversión de moneda, etc.)."""
    return {'mrr_total_usd': 0, 'by_currency': [], 'by_plan': [], 'churn_30d_pct': 0}


@platform_admin_router.get('/platform/incidents')
async def list_platform_incidents(
    status_filter: str | None = Query(default=None, alias='status'),
    limit: int = Query(default=50, ge=1, le=200),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Lista de operator_alerts (incidents cross-tenant)."""
    where = ['1=1']
    params: list = []
    if status_filter:
        params.append(status_filter)
        where.append(f'oa.status = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f'''
        select oa.id, oa.tenant_id, t.slug as tenant_slug, t.display_name as tenant_name,
               oa.kind, oa.payload, oa.status, oa.attempts, oa.last_error,
               oa.scheduled_for, oa.created_at, oa.sent_at
        from app.operator_alerts oa
        left join app.tenants t on t.id = oa.tenant_id
        where {' and '.join(where)}
        order by oa.created_at desc
        limit ${len(params)}
        ''',
        *params,
    )
    return {'items': [record_to_dict(r) for r in rows]}


@platform_admin_router.get('/platform/outbound-dlq')
async def list_outbound_dlq() -> dict:
    """DLQ outbound — placeholder. Los módulos opt-in que emiten mensajes
    salientes agregan la lógica real (lookup en su tabla de mensajes con
    status='failed'), agrupada por tenant."""
    return {'items': [], 'total': 0, 'note': 'Módulos opt-in agregan lógica.'}


@platform_admin_router.post('/platform/outbound-dlq/retry')
async def retry_outbound_dlq() -> dict:
    """Trigger de reintento masivo. Placeholder — los módulos opt-in lo
    implementan."""
    return {'queued': 0, 'note': 'Módulos opt-in agregan lógica.'}


_RUNBOOK_CATALOG: list[dict] = [
    {
        'slug': 'auth0-mfa-error',
        'title': 'Auth0 MFA error',
        'category': 'auth',
        'summary': 'Diagnóstico de errores MFA.',
        # M40 — body placeholder; cuando se conecte la lectura real de
        # `docs/runbooks/*.md` (TODO Fase 3) viene de ahí.
        'body_md': (
            '## Auth0 MFA error\n\n'
            'Placeholder. El detalle real vive en `docs/runbooks/auth0-mfa-error.md`.'
        ),
    },
    {
        'slug': 'backup-signature-setup',
        'title': 'Backup signature setup',
        'category': 'backups',
        'summary': 'Configurar firma GPG de backups.',
        'body_md': (
            '## Backup signature setup\n\n'
            'Placeholder. El detalle real vive en '
            '`docs/runbooks/backup-signature-setup.md`.'
        ),
    },
]


@platform_admin_router.get('/platform/runbooks')
async def list_runbooks() -> dict:
    """Catálogo de runbooks. Por ahora estático.

    TODO Fase 3: leer desde `docs/runbooks/` o desde una tabla
    `app.runbooks` (slug + content_md + category)."""
    # Devolver el catálogo sin `body_md` (el listado no necesita el
    # markdown completo — solo el detail endpoint lo expone).
    return {
        'items': [
            {k: v for k, v in item.items() if k != 'body_md'}
            for item in _RUNBOOK_CATALOG
        ],
    }


@platform_admin_router.get('/platform/runbooks/{slug}')
async def get_runbook(slug: str) -> dict:
    """Detalle de un runbook (M40 — antes no existía y el click del
    frontend explotaba con 404)."""
    for item in _RUNBOOK_CATALOG:
        if item['slug'] == slug:
            return dict(item)
    raise HTTPException(404, 'runbook_not_found')


# ═══════════════════════════════════════════════════════════════════════════
# Feature flags CRUD (Fase 2 write)
# ═══════════════════════════════════════════════════════════════════════════


class FeatureFlagPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    rollout_pct: int | None = Field(default=None, ge=0, le=100)
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict | None = None


class FeatureFlagCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    key: str = Field(min_length=1, max_length=200, pattern=r'^[a-z][a-z0-9_\.]*$')
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = False
    rollout_pct: int = Field(default=0, ge=0, le=100)
    metadata: dict = Field(default_factory=dict)


@platform_admin_router.get('/platform/feature-flags')
async def list_feature_flags(
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    rows = await conn.fetch(
        'select key, description, enabled, rollout_pct, metadata, created_at, updated_at '
        'from app.feature_flags order by key'
    )
    return {'items': [record_to_dict(r) for r in rows]}


@platform_admin_router.post(
    '/platform/feature-flags',
    status_code=status.HTTP_201_CREATED,
)
async def create_feature_flag(
    payload: FeatureFlagCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    try:
        row = await conn.fetchrow(
            '''
            insert into app.feature_flags (key, description, enabled, rollout_pct, metadata)
            values ($1, $2, $3, $4, $5::jsonb)
            returning *
            ''',
            payload.key, payload.description, payload.enabled,
            payload.rollout_pct, json.dumps(payload.metadata),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'key_taken'})
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.created',
        entity_type='feature_flag', entity_id=payload.key,
    )
    return record_to_dict(row)


@platform_admin_router.patch('/platform/feature-flags/{key}')
async def patch_feature_flag(
    key: str,
    payload: FeatureFlagPatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    sets, params = [], []
    for field in ('enabled', 'rollout_pct', 'description'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if 'metadata' in patch:
        params.append(json.dumps(patch['metadata']))
        sets.append(f'metadata = ${len(params)}::jsonb')
    sets.append('updated_at = now()')
    params.append(key)
    row = await conn.fetchrow(
        f'update app.feature_flags set {", ".join(sets)} '
        f'where key = ${len(params)} returning *',
        *params,
    )
    if not row:
        raise HTTPException(404, 'flag_not_found')
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.updated',
        entity_type='feature_flag', entity_id=key,
        metadata=patch,
    )
    return record_to_dict(row)


@platform_admin_router.delete(
    '/platform/feature-flags/{key}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_feature_flag(
    key: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    result = await conn.execute(
        'delete from app.feature_flags where key = $1', key,
    )
    if result.endswith(' 0'):
        raise HTTPException(404, 'flag_not_found')
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.deleted',
        entity_type='feature_flag', entity_id=key,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Auth0 admin per-user (M59 — exposición HTTP de auth0_admin)
# ═══════════════════════════════════════════════════════════════════════════
#
# Cross-tenant: solo platform_owner. Operaciones destructivas sobre la
# identidad del user en Auth0 (no su membresía local — para eso usar
# DELETE /v1/tenants/{tid}/members/{uid}).
#
#   POST   /v1/platform/users/{user_id}/auth0/block      — block login
#   POST   /v1/platform/users/{user_id}/auth0/unblock    — unblock
#   POST   /v1/platform/users/{user_id}/auth0/reset-mfa  — limpia MFA enrollments
#   DELETE /v1/platform/users/{user_id}/auth0            — borra de Auth0 (GDPR)
#
# M60/M-004 — los 4 endpoints exigen JUSTIFICATION en body (audit
# trail forense + bloquea cliquear-por-error). El DELETE además
# exige `confirm=True` explícito (irreversible — GDPR). El rate-limit
# per-actor + per-operation evita bulk-actions accidentales.
#
# `user_id` es el UUID local de `app.users`. El handler lookups
# `auth_subject` y delega a `app.services.auth0_admin`. Si el user
# es `pending|xxx` (invitado, nunca loggeado) o si Auth0 no está
# configurado, devuelve 409 explicando el estado.


# ─── Payload schemas (M-004) ─────────────────────────────────────────────


class Auth0AdminActionPayload(BaseModel):
    """Body para block / unblock / reset-mfa. La justificación queda
    en el audit log — al investigador forense le sirve más que el
    timestamp solo."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    justification: str = Field(
        min_length=10, max_length=500,
        description='Por qué se ejecuta la acción. Queda en audit forever.',
    )


class Auth0AdminDeletePayload(Auth0AdminActionPayload):
    """DELETE es irreversible: además de justificación, `confirm=true`."""
    confirm: bool = Field(
        description='Debe ser true. Borra al user de Auth0 (GDPR-style).',
    )


# ─── Rate-limit per actor + per operation (M-004) ────────────────────────
#
# Bucket in-memory por (actor_id, operation_class). Operaciones que sólo
# afectan capacidad de login se limitan más laxo; delete (irreversible)
# es muy restrictivo. Reset = restart limpia counters → aceptable: el
# enforcement crítico vive en audit + alertas.

_AUTH0_RL_BUCKETS: dict[tuple[str, str], list[float]] = {}


def _auth0_rl_check(
    actor_id: str | None, op_class: str, *,
    max_calls: int, window_seconds: float,
) -> None:
    """Token bucket sliding-window. Levanta 429 si excede.

    `op_class`:
      - 'mutate'  → block / unblock / reset-mfa.  max=10/5min.
      - 'destroy' → delete.                        max=3/30min.
    """
    if not actor_id:
        # Service tokens NO llegan acá (router exige platform_owner),
        # pero defensive: si por algun bug actor_id es None, dejar pasar
        # sin rate-limit (las otras gates ya rechazaron).
        return
    key = (actor_id, op_class)
    now = time.monotonic()
    bucket = _AUTH0_RL_BUCKETS.setdefault(key, [])
    # Drop calls fuera del window.
    cutoff = now - window_seconds
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= max_calls:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f'auth0_admin_rate_limit: max {max_calls} {op_class} '
                f'operations / {int(window_seconds / 60)}min per actor. '
                f'Esperar antes de reintentar.'
            ),
        )
    bucket.append(now)


def _auth0_rl_reset_all() -> None:
    """Test-only — limpia todos los buckets."""
    _AUTH0_RL_BUCKETS.clear()


async def _resolve_auth0_subject(
    conn: asyncpg.Connection, user_id: UUID,
) -> str:
    """Lookup `auth_subject` del local user_id. Levanta:
    - 404 si no existe.
    - 409 si es `pending|xxx` (no ha hecho login real todavía).
    """
    row = await conn.fetchrow(
        'select auth_subject, email from app.users where id = $1',
        user_id,
    )
    if row is None:
        raise HTTPException(404, 'user_not_found')
    auth_subject = row['auth_subject']
    if not auth_subject or auth_subject.startswith('pending|'):
        raise HTTPException(
            409, 'user_not_in_auth0_yet — pending invitation; '
            'no Auth0 identity to mutate.',
        )
    return auth_subject


def _require_auth0_configured() -> None:
    """Levanta 501 si Auth0 Management API no está wired (settings missing)."""
    from app.services import auth0_admin  # noqa: PLC0415
    if not auth0_admin.is_configured():
        raise HTTPException(
            501,
            'auth0_management_not_configured — set '
            'AUTH0_SERVICE_CLIENT_ID + AUTH0_SERVICE_CLIENT_SECRET[_FILE]',
        )


def _guard_not_self(actor_id: str | None, target_subject: str, action: str) -> None:
    """SEC-006 (audit 2026-05-27) — rechazar self-targeting en operaciones
    destructivas de Auth0 (block, delete). Sin esto, un platform_owner
    puede borrar/bloquear su propio Auth0 user y quedar locked-out
    permanente (si es el único platform_owner, la fleet queda sin
    administración). 409 conflict — usar lockout via otro path."""
    if actor_id and actor_id == target_subject:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f'self_{action}_forbidden — operación rechazada para evitar '
                'lockout. Pedile a otro platform_owner que ejecute la acción, '
                'o usá un mecanismo distinto (logout / revoke sessions).'
            ),
        )


@platform_admin_router.post(
    '/platform/users/{user_id}/auth0/block',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def block_user_in_auth0(
    user_id: UUID,
    payload: Auth0AdminActionPayload,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Bloquea login del user en Auth0. Idempotente.

    Las sesiones ACTIVAS no se invalidan (JWT siguen valid hasta exp);
    para revocar también las sesiones en flight, usar endpoint separado
    (TODO `POST /v1/platform/users/{uid}/sessions/revoke-all`).

    M-004: `justification` requerida + rate-limit 10/5min por actor.
    """
    from app.services import auth0_admin  # noqa: PLC0415
    actor_id = getattr(request.state, 'actor_id', None)
    _auth0_rl_check(actor_id, 'mutate', max_calls=10, window_seconds=300)
    _require_auth0_configured()
    auth_subject = await _resolve_auth0_subject(conn, user_id)
    _guard_not_self(actor_id, auth_subject, 'block')
    try:
        await auth0_admin.block_user(auth_subject)
    except auth0_admin.Auth0ApiError as exc:
        raise HTTPException(502, f'auth0_block_failed: {exc!s}'[:300]) from exc
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=actor_id,
        action='platform.auth0.user_blocked',
        entity_type='user', entity_id=str(user_id),
        metadata={
            'auth_subject': auth_subject,
            'justification': payload.justification,
        },
    )


@platform_admin_router.post(
    '/platform/users/{user_id}/auth0/unblock',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def unblock_user_in_auth0(
    user_id: UUID,
    payload: Auth0AdminActionPayload,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Desbloquea login en Auth0 (revierte `blocked=true`).

    M-004: `justification` requerida + rate-limit 10/5min por actor.
    """
    from app.services import auth0_admin  # noqa: PLC0415
    actor_id = getattr(request.state, 'actor_id', None)
    _auth0_rl_check(actor_id, 'mutate', max_calls=10, window_seconds=300)
    _require_auth0_configured()
    auth_subject = await _resolve_auth0_subject(conn, user_id)
    try:
        await auth0_admin.unblock_user(auth_subject)
    except auth0_admin.Auth0ApiError as exc:
        raise HTTPException(502, f'auth0_unblock_failed: {exc!s}'[:300]) from exc
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=actor_id,
        action='platform.auth0.user_unblocked',
        entity_type='user', entity_id=str(user_id),
        metadata={
            'auth_subject': auth_subject,
            'justification': payload.justification,
        },
    )


@platform_admin_router.post(
    '/platform/users/{user_id}/auth0/reset-mfa',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def reset_mfa_in_auth0(
    user_id: UUID,
    payload: Auth0AdminActionPayload,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Limpia TODOS los MFA enrollments del user en Auth0.

    Si `MFA_ENFORCEMENT_ENABLED=true` (default), el user vuelve a
    enrolar MFA en su próximo login. Usar cuando el user perdió su
    factor (extravió el teléfono, etc).

    M-004: `justification` requerida + rate-limit 10/5min por actor.
    """
    from app.services import auth0_admin  # noqa: PLC0415
    actor_id = getattr(request.state, 'actor_id', None)
    _auth0_rl_check(actor_id, 'mutate', max_calls=10, window_seconds=300)
    _require_auth0_configured()
    auth_subject = await _resolve_auth0_subject(conn, user_id)
    try:
        await auth0_admin.reset_mfa(auth_subject)
    except auth0_admin.Auth0ApiError as exc:
        raise HTTPException(502, f'auth0_reset_mfa_failed: {exc!s}'[:300]) from exc
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=actor_id,
        action='platform.auth0.user_mfa_reset',
        entity_type='user', entity_id=str(user_id),
        metadata={
            'auth_subject': auth_subject,
            'justification': payload.justification,
        },
    )


@platform_admin_router.delete(
    '/platform/users/{user_id}/auth0',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_user_in_auth0(
    user_id: UUID,
    payload: Auth0AdminDeletePayload,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Borra el user de Auth0 (irreversible — GDPR-style).

    Preferir `block` salvo que el user solicite explícitamente
    deletion. NO toca `app.users` local; ese borrado va por
    pipeline de retention separado.

    Side-effect: el user ya NO puede loguearse. Tampoco aparece más
    en Auth0 logs históricos. Si re-aparece luego (mismo email →
    nuevo signup), Auth0 le asigna un `user_id` distinto.

    M-004: requiere `{justification: str, confirm: true}` en body.
    Rate-limit dedicado: 3 deletes / 30min por actor.
    """
    from app.services import auth0_admin  # noqa: PLC0415
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='delete_requires_confirmation — set "confirm": true en body',
        )
    actor_id = getattr(request.state, 'actor_id', None)
    _auth0_rl_check(actor_id, 'destroy', max_calls=3, window_seconds=1800)
    _require_auth0_configured()
    auth_subject = await _resolve_auth0_subject(conn, user_id)
    _guard_not_self(actor_id, auth_subject, 'delete')
    try:
        await auth0_admin.delete_user(auth_subject)
    except auth0_admin.Auth0ApiError as exc:
        raise HTTPException(502, f'auth0_delete_failed: {exc!s}'[:300]) from exc
    # Marcamos `auth_subject` como pending para que la fila local
    # no quede colgada apuntando a un Auth0 ID inexistente. M57
    # reconciliará si el user re-signa-up con el mismo email.
    await conn.execute(
        '''update app.users
              set auth_subject = $1, status = 'invited', updated_at = now()
            where id = $2''',
        f'pending|{user_id.hex}', user_id,
    )
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=actor_id,
        action='platform.auth0.user_deleted',
        entity_type='user', entity_id=str(user_id),
        metadata={
            'auth_subject': auth_subject,
            'justification': payload.justification,
            'confirmed': True,
        },
    )
