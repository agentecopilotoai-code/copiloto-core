/**
 * SaludSistema — GD-UI-0066. Tablero de salud del sistema.
 *
 * Uptime, latencia, errores recientes, colas, integraciones.
 * Permisos: SAL-001 (R) — admin sistema, admin seguridad, auditor.
 */
import React from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useSaludSistema } from './useGdAdmin.js';

export function SaludSistema({ session, ...shellProps }) {
  const { data, loading, error, refresh } = useSaludSistema(session);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Salud del sistema' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Salud del sistema</h1>
          <p className="subtitle">
            Indicadores de operación del módulo de Gestión Documental.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="sal-refresh"
          >Actualizar</button>
        </div>
      </div>

      {loading && <p className="muted">Cargando indicadores…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <>
          <div
            data-testid="sal-kpis"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-4)',
              marginBottom: 'var(--s-5)',
            }}
          >
            <Kpi label="Uptime" value={data.uptime || '—'} tone="ok" />
            <Kpi label="Latencia API (p95)" value={data.latencia_p95_ms ? `${data.latencia_p95_ms} ms` : '—'} />
            <Kpi label="Errores (24h)" value={data.errores_24h ?? 0}
              tone={data.errores_24h > 50 ? 'danger' : 'ok'} />
            <Kpi label="Sesiones activas" value={data.sesiones_activas ?? 0} />
            <Kpi label="Cola notificaciones" value={data.cola_notificaciones ?? 0}
              tone={data.cola_notificaciones > 1000 ? 'warn' : 'ok'} />
            <Kpi label="Tareas pendientes" value={data.tareas_pendientes ?? 0} />
          </div>

          {(data.servicios || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Servicios</h3>
              <table className="data-table" data-testid="sal-servicios">
                <thead>
                  <tr>
                    <th>Servicio</th>
                    <th>Estado</th>
                    <th>Última verificación</th>
                    <th>Latencia</th>
                  </tr>
                </thead>
                <tbody>
                  {data.servicios.map((s) => (
                    <tr key={s.nombre} data-testid="sal-servicio">
                      <td>{s.nombre}</td>
                      <td>
                        <span className={`badge ${badgeTone(s.estado)}`}>
                          {s.estado}
                        </span>
                      </td>
                      <td>{s.checked_at}</td>
                      <td className="num">{s.latencia_ms ? `${s.latencia_ms} ms` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(data.alertas || []).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-5)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Alertas recientes</h3>
              <ul data-testid="sal-alertas" style={{ margin: 0, paddingLeft: 16 }}>
                {data.alertas.map((a, i) => (
                  <li key={i} style={{ fontSize: 13, marginBottom: 4 }}>
                    <span className={`badge ${a.nivel === 'critica' ? 'danger' : 'info'}`}>
                      {a.nivel}
                    </span>{' '}
                    <strong>{a.titulo}</strong> — {a.mensaje}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="kpi" data-testid="sal-kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : ''}`}>
        {value}
      </div>
    </div>
  );
}

function badgeTone(estado) {
  if (estado === 'ok' || estado === 'up') return 'ok';
  if (estado === 'degradado') return 'warn';
  if (estado === 'down') return 'danger';
  return 'info';
}

export default SaludSistema;
