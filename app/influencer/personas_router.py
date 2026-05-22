"""CRUD de personajes (``influencer.personas``) — TASK-INFLU-008.

Endpoints bajo ``/v1/influencer/personas`` montados sobre
``influencer_router`` (que ya provee ``authenticate_request`` +
``ensure_module_enabled``).

Política:
- Lista filtra por ``status`` (default: todos menos ``archived``).
- Soft delete: ``DELETE`` solo setea ``archived_at`` (el handle se
  mantiene reservado para evitar reuso accidental por otro usuario).
- ``DELETE`` exige ``require_mfa_for_privileged`` (defensa
  defense-in-depth: archivar un personaje rompe analytics + bot routing
  → operación sensible).
- RLS: cada query setea ``app.tenant_id`` para que las policies
  declaradas en la migración funcionen. Cross-tenant no es accesible
  ni con UUID adivinado.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.core.security import authenticate_request, require_mfa_for_privileged
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_models import (
    PersonaCreate,
    PersonaResponse,
    PersonasList,
    PersonaStatus,
    PersonaUpdate,
)

logger = logging.getLogger(__name__)


personas_router = APIRouter(
    prefix='/v1/influencer/personas',
    tags=['influencer-personas'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


# ─── Helpers ───────────────────────────────────────────────────────────────


async def _set_tenant_scope(conn: asyncpg.Connection, tenant_id: UUID) -> None:
    """Setea ``app.tenant_id`` GUC para que RLS aplique en la transacción."""
    await conn.execute('select set_config($1, $2, true)', 'app.tenant_id', str(tenant_id))


def _jsonb_to_dict(value: object) -> dict:
    """asyncpg sin codec global devuelve jsonb como string serializado.

    Acepta dict (codec registrado), str (default sin codec) o None.
    Devuelve siempre dict — vacío si la columna era NULL/empty.
    """
    if value is None or value == '':
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    # Fallback defensivo: si llega otro tipo, dejar que Pydantic falle claro.
    return value  # type: ignore[return-value]


def _row_to_response(row: asyncpg.Record) -> PersonaResponse:
    return PersonaResponse(
        id=row['id'],
        tenant_id=row['tenant_id'],
        name=row['name'],
        handle=row['handle'],
        status=row['status'],
        category=row['category'],
        face=_jsonb_to_dict(row['face']),
        body=_jsonb_to_dict(row['body']),
        identity=_jsonb_to_dict(row['identity']),
        voice=_jsonb_to_dict(row['voice']),
        platforms=_jsonb_to_dict(row['platforms']),
        mode=row['mode'],
        disclose_ai=row['disclose_ai'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        created_by=row['created_by'],
        archived_at=row['archived_at'],
    )


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='module not available for this caller',
        )
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


# ─── Endpoints ─────────────────────────────────────────────────────────────


@personas_router.get(
    '',
    response_model=PersonasList,
    summary='Lista personajes del tenant',
)
async def list_personas(
    request: Request,
    status_filter: Annotated[PersonaStatus | None, Query(alias='status')] = None,
    category: Annotated[str | None, Query(max_length=64)] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    include_archived: bool = False,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonasList:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    where = ['tenant_id = $1']
    params: list = [tenant_id]
    if status_filter is not None:
        params.append(status_filter)
        where.append(f'status = ${len(params)}')
    elif not include_archived:
        where.append("status <> 'archived'")
    if category:
        params.append(category)
        where.append(f'category = ${len(params)}')
    if search:
        params.append(f'%{search.lower()}%')
        where.append(
            f'(lower(name) like ${len(params)} or lower(handle) like ${len(params)})',
        )

    sql = (
        'select * from influencer.personas '
        f'where {" and ".join(where)} '
        'order by created_at desc'
    )
    rows = await conn.fetch(sql, *params)
    return PersonasList(
        items=[_row_to_response(r) for r in rows],
        total=len(rows),
    )


@personas_router.get(
    '/{persona_id}',
    response_model=PersonaResponse,
    summary='Detalle de un personaje',
)
async def get_persona(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    row = await conn.fetchrow(
        'select * from influencer.personas where id = $1', persona_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    return _row_to_response(row)


@personas_router.post(
    '',
    response_model=PersonaResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Crea un personaje en estado draft',
)
async def create_persona(
    request: Request,
    body: PersonaCreate,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)
    try:
        # JSONB columns: asyncpg requires a JSON-encoded string + explicit
        # ``::jsonb`` cast (passing a dict raises DataError "expected str,
        # got dict"). Mirrors the pattern in wizard_router / admin_routes.
        row = await conn.fetchrow(
            '''
            insert into influencer.personas
              (tenant_id, name, handle, status, category, face, body,
               identity, voice, platforms, mode, disclose_ai, created_by)
            values
              ($1, $2, $3, 'draft', $4,
               $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
               $10, $11, $12)
            returning *
            ''',
            tenant_id, body.name, body.handle, body.category,
            json.dumps(body.face), json.dumps(body.body),
            json.dumps(body.identity), json.dumps(body.voice),
            json.dumps(body.platforms),
            body.mode, body.disclose_ai, user_id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f'handle already taken: {body.handle}',
        ) from exc
    return _row_to_response(row)


@personas_router.patch(
    '/{persona_id}',
    response_model=PersonaResponse,
    summary='Update parcial de un personaje',
)
async def patch_persona(
    persona_id: UUID,
    request: Request,
    body: PersonaUpdate,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    # Sólo campos provistos (omitir None y unset).
    updates = body.model_dump(exclude_unset=True)

    # TASK-INFLU-018 — Enforcer disclose_ai: solo platform_owner puede
    # desactivar la disclosure. Un tenant común no puede ocultar que su
    # influencer es generado por IA.
    if updates.get('disclose_ai') is False:
        if not getattr(request.state, 'is_platform_owner', False):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                'AI disclosure is required by platform policy',
            )
    if not updates:
        # Nada que actualizar — devolver fila actual.
        row = await conn.fetchrow(
            'select * from influencer.personas where id = $1', persona_id,
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
        return _row_to_response(row)

    # JSONB columns must be JSON-encoded + casted (see create_persona note).
    _JSONB_COLS = {'face', 'body', 'identity', 'voice', 'platforms'}
    set_clauses: list[str] = []
    params: list = []
    for col, val in updates.items():
        if col in _JSONB_COLS:
            params.append(json.dumps(val) if val is not None else None)
            set_clauses.append(f'{col} = ${len(params)}::jsonb')
        else:
            params.append(val)
            set_clauses.append(f'{col} = ${len(params)}')
    set_clauses.append('updated_at = now()')
    params.append(persona_id)
    sql = (
        f'update influencer.personas set {", ".join(set_clauses)} '
        f'where id = ${len(params)} returning *'
    )
    try:
        row = await conn.fetchrow(sql, *params)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'handle already taken',
        ) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    return _row_to_response(row)


@personas_router.delete(
    '/{persona_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary='Archiva un personaje (soft delete, requiere MFA)',
    dependencies=[Depends(require_mfa_for_privileged)],
)
async def archive_persona(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)
    result = await conn.execute(
        '''
        update influencer.personas
        set status = 'archived', archived_at = now(), updated_at = now()
        where id = $1 and status <> 'archived'
        ''',
        persona_id,
    )
    # asyncpg returns 'UPDATE N' string; parse final int.
    rows_affected = int(result.split()[-1]) if result.startswith('UPDATE') else 0
    if rows_affected == 0:
        # Either not found or already archived → 404 (don't leak the difference).
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    logger.info(
        'persona archived tenant_id=%s persona_id=%s by user_id=%s',
        tenant_id, persona_id, user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ['personas_router']
