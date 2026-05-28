/**
 * SaludCorreo — GD-UI-0086. Dashboard de salud del canal de correo.
 *
 * KPIs globales (recibidos/enviados/bounces) + tabla por canal con
 * ok_pct, latencia p50/p99, errores 24h, último error. Selector de
 * ventana (24h, 7d, 30d).
 *
 * Read-only para todos los roles con COR-EMAIL-006 R (admin sistema,
 * admin seguridad, coordinador VU, auditor).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import { useSaludCorreo } from './useGdCorreo.js';

const VENTANAS = ['24h', '7d', '30d'];

export function SaludCorreo({
  session, roles = [], ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'COR-EMAIL-006', 'R');
  const [ventana, setVentana] = useState('24h');
  const s = useSaludCorreo(session, ventana);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Salud canal correo' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Salud del canal de correo</h1>
          <p className="subtitle">
            Métricas operativas de cada canal SMTP/IMAP: tasa de
            éxito, latencias, bounces y errores recientes.
          </p>
        </div>
        <div className="actions">
          <label style={{ fontSize: 12 }}>
            Ventana{' '}
            <select value={ventana} onChange={(e) => setVentana(e.target.value)}
              data-testid="cor-sal-ventana"
            >
              {VENTANAS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <button type="button" className="btn btn-secondary"
            onClick={s.refresh}
            data-testid="cor-sal-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="cor-sal-no-perm"
        >
          <div className="body">No tienes permiso para ver salud del correo.</div>
        </div>
      )}

      {tienePermiso && s.loading && <p className="muted">Cargando…</p>}
      {tienePermiso && s.error && (
        <div className="alert danger" role="alert"
          data-testid="cor-sal-error"
        >
          <div className="body">{s.error.message}</div>
        </div>
      )}

      {tienePermiso && s.data && (
        <>
          {s.data.totales && (
            <div data-testid="cor-sal-kpis"
              style={{ display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 'var(--s-3)', marginBottom: 'var(--s-4)' }}
            >
              <div className="kpi">
                <div className="label">Recibidos</div>
                <div className="value">{(s.data.totales.recibidos ?? 0).toLocaleString('es-CO')}</div>
              </div>
              <div className="kpi">
                <div className="label">Enviados</div>
                <div className="value">{(s.data.totales.enviados ?? 0).toLocaleString('es-CO')}</div>
              </div>
              <div className="kpi">
                <div className="label">Bounces</div>
                <div className={`value ${(s.data.totales.bounces ?? 0) > 0 ? 'warn' : ''}`}>
                  {s.data.totales.bounces ?? 0}
                </div>
              </div>
            </div>
          )}

          {(s.data.canales || []).length > 0 && (
            <table className="data-table" data-testid="cor-sal-tabla">
              <thead>
                <tr>
                  <th>Canal</th>
                  <th className="num">OK %</th>
                  <th className="num">Bounces</th>
                  <th className="num">Errores</th>
                  <th className="num">p50</th>
                  <th className="num">p99</th>
                  <th>Último error</th>
                </tr>
              </thead>
              <tbody>
                {s.data.canales.map((c) => (
                  <tr key={c.id} data-testid="cor-sal-row">
                    <td>{c.nombre || c.id}</td>
                    <td className="num">
                      <span className={`badge ${
                        (c.ok_pct ?? 1) >= 0.95 ? 'ok'
                          : (c.ok_pct ?? 1) >= 0.8 ? 'warn' : 'danger'
                      }`}>
                        {((c.ok_pct ?? 0) * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="num">{c.bounces ?? 0}</td>
                    <td className="num">{c.errores_24h ?? 0}</td>
                    <td className="num">{c.latencia_p50 ?? '—'}</td>
                    <td className="num">{c.latencia_p99 ?? '—'}</td>
                    <td>
                      {c.ultimo_error
                        ? <code style={{ fontSize: 11 }}>{c.ultimo_error}</code>
                        : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {(s.data.canales || []).length === 0 && (
            <div className="empty" data-testid="cor-sal-empty">
              <p className="muted">Sin canales con datos en esta ventana.</p>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

export default SaludCorreo;
