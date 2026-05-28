"""Platform admin endpoints — Email Providers (v2.0.0).

CRUD + test endpoint para `app.email_providers`. Solo platform_owner +
MFA — mismo gating que AI providers.

Espeja el patrón de `copiloto_core/platform_admin/admin_routes.py`:
  - Las rutas se decoran sobre `platform_admin_router` que ya tiene los
    deps de auth.
  - Soporte de RLS via `_set_support_mode` antes de cada operación
    (la tabla tiene `policy WHERE app.support_mode()`).
  - Cifrado de la api_key con Fernet (`AI_PROVIDER_MASTER_KEY` shared).
  - Audit en cada write.

Endpoints:
  GET    /v1/platform/email-providers           — list (sin api_key)
  POST   /v1/platform/email-providers           — create
  PATCH  /v1/platform/email-providers/{id}      — update
  DELETE /v1/platform/email-providers/{id}      — hard delete
  POST   /v1/platform/email-providers/{id}/test — send test email
"""
from __future__ import annotations

import json
import time
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from copiloto_core.api.v1.routes import platform_admin_router
from copiloto_core.db.pool import get_db
from copiloto_core.email.providers.base import (
    EmailMessage,
    ProviderError,
)
from copiloto_core.email.providers.factory import make_email_provider
from copiloto_core.platform_admin.admin_routes import (
    _encrypt_secret,
    _set_support_mode,
)
from copiloto_core.services.audit import audit


# ─── Schemas ──────────────────────────────────────────────────────────────


ProviderType = Literal['resend', 'sendgrid', 'mailgun', 'smtp']

# Regex permisivo de email — el provider real (Resend/SendGrid/etc) hace la
# validación canónica al enviar. Acá solo evitamos basura obvia. No usamos
# `EmailStr` para no agregar dep `email-validator` (no está en el core).
_EMAIL_RE = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'


class EmailProviderRow(BaseModel):
    """Una fila para el response. NO incluye la api_key — solo `has_api_key`
    bool para que la UI sepa si debe pedir rotación en el form de edit."""
    id: str
    code: str
    provider_type: ProviderType
    name: str
    config_jsonb: dict
    has_api_key: bool
    from_address_override: str | None
    from_name_override: str | None
    is_active: bool
    priority: int
    created_at: str
    updated_at: str


class EmailProviderListResponse(BaseModel):
    rows: list[EmailProviderRow]


class EmailProviderCreate(BaseModel):
    """Body del POST. La api_key viaja en claro UNA SOLA VEZ — se cifra antes
    de persistir y nunca se devuelve por la API después.

    `model_config = extra='forbid'`: campos desconocidos (typo, drift) → 422.
    """
    model_config = ConfigDict(extra='forbid')

    code: str = Field(min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9\-_]{0,63}$')
    provider_type: ProviderType
    name: str = Field(min_length=1, max_length=255)
    config_jsonb: dict = Field(default_factory=dict)
    api_key: str = Field(min_length=1, max_length=4096)
    from_address_override: str | None = Field(default=None, max_length=255, pattern=_EMAIL_RE)
    from_name_override: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    priority: int = Field(default=100, ge=0, le=10_000)


class EmailProviderUpdate(BaseModel):
    """Body del PATCH. Todos los campos son opt-in. Si `api_key` viene set,
    se rota (cifra el nuevo y persiste); si viene None, se preserva el
    ciphertext actual."""
    model_config = ConfigDict(extra='forbid')

    code: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9\-_]{0,63}$')
    provider_type: ProviderType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    config_jsonb: dict | None = None
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    from_address_override: str | None = Field(default=None, max_length=255, pattern=_EMAIL_RE)
    from_name_override: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)


class EmailProviderTestRequest(BaseModel):
    """Body del POST /{id}/test. `to_address` es a quién mandar el email."""
    model_config = ConfigDict(extra='forbid')
    to_address: str = Field(min_length=3, max_length=255, pattern=_EMAIL_RE)


class EmailProviderTestResponse(BaseModel):
    """Resultado uniforme del smoke test. La UI muestra `ok` + `error` si
    fail; nunca devolvemos 5xx por errores del provider — los traducimos
    a 200 con `ok=false` para que el operador vea el detalle."""
    ok: bool
    provider_code: str
    message_id: str = ''
    latency_ms: float = 0.0
    error: str | None = None
    error_class: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────


def _row_to_response(row: dict) -> EmailProviderRow:
    """asyncpg.Record → EmailProviderRow. Hace los ISO + dict casts."""
    config = row.get('config_jsonb')
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = {}
    return EmailProviderRow(
        id=str(row['id']),
        code=row['code'],
        provider_type=row['provider_type'],
        name=row['name'],
        config_jsonb=config if isinstance(config, dict) else {},
        has_api_key=bool(row.get('api_key_ciphertext')),
        from_address_override=row.get('from_address_override'),
        from_name_override=row.get('from_name_override'),
        is_active=bool(row['is_active']),
        priority=int(row['priority']),
        created_at=row['created_at'].isoformat() if row.get('created_at') else '',
        updated_at=row['updated_at'].isoformat() if row.get('updated_at') else '',
    )


async def _resolve_actor_id(
    conn: asyncpg.Connection, request: Request,
) -> UUID | None:
    """`request.state.actor_id` es el sub de Auth0 (str). Lo resolvemos al
    UUID de `app.users.id` para FKs. Si no existe, retorna None y el audit
    captura el sub como `actor_id` string aparte."""
    actor_id_raw = getattr(request.state, 'actor_id', None)
    if not actor_id_raw:
        return None
    u = await conn.fetchrow(
        'select id from app.users where auth_subject = $1',
        str(actor_id_raw),
    )
    return u['id'] if u else None


# ─── Endpoints ────────────────────────────────────────────────────────────


@platform_admin_router.get(
    '/platform/email-providers',
    response_model=EmailProviderListResponse,
    summary='Lista los providers de email configurados (sin api_key)',
)
async def list_email_providers(
    conn: asyncpg.Connection = Depends(get_db),
) -> EmailProviderListResponse:
    async with conn.transaction():
        await _set_support_mode(conn, True)
        rows = await conn.fetch(
            '''
            select id, code, provider_type, name, config_jsonb,
                   api_key_ciphertext, from_address_override,
                   from_name_override, is_active, priority,
                   created_at, updated_at
            from app.email_providers
            order by priority asc, code asc
            '''
        )
    return EmailProviderListResponse(
        rows=[_row_to_response(dict(r)) for r in rows],
    )


@platform_admin_router.post(
    '/platform/email-providers',
    response_model=EmailProviderRow,
    status_code=status.HTTP_201_CREATED,
    summary='Crea un nuevo provider de email',
)
async def create_email_provider(
    payload: EmailProviderCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> EmailProviderRow:
    ciphertext = _encrypt_secret(payload.api_key)
    async with conn.transaction():
        await _set_support_mode(conn, True)
        actor_id = await _resolve_actor_id(conn, request)
        try:
            row = await conn.fetchrow(
                '''
                insert into app.email_providers
                  (code, provider_type, name, config_jsonb,
                   api_key_ciphertext, from_address_override,
                   from_name_override, is_active, priority, created_by)
                values ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
                returning id, code, provider_type, name, config_jsonb,
                          api_key_ciphertext, from_address_override,
                          from_name_override, is_active, priority,
                          created_at, updated_at
                ''',
                payload.code,
                payload.provider_type,
                payload.name,
                json.dumps(payload.config_jsonb),
                # asyncpg con text column acepta str. Fernet emite bytes,
                # decode a utf-8 (es base64-urlsafe).
                ciphertext.decode('ascii'),
                str(payload.from_address_override) if payload.from_address_override else None,
                payload.from_name_override,
                payload.is_active,
                payload.priority,
                actor_id,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'code already exists: {payload.code}',
            ) from exc

        await audit(
            conn,
            tenant_id=None,
            actor_type='user',
            actor_id=str(getattr(request.state, 'actor_id', '') or '') or None,
            action='platform.email_provider.created',
            entity_type='email_provider',
            entity_id=str(row['id']),
            metadata={
                'code': row['code'],
                'provider_type': row['provider_type'],
                'is_active': row['is_active'],
                'priority': row['priority'],
            },
        )

    return _row_to_response(dict(row))


@platform_admin_router.patch(
    '/platform/email-providers/{provider_id}',
    response_model=EmailProviderRow,
    summary='Actualiza un provider de email (todos los campos opcionales)',
)
async def update_email_provider(
    provider_id: str,
    payload: EmailProviderUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> EmailProviderRow:
    try:
        pid = UUID(provider_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='provider_id must be a UUID',
        ) from exc

    # Construcción dinámica del UPDATE (solo cambia lo enviado).
    set_clauses: list[str] = []
    params: list[Any] = []

    def _add(col: str, value: Any) -> None:
        params.append(value)
        set_clauses.append(f'{col} = ${len(params)}')

    if payload.code is not None:
        _add('code', payload.code)
    if payload.provider_type is not None:
        _add('provider_type', payload.provider_type)
    if payload.name is not None:
        _add('name', payload.name)
    if payload.config_jsonb is not None:
        params.append(json.dumps(payload.config_jsonb))
        set_clauses.append(f'config_jsonb = ${len(params)}::jsonb')
    api_key_rotated = False
    if payload.api_key is not None:
        ciphertext = _encrypt_secret(payload.api_key)
        params.append(ciphertext.decode('ascii'))
        set_clauses.append(f'api_key_ciphertext = ${len(params)}')
        api_key_rotated = True
    if payload.from_address_override is not None:
        _add('from_address_override', str(payload.from_address_override))
    if payload.from_name_override is not None:
        _add('from_name_override', payload.from_name_override)
    if payload.is_active is not None:
        _add('is_active', payload.is_active)
    if payload.priority is not None:
        _add('priority', payload.priority)

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='at least one field must be provided',
        )

    params.append(pid)
    sql = (
        'update app.email_providers set '
        + ', '.join(set_clauses)
        + f' where id = ${len(params)}'
        + ' returning id, code, provider_type, name, config_jsonb,'
          ' api_key_ciphertext, from_address_override, from_name_override,'
          ' is_active, priority, created_at, updated_at'
    )

    async with conn.transaction():
        await _set_support_mode(conn, True)
        try:
            row = await conn.fetchrow(sql, *params)
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='code already exists',
            ) from exc
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'provider {provider_id} not found',
            )

        await audit(
            conn,
            tenant_id=None,
            actor_type='user',
            actor_id=str(getattr(request.state, 'actor_id', '') or '') or None,
            action='platform.email_provider.updated',
            entity_type='email_provider',
            entity_id=str(row['id']),
            metadata={
                'code': row['code'],
                'provider_type': row['provider_type'],
                'api_key_rotated': api_key_rotated,
                'is_active': row['is_active'],
            },
        )

    return _row_to_response(dict(row))


@platform_admin_router.delete(
    '/platform/email-providers/{provider_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Borra un provider de email (hard delete)',
)
async def delete_email_provider(
    provider_id: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    try:
        pid = UUID(provider_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='provider_id must be a UUID',
        ) from exc

    async with conn.transaction():
        await _set_support_mode(conn, True)
        row = await conn.fetchrow(
            'select code, provider_type from app.email_providers where id = $1',
            pid,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'provider {provider_id} not found',
            )
        await conn.execute(
            'delete from app.email_providers where id = $1', pid,
        )
        await audit(
            conn,
            tenant_id=None,
            actor_type='user',
            actor_id=str(getattr(request.state, 'actor_id', '') or '') or None,
            action='platform.email_provider.deleted',
            entity_type='email_provider',
            entity_id=str(pid),
            metadata={
                'code': row['code'],
                'provider_type': row['provider_type'],
            },
        )
    # 204 No Content: el handler debe devolver un Response sin body porque
    # FastAPI rechaza response_model con status 204.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@platform_admin_router.post(
    '/platform/email-providers/{provider_id}/test',
    response_model=EmailProviderTestResponse,
    summary='Envía un email de prueba con este provider',
)
async def test_email_provider(
    provider_id: str,
    payload: EmailProviderTestRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> EmailProviderTestResponse:
    try:
        pid = UUID(provider_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='provider_id must be a UUID',
        ) from exc

    async with conn.transaction():
        await _set_support_mode(conn, True)
        row = await conn.fetchrow(
            '''
            select id, code, provider_type, name, config_jsonb,
                   api_key_ciphertext, from_address_override,
                   from_name_override
            from app.email_providers
            where id = $1
            ''',
            pid,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'provider {provider_id} not found',
        )

    # Fallback sender — del Settings global. El factory ya combina con el
    # override per-provider si está set.
    from copiloto_core.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()

    try:
        adapter = make_email_provider(
            dict(row),
            fallback_from_address=settings.email_from_address,
            fallback_from_name=settings.email_from_name,
        )
    except Exception as exc:
        return EmailProviderTestResponse(
            ok=False,
            provider_code=row['code'],
            error=str(exc),
            error_class=type(exc).__name__,
        )

    test_msg = EmailMessage(
        to_address=str(payload.to_address),
        subject=f'CopilotoIA — test desde provider {row["code"]}',
        html=(
            '<p>Este es un email de prueba enviado desde el admin panel.</p>'
            f'<p>Provider: <strong>{row["code"]}</strong> '
            f'({row["provider_type"]})</p>'
        ),
        text=(
            f'Este es un email de prueba enviado desde el admin panel.\n'
            f'Provider: {row["code"]} ({row["provider_type"]})\n'
        ),
        tags={'kind': 'admin_smoke_test'},
    )

    # Audit del intento (independiente del resultado) — útil para detectar
    # que el operador probó el provider antes de activarlo.
    await audit(
        conn,
        tenant_id=None,
        actor_type='user',
        actor_id=str(getattr(request.state, 'actor_id', '') or '') or None,
        action='platform.email_provider.tested',
        entity_type='email_provider',
        entity_id=str(pid),
        metadata={
            'code': row['code'],
            'provider_type': row['provider_type'],
        },
    )

    t0 = time.monotonic()
    try:
        result = await adapter.send(test_msg)
    except ProviderError as exc:
        return EmailProviderTestResponse(
            ok=False,
            provider_code=row['code'],
            latency_ms=(time.monotonic() - t0) * 1000.0,
            error=str(exc),
            error_class=type(exc).__name__,
        )
    return EmailProviderTestResponse(
        ok=result.success,
        provider_code=result.provider_code or row['code'],
        message_id=result.message_id,
        latency_ms=result.latency_ms,
        error=result.error,
    )


__all__ = [
    'EmailProviderCreate',
    'EmailProviderListResponse',
    'EmailProviderRow',
    'EmailProviderTestRequest',
    'EmailProviderTestResponse',
    'EmailProviderUpdate',
    'create_email_provider',
    'delete_email_provider',
    'list_email_providers',
    'test_email_provider',
    'update_email_provider',
]
