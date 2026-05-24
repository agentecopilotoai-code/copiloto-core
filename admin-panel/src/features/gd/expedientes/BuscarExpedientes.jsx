/**
 * BuscarExpedientes — GD-UI-0051. Búsqueda de expedientes por filtros.
 *
 * Filtros: serie/subserie + texto + dependencia + estado + rango de
 * fechas (apertura). Resultados con paginación implícita via backend.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useTRD } from '../trd/useGdTRD.js';
import { useBuscarExpedientes } from './useGdExpedientes.js';

const ESTADOS = ['', 'abierto', 'cerrado', 'transferido'];

export function BuscarExpedientes({ session, onNavigate, ...shellProps }) {
  const [form, setForm] = useState({});
  const { items, total, loading, error, ran, buscar } =
    useBuscarExpedientes(session);
  const { items: series } = useTRD(session);

  function update(k, v) { setForm((p) => ({ ...p, [k]: v || undefined })); }

  function ejecutar(e) {
    e?.preventDefault?.();
    buscar(form);
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Buscar expedientes' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Buscar expedientes</h1>
          <p className="subtitle">
            Consulta de expedientes electrónicos abiertos, cerrados o
            transferidos.
          </p>
        </div>
      </div>

      <form className="card"
        style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}
        onSubmit={ejecutar}
        data-testid="exp-buscar-form"
      >
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 'var(--s-3)',
        }}>
          <div className="field">
            <label>Texto libre</label>
            <input
              className="input"
              value={form.q || ''}
              onChange={(e) => update('q', e.target.value)}
              placeholder="Título o código…"
              data-testid="exp-buscar-q"
            />
          </div>
          <div className="field">
            <label>Serie</label>
            <select
              className="select"
              value={form.serie_id || ''}
              onChange={(e) => update('serie_id', e.target.value)}
              data-testid="exp-buscar-serie"
            >
              <option value="">— Todas —</option>
              {series.map((s) => (
                <option key={s.id} value={s.id}>{s.codigo} — {s.nombre}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Estado</label>
            <select
              className="select"
              value={form.estado || ''}
              onChange={(e) => update('estado', e.target.value)}
              data-testid="exp-buscar-estado"
            >
              {ESTADOS.map((e) => (
                <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Dependencia</label>
            <input
              className="input"
              value={form.dependencia || ''}
              onChange={(e) => update('dependencia', e.target.value)}
              data-testid="exp-buscar-dep"
            />
          </div>
          <div className="field">
            <label>Apertura desde</label>
            <input
              type="date" className="input"
              value={form.apertura_desde || ''}
              onChange={(e) => update('apertura_desde', e.target.value)}
              data-testid="exp-buscar-desde"
            />
          </div>
          <div className="field">
            <label>Apertura hasta</label>
            <input
              type="date" className="input"
              value={form.apertura_hasta || ''}
              onChange={(e) => update('apertura_hasta', e.target.value)}
              data-testid="exp-buscar-hasta"
            />
          </div>
        </div>
        <div style={{ marginTop: 'var(--s-3)', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="submit"
            className="btn btn-accent"
            disabled={loading}
            data-testid="exp-buscar-submit"
          >{loading ? 'Buscando…' : 'Buscar'}</button>
        </div>
      </form>

      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'No se pudo realizar la búsqueda.'}</div>
        </div>
      )}

      {ran && !loading && !error && items.length === 0 && (
        <div className="empty" data-testid="exp-buscar-empty">
          <p>Sin expedientes con esos criterios.</p>
        </div>
      )}

      {items.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <p className="muted" style={{ padding: 'var(--s-3) var(--s-4)', margin: 0 }}>
            {total} resultado(s).
          </p>
          <table className="data-table" data-testid="exp-buscar-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Título</th>
                <th>Serie</th>
                <th>Dependencia</th>
                <th>Estado</th>
                <th>Apertura</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr
                  key={e.id}
                  data-testid="exp-buscar-row"
                  onClick={() => onNavigate?.(`/gd/expedientes/${e.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{e.codigo}</td>
                  <td>{e.titulo}</td>
                  <td>{e.serie_codigo || '—'}</td>
                  <td>{e.dependencia_nombre || '—'}</td>
                  <td><span className="badge">{e.estado}</span></td>
                  <td>{fmt(e.fecha_apertura)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </GdShell>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-CO'); }
  catch { return iso; }
}

export default BuscarExpedientes;
