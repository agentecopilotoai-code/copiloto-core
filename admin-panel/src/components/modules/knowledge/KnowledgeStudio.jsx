import { useEffect, useMemo, useState } from 'react';

import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  updateKnowledgeDocument,
} from '../../../services/coreApi.js';

const emptyForm = {
  title: '',
  document_type: 'faq',
  source_type: 'manual',
  source_uri: '',
  mime_type: '',
  checksum: '',
  visibility: 'tenant',
  status: 'draft',
  content: '',
};

const statusLabels = {
  draft: 'Draft',
  indexing: 'Indexing',
  active: 'Active',
  failed: 'Failed',
};

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function documentSummary(document) {
  if (document.content) return document.content.slice(0, 150);
  if (document.source_uri) return document.source_uri;
  return 'Documento sin contenido todavía.';
}

export function KnowledgeStudio({ module, session, tenant }) {
  const [documents, setDocuments] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [notice, setNotice] = useState(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === editingId),
    [documents, editingId],
  );

  function setField(field, value) {
    setForm((currentForm) => ({ ...currentForm, [field]: value }));
  }

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  function loadDocuments() {
    if (!tenant?.id) return;
    setIsLoading(true);
    setNotice(null);
    listKnowledgeDocuments(session, tenant.id, { status: statusFilter, visibility: visibilityFilter })
      .then(setDocuments)
      .catch((error) => setNotice({ type: 'error', text: error.message }))
      .finally(() => setIsLoading(false));
  }

  useEffect(loadDocuments, [session, tenant?.id, statusFilter, visibilityFilter]);

  function editDocument(document) {
    setEditingId(document.id);
    setForm({
      title: document.title || '',
      document_type: document.document_type || 'reference',
      source_type: document.source_type || 'manual',
      source_uri: document.source_uri || '',
      mime_type: document.mime_type || '',
      checksum: document.checksum || '',
      visibility: document.visibility || 'tenant',
      status: document.status || 'draft',
      content: document.content || '',
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!tenant?.id) return;
    setIsSaving(true);
    setNotice(null);
    const payload = {
      ...form,
      source_uri: form.source_uri || null,
      mime_type: form.mime_type || null,
      checksum: form.checksum || null,
      content: form.content || null,
      metadata: {
        editor: 'admin-panel',
        registered_source: form.source_type !== 'manual',
      },
    };

    try {
      if (editingId) {
        await updateKnowledgeDocument(session, tenant.id, editingId, payload);
        setNotice({ type: 'success', text: 'Documento actualizado.' });
      } else {
        await createKnowledgeDocument(session, tenant.id, payload);
        setNotice({ type: 'success', text: 'Documento creado en draft.' });
      }
      resetForm();
      loadDocuments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsSaving(false);
    }
  }

  async function changeStatus(document, nextStatus) {
    setNotice(null);
    try {
      await updateKnowledgeDocument(session, tenant.id, document.id, { status: nextStatus });
      setNotice({ type: 'success', text: `Estado cambiado a ${statusLabels[nextStatus]}.` });
      loadDocuments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    }
  }

  async function removeDocument(document) {
    setNotice(null);
    try {
      await deleteKnowledgeDocument(session, tenant.id, document.id);
      if (editingId === document.id) resetForm();
      setNotice({ type: 'success', text: 'Documento eliminado.' });
      loadDocuments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    }
  }

  return (
    <section className="module-card knowledge-studio">
      <div className="module-heading">
        <div>
          <p className="eyebrow">{module.label}</p>
          <h2>{module.summary}</h2>
          <p className="hint">Crea FAQ, políticas y registros de fuente aislados por tenant mediante RLS.</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label}</strong>
        </div>
      </div>

      {notice && <div className={`notice ${notice.type}`}>{notice.text}</div>}

      <div className="knowledge-layout">
        <form className="knowledge-editor" onSubmit={handleSubmit}>
          <div className="form-actions split-actions">
            {editingId && (
              <button className="secondary-action" onClick={resetForm} type="button">
                Nuevo documento
              </button>
            )}
            <button className="primary-action" disabled={isSaving || !form.title} type="submit">
              {isSaving ? 'Guardando…' : editingId ? 'Actualizar' : 'Crear documento'}
            </button>
          </div>

          <label>
            Título
            <input value={form.title} onChange={(event) => setField('title', event.target.value)} required />
          </label>

          <div className="form-grid compact-grid">
            <label>Tipo<select value={form.document_type} onChange={(event) => setField('document_type', event.target.value)}><option value="faq">FAQ</option><option value="policy">Política</option><option value="reference">Referencia</option></select></label>
            <label>Fuente<select value={form.source_type} onChange={(event) => setField('source_type', event.target.value)}><option value="manual">Manual</option><option value="upload">Archivo / object storage</option><option value="url">URL</option><option value="integration">Integración</option></select></label>
            <label>Visibilidad<select value={form.visibility} onChange={(event) => setField('visibility', event.target.value)}><option value="tenant">Tenant</option><option value="agents_only">Solo agentes</option><option value="public">Público</option></select></label>
            <label>Estado<select value={form.status} onChange={(event) => setField('status', event.target.value)}><option value="draft">Draft</option><option value="indexing">Indexing</option><option value="active">Active</option><option value="failed">Failed</option></select></label>
          </div>

          <label>
            FAQ / política manual
            <textarea value={form.content} onChange={(event) => setField('content', event.target.value)} placeholder="Pregunta/respuesta, política operativa o contenido de referencia." />
          </label>

          <div className="form-grid compact-grid">
            <label>URI de fuente u object key<input value={form.source_uri} onChange={(event) => setField('source_uri', event.target.value)} placeholder="s3://bucket/key.pdf o https://…" /></label>
            <label>MIME type<input value={form.mime_type} onChange={(event) => setField('mime_type', event.target.value)} placeholder="application/pdf" /></label>
            <label className="wide">Checksum<input value={form.checksum} onChange={(event) => setField('checksum', event.target.value)} placeholder="sha256 opcional" /></label>
          </div>

          {selectedDocument && (
            <p className="hint">Editando {selectedDocument.id} · actualizado {formatDate(selectedDocument.updated_at)}</p>
          )}
        </form>

        <aside className="knowledge-list-panel">
          <div className="list-header">
            <div>
              <h3>Documentos</h3>
              <p className="hint">{documents.length} visibles para este tenant.</p>
            </div>
            <button className="secondary-action" disabled={isLoading} onClick={loadDocuments} type="button">Refrescar</button>
          </div>

          <div className="form-grid compact-grid filters">
            <label>Estado<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">Todos</option><option value="draft">Draft</option><option value="indexing">Indexing</option><option value="active">Active</option><option value="failed">Failed</option></select></label>
            <label>Visibilidad<select value={visibilityFilter} onChange={(event) => setVisibilityFilter(event.target.value)}><option value="">Todas</option><option value="tenant">Tenant</option><option value="agents_only">Solo agentes</option><option value="public">Público</option></select></label>
          </div>

          <div className="knowledge-documents">
            {isLoading && <p className="notice info">Cargando documentos…</p>}
            {!isLoading && documents.length === 0 && <p className="notice info">No hay documentos con esos filtros.</p>}
            {documents.map((document) => (
              <article className="knowledge-document" key={document.id}>
                <div>
                  <strong>{document.title}</strong>
                  <p>{documentSummary(document)}</p>
                </div>
                <dl className="mini-meta">
                  <div><dt>Estado</dt><dd><span className={`status-pill ${document.status}`}>{statusLabels[document.status] || document.status}</span></dd></div>
                  <div><dt>Visibilidad</dt><dd>{document.visibility}</dd></div>
                  <div><dt>Fuente</dt><dd>{document.source_type}</dd></div>
                </dl>
                <div className="document-actions">
                  <button className="secondary-action" onClick={() => editDocument(document)} type="button">Editar</button>
                  <select value={document.status} onChange={(event) => changeStatus(document, event.target.value)}>
                    <option value="draft">Draft</option>
                    <option value="indexing">Indexing</option>
                    <option value="active">Active</option>
                    <option value="failed">Failed</option>
                  </select>
                  <button className="secondary-action danger" onClick={() => removeDocument(document)} type="button">Eliminar</button>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
