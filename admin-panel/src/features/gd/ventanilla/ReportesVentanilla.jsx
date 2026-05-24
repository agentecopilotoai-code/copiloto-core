/**
 * ReportesVentanilla — GD-UI-0014. Tableros de KPIs + tablas + exportación.
 *
 * KPIs principales:
 *  - Radicados por fecha (totales del periodo + delta).
 *  - Radicados por canal (gráfico simple stacked).
 *  - Radicados por dependencia (top 5).
 *  - Anulaciones por motivo (top 5).
 *  - Reasignaciones del periodo.
 *
 * Exportar PDF/Excel/CSV (PERM-REP-004). Encola job en backend → devuelve
 * `export_id` y notifica al completarse (worker async — bloque UI-14 cubre
 * UX de notificaciones para esto).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useReportesVentanilla } from './useGdRadicados.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function ReportesVentanilla({
  session,
  roles = [],
  onNavigate,
  ...shellProps
}) {
  const [periodo, setPeriodo] = useState(() => defaultPeriodo());
  const { data, loading, error, exportar, refresh } =
    useReportesVentanilla(session, { desde: periodo.desde, hasta: periodo.hasta });

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
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Reportes' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Reportes de Ventanilla</h1>
          <p className="subtitle">
            Tableros agregados para análisis del flujo de radicación.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="rep-refresh"
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
                data-testid="rep-exportar-csv"
              >
                Exportar CSV
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleExportar('excel')}
                disabled={exporting}
                data-testid="rep-exportar-excel"
              >
                Excel
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleExportar('pdf')}
                disabled={exporting}
                data-testid="rep-exportar-pdf"
              >
                PDF
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-5)' }}>
        <div style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'flex-end' }}>
          <div className="field" style={{ width: 180 }}>
            <label>Desde</label>
            <input
              type="date"
              className="input"
              value={periodo.desde}
              onChange={(e) => setPeriodo({ ...periodo, desde: e.target.value })}
              data-testid="rep-desde"
            />
          </div>
          <div className="field" style={{ width: 180 }}>
            <label>Hasta</label>
            <input
              type="date"
              className="input"
              value={periodo.hasta}
              onChange={(e) => setPeriodo({ ...periodo, hasta: e.target.value })}
              data-testid="rep-hasta"
            />
          </div>
        </div>
      </div>

      {exportInfo && (
        <div
          className={`alert ${exportInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="rep-export-info"
          style={{ marginBottom: 'var(--s-4)' }}
        >
          <div className="body">
            {exportInfo.ok
              ? <>Exportación encolada (formato <strong>{exportInfo.formato}</strong>). El archivo se enviará por notificación cuando esté listo.</>
              : <>No se pudo iniciar la exportación: {exportInfo.error?.message || 'Error.'}</>}
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
            data-testid="rep-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}
          >
            <Kpi label="Radicados periodo" value={data.totales?.radicados ?? 0} />
            <Kpi label="Anulaciones" value={data.totales?.anulaciones ?? 0} />
            <Kpi label="Reasignaciones" value={data.totales?.reasignaciones ?? 0} />
            <Kpi label="Tiempo medio cierre" value={fmtHoras(data.totales?.tiempo_medio_cierre_h)} />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Por canal</h3>
            <SimpleBars items={data.por_canal || []} fieldName="canal" fieldValue="total" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Top 5 dependencias</h3>
            <SimpleBars items={data.por_dependencia || []} fieldName="dependencia" fieldValue="total" />
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Anulaciones por motivo</h3>
            {(data.anulaciones_por_motivo || []).length === 0 ? (
              <p className="muted">Sin anulaciones en el periodo.</p>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {data.anulaciones_por_motivo.map((m) => (
                  <li
                    key={m.motivo}
                    style={{ padding: '4px 0', display: 'flex', justifyContent: 'space-between' }}
                  >
                    <span>{m.motivo}</span>
                    <span className="num">{m.total}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function SimpleBars({ items, fieldName, fieldValue }) {
  if (!items || items.length === 0) {
    return <p className="muted">Sin datos.</p>;
  }
  const max = items.reduce((m, it) => Math.max(m, it[fieldValue] || 0), 0);
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="simple-bars">
      {items.map((it, i) => {
        const v = it[fieldValue] || 0;
        const pct = max > 0 ? (v / max) * 100 : 0;
        return (
          <li key={`${it[fieldName]}-${i}`} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span>{it[fieldName]}</span>
              <span className="num">{v}</span>
            </div>
            <div
              style={{
                background: 'var(--slate-100)',
                borderRadius: 'var(--r-sm)',
                height: 8,
                overflow: 'hidden',
                marginTop: 2,
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: 'var(--accent-base)',
                }}
              />
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

export default ReportesVentanilla;
