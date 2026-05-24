/**
 * BusquedaSemantica — GD-UI-0074. Búsqueda semántica de documentos.
 *
 * El usuario pregunta en lenguaje natural; el backend retorna
 * documentos relevantes con score + fragmento + cita. IA-003.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useBusquedaSemanticaIA } from './useGdIA.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const SCOPES = [
  { v: '', l: 'Toda la entidad' },
  { v: 'mi_dependencia', l: 'Mi dependencia' },
  { v: 'mis_documentos', l: 'Mis documentos' },
];

export function BusquedaSemantica({ session, roles = [], onNavigate, ...shellProps }) {
  const { items, query, loading, error, ran, buscar } =
    useBusquedaSemanticaIA(session);
  const [q, setQ] = useState('');
  const [scope, setScope] = useState('');
  const puede = gdCanAny(roles, 'IA-003', 'R');

  function ejecutar(e) {
    e?.preventDefault?.();
    if (!q.trim()) return;
    buscar({ q: q.trim(), scope: scope || undefined, limit: 20 });
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
            Encuentre documentos por significado, no solo por palabras
            exactas. La IA respeta sus permisos rol-aware.
          </p>
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="iabs-no-perm">
          <div className="body">No tiene permisos para usar búsqueda semántica.</div>
        </div>
      )}

      {puede && (
        <>
          <form
            className="card"
            style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}
            onSubmit={ejecutar}
            data-testid="iabs-form"
          >
            <div className="field">
              <label>Consulta en lenguaje natural</label>
              <input
                type="search" className="input"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ej: contratos de prestación de servicios firmados en 2026"
                data-testid="iabs-q"
              />
            </div>
            <div style={{ display: 'flex', gap: 'var(--s-3)', marginTop: 'var(--s-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Alcance</label>
                <select className="select"
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                  data-testid="iabs-scope"
                >
                  {SCOPES.map((s) => (
                    <option key={s.v} value={s.v}>{s.l}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button type="submit" className="btn btn-accent"
                  disabled={loading || !q.trim()}
                  data-testid="iabs-submit"
                >{loading ? 'Buscando…' : 'Buscar'}</button>
              </div>
            </div>
          </form>

          {error && (
            <div className="alert danger" role="alert">
              <div className="body">{error.message || 'Error al consultar IA.'}</div>
            </div>
          )}

          {ran && !loading && !error && items.length === 0 && (
            <div className="empty" data-testid="iabs-empty">
              <p>Sin resultados para "{query}".</p>
            </div>
          )}

          {items.length > 0 && (
            <>
              <p className="muted" style={{ fontSize: 12 }}>
                {items.length} resultado(s) — ordenados por relevancia semántica.
              </p>
              <div data-testid="iabs-resultados">
                {items.map((r) => (
                  <div
                    key={r.id || r.documento_id}
                    className="card"
                    style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-3)', cursor: 'pointer' }}
                    onClick={() => onNavigate?.(`/gd/documentos/${r.documento_id || r.id}`)}
                    data-testid="iabs-resultado"
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <strong style={{ fontSize: 14 }}>{r.titulo}</strong>
                      <span className="muted" style={{ fontSize: 12 }}>
                        score: <strong>{fmtScore(r.score)}</strong>
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {r.tipo} · {r.fecha || r.created_at}
                    </div>
                    {r.fragmento && (
                      <p style={{ fontSize: 13, marginTop: 6, fontStyle: 'italic' }}
                        data-testid="iabs-fragmento">
                        "{r.fragmento}"
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </GdShell>
  );
}

function fmtScore(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(1)}`;
  return v.toFixed(1);
}

export default BusquedaSemantica;
