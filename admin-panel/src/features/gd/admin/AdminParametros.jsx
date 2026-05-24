/**
 * AdminParametros — GD-UI-0058. Parámetros del sistema GD.
 *
 * Edición inline de parámetros operativos (tiempos PQRSD, formatos,
 * cantidades, flags). PAR-001 (admin sistema).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useParametros, useActualizarParametro } from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function AdminParametros({ session, roles = [], ...shellProps }) {
  const { data, loading, error, refresh } = useParametros(session);
  const [editar, setEditar] = useState(null);
  const puedeEditar = gdCanAny(roles, 'PAR-001', 'RW');

  const items = data?.items || data?.parametros || (Array.isArray(data) ? data : []);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Parámetros del sistema' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Parámetros del sistema</h1>
          <p className="subtitle">
            Variables operativas del módulo (términos, formatos, límites).
            Los cambios quedan registrados en auditoría.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh} data-testid="par-refresh"
          >Actualizar</button>
        </div>
      </div>

      {loading && <p className="muted">Cargando parámetros…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {items.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table" data-testid="par-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th>Valor</th>
                <th>Tipo</th>
                {puedeEditar && <th>Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.codigo} data-testid="par-row">
                  <td><code>{p.codigo}</code></td>
                  <td>{p.descripcion}</td>
                  <td className="num">{String(p.valor ?? '—')}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.tipo || 'string'}</td>
                  {puedeEditar && (
                    <td>
                      <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => setEditar(p)}
                        data-testid="par-editar"
                      >Editar</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="par-empty">
          <p>No hay parámetros configurables.</p>
        </div>
      )}

      {editar && (
        <EditarParamModal
          session={session} param={editar}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function EditarParamModal({ session, param, onClose, onSuccess }) {
  const [valor, setValor] = useState(String(param.valor ?? ''));
  const hook = useActualizarParametro(session);

  async function handle() {
    try {
      const v = param.tipo === 'number' ? Number(valor)
        : param.tipo === 'boolean' ? valor === 'true'
        : valor;
      await hook.submit(param.codigo, { valor: v });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="par-editar-modal"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 480, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Editar parámetro</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          <code>{param.codigo}</code> — {param.descripcion}
        </p>
        <div className="field">
          <label>Valor ({param.tipo || 'string'})</label>
          {param.tipo === 'boolean' ? (
            <select className="select"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              data-testid="par-editar-valor"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              type={param.tipo === 'number' ? 'number' : 'text'}
              className="input" value={valor}
              onChange={(e) => setValor(e.target.value)}
              data-testid="par-editar-valor"
            />
          )}
        </div>
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-accent"
            disabled={hook.submitting} onClick={handle}
            data-testid="par-editar-submit"
          >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </div>
    </div>
  );
}

export default AdminParametros;
