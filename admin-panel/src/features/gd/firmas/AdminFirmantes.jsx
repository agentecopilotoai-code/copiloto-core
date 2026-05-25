/**
 * AdminFirmantes — GD-UI-0044. Configuración de firmantes autorizados.
 *
 * Solo Admin Sistema (FIR-005). Permite registrar quiénes pueden firmar
 * documentos institucionales, su cargo, alcance (tipos documentales
 * habilitados) y vigencia.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useFirmantesAutorizados,
  useCrearFirmanteAutorizado,
  useActualizarFirmanteAutorizado,
  useInactivarFirmanteAutorizado,
} from './useGdFirmas.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function AdminFirmantes({ session, roles = [], ...shellProps }) {
  const { items, loading, error, refresh } = useFirmantesAutorizados(session);
  const [showNuevo, setShowNuevo] = useState(false);
  const [editar, setEditar] = useState(null);
  const [inactivar, setInactivar] = useState(null);
  const puedeAdmin = gdCanAny(roles, 'FIR-005', 'RW');

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Firmantes autorizados' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Firmantes autorizados</h1>
          <p className="subtitle">
            {items.length} firmante(s) registrado(s). Solo personas en este
            registro pueden firmar documentos institucionales.
          </p>
        </div>
        <div className="actions">
          {puedeAdmin && (
            <button
              type="button"
              className="btn btn-accent"
              onClick={() => setShowNuevo(true)}
              data-testid="firmantes-nuevo"
            >+ Registrar firmante</button>
          )}
        </div>
      </div>

      {!puedeAdmin && (
        <div className="alert warning" role="alert" data-testid="firmantes-no-perm">
          <div className="body">Solo administración del sistema puede configurar firmantes.</div>
        </div>
      )}

      {puedeAdmin && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
          {error && (
            <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
              <div className="body">{error.message || 'Error.'}</div>
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <div className="empty" data-testid="firmantes-empty" style={{ margin: 'var(--s-4)' }}>
              <p>Aún no se han registrado firmantes autorizados.</p>
            </div>
          )}
          {items.length > 0 && (
            <table className="data-table" data-testid="firmantes-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Cargo</th>
                  <th>Dependencia</th>
                  <th>Tipos habilitados</th>
                  <th>Vigencia</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map((f) => (
                  <tr key={f.id} data-testid="firmantes-row">
                    <td>{f.nombre}</td>
                    <td>{f.cargo}</td>
                    <td>{f.dependencia_nombre || '—'}</td>
                    <td className="muted" style={{ fontSize: 12 }}>
                      {(f.tipos_habilitados || []).join(', ') || 'Todos'}
                    </td>
                    <td>{fmtVigencia(f.vigente_desde, f.vigente_hasta)}</td>
                    <td>
                      <span className={`badge ${f.activo ? 'ok' : 'neutral'}`}>
                        {f.activo ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setEditar(f)}
                          data-testid="firmantes-edit"
                        >Editar</button>
                        {f.activo && (
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => setInactivar(f)}
                            data-testid="firmantes-inactivar"
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
      )}

      {showNuevo && (
        <FormFirmante
          session={session}
          onClose={() => setShowNuevo(false)}
          onSuccess={() => { setShowNuevo(false); refresh(); }}
        />
      )}
      {editar && (
        <FormFirmante
          session={session}
          firmante={editar}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
      {inactivar && (
        <InactivarFirmante
          session={session}
          firmante={inactivar}
          onClose={() => setInactivar(null)}
          onSuccess={() => { setInactivar(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function FormFirmante({ session, firmante, onClose, onSuccess }) {
  const isEdit = Boolean(firmante);
  const [form, setForm] = useState({
    nombre: firmante?.nombre || '',
    cargo: firmante?.cargo || '',
    dependencia_id: firmante?.dependencia_id || '',
    tipos_habilitados: (firmante?.tipos_habilitados || []).join(', '),
    vigente_desde: firmante?.vigente_desde?.slice(0, 10) || '',
    vigente_hasta: firmante?.vigente_hasta?.slice(0, 10) || '',
  });
  const crear = useCrearFirmanteAutorizado(session);
  const editar = useActualizarFirmanteAutorizado(session);
  const hook = isEdit ? editar : crear;

  function update(k, v) { setForm((p) => ({ ...p, [k]: v })); }

  async function handle() {
    const payload = {
      ...form,
      tipos_habilitados: form.tipos_habilitados
        .split(',').map((s) => s.trim()).filter(Boolean),
    };
    try {
      if (isEdit) await editar.submit(firmante.id, payload);
      else await crear.submit(payload);
      onSuccess?.();
    } catch { /* hook */ }
  }

  const valid = form.nombre.trim().length >= 2 && form.cargo.trim().length >= 2;

  return (
    <div
      className="modal-overlay" role="dialog" aria-modal="true"
      data-testid="firmantes-form-modal"
    >
      <div className="modal-panel" style={{ maxWidth: 560 }}>
        <header className="modal-head">
          <h2>{isEdit ? 'Editar firmante' : 'Registrar firmante'}</h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className="modal-body">
          <div className="field">
            <label>Nombre completo <span className="req">*</span></label>
            <input
              className="input"
              value={form.nombre}
              onChange={(e) => update('nombre', e.target.value)}
              data-testid="firmantes-form-nombre"
            />
          </div>
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>Cargo <span className="req">*</span></label>
            <input
              className="input"
              value={form.cargo}
              onChange={(e) => update('cargo', e.target.value)}
              data-testid="firmantes-form-cargo"
            />
          </div>
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>ID Dependencia</label>
            <input
              className="input"
              value={form.dependencia_id}
              onChange={(e) => update('dependencia_id', e.target.value)}
              data-testid="firmantes-form-dep"
            />
          </div>
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>Tipos habilitados (separados por coma)</label>
            <input
              className="input"
              value={form.tipos_habilitados}
              onChange={(e) => update('tipos_habilitados', e.target.value)}
              data-testid="firmantes-form-tipos"
              placeholder="oficio, resolucion, …"
            />
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 'var(--s-3)' }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Vigente desde</label>
              <input
                type="date" className="input"
                value={form.vigente_desde}
                onChange={(e) => update('vigente_desde', e.target.value)}
                data-testid="firmantes-form-desde"
              />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Vigente hasta</label>
              <input
                type="date" className="input"
                value={form.vigente_hasta}
                onChange={(e) => update('vigente_hasta', e.target.value)}
                data-testid="firmantes-form-hasta"
              />
            </div>
          </div>
          {hook.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{hook.error.message || 'Error.'}</div>
            </div>
          )}
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="btn btn-accent"
            disabled={!valid || hook.submitting}
            onClick={handle}
            data-testid="firmantes-form-submit"
          >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
        </footer>
      </div>
    </div>
  );
}

function InactivarFirmante({ session, firmante, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarFirmanteAutorizado(session);

  async function handle() {
    try {
      await hook.submit(firmante.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      className="modal-overlay" role="dialog" aria-modal="true"
      data-testid="firmantes-inactivar-modal"
    >
      <div className="modal-panel" style={{ maxWidth: 480 }}>
        <header className="modal-head">
          <h2>Inactivar firmante</h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className="modal-body">
          <p className="muted" style={{ fontSize: 13 }}>
            <strong>{firmante.nombre}</strong> dejará de aparecer en las
            asignaciones de firma. Las firmas previas se conservan.
          </p>
          <JustificacionRequiredField
            value={motivo}
            onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
            label="Motivo de inactivación"
            id="firmantes-inactivar-motivo"
          />
          {hook.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{hook.error.message || 'Error.'}</div>
            </div>
          )}
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="btn btn-danger-solid"
            disabled={!valid || hook.submitting}
            onClick={handle}
            data-testid="firmantes-inactivar-submit"
          >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
        </footer>
      </div>
    </div>
  );
}

function fmtVigencia(desde, hasta) {
  const d = desde ? new Date(desde).toLocaleDateString('es-CO') : '—';
  const h = hasta ? new Date(hasta).toLocaleDateString('es-CO') : '—';
  return `${d} → ${h}`;
}

export default AdminFirmantes;
