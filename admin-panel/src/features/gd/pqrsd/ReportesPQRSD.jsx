/**
 * ReportesPQRSD — GD-UI-0028. Tableros agregados de PQRSD.
 *
 * KPIs: totales, vencidas, cumplimiento, tiempo medio respuesta.
 * Tableros: por dependencia, por tipo P/Q/R/S/D, por canal, por tiempo
 * (histograma de respuesta). Exportar PDF/Excel/CSV (PERM-REP-004).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useReportesPQRSD } from './useGdPQRSD.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function ReportesPQRSD({
  session,
  roles = [],
  onNavigate,
  ...shellProps
}) {
  const [periodo, setPeriodo] = useState(() => defaultPeriodo());
  const { data, loading, error, refresh, exportar } =
    useReportesPQRSD(session, { desde: periodo.desde, hasta: periodo.hasta });

  const [exporting, setExporting] = useState(false);
  const [exportInfo, setExportInfo] = useState(null);
  const puedeExportar = gdCanAny(roles, 'REP-004', 'RW');

  async function handleExportar(formato) {
    setExporting(true);
    setExportInfo(null);
    try {
      const r = await exportar(formato);
      setExportInfo({ ok: true, formato, ...r });
    } catch (err) {
      setExportInfo({ ok: false, error: err });
    } finally {
      setExporting(false);
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'PQRSD', path: '/gd/pqrsd' },
        { label: 'Reportes' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Reportes PQRSD</h1>
          <p className="subtitle">
            Tableros consolidados de Peticiones, Quejas, Reclamos,
            Sugerencias y Denuncias.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="rep-pqrsd-refresh"
          >
            Actualizar
          </button>
          {puedeExportar && (
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                type="button"
                className="btn btn-accent"
                onClick={() => handleExportar('csv')}
                disabled={exporting}
                data-testid="rep-pqrsd-csv"
              >Exportar CSV</button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleExportar('excel')}
                disabled={exporting}
                data-testid="rep-pqrsd-excel"
              >Excel</button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleExportar('pdf')}
                disabled={exporting}
                data-testid="rep-pqrsd-pdf"
              >PDF</button>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-5)' }}>
        <div style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'flex-end' }}>
          <div className="field" style={{ width: 180 }}>
            <label>Desde</label>
            <input
              type="date" className="input"
              value={periodo.desde}
              onChange={(e) => setPeriodo({ ...periodo, desde: e.target.value })}
              data-testid="rep-pqrsd-desde"
            />
          </div>
          <div className="field" style={{ width: 180 }}>
            <label>Hasta</label>
            <input
              type="date" className="input"
              value={periodo.hasta}
              onChange={(e) => setPeriodo({ ...periodo, hasta: e.target.value })}
              data-testid="rep-pqrsd-hasta"
            />
          </div>
        </div>
      </div>

      {exportInfo && (
        <div
          className={`alert ${exportInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="rep-pqrsd-export-info"
          style={{ marginBottom: 'var(--s-4)' }}
        >
          <div className="body">
            {exportInfo.ok
              ? <>Exportación encolada (formato <strong>{exportInfo.formato}</strong>).</>
              : <>No se pudo exportar: {exportInfo.error?.message || 'Error.'}</>}
          </div>
        </div>
      )}

      {loading && <p className="muted">Cargando reportes…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error al cargar.'}</div>
        </div>
      )}

      {data && (
        <>
          <div
            data-testid="rep-pqrsd-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}
          >
            <Kpi label="Total periodo" value={data.totales?.total ?? 0} />
            <Kpi label="Cerradas a tiempo" value={data.totales?.cerradas_a_tiempo ?? 0} tone="ok" />
            <Kpi label="Vencidas" value={data.totales?.vencidas ?? 0} tone="danger" />
            <Kpi label="% cumplimiento" value={fmtPct(data.totales?.cumplimiento)} />
            <Kpi label="Tiempo medio respuesta" value={fmtHoras(data.totales?.tiempo_medio_respuesta_h)} />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Por tipo (P/Q/R/S/D)</h3>
            <SimpleBars items={data.por_tipo || []} fieldName="tipo" fieldValue="total" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Top dependencias</h3>
            <SimpleBars items={data.por_dependencia || []} fieldName="dependencia" fieldValue="total" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Por canal</h3>
            <SimpleBars items={data.por_canal || []} fieldName="canal" fieldValue="total" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Distribución del tiempo de respuesta</h3>
            <SimpleBars items={data.por_tiempo || []} fieldName="rango" fieldValue="cantidad" />
          </div>
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function SimpleBars({ items, fieldName, fieldValue }) {
  if (!items || items.length === 0) {
    return <p className="muted">Sin datos.</p>;
  }
  const max = items.reduce((m, it) => Math.max(m, it[fieldValue] || 0), 0);
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="rep-pqrsd-bars">
      {items.map((it, i) => {
        const v = it[fieldValue] || 0;
        const pct = max > 0 ? (v / max) * 100 : 0;
        return (
          <li key={`${it[fieldName]}-${i}`} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span>{it[fieldName]}</span>
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

function fmtHoras(h) {
  if (h == null) return '—';
  if (h < 1) return `${Math.round(h * 60)}min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function fmtPct(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(1)}%`;
  return `${v.toFixed(1)}%`;
}

export default ReportesPQRSD;
