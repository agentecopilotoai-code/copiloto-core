/**
 * BusquedaSemantica — GD-UI-0074. Búsqueda semántica de
 * documentos vía embeddings IA-003.
 *
 * Vista standalone (página) — input query + filtros opcionales,
 * lista de resultados con score, fragmento resaltado, click para
 * abrir documento. Feedback "útil / no útil" por resultado para
 * refinar el modelo.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useBusquedaSemantica, useFeedbackBusqueda,
} from './useGdIa.js';

export function BusquedaSemantica({
  session, roles = [], onNavigate, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'IA-003', 'R') ||
    gdCanAny(roles, 'IA-003', 'RW');
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState('todos');
  const [topK, setTopK] = useState(10);
  const b = useBusquedaSemantica(session);
  const fb = useFeedbackBusqueda(session);
  const [feedbackPorDoc, setFeedbackPorDoc] = useState({});

  async function buscar(e) {
    e?.preventDefault?.();
    if (!query.trim()) return;
    try {
      await b.submit({ query: query.trim(), scope, top_k: topK });
    } catch (_) { /* mostrado */ }
  }

  async function votar(documentoId, util) {
    setFeedbackPorDoc((m) => ({ ...m, [documentoId]: util ? 'pos' : 'neg' }));
    try {
      await fb.submit({
        query: b.lastQuery, documento_id: documentoId, util,
      });
    } catch (_) {
      setFeedbackPorDoc((m) => {
        const c = { ...m }; delete c[documentoId]; return c;
      });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Búsqueda semántica' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Búsqueda semántica</h1>
          <p className="subtitle">
            Busca documentos por significado, no solo palabras
            exactas. Resultados ordenados por relevancia con
            citas y fragmentos.
          </p>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="ia-bs-no-perm"
        >
          <div className="body">
            No tienes permiso para usar búsqueda semántica.
          </div>
        </div>
      )}

      {tienePermiso && (
        <form onSubmit={buscar} className="card"
          style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}
          data-testid="ia-bs-form"
        >
          <div style={{ display: 'flex', gap: 'var(--s-2)',
            flexWrap: 'wrap', alignItems: 'flex-end' }}
          >
            <div style={{ flex: 1, minWidth: 280 }}>
              <label htmlFor="ia-bs-q" style={{ fontSize: 12 }}>
                ¿Qué buscas?
              </label>
              <input id="ia-bs-q" type="text"
                value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Ej. políticas internas sobre licencias remotas 2025"
                data-testid="ia-bs-query"
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label htmlFor="ia-bs-scope" style={{ fontSize: 12 }}>
                Ámbito
              </label>
              <select id="ia-bs-scope" value={scope}
                onChange={(e) => setScope(e.target.value)}
                data-testid="ia-bs-scope"
              >
                <option value="todos">Todos</option>
                <option value="mi_dependencia">Mi dependencia</option>
                <option value="mis_expedientes">Mis expedientes</option>
              </select>
            </div>
            <div>
              <label htmlFor="ia-bs-k" style={{ fontSize: 12 }}>
                Top K
              </label>
              <input id="ia-bs-k" type="number" min={1} max={50}
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value, 10) || 10)}
                style={{ width: 80 }}
                data-testid="ia-bs-topk"
              />
            </div>
            <button type="submit" className="btn btn-primary"
              disabled={b.loading || !query.trim()}
              data-testid="ia-bs-submit"
            >{b.loading ? 'Buscando…' : 'Buscar'}</button>
          </div>
        </form>
      )}

      {b.error && (
        <div className="alert danger" role="alert"
          data-testid="ia-bs-error"
        >
          <div className="body">
            {b.error.code === 'ia_budget_exceeded'
              ? 'Presupuesto IA agotado.'
              : (b.error.message || 'Error en búsqueda.')}
          </div>
        </div>
      )}

      {b.resultados.length > 0 && (
        <div data-testid="ia-bs-resultados">
          <div style={{ fontSize: 12, color: 'var(--c-muted)',
            marginBottom: 'var(--s-2)' }}
          >
            {b.resultados.length} resultados ·
            modelo: <code>{b.modelo || '?'}</code> ·
            tokens: {b.tokens}
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {b.resultados.map((r, i) => (
              <li key={r.documento_id || i} className="card"
                data-testid="ia-bs-item"
                style={{ padding: 'var(--s-3)', marginBottom: 'var(--s-2)' }}
              >
                <div style={{ display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline', gap: 'var(--s-2)' }}
                >
                  <a href="#" onClick={(e) => {
                    e.preventDefault();
                    onNavigate?.(`/gd/documentos/${r.documento_id}`);
                  }}
                    data-testid="ia-bs-item-link"
                  >
                    <strong>{r.titulo || r.documento_id}</strong>
                  </a>
                  <span className="badge" data-testid="ia-bs-item-score">
                    {((r.score ?? 0) * 100).toFixed(0)}%
                  </span>
                </div>
                {r.fragmento && (
                  <p style={{ fontSize: 13, marginTop: 'var(--s-1)',
                    color: 'var(--c-muted)' }}
                  >…{r.fragmento}…</p>
                )}
                {r.entidad && (
                  <small className="muted">{r.entidad}</small>
                )}
                <div style={{ display: 'flex', gap: 'var(--s-2)',
                  marginTop: 'var(--s-2)' }}
                >
                  <button type="button" className="btn btn-sm btn-secondary"
                    onClick={() => votar(r.documento_id, true)}
                    disabled={!!feedbackPorDoc[r.documento_id]}
                    data-testid="ia-bs-vote-up"
                  >
                    {feedbackPorDoc[r.documento_id] === 'pos' ? '✅ Útil' : '👍 Útil'}
                  </button>
                  <button type="button" className="btn btn-sm btn-secondary"
                    onClick={() => votar(r.documento_id, false)}
                    disabled={!!feedbackPorDoc[r.documento_id]}
                    data-testid="ia-bs-vote-down"
                  >
                    {feedbackPorDoc[r.documento_id] === 'neg' ? '❌ No útil' : '👎 No útil'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {b.lastQuery && b.resultados.length === 0 && !b.loading && !b.error && (
        <div className="empty" data-testid="ia-bs-empty">
          <p className="muted">
            Sin resultados para “{b.lastQuery}”. Intenta términos
            más generales o cambia el ámbito.
          </p>
        </div>
      )}
    </GdShell>
  );
}

export default BusquedaSemantica;
