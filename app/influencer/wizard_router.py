"""Wizard 5 pasos para crear personajes — TASK-INFLU-009.

Cada PUT actualiza el JSONB correspondiente en ``influencer.personas`` +
emite audit ``influencer.persona_step_updated``. El POST ``/activate``
valida que los 5 pasos tienen contenido mínimo y mueve ``status`` a
``'active'``.

Endpoints (todos bajo ``/v1/influencer/personas/{persona_id}/``):
- PUT /face
- PUT /body
- PUT /identity
- PUT /voice
- PUT /platforms
- POST /activate
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_models import PersonaResponse
from app.influencer.personas_router import _row_to_response, _set_tenant_scope
from app.influencer.wizard_models import (
    BodyStep,
    FaceStep,
    IdentityStep,
    PlatformsStep,
    VoiceStep,
)

logger = logging.getLogger(__name__)


wizard_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}',
    tags=['influencer-wizard'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


# ─── Helpers ───────────────────────────────────────────────────────────────


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


async def _update_step(
    *,
    conn: asyncpg.Connection,
    tenant_id: UUID,
    persona_id: UUID,
    step: str,
    payload: dict,
) -> PersonaResponse:
    """Actualiza el sub-jsonb del paso + audit row.

    Si la persona está en estado ``archived``, devuelve 409 (no se editan
    archivos). Si ``status='active'``, se permite seguir editando — el
    activate solo cambia el flag, no congela el contenido.
    """
    await _set_tenant_scope(conn, tenant_id)
    sql = (
        f'update influencer.personas '
        f'set {step} = $1, updated_at = now() '
        'where id = $2 and status <> \'archived\' '
        'returning *'
    )
    row = await conn.fetchrow(sql, json.dumps(payload), persona_id)
    if row is None:
        # Could be: persona doesn't exist OR is archived (don't leak which).
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    await _audit_step(conn, tenant_id, persona_id, step, list(payload.keys()))
    return _row_to_response(row)


async def _audit_step(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    persona_id: UUID,
    step: str,
    fields: list[str],
) -> None:
    """Inserta audit row si la tabla `influencer.persona_step_updated`
    existe. Si no (pre-migration), cae a logger.
    """
    try:
        await conn.execute(
            '''
            insert into influencer.persona_step_updated
              (tenant_id, persona_id, step, fields_changed)
            values ($1, $2, $3, $4)
            ''',
            tenant_id, persona_id, step, fields,
        )
    except asyncpg.PostgresError:
        logger.info(
            'persona_step_updated audit (no table): tenant=%s persona=%s step=%s fields=%s',
            tenant_id, persona_id, step, fields,
        )


# ─── PUT /face /body /identity /voice /platforms ───────────────────────────


@wizard_router.put('/face', response_model=PersonaResponse, summary='Wizard paso 1: cara')
async def put_face(
    persona_id: UUID,
    request: Request,
    body: FaceStep,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    return await _update_step(
        conn=conn,
        tenant_id=_require_tenant_id(request),
        persona_id=persona_id,
        step='face',
        payload=body.model_dump(),
    )


@wizard_router.put('/body', response_model=PersonaResponse, summary='Wizard paso 2: cuerpo')
async def put_body(
    persona_id: UUID,
    request: Request,
    body: BodyStep,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    return await _update_step(
        conn=conn,
        tenant_id=_require_tenant_id(request),
        persona_id=persona_id,
        step='body',
        payload=body.model_dump(),
    )


@wizard_router.put('/identity', response_model=PersonaResponse, summary='Wizard paso 3: identidad')
async def put_identity(
    persona_id: UUID,
    request: Request,
    body: IdentityStep,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    # `handle` puede cambiar aquí — también actualizar la columna top-level
    # para que el unique constraint lo enforce. Si conflict, 409.
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    payload = body.model_dump()
    try:
        row = await conn.fetchrow(
            '''
            update influencer.personas
            set identity = $1,
                name = $2,
                handle = $3,
                updated_at = now()
            where id = $4 and status <> 'archived'
            returning *
            ''',
            json.dumps(payload), payload['name'], payload['handle'], persona_id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f'handle already taken: {payload["handle"]}',
        ) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    await _audit_step(conn, tenant_id, persona_id, 'identity', list(payload.keys()))
    return _row_to_response(row)


@wizard_router.put('/voice', response_model=PersonaResponse, summary='Wizard paso 4: voz')
async def put_voice(
    persona_id: UUID,
    request: Request,
    body: VoiceStep,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    return await _update_step(
        conn=conn,
        tenant_id=_require_tenant_id(request),
        persona_id=persona_id,
        step='voice',
        payload=body.model_dump(),
    )


@wizard_router.put(
    '/platforms', response_model=PersonaResponse, summary='Wizard paso 5: plataformas',
)
async def put_platforms(
    persona_id: UUID,
    request: Request,
    body: PlatformsStep,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    return await _update_step(
        conn=conn,
        tenant_id=_require_tenant_id(request),
        persona_id=persona_id,
        step='platforms',
        payload=body.model_dump(),
    )


# ─── POST /activate ────────────────────────────────────────────────────────


@wizard_router.post(
    '/activate',
    response_model=PersonaResponse,
    summary='Activa el personaje (requiere los 5 pasos completos)',
)
async def activate_persona(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> PersonaResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    row = await conn.fetchrow(
        'select * from influencer.personas where id = $1', persona_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if row['status'] == 'archived':
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'cannot activate an archived persona',
        )

    missing = _missing_steps(row)
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'wizard incomplete — missing steps: {", ".join(missing)}',
        )

    updated = await conn.fetchrow(
        '''
        update influencer.personas
        set status = 'active', updated_at = now()
        where id = $1
        returning *
        ''',
        persona_id,
    )
    try:
        await conn.execute(
            '''
            insert into influencer.persona_activated
              (tenant_id, persona_id, activated_by)
            values ($1, $2, $3)
            ''',
            tenant_id, persona_id, user_id,
        )
    except asyncpg.PostgresError:
        logger.info(
            'persona_activated audit (no table): tenant=%s persona=%s',
            tenant_id, persona_id,
        )

    return _row_to_response(updated)


def _missing_steps(row: asyncpg.Record) -> list[str]:
    """Devuelve la lista de pasos sin contenido (jsonb vacío o None)."""
    missing: list[str] = []
    for step in ('face', 'body', 'identity', 'voice', 'platforms'):
        value = row[step]
        if value is None or (isinstance(value, dict) and not value):
            missing.append(step)
    return missing


__all__ = ['wizard_router']
