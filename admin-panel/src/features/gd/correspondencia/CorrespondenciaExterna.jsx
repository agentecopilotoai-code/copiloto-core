/**
 * CorrespondenciaExterna — GD-UI-0031..0034.
 *
 * Layout con tabs: Recibidas, Borradores, Por revisar, Por firmar,
 * Enviadas, Nueva. Click en fila → FichaCorrespondencia que incluye
 * todo el workflow (revisar → aprobar → firmar → radicar salida →
 * enviar), gestión de múltiples destinatarios y registro de soporte
 * de envío.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useCorrespondenciaList,
  useCrearBorradorCorrespondenciaExterna,
} from './useGdCorrespondencia.js';

const TABS = [
  { id: 'recibidas', label: 'Recibidas' },
  { id: 'borradores', label: 'Borradores' },
  { id: 'por-revisar', label: 'Por revisar' },
  { id: 'por-firmar', label: 'Por firmar' },
  { id: 'enviadas', label: 'Enviadas' },
  { id: 'nueva', label: 'Nueva' },
];

export function CorrespondenciaExterna({
  session,
  dependencias = [],
  onNavigate,
  ...shellProps
}) {
  const [tab, setTab] = useState('borradores');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Correspondencia externa' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Correspondencia externa</h1>
          <p className="subtitle">
            Comunicaciones oficiales hacia terceros externos a la entidad.
          </p>
        </div>
      </div>

      <nav className="tabs" data-testid="ce-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
            data-testid={`ce-tab-btn-${t.id}`}
          >{t.label}</button>
        ))}
      </nav>

      <div className="card" style={{ padding: 'var(--s-5)' }}>
        {tab !== 'nueva' ? (
          <BandejaExterna
            session={session}
            bandeja={tab}
            onNavigate={onNavigate}
          />
        ) : (
          <NuevoBorradorExterno
            session={session}
            dependencias={dependencias}
            onSuccess={(id) => onNavigate?.(`/gd/correspondencia/${id}`)}
          />
        )}
      </div>
    </GdShell>
  );
}

function BandejaExterna({ session, bandeja, onNavigate }) {
  const filtros = { tipo: 'externa', bandeja };
  const { items, total, loading, error, refresh } =
    useCorrespondenciaList(session, filtros);

  return (
    <div data-testid={`ce-bandeja-${bandeja}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--s-3)' }}>
        <span className="muted">{total} ítem(s).</span>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={refresh}
          data-testid="ce-refresh"
        >Actualizar</button>
      </div>
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="ce-empty">
          <p>Sin ítems en esta bandeja.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="ce-table">
          <thead>
            <tr>
              <th>Asunto</th>
              <th>Tercero destinatario</th>
              <th>Estado</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr
                key={c.id}
                data-testid="ce-row"
                onClick={() => onNavigate?.(`/gd/correspondencia/${c.id}`)}
              >
                <td>{c.asunto}</td>
                <td>{c.tercero_destinatario_nombre || c.entidad_destino || '—'}</td>
                <td><span className={`badge ${ceBadgeTone(c.estado)}`}>{c.estado}</span></td>
                <td>{fmtFecha(c.fecha)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NuevoBorradorExterno({ session, dependencias, onSuccess }) {
  const [form, setForm] = useState({
    asunto: '', descripcion: '',
    dependencia_origen_id: '',
    tercero_destinatario_id: '',
    documento_id: '',
  });
  const hook = useCrearBorradorCorrespondenciaExterna(session);

  function update(k, v) { setForm((p) => ({ ...p, [k]: v })); }

  const isValid = form.asunto.trim().length >= 2 &&
                  Boolean(form.dependencia_origen_id) &&
                  Boolean(form.tercero_destinatario_id);

  async function handleSubmit() {
    try {
      const r = await hook.submit(form);
      onSuccess?.(r?.id);
    } catch { /* hook */ }
  }

  return (
    <div data-testid="ce-nuevo-form">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>Nuevo borrador</h2>
      <div className="field">
        <label>Asunto <span className="req">*</span></label>
        <input
          className="input"
          value={form.asunto}
          onChange={(e) => update('asunto', e.target.value)}
          maxLength={300}
          data-testid="ce-asunto"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Cuerpo / Descripción</label>
        <textarea
          className="textarea"
          rows={6}
          value={form.descripcion}
          onChange={(e) => update('descripcion', e.target.value)}
          maxLength={4000}
          data-testid="ce-descripcion"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Dependencia origen <span className="req">*</span></label>
        <select
          className="select"
          value={form.dependencia_origen_id}
          onChange={(e) => update('dependencia_origen_id', e.target.value)}
          data-testid="ce-dep-origen"
        >
          <option value="">Seleccione…</option>
          {dependencias.map((d) => (
            <option key={d.id} value={d.id}>{d.nombre}</option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Tercero destinatario (UUID) <span className="req">*</span></label>
        <input
          className="input"
          value={form.tercero_destinatario_id}
          onChange={(e) => update('tercero_destinatario_id', e.target.value)}
          data-testid="ce-destinatario"
        />
        <span className="hint">
          Más destinatarios + copias pueden añadirse en la ficha luego.
        </span>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Documento adjunto (UUID — opcional en borrador)</label>
        <input
          className="input"
          value={form.documento_id}
          onChange={(e) => update('documento_id', e.target.value)}
          data-testid="ce-doc-id"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
        <button
          type="button"
          className="btn btn-accent"
          onClick={handleSubmit}
          disabled={!isValid || hook.submitting}
          data-testid="ce-crear-borrador"
        >
          {hook.submitting ? 'Creando…' : 'Crear borrador'}
        </button>
      </div>
    </div>
  );
}

function ceBadgeTone(estado) {
  if (estado === 'enviada' || estado === 'radicada_salida' || estado === 'firmada') return 'ok';
  if (estado === 'anulada' || estado === 'devuelta') return 'danger';
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

export default CorrespondenciaExterna;
