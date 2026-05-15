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

/**
 * Spanish labels for a document's lifecycle status. Mirrors the HTML mockup
 * (`docs/HTML DESIGN/Transversales/18 _ IA _ Knowledge Studio.html`): `active`,
 * `indexing`, `failed` stay in English (canonical, lowercase) inside the
 * Estado badges; `draft` becomes "Borrador" because that's how the designer
 * surfaces the not-yet-published state.
 */
export const STATUS_LABELS = {
  draft: 'Borrador',
  indexing: 'indexing',
  active: 'active',
  failed: 'failed',
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
  { value: 'draft', label: 'Borrador' },
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
 * Tab definitions for the Documents filter — Todos / Activos / Indexando /
 * Fallidos. Each tab carries the statuses it matches; `all` matches everything.
 * Used to derive counts directly from the document list (no extra fetch).
 */
export const DOCUMENT_FILTER_TABS = [
  { value: 'all', label: 'Todos', statuses: null },
  { value: 'active', label: 'Activos', statuses: ['active'] },
  { value: 'indexing', label: 'Indexando', statuses: ['indexing'] },
  { value: 'failed', label: 'Fallidos', statuses: ['failed'] },
];

/** Map a `DOCUMENT_FILTER_TABS` value to a list of matching statuses (null → all). */
export function statusesForFilterTab(tabValue) {
  const tab = DOCUMENT_FILTER_TABS.find((entry) => entry.value === tabValue);
  return tab ? tab.statuses : null;
}

/** Filter the documents list by the active filter-tab value. */
export function filterDocumentsByTab(documents, tabValue) {
  const statuses = statusesForFilterTab(tabValue);
  if (!statuses) return documents;
  return documents.filter((doc) => statuses.includes(doc.status));
}

/** Count documents matching each `DOCUMENT_FILTER_TABS` entry. */
export function countDocumentsByTab(documents) {
  const list = Array.isArray(documents) ? documents : [];
  const counts = {};
  for (const tab of DOCUMENT_FILTER_TABS) {
    if (!tab.statuses) {
      counts[tab.value] = list.length;
    } else {
      counts[tab.value] = list.filter((doc) => tab.statuses.includes(doc.status)).length;
    }
  }
  return counts;
}

/**
 * Best-effort chunk-count extraction for a document row. The backend exposes
 * it as `metadata.chunk_count` (preferred) or `metadata.indexing.chunk_count`
 * depending on the indexing pipeline version. Returns `null` when not present
 * — the table renders that as the em-dash shown in the design.
 */
export function chunkCount(document) {
  const meta = document?.metadata || {};
  if (typeof meta.chunk_count === 'number') return meta.chunk_count;
  if (typeof meta?.indexing?.chunk_count === 'number') return meta.indexing.chunk_count;
  return null;
}

/**
 * One-line origin label for the Origen column. Manual / integration sources
 * render as the source_type label; upload / url sources surface the URI when
 * available so the operator can recognize the bucket path at a glance.
 */
export function originLabel(document) {
  if (!document) return '—';
  const sourceType = document.source_type || 'manual';
  if (sourceType === 'manual' || sourceType === 'integration') {
    return sourceType;
  }
  return document.source_uri || sourceType;
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
