/**
 * UI-007.10 — IA · Knowledge Studio: pure data helpers.
 *
 * Form shapes, option catalogues, badge derivation and payload building —
 * extracted verbatim from the legacy `KnowledgeStudio` so the table / drawers /
 * RAG tester share them and they stay unit-testable without React.
 */

/** A blank document editor form. */
export const EMPTY_FORM = Object.freeze({
  title: '',
  document_type: 'faq',
  source_type: 'manual',
  source_uri: '',
  mime_type: '',
  checksum: '',
  visibility: 'tenant',
  status: 'draft',
  content: '',
});

/** A blank file-upload form. */
export const EMPTY_UPLOAD_FORM = Object.freeze({
  title: '',
  document_type: 'reference',
  visibility: 'tenant',
  file: null,
});

/** Spanish labels for a document's lifecycle status. */
export const STATUS_LABELS = {
  draft: 'Draft',
  indexing: 'Indexing',
  active: 'Active',
  failed: 'Failed',
};

/** `StatusBadge` tone for a document's lifecycle status. */
export const STATUS_TONE = {
  draft: 'neutral',
  indexing: 'warning',
  active: 'success',
  failed: 'danger',
};

/** Internal cls → `StatusBadge` tone mapping for derived badges. */
const CLS_TONE = { draft: 'neutral', indexing: 'warning', active: 'success', failed: 'danger' };

export const DOCUMENT_TYPE_OPTIONS = [
  { value: 'faq', label: 'FAQ' },
  { value: 'policy', label: 'Política' },
  { value: 'reference', label: 'Referencia' },
];

export const SOURCE_TYPE_OPTIONS = [
  { value: 'manual', label: 'Manual' },
  { value: 'upload', label: 'Archivo / object storage' },
  { value: 'url', label: 'URL' },
  { value: 'integration', label: 'Integración' },
];

export const VISIBILITY_OPTIONS = [
  { value: 'tenant', label: 'Tenant' },
  { value: 'agents_only', label: 'Solo agentes' },
  { value: 'public', label: 'Público' },
];

export const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'indexing', label: 'Indexing' },
  { value: 'failed', label: 'Failed' },
];

/** Build the editor-form shape from a document record. */
export function formFromDocument(document) {
  return {
    title: document.title || '',
    document_type: document.document_type || 'reference',
    source_type: document.source_type || 'manual',
    source_uri: document.source_uri || '',
    mime_type: document.mime_type || '',
    checksum: document.checksum || '',
    visibility: document.visibility || 'tenant',
    status: document.status || 'draft',
    content: document.content || '',
  };
}

/** Build the create/update payload from the editor form. */
export function buildPayload(form) {
  return {
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
}

/** Embedding-provider badge (or `null`) — lexical vs semantic. */
export function embeddingProviderBadge(document) {
  const provider = document.metadata?.embedding_provider;
  if (!provider) return null;
  if (provider === 'local_hash') return { label: 'Léxico (hash)', tone: CLS_TONE.draft };
  return { label: `Semántico (${provider})`, tone: CLS_TONE.active };
}

/** Extraction-status badge (or `null`) for upload-backed documents. */
export function extractionStatusBadge(document) {
  const meta = document.metadata || {};
  if (meta.extraction_pending && !meta.extracted_text && document.status !== 'failed') {
    const attempts = meta.extraction_attempt_count || 0;
    return attempts > 0
      ? { label: `Extrayendo… (intento ${attempts})`, tone: CLS_TONE.indexing }
      : { label: 'En cola de extracción', tone: CLS_TONE.indexing };
  }
  if (document.status === 'failed' && meta.extraction_error) {
    return { label: 'Extracción fallida', tone: CLS_TONE.failed };
  }
  if (meta.extracted_text && document.status === 'draft') {
    return { label: 'Texto extraído · listo para indexar', tone: CLS_TONE.active };
  }
  return null;
}

/** True when a document is still waiting for its file text to be extracted. */
export function isAwaitingExtraction(document) {
  const meta = document.metadata || {};
  return Boolean(meta.extraction_pending && !meta.extracted_text);
}

/** Locale-aware date/time formatter for document timestamps. */
export function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  );
}

/** Short one-line summary for a document row. */
export function documentSummary(document) {
  if (document.content) return document.content.slice(0, 150);
  if (document.source_uri) return document.source_uri;
  return 'Documento sin contenido todavía.';
}

/**
 * True when the active documents are indexed with the lexical (`local_hash`)
 * embedding provider — i.e. semantic search is unavailable. Mirrors the legacy
 * banner condition (also true when there are no active providers yet).
 */
export function hasLocalHashActive(documents) {
  const activeProviders = new Set(
    (documents || [])
      .filter((d) => d.status === 'active' && d.metadata?.embedding_provider)
      .map((d) => d.metadata.embedding_provider),
  );
  return activeProviders.has('local_hash') || activeProviders.size === 0;
}
