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


def knowledge_object_key(*, tenant_id: str, document_id: str, filename: str, digest: str) -> str:
    safe_filename = safe_storage_segment(filename)
    return f'tenants/{tenant_id}/knowledge/{document_id}/{digest[:16]}-{safe_filename}'


def is_text_upload(filename: str, mime_type: str | None) -> bool:
    if mime_type and mime_type.split(';', 1)[0].lower() in TEXT_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in TEXT_EXTENSIONS


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


def _s3_client(settings: Settings) -> BaseClient:
    return boto3.client(
        's3',
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def store_knowledge_file(
    *,
    data: bytes,
    tenant_id: str,
    document_id: str,
    filename: str,
    mime_type: str | None,
    settings: Settings,
) -> StoredKnowledgeFile:
    validate_knowledge_upload(data, filename=filename, mime_type=mime_type, settings=settings)
    digest = hashlib.sha256(data).hexdigest()
    object_key = knowledge_object_key(
        tenant_id=tenant_id, document_id=document_id, filename=filename, digest=digest
    )
    backend = settings.knowledge_storage_backend.lower()

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
        bucket = settings.knowledge_storage_bucket
        client = _s3_client(settings)
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
