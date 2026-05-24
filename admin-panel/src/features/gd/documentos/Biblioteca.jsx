/**
 * Biblioteca — GD-UI-0035. Lista filtrable de documentos.
 *
 * Filtros: tipo, estado, autor, fecha desde/hasta, búsqueda.
 * Click en fila → ficha del documento.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useDocumentosList } from './useGdDocumentos.js';
import { CargarDocumentoModal } from './CargarDocumentoModal.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const ESTADOS = ['', 'borrador', 'revisado', 'aprobado', 'firmado', 'anulado'];

export function Biblioteca({ session, roles = [], onNavigate, ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const [showCargar, setShowCargar] = useState(false);
  const { items, total, loading, error, refresh } =
    useDocumentosList(session, filtros);
  const puedeCargar = gdCanAny(roles, 'DOC-001', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Biblioteca' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Biblioteca de documentos</h1>
          <p className="subtitle">
            {total} documento(s). Cada documento referencia un archivo
            digital del repositorio compartido.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="bib-refresh"
          >Actualizar</button>
          {puedeCargar && (
            <button
              type="button"
              className="btn btn-accent"
              onClick={() => setShowCargar(true)}
              data-testid="bib-cargar"
            >+ Cargar documento</button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--s-3)',
          }}
        >
          <div className="field">
            <label>Búsqueda</label>
            <input
              type="search"
              className="input"
              value={filtros.q || ''}
              onChange={(e) => update('q', e.target.value)}
              placeholder="Título o palabras clave…"
              data-testid="bib-filter-q"
            />
          </div>
          <div className="field">
            <label>Tipo</label>
            <input
              className="input"
              value={filtros.tipo || ''}
              onChange={(e) => update('tipo', e.target.value)}
              data-testid="bib-filter-tipo"
            />
          </div>
          <div className="field">
            <label>Estado</label>
            <select
              className="select"
              value={filtros.estado || ''}
              onChange={(e) => update('estado', e.target.value)}
              data-testid="bib-filter-estado"
            >
              {ESTADOS.map((e) => (
                <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Desde</label>
            <input
              type="date"
              className="input"
              value={filtros.fecha_desde || ''}
              onChange={(e) => update('fecha_desde', e.target.value)}
              data-testid="bib-filter-desde"
            />
          </div>
          <div className="field">
            <label>Hasta</label>
            <input
              type="date"
              className="input"
              value={filtros.fecha_hasta || ''}
              onChange={(e) => update('fecha_hasta', e.target.value)}
              data-testid="bib-filter-hasta"
            />
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="bib-empty" style={{ margin: 'var(--s-4)' }}>
            <p>Sin documentos con esos criterios.</p>
          </div>
        )}
        {items.length > 0 && (
          <table className="data-table" data-testid="bib-table">
            <thead>
              <tr>
                <th>Título</th>
                <th>Tipo</th>
                <th>Versión</th>
                <th>Estado</th>
                <th>Autor</th>
                <th>Modificado</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr
                  key={d.id}
                  data-testid="bib-row"
                  onClick={() => onNavigate?.(`/gd/documentos/${d.id}`)}
                >
                  <td>{d.titulo}</td>
                  <td>{d.tipo}</td>
                  <td className="num">v{d.version_actual}</td>
                  <td>
                    <span className={`badge ${badgeTone(d.estado)}`}>{d.estado}</span>
                  </td>
                  <td>{d.autor_nombre || '—'}</td>
                  <td>{fmtFecha(d.updated_at || d.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCargar && (
        <CargarDocumentoModal
          session={session}
          onClose={() => setShowCargar(false)}
          onSuccess={() => { setShowCargar(false); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function badgeTone(estado) {
  if (estado === 'aprobado' || estado === 'firmado') return 'ok';
  if (estado === 'anulado') return 'danger';
  if (estado === 'borrador') return 'neutral';
  return 'info';
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch { return iso; }
}

export default Biblioteca;
