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

import json
import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.ai.providers.base import (
    PersonaAnchor,
    ProviderContentRejected,
    ProviderError,
)
from app.api.v1._helpers.knowledge_storage_db import (
    fetch_tenant_knowledge_storage_config,
)
from app.core.config import get_settings
from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.admin_routes import (
    _build_test_provider,
    _decrypt_secret,
    _set_support_mode,
)
from app.influencer.personas_router import _set_tenant_scope
from app.services.influencer_storage import (
    read_local_asset,
    s3_get_asset_bytes,
    store_face_variation_asset,
    store_reference_asset,
)

logger = logging.getLogger(__name__)


face_variations_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}/face',
    tags=['influencer-face-variations'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


# UI-INFLU-014.7 — Router separado para servir archivos del storage.
# Path: `GET /v1/influencer/storage/{key:path}`. Auth requerido +
# tenant_scope: la key SIEMPRE empieza con `tenants/{tenant_id}/...`
# y solo se sirve si el `tenant_id` del path matchea el del request
# (RLS de aplicación).
storage_router = APIRouter(
    prefix='/v1/influencer/storage',
    tags=['influencer-storage'],
    dependencies=[Depends(authenticate_request)],
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
    if storage_key.startswith(('http://', 'https://', 'data:')):
        # UI-INFLU-014.7: `data:` URLs (base64 inline) son auto-contenidas;
        # el navegador las renderiza directo en <img src=>. NO las
        # prefijamos con el path del proxy — eso causaba que el frontend
        # hiciera GET /admin/api/core/v1/influencer/storage/data:image/...
        # con el data URL como path (404 / 200 inválido).
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

    # 6. Persistir cada result como asset usando el storage del tenant
    # (mismo backend que knowledge: local Docker volume o S3 según
    # `app.tenant_settings.knowledge_storage`).
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    settings_obj = get_settings()
    assets_out: list[VariationAsset] = []
    for idx, img in enumerate(results):
        try:
            stored = store_face_variation_asset(
                data=img.image_bytes,
                tenant_id=str(tenant_id),
                request_id=str(req_id),
                idx=idx,
                mime=img.mime,
                settings=settings_obj,
                config=storage_config,
            )
        except Exception as exc:  # noqa: BLE001
            await conn.execute(
                "update influencer.face_variation_requests set status='failed', "
                "error_message=$1, completed_at=now() where id=$2",
                f'storage_error: {exc}', req_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'failed to persist asset: {exc}',
            ) from exc
        asset_row = await conn.fetchrow(
            '''
            insert into influencer.assets
              (tenant_id, persona_id, face_variation_request_id, kind,
               storage_key, mime, width, height, bytes)
            values ($1, $2, $3, 'face_variation', $4, $5, $6, $7, $8)
            returning id, marked_canonical
            ''',
            tenant_id, persona_id, req_id, stored.object_key, img.mime,
            img.width, img.height, stored.size_bytes,
        )
        assets_out.append(VariationAsset(
            id=asset_row['id'],
            storage_key=stored.object_key,
            url=_storage_key_to_url(stored.object_key),
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


# ─── Upload de referencia (UI-INFLU-014.13) ────────────────────────────────
#
# El composer del studio permite al usuario subir una foto de referencia
# que el provider usa como condicionador visual (la escena, no la cara).
# El upload se persiste en el mismo storage que face-variations/generations,
# bajo el prefix `references/{persona_id}/`. Devolvemos `url` lista para
# pasar como `params.reference_image_url` en el POST /generate.


_REFERENCE_MIME_ALLOWLIST = {
    'image/png', 'image/jpeg', 'image/webp', 'image/gif',
}
_REFERENCE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class ReferenceUploadResponse(BaseModel):
    storage_key: str
    url: str
    mime: str
    size_bytes: int


@face_variations_router.post(
    '/reference',
    response_model=ReferenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Sube una foto de referencia para el composer del studio',
)
async def upload_reference_image(
    persona_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    conn: asyncpg.Connection = Depends(get_db),
) -> ReferenceUploadResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    # Verifica que la persona exista y pertenezca al tenant — RLS adicional.
    persona = await conn.fetchrow(
        'select id from influencer.personas where id = $1', persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    mime = (file.content_type or '').lower().split(';', 1)[0].strip()
    if mime not in _REFERENCE_MIME_ALLOWLIST:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f'mime {mime!r} no soportado; permitidos: {sorted(_REFERENCE_MIME_ALLOWLIST)}',
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'archivo vacío')
    if len(data) > _REFERENCE_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f'archivo excede {_REFERENCE_MAX_BYTES // (1024 * 1024)}MB',
        )

    # Cada upload genera un idx incremental — usamos timestamp simple para
    # evitar colisiones sin tener que hacer un count() previo.
    from time import time
    idx = int(time() * 1000) % 1_000_000

    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    settings_obj = get_settings()
    try:
        stored = store_reference_asset(
            data=data,
            tenant_id=str(tenant_id),
            persona_id=str(persona_id),
            idx=idx,
            mime=mime,
            settings=settings_obj,
            config=storage_config,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f'failed to persist reference: {exc}',
        ) from exc

    # No persistimos el reference en `influencer.assets` — el CHECK
    # constraint del schema solo permite kinds de output del provider
    # (photo, reel, face_variation, etc.) y un upload del usuario no
    # encaja semánticamente. La referencia vive solo en storage; el
    # frontend incluye su URL en `params.reference_image_url` al hacer
    # POST /generate. Cuando el personaje se archive, una limpieza
    # periódica del prefix `references/{persona_id}/` se encarga.
    logger.info(
        'reference uploaded tenant=%s persona=%s key=%s bytes=%d',
        tenant_id, persona_id, stored.object_key, stored.size_bytes,
    )

    return ReferenceUploadResponse(
        storage_key=stored.object_key,
        url=_storage_key_to_url(stored.object_key),
        mime=mime,
        size_bytes=stored.size_bytes,
    )


# ─── Storage server (UI-INFLU-014.7) ───────────────────────────────────────


def _key_belongs_to_tenant(object_key: str, tenant_id: UUID) -> bool:
    """Valida que la key empiece con `tenants/{tenant_id}/`."""
    expected = f'tenants/{tenant_id}/'
    return object_key.startswith(expected)


def _extract_tenant_id_from_key(object_key: str) -> UUID | None:
    """Las keys del storage siempre empiezan con `tenants/{uuid}/...`.
    Devuelve el UUID parseado o None si el path es inválido.
    """
    parts = object_key.split('/', 2)
    if len(parts) < 2 or parts[0] != 'tenants':
        return None
    try:
        return UUID(parts[1])
    except ValueError:
        return None


@storage_router.get('/{object_key:path}', summary='Sirve un asset del storage del tenant')
async def serve_storage_asset(
    object_key: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Sirve un archivo del storage del tenant (local Docker volume o S3).

    UI-INFLU-014.7.1: el navegador renderiza `<img src="...">` SIN
    el header `X-Tenant-Id`, así que NO podemos depender de
    `request.state.tenant_id`. En su lugar:

    1. Extraemos `tenant_id` del path (`tenants/{tid}/...`).
    2. Validamos que el caller autenticado tiene acceso al tenant:
       - support_mode=true (platform_owner) → permitido.
       - sino, verificar fila en `app.user_tenant_roles`.
    3. Cargamos la config storage del tenant y servimos.
    """
    from fastapi.responses import FileResponse, Response

    actor_id = getattr(request.state, 'actor_id', None)
    if actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='authentication required',
        )

    path_tenant_id = _extract_tenant_id_from_key(object_key)
    if path_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='invalid object_key — must start with tenants/{uuid}/',
        )

    # Defensa anti-traversal: la key del path no puede contener `..`.
    if '..' in object_key.split('/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='object_key contains forbidden path segments',
        )

    # Validar acceso al tenant. support_mode bypasa (platform_owner en
    # modo soporte). Sino, requiere fila en user_tenant_roles.
    support_mode = bool(getattr(request.state, 'support_mode', False))
    if not support_mode:
        membership = await conn.fetchrow(
            'select 1 from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
            actor_id, path_tenant_id,
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='user has no access to this tenant',
            )

    # Set tenant scope para que `fetch_tenant_knowledge_storage_config`
    # pueda leer la fila (la tabla tiene RLS basada en `app.tenant_id`).
    await conn.execute(
        'select set_config($1, $2, true)', 'app.tenant_id', str(path_tenant_id),
    )

    storage_config = await fetch_tenant_knowledge_storage_config(conn, path_tenant_id)
    settings_obj = get_settings()
    backend = (storage_config.get('backend') or 'local').lower()

    if backend == 'local':
        path = read_local_asset(settings=settings_obj, object_key=object_key)
        if path is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'asset not found')
        # mime by extension — basta para image/png|jpeg|webp.
        import mimetypes as _mt
        mime = _mt.guess_type(str(path))[0] or 'application/octet-stream'
        return FileResponse(
            str(path),
            media_type=mime,
            headers={'Cache-Control': 'private, max-age=3600'},
        )

    if backend == 's3':
        result = s3_get_asset_bytes(
            settings=settings_obj, object_key=object_key, config=storage_config,
        )
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'asset not found')
        body, mime = result
        return Response(
            content=body,
            media_type=mime,
            headers={'Cache-Control': 'private, max-age=3600'},
        )

    raise HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f'unsupported storage backend: {backend!r}',
    )


__all__ = ['face_variations_router', 'storage_router', '_build_prompt']
