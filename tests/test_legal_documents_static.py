"""Static tests for TASK-0076 — Páginas legales por tenant.

Coverage (≥ 8 tests):
- Schema: ``app.tenant_legal_documents`` exists with the right columns, the
  append-only trigger blocks content mutations and deletes, the partial
  unique index keeps a single published version per (kind, language), and
  the table participates in the generic RLS loop.
- Markdown renderer: escapes raw HTML, allows the constrained subset, drops
  ``javascript:`` link schemes, and wraps the output in the legal article
  shell.
- Consent template: the request body builder appends the legal-page footer
  when a URL is provided, the orchestrator looks up the published doc via
  ``fetch_published_legal_url``.
- Routes: public GET, admin list, draft create, publish.
- Admin panel: module registered, sidebar wiring, coreApi exposes the four
  client functions.
"""

from __future__ import annotations

from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import LegalDocumentDraftCreate
from app.services import consent as consent_service
from app.services.legal import (
    LEGAL_KIND_LABELS_ES,
    LEGAL_KINDS,
    legal_public_url,
    render_markdown_to_safe_html,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
CONSENT = Path('app/services/consent.py')
ADMIN_LAYOUT = Path('admin-panel/src/app/ModuleContent.jsx')
ADMIN_MODULES = Path('admin-panel/src/data/modules.js')
LEGAL_MODULE = Path('admin-panel/src/components/modules/legal/LegalModule.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')


# ─── Schema ───────────────────────────────────────────────────────────────


def test_schema_creates_tenant_legal_documents_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.tenant_legal_documents (' in schema
    for fragment in (
        'tenant_id uuid not null references app.tenants(id) on delete cascade',
        "kind text not null check (kind in ('terms','privacy','consent'))",
        "language text not null default 'es'",
        'version int not null check (version >= 1)',
        'title text not null',
        'content_md text not null',
        'published_at timestamptz',
        'archived_at timestamptz',
    ):
        assert fragment in schema, f'missing tenant_legal_documents column: {fragment}'
    assert (
        'constraint uq_tenant_legal_documents_version unique (tenant_id, kind, language, version)'
        in schema
    )
    # Only one live (published & not archived) doc per (tenant, kind, language)
    assert (
        'create unique index ux_tenant_legal_documents_published_current\n'
        '  on app.tenant_legal_documents(tenant_id, kind, language)\n'
        '  where published_at is not null and archived_at is null'
    ) in schema


def test_schema_blocks_legal_document_content_mutations_and_deletes():
    schema = SCHEMA.read_text()
    # Append-only trigger: any UPDATE that changes content_md / kind / language /
    # version raises a permission error so we keep the audit trail intact.
    assert 'app.tenant_legal_documents_block_content_mutations()' in schema
    assert 'trg_tenant_legal_documents_no_content_update' in schema
    assert "raise exception 'tenant_legal_documents is append-only by version (TASK-0076)'" in schema
    # No DELETEs allowed.
    assert 'app.tenant_legal_documents_block_delete()' in schema
    assert 'trg_tenant_legal_documents_no_delete' in schema
    # Publishing v2 archives the prior v1 for the same (tenant, kind, language).
    assert 'app.tenant_legal_documents_archive_previous()' in schema
    assert 'trg_tenant_legal_documents_archive_previous' in schema


def test_schema_enables_rls_and_registers_legal_table_in_policy_loop():
    schema = SCHEMA.read_text()
    assert 'alter table app.tenant_legal_documents enable row level security;' in schema
    # The generic policy loop attaches tenant_select/insert/update/delete.
    assert "'tenant_legal_documents'" in schema


# ─── Markdown renderer ────────────────────────────────────────────────────


def test_render_markdown_escapes_raw_html_and_drops_script_tags():
    payload = '<script>alert(1)</script>\n\nHola **mundo**'
    out = render_markdown_to_safe_html(payload)
    assert '<script>' not in out
    assert '&lt;script&gt;' in out
    assert '<strong>mundo</strong>' in out
    assert out.startswith('<article class="legal-document">')
    assert out.endswith('</article>')


def test_render_markdown_drops_javascript_link_scheme():
    payload = '[click](javascript:alert(1))'
    out = render_markdown_to_safe_html(payload)
    assert '<a ' not in out
    assert 'javascript:' not in out
    assert 'click' in out  # label is preserved as plain text


def test_render_markdown_supports_headings_lists_and_safe_links():
    payload = (
        '# Política\n\n'
        'Bienvenido a *nuestra* política.\n\n'
        '- Punto 1\n'
        '- Punto 2\n\n'
        '[Soporte](https://example.com/help)'
    )
    out = render_markdown_to_safe_html(payload)
    assert '<h1>Política</h1>' in out
    assert '<em>nuestra</em>' in out
    assert '<ul><li>Punto 1</li><li>Punto 2</li></ul>' in out
    assert '<a href="https://example.com/help"' in out
    assert 'rel="nofollow noopener noreferrer"' in out


def test_legal_public_url_validates_kind():
    url = legal_public_url('http://api.local', 'aaaa-bbbb', 'privacy')
    assert url == 'http://api.local/v1/tenants/aaaa-bbbb/legal/privacy'
    import pytest

    with pytest.raises(ValueError):
        legal_public_url('http://api.local', 'aaaa-bbbb', 'gdpr')


def test_legal_kinds_constants_match_backlog():
    assert LEGAL_KINDS == ('terms', 'privacy', 'consent')
    assert set(LEGAL_KIND_LABELS_ES.keys()) == set(LEGAL_KINDS)


# ─── Consent template integration ─────────────────────────────────────────


def test_consent_request_body_appends_legal_link_when_provided():
    body = consent_service.build_consent_request_body_text(
        'Spa La Florida',
        legal_url='https://api.copilotoia.com/v1/tenants/T/legal/privacy',
    )
    assert 'Spa La Florida' in body
    assert 'Conoce nuestra política' in body
    assert 'https://api.copilotoia.com/v1/tenants/T/legal/privacy' in body


def test_consent_request_body_skips_footer_when_no_legal_url():
    body = consent_service.build_consent_request_body_text('Demo')
    assert 'Conoce nuestra política' not in body
    assert 'Demo' in body


def test_consent_payload_carries_legal_url_in_body():
    payload = consent_service.build_consent_request_payload(
        'Demo', legal_url='https://example.com/v1/tenants/T/legal/privacy'
    )
    text = payload['body']['text']
    assert 'https://example.com/v1/tenants/T/legal/privacy' in text
    # Buttons stay intact.
    button_ids = [b['reply']['id'] for b in payload['action']['buttons']]
    assert button_ids == ['consent:yes', 'consent:no']


def test_orchestrator_calls_fetch_published_legal_url_when_sending_request():
    src = CONSENT.read_text()
    assert 'fetch_published_legal_url' in src
    assert "kind: str = 'privacy'" in src
    # The unknown opt-in branch must look up the URL before queueing.
    assert "await fetch_published_legal_url(conn, tenant_id, 'privacy')" in src


# ─── Routes / schemas ─────────────────────────────────────────────────────


def test_legal_document_draft_create_schema_enforces_kind():
    draft = LegalDocumentDraftCreate(
        kind='privacy', language='es', title='Política', content_md='# Hola'
    )
    assert draft.kind == 'privacy'
    assert draft.language == 'es'

    import pytest

    with pytest.raises(Exception):
        LegalDocumentDraftCreate(kind='gdpr', title='x', content_md='y')


def test_routes_register_public_legal_get_and_admin_endpoints():
    src = ROUTES.read_text()
    assert "@public_router.get('/tenants/{tenant_id}/legal/{kind}')" in src
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/legal')" in src
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/legal', status_code=201)" in src
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/legal/{document_id}/publish')" in src
    # The public endpoint returns HTML (not JSON) because it's intended to be
    # opened in a browser from a WhatsApp link or campaign footer.
    assert 'HTMLResponse' in src


def test_routes_audit_legal_publishing_actions():
    src = ROUTES.read_text()
    assert "action='legal_document.drafted'" in src
    assert "action='legal_document.published'" in src
    assert "entity_type='tenant_legal_document'" in src


def test_routes_module_imports_legal_helpers():
    # We rely on these names existing at import time so missing imports are
    # caught here, not at first hit of the public endpoint in production.
    assert hasattr(routes_module, 'render_markdown_to_safe_html')
    assert hasattr(routes_module, 'LEGAL_KINDS')


# ─── Admin panel ──────────────────────────────────────────────────────────


def test_admin_panel_registers_legal_module():
    modules = ADMIN_MODULES.read_text()
    assert "id: 'legal'" in modules
    assert 'TASK-0076' in modules
    layout = ADMIN_LAYOUT.read_text()
    assert "import { LegalModule }" in layout
    assert "case 'legal'" in layout


def test_core_api_exposes_legal_client_functions():
    api = CORE_API.read_text()
    for symbol in (
        'export function listLegalDocuments',
        'export function createLegalDocumentDraft',
        'export function publishLegalDocument',
        'export function legalDocumentPublicUrl',
    ):
        assert symbol in api, f'missing coreApi export: {symbol}'


def test_legal_module_renders_preview_with_safe_html_helper():
    src = LEGAL_MODULE.read_text()
    # The preview uses a local Markdown subset renderer; ensure it escapes HTML
    # before applying transformations (mirrors the backend renderer).
    assert 'function escapeHtml' in src
    assert 'function renderPreview' in src
    assert 'dangerouslySetInnerHTML' in src
    # Only http(s) and mailto link schemes are accepted in the preview regex.
    assert 'https?:\\/\\/' in src
    assert 'mailto:' in src
