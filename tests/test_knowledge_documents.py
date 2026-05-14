from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import KnowledgeDocumentCreate, KnowledgeDocumentUpdate


def test_knowledge_document_create_accepts_manual_faq_content():
    tenant_id = uuid4()

    payload = KnowledgeDocumentCreate(
        tenant_id=tenant_id,
        title='FAQ de garantías',
        document_type='faq',
        content='P: ¿Cuánto dura la garantía? R: 30 días.',
        visibility='agents_only',
        metadata={'category': 'postventa'},
    )

    assert payload.tenant_id == tenant_id
    assert payload.source_type == 'manual'
    assert payload.status == 'draft'
    assert payload.metadata == {'category': 'postventa'}


def test_knowledge_document_create_accepts_registered_upload_source():
    payload = KnowledgeDocumentCreate(
        tenant_id=uuid4(),
        title='Manual de servicios',
        source_type='upload',
        document_type='policy',
        source_uri='s3://copilotoia-local/manual.pdf',
        mime_type='application/pdf',
        checksum='sha256:abc123',
        status='indexing',
    )

    assert payload.source_uri == 's3://copilotoia-local/manual.pdf'
    assert payload.mime_type == 'application/pdf'
    assert payload.status == 'indexing'


@pytest.mark.parametrize('field,value', [('status', 'archived'), ('visibility', 'private'), ('source_type', 'file')])
def test_knowledge_document_create_rejects_unsupported_enums(field, value):
    data = {'tenant_id': uuid4(), 'title': 'Documento'}
    data[field] = value

    with pytest.raises(ValidationError):
        KnowledgeDocumentCreate(**data)


def test_knowledge_document_update_allows_partial_status_change():
    payload = KnowledgeDocumentUpdate(status='active')

    assert payload.model_dump(exclude_unset=True) == {'status': 'active'}


def test_knowledge_document_projection_exposes_canonical_columns():
    """The projection is now a static list of the canonical columns — there is no
    runtime column-existence check anymore."""
    from app.api.v1.routes import KNOWLEDGE_DOCUMENT_PROJECTION

    assert 'document_type' in KNOWLEDGE_DOCUMENT_PROJECTION
    assert 'content' in KNOWLEDGE_DOCUMENT_PROJECTION
    assert 'metadata' in KNOWLEDGE_DOCUMENT_PROJECTION
    assert 'select' not in KNOWLEDGE_DOCUMENT_PROJECTION.lower()


def test_normalize_knowledge_document_parses_jsonb_metadata_strings():
    from app.api.v1.routes import normalize_knowledge_document

    document = normalize_knowledge_document(
        {
            'id': uuid4(),
            'tenant_id': uuid4(),
            'title': 'FAQ',
            'status': 'draft',
            'metadata': '{"extracted_text": "Texto listo para indexar"}',
        }
    )

    assert document['metadata'] == {'extracted_text': 'Texto listo para indexar'}


def test_normalize_knowledge_document_recovers_invalid_metadata_as_empty_object():
    from app.api.v1.routes import normalize_knowledge_document

    document = normalize_knowledge_document(
        {
            'id': uuid4(),
            'tenant_id': uuid4(),
            'title': 'FAQ',
            'status': 'draft',
            'metadata': 'not-json',
        }
    )

    assert document['metadata'] == {}


def test_knowledge_storage_routes_and_admin_module_are_registered():
    routes_source = Path('app/api/v1/routes.py').read_text()
    modules_source = Path('admin-panel/src/data/modules.js').read_text()
    layout_source = Path('admin-panel/src/app/ModuleContent.jsx').read_text()

    assert "@tenant_admin_router.get('/tenants/{tenant_id}/knowledge/storage')" in routes_source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/knowledge/storage')" in routes_source
    assert "id: 'knowledge-storage'" in modules_source
    assert 'KnowledgeStorageSettings' in layout_source
