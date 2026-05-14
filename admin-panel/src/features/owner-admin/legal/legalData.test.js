import { describe, it, expect } from 'vitest';

import {
  docStatusLabel,
  docStatusTone,
  emptyDraft,
  escapeHtml,
  groupByKind,
  publishedByKind,
  renderInline,
  renderPreview,
} from './legalData.js';

describe('legalData', () => {
  it('emptyDraft starts blank with privacy + es defaults', () => {
    expect(emptyDraft()).toEqual({
      kind: 'privacy',
      language: 'es',
      title: '',
      content_md: '',
    });
  });

  it('escapeHtml neutralises raw HTML', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt;',
    );
    expect(escapeHtml('a & "b" \'c\'')).toBe('a &amp; &quot;b&quot; &#39;c&#39;');
  });

  it('renderInline escapes first, then applies the markdown subset', () => {
    expect(renderInline('**bold** and `code`')).toBe(
      '<strong>bold</strong> and <code>code</code>',
    );
    // Only http(s) / mailto link schemes are accepted.
    expect(renderInline('[ok](https://x.co)')).toContain('<a href="https://x.co"');
    expect(renderInline('[bad](javascript:alert(1))')).toBe(
      '[bad](javascript:alert(1))',
    );
  });

  it('renderPreview builds headings, lists and paragraphs into safe HTML', () => {
    const html = renderPreview('# Title\n\n- one\n- two\n\nparagraph');
    expect(html).toContain('<h1>Title</h1>');
    expect(html).toContain('<ul><li>one</li><li>two</li></ul>');
    expect(html).toContain('<p>paragraph</p>');
    expect(html.startsWith('<article class="legal-document">')).toBe(true);
  });

  it('groupByKind + publishedByKind bucket documents and pick the live version', () => {
    const docs = [
      { id: 'd1', kind: 'privacy', version: 1, published_at: '2026-01-01', archived_at: '2026-02-01' },
      { id: 'd2', kind: 'privacy', version: 2, published_at: '2026-02-01', archived_at: null },
      { id: 'd3', kind: 'terms', version: 1, published_at: null, archived_at: null },
    ];
    const grouped = groupByKind(docs);
    expect(grouped.privacy).toHaveLength(2);
    expect(grouped.terms).toHaveLength(1);
    const published = publishedByKind(grouped);
    expect(published.privacy.id).toBe('d2');
    expect(published.terms).toBeUndefined();
  });

  it('docStatusLabel + docStatusTone reflect the publish/archive lifecycle', () => {
    expect(docStatusLabel({ published_at: null })).toBe('Borrador');
    expect(docStatusTone({ published_at: null })).toBe('warning');
    expect(docStatusLabel({ published_at: '2026-01-01', archived_at: null })).toBe('Publicado');
    expect(docStatusTone({ published_at: '2026-01-01', archived_at: null })).toBe('success');
    expect(docStatusLabel({ published_at: '2026-01-01', archived_at: '2026-02-01' })).toBe(
      'Archivado',
    );
  });
});
