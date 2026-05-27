/**
 * UsoIAPanel — GD-UI-0077. Panel de uso de IA + costos +
 * límites por usuario.
 *
 * - KPIs globales (tokens, $USD, # llamadas).
 * - Desglose por modelo, usuario, funcionalidad.
 * - Configuración de límite por usuario (admin sistema RW).
 * - Indicador de % consumido vs límite.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useUsoIa, useLimitesIa, useActualizarLimitesIa,
} from './useGdIa.js';

export function UsoIAPanel({
  session, roles = [], ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'IA-006', 'R');
  const puedeAjustar = gdCanAny(roles, 'IA-007', 'RW');
  const [filtros, setFiltros] = useState({});
  const uso = useUsoIa(session, filtros);
  const limites = useLimitesIa(session);
  const actLim = useActualizarLimitesIa(session);
  const [edicion, setEdicion] = useState(null);
  const [feedback, setFeedback] = useState(null);

  async function guardarLimite() {
    setFeedback(null);
    try {
      await actLim.submit({
        usuario_id: edicion.usuario_id,
        limite_diario_usd: edicion.diario,
        limite_mensual_usd: edicion.mensual,
        motivo: edicion.motivo || 'ajuste_manual',
      });
      setFeedback({ ok: true });
      setEdicion(null);
      limites.refresh?.();
      uso.refresh?.();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Uso IA' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Panel de uso IA + costos</h1>
          <p className="subtitle">
            Tokens consumidos, costos estimados y límites por
            usuario / dependencia. Datos en tiempo casi-real.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={() => { uso.refresh?.(); limites.refresh?.(); }}
            data-testid="ia-uso-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="ia-uso-no-perm"
        >
          <div className="body">
            No tienes permiso para ver el panel de uso IA.
          </div>
        </div>
      )}

      {tienePermiso && (
        <>
          {/* Filtros */}
          <div className="card" style={{ padding: 'var(--s-3)',
            marginBottom: 'var(--s-3)', display: 'flex',
            gap: 'var(--s-2)', flexWrap: 'wrap' }}
            data-testid="ia-uso-filtros"
          >
            <label style={{ fontSize: 12 }}>
              Desde{' '}
              <input type="date"
                value={filtros.from || ''}
                onChange={(e) => setFiltros((f) => ({ ...f, from: e.target.value || undefined }))}
                data-testid="ia-uso-from"
              />
            </label>
            <label style={{ fontSize: 12 }}>
              Hasta{' '}
              <input type="date"
                value={filtros.to || ''}
                onChange={(e) => setFiltros((f) => ({ ...f, to: e.target.value || undefined }))}
                data-testid="ia-uso-to"
              />
            </label>
            <label style={{ fontSize: 12 }}>
              Modelo{' '}
              <input type="text"
                value={filtros.modelo || ''}
                onChange={(e) => setFiltros((f) => ({ ...f, modelo: e.target.value || undefined }))}
                placeholder="gpt-4, claude-3…"
                data-testid="ia-uso-modelo"
              />
            </label>
          </div>

          {uso.loading && <p className="muted">Cargando uso…</p>}
          {uso.error && (
            <div className="alert danger" role="alert"
              data-testid="ia-uso-error"
            >
              <div className="body">{uso.error.message}</div>
            </div>
          )}

          {uso.data && (
            <>
              <div data-testid="ia-uso-kpis"
                style={{ display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: 'var(--s-3)', marginBottom: 'var(--s-4)' }}
              >
                <div className="kpi">
                  <div className="label">Tokens totales</div>
                  <div className="value">{(uso.data.total_tokens ?? 0).toLocaleString('es-CO')}</div>
                </div>
                <div className="kpi">
                  <div className="label">Costo (USD)</div>
                  <div className="value">${(uso.data.total_coste_usd ?? 0).toFixed(2)}</div>
                </div>
                <div className="kpi">
                  <div className="label">Límite mensual</div>
                  <div className="value">${(uso.data.limite_actual_usd ?? 0).toFixed(2)}</div>
                </div>
                <div className="kpi">
                  <div className="label">% consumido</div>
                  <div className={`value ${
                    pctConsumido(uso.data) >= 0.9 ? 'danger'
                      : pctConsumido(uso.data) >= 0.7 ? 'warn' : ''
                  }`}>
                    {(pctConsumido(uso.data) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Tabla por modelo */}
              {(uso.data.por_modelo || []).length > 0 && (
                <div className="card" style={{ padding: 'var(--s-4)',
                  marginBottom: 'var(--s-3)' }}
                >
                  <h3 style={{ fontSize: 14, marginTop: 0 }}>Por modelo</h3>
                  <table className="data-table"
                    data-testid="ia-uso-tabla-modelo"
                  >
                    <thead>
                      <tr>
                        <th>Modelo</th>
                        <th className="num">Llamadas</th>
                        <th className="num">Tokens</th>
                        <th className="num">USD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {uso.data.por_modelo.map((m, i) => (
                        <tr key={m.codigo || i}>
                          <td>{m.codigo || m.modelo}</td>
                          <td className="num">{(m.llamadas ?? 0).toLocaleString('es-CO')}</td>
                          <td className="num">{(m.tokens ?? 0).toLocaleString('es-CO')}</td>
                          <td className="num">${(m.coste_usd ?? 0).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Por usuario (con CTA editar límite si tiene RW) */}
              {(uso.data.por_usuario || []).length > 0 && (
                <div className="card" style={{ padding: 'var(--s-4)',
                  marginBottom: 'var(--s-3)' }}
                >
                  <h3 style={{ fontSize: 14, marginTop: 0 }}>Por usuario</h3>
                  <table className="data-table"
                    data-testid="ia-uso-tabla-usuario"
                  >
                    <thead>
                      <tr>
                        <th>Usuario</th>
                        <th className="num">Tokens</th>
                        <th className="num">USD</th>
                        <th className="num">Límite diario</th>
                        {puedeAjustar && <th>Acciones</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {uso.data.por_usuario.map((u, i) => (
                        <tr key={u.usuario_id || i}
                          data-testid="ia-uso-row-usuario"
                        >
                          <td>{u.nombre || u.usuario_id}</td>
                          <td className="num">{(u.tokens ?? 0).toLocaleString('es-CO')}</td>
                          <td className="num">${(u.coste_usd ?? 0).toFixed(2)}</td>
                          <td className="num">
                            ${(u.limite_diario_usd ?? 0).toFixed(2)}
                          </td>
                          {puedeAjustar && (
                            <td>
                              <button type="button"
                                className="btn btn-sm"
                                onClick={() => setEdicion({
                                  usuario_id: u.usuario_id,
                                  nombre: u.nombre,
                                  diario: u.limite_diario_usd ?? 0,
                                  mensual: u.limite_mensual_usd ?? 0,
                                  motivo: '',
                                })}
                                data-testid="ia-uso-editar"
                              >Editar límite</button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {/* Modal edición de límite */}
          {edicion && (
            <div className="modal-backdrop"
              data-testid="ia-uso-modal-edicion"
              style={{ position: 'fixed', inset: 0,
                background: 'rgba(0,0,0,0.4)', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                zIndex: 100 }}
            >
              <div className="modal" style={{ background: 'white',
                padding: 'var(--s-5)', minWidth: 360, borderRadius: 8 }}
              >
                <h3 style={{ marginTop: 0 }}>
                  Editar límite — {edicion.nombre || edicion.usuario_id}
                </h3>
                <label style={{ display: 'block',
                  marginBottom: 'var(--s-2)' }}
                >
                  Límite diario (USD)
                  <input type="number" step="0.01" min="0"
                    value={edicion.diario}
                    onChange={(e) => setEdicion((d) => ({
                      ...d, diario: parseFloat(e.target.value) || 0,
                    }))}
                    style={{ width: '100%' }}
                    data-testid="ia-uso-edit-diario"
                  />
                </label>
                <label style={{ display: 'block',
                  marginBottom: 'var(--s-2)' }}
                >
                  Límite mensual (USD)
                  <input type="number" step="0.01" min="0"
                    value={edicion.mensual}
                    onChange={(e) => setEdicion((d) => ({
                      ...d, mensual: parseFloat(e.target.value) || 0,
                    }))}
                    style={{ width: '100%' }}
                    data-testid="ia-uso-edit-mensual"
                  />
                </label>
                <label style={{ display: 'block',
                  marginBottom: 'var(--s-2)' }}
                >
                  Motivo (auditoría)
                  <input type="text"
                    value={edicion.motivo}
                    onChange={(e) => setEdicion((d) => ({
                      ...d, motivo: e.target.value,
                    }))}
                    style={{ width: '100%' }}
                    data-testid="ia-uso-edit-motivo"
                    required
                  />
                </label>
                <div style={{ display: 'flex', gap: 'var(--s-2)',
                  marginTop: 'var(--s-3)', justifyContent: 'flex-end' }}
                >
                  <button type="button" className="btn btn-secondary"
                    onClick={() => setEdicion(null)}
                    data-testid="ia-uso-edit-cancelar"
                  >Cancelar</button>
                  <button type="button" className="btn btn-primary"
                    onClick={guardarLimite}
                    disabled={actLim.loading || !edicion.motivo}
                    data-testid="ia-uso-edit-guardar"
                  >{actLim.loading ? 'Guardando…' : 'Guardar'}</button>
                </div>
              </div>
            </div>
          )}

          {feedback && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" data-testid="ia-uso-feedback"
            >
              <div className="body">
                {feedback.ok
                  ? 'Límite actualizado.'
                  : (feedback.error?.message || 'Error guardando.')}
              </div>
            </div>
          )}

          {/* Vista compacta de mis límites (solo usuarios non-admin) */}
          {limites.data && (
            <div className="card" style={{ padding: 'var(--s-3)',
              marginTop: 'var(--s-3)' }}
              data-testid="ia-uso-mis-limites"
            >
              <strong style={{ fontSize: 13 }}>Mis límites IA</strong>
              <div style={{ fontSize: 13, marginTop: 'var(--s-1)' }}>
                Hoy: ${(limites.data.consumido_dia ?? 0).toFixed(2)} /
                ${(limites.data.limite_diario_usd ?? 0).toFixed(2)} ·
                Mes: ${(limites.data.consumido_mes ?? 0).toFixed(2)} /
                ${(limites.data.limite_mensual_usd ?? 0).toFixed(2)}
              </div>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

function pctConsumido(d) {
  const lim = d.limite_actual_usd ?? 0;
  const cons = d.limite_consumido_usd ?? d.total_coste_usd ?? 0;
  if (lim <= 0) return 0;
  return Math.min(1, cons / lim);
}

export default UsoIAPanel;
