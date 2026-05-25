/**
 * CalendarioLaboral — GD-UI-0059. Días festivos / no hábiles.
 *
 * Afecta cómputo de términos PQRSD (días hábiles vs corridos).
 * Permisos: CAL-001 (admin sistema).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useCalendarioLaboral, useAgregarDiaFestivo, useQuitarDiaFestivo,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function CalendarioLaboral({ session, roles = [], ...shellProps }) {
  const [anio, setAnio] = useState(() => new Date().getFullYear());
  const { data, loading, error, refresh } = useCalendarioLaboral(session, anio);
  const [showAgregar, setShowAgregar] = useState(false);
  const [quitar, setQuitar] = useState(null);
  const puedeEditar = gdCanAny(roles, 'CAL-001', 'RW');

  const festivos = data?.festivos || data?.items || (Array.isArray(data) ? data : []);

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Calendario laboral' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Calendario laboral</h1>
          <p className="subtitle">
            Días festivos y no hábiles que afectan el cómputo de términos.
          </p>
        </div>
        <div className="actions">
          <div className="field" style={{ width: 100, margin: 0 }}>
            <input type="number" className="input"
              value={anio}
              min={2020} max={2100}
              onChange={(e) => setAnio(Number(e.target.value))}
              data-testid="cal-anio"
            />
          </div>
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="cal-refresh"
          >Actualizar</button>
          {puedeEditar && (
            <button type="button" className="btn btn-accent"
              onClick={() => setShowAgregar(true)}
              data-testid="cal-agregar"
            >+ Agregar día</button>
          )}
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && festivos.length === 0 && (
        <div className="empty" data-testid="cal-empty">
          <p>No hay días no hábiles registrados para {anio}.</p>
        </div>
      )}
      {festivos.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table" data-testid="cal-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Descripción</th>
                <th>Tipo</th>
                {puedeEditar && <th>Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {festivos.map((f) => (
                <tr key={f.id || f.fecha} data-testid="cal-row">
                  <td><strong>{f.fecha}</strong></td>
                  <td>{f.descripcion}</td>
                  <td><span className="badge">{f.tipo || 'festivo'}</span></td>
                  {puedeEditar && (
                    <td>
                      <button type="button" className="btn btn-danger btn-sm"
                        onClick={() => setQuitar(f)}
                        data-testid="cal-quitar"
                      >Quitar</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAgregar && (
        <AgregarFestivoModal
          session={session} anio={anio}
          onClose={() => setShowAgregar(false)}
          onSuccess={() => { setShowAgregar(false); refresh(); }}
        />
      )}
      {quitar && (
        <QuitarFestivoModal
          session={session} festivo={quitar}
          onClose={() => setQuitar(null)}
          onSuccess={() => { setQuitar(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function AgregarFestivoModal({ session, anio, onClose, onSuccess }) {
  const [form, setForm] = useState({
    fecha: `${anio}-01-01`, descripcion: '', tipo: 'festivo',
  });
  const hook = useAgregarDiaFestivo(session);

  async function handle() {
    try {
      await hook.submit(form);
      onSuccess?.();
    } catch { /* hook */ }
  }
  const valid = form.fecha && form.descripcion.trim().length >= 2;

  return (
    <ModalShell title="Agregar día no hábil" onClose={onClose} testid="cal-agregar-modal">
      <div className="field">
        <label>Fecha <span className="req">*</span></label>
        <input type="date" className="input"
          value={form.fecha}
          onChange={(e) => setForm({ ...form, fecha: e.target.value })}
          data-testid="cal-agregar-fecha"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción <span className="req">*</span></label>
        <input className="input"
          value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          data-testid="cal-agregar-desc"
          placeholder="Día de la Independencia, p. ej."
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Tipo</label>
        <select className="select"
          value={form.tipo}
          onChange={(e) => setForm({ ...form, tipo: e.target.value })}
          data-testid="cal-agregar-tipo"
        >
          <option value="festivo">Festivo nacional</option>
          <option value="conmemoracion">Conmemoración local</option>
          <option value="institucional">Día institucional</option>
        </select>
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="cal-agregar-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function QuitarFestivoModal({ session, festivo, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useQuitarDiaFestivo(session);

  async function handle() {
    try {
      await hook.submit(festivo.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Quitar día del calendario" onClose={onClose} testid="cal-quitar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{festivo.fecha}</strong> — {festivo.descripcion}.{' '}
        Esta operación afecta cómputos futuros de términos.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo del cambio"
        id="cal-quitar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="cal-quitar-submit"
        >{hook.submitting ? 'Quitando…' : 'Quitar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div
      role="dialog" aria-modal="true" data-testid={testid}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 480, padding: 'var(--s-5)' }}>
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

export default CalendarioLaboral;
