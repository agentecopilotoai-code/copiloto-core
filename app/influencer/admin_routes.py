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
from app.ai.registry import (
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

    Si ``secret_value`` viene set, se cifra con la master key
    (`AI_PROVIDER_MASTER_KEY`, Fernet) y se persiste en
    ``app.platform_secrets.ciphertext``. ``hint`` (últimos 4 chars) queda
    visible para el operador como identificador del key activo. **El
    ``secret_value`` nunca se persiste en claro en la DB** — solo el
    ciphertext encriptado at-rest.

    La key descifrada vive solo en memoria del request que la consume
    (PATCH para guardar, POST /test para probar). Sin la master key
    configurada los endpoints fallan con un mensaje claro.

    Como alternativa a ``secret_value``, ``reuse_from_modality`` permite
    apuntar el ``secret_ref`` actual al ``secret_ref`` de OTRA modalidad
    que ya tenga una key configurada. Útil cuando varias modalidades
    comparten el mismo provider (ej. la misma key de xAI alimenta llm,
    image, video, tts, stt). El ``secret_ref`` es opaco — el frontend NUNCA
    lo ve; solo elige la modalidad fuente y el backend resuelve el join.
    """
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    params: dict | None = None
    secret_value: str | None = Field(default=None, min_length=8, max_length=512)
    secret_backend: Literal['env', 'aws_sm', 'vault', 'file'] | None = None
    reuse_from_modality: Literal['llm', 'image', 'video', 'tts', 'stt'] | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────


def _hint_of(secret_value: str) -> str:
    """Últimos 4 chars del valor en claro. Insuficiente para reconstruir el
    secret pero útil para distinguir cuál key está activa (e.g. ``...A1B2``).
    """
    return secret_value[-4:]


def _generate_secret_ref(modality: str, backend: str) -> str:
    """Genera un secret_ref opaco único. Formato:
    ``ai:{backend}:{modality}:{token}`` — el ``token`` es random 12-char
    hex; no se reusa cross-modality ni cross-backend.
    """
    token = secrets_module.token_hex(6)
    return f'ai:{backend}:{modality}:{token}'


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

    BUGFIX-AI-PROVIDERS-RLS — `platform_ai_providers` y `platform_secrets`
    tienen RLS habilitada con policies que requieren
    ``app.support_mode='on'``. Sin la transacción explícita el
    ``set_config(..., true)`` se descarta antes del SELECT y RLS oculta
    todas las filas → la UI pinta 5 placeholders "sin configurar".
    """
    async with conn.transaction():
        await _set_support_mode(conn, True)
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
        and payload.reuse_from_modality is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='at least one field must be provided',
        )

    # `secret_value` (rotar nueva key) y `reuse_from_modality` (apuntar a otra
    # modalidad) son mutuamente excluyentes — pasar las dos es ambiguo y casi
    # seguro un bug en el cliente.
    if payload.secret_value is not None and payload.reuse_from_modality is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='secret_value and reuse_from_modality are mutually exclusive',
        )

    # Reusar de uno mismo no tiene sentido (sería un no-op caro con audit).
    if payload.reuse_from_modality == modality:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='reuse_from_modality cannot equal the target modality',
        )

    # BUGFIX-AI-PROVIDERS-RLS — ver comentario en `list_platform_ai_providers`.
    # Toda la cadena (insert en `platform_secrets` → UPDATE de
    # `platform_ai_providers` → SELECT del hint → audit) corre dentro de la
    # misma transacción para que `set_config('app.support_mode', 'on', true)`
    # siga vigente; sin esto, RLS rechaza el UPDATE y el handler responde 404
    # aunque la fila exista (seed de la migración).
    async with conn.transaction():
        await _set_support_mode(conn, True)

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
        reused_from: str | None = None
        if payload.secret_value is not None:
            backend = payload.secret_backend or 'env'
            secret_ref = _generate_secret_ref(modality, backend)
            # Cifrar al guardar — la key plaintext muere con el request.
            ciphertext = _encrypt_secret(payload.secret_value)
            await conn.execute(
                """
                insert into app.platform_secrets (secret_ref, backend, ciphertext, hint, created_by)
                values ($1, $2, $3, $4, $5)
                on conflict (secret_ref) do update
                  set ciphertext = excluded.ciphertext,
                      hint = excluded.hint,
                      rotated_at = now()
                """,
                secret_ref,
                backend,
                ciphertext,
                _hint_of(payload.secret_value),
                actor_id,
            )
            secret_rotated = True
        elif payload.reuse_from_modality is not None:
            # Resolver el `secret_ref` de la modalidad fuente. Se exige que la
            # fuente tenga un secret_ref configurado Y que el provider coincida
            # con el provider efectivo del target (el del payload si se está
            # cambiando, o el actual de la DB si no). Esto evita pegar una key
            # de xAI a una modalidad cuyo provider es OpenAI — el backend
            # rechazaría el call en runtime pero igual queda config inconsistente.
            src = await conn.fetchrow(
                """
                select provider, secret_ref
                from app.platform_ai_providers
                where modality = $1
                """,
                payload.reuse_from_modality,
            )
            if src is None or src['secret_ref'] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f'reuse_from_modality={payload.reuse_from_modality!r} '
                        'has no secret configured'
                    ),
                )

            target_provider = payload.provider
            if target_provider is None:
                # Provider efectivo = el actual en DB. Necesitamos leerlo aquí
                # porque más abajo el UPDATE solo lo cambia si está en el payload.
                cur = await conn.fetchrow(
                    'select provider from app.platform_ai_providers where modality = $1',
                    modality,
                )
                target_provider = cur['provider'] if cur else None

            if target_provider != src['provider']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"provider mismatch: cannot reuse {src['provider']!r} key "
                        f"for a {target_provider!r} target"
                    ),
                )

            secret_ref = src['secret_ref']
            secret_rotated = True
            reused_from = payload.reuse_from_modality
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
                # `reused_from` queda como pista de auditoría útil: distingue
                # rotación con key nueva (None) vs reuse cross-modality.
                'reused_from': reused_from,
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


# ─── Smoke test endpoint — "Probar" en el modal del operador ────────────────
#
# El operador platform_owner pulsa "Probar" en la fila de una modalidad para
# validar que la config llega al provider y devuelve algo razonable (key
# correcta, modelo válido, network alcanza). Cada modalidad tiene un payload
# de entrada y una respuesta uniforme. El resultado se renderiza inline en
# el modal de prueba (texto, imagen, video, audio o transcript).
#
# Secrets: la key plaintext se cifra al guardar y se descifra al usar.
# `app.platform_secrets.ciphertext` guarda el blob Fernet; la master key
# (`AI_PROVIDER_MASTER_KEY` en env) vive solo en el proceso de la API.
# Esto evita el footgun previo donde el operador debía pegar la key dos
# veces (UI + env var) y reiniciar el container para cada rotación.
#
# Cobertura: hoy solo `grok` está cableado vía `GrokProvider`. Otros
# providers responden 501 con un mensaje claro hasta que se integren.


import base64 as _base64_module  # noqa: E402
import binascii as _binascii_module  # noqa: E402
import time as _time_module  # noqa: E402

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402

from app.ai.providers.base import (  # noqa: E402
    PersonaAnchor,
    ProviderContentRejected,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
)
from app.core.config import get_settings  # noqa: E402


class TestProviderRequest(BaseModel):
    """Body polimórfico para el smoke test. Cada modalidad usa el subset de
    campos relevante; los demás se ignoran. El handler valida que los campos
    requeridos por la modalidad estén presentes y rechaza con 400 si no.
    """
    # LLM
    prompt: str | None = Field(default=None, max_length=2000)
    system: str | None = Field(default=None, max_length=2000)
    # Image / Video (heredan prompt). Video además:
    duration_s: float | None = Field(default=None, ge=1.0, le=15.0)
    aspect_ratio: str | None = Field(default=None, max_length=16)
    # TTS
    text: str | None = Field(default=None, max_length=2000)
    voice_tone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=8)
    # STT
    audio_b64: str | None = Field(default=None, max_length=10_000_000)  # ~7.5MB raw
    audio_mime: str | None = Field(default=None, max_length=64)


class TestProviderResponse(BaseModel):
    """Respuesta uniforme del smoke test.

    `output` es un dict modality-specific:
      - llm   → {kind: 'text',       text: str, tokens_used?: int}
      - image → {kind: 'image',      image_b64: str, mime: str}
      - video → {kind: 'video',      video_b64: str, mime: str, duration_s: float}
      - tts   → {kind: 'audio',      audio_b64: str, mime: str, duration_s: float}
      - stt   → {kind: 'transcript', text: str, language?: str, confidence?: float}

    `error` solo se incluye cuando `ok=false`. El handler nunca devuelve 5xx
    por errores del provider — los traduce a 200 con `ok=false` para que la
    UI muestre el detalle (rate-limited, content-filter, etc.) sin un toast
    de fallo opaco.
    """
    ok: bool
    modality: str
    provider: str
    model: str | None
    elapsed_ms: float
    output: dict | None = None
    error: str | None = None
    error_class: str | None = None


def _get_secret_cipher() -> Fernet:
    """Instancia Fernet con la master key del env. Centraliza el error
    cuando la key no está configurada para que tanto el PATCH (cifrar)
    como el smoke test (descifrar) compartan el mismo mensaje.
    """
    settings = get_settings()
    key = settings.ai_provider_master_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                'AI_PROVIDER_MASTER_KEY no configurada en el proceso de la API. '
                'Genera una con: '
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())" '
                'y agrégala al .env del backend.'
            ),
        )
    return Fernet(key.encode('ascii') if isinstance(key, str) else key)


def _encrypt_secret(plaintext: str) -> bytes:
    """Encripta la API key plaintext con Fernet → bytes para guardar en
    `platform_secrets.ciphertext`. La key plaintext muere con el request.
    """
    return _get_secret_cipher().encrypt(plaintext.encode('utf-8'))


def _decrypt_secret(ciphertext: bytes) -> str:
    """Descifra el ciphertext leído de DB → API key plaintext. Solo se
    invoca desde el request que está por llamar al provider.
    """
    try:
        return _get_secret_cipher().decrypt(bytes(ciphertext)).decode('utf-8')
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                'Stored secret cannot be decrypted with the current master key. '
                'This usually means AI_PROVIDER_MASTER_KEY was rotated without '
                're-encrypting existing rows.'
            ),
        ) from exc


def _build_test_provider(provider_name: str, *, api_key: str, model: str | None):
    """Instancia el adapter correcto del registry. Hoy solo `grok` está
    cableado; otros providers levantan NotImplementedError y el endpoint
    los traduce a 501 con mensaje claro.

    El `model` se pasa al adapter como override del default; si es None,
    el adapter usa su modelo por defecto (e.g. ``grok-4.3`` para LLM).
    """
    if provider_name == 'grok':
        from app.ai.providers.grok import GrokProvider  # local import: evita ciclos
        models: dict[str, str] = {}
        # GrokProvider acepta un dict completo de modelos por modalidad. Para
        # el smoke test solo sobrescribimos uno (el de la modalidad bajo
        # prueba); el wrapper de abajo lo hace por modalidad antes de llamar.
        return GrokProvider(api_key=api_key, models=models)
    raise NotImplementedError(
        f'smoke test not implemented for provider {provider_name!r} yet'
    )


def _persona_for_test() -> PersonaAnchor:
    """PersonaAnchor mínima para el smoke test. No representa un personaje
    real — solo satisface el contrato del adapter (`persona_id` requerido).
    """
    return PersonaAnchor(persona_id='__platform_smoke_test__')


@platform_admin_router.post(
    '/platform/ai-providers/{modality}/test',
    response_model=TestProviderResponse,
    summary='Smoke test del provider configurado para una modalidad',
)
async def smoke_test_platform_ai_provider(
    modality: str,
    body: TestProviderRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> TestProviderResponse:
    if modality not in MODALITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'modality must be one of {sorted(MODALITIES)}',
        )

    # Lee la fila configurada bajo support_mode (RLS). Trae `ciphertext`
    # para descifrar la key sin obligar al operador a una env var manual.
    async with conn.transaction():
        await _set_support_mode(conn, True)
        row = await conn.fetchrow(
            """
            select p.provider, p.model, p.params, s.hint, s.ciphertext
            from app.platform_ai_providers p
            left join app.platform_secrets s on s.secret_ref = p.secret_ref
            where p.modality = $1
            """,
            modality,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'modality {modality} not found',
        )

    provider_name = row['provider']
    model = row['model']
    hint = row['hint']
    ciphertext = row['ciphertext']

    if provider_name == 'unset' or hint is None or not ciphertext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f'modality {modality} is not fully configured: '
                'set provider, model, and rotate the API key first'
            ),
        )

    # Descifrado in-memory — la key plaintext vive solo dentro de este
    # request, no se logea ni se devuelve por API.
    api_key = _decrypt_secret(ciphertext)

    # Instanciar adapter — los providers no-grok aún no están cableados.
    try:
        provider = _build_test_provider(provider_name, api_key=api_key, model=model)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc

    # El adapter usa el dict `_models` por modalidad para resolver qué modelo
    # mandar al endpoint. Para el smoke test sobrescribimos solo la entrada
    # de la modalidad bajo prueba.
    if model:
        provider._models[modality] = model  # noqa: SLF001 — internal, controlado

    t0 = _time_module.monotonic()
    try:
        output = await _run_smoke_call(provider, modality, body)
    except (
        ProviderContentRejected,
        ProviderRateLimited,
        ProviderTimeoutError,
        ProviderUnavailable,
        ProviderError,
        ValueError,
    ) as exc:
        elapsed_ms = (_time_module.monotonic() - t0) * 1000.0
        return TestProviderResponse(
            ok=False,
            modality=modality,
            provider=provider_name,
            model=model,
            elapsed_ms=elapsed_ms,
            error=str(exc),
            error_class=type(exc).__name__,
        )

    elapsed_ms = (_time_module.monotonic() - t0) * 1000.0
    return TestProviderResponse(
        ok=True,
        modality=modality,
        provider=provider_name,
        model=model,
        elapsed_ms=elapsed_ms,
        output=output,
    )


async def _run_smoke_call(provider, modality: str, body: TestProviderRequest) -> dict:
    """Dispatch por modalidad. Cada rama valida sus campos requeridos del
    body y devuelve un dict serializable (base64 para binarios)."""
    if modality == 'llm':
        if not body.prompt:
            raise ValueError("'prompt' is required for llm smoke test")
        res = await provider.generate_text(
            prompt=body.prompt,
            system=body.system,
            max_tokens=256,
            temperature=0.7,
        )
        return {
            'kind': 'text',
            'text': res.text,
            'tokens_used': res.provider_meta.get('tokens_used'),
            'finish_reason': res.finish_reason,
        }

    if modality == 'image':
        if not body.prompt:
            raise ValueError("'prompt' is required for image smoke test")
        results = await provider.generate_image(
            prompt=body.prompt,
            persona_anchor=_persona_for_test(),
            count=1,
            format=body.aspect_ratio or '1:1',
            safety_mode=True,
        )
        first = results[0]
        return {
            'kind': 'image',
            'image_b64': _base64_module.b64encode(first.image_bytes).decode('ascii'),
            'mime': first.mime,
            'width': first.width,
            'height': first.height,
        }

    if modality == 'video':
        if not body.prompt:
            raise ValueError("'prompt' is required for video smoke test")
        res = await provider.generate_video(
            prompt=body.prompt,
            persona_anchor=_persona_for_test(),
            duration_s=body.duration_s or 5.0,
            format=body.aspect_ratio or '16:9',
            safety_mode=True,
        )
        # Para video preferimos URL sobre bytes (xAI Imagine devuelve URL
        # temporal; los videos pesan megabytes y no queremos inline-b64 en
        # el JSON). El frontend usa `<video src>` directo. Si el provider
        # downloadeó bytes (cualquier caller que lo necesite), también
        # los exponemos como fallback.
        out: dict = {
            'kind': 'video',
            'mime': res.mime,
            'duration_s': res.duration_s,
            'width': res.width,
            'height': res.height,
        }
        video_url = res.provider_meta.get('video_url') if res.provider_meta else None
        if video_url:
            out['video_url'] = video_url
        if res.video_bytes:
            out['video_b64'] = _base64_module.b64encode(res.video_bytes).decode('ascii')
        return out

    if modality == 'tts':
        if not body.text:
            raise ValueError("'text' is required for tts smoke test")
        # Para el smoke test no hay voice clone — usamos PersonaAnchor mínima.
        # El backend del provider acepta `voice_tone` como fallback.
        persona = PersonaAnchor(
            persona_id='__platform_smoke_test__',
            voice_tone=body.voice_tone,
        )
        res = await provider.synthesize_speech(
            text=body.text,
            persona_anchor=persona,
            language=body.language or 'es',
        )
        return {
            'kind': 'audio',
            'audio_b64': _base64_module.b64encode(res.audio_bytes).decode('ascii'),
            'mime': res.mime,
            'duration_s': res.duration_s,
            'sample_rate': res.sample_rate,
        }

    if modality == 'stt':
        if not body.audio_b64:
            raise ValueError("'audio_b64' is required for stt smoke test")
        try:
            audio_bytes = _base64_module.b64decode(body.audio_b64, validate=False)
        except (ValueError, _binascii_module.Error) as exc:
            raise ValueError(f'invalid base64 audio: {exc}') from exc
        res = await provider.transcribe(
            audio_bytes=audio_bytes,
            mime=body.audio_mime or 'audio/mpeg',
            language=body.language,
        )
        return {
            'kind': 'transcript',
            'text': res.text,
            'language': res.language,
            'confidence': res.confidence,
        }

    raise ValueError(f'unsupported modality {modality!r}')


# ─── TASK-INFLU-019 — tenant_modules platform_admin endpoints ──────────────


from app.influencer import _cache_invalidate as _module_gate_cache_invalidate  # noqa: E402


_REQUIRED_MODALITIES_FOR_INFLUENCER = ('llm', 'image')


class TenantModuleRow(BaseModel):
    tenant_id: str
    tenant_slug: str | None
    tenant_name: str | None
    module: str
    enabled: bool
    plan: str | None = None
    activated_at: str | None = None
    activated_by: str | None = None
    notes: str | None = None


class TenantModuleListResponse(BaseModel):
    items: list[TenantModuleRow]


class TenantModuleUpdate(BaseModel):
    enabled: bool
    plan: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)


async def _set_support_mode(conn: asyncpg.Connection, on: bool) -> None:
    # `is_local=true` ata el setting al *current transaction*. asyncpg corre
    # cada `conn.execute`/`fetch` en autocommit (transacción implícita de un
    # sólo statement), entonces sin un `BEGIN` explícito el `set_config(...,
    # true)` se descarta al cerrar la transacción implícita y la siguiente
    # query corre sin `app.support_mode='on'` → RLS rechaza el INSERT con
    # `InsufficientPrivilegeError`. El caller DEBE envolver el bloque en
    # `async with conn.transaction()` para que el config sobreviva.
    await conn.execute(
        'select set_config($1, $2, true)',
        'app.support_mode', 'on' if on else 'off',
    )


@platform_admin_router.get(
    '/platform/tenant-modules',
    response_model=TenantModuleListResponse,
    summary='Lista cross-tenant de `app.tenant_modules` (platform_owner only)',
)
async def list_tenant_modules(
    request: Request,
    module: str | None = None,
    enabled: bool | None = None,
    tenant_search: str | None = None,
    conn: asyncpg.Connection = Depends(get_db),
) -> TenantModuleListResponse:
    # Transacción explícita para que `set_config('app.support_mode', 'on',
    # true)` siga vigente cuando corra el `fetch` siguiente (ver comentario
    # en `_set_support_mode`).
    async with conn.transaction():
        await _set_support_mode(conn, True)

        where: list[str] = ['tm.tenant_id is not null']
        params: list = []
        if module:
            params.append(module)
            where.append(f'tm.module = ${len(params)}')
        if enabled is not None:
            params.append(enabled)
            where.append(f'tm.enabled = ${len(params)}')
        if tenant_search:
            params.append(f'%{tenant_search.lower()}%')
            # BUGFIX — el query usaba `t.name` que no existe en `app.tenants`.
            # Las columnas reales son `legal_name` y `display_name`. Buscamos
            # contra `display_name` (lo que ve el operador en la UI) además del
            # slug.
            where.append(
                f'(lower(t.slug) like ${len(params)} or lower(t.display_name) like ${len(params)})',
            )

        rows = await conn.fetch(
            f'''
            select t.id as tenant_id, t.slug as tenant_slug, t.display_name as tenant_name,
                   tm.module, tm.enabled, tm.plan, tm.activated_at, tm.activated_by,
                   tm.notes
            from app.tenants t
            left join app.tenant_modules tm on tm.tenant_id = t.id
            where {' and '.join(where)}
            order by t.slug, tm.module
            ''',
            *params,
        )
    items = [
        TenantModuleRow(
            tenant_id=str(r['tenant_id']),
            tenant_slug=r['tenant_slug'],
            tenant_name=r['tenant_name'],
            module=r['module'] or '',
            enabled=bool(r['enabled']),
            plan=r['plan'],
            activated_at=r['activated_at'].isoformat() if r['activated_at'] else None,
            activated_by=str(r['activated_by']) if r['activated_by'] else None,
            notes=r['notes'],
        )
        for r in rows
    ]
    return TenantModuleListResponse(items=items)


@platform_admin_router.patch(
    '/platform/tenant-modules/{tenant_id}/{module}',
    response_model=TenantModuleRow,
    summary='Activa/desactiva un módulo opt-in para un tenant',
)
async def update_tenant_module(
    tenant_id: str,
    module: str,
    body: TenantModuleUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> TenantModuleRow:
    actor_id = getattr(request.state, 'user_id', None)

    # Toda la operación en una transacción única: `set_config('app.support_mode',
    # 'on', true)` es transaction-local; sin este `BEGIN` explícito, el setting
    # se descarta antes del INSERT/UPDATE y RLS rechaza la escritura con
    # `InsufficientPrivilegeError: new row violates row-level security policy for
    # table "tenant_modules"`. Audit + invalidate cache también caen dentro: si
    # algo falla, no queremos una fila escrita sin audit trail.
    async with conn.transaction():
        await _set_support_mode(conn, True)

        # Verifica que el tenant existe.
        # BUGFIX — la columna `name` no existe; usar `display_name`.
        tenant = await conn.fetchrow(
            'select id, slug, display_name from app.tenants where id = $1', tenant_id,
        )
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'tenant not found')

        # Pre-flight check para el módulo influencer: providers configurados.
        if module == 'influencer' and body.enabled is True:
            configured = await conn.fetch(
                '''
                select modality from app.platform_ai_providers
                where modality = any($1) and secret_ref is not null
                ''',
                list(_REQUIRED_MODALITIES_FOR_INFLUENCER),
            )
            configured_modalities = {r['modality'] for r in configured}
            missing = set(_REQUIRED_MODALITIES_FOR_INFLUENCER) - configured_modalities
            if missing:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f'ai_providers_not_configured: missing {sorted(missing)}',
                )

        # Lee la fila existente para decidir si activated_at debe cambiar.
        existing = await conn.fetchrow(
            '''
            select enabled from app.tenant_modules
            where tenant_id = $1 and module = $2
            ''',
            tenant_id, module,
        )

        # Si no existía o cambia el toggle, activated_at = now()
        activated_changed = existing is None or bool(existing['enabled']) != body.enabled

        if activated_changed:
            sql = '''
                insert into app.tenant_modules
                  (tenant_id, module, enabled, plan, activated_at, activated_by, notes)
                values ($1, $2, $3, $4, now(), $5, $6)
                on conflict (tenant_id, module) do update set
                  enabled = excluded.enabled,
                  plan = excluded.plan,
                  activated_at = now(),
                  activated_by = excluded.activated_by,
                  notes = excluded.notes
                returning *
            '''
            params = (tenant_id, module, body.enabled, body.plan, actor_id, body.notes)
        else:
            sql = '''
                update app.tenant_modules
                set plan = $1, notes = $2
                where tenant_id = $3 and module = $4
                returning *
            '''
            params = (body.plan, body.notes, tenant_id, module)

        try:
            row = await conn.fetchrow(sql, *params)
        except asyncpg.CheckViolationError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'module {module!r} not in CHECK constraint: {exc}',
            ) from exc

        if activated_changed:
            # Audit (sin `notes` — puede contener PII).
            action = (
                'platform.tenant_module.activated' if body.enabled
                else 'platform.tenant_module.deactivated'
            )
            await audit(
                conn,
                tenant_id=None,
                actor_type='platform_owner',
                actor_id=str(actor_id) if actor_id else None,
                action=action,
                entity_type='tenant_module',
                entity_id=f'{tenant_id}:{module}',
                metadata={
                    'tenant_id': str(tenant_id),
                    'module': module,
                    'enabled': body.enabled,
                    'plan': body.plan,
                    'notes_provided': bool(body.notes),
                },
            )
            # Invalidate gate cache (mismo worker; otros workers vencen por TTL 5min).
            _module_gate_cache_invalidate()

    return TenantModuleRow(
        tenant_id=str(row['tenant_id']),
        tenant_slug=tenant['slug'],
        tenant_name=tenant['display_name'],
        module=row['module'],
        enabled=bool(row['enabled']),
        plan=row['plan'],
        activated_at=row['activated_at'].isoformat() if row['activated_at'] else None,
        activated_by=str(row['activated_by']) if row['activated_by'] else None,
        notes=row['notes'],
    )


# Re-export silencer (`secrets_module` import-only).
_ = secrets_module


__all__ = [
    'PlatformAIProviderListResponse',
    'PlatformAIProviderRow',
    'PlatformAIProviderUpdate',
    'TenantModuleListResponse',
    'TenantModuleRow',
    'TenantModuleUpdate',
    'list_platform_ai_providers',
    'list_tenant_modules',
    'update_platform_ai_provider',
    'update_tenant_module',
]
