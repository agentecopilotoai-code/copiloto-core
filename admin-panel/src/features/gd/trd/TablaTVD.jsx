/**
 * TablaTVD — GD-UI-0047. Tabla de Valoración Documental.
 *
 * Muestra para cada serie/subserie: tiempo de retención en Archivo de
 * Gestión (AG) y en Archivo Central (AC), disposición final
 * (CT/E/S/M) y procedimiento. Edición restringida a TRD-001 (admin
 * documental).
 *
 *   CT = Conservación total · E = Eliminación · S = Selección
 *   M = Microfilmación / digitalización
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { useTVD, useActualizarTVD } from './useGdTRD.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const DISPOSICIONES = [
  { v: 'CT', l: 'Conservación total' },
  { v: 'E', l: 'Eliminación' },
  { v: 'S', l: 'Selección' },
  { v: 'M', l: 'Microfilm./Digit.' },
];

export function TablaTVD({ session, roles = [], ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, loading, error, refresh } = useTVD(session, filtros);
  const [editando, setEditando] = useState(null);
  const puedeEditar = gdCanAny(roles, 'TRD-001', 'RW');

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'TVD' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Tabla de Valoración Documental</h1>
          <p className="subtitle">
            Tiempos de retención por serie/subserie y disposición final.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="tvd-refresh"
          >Actualizar</button>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div className="field">
          <label>Buscar por serie / subserie</label>
          <input
            className="input"
            value={filtros.q || ''}
            onChange={(e) => setFiltros({ ...filtros, q: e.target.value || undefined })}
            data-testid="tvd-filter-q"
          />
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
          <div className="empty" data-testid="tvd-empty" style={{ margin: 'var(--s-4)' }}>
            <p>Sin filas de TVD registradas.</p>
          </div>
        )}
        {items.length > 0 && (
          <table className="data-table" data-testid="tvd-table">
            <thead>
              <tr>
                <th>Serie</th>
                <th>Subserie</th>
                <th>AG (años)</th>
                <th>AC (años)</th>
                <th>Disposición</th>
                <th>Procedimiento</th>
                {puedeEditar && <th>Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} data-testid="tvd-row">
                  <td>{r.serie_codigo} {r.serie_nombre && `— ${r.serie_nombre}`}</td>
                  <td>{r.subserie_codigo || '—'}</td>
                  <td className="num">{r.retencion_ag ?? '—'}</td>
                  <td className="num">{r.retencion_ac ?? '—'}</td>
                  <td>
                    <span className="badge">{r.disposicion || '—'}</span>
                  </td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {r.procedimiento || '—'}
                  </td>
                  {puedeEditar && (
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setEditando(r)}
                        data-testid="tvd-editar"
                      >Editar</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editando && (
        <EditarTVDModal
          session={session}
          fila={editando}
          onClose={() => setEditando(null)}
          onSuccess={() => { setEditando(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function EditarTVDModal({ session, fila, onClose, onSuccess }) {
  const [form, setForm] = useState({
    retencion_ag: fila.retencion_ag ?? '',
    retencion_ac: fila.retencion_ac ?? '',
    disposicion: fila.disposicion || 'CT',
    procedimiento: fila.procedimiento || '',
  });
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const hook = useActualizarTVD(session);

  async function handle() {
    try {
      await hook.submit(fila.id, {
        retencion_ag: form.retencion_ag === '' ? null : Number(form.retencion_ag),
        retencion_ac: form.retencion_ac === '' ? null : Number(form.retencion_ac),
        disposicion: form.disposicion,
        procedimiento: form.procedimiento,
        motivo,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="tvd-editar-modal"
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: 520, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Editar TVD — {fila.serie_codigo}</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="field">
            <label>Retención AG (años)</label>
            <input type="number" className="input"
              value={form.retencion_ag}
              onChange={(e) => setForm({ ...form, retencion_ag: e.target.value })}
              data-testid="tvd-ag" />
          </div>
          <div className="field">
            <label>Retención AC (años)</label>
            <input type="number" className="input"
              value={form.retencion_ac}
              onChange={(e) => setForm({ ...form, retencion_ac: e.target.value })}
              data-testid="tvd-ac" />
          </div>
        </div>
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Disposición final</label>
          <select className="select"
            value={form.disposicion}
            onChange={(e) => setForm({ ...form, disposicion: e.target.value })}
            data-testid="tvd-disposicion"
          >
            {DISPOSICIONES.map((d) => (
              <option key={d.v} value={d.v}>{d.v} — {d.l}</option>
            ))}
          </select>
        </div>
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Procedimiento</label>
          <textarea className="textarea" rows={2}
            value={form.procedimiento}
            onChange={(e) => setForm({ ...form, procedimiento: e.target.value })}
            data-testid="tvd-proc" />
        </div>
        <div style={{ marginTop: 'var(--s-3)' }}>
          <JustificacionRequiredField
            value={motivo}
            onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
            label="Motivo del cambio (auditable)"
            id="tvd-motivo"
          />
        </div>
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-accent"
            disabled={!motivoValid || hook.submitting} onClick={handle}
            data-testid="tvd-editar-submit"
          >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </div>
    </div>
  );
}

export default TablaTVD;
