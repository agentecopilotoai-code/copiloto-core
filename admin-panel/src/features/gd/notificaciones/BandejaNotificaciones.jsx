/**
 * BandejaNotificaciones — GD-UI-0081.
 *
 * Bandeja de notificaciones in-app del usuario. Filtros por tipo
 * (informativa, advertencia, error), leída/no leída, fecha desde.
 * Click en notificación marca como leída + navega al link.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useNotificacionesInbox, useMarcarNotifLeida, useMarcarTodasLeidas,
} from './useGdNotif.js';

const TIPOS = ['informativa', 'advertencia', 'error', 'sistema'];

export function BandejaNotificaciones({
  session, roles = [], onNavigate, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'NOT-READ', 'R');
  const [filtros, setFiltros] = useState({});
  const inbox = useNotificacionesInbox(session, filtros);
  const marcar = useMarcarNotifLeida(session);
  const marcarTodas = useMarcarTodasLeidas(session);

  function actualizar(k, v) {
    // OJO: no usar `v || undefined` — eso colapsa `false` (filtro
    // "leída=false") a undefined y nunca se manda al backend.
    const next = (v === undefined || v === null || v === '') ? undefined : v;
    setFiltros((p) => ({ ...p, [k]: next }));
  }

  async function abrir(n) {
    try {
      if (!n.leida) await marcar.submit(n.id);
    } catch (_) { /* swallow */ }
    if (n.link) onNavigate?.(n.link);
    inbox.refresh();
  }

  async function marcarAll() {
    try {
      await marcarTodas.submit();
      inbox.refresh();
    } catch (_) { /* swallow */ }
  }

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
          <h1>Bandeja de notificaciones
            {inbox.noLeidas > 0 && (
              <span className="badge warn" style={{ marginLeft: 8 }}
                data-testid="not-bd-badge-noleidas"
              >{inbox.noLeidas} sin leer</span>
            )}
          </h1>
          <p className="subtitle">
            Notificaciones del módulo dirigidas a tu usuario.
            Pulsa una para verla y marcarla como leída.
          </p>
        </div>
        <div className="actions">
          {inbox.noLeidas > 0 && (
            <button type="button" className="btn btn-secondary"
              onClick={marcarAll}
              disabled={marcarTodas.loading}
              data-testid="not-bd-marcar-todas"
            >Marcar todas como leídas</button>
          )}
          <button type="button" className="btn btn-secondary"
            onClick={inbox.refresh}
            data-testid="not-bd-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="not-bd-no-perm"
        >
          <div className="body">No tienes permiso para ver notificaciones.</div>
        </div>
      )}

      {tienePermiso && (
        <>
          <div className="card" style={{ padding: 'var(--s-3)',
            marginBottom: 'var(--s-3)', display: 'flex',
            gap: 'var(--s-2)', flexWrap: 'wrap' }}
            data-testid="not-bd-filtros"
          >
            <label style={{ fontSize: 12 }}>
              Tipo{' '}
              <select value={filtros.tipo || ''}
                onChange={(e) => actualizar('tipo', e.target.value)}
                data-testid="not-bd-tipo"
              >
                <option value="">— Todos —</option>
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 12 }}>
              Estado{' '}
              <select value={filtros.leida === undefined ? '' : String(filtros.leida)}
                onChange={(e) => actualizar('leida',
                  e.target.value === '' ? undefined : e.target.value === 'true')}
                data-testid="not-bd-leida"
              >
                <option value="">— Todas —</option>
                <option value="false">No leídas</option>
                <option value="true">Leídas</option>
              </select>
            </label>
          </div>

          {inbox.loading && <p className="muted">Cargando…</p>}
          {inbox.error && (
            <div className="alert danger" role="alert"
              data-testid="not-bd-error"
            >
              <div className="body">{inbox.error.message}</div>
            </div>
          )}

          {inbox.items.length === 0 && !inbox.loading && !inbox.error && (
            <div className="empty" data-testid="not-bd-empty">
              <p className="muted">Sin notificaciones.</p>
            </div>
          )}

          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {inbox.items.map((n) => (
              <li key={n.id}
                className="card"
                style={{ padding: 'var(--s-3)', marginBottom: 'var(--s-1)',
                  cursor: 'pointer',
                  borderLeft: n.leida ? '3px solid transparent'
                    : '3px solid var(--c-primary)',
                  opacity: n.leida ? 0.7 : 1 }}
                onClick={() => abrir(n)}
                data-testid="not-bd-item"
              >
                <div style={{ display: 'flex',
                  justifyContent: 'space-between' }}
                >
                  <strong>{n.titulo}</strong>
                  <div style={{ display: 'flex', gap: 'var(--s-1)',
                    alignItems: 'center' }}
                  >
                    {n.severidad && (
                      <span className={`badge ${
                        n.severidad === 'alta' ? 'danger'
                          : n.severidad === 'media' ? 'warn' : ''
                      }`}>{n.severidad}</span>
                    )}
                    <small className="muted">{fmt(n.creado_en)}</small>
                  </div>
                </div>
                <p style={{ margin: 'var(--s-1) 0 0', fontSize: 13 }}>
                  {n.mensaje}
                </p>
                {n.tipo && (
                  <small className="muted">tipo: {n.tipo}</small>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </GdShell>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default BandejaNotificaciones;
