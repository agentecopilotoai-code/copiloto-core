"""Generación async de variaciones de cara — TASK-INFLU-010.

Endpoint POST que encola un request; un worker (TASK-INFLU-012) lo
procesa con el `provider_dispatcher`. Cliente refresca con GET o
WebSocket (TASK-INFLU-018 monta el bus de eventos).
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_router import _set_tenant_scope

logger = logging.getLogger(__name__)


face_variations_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}/face',
    tags=['influencer-face-variations'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


# ─── Models ────────────────────────────────────────────────────────────────


class VariationRequest(BaseModel):
    # UI-INFLU-014.1: cada click del usuario en "Generar +1" cuesta 1 crédito
    # y produce 1 variación. El range mantiene hasta 10 para herramientas
    # internas / scripts / smoke tests.
    count: int = Field(default=1, ge=1, le=10)


class VariationAsset(BaseModel):
    """Una imagen generada asociada a un face_variation_request."""
    id: UUID
    storage_key: str
    url: str  # URL pública/firmada para el frontend; deriva de storage_key.
    mime: str
    width: int | None = None
    height: int | None = None
    marked_canonical: bool = False


class VariationRequestResponse(BaseModel):
    id: UUID
    persona_id: UUID
    requested_count: int
    status: Literal['queued', 'in_progress', 'completed', 'failed']
    prompt_used: str | None = None
    error_message: str | None = None
    # UI-INFLU-014.1: cuando status='completed', estos son los assets
    # generados — el wizard hace polling y muestra las thumbnails.
    assets: list[VariationAsset] = Field(default_factory=list)


def _storage_key_to_url(storage_key: str) -> str:
    """Convierte el storage_key opaco en una URL accesible por el frontend.

    En producción esto firma con S3/CloudFront. En dev (storage_upload
    devuelve `s3://stub/...`), el frontend recibe la misma key prefijada
    y la sirve desde su CDN/proxy. La función centraliza el mapeo para
    que cuando exista S3 real solo cambie este helper.
    """
    if storage_key.startswith(('http://', 'https://')):
        return storage_key
    # Default: mapeo idempotente — el frontend admin sabe interpretar
    # `tenants/.../face_variations/...` y servirlo via su proxy.
    return f'/admin/api/core/v1/influencer/storage/{storage_key}'


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


def _build_prompt(
    face: dict | None,
    body: dict | None = None,
    identity: dict | None = None,
    voice: dict | None = None,
) -> str:
    """Construye un prompt determinista usando TODOS los jsonb que el usuario
    haya pre-seleccionado hasta ahora (face + body + identity + voice).

    Cada campo se incluye solo si tiene valor — el wizard puede llamar a
    "Generar +1" en cualquier paso (el preview es persistente), así que
    los pasos posteriores al actual pueden estar vacíos. El prompt se
    enriquece progresivamente conforme el usuario avanza.

    El image provider (configurado en ``platform_ai_providers.image``)
    recibe este prompt; el ``persona_anchor`` + ``reference_image_urls``
    van aparte vía PersonaAnchor para mantener consistencia de cara
    entre generaciones.
    """
    face = face if isinstance(face, dict) else {}
    body = body if isinstance(body, dict) else {}
    identity = identity if isinstance(identity, dict) else {}
    voice = voice if isinstance(voice, dict) else {}

    parts: list[str] = ['portrait headshot']

    # ── Cara ────────────────────────────────────────────────────────────
    if (ethnicity := face.get('ethnicity')):
        parts.append(str(ethnicity))
    if (eye_color := face.get('eye_color')):
        parts.append(f'{eye_color} eyes')
    hair_color = face.get('hair_color', '')
    hair_style = face.get('hair_style', '')
    if hair_color or hair_style:
        parts.append(f'{hair_color} {hair_style} hair'.strip())
    if (skin_tone := face.get('skin_tone')):
        parts.append(f'skin tone {skin_tone}')
    if (age_range := face.get('age_range')):
        parts.append(f'age range {age_range}')

    # ── Cuerpo ──────────────────────────────────────────────────────────
    if (silhouette := body.get('silhouette')):
        parts.append(f'{silhouette} build')
    if (posture := body.get('posture')):
        parts.append(f'{posture} posture')
    if (height_cm := body.get('height_cm')):
        parts.append(f'{height_cm}cm tall')

    # ── Identidad (location + categorías como context visual) ───────────
    # Solo agregamos pistas visuales (city/country/categories) que
    # ayudan al provider a elegir wardrobe/scenery. El name/handle/age
    # numérico NO van al prompt — son metadata del personaje.
    if (city := identity.get('city')) and (country := identity.get('country')):
        parts.append(f'{city} {country} setting')
    elif country := identity.get('country'):
        parts.append(f'{country} setting')
    categories = identity.get('categories') or []
    if isinstance(categories, list) and categories:
        # Limit a 3 para no saturar el prompt.
        parts.append(f"style: {', '.join(str(c) for c in categories[:3])}")

    # ── Voz (tone como pista de expresión facial) ───────────────────────
    if (tone := voice.get('tone')):
        parts.append(f'{tone} expression')

    # Cola siempre — instrucciones de safety + estilo profesional.
    parts.append('consistent identity, professional photography, neutral background')

    return ', '.join(p.strip() for p in parts if p.strip())


# ─── Endpoints ─────────────────────────────────────────────────────────────


@face_variations_router.post(
    '/variations',
    response_model=VariationRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary='Encola N variaciones de cara (async)',
)
async def create_face_variations(
    persona_id: UUID,
    request: Request,
    body: VariationRequest = VariationRequest(),
    conn: asyncpg.Connection = Depends(get_db),
) -> VariationRequestResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # Lee TODOS los jsonb que el usuario haya pre-seleccionado para
    # construir un prompt rico (face + body + identity + voice).
    persona = await conn.fetchrow(
        '''
        select id, face, body, identity, voice, status
        from influencer.personas where id = $1
        ''',
        persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if persona['status'] == 'archived':
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'cannot generate for archived persona',
        )

    # asyncpg sin codec global devuelve jsonb como string serializado;
    # decodificamos defensivamente igual que en personas_router._jsonb_to_dict.
    def _to_dict(value: object) -> dict:
        if value is None or value == '':
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            import json
            return json.loads(value)
        return {}  # tipo inesperado → tratamos como vacío

    prompt = _build_prompt(
        face=_to_dict(persona['face']),
        body=_to_dict(persona['body']),
        identity=_to_dict(persona['identity']),
        voice=_to_dict(persona['voice']),
    )
    row = await conn.fetchrow(
        '''
        insert into influencer.face_variation_requests
          (tenant_id, persona_id, requested_count, status, prompt_used, requested_by)
        values ($1, $2, $3, 'queued', $4, $5)
        returning *
        ''',
        tenant_id, persona_id, body.count, prompt, user_id,
    )
    logger.info(
        'face_variation queued tenant=%s persona=%s count=%d req_id=%s',
        tenant_id, persona_id, body.count, row['id'],
    )
    return VariationRequestResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        requested_count=row['requested_count'],
        status=row['status'],
        prompt_used=row['prompt_used'],
        error_message=row['error_message'],
        assets=[],  # recién encolado, todavía no hay assets.
    )


async def _fetch_request_assets(
    conn: asyncpg.Connection, request_id: UUID,
) -> list[VariationAsset]:
    """Devuelve los assets generados para un face_variation_request."""
    rows = await conn.fetch(
        '''
        select id, storage_key, mime, width, height, marked_canonical
        from influencer.assets
        where face_variation_request_id = $1
          and kind = 'face_variation'
        order by created_at
        ''',
        request_id,
    )
    return [
        VariationAsset(
            id=r['id'],
            storage_key=r['storage_key'],
            url=_storage_key_to_url(r['storage_key']),
            mime=r['mime'],
            width=r['width'],
            height=r['height'],
            marked_canonical=r['marked_canonical'],
        )
        for r in rows
    ]


@face_variations_router.get(
    '/variations/{variation_request_id}',
    response_model=VariationRequestResponse,
    summary='Estado de un request de variaciones',
)
async def get_face_variation_status(
    persona_id: UUID,
    variation_request_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> VariationRequestResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    row = await conn.fetchrow(
        '''
        select * from influencer.face_variation_requests
        where id = $1 and persona_id = $2
        ''',
        variation_request_id, persona_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'variation request not found')
    assets = await _fetch_request_assets(conn, row['id'])
    return VariationRequestResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        requested_count=row['requested_count'],
        status=row['status'],
        prompt_used=row['prompt_used'],
        error_message=row['error_message'],
        assets=assets,
    )


__all__ = ['face_variations_router', '_build_prompt']
