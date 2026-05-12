"""Storage helpers for the media library (TASK-0046).

Reuses the same backend toggle used by Knowledge (`local` / `s3`) but keeps
its own validation: MIME-type allowlists and per-kind size caps that match
Meta's WhatsApp Cloud API limits (5MB image, 16MB video, 16MB audio,
100MB pdf). The on-disk / object-key prefix is ``media/<tenant_id>/`` so
media files live next to knowledge files without colliding.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import re

from app.core.config import Settings


_SAFE_SEGMENT_RE = re.compile(r'[^a-zA-Z0-9_.=-]+')


def _safe_storage_segment(value: str) -> str:
    cleaned = _SAFE_SEGMENT_RE.sub('-', value.strip()).strip('.-/')
    return cleaned[:180] or 'file'


MEDIA_KINDS = ('image', 'video', 'pdf', 'audio')

# Mime allowlists per kind. Values must match what Meta/WhatsApp Cloud API
# accepts as `image|video|audio|document` payloads.
MEDIA_MIME_ALLOWLIST: dict[str, frozenset[str]] = {
    'image': frozenset({'image/jpeg', 'image/png', 'image/webp'}),
    'video': frozenset({'video/mp4', 'video/3gpp'}),
    'audio': frozenset({'audio/aac', 'audio/mp4', 'audio/mpeg', 'audio/amr', 'audio/ogg'}),
    'pdf': frozenset({'application/pdf'}),
}

# Hard size caps per kind, mirroring Meta's documented limits.
MEDIA_SIZE_LIMITS_BYTES: dict[str, int] = {
    'image': 5 * 1024 * 1024,
    'video': 16 * 1024 * 1024,
    'audio': 16 * 1024 * 1024,
    'pdf': 100 * 1024 * 1024,
}


@dataclass(frozen=True)
class StoredMediaFile:
    storage_backend: str
    bucket: str | None
    object_key: str
    source_uri: str
    sha256: str
    size_bytes: int
    mime_type: str


def media_object_key(*, tenant_id: str, asset_id: str, filename: str, digest: str) -> str:
    safe = _safe_storage_segment(filename)
    return f'media/{tenant_id}/{asset_id}/{digest[:16]}-{safe}'


def validate_media_upload(
    data: bytes, *, kind: str, filename: str, mime_type: str | None
) -> str:
    """Return the normalized mime_type if valid. Raises ``ValueError``
    otherwise so the route layer can surface a 4xx."""
    if kind not in MEDIA_KINDS:
        raise ValueError(f'Unsupported media kind: {kind}')
    if not filename or not filename.strip():
        raise ValueError('Media upload requires a filename')
    if not data:
        raise ValueError('Media upload is empty')
    size_limit = MEDIA_SIZE_LIMITS_BYTES[kind]
    if len(data) > size_limit:
        raise ValueError(
            f'Media {kind} exceeds the {size_limit // (1024 * 1024)} MB cap'
        )
    normalized = (mime_type or '').split(';', 1)[0].strip().lower()
    allowlist = MEDIA_MIME_ALLOWLIST[kind]
    if normalized not in allowlist:
        raise ValueError(
            f'MIME type {normalized or "(missing)"} is not allowed for {kind}'
        )
    return normalized


def store_media_file(
    *,
    data: bytes,
    tenant_id: str,
    asset_id: str,
    kind: str,
    filename: str,
    mime_type: str | None,
    settings: Settings,
) -> StoredMediaFile:
    normalized_mime = validate_media_upload(
        data, kind=kind, filename=filename, mime_type=mime_type
    )
    digest = hashlib.sha256(data).hexdigest()
    object_key = media_object_key(
        tenant_id=tenant_id, asset_id=asset_id, filename=filename, digest=digest
    )
    backend = (settings.knowledge_storage_backend or 'local').lower()

    if backend == 'local':
        root = Path(settings.knowledge_storage_local_path)
        destination = (root / object_key).resolve()
        root_resolved = root.resolve()
        if root_resolved not in destination.parents:
            raise ValueError('Invalid media storage path')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return StoredMediaFile(
            storage_backend=backend,
            bucket=None,
            object_key=object_key,
            source_uri=f'file://{destination}',
            sha256=digest,
            size_bytes=len(data),
            mime_type=normalized_mime,
        )
    if backend == 's3':
        from app.services.knowledge_storage import _s3_client  # lazy

        bucket = settings.knowledge_storage_bucket
        client = _s3_client(settings)
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=data,
            ContentType=normalized_mime,
            Metadata={'tenant_id': tenant_id, 'asset_id': asset_id, 'sha256': digest},
        )
        return StoredMediaFile(
            storage_backend=backend,
            bucket=bucket,
            object_key=object_key,
            source_uri=f's3://{bucket}/{object_key}',
            sha256=digest,
            size_bytes=len(data),
            mime_type=normalized_mime,
        )
    raise ValueError(f'Unsupported storage backend: {backend}')


def delete_media_file(
    *,
    storage_backend: str,
    object_key: str,
    source_uri: str | None,
    bucket: str | None,
    settings: Settings,
) -> None:
    backend = (storage_backend or '').lower()
    if backend == 'local':
        if source_uri and source_uri.startswith('file://'):
            try:
                Path(source_uri[7:]).unlink(missing_ok=True)
            except OSError:
                return
        return
    if backend == 's3' and bucket and object_key:
        try:
            from app.services.knowledge_storage import _s3_client  # lazy

            client = _s3_client(settings)
            client.delete_object(Bucket=bucket, Key=object_key)
        except Exception:
            return
