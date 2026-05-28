/**
 * AlertasCriticas — GD-UI-0083.
 *
 * Panel admin de alertas críticas del módulo:
 *  - Categoría: vencimiento, sla, fallo_canal, integridad,
 *    seguridad.
 *  - Severidad: alta/media/baja.
 *  - Click → modal con detalle + atender (con comentario).
 *
 * Acceso: jefes, coordinadores, admin (RW); auditor (R).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useAlertasCriticas, useAtenderAlerta,
} from './useGdNotif.js';

const CATEGORIAS = [
  'vencimiento', 'sla', 'fallo_canal', 'integridad', 'seguridad',
];
const SEVERIDADES = ['alta', 'media', 'baja'];

export function AlertasCriticas({
  session, roles = [], onNavigate, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'ALR-001', 'R');
  const puedeAtender = gdCanAny(roles, 'ALR-002', 'RW');
  const [filtros, setFiltros] = useState({});
  const alertas = useAlertasCriticas(session, filtros);
  const atender = useAtenderAlerta(session);
  const [seleccion, setSeleccion] = useState(null);
  const [comentario, setComentario] = useState('');
  const [feedback, setFeedback] = useState(null);

  function actualizar(k, v) {
    setFiltros((p) => ({ ...p, [k]: v || undefined }));
  }

  async function atenderSubmit() {
    if (!seleccion) return;
    setFeedback(null);
    try {
      await atender.submit(seleccion.id, comentario);
      setFeedback({ ok: true });
      setSeleccion(null);
      setComentario('');
      alertas.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Alertas críticas' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Alertas críticas
            {alertas.totalPendientes > 0 && (
              <span className="badge danger" style={{ marginLeft: 8 }}
                data-testid="alr-badge-pendientes"
              >{alertas.totalPendientes} pendientes</span>
            )}
          </h1>
          <p className="subtitle">
            Vencimientos, fallos de SLA, fallos de canal e
            integridad. Atender una alerta queda registrado en
            auditoría con comentario y responsable.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={alertas.refresh}
            data-testid="alr-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="alr-no-perm"
        >
          <div className="body">No tienes permiso para ver alertas críticas.</div>
        </div>
      )}

      {tienePermiso && (
        <>
          <div className="card" style={{ padding: 'var(--s-3)',
            marginBottom: 'var(--s-3)', display: 'flex',
            gap: 'var(--s-2)', flexWrap: 'wrap' }}
            data-testid="alr-filtros"
          >
            <label style={{ fontSize: 12 }}>
              Categoría{' '}
              <select value={filtros.categoria || ''}
                onChange={(e) => actualizar('categoria', e.target.value)}
                data-testid="alr-categoria"
              >
                <option value="">— Todas —</option>
                {CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 12 }}>
              Severidad{' '}
              <select value={filtros.severidad || ''}
                onChange={(e) => actualizar('severidad', e.target.value)}
                data-testid="alr-severidad"
              >
                <option value="">— Todas —</option>
                {SEVERIDADES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>

          {alertas.loading && <p className="muted">Cargando…</p>}
          {alertas.error && (
            <div className="alert danger" role="alert"
              data-testid="alr-error"
            >
              <div className="body">{alertas.error.message}</div>
            </div>
          )}

          {alertas.items.length === 0 && !alertas.loading && !alertas.error && (
            <div className="empty" data-testid="alr-empty">
              <p className="muted">Sin alertas en este filtro.</p>
            </div>
          )}

          {alertas.items.length > 0 && (
            <table className="data-table" data-testid="alr-tabla">
              <thead>
                <tr>
                  <th>Categoría</th>
                  <th>Severidad</th>
                  <th>Título</th>
                  <th>Entidad</th>
                  <th>Creada</th>
                  <th>Estado</th>
                  {puedeAtender && <th>Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {alertas.items.map((a) => (
                  <tr key={a.id} data-testid="alr-row">
                    <td>{a.categoria}</td>
                    <td>
                      <span className={`badge ${
                        a.severidad === 'alta' ? 'danger'
                          : a.severidad === 'media' ? 'warn' : ''
                      }`}>{a.severidad}</span>
                    </td>
                    <td>{a.titulo}</td>
                    <td>
                      {a.entidad ? (
                        <button type="button" className="btn-link"
                          onClick={() => onNavigate?.(
                            `/gd/${a.entidad.tipo}/${a.entidad.id}`,
                          )}
                          data-testid="alr-ir-entidad"
                          style={{ background: 'none', border: 0,
                            color: 'var(--c-primary)', cursor: 'pointer' }}
                        >
                          {a.entidad.tipo}#{a.entidad.id}
                        </button>
                      ) : '—'}
                    </td>
                    <td>{fmt(a.creada_en)}</td>
                    <td>
                      {a.atendida_por ? (
                        <span className="badge ok">atendida</span>
                      ) : (
                        <span className="badge warn">pendiente</span>
                      )}
                    </td>
                    {puedeAtender && (
                      <td>
                        {!a.atendida_por && (
                          <button type="button" className="btn btn-sm btn-primary"
                            onClick={() => setSeleccion(a)}
                            data-testid="alr-atender"
                          >Atender</button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {seleccion && (
            <div className="modal-backdrop"
              data-testid="alr-modal"
              style={{ position: 'fixed', inset: 0,
                background: 'rgba(0,0,0,0.4)', display: 'flex',
                alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
            >
              <div className="modal" style={{ background: 'white',
                padding: 'var(--s-5)', minWidth: 400, maxWidth: 600,
                borderRadius: 8 }}
              >
                <h3 style={{ marginTop: 0 }}>{seleccion.titulo}</h3>
                {seleccion.descripcion && (
                  <p>{seleccion.descripcion}</p>
                )}
                <label style={{ display: 'block', marginTop: 'var(--s-3)' }}>
                  Comentario (auditado)
                  <textarea value={comentario}
                    onChange={(e) => setComentario(e.target.value)}
                    rows={3} style={{ width: '100%' }}
                    placeholder="Acción tomada, hallazgos…"
                    data-testid="alr-modal-comentario"
                  />
                </label>
                <div style={{ display: 'flex', gap: 'var(--s-2)',
                  marginTop: 'var(--s-3)', justifyContent: 'flex-end' }}
                >
                  <button type="button" className="btn btn-secondary"
                    onClick={() => { setSeleccion(null); setComentario(''); }}
                    data-testid="alr-modal-cancelar"
                  >Cancelar</button>
                  <button type="button" className="btn btn-primary"
                    onClick={atenderSubmit}
                    disabled={atender.loading || !comentario.trim()}
                    data-testid="alr-modal-confirmar"
                  >{atender.loading ? 'Atendiendo…' : 'Atender'}</button>
                </div>
              </div>
            </div>
          )}

          {feedback && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" data-testid="alr-feedback"
            >
              <div className="body">
                {feedback.ok ? 'Alerta atendida.'
                  : (feedback.error?.message || 'Error.')}
              </div>
            </div>
          )}
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

export default AlertasCriticas;
