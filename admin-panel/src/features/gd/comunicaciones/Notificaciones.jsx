/**
 * Notificaciones — GD-UI-0082/0083. Bandeja personal + preferencias.
 *
 * Lista las notificaciones del usuario actual, permite marcar como
 * leídas (individual o masivo) y configurar canales preferidos
 * (in-app, email, SMS) por tipo de evento.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useMisNotificaciones, useMarcarNotificacionLeida,
  useMarcarTodasLeidas,
  usePreferenciasNotificaciones,
  useActualizarPreferenciasNotificaciones,
} from './useGdComunicaciones.js';

const TABS = ['Bandeja', 'Preferencias'];
const TIPOS_EVENTO = [
  { codigo: 'radicado_asignado', label: 'Radicado asignado a mí' },
  { codigo: 'pqrsd_proximo_vencer', label: 'PQRSD próxima a vencer' },
  { codigo: 'pqrsd_vencida', label: 'PQRSD vencida' },
  { codigo: 'doc_por_firmar', label: 'Documento por firmar' },
  { codigo: 'doc_firmado', label: 'Mi documento fue firmado' },
  { codigo: 'expediente_cerrado', label: 'Expediente cerrado' },
  { codigo: 'alerta_pii', label: 'Alerta PII detectada' },
];

export function Notificaciones({ session, onNavigate, ...shellProps }) {
  const [tab, setTab] = useState('Bandeja');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Notificaciones' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Mis notificaciones</h1>
        </div>
      </div>

      <nav className="tabs" data-testid="not-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t} role="tab"
            aria-selected={tab === t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
            data-testid={`not-tab-btn-${t}`}
          >{t}</button>
        ))}
      </nav>

      <div className="card" style={{ padding: 'var(--s-5)' }}>
        {tab === 'Bandeja' && <Bandeja session={session} onNavigate={onNavigate} />}
        {tab === 'Preferencias' && <Preferencias session={session} />}
      </div>
    </GdShell>
  );
}

function Bandeja({ session, onNavigate }) {
  const [soloNoLeidas, setSoloNoLeidas] = useState(false);
  const { items, no_leidas, loading, error, refresh } =
    useMisNotificaciones(session, soloNoLeidas ? { leida: false } : {});
  const marcar = useMarcarNotificacionLeida(session);
  const marcarTodas = useMarcarTodasLeidas(session);

  async function handleClick(n) {
    if (!n.leida) {
      try { await marcar.submit(n.id); refresh(); } catch { /* */ }
    }
    if (n.enlace) onNavigate?.(n.enlace);
  }

  async function handleTodas() {
    try { await marcarTodas.submit(); refresh(); } catch { /* */ }
  }

  return (
    <div data-testid="not-bandeja">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--s-3)' }}>
        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={soloNoLeidas}
              onChange={(e) => setSoloNoLeidas(e.target.checked)}
              data-testid="not-solo-no-leidas"
            />
            Solo no leídas
          </label>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {no_leidas > 0 && (
            <span className="badge warn" data-testid="not-badge-no-leidas">
              {no_leidas} no leída(s)
            </span>
          )}
          <button type="button" className="btn btn-secondary btn-sm"
            onClick={refresh}
            data-testid="not-refresh"
          >Actualizar</button>
          {no_leidas > 0 && (
            <button type="button" className="btn btn-accent btn-sm"
              disabled={marcarTodas.submitting}
              onClick={handleTodas}
              data-testid="not-marcar-todas"
            >Marcar todas leídas</button>
          )}
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="not-empty">
          <p>No tiene notificaciones {soloNoLeidas && 'no leídas'}.</p>
        </div>
      )}
      {items.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="not-lista">
          {items.map((n) => (
            <li
              key={n.id}
              data-testid="not-item"
              onClick={() => handleClick(n)}
              style={{
                padding: 'var(--s-3)',
                borderBottom: '1px solid var(--border-subtle)',
                background: n.leida ? 'transparent' : 'var(--sky-50)',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong style={{ fontSize: 13, fontWeight: n.leida ? 400 : 700 }}>
                  {n.titulo}
                </strong>
                <span className="muted" style={{ fontSize: 11 }}>
                  {fmt(n.creada_en)}
                </span>
              </div>
              <p style={{ margin: '4px 0 0', fontSize: 12 }}>{n.mensaje}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Preferencias({ session }) {
  const { data, loading, error, refresh } = usePreferenciasNotificaciones(session);
  const editar = useActualizarPreferenciasNotificaciones(session);
  const [form, setForm] = useState({});
  const [info, setInfo] = useState(null);

  useEffect(() => {
    if (data?.preferencias) {
      setForm({ ...data.preferencias });
    }
  }, [data]);

  function toggle(codigo, canal, on) {
    setForm((p) => {
      const cur = p[codigo] || { in_app: true };
      return { ...p, [codigo]: { ...cur, [canal]: on } };
    });
  }

  async function handle() {
    setInfo(null);
    try {
      await editar.submit({ preferencias: form });
      setInfo({ ok: true });
      refresh();
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  if (loading) return <p className="muted">Cargando preferencias…</p>;
  if (error) {
    return (
      <div className="alert danger" role="alert">
        <div className="body">{error.message || 'Error.'}</div>
      </div>
    );
  }

  return (
    <div data-testid="not-prefs">
      <p className="muted" style={{ fontSize: 13 }}>
        Elija por qué canales quiere recibir cada tipo de notificación.
        Las notificaciones in-app no se pueden desactivar (siempre se
        registran en su bandeja).
      </p>
      <table className="data-table" data-testid="not-prefs-table">
        <thead>
          <tr>
            <th>Tipo de evento</th>
            <th>In-app</th>
            <th>Email</th>
            <th>SMS</th>
          </tr>
        </thead>
        <tbody>
          {TIPOS_EVENTO.map((t) => {
            const v = form[t.codigo] || {};
            return (
              <tr key={t.codigo} data-testid="not-prefs-row">
                <td>{t.label}</td>
                <td>
                  <input type="checkbox" disabled checked
                    data-testid={`not-prefs-${t.codigo}-inapp`}
                  />
                </td>
                <td>
                  <input type="checkbox"
                    checked={!!v.email}
                    onChange={(e) => toggle(t.codigo, 'email', e.target.checked)}
                    data-testid={`not-prefs-${t.codigo}-email`}
                  />
                </td>
                <td>
                  <input type="checkbox"
                    checked={!!v.sms}
                    onChange={(e) => toggle(t.codigo, 'sms', e.target.checked)}
                    data-testid={`not-prefs-${t.codigo}-sms`}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="not-prefs-info"
          style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok ? 'Preferencias actualizadas.'
              : `Error: ${info.error?.message || 'desconocido'}`}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={editar.submitting} onClick={handle}
          data-testid="not-prefs-guardar"
        >{editar.submitting ? 'Guardando…' : 'Guardar preferencias'}</button>
      </div>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default Notificaciones;
