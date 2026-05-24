/**
 * Alertas — GD-UI-0084/0085/0086.
 *
 * Tabs:
 *  - Mis alertas: alertas operacionales (vencimientos PQRSD, plazos,
 *    sobrecargas de buzón). Atender con motivo.
 *  - Reglas: configurar reglas de generación de alertas (umbral +
 *    severidad + destinatarios). Solo admin sistema/PQRSD.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useAlertas, useAtenderAlerta,
  useReglasAlerta, useCrearReglaAlerta,
  useActualizarReglaAlerta, useInactivarReglaAlerta,
} from './useGdComunicaciones.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS_BASE = ['Mis alertas'];
const TIPOS = [
  'pqrsd_vencimiento', 'buzon_sobrecarga', 'documento_sin_firmar',
  'expediente_inactivo', 'integracion_caida', 'otro',
];

export function Alertas({ session, roles = [], ...shellProps }) {
  const puedeConfig = gdCanAny(roles, 'ALERTA-002', 'RW');
  const tabs = puedeConfig ? [...TABS_BASE, 'Reglas'] : TABS_BASE;
  const [tab, setTab] = useState('Mis alertas');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Alertas' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Alertas operacionales</h1>
          <p className="subtitle">
            Alertas generadas automáticamente por reglas de operación
            (vencimientos, sobrecargas, fallas).
          </p>
        </div>
      </div>

      <nav className="tabs" data-testid="alerta-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t} role="tab"
            aria-selected={tab === t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
            data-testid={`alerta-tab-btn-${t}`}
          >{t}</button>
        ))}
      </nav>

      <div className="card" style={{ padding: 'var(--s-5)' }}>
        {tab === 'Mis alertas' && <MisAlertas session={session} roles={roles} />}
        {tab === 'Reglas' && puedeConfig && <ReglasAlertas session={session} />}
      </div>
    </GdShell>
  );
}

function MisAlertas({ session, roles }) {
  const [filtros, setFiltros] = useState({ estado: 'pendiente' });
  const { items, total, loading, error, refresh } = useAlertas(session, filtros);
  const [atender, setAtender] = useState(null);
  const puede = gdCanAny(roles, 'ALERTA-001', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <div data-testid="alerta-mis">
      <div className="muted" style={{ fontSize: 12, marginBottom: 'var(--s-3)' }}>
        {total} alerta(s) — filtros activos.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--s-3)', marginBottom: 'var(--s-3)' }}>
        <div className="field">
          <label>Tipo</label>
          <select className="select"
            value={filtros.tipo || ''}
            onChange={(e) => update('tipo', e.target.value)}
            data-testid="alerta-filter-tipo"
          >
            <option value="">Todos</option>
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Estado</label>
          <select className="select"
            value={filtros.estado || ''}
            onChange={(e) => update('estado', e.target.value)}
            data-testid="alerta-filter-estado"
          >
            <option value="">Todos</option>
            <option value="pendiente">Pendiente</option>
            <option value="atendida">Atendida</option>
            <option value="descartada">Descartada</option>
          </select>
        </div>
        <div className="field">
          <label>Severidad</label>
          <select className="select"
            value={filtros.severidad || ''}
            onChange={(e) => update('severidad', e.target.value)}
            data-testid="alerta-filter-sev"
          >
            <option value="">Todas</option>
            <option value="alta">Alta</option>
            <option value="media">Media</option>
            <option value="baja">Baja</option>
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="alerta-refresh"
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
        <div className="empty" data-testid="alerta-empty">
          <p>Sin alertas con esos criterios.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="alerta-table">
          <thead>
            <tr>
              <th>Severidad</th>
              <th>Tipo</th>
              <th>Mensaje</th>
              <th>Creada</th>
              <th>Estado</th>
              {puede && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} data-testid="alerta-row">
                <td>
                  <span className={`badge ${badgeSev(a.severidad)}`}>{a.severidad}</span>
                </td>
                <td>{a.tipo}</td>
                <td style={{ fontSize: 13 }}>{a.mensaje}</td>
                <td>{fmt(a.creada_en)}</td>
                <td>
                  <span className={`badge ${a.estado === 'pendiente' ? 'warn' : 'neutral'}`}>
                    {a.estado}
                  </span>
                </td>
                {puede && (
                  <td>
                    {a.estado === 'pendiente' && (
                      <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => setAtender(a)}
                        data-testid="alerta-atender"
                      >Atender</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {atender && (
        <AtenderAlertaModal
          session={session} alerta={atender}
          onClose={() => setAtender(null)}
          onSuccess={() => { setAtender(null); refresh(); }}
        />
      )}
    </div>
  );
}

function AtenderAlertaModal({ session, alerta, onClose, onSuccess }) {
  const [decision, setDecision] = useState('atendida');
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useAtenderAlerta(session);

  async function handle() {
    try {
      await hook.submit(alerta.id, { decision, motivo });
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Atender alerta" onClose={onClose} testid="alerta-atender-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{alerta.tipo}</strong>: {alerta.mensaje}
      </p>
      <div className="field">
        <label>Decisión</label>
        <select className="select"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          data-testid="alerta-atender-decision"
        >
          <option value="atendida">Atendida</option>
          <option value="descartada">Descartada (falso positivo)</option>
        </select>
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Acción tomada / justificación"
          id="alerta-atender-motivo"
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
          data-testid="alerta-atender-submit"
        >{hook.submitting ? 'Guardando…' : 'Atender'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ReglasAlertas({ session }) {
  const { items, loading, error, refresh } = useReglasAlerta(session);
  const [modal, setModal] = useState(null);

  return (
    <div data-testid="alerta-reglas">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--s-3)' }}>
        <span className="muted" style={{ fontSize: 13 }}>
          {items.length} regla(s) activa(s).
        </span>
        <button type="button" className="btn btn-accent btn-sm"
          onClick={() => setModal({ tipo: 'nueva' })}
          data-testid="alerta-regla-nueva"
        >+ Nueva regla</button>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="alerta-reglas-empty">
          <p>No hay reglas configuradas.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="alerta-reglas-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Tipo</th>
              <th>Severidad</th>
              <th>Umbral</th>
              <th>Activa</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} data-testid="alerta-regla-row">
                <td>{r.nombre}</td>
                <td>{r.tipo}</td>
                <td>
                  <span className={`badge ${badgeSev(r.severidad)}`}>{r.severidad}</span>
                </td>
                <td className="num">{r.umbral || '—'}</td>
                <td>
                  <span className={`badge ${r.activa ? 'ok' : 'neutral'}`}>
                    {r.activa ? 'Sí' : 'No'}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button type="button" className="btn btn-secondary btn-sm"
                      onClick={() => setModal({ tipo: 'editar', regla: r })}
                      data-testid="alerta-regla-editar"
                    >Editar</button>
                    {r.activa && (
                      <button type="button" className="btn btn-danger btn-sm"
                        onClick={() => setModal({ tipo: 'inactivar', regla: r })}
                        data-testid="alerta-regla-inactivar"
                      >Inactivar</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(modal?.tipo === 'nueva' || modal?.tipo === 'editar') && (
        <FormReglaModal
          session={session} regla={modal.regla}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal?.tipo === 'inactivar' && (
        <InactivarReglaModal
          session={session} regla={modal.regla}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
    </div>
  );
}

function FormReglaModal({ session, regla, onClose, onSuccess }) {
  const isEdit = Boolean(regla);
  const [form, setForm] = useState({
    nombre: regla?.nombre || '',
    tipo: regla?.tipo || 'pqrsd_vencimiento',
    severidad: regla?.severidad || 'media',
    umbral: regla?.umbral || '',
    descripcion: regla?.descripcion || '',
  });
  const crear = useCrearReglaAlerta(session);
  const editar = useActualizarReglaAlerta(session);
  const hook = isEdit ? editar : crear;

  async function handle() {
    try {
      const payload = { ...form, umbral: form.umbral === '' ? null : Number(form.umbral) };
      if (isEdit) await editar.submit(regla.id, payload);
      else await crear.submit(payload);
      onSuccess?.();
    } catch { /* */ }
  }

  const valid = form.nombre.trim().length >= 3;

  return (
    <ModalShell title={isEdit ? 'Editar regla' : 'Nueva regla de alerta'} onClose={onClose} testid="alerta-regla-modal">
      <div className="field">
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="alerta-regla-nombre"
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 'var(--s-3)' }}>
        <div className="field">
          <label>Tipo</label>
          <select className="select"
            value={form.tipo}
            onChange={(e) => setForm({ ...form, tipo: e.target.value })}
            data-testid="alerta-regla-tipo"
          >
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Severidad</label>
          <select className="select"
            value={form.severidad}
            onChange={(e) => setForm({ ...form, severidad: e.target.value })}
            data-testid="alerta-regla-sev"
          >
            <option value="baja">Baja</option>
            <option value="media">Media</option>
            <option value="alta">Alta</option>
          </select>
        </div>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Umbral (días, cantidad, etc.)</label>
        <input type="number" className="input" value={form.umbral}
          onChange={(e) => setForm({ ...form, umbral: e.target.value })}
          data-testid="alerta-regla-umbral"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea className="textarea" rows={2} value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          data-testid="alerta-regla-desc"
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
          data-testid="alerta-regla-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function InactivarReglaModal({ session, regla, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarReglaAlerta(session);

  async function handle() {
    try {
      await hook.submit(regla.id, motivo);
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Inactivar regla" onClose={onClose} testid="alerta-regla-inactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        La regla <strong>{regla.nombre}</strong> dejará de generar alertas.
        Las alertas ya generadas se conservan.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="alerta-regla-inact-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="alerta-regla-inact-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div role="dialog" aria-modal="true" data-testid={testid}
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 500, padding: 'var(--s-5)' }}>
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

function badgeSev(s) {
  if (s === 'alta') return 'danger';
  if (s === 'media') return 'warn';
  return 'neutral';
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default Alertas;
