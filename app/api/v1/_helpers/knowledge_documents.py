"""Knowledge document projection + normalizers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import asyncpg

from app.api.v1._helpers.parsing import parse_json_object
from app.db.pool import record_to_dict


KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS = (
    'id',
    'tenant_id',
    'source_type',
    'document_type',
    'title',
    'source_uri',
    'checksum',
    'mime_type',
    'content',
    'visibility',
    'status',
    'uploaded_by_user_id',
    'metadata',
    'created_at',
    'updated_at',
)
KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS = (
    'source_type',
    'document_type',
    'title',
    'source_uri',
    'checksum',
    'mime_type',
    'content',
    'visibility',
    'status',
    'metadata',
)
KNOWLEDGE_DOCUMENT_PROJECTION = ', '.join(KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS)


def normalize_knowledge_document(row: asyncpg.Record | None) -> dict | None:
    document = record_to_dict(row)
    if not document:
        return None
    document['metadata'] = parse_json_object(document.get('metadata'), default={})
    return document


def normalize_knowledge_documents(rows: list[asyncpg.Record]) -> list[dict]:
    return [normalize_knowledge_document(row) for row in rows]
