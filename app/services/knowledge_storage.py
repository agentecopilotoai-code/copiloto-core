from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.client import BaseClient

from app.core.config import Settings

SAFE_SEGMENT_RE = re.compile(r'[^a-zA-Z0-9_.=-]+')
TEXT_MIME_TYPES = {
    'text/plain',
    'text/markdown',
    'text/csv',
    'application/json',
    'application/x-ndjson',
}
TEXT_EXTENSIONS = {'.txt', '.md', '.markdown', '.csv', '.json', '.ndjson'}
BINARY_EXTRACTABLE_MIME_TYPES = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
BINARY_EXTRACTABLE_EXTENSIONS = {'.pdf', '.docx'}


@dataclass(frozen=True)
class StoredKnowledgeFile:
    storage_backend: str
    bucket: str | None
    object_key: str
    source_uri: str
    checksum: str
    size_bytes: int
    content: str | None
    extracted_text: str | None


def safe_storage_segment(value: str) -> str:
    cleaned = SAFE_SEGMENT_RE.sub('-', value.strip()).strip('.-/')
    return cleaned[:180] or 'file'


def normalize_object_prefix(prefix: str | None, tenant_id: str) -> str:
    if not prefix:
        return f'tenants/{tenant_id}/knowledge'
    parts = [safe_storage_segment(part) for part in prefix.strip('/').split('/') if part.strip('/')]
    if not parts or any(part in {'.', '..'} for part in parts):
        raise ValueError('Invalid knowledge storage prefix')
    return '/'.join(parts)


def knowledge_object_key(
    *, tenant_id: str, document_id: str, filename: str, digest: str, prefix: str | None = None
) -> str:
    safe_filename = safe_storage_segment(filename)
    object_prefix = normalize_object_prefix(prefix, tenant_id)
    return f'{object_prefix}/{document_id}/{digest[:16]}-{safe_filename}'


def is_text_upload(filename: str, mime_type: str | None) -> bool:
    if mime_type and mime_type.split(';', 1)[0].lower() in TEXT_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in TEXT_EXTENSIONS


def is_binary_extractable(filename: str, mime_type: str | None) -> bool:
    """Return True for formats that require async extraction (PDF, DOCX)."""
    if mime_type and mime_type.split(';', 1)[0].lower() in BINARY_EXTRACTABLE_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in BINARY_EXTRACTABLE_EXTENSIONS


def extract_text_if_supported(data: bytes, *, filename: str, mime_type: str | None) -> str | None:
    if not is_text_upload(filename, mime_type):
        return None
    return data.decode('utf-8-sig').strip()


def validate_knowledge_upload(
    data: bytes, *, filename: str, mime_type: str | None, settings: Settings
) -> None:
    if not filename.strip():
        raise ValueError('Uploaded file requires a filename')
    if not data:
        raise ValueError('Uploaded file is empty')
    if len(data) > settings.knowledge_file_max_bytes:
        raise ValueError(f'Uploaded file exceeds {settings.knowledge_file_max_bytes} bytes')
    if mime_type:
        normalized = mime_type.split(';', 1)[0].lower()
        if normalized not in settings.knowledge_allowed_mime_types_set:
            raise ValueError(f'MIME type {normalized} is not allowed for knowledge uploads')


def _s3_client(
    settings: Settings,
    *,
    endpoint_url: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region_name: str | None = None,
) -> BaseClient:
    # TASK-0079 / BUG18: when a tenant-controlled endpoint_url is provided, it
    # must pass the outbound URL guard (HTTPS, no loopback/RFC1918/metadata) and
    # MUST be paired with tenant-supplied credentials. We refuse to sign
    # requests against a tenant endpoint using platform-wide access keys.
    effective_endpoint = endpoint_url or settings.s3_endpoint_url or None
    tenant_endpoint_provided = bool(endpoint_url)
    if tenant_endpoint_provided:
        from app.services.url_guard import (  # noqa: PLC0415
            S3_ENDPOINT_HOST_ALLOWLIST,
            UnsafeOutboundURLError,
            validate_outbound_url,
        )

        try:
            validate_outbound_url(
                endpoint_url,
                allowed_schemes=('https',),
                host_allowlist=S3_ENDPOINT_HOST_ALLOWLIST,
                allow_http_for_local_dev=True,
            )
        except UnsafeOutboundURLError as exc:
            raise ValueError(f'Tenant S3 endpoint_url rejected: {exc}') from exc
        if not (access_key_id and secret_access_key):
            raise ValueError(
                'Tenant S3 endpoint_url requires tenant-supplied access_key_id '
                'and secret_access_key; platform credentials are never used '
                'against a tenant-controlled endpoint.'
            )

    client_kwargs = {
        'endpoint_url': effective_endpoint,
        'aws_access_key_id': access_key_id or settings.s3_access_key_id,
        'aws_secret_access_key': secret_access_key or settings.s3_secret_access_key,
    }
    if region_name:
        client_kwargs['region_name'] = region_name
    return boto3.client('s3', **client_kwargs)


def store_knowledge_file(
    *,
    data: bytes,
    tenant_id: str,
    document_id: str,
    filename: str,
    mime_type: str | None,
    settings: Settings,
    backend: str | None = None,
    bucket: str | None = None,
    endpoint_url: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region_name: str | None = None,
    prefix: str | None = None,
) -> StoredKnowledgeFile:
    validate_knowledge_upload(data, filename=filename, mime_type=mime_type, settings=settings)
    digest = hashlib.sha256(data).hexdigest()
    object_key = knowledge_object_key(
        tenant_id=tenant_id, document_id=document_id, filename=filename, digest=digest, prefix=prefix
    )
    backend = (backend or settings.knowledge_storage_backend).lower()

    if backend == 'local':
        root = Path(settings.knowledge_storage_local_path)
        destination = (root / object_key).resolve()
        root_resolved = root.resolve()
        if root_resolved not in destination.parents:
            raise ValueError('Invalid knowledge storage path')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        source_uri = f'file://{destination}'
        bucket = None
    elif backend == 's3':
        bucket = bucket or settings.knowledge_storage_bucket
        client = _s3_client(
            settings,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name=region_name,
        )
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=data,
            ContentType=mime_type or 'application/octet-stream',
            Metadata={'tenant_id': tenant_id, 'document_id': document_id, 'sha256': digest},
        )
        source_uri = f's3://{bucket}/{object_key}'
    else:
        raise ValueError(f'Unsupported knowledge storage backend: {settings.knowledge_storage_backend}')

    extracted_text = extract_text_if_supported(data, filename=filename, mime_type=mime_type)
    return StoredKnowledgeFile(
        storage_backend=backend,
        bucket=bucket,
        object_key=object_key,
        source_uri=source_uri,
        checksum=f'sha256:{digest}',
        size_bytes=len(data),
        content=extracted_text,
        extracted_text=extracted_text,
    )


def _resolve_within(base: Path, candidate: Path) -> Path | None:
    """Return candidate.resolve() if it is contained within base.resolve(), else None."""
    try:
        base_resolved = base.resolve()
        candidate_resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if candidate_resolved == base_resolved:
        return None
    if not candidate_resolved.is_relative_to(base_resolved):
        return None
    return candidate_resolved


def delete_knowledge_file(
    *,
    source_uri: str,
    storage_backend: str,
    object_key: str | None = None,
    bucket: str | None = None,
    settings: Settings,
    tenant_prefix: str | None = None,
    expected_bucket: str | None = None,
    endpoint_url: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region_name: str | None = None,
) -> None:
    """Remove a stored knowledge file from local disk or S3.

    Enforces that the target file/object resides under the trusted storage
    location (storage root and, if provided, tenant prefix / configured bucket).
    Inputs derived from caller-controlled DB fields (``source_uri``,
    ``object_key``, ``bucket``) are validated before any unlink/delete is
    attempted, so a tenant-writable value pointing outside the tenant's
    storage region is silently refused. Missing files are also ignored.
    """
    backend = (storage_backend or '').lower()

    # Normalize the tenant prefix up front. A provided-but-empty / root-like
    # / traversal-laden prefix is treated as untrusted: we refuse the delete
    # rather than fall back to "no containment", which would let a tenant
    # admin who configured prefix='/' (or '', '.', '..') reach objects
    # outside their tenant region in the shared bucket / storage root.
    normalized_tenant_prefix: str | None = None
    if tenant_prefix is not None:
        candidate_prefix = tenant_prefix.strip('/').replace('\\', '/')
        if not candidate_prefix or any(
            part in {'', '.', '..'} for part in candidate_prefix.split('/')
        ):
            return
        normalized_tenant_prefix = candidate_prefix

    if backend == 'local':
        root = Path(settings.knowledge_storage_local_path)
        allowed_base = root / normalized_tenant_prefix if normalized_tenant_prefix else root

        candidate: Path | None = None
        if object_key:
            normalized_key = object_key.replace('\\', '/').lstrip('/')
            if normalized_key and not any(
                part in {'', '.', '..'} for part in normalized_key.split('/')
            ):
                candidate = root / normalized_key
        elif source_uri and source_uri.startswith('file://'):
            candidate = Path(source_uri[7:])

        if candidate is None:
            return

        safe_path = _resolve_within(allowed_base, candidate)
        if safe_path is None:
            return

        try:
            safe_path.unlink(missing_ok=True)
            # Remove empty parent directories up to (but not including) allowed_base
            try:
                base_resolved = allowed_base.resolve()
            except (OSError, RuntimeError, ValueError):
                return
            parent = safe_path.parent
            while parent != base_resolved and parent.is_relative_to(base_resolved):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        except OSError:
            pass

    elif backend == 's3':
        if not object_key or not bucket:
            return
        if expected_bucket and bucket != expected_bucket:
            return
        normalized_key = object_key.replace('\\', '/').lstrip('/')
        if not normalized_key or any(
            part in {'', '.', '..'} for part in normalized_key.split('/')
        ):
            return
        if normalized_tenant_prefix and not normalized_key.startswith(
            normalized_tenant_prefix + '/'
        ):
            return
        try:
            client = _s3_client(
                settings,
                endpoint_url=endpoint_url,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region_name=region_name,
            )
            client.delete_object(Bucket=bucket, Key=normalized_key)
        except Exception:
            pass
