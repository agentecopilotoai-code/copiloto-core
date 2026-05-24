/**
 * Integraciones — GD-UI-0063. Configuración de integraciones externas.
 *
 * Correo institucional, SMS, firmadigital, etc. Permite probar
 * conectividad. INT-001 (admin sistema).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useIntegraciones, useActualizarIntegracion, useProbarIntegracion,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function Integraciones({ session, roles = [], ...shellProps }) {
  const { items, loading, error, refresh } = useIntegraciones(session);
  const [editar, setEditar] = useState(null);
  const [probarInfo, setProbarInfo] = useState(null);
  const probar = useProbarIntegracion(session);
  const puedeEditar = gdCanAny(roles, 'INT-001', 'RW');

  async function handleProbar(codigo) {
    setProbarInfo(null);
    try {
      const r = await probar.submit(codigo);
      setProbarInfo({ ok: true, codigo, ...r });
    } catch (err) {
      setProbarInfo({ ok: false, codigo, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Integraciones' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Integraciones externas</h1>
          <p className="subtitle">
            {items.length} integración(es) configurada(s) con sistemas
            externos (correo, SMS, firma, etc).
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="int-refresh"
          >Actualizar</button>
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="int-empty">
          <p>No hay integraciones configuradas.</p>
        </div>
      )}
      {items.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table" data-testid="int-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Tipo</th>
                <th>Estado</th>
                <th>Última prueba</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.codigo} data-testid="int-row">
                  <td><code>{i.codigo}</code></td>
                  <td>{i.nombre}</td>
                  <td><span className="badge">{i.tipo}</span></td>
                  <td>
                    <span className={`badge ${i.activa ? 'ok' : 'neutral'}`}>
                      {i.activa ? 'Activa' : 'Inactiva'}
                    </span>
                  </td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {i.ultima_prueba || '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => handleProbar(i.codigo)}
                        disabled={probar.submitting}
                        data-testid="int-probar"
                      >Probar</button>
                      {puedeEditar && (
                        <button type="button" className="btn btn-secondary btn-sm"
                          onClick={() => setEditar(i)}
                          data-testid="int-editar"
                        >Configurar</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {probarInfo && (
        <div
          className={`alert ${probarInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="int-prueba-info"
          style={{ marginTop: 'var(--s-3)' }}
        >
          <div className="body">
            {probarInfo.ok
              ? <>Prueba de <strong>{probarInfo.codigo}</strong> exitosa.</>
              : <>Prueba de <strong>{probarInfo.codigo}</strong> falló:{' '}
                  {probarInfo.error?.message || 'error desconocido'}.</>
            }
          </div>
        </div>
      )}

      {editar && (
        <EditarIntegracionModal
          session={session} integracion={editar}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function EditarIntegracionModal({ session, integracion, onClose, onSuccess }) {
  const [form, setForm] = useState({
    activa: integracion.activa !== false,
    config_json: JSON.stringify(integracion.config || {}, null, 2),
  });
  const hook = useActualizarIntegracion(session);
  const [jsonError, setJsonError] = useState(null);

  async function handle() {
    setJsonError(null);
    let parsed;
    try {
      parsed = JSON.parse(form.config_json || '{}');
    } catch (err) {
      setJsonError(err.message);
      return;
    }
    try {
      await hook.submit(integracion.codigo, {
        activa: form.activa,
        config: parsed,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="int-editar-modal"
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 560, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>
          Configurar {integracion.nombre || integracion.codigo}
        </h2>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox" checked={form.activa}
            onChange={(e) => setForm({ ...form, activa: e.target.checked })}
            data-testid="int-activa"
          /> Activa
        </label>
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Configuración (JSON)</label>
          <textarea className="textarea" rows={10}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            value={form.config_json}
            onChange={(e) => setForm({ ...form, config_json: e.target.value })}
            data-testid="int-config-json"
          />
          {jsonError && (
            <p style={{ color: 'var(--red-700)', fontSize: 12 }}
              data-testid="int-json-err"
            >JSON inválido: {jsonError}</p>
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
            data-testid="int-editar-submit"
          >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </div>
    </div>
  );
}

export default Integraciones;
