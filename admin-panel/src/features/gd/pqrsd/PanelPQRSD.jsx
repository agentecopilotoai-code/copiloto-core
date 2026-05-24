/**
 * PanelPQRSD — GD-UI-0020. Dashboard del administrador PQRSD.
 *
 * KPIs: total nuevas, asignadas, en proyección, en revisión, aprobadas,
 * cerradas, anuladas, vencidas, próximas a vencer. Filtros: dependencia,
 * periodo. CTA "Ver lista" → GD-UI-0021.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { usePQRSDDashboard } from './useGdPQRSD.js';

export function PanelPQRSD({ session, onNavigate, ...shellProps }) {
  const [periodo, setPeriodo] = useState(() => defaultPeriodo());
  const { data, loading, error, refresh } = usePQRSDDashboard(session, periodo);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Panel PQRSD' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Panel PQRSD</h1>
          <p className="subtitle">
            Monitoreo de Peticiones, Quejas, Reclamos, Sugerencias y
            Denuncias. Decreto 1166/2016.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="panel-refresh"
          >
            Actualizar
          </button>
          <button
            type="button"
            className="btn btn-accent"
            onClick={() => onNavigate?.('/gd/pqrsd/mias')}
            data-testid="panel-ver-mis"
          >
            Mis PQRSD
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-5)' }}>
        <div style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'flex-end' }}>
          <div className="field" style={{ width: 180 }}>
            <label>Desde</label>
            <input
              type="date" className="input"
              value={periodo.desde || ''}
              onChange={(e) => setPeriodo({ ...periodo, desde: e.target.value })}
              data-testid="panel-desde"
            />
          </div>
          <div className="field" style={{ width: 180 }}>
            <label>Hasta</label>
            <input
              type="date" className="input"
              value={periodo.hasta || ''}
              onChange={(e) => setPeriodo({ ...periodo, hasta: e.target.value })}
              data-testid="panel-hasta"
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
          <div
            data-testid="panel-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 'var(--s-3)',
              marginBottom: 'var(--s-5)',
            }}
          >
            <Kpi label="Total periodo" value={data.totales?.total ?? 0} />
            <Kpi label="Nuevas" value={data.por_estado?.nueva ?? 0} />
            <Kpi label="Asignadas" value={data.por_estado?.asignada ?? 0} />
            <Kpi label="En proyección" value={data.por_estado?.en_proyeccion ?? 0} />
            <Kpi label="En revisión" value={data.por_estado?.en_revision ?? 0} />
            <Kpi label="Cerradas" value={data.por_estado?.cerrada ?? 0} tone="ok" />
            <Kpi label="Próximas a vencer" value={data.alertas?.proximas_vencer ?? 0} tone="warn" />
            <Kpi label="Vencidas" value={data.alertas?.vencidas ?? 0} tone="danger" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Distribución por tipo (P/Q/R/S/D)</h3>
            <DistTipos data={data.por_tipo || {}} />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Acceso rápido</h3>
            <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onNavigate?.('/gd/pqrsd/sin-asignar')}
                data-testid="link-sin-asignar"
              >
                Sin asignar ({data.alertas?.sin_asignar ?? 0})
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onNavigate?.('/gd/pqrsd/vencimientos')}
                data-testid="link-vencimientos"
              >
                Por vencer ({data.alertas?.proximas_vencer ?? 0})
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => onNavigate?.('/gd/pqrsd/vencidas')}
                data-testid="link-vencidas"
              >
                Vencidas ({data.alertas?.vencidas ?? 0})
              </button>
            </div>
          </div>
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi" data-testid={`kpi-${label.toLowerCase().replace(/[\s.]+/g, '-')}`}>
      <div className="label">{label}</div>
      <div className={`value ${tone === 'warn' ? 'warn' : tone === 'danger' ? 'danger' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function DistTipos({ data }) {
  const tipos = ['P', 'Q', 'R', 'S', 'D'];
  const labels = { P: 'Petición', Q: 'Queja', R: 'Reclamo', S: 'Sugerencia', D: 'Denuncia' };
  const max = tipos.reduce((m, t) => Math.max(m, data[t] || 0), 0);
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="dist-tipos">
      {tipos.map((t) => {
        const v = data[t] || 0;
        const pct = max ? (v / max) * 100 : 0;
        return (
          <li key={t} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span><strong>{t}</strong> · {labels[t]}</span>
              <span className="num">{v}</span>
            </div>
            <div style={{ background: 'var(--slate-100)', borderRadius: 'var(--r-sm)', height: 8 }}>
              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent-base)' }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function defaultPeriodo() {
  const now = new Date();
  const hasta = now.toISOString().slice(0, 10);
  const d = new Date(now);
  d.setDate(d.getDate() - 30);
  const desde = d.toISOString().slice(0, 10);
  return { desde, hasta };
}

export default PanelPQRSD;
