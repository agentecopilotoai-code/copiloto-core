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
