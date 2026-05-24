/**
 * CorrespondenciaInterna — GD-UI-0029 (crear) + GD-UI-0030 (bandeja).
 *
 * Layout con tabs Recibidas / Enviadas / Nueva. La pestaña Nueva muestra
 * un form simple (asunto, dependencia destino, destinatario, adjunto).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useCorrespondenciaList,
  useCrearCorrespondenciaInterna,
} from './useGdCorrespondencia.js';

const TABS = ['Recibidas', 'Enviadas', 'Nueva'];

export function CorrespondenciaInterna({
  session,
  dependencias = [],
  onNavigate,
  ...shellProps
}) {
  const [tab, setTab] = useState('Recibidas');
  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Correspondencia interna' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Correspondencia interna</h1>
          <p className="subtitle">
            Comunicaciones entre dependencias de la entidad.
          </p>
        </div>
      </div>

      <nav className="tabs" data-testid="ci-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
            data-testid={`ci-tab-btn-${t}`}
          >{t}</button>
        ))}
      </nav>

      <div className="card" style={{ padding: 'var(--s-5)' }}>
        {tab === 'Recibidas' && (
          <BandejaInterna
            session={session}
            bandeja="recibidas"
            onNavigate={onNavigate}
          />
        )}
        {tab === 'Enviadas' && (
          <BandejaInterna
            session={session}
            bandeja="enviadas"
            onNavigate={onNavigate}
          />
        )}
        {tab === 'Nueva' && (
          <NuevaInternaForm
            session={session}
            dependencias={dependencias}
            onSuccess={() => setTab('Enviadas')}
          />
        )}
      </div>
    </GdShell>
  );
}

function BandejaInterna({ session, bandeja, onNavigate }) {
  const filtros = { tipo: 'interna', bandeja };
  const { items, total, loading, error, refresh } =
    useCorrespondenciaList(session, filtros);

  return (
    <div data-testid={`ci-bandeja-${bandeja}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--s-3)' }}>
        <span className="muted">{total} comunicación(es).</span>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={refresh}
          data-testid="ci-refresh"
        >Actualizar</button>
      </div>
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="ci-empty">
          <p>Sin comunicaciones en esta bandeja.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="ci-table">
          <thead>
            <tr>
              <th>Asunto</th>
              <th>Remitente</th>
              <th>Destinatario</th>
              <th>Fecha</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr
                key={c.id}
                data-testid="ci-row"
                onClick={() => onNavigate?.(`/gd/correspondencia/${c.id}`)}
              >
                <td>
                  {!c.leida && bandeja === 'recibidas' && <strong>● </strong>}
                  {c.asunto}
                </td>
                <td>{c.remitente_dependencia_nombre || c.remitente_usuario_nombre || '—'}</td>
                <td>{c.destinatario_dependencia_nombre || c.destinatario_usuario_nombre || '—'}</td>
                <td>{fmtFecha(c.fecha)}</td>
                <td><span className={`badge ${badgeTone(c.estado)}`}>{c.estado}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NuevaInternaForm({ session, dependencias, onSuccess }) {
  const [form, setForm] = useState({
    asunto: '', descripcion: '',
    dependencia_destino_id: '',
    destinatario_user_id: '',
    documento_id: '',
  });
  const hook = useCrearCorrespondenciaInterna(session);

  function update(k, v) { setForm((p) => ({ ...p, [k]: v })); }

  const isValid = form.asunto.trim().length >= 2 && Boolean(form.dependencia_destino_id);

  async function handleSubmit() {
    try {
      await hook.submit(form);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="ci-nueva-form">
      <div className="field">
        <label>Asunto <span className="req">*</span></label>
        <input
          className="input"
          maxLength={300}
          value={form.asunto}
          onChange={(e) => update('asunto', e.target.value)}
          data-testid="ci-asunto"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción / Cuerpo</label>
        <textarea
          className="textarea"
          rows={5}
          maxLength={4000}
          value={form.descripcion}
          onChange={(e) => update('descripcion', e.target.value)}
          data-testid="ci-descripcion"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Dependencia destino <span className="req">*</span></label>
        <select
          className="select"
          value={form.dependencia_destino_id}
          onChange={(e) => update('dependencia_destino_id', e.target.value)}
          data-testid="ci-dep-destino"
        >
          <option value="">Seleccione…</option>
          {dependencias.map((d) => (
            <option key={d.id} value={d.id}>{d.nombre}</option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Destinatario específico (opcional — UUID)</label>
        <input
          className="input"
          value={form.destinatario_user_id}
          onChange={(e) => update('destinatario_user_id', e.target.value)}
          data-testid="ci-destinatario"
        />
        <span className="hint">
          Si se deja vacío, la comunicación queda en bandeja de la
          dependencia destino.
        </span>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Documento adjunto (UUID de archivo digital)</label>
        <input
          className="input"
          value={form.documento_id}
          onChange={(e) => update('documento_id', e.target.value)}
          data-testid="ci-doc-id"
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
          data-testid="ci-enviar"
        >
          {hook.submitting ? 'Enviando…' : 'Enviar comunicación'}
        </button>
      </div>
    </div>
  );
}

function badgeTone(estado) {
  if (estado === 'enviada' || estado === 'leida') return 'ok';
  if (estado === 'anulada') return 'danger';
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

export default CorrespondenciaInterna;
