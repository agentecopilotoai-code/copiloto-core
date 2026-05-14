/**
 * UI-007.14 — Config · Legal: pure data helpers.
 *
 * Legal-document kinds, the draft-form shape, document grouping and the safe
 * Markdown-subset preview renderer — extracted verbatim from the legacy
 * `LegalModule` so the editor / history / published panels share them and they
 * stay unit-testable without React.
 */

/** Spanish labels per legal-document kind. */
export const KIND_LABELS = {
  terms: 'Términos y Condiciones',
  privacy: 'Política de Privacidad',
  consent: 'Aviso de Tratamiento de Datos',
};

/** Display order of the legal-document kinds. */
export const KIND_ORDER = ['privacy', 'terms', 'consent'];

/** A blank legal-draft form. */
export function emptyDraft() {
  return {
    kind: 'privacy',
    language: 'es',
    title: '',
    content_md: '',
  };
}

/**
 * HTML-escape a string. All preview inputs are escaped before transformation
 * so the preview cannot inject scripts even if the admin pastes raw HTML.
 */
export function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/** Render inline Markdown (code, bold, italic, http(s)/mailto links). */
export function renderInline(line) {
  let out = escapeHtml(line);
  out = out.replaceAll(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replaceAll(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replaceAll(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  out = out.replaceAll(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    '<a href="$2" rel="nofollow noopener noreferrer">$1</a>',
  );
  return out;
}

/**
 * Render the Markdown subset shared with the backend renderer: paragraphs,
 * headings, ordered/unordered lists and the inline transforms above. Returns a
 * sanitised HTML string safe for `dangerouslySetInnerHTML`.
 */
export function renderPreview(md) {
  const lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let para = [];
  let list = null;
  let items = [];
  const flushPara = () => {
    if (para.length) {
      blocks.push(`<p>${para.map(renderInline).join(' ')}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list && items.length) {
      blocks.push(
        `<${list}>${items.map((it) => `<li>${renderInline(it)}</li>`).join('')}</${list}>`,
      );
    }
    list = null;
    items = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushPara();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushPara();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInline(heading[2].trim())}</h${level}>`);
      continue;
    }
    const ul = line.match(/^[-*+]\s+(.+)$/);
    if (ul) {
      flushPara();
      if (list && list !== 'ul') flushList();
      list = 'ul';
      items.push(ul[1].trim());
      continue;
    }
    const ol = line.match(/^\d+\.\s+(.+)$/);
    if (ol) {
      flushPara();
      if (list && list !== 'ol') flushList();
      list = 'ol';
      items.push(ol[1].trim());
      continue;
    }
    flushList();
    para.push(line);
  }
  flushPara();
  flushList();
  return `<article class="legal-document">${blocks.join('')}</article>`;
}

/** Group legal documents by kind. */
export function groupByKind(documents) {
  const out = { privacy: [], terms: [], consent: [] };
  (documents || []).forEach((doc) => {
    if (out[doc.kind]) out[doc.kind].push(doc);
  });
  return out;
}

/** The currently-published (non-archived) document per kind, or `undefined`. */
export function publishedByKind(grouped) {
  const out = {};
  for (const kind of KIND_ORDER) {
    out[kind] = (grouped[kind] || []).find((d) => d.published_at && !d.archived_at);
  }
  return out;
}

/** Spanish status label for a legal-document version. */
export function docStatusLabel(doc) {
  if (doc.published_at && !doc.archived_at) return 'Publicado';
  if (doc.archived_at) return 'Archivado';
  return 'Borrador';
}

/** `StatusBadge` tone for a legal-document version status. */
export function docStatusTone(doc) {
  if (doc.published_at && !doc.archived_at) return 'success';
  if (doc.archived_at) return 'neutral';
  return 'warning';
}
