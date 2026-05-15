import { describe, it, expect } from 'vitest';

import {
  buildPayload,
  chunkCount,
  countDocumentsByTab,
  documentSummary,
  embeddingProviderBadge,
  extractionStatusBadge,
  filterDocumentsByTab,
  formFromDocument,
  hasLocalHashActive,
  isAwaitingExtraction,
  originLabel,
  STATUS_LABELS,
} from './knowledgeStudioData.js';

describe('knowledgeStudioData', () => {
  it('formFromDocument maps a document record into the editor-form shape', () => {
    const form = formFromDocument({
      title: 'Política',
      document_type: 'policy',
      source_type: 'url',
      status: 'active',
      content: 'texto',
    });
    expect(form.title).toBe('Política');
    expect(form.document_type).toBe('policy');
    expect(form.source_type).toBe('url');
    expect(form.status).toBe('active');
  });

  it('buildPayload nulls empty optionals and tags the metadata source', () => {
    const manual = buildPayload({ ...formFromDocument({}), title: 'X', source_type: 'manual' });
    expect(manual.source_uri).toBeNull();
    expect(manual.content).toBeNull();
    expect(manual.metadata).toEqual({ editor: 'admin-panel', registered_source: false });

    const fromUrl = buildPayload({ ...formFromDocument({}), source_type: 'url' });
    expect(fromUrl.metadata.registered_source).toBe(true);
  });

  it('embeddingProviderBadge distinguishes lexical from semantic providers', () => {
    expect(embeddingProviderBadge({ metadata: {} })).toBeNull();
    expect(embeddingProviderBadge({ metadata: { embedding_provider: 'local_hash' } })).toEqual({
      label: 'Léxico (hash)',
      tone: 'neutral',
    });
    expect(
      embeddingProviderBadge({ metadata: { embedding_provider: 'openai' } }),
    ).toEqual({ label: 'Semántico (openai)', tone: 'success' });
  });

  it('extractionStatusBadge + isAwaitingExtraction reflect the extraction lifecycle', () => {
    const pending = { status: 'draft', metadata: { extraction_pending: true } };
    expect(isAwaitingExtraction(pending)).toBe(true);
    expect(extractionStatusBadge(pending).label).toBe('En cola de extracción');

    const failed = { status: 'failed', metadata: { extraction_error: 'bad pdf' } };
    expect(extractionStatusBadge(failed)).toEqual({ label: 'Extracción fallida', tone: 'danger' });

    const ready = { status: 'draft', metadata: { extracted_text: 'hola' } };
    expect(extractionStatusBadge(ready).tone).toBe('success');
    expect(isAwaitingExtraction(ready)).toBe(false);
  });

  it('documentSummary prefers content, then source uri, then a fallback', () => {
    expect(documentSummary({ content: 'abc' })).toBe('abc');
    expect(documentSummary({ source_uri: 's3://k' })).toBe('s3://k');
    expect(documentSummary({})).toBe('Documento sin contenido todavía.');
  });

  it('chunkCount reads metadata.chunk_count or falls back to indexing.chunk_count', () => {
    expect(chunkCount({ metadata: { chunk_count: 12 } })).toBe(12);
    expect(chunkCount({ metadata: { indexing: { chunk_count: 7 } } })).toBe(7);
    expect(chunkCount({ metadata: {} })).toBeNull();
    expect(chunkCount(undefined)).toBeNull();
  });

  it('originLabel returns the source_type for manual/integration and the URI otherwise', () => {
    expect(originLabel({ source_type: 'manual' })).toBe('manual');
    expect(originLabel({ source_type: 'integration' })).toBe('integration');
    expect(originLabel({ source_type: 'upload', source_uri: 's3://kb/x.pdf' })).toBe(
      's3://kb/x.pdf',
    );
    expect(originLabel({ source_type: 'url' })).toBe('url');
    expect(originLabel(null)).toBe('—');
  });

  it('countDocumentsByTab derives counts for Todos / Activos / Indexando / Fallidos', () => {
    const docs = [
      { status: 'active' },
      { status: 'active' },
      { status: 'indexing' },
      { status: 'failed' },
      { status: 'draft' },
    ];
    expect(countDocumentsByTab(docs)).toEqual({
      all: 5,
      active: 2,
      indexing: 1,
      failed: 1,
    });
    expect(countDocumentsByTab([])).toEqual({ all: 0, active: 0, indexing: 0, failed: 0 });
  });

  it('filterDocumentsByTab returns all docs for "all" and filters by status otherwise', () => {
    const docs = [
      { status: 'active', id: 'a' },
      { status: 'indexing', id: 'b' },
      { status: 'failed', id: 'c' },
      { status: 'draft', id: 'd' },
    ];
    expect(filterDocumentsByTab(docs, 'all')).toHaveLength(4);
    expect(filterDocumentsByTab(docs, 'active').map((d) => d.id)).toEqual(['a']);
    expect(filterDocumentsByTab(docs, 'indexing').map((d) => d.id)).toEqual(['b']);
    expect(filterDocumentsByTab(docs, 'failed').map((d) => d.id)).toEqual(['c']);
    // unknown tabs degrade to "show all" rather than hiding rows
    expect(filterDocumentsByTab(docs, 'unknown')).toHaveLength(4);
  });

  it('STATUS_LABELS uses "Borrador" for draft to match the designer HTML', () => {
    expect(STATUS_LABELS.draft).toBe('Borrador');
    expect(STATUS_LABELS.active).toBe('active');
    expect(STATUS_LABELS.indexing).toBe('indexing');
    expect(STATUS_LABELS.failed).toBe('failed');
  });

  it('hasLocalHashActive is true with local_hash docs or no active providers', () => {
    expect(hasLocalHashActive([])).toBe(true);
    expect(
      hasLocalHashActive([
        { status: 'active', metadata: { embedding_provider: 'local_hash' } },
      ]),
    ).toBe(true);
    expect(
      hasLocalHashActive([
        { status: 'active', metadata: { embedding_provider: 'openai' } },
      ]),
    ).toBe(false);
  });
});
