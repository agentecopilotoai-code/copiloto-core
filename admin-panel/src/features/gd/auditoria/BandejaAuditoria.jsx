/**
 * BandejaAuditoria — GD-UI-0067. Bandeja de auditoría filtrable.
 *
 * Filtros: actor (usuario), entidad (tipo + id), acción, rango de
 * fechas, IP. Exportar CSV/Excel (REP-008 / AUD-005). Click en fila
 * navega a la ficha del evento.
 *
 * Integridad RNF-009: cada fila se vincula a su evento con hash
 * SHA-256 que la ficha valida en vivo.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useAuditoriaBandeja,
  useCatalogosAuditoria,
  useExportarAuditoria,
} from './useGdAuditoria.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function BandejaAuditoria({ session, roles = [], onNavigate, ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, total, loading, error, refresh } =
    useAuditoriaBandeja(session, filtros);
  const cat = useCatalogosAuditoria(session);
  const exportar = useExportarAuditoria(session);
  const [exportInfo, setExportInfo] = useState(null);
  const puedeExportar = gdCanAny(roles, 'AUD-005', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  async function handleExportar(formato) {
    setExportInfo(null);
    try {
      const r = await exportar.submit({ ...filtros, formato });
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
        { label: 'Auditoría' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Auditoría del sistema</h1>
          <p className="subtitle">
            {total} evento(s) registrado(s) con los criterios actuales.
            Cada evento es inalterable y queda sellado con hash SHA-256.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="aud-refresh"
          >Actualizar</button>
          {puedeExportar && (
            <div style={{ display: 'flex', gap: 6 }}>
              <button type="button" className="btn btn-accent"
                disabled={exportar.submitting}
                onClick={() => handleExportar('csv')}
                data-testid="aud-export-csv"
              >Exportar CSV</button>
              <button type="button" className="btn btn-secondary"
                disabled={exportar.submitting}
                onClick={() => handleExportar('excel')}
                data-testid="aud-export-excel"
              >Excel</button>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 'var(--s-3)',
          }}
        >
          <div className="field">
            <label>Actor (correo o id)</label>
            <input className="input"
              value={filtros.actor || ''}
              onChange={(e) => update('actor', e.target.value)}
              data-testid="aud-filter-actor"
            />
          </div>
          <div className="field">
            <label>Entidad</label>
            <select className="select"
              value={filtros.entidad_tipo || ''}
              onChange={(e) => update('entidad_tipo', e.target.value)}
              data-testid="aud-filter-entidad"
            >
              <option value="">Todas</option>
              {cat.entidades.map((e) => (
                <option key={e.codigo || e} value={e.codigo || e}>
                  {e.nombre || e.codigo || e}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Acción</label>
            <select className="select"
              value={filtros.accion || ''}
              onChange={(e) => update('accion', e.target.value)}
              data-testid="aud-filter-accion"
            >
              <option value="">Todas</option>
              {cat.acciones.map((a) => (
                <option key={a.codigo || a} value={a.codigo || a}>
                  {a.nombre || a.codigo || a}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>UUID entidad</label>
            <input className="input"
              value={filtros.entidad_id || ''}
              onChange={(e) => update('entidad_id', e.target.value)}
              data-testid="aud-filter-entid"
            />
          </div>
          <div className="field">
            <label>IP</label>
            <input className="input"
              value={filtros.ip || ''}
              onChange={(e) => update('ip', e.target.value)}
              data-testid="aud-filter-ip"
            />
          </div>
          <div className="field">
            <label>Desde</label>
            <input type="date" className="input"
              value={filtros.desde || ''}
              onChange={(e) => update('desde', e.target.value)}
              data-testid="aud-filter-desde"
            />
          </div>
          <div className="field">
            <label>Hasta</label>
            <input type="date" className="input"
              value={filtros.hasta || ''}
              onChange={(e) => update('hasta', e.target.value)}
              data-testid="aud-filter-hasta"
            />
          </div>
        </div>
      </div>

      {exportInfo && (
        <div
          className={`alert ${exportInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="aud-export-info"
          style={{ marginBottom: 'var(--s-3)' }}
        >
          <div className="body">
            {exportInfo.ok
              ? <>Exportación encolada (formato <strong>{exportInfo.formato}</strong>).</>
              : <>No se pudo exportar: {exportInfo.error?.message || 'error.'}</>
            }
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="aud-empty" style={{ margin: 'var(--s-4)' }}>
            <p>No hay eventos con esos criterios.</p>
          </div>
        )}
        {items.length > 0 && (
          <table className="data-table" data-testid="aud-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Actor</th>
                <th>Acción</th>
                <th>Entidad</th>
                <th>IP</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {items.map((ev) => (
                <tr
                  key={ev.id}
                  data-testid="aud-row"
                  onClick={() => onNavigate?.(`/gd/auditoria/${ev.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{fmt(ev.created_at || ev.timestamp)}</td>
                  <td>{ev.actor_email || ev.actor_id || '—'}</td>
                  <td><span className="badge">{ev.accion}</span></td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {ev.entidad_tipo}{ev.entidad_id ? ` · ${ev.entidad_id.slice(0, 8)}…` : ''}
                  </td>
                  <td>{ev.ip || '—'}</td>
                  <td>
                    <code style={{ fontSize: 11 }}>
                      {(ev.hash || '').slice(0, 12)}{ev.hash ? '…' : '—'}
                    </code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </GdShell>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default BandejaAuditoria;
