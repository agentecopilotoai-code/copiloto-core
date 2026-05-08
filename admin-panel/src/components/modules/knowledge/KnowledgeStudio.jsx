import { useEffect, useMemo, useState } from 'react';

import {
  createKnowledgeDocument,
  evaluateIntent,
  deleteKnowledgeDocument,
  indexKnowledgeDocument,
  listKnowledgeDocuments,
  updateKnowledgeDocument,
  uploadKnowledgeDocument,
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
  const [ragQuestion, setRagQuestion] = useState('');
  const [ragResult, setRagResult] = useState(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [uploadForm, setUploadForm] = useState({ title: '', document_type: 'reference', visibility: 'tenant', file: null });
  const [isUploading, setIsUploading] = useState(false);

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

  async function runIndexing(document) {
    setNotice(null);
    try {
      const indexedDocument = await indexKnowledgeDocument(session, tenant.id, document.id);
      const chunkCount = indexedDocument.indexing?.chunk_count || indexedDocument.metadata?.chunk_count || 0;
      setNotice({
        type: 'success',
        text: `Documento indexado y activado con ${chunkCount} chunks.`,
      });
      loadDocuments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
      loadDocuments();
    }
  }

  async function evaluateRetrieval(event) {
    event.preventDefault();
    if (!tenant?.id || !ragQuestion.trim()) return;
    setIsEvaluating(true);
    setNotice(null);
    try {
      const result = await evaluateIntent(session, tenant.id, { question: ragQuestion.trim() });
      setRagResult(result);
      setNotice({
        type: result.sufficient_context ? 'success' : 'info',
        text: result.sufficient_context
          ? 'Respuesta RAG generada con evidencia trazable.'
          : 'Sin evidencia suficiente: escalar a humano.',
      });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsEvaluating(false);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!tenant?.id || !uploadForm.file || !uploadForm.title.trim()) return;
    setIsUploading(true);
    setNotice(null);
    try {
      const uploaded = await uploadKnowledgeDocument(session, tenant.id, uploadForm);
      setNotice({
        type: 'success',
        text: uploaded.content
          ? 'Archivo guardado; texto extraído. Ya puedes indexarlo.'
          : 'Archivo guardado; agrega texto extraído antes de indexar este formato.',
      });
      setUploadForm({ title: '', document_type: 'reference', visibility: 'tenant', file: null });
      event.target.reset();
      loadDocuments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsUploading(false);
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
          <p className="hint">Crea FAQ, políticas y registros de fuente aislados por tenant mediante RLS. Usa Indexar para generar chunks y activar documentos.</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label}</strong>
        </div>
      </div>

      {notice && <div className={`notice ${notice.type}`}>{notice.text}</div>}

      <form className="knowledge-upload" onSubmit={handleUpload}>
        <div>
          <h3>Carga de archivos</h3>
          <p className="hint">Guarda archivos en el backend configurado para conocimiento. TXT, Markdown, CSV y JSON se extraen automáticamente para indexado; PDF queda almacenado y requiere texto extraído en edición.</p>
        </div>
        <div className="form-grid compact-grid">
          <label>Título del archivo<input value={uploadForm.title} onChange={(event) => setUploadForm((current) => ({ ...current, title: event.target.value }))} required /></label>
          <label>Tipo<select value={uploadForm.document_type} onChange={(event) => setUploadForm((current) => ({ ...current, document_type: event.target.value }))}><option value="faq">FAQ</option><option value="policy">Política</option><option value="reference">Referencia</option></select></label>
          <label>Visibilidad<select value={uploadForm.visibility} onChange={(event) => setUploadForm((current) => ({ ...current, visibility: event.target.value }))}><option value="tenant">Tenant</option><option value="agents_only">Solo agentes</option><option value="public">Público</option></select></label>
          <label className="wide">Archivo<input accept=".txt,.md,.markdown,.csv,.json,.pdf,text/plain,text/markdown,text/csv,application/json,application/pdf" onChange={(event) => setUploadForm((current) => ({ ...current, file: event.target.files?.[0] || null }))} required type="file" /></label>
        </div>
        <div className="form-actions">
          <button className="primary-action" disabled={isUploading || !uploadForm.file || !uploadForm.title.trim()} type="submit">
            {isUploading ? 'Subiendo…' : 'Guardar archivo'}
          </button>
        </div>
      </form>

      <form className="rag-tester" onSubmit={evaluateRetrieval}>
        <div>
          <h3>Prueba RAG</h3>
          <p className="hint">Pregunta contra documentos activos. La respuesta solo se muestra si hay contexto suficiente; si no, se solicita handoff humano.</p>
        </div>
        <label>
          Pregunta de prueba
          <textarea
            value={ragQuestion}
            onChange={(event) => setRagQuestion(event.target.value)}
            placeholder="Ej. ¿Cuánto dura la garantía del servicio?"
          />
        </label>
        <div className="form-actions">
          <button className="primary-action" disabled={isEvaluating || !ragQuestion.trim()} type="submit">
            {isEvaluating ? 'Evaluando…' : 'Evaluar retrieval'}
          </button>
        </div>
        {ragResult && (
          <div className="rag-result">
            <div className="rag-answer">
              <span className={`status-pill ${ragResult.sufficient_context ? 'active' : 'failed'}`}>
                {ragResult.status}
              </span>
              <p>{ragResult.answer || ragResult.reason}</p>
              {ragResult.handoff?.required && <strong>Escalar a humano: {ragResult.handoff.reason}</strong>}
            </div>
            <div className="rag-chunks">
              <h4>Chunks recuperados</h4>
              {ragResult.chunks.length === 0 && <p className="hint">No se recuperaron chunks activos para esta pregunta.</p>}
              {ragResult.chunks.map((chunk) => (
                <article className="rag-chunk" key={chunk.id}>
                  <div className="document-subtle-meta">
                    <span>score {chunk.score}</span>
                    <span>{chunk.visibility}</span>
                    <span>{chunk.source_type}</span>
                  </div>
                  <strong>{chunk.document_title}</strong>
                  <small>{chunk.section_path || 'Documento'} · {chunk.source_uri || 'fuente manual'} · chunk #{chunk.chunk_index}</small>
                  <p>{chunk.excerpt}</p>
                </article>
              ))}
            </div>
          </div>
        )}
      </form>

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
            <label>Estado<select value={form.status} onChange={(event) => setField('status', event.target.value)}><option value="draft">Draft</option><option value="indexing">Indexing</option><option value="active" disabled>Active (solo por indexado)</option><option value="failed">Failed</option></select></label>
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
                <div className="knowledge-document-main">
                  <strong>{document.title}</strong>
                  <p>{documentSummary(document)}</p>
                </div>
                <div className="document-subtle-meta" aria-label="Metadatos del documento">
                  <span className={`status-pill ${document.status}`}>{statusLabels[document.status] || document.status}</span>
                  <span>{document.visibility}</span>
                  <span>{document.source_type}</span>
                </div>
                <div className="document-actions">
                  <select
                    aria-label={`Cambiar estado de ${document.title}`}
                    className="status-select"
                    value={document.status}
                    onChange={(event) => changeStatus(document, event.target.value)}
                  >
                    <option value="draft">Draft</option>
                    <option value="indexing">Indexing</option>
                    <option value="active" disabled>Active (solo por indexado)</option>
                    <option value="failed">Failed</option>
                  </select>
                  <button className="icon-action" onClick={() => runIndexing(document)} type="button">Indexar</button>
                  <button className="icon-action" onClick={() => editDocument(document)} type="button">Editar</button>
                  <button className="icon-action danger" onClick={() => removeDocument(document)} type="button">Eliminar</button>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
