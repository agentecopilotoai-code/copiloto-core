/**
 * AdminPerifericos — GD-UI-0087. Administración de periféricos.
 *
 * Impresoras, escáneres, lectores de código de barras autorizados
 * en la ventanilla. Estado en línea, modelo, ubicación, capacidades.
 * PER-001/002 (admin sistema).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePerifericos, useEstadoPerifericos,
  useCrearPeriferico, useActualizarPeriferico, useInactivarPeriferico,
} from './useGdPerifericos.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TIPOS = ['impresora', 'escaner', 'lector_barras', 'otro'];

export function AdminPerifericos({ session, roles = [], ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, total, loading, error, refresh } =
    usePerifericos(session, filtros);
  const estado = useEstadoPerifericos(session);
  const [modal, setModal] = useState(null);
  const puede = gdCanAny(roles, 'PER-001', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Periféricos' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Periféricos autorizados</h1>
          <p className="subtitle">
            {total} dispositivo(s) registrado(s) en el inventario de
            periféricos del módulo.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="per-refresh"
          >Actualizar</button>
          {puede && (
            <button type="button" className="btn btn-accent"
              onClick={() => setModal({ tipo: 'nuevo' })}
              data-testid="per-nuevo"
            >+ Registrar periférico</button>
          )}
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="per-no-perm">
          <div className="body">Solo administración del sistema puede gestionar periféricos.</div>
        </div>
      )}

      {puede && estado.data && (
        <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }} data-testid="per-estado">
          <div style={{ display: 'flex', gap: 'var(--s-4)', flexWrap: 'wrap' }}>
            <Kpi label="En línea" value={estado.data.en_linea ?? 0} tone="ok" />
            <Kpi label="Fuera de línea" value={estado.data.fuera_linea ?? 0}
              tone={estado.data.fuera_linea > 0 ? 'danger' : 'ok'} />
            <Kpi label="Pendientes mantenimiento" value={estado.data.mantenimiento ?? 0}
              tone={estado.data.mantenimiento > 0 ? 'warn' : 'ok'} />
          </div>
        </div>
      )}

      {puede && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--s-3)' }}>
              <div className="field">
                <label>Tipo</label>
                <select className="select"
                  value={filtros.tipo || ''}
                  onChange={(e) => update('tipo', e.target.value)}
                  data-testid="per-filter-tipo"
                >
                  <option value="">Todos</option>
                  {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Ubicación</label>
                <input className="input"
                  value={filtros.ubicacion || ''}
                  onChange={(e) => update('ubicacion', e.target.value)}
                  data-testid="per-filter-ubic"
                />
              </div>
              <div className="field">
                <label>Estado</label>
                <select className="select"
                  value={filtros.estado || ''}
                  onChange={(e) => update('estado', e.target.value)}
                  data-testid="per-filter-estado"
                >
                  <option value="">Todos</option>
                  <option value="activo">Activo</option>
                  <option value="inactivo">Inactivo</option>
                </select>
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
              <div className="empty" data-testid="per-empty" style={{ margin: 'var(--s-4)' }}>
                <p>No hay periféricos registrados con esos criterios.</p>
              </div>
            )}
            {items.length > 0 && (
              <table className="data-table" data-testid="per-table">
                <thead>
                  <tr>
                    <th>Código</th>
                    <th>Tipo</th>
                    <th>Modelo</th>
                    <th>Ubicación</th>
                    <th>Estado</th>
                    <th>En línea</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((p) => (
                    <tr key={p.id} data-testid="per-row">
                      <td><code>{p.codigo}</code></td>
                      <td>{p.tipo}</td>
                      <td>{p.modelo}</td>
                      <td>{p.ubicacion || '—'}</td>
                      <td>
                        <span className={`badge ${p.activo ? 'ok' : 'neutral'}`}>
                          {p.activo ? 'Activo' : 'Inactivo'}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${p.en_linea ? 'ok' : 'danger'}`}>
                          {p.en_linea ? '✓' : '✗'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button type="button" className="btn btn-secondary btn-sm"
                            onClick={() => setModal({ tipo: 'editar', periferico: p })}
                            data-testid="per-editar"
                          >Editar</button>
                          {p.activo && (
                            <button type="button" className="btn btn-danger btn-sm"
                              onClick={() => setModal({ tipo: 'inactivar', periferico: p })}
                              data-testid="per-inactivar"
                            >Inactivar</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {(modal?.tipo === 'nuevo' || modal?.tipo === 'editar') && (
        <FormPerifericoModal
          session={session} periferico={modal.periferico}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); estado.refresh(); }}
        />
      )}
      {modal?.tipo === 'inactivar' && (
        <InactivarPerifericoModal
          session={session} periferico={modal.periferico}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); estado.refresh(); }}
        />
      )}
    </GdShell>
  );
}

function FormPerifericoModal({ session, periferico, onClose, onSuccess }) {
  const isEdit = Boolean(periferico);
  const [form, setForm] = useState({
    codigo: periferico?.codigo || '',
    tipo: periferico?.tipo || 'impresora',
    modelo: periferico?.modelo || '',
    ubicacion: periferico?.ubicacion || '',
    descripcion: periferico?.descripcion || '',
    direccion_red: periferico?.direccion_red || '',
  });
  const crear = useCrearPeriferico(session);
  const editar = useActualizarPeriferico(session);
  const hook = isEdit ? editar : crear;

  async function handle() {
    try {
      if (isEdit) await editar.submit(periferico.id, form);
      else await crear.submit(form);
      onSuccess?.();
    } catch { /* */ }
  }
  const valid = form.codigo.trim().length >= 1 && form.modelo.trim().length >= 2;

  return (
    <ModalShell title={isEdit ? 'Editar periférico' : 'Registrar periférico'} onClose={onClose} testid="per-form-modal">
      <div className="field">
        <label>Código <span className="req">*</span></label>
        <input className="input" value={form.codigo}
          disabled={isEdit}
          onChange={(e) => setForm({ ...form, codigo: e.target.value })}
          data-testid="per-form-codigo"
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 'var(--s-3)' }}>
        <div className="field">
          <label>Tipo</label>
          <select className="select"
            value={form.tipo}
            onChange={(e) => setForm({ ...form, tipo: e.target.value })}
            data-testid="per-form-tipo"
          >
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Modelo <span className="req">*</span></label>
          <input className="input" value={form.modelo}
            onChange={(e) => setForm({ ...form, modelo: e.target.value })}
            data-testid="per-form-modelo"
          />
        </div>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Ubicación</label>
        <input className="input" value={form.ubicacion}
          onChange={(e) => setForm({ ...form, ubicacion: e.target.value })}
          data-testid="per-form-ubic"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Dirección de red / IP</label>
        <input className="input" value={form.direccion_red}
          onChange={(e) => setForm({ ...form, direccion_red: e.target.value })}
          data-testid="per-form-red"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea className="textarea" rows={2} value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          data-testid="per-form-desc"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="per-form-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function InactivarPerifericoModal({ session, periferico, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarPeriferico(session);

  async function handle() {
    try {
      await hook.submit(periferico.id, motivo);
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Inactivar periférico" onClose={onClose} testid="per-inactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{periferico.codigo}</strong> dejará de estar disponible
        para imprimir/digitalizar. Los trabajos en cola se preservan.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="per-inactivar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="per-inactivar-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi" data-testid="per-kpi" style={{ minWidth: 160 }}>
      <div className="label">{label}</div>
      <div className={`value ${tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div role="dialog" aria-modal="true" data-testid={testid}
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 540, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ModalFoot({ onClose, children }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
      <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
      {children}
    </div>
  );
}

export default AdminPerifericos;
