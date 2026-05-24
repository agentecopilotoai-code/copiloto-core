/**
 * VistaAuditor — GD-UI-0071. Landing del rol Auditor Externo.
 *
 * Vista resumen de integridad del módulo:
 *  - Total de registros sellados por entidad
 *  - Hash raíz del módulo (sello Merkle de todos los registros)
 *  - % de registros con integridad verificada vs. comprometida
 *  - Accesos rápidos a Auditoría y Reportes consolidados (read-only)
 *
 * El auditor externo NO tiene RW sobre nada — solo R. La vista
 * resalta los hashes y enlaza a herramientas de verificación.
 */
import React from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useResumenIntegridadAuditor } from './useGdAuditoria.js';

export function VistaAuditor({ session, onNavigate, ...shellProps }) {
  const { data, loading, error, refresh } =
    useResumenIntegridadAuditor(session);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Vista Auditor' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Vista del Auditor Externo</h1>
          <p className="subtitle">
            Resumen de integridad del módulo. Todos los registros se
            sellan con SHA-256 al crearse; las cadenas de hash
            permiten detectar cualquier alteración posterior.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="aud-vista-refresh"
          >Actualizar</button>
        </div>
      </div>

      {loading && <p className="muted">Cargando resumen…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <>
          <div className="alert info" data-testid="aud-vista-banner">
            <div className="body">
              <strong>Hash raíz actual del módulo:</strong>{' '}
              <code data-testid="aud-vista-hash-raiz">{data.hash_raiz || '—'}</code>
              {data.calculado_en && (
                <> · Calculado el {fmt(data.calculado_en)}</>
              )}
            </div>
          </div>

          <div data-testid="aud-vista-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginTop: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}
          >
            <Kpi label="Registros sellados" value={data.total_registros ?? 0} />
            <Kpi label="Verificados (íntegros)" value={data.verificados ?? 0} tone="ok" />
            <Kpi label="Discrepancias" value={data.discrepancias ?? 0}
              tone={data.discrepancias > 0 ? 'danger' : 'ok'} />
            <Kpi label="% integridad" value={fmtPct(data.porcentaje_integridad)}
              tone={data.porcentaje_integridad < 1 ? 'warn' : 'ok'} />
          </div>

          {(data.por_entidad || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Por tipo de entidad</h3>
              <table className="data-table" data-testid="aud-vista-tabla">
                <thead>
                  <tr>
                    <th>Entidad</th>
                    <th>Registros</th>
                    <th>Verificados</th>
                    <th>Discrepancias</th>
                    <th>Hash raíz parcial</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_entidad.map((e) => (
                    <tr key={e.entidad} data-testid="aud-vista-row">
                      <td>{e.entidad}</td>
                      <td className="num">{e.total}</td>
                      <td className="num">{e.verificados}</td>
                      <td className="num">
                        {e.discrepancias > 0 ? (
                          <span className="badge danger">{e.discrepancias}</span>
                        ) : (
                          <span className="badge ok">0</span>
                        )}
                      </td>
                      <td><code style={{ fontSize: 11 }}>{(e.hash_raiz || '').slice(0, 16)}…</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Herramientas del auditor</h3>
            <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-secondary"
                onClick={() => onNavigate?.('/gd/auditoria')}
                data-testid="aud-vista-ir-auditoria"
              >Bandeja de auditoría</button>
              <button type="button" className="btn btn-secondary"
                onClick={() => onNavigate?.('/gd/reportes')}
                data-testid="aud-vista-ir-reportes"
              >Reportes consolidados</button>
            </div>
          </div>
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi" data-testid="aud-vista-kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function fmtPct(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(2)}%`;
  return `${v.toFixed(2)}%`;
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default VistaAuditor;
