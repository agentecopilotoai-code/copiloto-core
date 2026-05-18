"""Async worker that extracts text from binary knowledge documents (PDF, DOCX).

Polls for draft documents with binary MIME types that lack metadata.extracted_text,
extracts text with a configurable timeout, and updates metadata accordingly.
Documents that succeed remain draft (ready for manual indexing); those that
exhaust retries are set to failed with an actionable extraction_error.
"""
from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import boto3
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.knowledge_storage import BINARY_EXTRACTABLE_MIME_TYPES

log = structlog.get_logger()

POLL_INTERVAL_SECONDS = 15
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
PDF_MIME = 'application/pdf'


# ---------------------------------------------------------------------------
# Low-level extraction helpers (synchronous, run in executor)
# ---------------------------------------------------------------------------

def _extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Return (text, page_count). Raises ValueError on unreadable PDF."""
    try:
        from pypdf import PdfReader  # type: ignore[import]
    except ImportError as exc:
        raise ValueError('pypdf is not installed; cannot extract PDF text') from exc

    reader = PdfReader(io.BytesIO(data))
    page_count = len(reader.pages)
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ''
        parts.append(page_text)
    text = '\n'.join(parts).strip()
    if not text:
        raise ValueError('PDF contains no extractable text (possibly scanned image)')
    return text, page_count


def _extract_docx_text(data: bytes) -> tuple[str, int]:
    """Return (text, paragraph_count). Raises ValueError on unreadable DOCX."""
    try:
        from docx import Document  # type: ignore[import]
    except ImportError as exc:
        raise ValueError('python-docx is not installed; cannot extract DOCX text') from exc

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = '\n'.join(paragraphs).strip()
    if not text:
        raise ValueError('DOCX contains no extractable text')
    return text, len(paragraphs)


def _read_local_file(storage_key: str, settings: Any) -> bytes:
    root = Path(settings.knowledge_storage_local_path)
    file_path = (root / storage_key).resolve()
    if root.resolve() not in file_path.parents:
        raise ValueError('Storage key escapes local root')
    if not file_path.exists():
        raise FileNotFoundError(f'Local file not found: {storage_key}')
    return file_path.read_bytes()


def _read_s3_file(bucket: str, storage_key: str, settings: Any) -> bytes:
    client = boto3.client(
        's3',
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )
    response = client.get_object(Bucket=bucket, Key=storage_key)
    return response['Body'].read()


def _extract_text_sync(data: bytes, mime_type: str) -> tuple[str, int]:
    """Dispatch to the right extractor based on mime_type."""
    normalized = (mime_type or '').split(';', 1)[0].lower().strip()
    if normalized == PDF_MIME or normalized == 'application/pdf':
        return _extract_pdf_text(data)
    if normalized == DOCX_MIME:
        return _extract_docx_text(data)
    raise ValueError(f'No extractor available for MIME type: {normalized}')


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _fetch_eligible_documents(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Select draft binary documents that still need extraction and haven't exceeded retry limit."""
    settings = get_settings()
    mime_types = list(BINARY_EXTRACTABLE_MIME_TYPES)
    return await conn.fetch(
        """
        select id, tenant_id, mime_type, metadata
        from app.knowledge_documents
        where status = 'draft'
          and mime_type = any($1::text[])
          and (metadata->>'extracted_text') is null
          and (metadata->>'extraction_pending')::boolean is not false
          and coalesce((metadata->>'extraction_attempt_count')::int, 0) < $2
        order by created_at
        limit 10
        for update skip locked
        """,
        mime_types,
        settings.extraction_max_attempts,
    )


async def _load_file_bytes(
    metadata: dict[str, Any],
    settings: Any,
    *,
    tenant_id: Any,
    tenant_storage_config: dict[str, Any] | None = None,
) -> bytes:
    """Read the raw file from storage based on TRUSTED tenant config.

    BUG-213 (codex HIGH): el worker antes consumía `metadata.storage_backend`,
    `metadata.storage_bucket` y `metadata.storage_key` directamente. Los
    campos `metadata.*` son tenant-writable via los endpoints de
    knowledge_documents PATCH — un tenant admin malicioso podía crear o
    actualizar un documento con `storage_key` apuntando al bucket/prefix
    de otro tenant, y el extraction worker (que corre con `app.support_mode`
    bypaseando RLS) leía el archivo cross-tenant y persistía su
    `extracted_text` en `metadata.extracted_text` del documento del
    atacante.

    Codex P1 follow-up: la versión original derivaba `backend`/`bucket` SOLO
    del settings global. Pero los tenants con storage custom (S3 mientras
    global es local, o un bucket distinto) suben con la config tenant via
    `fetch_tenant_knowledge_storage_config(...)` — para ESOS tenants el
    worker leía del backend equivocado. Fix: el caller pasa
    `tenant_storage_config` (el mismo dict que usa el upload), trusted
    porque viene de `tenant_settings.knowledge_storage` (DB, no metadata
    tenant-writable). Si es None, fallback al settings global.

    Codex P2 follow-up: el prefix esperado también viene del tenant config
    (`config['prefix']` validado por `normalize_object_prefix` al PATCH).
    Hardcodear `tenants/<tenant_id>/` rechazaba tenants con prefix custom
    como `knowledge/<tenant_id>`. Fix: validar contra `trusted_prefix`.
    """
    storage_key = metadata.get('storage_key') or ''
    if not storage_key:
        raise ValueError('Document metadata has no storage_key; cannot read file')

    # Server-side: usar tenant config trusted si está disponible; fallback global.
    if isinstance(tenant_storage_config, dict):
        backend = (tenant_storage_config.get('backend') or 'local').lower()
        bucket = tenant_storage_config.get('bucket') or settings.knowledge_storage_bucket
        trusted_prefix = tenant_storage_config.get('prefix') or f'tenants/{tenant_id}/knowledge'
    else:
        backend = (settings.knowledge_storage_backend or 'local').lower()
        bucket = settings.knowledge_storage_bucket
        trusted_prefix = f'tenants/{tenant_id}/knowledge'

    # BUG-213 + P2 follow-up: storage_key debe estar bajo el prefix confiable
    # del tenant (`<prefix>/` con trailing slash para evitar matches parciales).
    expected_prefix = trusted_prefix.rstrip('/') + '/'
    if not storage_key.startswith(expected_prefix):
        raise ValueError(
            f'extraction_worker.storage_key_not_tenant_scoped: '
            f'expected prefix {expected_prefix!r}, got key {storage_key!r}'
        )

    loop = asyncio.get_event_loop()
    if backend == 'local':
        return await asyncio.wait_for(
            loop.run_in_executor(None, _read_local_file, storage_key, settings),
            timeout=10,
        )
    elif backend == 's3':
        if not bucket:
            raise ValueError('extraction_worker.no_bucket_configured')
        return await asyncio.wait_for(
            loop.run_in_executor(None, _read_s3_file, bucket, storage_key, settings),
            timeout=30,
        )
    else:
        raise ValueError(f'Unsupported storage backend for extraction: {backend}')


async def _process_document(conn: asyncpg.Connection, row: asyncpg.Record) -> None:
    doc_id = row['id']
    tenant_id = row['tenant_id']
    mime_type = row['mime_type'] or ''

    raw_metadata = row['metadata']
    if isinstance(raw_metadata, str):
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = dict(raw_metadata) if raw_metadata else {}

    attempt = int(metadata.get('extraction_attempt_count') or 0) + 1
    settings = get_settings()
    started_at = datetime.now(UTC).isoformat()

    log.info('extraction_started', document_id=str(doc_id), tenant_id=str(tenant_id), attempt=attempt)

    # Codex P1 follow-up: cargar la config tenant (DB-trusted) para que el
    # worker use el mismo backend/bucket/prefix que el upload path. Import
    # lazy para evitar ciclo (routes.py importa este módulo indirectamente).
    from app.api.v1.routes import fetch_tenant_knowledge_storage_config  # noqa: PLC0415

    try:
        tenant_storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    except Exception:  # noqa: BLE001
        log.exception(
            'extraction_worker.tenant_config_fetch_failed',
            tenant_id=str(tenant_id),
            document_id=str(doc_id),
        )
        tenant_storage_config = None

    try:
        file_bytes = await _load_file_bytes(
            metadata,
            settings,
            tenant_id=tenant_id,
            tenant_storage_config=tenant_storage_config,
        )
        loop = asyncio.get_event_loop()
        text, pages = await asyncio.wait_for(
            loop.run_in_executor(None, _extract_text_sync, file_bytes, mime_type),
            timeout=settings.extraction_timeout_seconds,
        )

        completed_at = datetime.now(UTC).isoformat()
        patch = {
            'extracted_text': text,
            'pages_processed': pages,
            'extraction_attempt_count': attempt,
            'extraction_started_at': started_at,
            'extraction_completed_at': completed_at,
            'extraction_error': None,
            'extraction_pending': False,
        }
        await conn.execute(
            """
            update app.knowledge_documents
            set metadata = metadata || $3::jsonb
            where tenant_id = $1 and id = $2
            """,
            tenant_id,
            doc_id,
            json.dumps(patch),
        )
        log.info(
            'extraction_completed',
            document_id=str(doc_id),
            pages=pages,
            text_length=len(text),
        )
        await _audit(conn, tenant_id, doc_id, 'knowledge_document.extraction_completed', {
            'pages_processed': pages,
            'text_length': len(text),
            'attempt': attempt,
        })

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        completed_at = datetime.now(UTC).isoformat()
        is_final = attempt >= settings.extraction_max_attempts
        next_status = 'failed' if is_final else 'draft'
        patch = {
            'extraction_attempt_count': attempt,
            'extraction_started_at': started_at,
            'extraction_error': error_msg,
            'extraction_pending': not is_final,
        }
        await conn.execute(
            """
            update app.knowledge_documents
            set status = $3, metadata = metadata || $4::jsonb
            where tenant_id = $1 and id = $2
            """,
            tenant_id,
            doc_id,
            next_status,
            json.dumps(patch),
        )
        log.warning(
            'extraction_failed',
            document_id=str(doc_id),
            attempt=attempt,
            final=is_final,
            error=error_msg,
        )
        await _audit(conn, tenant_id, doc_id, 'knowledge_document.extraction_failed', {
            'attempt': attempt,
            'final': is_final,
            'error': error_msg,
        })


async def _audit(
    conn: asyncpg.Connection,
    tenant_id: Any,
    entity_id: Any,
    action: str,
    metadata: dict[str, Any],
) -> None:
    try:
        await conn.execute(
            """
            insert into app.audit_logs
              (tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)
            values ($1, 'system', 'extraction_worker', $2, 'knowledge_document', $3, $4::jsonb)
            """,
            tenant_id,
            action,
            str(entity_id),
            json.dumps(metadata),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning('audit_failed', action=action, error=str(exc))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def main() -> None:
    configure_logging(get_settings().log_level)
    settings = get_settings()
    log.info('extraction_worker_starting', poll_interval=POLL_INTERVAL_SECONDS)
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            async with conn.transaction():
                rows = await _fetch_eligible_documents(conn)
                for row in rows:
                    try:
                        await _process_document(conn, row)
                    except Exception as exc:  # noqa: BLE001
                        log.error('process_document_unexpected_error', document_id=str(row['id']), error=str(exc))
            if not rows:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
