/**
 * ReportesConsolidados — GD-UI-0069/0070.
 *
 * Tableros agregados cruzados: PQRSD + Ventanilla + Documentos +
 * Expedientes. Filtros por periodo + dependencia.
 *
 * Exportación PDF ejecutivo (GD-UI-0070) con firma institucional
 * (sello, logo, hash del periodo). REP-008.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useReportesConsolidados,
  useExportarReporteConsolidado,
  useExportarReporteEjecutivoPdf,
} from './useGdAuditoria.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function ReportesConsolidados({ session, roles = [], ...shellProps }) {
  const [periodo, setPeriodo] = useState(() => defaultPeriodo());
  const { data, loading, error, refresh } =
    useReportesConsolidados(session, periodo);
  const exportar = useExportarReporteConsolidado(session);
  const pdf = useExportarReporteEjecutivoPdf(session);
  const [exportInfo, setExportInfo] = useState(null);
  const puedeExportar = gdCanAny(roles, 'REP-008', 'RW');

  async function handleExportar(formato) {
    setExportInfo(null);
    const hook = formato === 'pdf_ejecutivo' ? pdf : exportar;
    try {
      const r = await hook.submit({ ...periodo, formato });
      setExportInfo({ ok: true, formato, ...r });
    } catch (err) {
      setExportInfo({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Reportes consolidados' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Reportes consolidados</h1>
          <p className="subtitle">
            Indicadores cruzados de operación del módulo (Ventanilla,
            PQRSD, Documentos, Expedientes).
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="rep-refresh"
          >Actualizar</button>
          {puedeExportar && (
            <div style={{ display: 'flex', gap: 6 }}>
              <button type="button" className="btn btn-accent"
                onClick={() => handleExportar('csv')}
                disabled={exportar.submitting || pdf.submitting}
                data-testid="rep-csv"
              >CSV</button>
              <button type="button" className="btn btn-secondary"
                onClick={() => handleExportar('excel')}
                disabled={exportar.submitting || pdf.submitting}
                data-testid="rep-excel"
              >Excel</button>
              <button type="button" className="btn btn-secondary"
                onClick={() => handleExportar('pdf_ejecutivo')}
                disabled={exportar.submitting || pdf.submitting}
                data-testid="rep-pdf"
              >PDF ejecutivo</button>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'flex-end' }}>
          <div className="field" style={{ width: 180 }}>
            <label>Desde</label>
            <input type="date" className="input"
              value={periodo.desde}
              onChange={(e) => setPeriodo({ ...periodo, desde: e.target.value })}
              data-testid="rep-desde"
            />
          </div>
          <div className="field" style={{ width: 180 }}>
            <label>Hasta</label>
            <input type="date" className="input"
              value={periodo.hasta}
              onChange={(e) => setPeriodo({ ...periodo, hasta: e.target.value })}
              data-testid="rep-hasta"
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>Dependencia (opcional)</label>
            <input className="input"
              value={periodo.dependencia || ''}
              onChange={(e) => setPeriodo({ ...periodo, dependencia: e.target.value || undefined })}
              data-testid="rep-dep"
            />
          </div>
        </div>
      </div>

      {exportInfo && (
        <div
          className={`alert ${exportInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="rep-export-info"
          style={{ marginBottom: 'var(--s-3)' }}
        >
          <div className="body">
            {exportInfo.ok
              ? exportInfo.formato === 'pdf_ejecutivo'
                ? <>Reporte ejecutivo PDF encolado (incluye firma institucional + hash de periodo).</>
                : <>Exportación encolada (formato <strong>{exportInfo.formato}</strong>).</>
              : <>No se pudo exportar: {exportInfo.error?.message || 'error.'}</>
            }
            {exportInfo.url_descarga && (
              <> <a href={exportInfo.url_descarga} data-testid="rep-export-link">Descargar</a>.</>
            )}
          </div>
        </div>
      )}

      {loading && <p className="muted">Cargando reportes…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <>
          <div data-testid="rep-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}>
            <Kpi label="Radicados (entrada+salida)" value={data.radicados_total ?? 0} />
            <Kpi label="PQRSD periodo" value={data.pqrsd_total ?? 0} />
            <Kpi label="PQRSD vencidas" value={data.pqrsd_vencidas ?? 0} tone="danger" />
            <Kpi label="Documentos cargados" value={data.documentos_total ?? 0} />
            <Kpi label="Expedientes nuevos" value={data.expedientes_nuevos ?? 0} />
            <Kpi label="Expedientes cerrados" value={data.expedientes_cerrados ?? 0} tone="ok" />
            <Kpi label="% Cumplimiento PQRSD" value={fmtPct(data.pqrsd_cumplimiento)} />
            <Kpi label="Tiempo medio respuesta" value={fmtHoras(data.pqrsd_tiempo_medio_h)} />
          </div>

          {(data.por_dependencia || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Operación por dependencia</h3>
              <table className="data-table" data-testid="rep-dep-table">
                <thead>
                  <tr>
                    <th>Dependencia</th>
                    <th>Radicados</th>
                    <th>PQRSD</th>
                    <th>Documentos</th>
                    <th>Expedientes</th>
                    <th>% cumpl.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_dependencia.map((d, i) => (
                    <tr key={`${d.dependencia}-${i}`} data-testid="rep-dep-row">
                      <td>{d.dependencia}</td>
                      <td className="num">{d.radicados ?? 0}</td>
                      <td className="num">{d.pqrsd ?? 0}</td>
                      <td className="num">{d.documentos ?? 0}</td>
                      <td className="num">{d.expedientes ?? 0}</td>
                      <td className="num">{fmtPct(d.cumplimiento)}</td>
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
    <div className="kpi" data-testid="rep-kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone === 'danger' ? 'danger' : tone === 'ok' ? '' : ''}`}>
        {value}
      </div>
    </div>
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

function fmtPct(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(1)}%`;
  return `${v.toFixed(1)}%`;
}

function fmtHoras(h) {
  if (h == null) return '—';
  if (h < 1) return `${Math.round(h * 60)}min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

export default ReportesConsolidados;
