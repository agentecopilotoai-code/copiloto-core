import { useEffect, useMemo, useState } from 'react';

import {
  createLegalDocumentDraft,
  legalDocumentPublicUrl,
  listLegalDocuments,
  publishLegalDocument,
} from '../../../services/coreApi.js';

const KIND_LABELS = {
  terms: 'Términos y Condiciones',
  privacy: 'Política de Privacidad',
  consent: 'Aviso de Tratamiento de Datos',
};
const KIND_ORDER = ['privacy', 'terms', 'consent'];

function emptyDraft() {
  return {
    kind: 'privacy',
    language: 'es',
    title: '',
    content_md: '',
  };
}

// Tiny Markdown preview: subset shared with backend renderer (paragraphs,
// headings, lists, **bold**, *italic*, `code`, [label](http(s)://...)). All
// inputs are HTML-escaped before transformation so the preview cannot inject
// scripts even if the admin pastes raw HTML.
function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderInline(line) {
  let out = escapeHtml(line);
  out = out.replaceAll(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replaceAll(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replaceAll(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  out = out.replaceAll(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    '<a href="$2" rel="nofollow noopener noreferrer">$1</a>');
  return out;
}

function renderPreview(md) {
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
      blocks.push(`<${list}>${items.map((it) => `<li>${renderInline(it)}</li>`).join('')}</${list}>`);
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

export function LegalModule({ module, session, tenant }) {
  const [documents, setDocuments] = useState([]);
  const [form, setForm] = useState(emptyDraft);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  async function refresh() {
    if (!tenant?.id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listLegalDocuments(session, tenant.id);
      setDocuments(Array.isArray(res?.documents) ? res.documents : []);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar los documentos legales.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  const groupedByKind = useMemo(() => {
    const out = { privacy: [], terms: [], consent: [] };
    for (const doc of documents) {
      if (out[doc.kind]) out[doc.kind].push(doc);
    }
    return out;
  }, [documents]);

  const publishedByKind = useMemo(() => {
    const out = {};
    for (const kind of KIND_ORDER) {
      out[kind] = (groupedByKind[kind] || []).find(
        (d) => d.published_at && !d.archived_at,
      );
    }
    return out;
  }, [groupedByKind]);

  async function handleSaveDraft(evt) {
    evt.preventDefault();
    if (!tenant?.id) return;
    if (!form.title.trim()) {
      setError('El título es obligatorio.');
      return;
    }
    if (!form.content_md.trim()) {
      setError('El contenido en Markdown no puede estar vacío.');
      return;
    }
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const created = await createLegalDocumentDraft(session, tenant.id, {
        kind: form.kind,
        language: (form.language || 'es').slice(0, 8),
        title: form.title.trim(),
        content_md: form.content_md,
      });
      setInfo(`Borrador v${created.version} creado. Publícalo cuando esté listo.`);
      setForm(emptyDraft());
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo crear el borrador.');
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish(doc) {
    if (!tenant?.id) return;
    if (!window.confirm(
      `¿Publicar v${doc.version} de "${doc.title}"? La versión anterior quedará archivada.`,
    )) return;
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      await publishLegalDocument(session, tenant.id, doc.id);
      setInfo(`v${doc.version} publicada. El bot ya enlaza la nueva versión.`);
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo publicar el documento.');
    } finally {
      setSaving(false);
    }
  }

  const previewHtml = renderPreview(form.content_md);

  return (
    <section className="module-card legal-module" data-module-key="legal">
      <header>
        <h2>{module?.label || 'Legal'}</h2>
        <p className="hint">{module?.summary}</p>
      </header>

      {error ? (
        <div className="callout callout-error" role="alert">{error}</div>
      ) : null}
      {info ? (
        <div className="callout callout-success" role="status">{info}</div>
      ) : null}

      <h3>Versión publicada vigente</h3>
      <ul className="legal-published-list">
        {KIND_ORDER.map((kind) => {
          const published = publishedByKind[kind];
          const link = tenant?.id ? legalDocumentPublicUrl(session, tenant.id, kind) : '';
          return (
            <li key={kind} className="legal-published-row">
              <div>
                <strong>{KIND_LABELS[kind]}</strong>{' '}
                {published ? (
                  <span className="hint">
                    v{published.version} — publicado{' '}
                    {new Date(published.published_at).toLocaleString()}
                  </span>
                ) : (
                  <span className="hint">— sin publicar —</span>
                )}
              </div>
              {published ? (
                <div className="legal-published-link">
                  <a href={link} target="_blank" rel="noreferrer">
                    Ver página pública ↗
                  </a>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      <form className="legal-form" onSubmit={handleSaveDraft} aria-label="Nuevo borrador legal">
        <h3>Nuevo borrador</h3>
        <div className="grid-3">
          <label>
            Tipo
            <select
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              {KIND_ORDER.map((k) => (
                <option key={k} value={k}>{KIND_LABELS[k]}</option>
              ))}
            </select>
          </label>
          <label>
            Idioma
            <input
              maxLength={8}
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
              placeholder="es"
            />
          </label>
          <label>
            Título
            <input
              required
              maxLength={200}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Política de Privacidad — Spa La Florida"
            />
          </label>
        </div>
        <div className="legal-editor grid-2">
          <label>
            Contenido (Markdown)
            <textarea
              required
              rows={18}
              value={form.content_md}
              onChange={(e) => setForm({ ...form, content_md: e.target.value })}
              placeholder={'# Aviso de Privacidad\n\nResponsable del tratamiento: ...'}
            />
          </label>
          <div>
            <span className="hint">Vista previa (subset Markdown, sin HTML embebido)</span>
            <div
              className="legal-preview"
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
        <div className="actions">
          <button type="submit" disabled={saving || !tenant?.id}>
            Crear borrador
          </button>
        </div>
      </form>

      <h3>Historial de versiones</h3>
      {loading ? <p>Cargando…</p> : null}
      {KIND_ORDER.map((kind) => {
        const rows = groupedByKind[kind] || [];
        if (!rows.length) return null;
        return (
          <div key={kind} className="legal-history">
            <h4>{KIND_LABELS[kind]}</h4>
            <table className="legal-history-table">
              <thead>
                <tr>
                  <th>v</th>
                  <th>Idioma</th>
                  <th>Título</th>
                  <th>Estado</th>
                  <th>Creado</th>
                  <th aria-label="acciones" />
                </tr>
              </thead>
              <tbody>
                {rows.map((doc) => {
                  let estado = 'Borrador';
                  if (doc.published_at && !doc.archived_at) estado = 'Publicado';
                  else if (doc.archived_at) estado = 'Archivado';
                  return (
                    <tr key={doc.id}>
                      <td>{doc.version}</td>
                      <td>{doc.language}</td>
                      <td>{doc.title}</td>
                      <td>{estado}</td>
                      <td>{new Date(doc.created_at).toLocaleString()}</td>
                      <td>
                        {!doc.published_at ? (
                          <button type="button" onClick={() => handlePublish(doc)} disabled={saving}>
                            Publicar
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </section>
  );
}
