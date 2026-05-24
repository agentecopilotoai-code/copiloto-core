"""UI-INFLU-014.7 — Storage de assets del módulo influencer.

Reusa la misma config por-tenant que el módulo knowledge
(`app.tenant_settings.knowledge_storage`): el usuario configura un
solo backend (local Docker volume o S3) y ambos módulos lo respetan.

Convención de path (local + S3):

    tenants/{tenant_id}/influencer/face-variations/{request_id}/{idx}.{ext}

Razones para no reusar ``store_knowledge_file`` directamente:

1. Knowledge corre ``extract_text_if_supported`` (OCR/text) que no
   aplica a PNG generados por IA.
2. ``knowledge_object_key`` usa el patrón ``{doc_id}/{digest}-file``
   que no aplica a variaciones por request.
3. ``validate_knowledge_upload`` valida MIME contra una allowlist
   pensada para documentos; las imágenes del influencer ya están
   confirmadas de tipo ``image/png|jpeg`` por el provider.

Lo que sí reusamos: ``_s3_client`` (con sus guardas de seguridad de
endpoint), ``Settings.knowledge_storage_local_path`` (mismo Docker
volume), y el normalizador ``normalize_object_prefix`` (sanitiza
prefix custom del tenant).
"""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.services.knowledge_storage import (
    _s3_client,
    normalize_object_prefix,
)


@dataclass(frozen=True)
class StoredInfluencerAsset:
    storage_backend: str  # 'local' | 's3'
    bucket: str | None
    object_key: str
    source_uri: str  # file:///... | s3://bucket/key
    size_bytes: int
    mime: str


def _ext_for_mime(mime: str) -> str:
    """Devuelve la extensión `.png` / `.jpg` / `.webp` desde el mime."""
    if not mime:
        return '.bin'
    guess = mimetypes.guess_extension(mime.split(';', 1)[0].lower())
    return guess or '.bin'


def _build_object_key(
    *, tenant_id: str, kind: str, request_id: str, idx: int, mime: str,
    prefix: str | None,
) -> str:
    """Construye la key del asset.

    `kind` ∈ ('face-variations', 'body-views', 'generations'). Por
    ahora face-variations; futuras integraciones reutilizan el módulo
    con su propio `kind`.
    """
    # Reusa el normalizador del knowledge: tenants/{tid}/<prefix opcional>.
    base_prefix = normalize_object_prefix(prefix, tenant_id)
    # base_prefix ya viene como `tenants/{tid}/knowledge` (default) o el
    # custom del tenant. Lo reemplazamos por `tenants/{tid}/influencer`
    # para mantener separación de namespaces dentro del mismo bucket /
    # mismo volume.
    if base_prefix == f'tenants/{tenant_id}/knowledge':
        base_prefix = f'tenants/{tenant_id}/influencer'
    else:
        # Custom prefix del tenant: respétalo y agrega /influencer dentro.
        base_prefix = f'{base_prefix}/influencer'
    return f'{base_prefix}/{kind}/{request_id}/{idx}{_ext_for_mime(mime)}'


def _store_asset_with_kind(
    *,
    data: bytes,
    tenant_id: str,
    asset_kind: str,  # 'face-variations' | 'references' | 'generations'
    request_id: str,
    idx: int,
    mime: str,
    settings: Settings,
    config: dict,
    metadata_kind: str,  # logical kind for S3 metadata
) -> StoredInfluencerAsset:
    """Persiste un asset genérico según `asset_kind` (path prefix).

    Reusa el mismo storage backend (local/S3) y la misma convención de
    path; solo cambia el segmento `kind/` en el object_key. Esto permite
    que `face-variations`, `references` (uploads del usuario) y
    `generations` (output del composer del studio) compartan toda la
    infra de upload sin código duplicado.
    """
    backend = (config.get('backend') or 'local').lower()
    prefix = config.get('prefix')
    bucket = config.get('bucket')
    region = config.get('region')
    endpoint_url = config.get('endpoint_url')
    access_key_id = config.get('access_key_id')
    secret_access_key = config.get('secret_access_key')  # transient

    object_key = _build_object_key(
        tenant_id=tenant_id,
        kind=asset_kind,
        request_id=request_id,
        idx=idx,
        mime=mime,
        prefix=prefix,
    )

    if backend == 'local':
        # Reusa el path del knowledge para no proliferar volumes.
        root = Path(settings.knowledge_storage_local_path)
        destination = (root / object_key).resolve()
        root_resolved = root.resolve()
        if root_resolved not in destination.parents:
            raise ValueError('Invalid influencer storage path')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        source_uri = f'file://{destination}'
        return StoredInfluencerAsset(
            storage_backend='local',
            bucket=None,
            object_key=object_key,
            source_uri=source_uri,
            size_bytes=len(data),
            mime=mime,
        )

    if backend == 's3':
        if not bucket:
            raise ValueError('S3 backend requires tenant config.bucket')
        client = _s3_client(
            settings,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name=region,
        )
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=data,
            ContentType=mime or 'application/octet-stream',
            Metadata={
                'tenant_id': tenant_id,
                'request_id': request_id,
                'kind': metadata_kind,
            },
        )
        return StoredInfluencerAsset(
            storage_backend='s3',
            bucket=bucket,
            object_key=object_key,
            source_uri=f's3://{bucket}/{object_key}',
            size_bytes=len(data),
            mime=mime,
        )

    raise ValueError(f'Unsupported influencer storage backend: {backend!r}')


def store_face_variation_asset(
    *,
    data: bytes,
    tenant_id: str,
    request_id: str,
    idx: int,
    mime: str,
    settings: Settings,
    config: dict,
) -> StoredInfluencerAsset:
    """Backwards-compat wrapper sobre `_store_asset_with_kind` para los
    callers que ya existían (face-variations del wizard).
    """
    return _store_asset_with_kind(
        data=data,
        tenant_id=tenant_id,
        asset_kind='face-variations',
        request_id=request_id,
        idx=idx,
        mime=mime,
        settings=settings,
        config=config,
        metadata_kind='face_variation',
    )


def store_reference_asset(
    *,
    data: bytes,
    tenant_id: str,
    persona_id: str,
    idx: int,
    mime: str,
    settings: Settings,
    config: dict,
) -> StoredInfluencerAsset:
    """Persiste una foto de referencia subida por el usuario desde el
    composer del studio (UI-INFLU-014.13). El path queda bajo
    ``tenants/{tid}/influencer/references/{persona_id}/{idx}.{ext}``
    para mantener separación de namespaces.
    """
    return _store_asset_with_kind(
        data=data,
        tenant_id=tenant_id,
        asset_kind='references',
        request_id=persona_id,
        idx=idx,
        mime=mime,
        settings=settings,
        config=config,
        metadata_kind='reference',
    )


def read_local_asset(*, settings: Settings, object_key: str) -> Path | None:
    """Resuelve la ruta absoluta de un asset local. None si no existe
    o si está fuera del root (defensa anti-traversal).

    El endpoint que sirve el archivo (`GET /influencer/storage/...`)
    usa esto y luego decide hacer FileResponse o 404.
    """
    root = Path(settings.knowledge_storage_local_path)
    candidate = (root / object_key).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def s3_get_asset_bytes(
    *,
    settings: Settings,
    object_key: str,
    config: dict,
) -> tuple[bytes, str] | None:
    """Descarga bytes del asset desde S3. Devuelve (bytes, mime) o None
    si no existe. Reusa el _s3_client con la config del tenant.
    """
    bucket = config.get('bucket')
    if not bucket:
        return None
    client = _s3_client(
        settings,
        endpoint_url=config.get('endpoint_url'),
        access_key_id=config.get('access_key_id'),
        secret_access_key=config.get('secret_access_key'),
        region_name=config.get('region'),
    )
    try:
        resp = client.get_object(Bucket=bucket, Key=object_key)
    except Exception:  # noqa: BLE001 — boto3 client errors are heterogeneous
        return None
    body = resp['Body'].read()
    mime = resp.get('ContentType') or 'application/octet-stream'
    return body, mime


__all__ = [
    'StoredInfluencerAsset',
    'read_local_asset',
    's3_get_asset_bytes',
    'store_face_variation_asset',
    'store_reference_asset',
]
