"""Platform admin endpoints del módulo Influencer — TASK-INFLU-002.

Endpoints SOLO para ``platform_owner`` con MFA. Decisión D3 del backlog:
la configuración de proveedores IA del módulo es exclusiva del dueño de
la plataforma — los tenants nunca ven ni configuran estos modelos.

Se montan sobre ``platform_admin_router`` (definido en ``app/api/v1/routes.py``)
que ya aplica las dependencies ``authenticate_request`` +
``require_platform_owner`` + ``require_mfa_for_privileged``. Importar este
módulo es lo único que necesita ``app/main.py`` para que las rutas queden
registradas — el decorator ``@platform_admin_router.X(...)`` corre al import.
"""
from __future__ import annotations

import secrets as secrets_module
from typing import Literal

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.v1.routes import platform_admin_router
from app.db.pool import get_db
from app.services.audit import audit
from app.services.influencer.provider_registry import (
    MODALITIES,
    _cache_invalidate as _provider_cache_invalidate,
)


# ─── Schemas ──────────────────────────────────────────────────────────────


class PlatformAIProviderRow(BaseModel):
    """Una fila de ``platform_ai_providers`` para el response GET.

    NO incluye `secret_ref` resuelto ni `ciphertext` — el operador solo ve
    ``hint`` (últimos 4 chars en claro) para identificar qué key está activa.
    """
    modality: Literal['llm', 'image', 'video', 'tts', 'stt']
    provider: str
    model: str | None
    params: dict
    hint: str | None
    updated_at: str | None


class PlatformAIProviderListResponse(BaseModel):
    rows: list[PlatformAIProviderRow]


class PlatformAIProviderUpdate(BaseModel):
    """Body del PATCH. Todos los campos son opt-in — el caller manda solo
    lo que quiere actualizar.

    Si ``secret_value`` viene set, se genera un ``secret_ref`` opaco,
    se persiste en ``app.platform_secrets`` con backend ``env`` y hint =
    últimos 4 chars del valor en claro. La columna ``ciphertext`` queda en
    NULL — el operador es responsable de proveer el valor real al runtime
    vía env var ``INFLUENCER_SECRET_<HINT>`` o vía un backend externo
    (AWS Secrets Manager, Vault) referenciado por ``secret_ref``. **El
    ``secret_value`` nunca se persiste en claro en la DB.**
    """
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    params: dict | None = None
    secret_value: str | None = Field(default=None, min_length=8, max_length=512)
    secret_backend: Literal['env', 'aws_sm', 'vault', 'file'] | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────


def _hint_of(secret_value: str) -> str:
    """Últimos 4 chars del valor en claro. Insuficiente para reconstruir el
    secret pero útil para distinguir cuál key está activa (e.g. ``...A1B2``).
    """
    return secret_value[-4:]


def _generate_secret_ref(modality: str, backend: str) -> str:
    """Genera un secret_ref opaco único. Formato:
    ``infl:{backend}:{modality}:{token}`` — el ``token`` es random 12-char
    hex; no se reusa cross-modality ni cross-backend.
    """
    token = secrets_module.token_hex(6)
    return f'infl:{backend}:{modality}:{token}'


# ─── Endpoints ─────────────────────────────────────────────────────────────


@platform_admin_router.get(
    '/platform/ai-providers',
    response_model=PlatformAIProviderListResponse,
    summary='Lista la configuración de proveedores IA del módulo Influencer',
)
async def list_platform_ai_providers(
    conn: asyncpg.Connection = Depends(get_db),
) -> PlatformAIProviderListResponse:
    """Lista las 5 modalidades con su provider/model/hint activos.

    NO devuelve el secret en claro ni el ``ciphertext``. El campo ``hint``
    es los últimos 4 chars del secret original (suficiente para que el
    operador verifique cuál key está montada).
    """
    rows = await conn.fetch(
        """
        select
          p.modality,
          p.provider,
          p.model,
          p.params,
          s.hint,
          p.updated_at
        from app.platform_ai_providers p
        left join app.platform_secrets s on s.secret_ref = p.secret_ref
        order by p.modality
        """,
    )
    out = [
        PlatformAIProviderRow(
            modality=r['modality'],
            provider=r['provider'],
            model=r['model'],
            params=r['params'] if isinstance(r['params'], dict) else {},
            hint=r['hint'],
            updated_at=r['updated_at'].isoformat() if r['updated_at'] else None,
        )
        for r in rows
    ]
    return PlatformAIProviderListResponse(rows=out)


@platform_admin_router.patch(
    '/platform/ai-providers/{modality}',
    response_model=PlatformAIProviderRow,
    summary='Actualiza la configuración de proveedor IA para una modalidad',
)
async def update_platform_ai_provider(
    modality: str,
    payload: PlatformAIProviderUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> PlatformAIProviderRow:
    """Actualiza el proveedor/modelo/params/secret para una modalidad.

    - Si ``secret_value`` viene set, persiste una nueva fila en
      ``platform_secrets`` con ``hint`` (últimos 4 chars) y vincula via
      ``secret_ref``. **El valor nunca se devuelve por la API** después de
      este PATCH — el GET solo expone ``hint``.
    - Audit ``platform.ai_provider_updated`` con metadata
      ``{modality, provider, secret_rotated}``.
    - Invalida el cache de ``resolve_provider`` para que el cambio tome
      efecto inmediato (en el worker actual; otros workers en ≤ TTL 5 min).
    """
    if modality not in MODALITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'modality must be one of {sorted(MODALITIES)}',
        )

    if (
        payload.provider is None
        and payload.model is None
        and payload.params is None
        and payload.secret_value is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='at least one field must be provided',
        )

    actor_id_raw = getattr(request.state, 'actor_id', None)
    actor_id = None
    if actor_id_raw:
        # actor_id viene como str en request.state (sub del JWT). La FK
        # `app.users.id` es UUID; resolvemos el UUID DB del usuario por
        # auth_subject. Si no existe, dejamos null — el audit captura el
        # actor_subject por separado.
        u = await conn.fetchrow(
            'select id from app.users where auth_subject = $1',
            str(actor_id_raw),
        )
        if u:
            actor_id = u['id']

    secret_rotated = False
    if payload.secret_value is not None:
        backend = payload.secret_backend or 'env'
        secret_ref = _generate_secret_ref(modality, backend)
        await conn.execute(
            """
            insert into app.platform_secrets (secret_ref, backend, hint, created_by)
            values ($1, $2, $3, $4)
            on conflict (secret_ref) do update
              set hint = excluded.hint,
                  rotated_at = now()
            """,
            secret_ref,
            backend,
            _hint_of(payload.secret_value),
            actor_id,
        )
        secret_rotated = True
    else:
        secret_ref = None

    set_clauses = ['updated_at = now()', 'updated_by = $1']
    params_sql: list = [actor_id]
    if payload.provider is not None:
        set_clauses.append(f'provider = ${len(params_sql) + 1}')
        params_sql.append(payload.provider)
    if payload.model is not None:
        set_clauses.append(f'model = ${len(params_sql) + 1}')
        params_sql.append(payload.model)
    if payload.params is not None:
        set_clauses.append(f'params = ${len(params_sql) + 1}::jsonb')
        # asyncpg necesita JSON string explícito para jsonb cast.
        import json as _json
        params_sql.append(_json.dumps(payload.params))
    if secret_ref is not None:
        set_clauses.append(f'secret_ref = ${len(params_sql) + 1}')
        params_sql.append(secret_ref)

    where_idx = len(params_sql) + 1
    params_sql.append(modality)
    sql = (
        'update app.platform_ai_providers set '
        + ', '.join(set_clauses)
        + f' where modality = ${where_idx}'
        + ' returning modality, provider, model, params, secret_ref, updated_at'
    )
    row = await conn.fetchrow(sql, *params_sql)
    if row is None:
        # Defensive — la fila debería existir por el seed de la migración.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'modality {modality} not found',
        )

    # Hint resuelto del secret_ref activo (puede ser el nuevo o el preexistente).
    hint = None
    if row['secret_ref']:
        h = await conn.fetchrow(
            'select hint from app.platform_secrets where secret_ref = $1',
            row['secret_ref'],
        )
        if h:
            hint = h['hint']

    await audit(
        conn,
        tenant_id=None,  # config global, no per-tenant
        actor_type='user',
        actor_id=str(actor_id_raw) if actor_id_raw else None,
        action='platform.ai_provider_updated',
        entity_type='platform_ai_provider',
        entity_id=modality,
        metadata={
            'modality': modality,
            'provider': row['provider'],
            'secret_rotated': secret_rotated,
        },
    )

    # Invalida cache local del worker — sin esto el primer request al provider
    # de esta modalidad sigue usando la config vieja hasta el TTL.
    _provider_cache_invalidate()

    return PlatformAIProviderRow(
        modality=row['modality'],
        provider=row['provider'],
        model=row['model'],
        params=row['params'] if isinstance(row['params'], dict) else {},
        hint=hint,
        updated_at=row['updated_at'].isoformat() if row['updated_at'] else None,
    )


__all__ = [
    'PlatformAIProviderListResponse',
    'PlatformAIProviderRow',
    'PlatformAIProviderUpdate',
    'list_platform_ai_providers',
    'update_platform_ai_provider',
]
