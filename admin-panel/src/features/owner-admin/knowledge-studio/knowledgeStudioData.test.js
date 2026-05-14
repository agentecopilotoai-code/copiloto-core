import { describe, it, expect } from 'vitest';

import {
  buildPayload,
  documentSummary,
  embeddingProviderBadge,
  extractionStatusBadge,
  formFromDocument,
  hasLocalHashActive,
  isAwaitingExtraction,
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
