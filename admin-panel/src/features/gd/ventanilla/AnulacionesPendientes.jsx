/**
 * AnulacionesPendientes — GD-UI-0011 parte 2.
 *
 * Vista del coordinador VU (PERM-VU-016) para aprobar/rechazar solicitudes
 * de anulación de radicados. Aplica RNF-058: el solicitante ≠ aprobador
 * (validado server-side; el botón se oculta si `solicitante_id === userId`).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useAnulacionesPendientes } from './useGdRadicados.js';

export function AnulacionesPendientes({
  session,
  currentUserId,
  onNavigate,
  ...shellProps
}) {
  const { items, total, loading, error, aprobar, rechazar, refresh } =
    useAnulacionesPendientes(session, { estado: 'pendiente' });
  const [actionTarget, setActionTarget] = useState(null); // {id, action}
  const [observacion, setObservacion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  async function handleConfirm() {
    if (!actionTarget) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (actionTarget.action === 'aprobar') {
        await aprobar(actionTarget.id, observacion || undefined);
      } else {
        await rechazar(actionTarget.id, observacion || undefined);
      }
      setActionTarget(null);
      setObservacion('');
    } catch (err) {
      setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Anulaciones pendientes' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Anulaciones pendientes</h1>
          <p className="subtitle">
            {total} solicitud(es) en espera de aprobación. El solicitante
            no puede aprobar su propia anulación.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="anul-refresh"
          >
            Actualizar
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">
              <div>{error.message || 'No se pudo cargar.'}</div>
            </div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="anul-empty" style={{ margin: 'var(--s-4)' }}>
            <p>No hay solicitudes de anulación pendientes.</p>
          </div>
        )}
        {items.length > 0 && (
          <table className="data-table" data-testid="anul-table">
            <thead>
              <tr>
                <th>Radicado</th>
                <th>Solicitante</th>
                <th>Motivo</th>
                <th>Fecha solicitud</th>
                <th style={{ textAlign: 'right' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const esPropia = currentUserId
                  && s.solicitante_user_id === currentUserId;
                return (
                  <tr key={s.id} data-testid="anul-row">
                    <td className="num">{s.numero_radicado}</td>
                    <td>{s.solicitante_nombre}</td>
                    <td title={s.motivo}>
                      {(s.motivo || '').slice(0, 80)}
                      {s.motivo?.length > 80 ? '…' : ''}
                    </td>
                    <td>{fmtFecha(s.fecha_solicitud)}</td>
                    <td style={{ textAlign: 'right' }}>
                      {esPropia ? (
                        <span className="muted" style={{ fontSize: 12 }}>
                          No puede aprobar la propia
                        </span>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm btn-accent"
                            onClick={() => setActionTarget({ id: s.id, action: 'aprobar' })}
                            data-testid="anul-aprobar-btn"
                            style={{ marginRight: 6 }}
                          >
                            Aprobar
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            onClick={() => setActionTarget({ id: s.id, action: 'rechazar' })}
                            data-testid="anul-rechazar-btn"
                          >
                            Rechazar
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {actionTarget && (
        <div
          role="dialog"
          aria-modal="true"
          data-testid="anul-modal"
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(15,23,42,0.4)',
            display: 'grid', placeItems: 'center', zIndex: 50,
          }}
          onClick={() => setActionTarget(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card"
            style={{ width: 420, padding: 'var(--s-5)' }}
          >
            <h2 style={{ margin: 0, fontSize: 16 }}>
              {actionTarget.action === 'aprobar'
                ? 'Aprobar anulación'
                : 'Rechazar anulación'}
            </h2>
            <p className="muted" style={{ fontSize: 13 }}>
              Observación (opcional, recomendada).
            </p>
            <textarea
              className="textarea"
              rows={3}
              value={observacion}
              onChange={(e) => setObservacion(e.target.value)}
              data-testid="anul-observacion"
            />
            {submitError && (
              <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
                <div className="body">{submitError.message || 'Error.'}</div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={() => setActionTarget(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className={`btn ${actionTarget.action === 'aprobar' ? 'btn-accent' : 'btn-danger-solid'}`}
                onClick={handleConfirm}
                disabled={submitting}
                data-testid="anul-confirm"
              >
                {submitting ? 'Procesando…' :
                  actionTarget.action === 'aprobar' ? 'Aprobar' : 'Rechazar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </GdShell>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default AnulacionesPendientes;
