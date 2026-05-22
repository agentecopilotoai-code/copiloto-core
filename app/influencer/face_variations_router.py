"""Generación de variaciones de cara — TASK-INFLU-010 / UI-INFLU-014.3.

**Refactor síncrono (2026-05-22):** el endpoint POST ahora llama al
provider configurado directamente (mismo patrón que el smoke test
``POST /platform/ai-providers/image/test``), espera la respuesta,
persiste los assets, y devuelve la response con ``status='completed'``
y ``assets=[...]`` poblada.

Razón: el flujo async previo (encolar en ``face_variation_requests`` +
worker dedicado + polling del frontend) era operacionalmente complejo
(requería un worker corriendo) y producía consumo excesivo (polling
infinito si el worker no procesaba). Para el wizard el usuario espera
respuesta inmediata; síncrono cumple ese contrato 1:1 con el smoke test.

Se mantiene la tabla ``influencer.face_variation_requests`` y el GET
status para historia/auditoría; el GET siempre devolverá ``'completed'``
para requests nuevos (no hay más estado intermedio).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.ai.providers.base import (
    PersonaAnchor,
    ProviderContentRejected,
    ProviderError,
)
from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.admin_routes import (
    _build_test_provider,
    _decrypt_secret,
    _set_support_mode,
)
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


def _to_dict(value: object) -> dict:
    """asyncpg sin codec global devuelve jsonb como string serializado;
    decodificamos defensivamente igual que en personas_router._jsonb_to_dict.
    """
    if value is None or value == '':
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


async def _resolve_image_provider_config(conn: asyncpg.Connection) -> tuple[str, str | None, str]:
    """Lee la config del provider de imagen y descifra la API key.

    Mismo patrón usado por el smoke test (``smoke_test_platform_ai_provider``):
    SELECT + Fernet decrypt. Setea ``app.support_mode=true`` localmente
    en la transacción actual para bypasar RLS (la tabla
    ``platform_ai_providers`` es global y solo platform_owner /
    support_mode la lee).

    Returns: ``(provider_name, model, api_key)``.
    """
    await _set_support_mode(conn, True)
    row = await conn.fetchrow(
        """
        select p.provider, p.model, s.hint, s.ciphertext
        from app.platform_ai_providers p
        left join app.platform_secrets s on s.secret_ref = p.secret_ref
        where p.modality = 'image'
        """,
    )
    if row is None or row['provider'] == 'unset' or not row['ciphertext']:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                'El proveedor de imagen no está configurado. '
                'Configúralo en /platform/ai-providers/image (provider + API key).'
            ),
        )
    api_key = _decrypt_secret(row['ciphertext'])
    return row['provider'], row['model'], api_key


def _build_persona_anchor(persona_id: UUID, face: dict, body: dict, voice: dict) -> PersonaAnchor:
    """Mínimo viable para Grok: solo persona_id es obligatorio.
    Le pasamos style hints derivados de los jsonb para consistencia.
    """
    style_tokens = []
    if (e := face.get('ethnicity')):
        style_tokens.append(str(e))
    if (s := body.get('silhouette')):
        style_tokens.append(f'{s} build')
    return PersonaAnchor(
        persona_id=str(persona_id),
        body_traits=body,
        style_tokens=tuple(style_tokens),
        voice_tone=voice.get('tone'),
    )


@face_variations_router.post(
    '/variations',
    response_model=VariationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Genera N variaciones de cara síncronamente (1 click = 1 crédito)',
)
async def create_face_variations(
    persona_id: UUID,
    request: Request,
    body: VariationRequest = VariationRequest(),
    conn: asyncpg.Connection = Depends(get_db),
) -> VariationRequestResponse:
    """Refactor UI-INFLU-014.3 — síncrono.

    1. Lee persona + jsonb completos.
    2. Construye prompt.
    3. INSERT row en face_variation_requests (status='in_progress').
    4. Lee config del provider de imagen + descifra key.
    5. Llama provider.generate_image() sincrono (mismo patrón que el
       smoke test).
    6. Persiste cada result en influencer.assets (URL = data:image/...;base64).
    7. UPDATE request → status='completed'.
    8. Devuelve response con assets pobladas — el frontend muestra
       las thumbnails inmediato sin polling.
    """
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # 1. Lee persona + jsonb.
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

    face = _to_dict(persona['face'])
    body_jsonb = _to_dict(persona['body'])
    identity = _to_dict(persona['identity'])
    voice = _to_dict(persona['voice'])
    prompt = _build_prompt(face=face, body=body_jsonb, identity=identity, voice=voice)

    # 3. INSERT request marcado in_progress (lo cerramos al final).
    req_row = await conn.fetchrow(
        '''
        insert into influencer.face_variation_requests
          (tenant_id, persona_id, requested_count, status, prompt_used, requested_by)
        values ($1, $2, $3, 'in_progress', $4, $5)
        returning *
        ''',
        tenant_id, persona_id, body.count, prompt, user_id,
    )
    req_id = req_row['id']

    # 4. Resolver provider + key (mismo patrón que smoke test).
    try:
        provider_name, model, api_key = await _resolve_image_provider_config(conn)
        # Re-set tenant scope tras la sub-transacción del resolve.
        await _set_tenant_scope(conn, tenant_id)
    except HTTPException:
        # Marca el request como failed y propaga el error claro.
        await conn.execute(
            "update influencer.face_variation_requests set status='failed', "
            "error_message=$1, completed_at=now() where id=$2",
            'image provider not configured', req_id,
        )
        raise

    # 5. Llamar al provider sincrono.
    try:
        adapter = _build_test_provider(provider_name, api_key=api_key, model=model)
    except NotImplementedError as exc:
        await conn.execute(
            "update influencer.face_variation_requests set status='failed', "
            "error_message=$1, completed_at=now() where id=$2",
            f'provider {provider_name} not wired yet: {exc}', req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f'image provider {provider_name!r} not implemented',
        ) from exc

    if model:
        adapter._models['image'] = model  # noqa: SLF001

    anchor = _build_persona_anchor(persona_id, face, body_jsonb, voice)
    try:
        results = await adapter.generate_image(
            prompt=prompt,
            persona_anchor=anchor,
            count=body.count,
            format='1:1',
            safety_mode=True,
        )
    except ProviderContentRejected as exc:
        await conn.execute(
            "update influencer.face_variation_requests set status='failed', "
            "error_message=$1, completed_at=now() where id=$2",
            f'content_rejected: {exc}', req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'content rejected by provider: {exc}',
        ) from exc
    except ProviderError as exc:
        await conn.execute(
            "update influencer.face_variation_requests set status='failed', "
            "error_message=$1, completed_at=now() where id=$2",
            f'provider_error: {exc}', req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'image provider error: {exc}',
        ) from exc

    # 6. Persistir cada result como asset. URL = data: inline para no
    # depender de storage externo en este momento.
    assets_out: list[VariationAsset] = []
    for img in results:
        b64 = base64.b64encode(img.image_bytes).decode('ascii')
        data_url = f'data:{img.mime};base64,{b64}'
        # storage_key = data URL completa (autocontenida; el frontend la usa
        # como `src` directo en <img>).
        asset_row = await conn.fetchrow(
            '''
            insert into influencer.assets
              (tenant_id, persona_id, face_variation_request_id, kind,
               storage_key, mime, width, height, bytes)
            values ($1, $2, $3, 'face_variation', $4, $5, $6, $7, $8)
            returning id, marked_canonical
            ''',
            tenant_id, persona_id, req_id, data_url, img.mime,
            img.width, img.height, len(img.image_bytes),
        )
        assets_out.append(VariationAsset(
            id=asset_row['id'],
            storage_key=data_url,
            url=data_url,
            mime=img.mime,
            width=img.width,
            height=img.height,
            marked_canonical=asset_row['marked_canonical'],
        ))

    # 7. Cerrar request.
    await conn.execute(
        "update influencer.face_variation_requests set status='completed', "
        "completed_at=now() where id=$1",
        req_id,
    )
    logger.info(
        'face_variation completed tenant=%s persona=%s req=%s count=%d provider=%s',
        tenant_id, persona_id, req_id, len(assets_out), provider_name,
    )

    return VariationRequestResponse(
        id=req_id,
        persona_id=persona_id,
        requested_count=body.count,
        status='completed',
        prompt_used=prompt,
        error_message=None,
        assets=assets_out,
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
