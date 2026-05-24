/**
 * PanelUsoIA — GD-UI-0077. Uso de IA + costos + límites.
 *
 * Por usuario, por funcionalidad, por dependencia. IA-006.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useUsoIA } from './useGdIA.js';

export function PanelUsoIA({ session, ...shellProps }) {
  const [periodo, setPeriodo] = useState(() => defaultPeriodo());
  const { data, loading, error, refresh } = useUsoIA(session, periodo);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Uso de IA' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Uso de IA del módulo</h1>
          <p className="subtitle">
            Tokens consumidos, costos aproximados y límites por usuario.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="ia-uso-refresh"
          >Actualizar</button>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'flex-end' }}>
          <div className="field" style={{ width: 180 }}>
            <label>Desde</label>
            <input type="date" className="input"
              value={periodo.desde}
              onChange={(e) => setPeriodo({ ...periodo, desde: e.target.value })}
              data-testid="ia-uso-desde"
            />
          </div>
          <div className="field" style={{ width: 180 }}>
            <label>Hasta</label>
            <input type="date" className="input"
              value={periodo.hasta}
              onChange={(e) => setPeriodo({ ...periodo, hasta: e.target.value })}
              data-testid="ia-uso-hasta"
            />
          </div>
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <>
          <div data-testid="ia-uso-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}>
            <Kpi label="Llamadas IA" value={data.total_llamadas ?? 0} />
            <Kpi label="Tokens entrada" value={fmtNum(data.tokens_entrada ?? 0)} />
            <Kpi label="Tokens salida" value={fmtNum(data.tokens_salida ?? 0)} />
            <Kpi label="Costo periodo" value={fmtMoneda(data.costo_total)} />
            <Kpi label="Usuarios activos" value={data.usuarios_activos ?? 0} />
            <Kpi label="% sobre límite" value={fmtPct(data.uso_sobre_limite)}
              tone={data.uso_sobre_limite > 0.9 ? 'warn' : 'ok'} />
          </div>

          {(data.por_funcionalidad || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Por funcionalidad</h3>
              <table className="data-table" data-testid="ia-uso-funcs">
                <thead>
                  <tr>
                    <th>Funcionalidad</th>
                    <th>Llamadas</th>
                    <th>Tokens</th>
                    <th>Costo</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_funcionalidad.map((f) => (
                    <tr key={f.funcionalidad} data-testid="ia-uso-func-row">
                      <td>{f.funcionalidad}</td>
                      <td className="num">{f.llamadas}</td>
                      <td className="num">{fmtNum(f.tokens)}</td>
                      <td className="num">{fmtMoneda(f.costo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(data.por_usuario || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Top usuarios</h3>
              <table className="data-table" data-testid="ia-uso-usuarios">
                <thead>
                  <tr>
                    <th>Usuario</th>
                    <th>Llamadas</th>
                    <th>Tokens</th>
                    <th>Costo</th>
                    <th>% límite mensual</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_usuario.map((u) => (
                    <tr key={u.usuario_id || u.email} data-testid="ia-uso-user-row">
                      <td>{u.email || u.usuario_id}</td>
                      <td className="num">{u.llamadas}</td>
                      <td className="num">{fmtNum(u.tokens)}</td>
                      <td className="num">{fmtMoneda(u.costo)}</td>
                      <td className="num">
                        <span className={`badge ${u.pct_limite > 0.9 ? 'danger' : ''}`}>
                          {fmtPct(u.pct_limite)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi" data-testid="ia-uso-kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone === 'warn' ? 'warn' : tone === 'danger' ? 'danger' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function defaultPeriodo() {
  const now = new Date();
  const hasta = now.toISOString().slice(0, 10);
  const d = new Date(now); d.setDate(d.getDate() - 30);
  return { desde: d.toISOString().slice(0, 10), hasta };
}

function fmtNum(n) {
  return (n ?? 0).toLocaleString('es-CO');
}
function fmtMoneda(v) {
  if (v == null) return '—';
  return `COP ${v.toLocaleString('es-CO', { maximumFractionDigits: 0 })}`;
}
function fmtPct(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(1)}%`;
  return `${v.toFixed(1)}%`;
}

export default PanelUsoIA;
